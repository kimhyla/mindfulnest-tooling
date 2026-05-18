#!/usr/bin/env python3
"""Generate OpenAPI 3.0 YAML from production_server.py dispatch table.

V59 Phase 1 §1 — walks do_GET (~line 5614) and do_POST (~line 5759) extracting:
  - `if path == "/api/foo": return self._handle_foo()`  → /api/foo GET
  - `if path.startswith("/api/foo/"): ...`              → /api/foo/{param} GET
  - `if path.startswith("/api/foo") and path.endswith("/bar"): ...` → /api/foo/{id}/bar
  - elif chains in both methods

For each route, finds the handler method docstring (if any) and emits a brief summary.
Writes Production/openapi/production_server.yaml.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
SERVER_PATH = ROOT / "tools" / "production_server.py"
OUT_DIR = ROOT / "openapi"
OUT_PATH = OUT_DIR / "production_server.yaml"

RE_EXACT = re.compile(
    r'^\s*(?:if|elif)\s+path\s*==\s*"([^"]+)"\s*:',
    re.MULTILINE,
)
RE_EXACT_INLINE = re.compile(r'path\s*==\s*"([^"]+)"')
RE_STARTSWITH = re.compile(
    r'^\s*(?:if|elif)\s+path\.startswith\("([^"]+)"\)\s*(?!and\s+path\.endswith)',
    re.MULTILINE,
)
RE_START_END = re.compile(
    r'^\s*(?:if|elif)\s+path\.startswith\("([^"]+)"\)\s+and\s+path\.endswith\("([^"]+)"\)\s*:',
    re.MULTILINE,
)
RE_PATH_IN = re.compile(r'path\s+in\s+\(([^)]+)\)')
HANDLER_CALL_RE = re.compile(
    r"return\s+self\.(_handle_[A-Za-z_][\w]*|_serve_[A-Za-z_][\w]*)\s*\("
)
HANDLER_DEF_RE = re.compile(r"def\s+(_handle_[A-Za-z_][\w]*)\s*\(")


@dataclass(frozen=True)
class Route:
    path: str
    method: str
    handler: str
    summary: str
    line: int


def _repo_root() -> Path:
    return REPO_ROOT


def _extract_method_block(src: str, method_name: str) -> str:
    """Return source slice for do_GET or do_POST body."""
    m = re.search(rf"def {method_name}\(self\).*?:", src)
    if not m:
        return ""
    start = m.end()
    # Next sibling method at class indent (4 spaces + def)
    nxt = re.search(r"\n    def \w+\(", src[start:])
    end = start + nxt.start() if nxt else len(src)
    return src[start:end]


def _openapi_path(prefix: str, suffix: str = "") -> str:
    """Convert dispatch prefix/suffix to OpenAPI path template."""
    if suffix:
        p = prefix.rstrip("/")
        s = suffix if suffix.startswith("/") else f"/{suffix}"
        if p.endswith("/"):
            return f"{p}{{{'id'}}}{s}"
        return f"{p}/{{id}}{s}"
    if prefix.endswith("/"):
        return f"{prefix}{'{param}'}"
    return f"{prefix}/{{param}}"


def _handler_summaries(src: str) -> dict[str, str]:
    summaries: dict[str, str] = {}
    for m in HANDLER_DEF_RE.finditer(src):
        name = m.group(1)
        rest = src[m.end() : m.end() + 800]
        doc = re.match(r'\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', rest, re.DOTALL)
        if doc:
            first = doc.group(1).strip().split("\n")[0].strip()
            if first:
                summaries[name] = first
    return summaries


def _summary_for(handler: str, path: str, summaries: dict[str, str]) -> str:
    if handler in summaries:
        return summaries[handler]
    parts = path.strip("/").split("/")
    tail = parts[-1] if parts else "root"
    return f"{handler.replace('_handle_', '').replace('_', ' ')} — {tail}"


def _operation_id(method: str, path: str) -> str:
    slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"{method.lower()}_{slug or 'root'}"


def _pair_handler(block: str, line_no: int, window: int = 8) -> Optional[str]:
    lines = block.splitlines()
    idx = line_no - 1
    for off in range(window):
        if idx + off >= len(lines):
            break
        hm = HANDLER_CALL_RE.search(lines[idx + off])
        if hm:
            return hm.group(1)
    return None


def _collect_routes(block: str, http_method: str, summaries: dict[str, str]) -> list[Route]:
    routes: list[Route] = []
    seen: set[tuple[str, str]] = set()

    def add(path: str, line: int) -> None:
        handler = _pair_handler(block, line) or "_handle_unknown"
        key = (http_method, path)
        if key in seen:
            return
        seen.add(key)
        routes.append(
            Route(
                path=path,
                method=http_method,
                handler=handler,
                summary=_summary_for(handler, path, summaries),
                line=line,
            )
        )

    for m in RE_START_END.finditer(block):
        line = block.count("\n", 0, m.start()) + 1
        add(_openapi_path(m.group(1), m.group(2)), line)

    for m in RE_STARTSWITH.finditer(block):
        line = block.count("\n", 0, m.start()) + 1
        add(_openapi_path(m.group(1)), line)

    for m in RE_EXACT.finditer(block):
        line = block.count("\n", 0, m.start()) + 1
        add(m.group(1), line)

    # `if path == "/a" or path == "/":` — secondary exact paths on same line block
    for m in re.finditer(r"^\s*if\s+path\s*==", block, re.MULTILINE):
        line_start = m.start()
        line_end = block.find("\n", line_start)
        line_text = block[line_start:line_end if line_end != -1 else None]
        for em in RE_EXACT_INLINE.finditer(line_text):
            path = em.group(1)
            line = block.count("\n", 0, line_start) + 1
            add(path, line)
        pim = RE_PATH_IN.search(line_text)
        if pim:
            for quoted in re.findall(r'"([^"]+)"', pim.group(1)):
                line = block.count("\n", 0, line_start) + 1
                add(quoted, line)

    return routes


def parse_dispatch_routes(server_path: Path) -> tuple[list[Route], list[Route]]:
    src = server_path.read_text(encoding="utf-8")
    summaries = _handler_summaries(src)
    get_block = _extract_method_block(src, "do_GET")
    post_block = _extract_method_block(src, "do_POST")
    get_routes = _collect_routes(get_block, "get", summaries)
    post_routes = _collect_routes(post_block, "post", summaries)
    return get_routes, post_routes


def _build_openapi_doc(get_routes: list[Route], post_routes: list[Route]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for route in get_routes + post_routes:
        entry = paths.setdefault(route.path, {})
        op: dict[str, Any] = {
            "summary": route.summary,
            "operationId": _operation_id(route.method, route.path),
            "responses": {
                "200": {"description": "ok"},
                "4XX": {"description": "client error"},
                "5XX": {"description": "server error"},
            },
        }
        if route.method == "post":
            op["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"type": "object"}},
                },
            }
        entry[route.method] = op
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "MindfulNest Production Server",
            "version": "V59",
            "description": (
                "Auto-generated from production_server.py do_GET/do_POST dispatch (Phase 1 §1)"
            ),
        },
        "servers": [{"url": "http://localhost:5111"}],
        "paths": dict(sorted(paths.items())),
    }


def _emit_yaml(doc: dict[str, Any], dest: Path) -> None:
    try:
        import yaml  # type: ignore
    except ImportError:
        import json

        dest.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print("WARN: pyyaml not installed; wrote JSON-equivalent", file=sys.stderr)
        return
    dest.write_text(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False), encoding="utf-8")


def main() -> int:
    if not SERVER_PATH.is_file():
        print(f"ERROR: missing {SERVER_PATH}", file=sys.stderr)
        return 2
    get_routes, post_routes = parse_dispatch_routes(SERVER_PATH)
    doc = _build_openapi_doc(get_routes, post_routes)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _emit_yaml(doc, OUT_PATH)
    print(
        f"OPENAPI_GENERATED routes_get={len(get_routes)} routes_post={len(post_routes)} "
        f"path={OUT_PATH.relative_to(_repo_root())}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

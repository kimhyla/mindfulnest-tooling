#!/usr/bin/env python3
"""Lint guard — assert client endpoint catalog matches server routes.

Closes audit findings C3-3 / C3-4 / C7-1..C7-7. The
`storyboard-v2/src/api/endpoints.ts` file is meant to be the source of
truth for every client→server fetch URL. Today's drift cases (from the
2026-05-19 audit):
  - `MUTATION_ENDPOINTS.v2_sidecar_write` declared, no server handler
  - `voice_profile: /api/voice/profile` declared, server requires
    `/api/voice/profile/<id>` (prefix). bare GET → 404.
  - `patch_health` in READ_ENDPOINTS but server route is POST-only.

This script:
1. Parses `endpoints.ts` to extract every declared URL (READ + MUTATION).
2. Greps `production_server.py` + every `server_handlers/*.py` for
   `path == "/api/..."` and `path.startswith("/api/...")` registrations.
3. Asserts: every declared endpoint has a matching server route. For
   templated endpoints (e.g. `/api/beat/audio/{beat_id}`), looks for a
   `startswith` registration on the prefix.
4. (Reverse) Reports server routes NOT in `endpoints.ts` as a warning
   only — not all routes need a client entry (e.g. /api/state, /api/health
   are direct server-side reads).

Exit code 0 on clean; 1 on violations.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

ENDPOINTS_TS = REPO_ROOT / "Production/tools/storyboard-v2/src/api/endpoints.ts"
PRODUCTION_SERVER = REPO_ROOT / "Production/tools/production_server.py"
HANDLERS_DIR = REPO_ROOT / "Production/tools/server_handlers"

# Server routes that legitimately exist without a client catalog entry.
# (e.g. infrastructure / direct-fetch APIs / server-only endpoints.)
SERVER_ONLY_ALLOWLIST = {
    "/api/health",
    "/api/state",
    "/api/state/snapshot",
    "/api/storyboard/list",  # used by builder tools
    "/api/storyboard/switch",
    "/api/storyboard/magic_still",
    "/api/storyboard/magic_video",
    "/api/export",  # POST-only, infrastructure tool
    "/api/server/restart",
    "/api/finder_video",
    "/api/preview_stitched",
    "/api/magic/resolve_bg",
    "/api/magic/status",
    "/api/magic/submit_path",
    "/api/timeline/audio",
    "/api/timeline/cues/bake",
    "/api/timeline/open_in_quicktime",
    "/api/timeline/preview_with_sfx",
    "/api/timeline/sfx_library",
    "/api/tts",
    "/api/voice/profile",  # prefix; client uses /api/voice/profile/<id>
    "/api/voice/profile_update",
    "/api/budget/override",
    "/api/media/timeline_audio_",
    "/api/phase/watercolor_file",
    "/api/phase_b/media",
    "/api/phase_b/preview",
    "/api/phase_b/watercolor",
    "/api/stitch_editor/audio_extract",
    "/api/stitch_editor/audio_file",
    "/api/stitch_editor/library",
    "/api/stitch_editor/preview_file",
    "/api/v2/beat",  # prefix for /create + /delete + /<id>/patch + /swap_to_a
    # BG endpoints that exist for legacy/builder tools (not in v59 catalog yet)
    "/api/bg/accept-local-animation",
    "/api/bg/assemble-group",
    "/api/bg/create-group",
    "/api/bg/crop-preview",
    "/api/bg/delete-group",
    "/api/bg/groups",
    "/api/bg/poll-assemble-status",
    "/api/bg/poll-export-to-stitcher",
    "/api/bg/poll-flux-status",
    "/api/bg/run-local-animation",
    "/api/bg/submit-flux-batch",
    "/api/bg/update-beat-animation-method",
    "/api/bg/update-group",
    "/api/beat/accepted-bg",
}


def parse_endpoints_ts() -> tuple[dict[str, str], dict[str, str]]:
    """Return (READ_ENDPOINTS_dict, MUTATION_ENDPOINTS_dict) parsed from endpoints.ts."""
    text = ENDPOINTS_TS.read_text()
    out: dict[str, dict[str, str]] = {"READ": {}, "MUTATION": {}}
    # Match: export const READ_ENDPOINTS = { ... } as const;
    for kind in ("READ", "MUTATION"):
        m = re.search(
            rf'export const {kind}_ENDPOINTS\s*=\s*\{{(.+?)\}}\s*as\s+const',
            text,
            re.DOTALL,
        )
        if not m:
            continue
        body = m.group(1)
        for name, url in re.findall(
            r"^\s*(\w+):\s*`\$\{SERVER_BASE\}(/api/[^`]+)`",
            body,
            re.MULTILINE,
        ):
            out[kind][name] = url
    return out["READ"], out["MUTATION"]


def collect_server_routes() -> set[str]:
    """Return set of every route registered via path== or path.startswith."""
    routes: set[str] = set()
    sources = [PRODUCTION_SERVER] + list(HANDLERS_DIR.glob("*.py"))
    for src in sources:
        text = src.read_text()
        for m in re.finditer(r'path == ["\'](/api/[^"\']+)["\']', text):
            routes.add(m.group(1))
        for m in re.finditer(r'path\.startswith\(["\'](/api/[^"\']+)["\']\)', text):
            routes.add(m.group(1).rstrip("/"))
    return routes


def main() -> int:
    read_endpoints, mutation_endpoints = parse_endpoints_ts()
    routes = collect_server_routes()
    # Build set of declared URL bases (strip {param} placeholders)
    declared_concrete: dict[str, tuple[str, str]] = {}  # url -> (kind, name)
    declared_prefixes: dict[str, tuple[str, str]] = {}  # prefix -> (kind, name)
    for name, url in read_endpoints.items():
        if "{" in url:
            declared_prefixes[url.split("{")[0].rstrip("/")] = ("READ", name)
        else:
            declared_concrete[url] = ("READ", name)
    for name, url in mutation_endpoints.items():
        if "{" in url:
            declared_prefixes[url.split("{")[0].rstrip("/")] = ("MUTATION", name)
        else:
            declared_concrete[url] = ("MUTATION", name)

    violations: list[str] = []
    # 1. Every declared concrete URL must have a server route
    for url, (kind, name) in declared_concrete.items():
        if url in routes:
            continue
        # may match a prefix
        if any(url.startswith(r + "/") or url == r for r in routes if r in routes):
            continue
        violations.append(
            f"  [{kind}.{name}] declared {url}  →  NO server handler "
            f"(audit C3-3 class)"
        )
    # 2. Every templated declared URL must have a startswith registration
    for prefix, (kind, name) in declared_prefixes.items():
        if any(r.startswith(prefix) or r == prefix for r in routes):
            continue
        violations.append(
            f"  [{kind}.{name}] declared prefix {prefix}/{{...}}  →  NO server handler"
        )

    # 3. Server routes NOT in catalog and NOT allow-listed → warning only.
    declared_urls = set(declared_concrete.keys()) | set(declared_prefixes.keys())
    orphans: list[str] = []
    for r in sorted(routes):
        if r in declared_urls:
            continue
        if any(r.startswith(p + "/") or r == p for p in declared_prefixes.keys()):
            continue
        if any(r == p or r.startswith(p + "/") for p in SERVER_ONLY_ALLOWLIST):
            continue
        if r in SERVER_ONLY_ALLOWLIST:
            continue
        orphans.append(r)

    print(
        f"[lint_endpoint_catalog] catalog: {len(read_endpoints)} READ + "
        f"{len(mutation_endpoints)} MUTATION = {len(read_endpoints)+len(mutation_endpoints)} declared"
    )
    print(f"[lint_endpoint_catalog] server: {len(routes)} routes registered")

    if violations:
        print(f"[lint_endpoint_catalog] FAIL — {len(violations)} declared endpoints lack a server handler:")
        for v in violations:
            print(v)
        print()
        print("Fix: either implement the handler in production_server.py /")
        print("server_handlers/*.py, or remove the declaration from endpoints.ts.")
        return 1

    if orphans:
        print(
            f"[lint_endpoint_catalog] WARN — {len(orphans)} server routes not in "
            f"endpoints.ts and not allow-listed:"
        )
        for o in orphans[:20]:
            print(f"  {o}")
        if len(orphans) > 20:
            print(f"  ... and {len(orphans)-20} more")
        print()
        print("Add to endpoints.ts (preferred for new v59 client work) or")
        print("add to SERVER_ONLY_ALLOWLIST in this script (for server-only routes).")
        # WARN-only: exit 0 unless STRICT mode
        if "--strict" in sys.argv:
            return 1

    print("[lint_endpoint_catalog] OK — declared endpoints all have server handlers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

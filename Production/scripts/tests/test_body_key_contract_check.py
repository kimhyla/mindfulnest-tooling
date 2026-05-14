"""Unit tests for body_key_contract_check.py.

Builds tiny synthetic projects on disk, runs the checker, asserts findings.
Stdlib only — no pytest fixtures needed beyond tmp_path.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "Production" / "scripts" / "body_key_contract_check.py"


def _scaffold(tmp_path: Path, server_py: str, endpoints_ts: str, tsx: dict[str, str]) -> Path:
    """Create a minimal project layout the checker can scan."""
    server = tmp_path / "Production" / "tools" / "production_server.py"
    server.parent.mkdir(parents=True, exist_ok=True)
    server.write_text(server_py, encoding="utf-8")
    endpoints = (
        tmp_path / "Production" / "tools" / "storyboard-v2" / "src" / "api" / "endpoints.ts"
    )
    endpoints.parent.mkdir(parents=True, exist_ok=True)
    endpoints.write_text(endpoints_ts, encoding="utf-8")
    components = tmp_path / "Production" / "tools" / "storyboard-v2" / "src" / "components"
    components.mkdir(parents=True, exist_ok=True)
    for name, body in tsx.items():
        (components / name).write_text(body, encoding="utf-8")
    return tmp_path


def _run(root: Path) -> tuple[int, dict]:
    """Run the checker against root, return (exit_code, parsed_json)."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 2:
        pytest.fail(f"infrastructure error: {res.stderr}")
    return res.returncode, json.loads(res.stdout)


ENDPOINTS_BOILERPLATE = textwrap.dedent("""\
    export const SERVER_BASE = 'http://localhost:5111';
    export const READ_ENDPOINTS = {{}} as const;
    export const MUTATION_ENDPOINTS = {{
    {entries}
    }} as const;
""")


def _endpoints(entries: dict[str, str]) -> str:
    body = "\n".join(f"  {name}: `${{SERVER_BASE}}{url}`," for name, url in entries.items())
    return ENDPOINTS_BOILERPLATE.format(entries=body)


SERVER_PROLOGUE = textwrap.dedent("""\
    class Handler:
        def do_POST(self):
            path = '?'
            body = {}
""")


def _server(routes: list[tuple[str, str, str]]) -> str:
    """routes: list of (url_path, handler_name, handler_body_indented)."""
    # do_POST stub with if/elif routing.
    lines = [SERVER_PROLOGUE]
    for url, handler, _ in routes:
        lines.append(f'        if path == "{url}":')
        lines.append(f"            return self.{handler}(body)")
    for _, handler, body in routes:
        lines.append("")
        lines.append(f"    def {handler}(self, body):")
        for raw in body.splitlines():
            lines.append("        " + raw if raw.strip() else raw)
    return "\n".join(lines) + "\n"


def test_clean_pair(tmp_path):
    root = _scaffold(
        tmp_path,
        server_py=_server([
            ("/api/echo", "_handle_echo", "x = body.get('foo')\ny = body.get('bar')"),
        ]),
        endpoints_ts=_endpoints({"echo": "/api/echo"}),
        tsx={
            "Use.tsx": textwrap.dedent("""\
                import { pathappPatch } from '../api/client';
                pathappPatch(scope, 'echo', { foo: 1, bar: 'x' });
            """),
        },
    )
    rc, report = _run(root)
    assert rc == 0, report
    assert report["mismatches"] == 0


def test_client_extra_key_caught(tmp_path):
    root = _scaffold(
        tmp_path,
        server_py=_server([
            ("/api/echo", "_handle_echo", "x = body.get('foo')"),
        ]),
        endpoints_ts=_endpoints({"echo": "/api/echo"}),
        tsx={
            "Use.tsx": "pathappPatch(scope, 'echo', { foo: 1, extra: 2 });",
        },
    )
    rc, report = _run(root)
    assert rc == 1
    kinds = {(i["kind"], i["key"]) for i in report["items"]}
    assert ("CLIENT_EXTRA", "extra") in kinds


def test_server_extra_key_caught(tmp_path):
    root = _scaffold(
        tmp_path,
        server_py=_server([
            ("/api/echo", "_handle_echo", "x = body.get('foo')\ny = body.get('legacy')"),
        ]),
        endpoints_ts=_endpoints({"echo": "/api/echo"}),
        tsx={"Use.tsx": "pathappPatch(scope, 'echo', { foo: 1 });"},
    )
    rc, report = _run(root)
    assert rc == 1
    kinds = {(i["kind"], i["key"]) for i in report["items"]}
    assert ("SERVER_EXTRA", "legacy") in kinds


def test_multi_key_backcompat_clean(tmp_path):
    """Server accepts both legacy and new key — both sides should pass when
    each side declares its intent."""
    root = _scaffold(
        tmp_path,
        server_py=_server([
            (
                "/api/delay",
                "_handle_delay",
                "# BODY_KEY_ALLOW: audio_delay legacy back-compat retained\n"
                "raw = body.get('audio_delay')\n"
                "if raw is None:\n"
                "    raw = body.get('delay_seconds', 0)",
            ),
        ]),
        endpoints_ts=_endpoints({"delay": "/api/delay"}),
        tsx={"Use.tsx": "pathappPatch(scope, 'delay', { delay_seconds: 1.5 });"},
    )
    rc, report = _run(root)
    assert rc == 0, report


def test_allowlist_exempts_client_extra(tmp_path):
    root = _scaffold(
        tmp_path,
        server_py=_server([
            ("/api/echo", "_handle_echo", "x = body.get('foo')"),
        ]),
        endpoints_ts=_endpoints({"echo": "/api/echo"}),
        tsx={
            "Use.tsx": (
                "// BODY_KEY_ALLOW: debug_marker only used by dev tooling\n"
                "pathappPatch(scope, 'echo', { foo: 1, debug_marker: true });"
            ),
        },
    )
    rc, report = _run(root)
    assert rc == 0, report


def test_run_mutation_wrapper_extracts_body(tmp_path):
    """runMutation auto-injects beat_id; the wire body still includes the
    explicit object literal keys."""
    root = _scaffold(
        tmp_path,
        server_py=_server([
            (
                "/api/beat/trim",
                "_handle_beat_trim",
                "b = body.get('beat_id')\nti = body.get('trim_in')\nto = body.get('trim_out')",
            ),
        ]),
        endpoints_ts=_endpoints({"beat_trim": "/api/beat/trim"}),
        tsx={
            "Use.tsx": (
                "const runMutation = async (label, endpoint, body) => {};\n"
                "runMutation('Trim', 'beat_trim', { trim_in: 0.1, trim_out: 2.3 });"
            ),
        },
    )
    rc, report = _run(root)
    assert rc == 0, report


def test_malformed_endpoints_block_fails_loud(tmp_path):
    root = _scaffold(
        tmp_path,
        server_py=_server([("/api/echo", "_handle_echo", "pass")]),
        endpoints_ts="// no MUTATION_ENDPOINTS here",
        tsx={"Use.tsx": ""},
    )
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 2  # parse error, never silent (Rule 19)


def test_unanalyzable_call_flagged(tmp_path):
    """Dynamic endpoint argument cannot be statically bound."""
    root = _scaffold(
        tmp_path,
        server_py=_server([("/api/echo", "_handle_echo", "pass")]),
        endpoints_ts=_endpoints({"echo": "/api/echo"}),
        tsx={
            "Use.tsx": (
                "const ep: any = pickEndpoint();\n"
                "pathappPatch(scope, ep, { foo: 1 });"
            ),
        },
    )
    rc, report = _run(root)
    assert rc == 1
    kinds = {i["kind"] for i in report["items"]}
    assert "UNANALYZABLE_CLIENT_CALL" in kinds


def test_no_client_callers_endpoint_is_silent(tmp_path):
    """Endpoints with zero client callers (admin, internal) should NOT be
    flagged as SERVER_EXTRA on every key — that would be noise."""
    root = _scaffold(
        tmp_path,
        server_py=_server([
            ("/api/admin/op", "_handle_admin_op", "x = body.get('foo')"),
        ]),
        endpoints_ts=_endpoints({"admin_op": "/api/admin/op"}),
        tsx={"Use.tsx": ""},
    )
    rc, report = _run(root)
    assert rc == 0, report

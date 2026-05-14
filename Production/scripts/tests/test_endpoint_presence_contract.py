"""test_endpoint_presence_contract.py — endpoint-presence CI gate.

Closes the verification-of-deployment-target gap that produced the May 14 2026
"dropdown sets to CHIPPER but Regen Audio says could not resolve speaker"
bug class (durability fix per CLAUDE.md Rule 19 + Rule 28).

The body-key-contract gate (LD BODY_KEY_CONTRACT_CI_GREP_GATE_V1) validates
that for each *paired* endpoint (registered on BOTH client and server) the
body keys match. It does NOT validate that the endpoint is actually
registered on the server in the first place. If a client adds an endpoint
to `endpoints.ts` (MUTATION_ENDPOINTS) but the server PR fails to land a
corresponding route, the gate is silent and the bug surfaces only when a
user hits the UI.

This test forces the pair check: every MUTATION_ENDPOINTS URL path MUST
appear as a route in production_server.py (parsed by the same machinery
the body-key gate already uses, so the two checks share fate).

Authority: LD DROPDOWN_SPEAKER_DURABILITY_FIX_V1.
Symmetric to: body_key_contract_check.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Re-use the existing parsers — same gate, same fate. If the body-key script
# refactors how it parses, this test refactors with it.
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[3]
SCRIPTS_DIR = REPO_ROOT / "Production" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from body_key_contract_check import (  # noqa: E402
    parse_mutation_endpoints,
    parse_server_routes,
)

ENDPOINTS_FILE = REPO_ROOT / "Production" / "tools" / "storyboard-v2" / "src" / "api" / "endpoints.ts"
SERVER_FILE = REPO_ROOT / "Production" / "tools" / "production_server.py"

# Endpoints intentionally registered on the client without a corresponding
# server route — keep this list empty unless there's a documented reason
# (e.g. an endpoint that lives on a different server, or a deprecated stub
# being retired). Adding here without justification is a Rule 19 violation.
ALLOWED_CLIENT_ONLY_ENDPOINTS: frozenset[str] = frozenset({
    # v2_sidecar_write: declared in endpoints.ts but currently uncalled from
    # any client component (verified 2026-05-14 — grep returns only the
    # declaration line). Dead-code candidate for removal in a follow-up PR.
    # Tracked as a separate blocker rather than auto-removed in this PR to
    # keep the dropdown-restore change focused.
    "v2_sidecar_write",
})


def test_every_mutation_endpoint_has_server_route() -> None:
    """For every MUTATION_ENDPOINTS entry, the URL must be a registered route.

    Failure mode caught: client adds a new endpoint to endpoints.ts, server
    PR fails to add the route, the body-key gate doesn't catch it (because
    that gate iterates client+server intersection), and Kim's UI silently
    404s when a user clicks the button.
    """
    assert ENDPOINTS_FILE.exists(), f"missing client endpoints file: {ENDPOINTS_FILE}"
    assert SERVER_FILE.exists(), f"missing server file: {SERVER_FILE}"

    client_endpoints = parse_mutation_endpoints(ENDPOINTS_FILE)  # name -> path
    server_routes = parse_server_routes(SERVER_FILE)             # path -> [handlers]

    missing: list[tuple[str, str]] = []
    for endpoint_name, url_path in client_endpoints.items():
        if endpoint_name in ALLOWED_CLIENT_ONLY_ENDPOINTS:
            continue
        if url_path not in server_routes:
            missing.append((endpoint_name, url_path))

    if missing:
        lines = [
            "Client MUTATION_ENDPOINTS reference URLs with NO server route:",
            "",
        ]
        for name, url in missing:
            lines.append(f"  - {name!r}: {url!r}")
        lines.append("")
        lines.append(
            "Each entry above will 404 at runtime when the client clicks "
            "the corresponding button. Either:\n"
            "  1. Add the matching `if path == \"<url>\": return self._handle_<name>(body)` "
            "to production_server.py's do_POST router and implement the handler, or\n"
            "  2. Remove the unused entry from MUTATION_ENDPOINTS in endpoints.ts, or\n"
            "  3. Add to ALLOWED_CLIENT_ONLY_ENDPOINTS with a comment explaining why "
            "(e.g. deprecated stub being retired).\n\n"
            "Authority: LD DROPDOWN_SPEAKER_DURABILITY_FIX_V1, CLAUDE.md Rule 19."
        )
        raise AssertionError("\n".join(lines))


def test_speaker_dropdown_endpoint_present() -> None:
    """Pin the specific endpoint that regressed on 2026-05-14.

    This is the canary for the dropdown bug: if /api/beat/update_speaker
    disappears from production_server.py again (e.g. due to a merge to the
    wrong base branch, a deploy from the wrong checkout, or a revert), this
    test fails immediately with a recognizable name so the diagnostic
    pathway is short.
    """
    server_routes = parse_server_routes(SERVER_FILE)
    assert "/api/beat/update_speaker" in server_routes, (
        "/api/beat/update_speaker is NOT a registered route in production_server.py. "
        "This is the May 14 2026 bug class — the dropdown UI will silently 404 "
        "when Kim changes a beat's speaker. Re-apply LD CHARACTER_DROPDOWN_RESTORED_V1 "
        "to production_server.py (commit 1ec3cd2 on the original feature branch)."
    )


if __name__ == "__main__":
    # Manual invocation for local dev — pytest is the canonical runner.
    test_every_mutation_endpoint_has_server_route()
    test_speaker_dropdown_endpoint_present()
    print("OK — all MUTATION_ENDPOINTS have server routes.")

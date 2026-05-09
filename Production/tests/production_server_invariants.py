#!/usr/bin/env python3
"""
Production server code-level invariant tests.

Wave B1 WB-C17 per spec v2 §C17. These tests use inspect.getsource() (or
equivalent file-content reads) to assert that top-5 server-side LDs remain
intact at the SOURCE level. Catches regressions that other layers can't see:

- Firestore rules catch DB-level invariants
- ESLint catches TypeScript/RN invariants
- Jest tests catch runtime behavior invariants
- THIS test catches Python source-code invariants (someone removes OP_NO_TICKET
  or stops calling sanitize_prompt — the rule would still "run" but produce
  broken output)

Top-5 LDs under invariant:
  LD-137  POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT  (fresh SSL + OP_NO_TICKET per poll)
  LD-144  ANIMATION_DURATION_MATCHES_AUDIO     (trim uses audio_duration + 0.4s tail)
  LD-155  TRIM_END_SELECTED_VIDEO_ONLY         (trim operates on phase_1.selected_option)
  LD-166  TTS_APPROACH_A_SHIPS_V1              (ElevenLabs per-voice render; no runtime splice)
  LD-171  FIRESTORE_FIELD_LEVEL_SANITIZATION   (sanitize_prompt() called before vendor API)

Usage:
    cd <project-root>
    python3 Production/tests/production_server_invariants.py

Exit 0 = all invariants pass. Exit 1 = at least one invariant violated.
CI workflow .github/workflows/server-invariants.yml runs this (once cross-repo
sync is wired at Stage 3 kickoff — currently scaffolded-only).
"""

from __future__ import annotations
import inspect
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRODUCTION_SERVER = PROJECT_ROOT / "Production" / "tools" / "production_server.py"
POLL_CLIENT = PROJECT_ROOT / "Production" / "lib" / "wavespeed_poll_client.py"


class InvariantError(AssertionError):
    def __init__(self, ld: str, msg: str):
        super().__init__(f"{ld} VIOLATED: {msg}")
        self.ld = ld


# Track results for summary
results: list[tuple[str, str, bool, str]] = []  # (ld, test_name, passed, detail)


def _assert(ld: str, name: str, condition: bool, detail: str) -> None:
    results.append((ld, name, condition, detail))
    if not condition:
        print(f"  ✗ {ld} {name}: {detail}")
    else:
        print(f"  ✓ {ld} {name}")


def _load(path: Path) -> str:
    if not path.exists():
        raise InvariantError("SETUP", f"Source file missing: {path}")
    return path.read_text()


# ─────────────────────────────────────────────────────────────────────────────
# LD-137 POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT
# ─────────────────────────────────────────────────────────────────────────────
# The WaveSpeed polling client must:
#   (a) import http.client (NOT requests or urllib for poll GETs)
#   (b) set ssl.OP_NO_TICKET on its SSL context
#   (c) create a fresh HTTPSConnection per poll (not reuse)
# ─────────────────────────────────────────────────────────────────────────────

def test_ld_137_poll_client_uses_http_client() -> None:
    src = _load(POLL_CLIENT)
    _assert("LD-137", "imports http.client",
            "import http.client" in src,
            f"expected 'import http.client' in {POLL_CLIENT.name}")
    _assert("LD-137", "does NOT import requests for poll",
            not re.search(r"^\s*import requests", src, re.MULTILINE),
            "poll client must not use requests (LD-137)")
    _assert("LD-137", "uses HTTPSConnection directly",
            "http.client.HTTPSConnection" in src,
            "expected http.client.HTTPSConnection call")
    _assert("LD-137", "sets OP_NO_TICKET on SSL context",
            "OP_NO_TICKET" in src and "ctx.options |= ssl.OP_NO_TICKET" in src,
            "OP_NO_TICKET must be set on fresh SSL context per call")
    # Fresh connection — verify _make_ssl_context is called inside the request method
    _assert("LD-137", "calls _make_ssl_context per request (fresh SSL)",
            "_make_ssl_context()" in src,
            "fresh SSL context per poll (not cached)")


# ─────────────────────────────────────────────────────────────────────────────
# LD-144 ANIMATION_DURATION_MATCHES_AUDIO
# ─────────────────────────────────────────────────────────────────────────────
# Trim logic in production_server.py must use audio_duration + 0.4s tail
# (constant _VIDEO_TRIM_TAILROOM_S), not a different target.
# ─────────────────────────────────────────────────────────────────────────────

def test_ld_144_animation_trim_matches_audio() -> None:
    src = _load(PRODUCTION_SERVER)
    _assert("LD-144", "defines _VIDEO_TRIM_TAILROOM_S constant",
            "_VIDEO_TRIM_TAILROOM_S" in src,
            "trim tailroom constant must exist")
    _assert("LD-144", "tailroom is 0.4 seconds",
            re.search(r"_VIDEO_TRIM_TAILROOM_S\s*=\s*0\.4\b", src) is not None,
            "tailroom must equal 0.4s per LD-144")
    _assert("LD-144", "trim function references audio_duration",
            re.search(r"def _?trim_video_to_audio", src) is not None
            and "audio_duration_s" in src,
            "trim function must exist and reference audio_duration_s")
    _assert("LD-144", "target is audio_duration + tailroom",
            "audio_duration_s + _VIDEO_TRIM_TAILROOM_S" in src,
            "trim target expression must be audio_duration_s + _VIDEO_TRIM_TAILROOM_S")


# ─────────────────────────────────────────────────────────────────────────────
# LD-155 TRIM_END_SELECTED_VIDEO_ONLY
# ─────────────────────────────────────────────────────────────────────────────
# Trim-end metadata listener must operate on phase_1.selected_option only —
# NOT update all options. Implementation must check that selected_option is
# retrieved from phase_1 dict before the trim action.
# ─────────────────────────────────────────────────────────────────────────────

def test_ld_155_trim_end_selected_only() -> None:
    src = _load(PRODUCTION_SERVER)
    _assert("LD-155", "retrieves selected_option from phase_1",
            re.search(r'phase1\.get\("selected_option"\)', src) is not None,
            "trim handler must read selected_option from phase_1 dict")
    _assert("LD-155", "error message references selected_option range",
            "selected_option" in src and "out of range" in src,
            "bounds check error must mention selected_option")


# ─────────────────────────────────────────────────────────────────────────────
# LD-166 TTS_APPROACH_A_SHIPS_V1
# ─────────────────────────────────────────────────────────────────────────────
# TTS calls go through ElevenLabs per-voice endpoint. No runtime splice
# (Approach B) in v1. Approach C (single-word splicing with PII) forbidden.
# ─────────────────────────────────────────────────────────────────────────────

def test_ld_166_tts_approach_a() -> None:
    src = _load(PRODUCTION_SERVER)
    _assert("LD-166", "uses ElevenLabs per-voice endpoint",
            "api.elevenlabs.io/v1/text-to-speech/{voice_id}" in src,
            "TTS endpoint must be ElevenLabs per-voice (Approach A)")
    # Approach C forbids raw PII in prompts — sanitize_prompt called (see LD-171)
    # LD-167 Approach B is deferred until 5K trigger — check it's NOT accidentally active
    _assert("LD-166", "no raw Approach B splice endpoint active",
            "short_phrase_splice" not in src and "approach_b_active" not in src,
            "Approach B not yet triggered (5K concurrent per LD-167)")


# ─────────────────────────────────────────────────────────────────────────────
# LD-171 FIRESTORE_FIELD_LEVEL_SANITIZATION_VIA_CLOUD_FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
# sanitize_prompt() must exist AND be called before motion prompts go to
# vendor APIs (WaveSpeed/BFL/etc.). This is the Python-side enforcement of
# the sanitization invariant — the Cloud Function form is enforced via
# Firestore rules (COPPA-2 LD-217).
# ─────────────────────────────────────────────────────────────────────────────

def test_ld_171_sanitize_prompt_exists_and_called() -> None:
    src = _load(PRODUCTION_SERVER)
    _assert("LD-171", "sanitize_prompt function defined",
            re.search(r"^def sanitize_prompt\(", src, re.MULTILINE) is not None,
            "sanitize_prompt() must be a module-level function")
    # Must be called at every vendor-API call site (build_motion_prompt wraps)
    calls = re.findall(r"sanitize_prompt\(build_motion_prompt\(", src)
    _assert("LD-171", "called at motion prompt sites (at least 3)",
            len(calls) >= 3,
            f"expected >=3 sanitize_prompt(build_motion_prompt(...)) calls, found {len(calls)}")


# ─────────────────────────────────────────────────────────────────────────────
# Top-level runner
# ─────────────────────────────────────────────────────────────────────────────

TESTS = [
    ("LD-137", test_ld_137_poll_client_uses_http_client),
    ("LD-144", test_ld_144_animation_trim_matches_audio),
    ("LD-155", test_ld_155_trim_end_selected_only),
    ("LD-166", test_ld_166_tts_approach_a),
    ("LD-171", test_ld_171_sanitize_prompt_exists_and_called),
]


def main() -> int:
    print(f"Production server invariants — Wave B1 WB-C17")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Testing {len(TESTS)} LDs...\n")
    for ld, fn in TESTS:
        print(f"[{ld}]")
        try:
            fn()
        except InvariantError as e:
            results.append((ld, "setup", False, str(e)))
            print(f"  ✗ SETUP failure: {e}")
        print()

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r[2])
    failed = total - passed
    print(f"{'='*60}")
    print(f"Results: {passed}/{total} invariants pass")
    if failed:
        print(f"\nFailed invariants:")
        for ld, name, ok, detail in results:
            if not ok:
                print(f"  {ld} {name}: {detail}")
        return 1
    print(f"All {total} invariants intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

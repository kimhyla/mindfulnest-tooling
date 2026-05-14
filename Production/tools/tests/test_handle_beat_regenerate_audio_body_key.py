#!/usr/bin/env python3
"""F-REGEN-AUDIO-001 — body-key contract on /api/beat/regenerate_audio.

Server handler `_handle_beat_regenerate_audio` (production_server.py)
must accept the body shape the client sends. The v59 client at
`Production/tools/storyboard-v2/src/components/StoryboardTab.tsx:192`
sends:

    pathappPatch(activeScope.value, endpoint, { beat_id: beatId, ...body })

Pre-fix the server read only `body.get("beat")` — every Regen Audio
button click returned HTTP 400 `{"error": "missing 'beat'"}`. Filed as
prod_blockers id=124 (severity=high). Post-fix the server accepts
either key:

    beat_id = body.get("beat_id") or body.get("beat")

This matches the established back-compat precedent at
`production_server.py:11516` (`_handle_use_as_final`).

Tests (3) — all run offline; mock `_tts_regenerate_for_beat` and
`credentials.load_credentials` so the body-key contract is the only
thing exercised:

  1. test_F_REGEN_AUDIO_001_client_beat_id_body_key_accepted
       - RED pre-fix / GREEN post-fix.
       - Sends client-canonical `{scope_event_id, scope_video_role,
         scope_target_video, beat_id}` body.
       - Asserts response is NOT (400, "missing 'beat'").
  2. test_legacy_beat_body_key_still_works
       - Back-compat: sends legacy `{beat: ...}` form.
       - Should pass both pre-fix and post-fix.
  3. test_missing_both_keys_returns_400
       - Regression guard: no key → still 400.

Run directly:
    python3 Production/tools/tests/test_handle_beat_regenerate_audio_body_key.py

Or via unittest:
    python3 -m unittest -v \\
        Production.tools.tests.test_handle_beat_regenerate_audio_body_key
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

# sys.path setup MUST run before importing production_server.
# See test_scope_router_scrambled.py for the rationale on why
# Production/ must be inserted at the FRONT of sys.path.
_THIS_FILE = Path(__file__).resolve()
_PRODUCTION_DIR = _THIS_FILE.parents[2]               # tooling-repo/Production
_PRODUCTION_DIR_S = str(_PRODUCTION_DIR)
_TOOLS_DIR_S = str(_PRODUCTION_DIR / "tools")
if _PRODUCTION_DIR_S not in sys.path:
    sys.path.insert(0, _PRODUCTION_DIR_S)
if _TOOLS_DIR_S not in sys.path:
    sys.path.append(_TOOLS_DIR_S)
os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")

import production_server as _ps  # noqa: E402,F401


_PRISTINE_STATE = (
    _PRODUCTION_DIR / "Event_e2e_fixture" / ".pristine" / "production_state.json"
)


class BeatRegenerateAudioBodyKeyContractTests(unittest.TestCase):
    """F-REGEN-AUDIO-001 — body-key contract: client sends `beat_id`,
    server must accept (and continue accepting legacy `beat`)."""

    @classmethod
    def setUpClass(cls):
        if not _PRISTINE_STATE.is_file():
            raise unittest.SkipTest(
                f"Event_e2e_fixture pristine state not found at {_PRISTINE_STATE}"
            )

    def setUp(self):
        # Per-test tmpfs event_dir built from pristine fixture state so
        # tests are hermetic (no Dropbox dependency, no cross-test leak).
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)
        self.tmp_event_dir = tmp / "Event_e2e_fixture_target"
        self.tmp_event_dir.mkdir()

        # Copy pristine state and override event_id to match tmp dir name
        # (so _assert_event_scope's body_event == server_event check
        # passes when the test body sets scope_event_id="Event_e2e_fixture_target").
        with open(_PRISTINE_STATE, "r", encoding="utf-8") as f:
            state = json.load(f)
        state["event_id"] = "Event_e2e_fixture_target"
        (self.tmp_event_dir / "production_state.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8",
        )
        # Placeholder storyboard html so app.storyboard_path resolves.
        (self.tmp_event_dir / "storyboard_v59_prod.html").write_text(
            "<html></html>", encoding="utf-8",
        )

        # Inject a fake `credentials` module so load_credentials() returns a
        # synthetic ElevenLabs key. The handler imports `credentials` from
        # `Production/tools/credentials_lib/` lazily inside the function body,
        # so we shadow it via sys.modules before the handler runs.
        fake_creds_mod = types.ModuleType("credentials")
        fake_creds_mod.load_credentials = lambda: {  # type: ignore[attr-defined]
            "elevenlabs_key": "fake_key_for_test"
        }
        self._original_creds_mod = sys.modules.get("credentials")
        sys.modules["credentials"] = fake_creds_mod

        # Mock `_tts_regenerate_for_beat` to avoid any real ElevenLabs API
        # call. Returns a synthetic success response. The handler reads
        # this attribute via the module global at call time, so monkey-
        # patching the module attribute is sufficient.
        self._original_tts = _ps._tts_regenerate_for_beat

        def _fake_tts(_app, beat_id, _text, _key, video_role="intro"):
            return {
                "ok": True,
                "audio_file": f"{beat_id}_fake.mp3",
                "audio_duration_s": 1.0,
                "elapsed_s": 0.05,
            }

        _ps._tts_regenerate_for_beat = _fake_tts

    def tearDown(self):
        # Restore monkey-patches so other tests aren't affected.
        _ps._tts_regenerate_for_beat = self._original_tts
        if self._original_creds_mod is None:
            sys.modules.pop("credentials", None)
        else:
            sys.modules["credentials"] = self._original_creds_mod

    def _build_handler(self):
        """Build a ProductionHandler stub bound to the tmpfs event_dir.

        Mirrors the pattern from test_scope_router_scrambled.py — captures
        `_send_json` calls into a dict so the test can assert status + payload
        without a real socket.
        """
        sm = _ps.StateManager(self.tmp_event_dir, "Event_e2e_fixture_target")

        class _App:
            def __init__(_self):
                _self.state = sm
                _self.event_dir = self.tmp_event_dir
                _self.event_id = "Event_e2e_fixture_target"
                _self.storyboard_path = (
                    self.tmp_event_dir / "storyboard_v59_prod.html"
                )
                _self.source_event_dir = None
                # Tier1A (fired only when TIER1A_ENABLED) reads app state
                # via _tier1a_mark_regen_fired; provide a generation int.
                _self.event_generation = 0
                # _tier1a_mark_regen_fired writes nothing if app.state has
                # no badges; skip extra plumbing.

        class _Server:
            def __init__(_self, _app):
                _self.app = _app

        h = _ps.ProductionHandler.__new__(_ps.ProductionHandler)
        h.server = _Server(_App())
        captured = {"status": None, "payload": None}

        def _capture(status, payload, _c=captured):
            _c["status"] = status
            _c["payload"] = payload

        h._send_json = _capture
        h.path = "/api/beat/regenerate_audio"
        h.command = "POST"
        return h, captured

    # ------------------------------------------------------------------
    # F-REGEN-AUDIO-001 — RED pre-fix / GREEN post-fix
    # ------------------------------------------------------------------
    def test_F_REGEN_AUDIO_001_client_beat_id_body_key_accepted(self):
        """Client sends `beat_id`; server must accept (not 400 missing 'beat').

        Per StoryboardTab.tsx:192 — `pathappPatch(scope, endpoint,
        { beat_id: beatId, ...body })`. Server pre-fix reads
        `body.get("beat")` only and rejects with 400 missing 'beat'.
        Post-fix reads `body.get("beat_id") or body.get("beat")`
        (precedent: production_server.py:11516).
        """
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "scope_target_video": "intro",
            "beat_id": "beat_01",
        }
        h._handle_beat_regenerate_audio(body)

        # Pre-fix: status=400, payload={"error":"missing 'beat'"}
        # Post-fix: status=200 (or any non-400), got past the body-key gate
        is_missing_beat_400 = (
            captured["status"] == 400
            and isinstance(captured["payload"], dict)
            and captured["payload"].get("error") == "missing 'beat'"
        )
        self.assertFalse(
            is_missing_beat_400,
            (
                f"F-REGEN-AUDIO-001: client sends {{beat_id: 'beat_01'}}; "
                f"server must read body.get('beat_id') or body.get('beat'). "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )
        # Stronger post-fix assertion: with mocks in place the handler should
        # reach the 200 success path.
        self.assertEqual(
            captured["status"], 200,
            (
                f"Post-fix expectation: with credentials + TTS mocked, handler "
                f"should return 200. Got status={captured['status']} "
                f"payload={captured['payload']!r}"
            ),
        )
        self.assertEqual(captured["payload"].get("ok"), True)
        self.assertEqual(captured["payload"].get("beat"), "beat_01")

    # ------------------------------------------------------------------
    # Back-compat: legacy `{beat: ...}` form continues to work
    # ------------------------------------------------------------------
    def test_legacy_beat_body_key_still_works(self):
        """Pre-fix and post-fix: legacy clients sending `{beat: ...}` still pass."""
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "scope_target_video": "intro",
            "beat": "beat_01",
        }
        h._handle_beat_regenerate_audio(body)
        self.assertEqual(
            captured["status"], 200,
            (
                f"Back-compat: legacy `beat` key must still be accepted. "
                f"Got status={captured['status']} payload={captured['payload']!r}"
            ),
        )
        self.assertEqual(captured["payload"].get("beat"), "beat_01")

    # ------------------------------------------------------------------
    # Regression guard: with neither beat_id nor beat, still 400
    # ------------------------------------------------------------------
    def test_missing_both_keys_returns_400(self):
        """Both keys absent → 400 missing 'beat' (regression guard)."""
        h, captured = self._build_handler()
        body = {
            "scope_event_id": "Event_e2e_fixture_target",
            "scope_video_role": "intro",
            "scope_target_video": "intro",
            # neither beat nor beat_id
        }
        h._handle_beat_regenerate_audio(body)
        self.assertEqual(
            captured["status"], 400,
            f"Missing both keys must still 400. Got {captured['status']} {captured['payload']!r}",
        )
        self.assertEqual(captured["payload"].get("error"), "missing 'beat'")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Tier 1A HTTP-based tests: TTS regen debounce + v2 flag forwarding.

Preflight 65 (April 18 2026). Exercises two locked decisions:
  LD TTS_REGEN_DEBOUNCE_60S_WINDOW_PER_BEAT (MEDIUM)
  LD V2_DIALOGUE_EXPLICIT_FIELD_FORWARDING_WITH_ALLOWLIST (MEDIUM)

Tests run against a LIVE in-process ProductionServer on an ephemeral port,
with a synthetic event_dir and beat_99_test fixture — NEVER touches the
real production_state.json, the real storyboard HTML, or any real ElevenLabs
TTS endpoint. _tts_regenerate_for_beat is monkey-patched to a stub that
records calls and returns a synthetic success payload.

Run:
    python3 -m unittest Production.tools.tests.test_tier1a_debounce
  or
    cd Production/tools/tests && python3 test_tier1a_debounce.py
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

# Bypass the Directus cross-machine lock — required for isolated tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
# Hard-enable Tier 1A for the test run (it's default ON, but be explicit).
os.environ["MINDFULNEST_T1_ENABLED"] = "1"

import production_server as PS  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixture: minimal event_dir + storyboard + production_state.json
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _build_storyboard_html(beat_ids: list[str]) -> str:
    """Minimal storyboard with an L[] block containing each beat's line entry.
    _patch_storyboard_L_field looks for a:"line_NN" markers + t:"..." fields.
    """
    entries = []
    for bid in beat_ids:
        n = int(bid.split("_")[1])
        entries.append(
            f'{{a:"line_{n:02d}",t:"placeholder",i:"shot{n}_initial"}}'
        )
    return (
        "<html><head><script>\n"
        "var L = [" + ",".join(entries) + "];\n"
        "var TH = {};\n"
        "</script></head><body></body></html>\n"
    )


def _make_event_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    event_dir = tmp_path / "Event_TEST"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard_path = event_dir / "storyboard_test_t1a.html"
    storyboard_path.write_text(
        _build_storyboard_html(["beat_01", "beat_02", "beat_03"]),
        encoding="utf-8",
    )
    # Seed production_state.json with the beats so update_text doesn't
    # need to extract from storyboard.
    state_path = event_dir / "production_state.json"
    state_path.write_text(json.dumps({
        "beats": {
            "beat_01": {"text": "original text beat 1", "phase_1": {}, "_version": 1},
            "beat_02": {"text": "original text beat 2", "phase_1": {}, "_version": 1},
            "beat_03": {"text": "original text beat 3", "phase_1": {}, "_version": 1},
        },
        "image_overrides": {},
    }, indent=2))
    return event_dir, storyboard_path, "Event_TEST"


# ---------------------------------------------------------------------------
# TTS stub — replaces _tts_regenerate_for_beat so tests run offline
# ---------------------------------------------------------------------------

class _TTSStub:
    """Records each call to _tts_regenerate_for_beat. Returns a synthetic
    success payload. Thread-safe because production_server dispatches
    requests on a ThreadingHTTPServer."""
    def __init__(self):
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def __call__(self, app, beat_id: str, text: str, el_key: str):
        with self._lock:
            self.calls.append({
                "beat_id": beat_id,
                "text": text,
                "ts": time.time(),
            })
        return {
            "ok": True,
            "audio_file": f"stub_{beat_id}.mp3",
            "audio_duration_s": 1.23,
            "elapsed_s": 0.01,
        }

    def reset(self):
        with self._lock:
            self.calls.clear()


class _CredStub:
    """Stub replacement for lib.credentials.load_credentials so the
    TTS key check passes without hitting API_KEYS_MASTER.md."""
    @staticmethod
    def load_credentials():
        return {
            "elevenlabs_key": "stub-eleven-key",
            "directus_url": "https://example.invalid",
            "directus_email": "test@example.invalid",
            "directus_password": "stub",
        }


# ---------------------------------------------------------------------------
# Server lifecycle helpers
# ---------------------------------------------------------------------------

def _start_server(event_dir: Path, storyboard_path: Path, event_id: str,
                  port: int):
    """Build AppContext + ProductionServer, return (server, thread)."""
    state_mgr = PS.StateManager(event_dir, event_id)
    # Re-read seeded state so mutate_state calls don't drop it (state manager
    # reads lazily but mutate_state expects the file to exist — which it does
    # since the fixture wrote it).

    # Build AppContext with no WaveSpeedClient — we never call /api/animate here.
    app = PS.AppContext(
        event_dir=event_dir,
        storyboard_path=storyboard_path,
        event_id=event_id,
        state=state_mgr,
        client=None,
    )
    # AppContext init reads state; verify the seeded beat survived.
    assert state_mgr.read_state()["beats"]["beat_01"]["text"] == "original text beat 1"

    # Extend AppContext with .touch() (ProductionHandler uses it on every req)
    if not hasattr(app, "touch"):
        app.touch = lambda: None  # type: ignore[attr-defined]

    server = PS.ProductionServer(("127.0.0.1", port), app)
    thread = threading.Thread(
        target=server.serve_forever, name="t1a-test-server", daemon=True,
    )
    thread.start()
    # Wait briefly for bind to settle
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.05)
    return server, thread


def _http_post(port: int, path: str, body: dict,
               timeout: float = 5.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestTier1ADebounceHTTP(unittest.TestCase):
    """HTTP-based tests per Tier 1A spec."""

    # Hard timeout: kill a stuck test after 30s
    @classmethod
    def setUpClass(cls):
        if hasattr(signal, "alarm"):
            def _timeout_handler(signum, frame):
                print("[T1A TEST] signal.alarm fired — test hung — aborting",
                      file=sys.stderr, flush=True)
                os._exit(2)
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(30)

    @classmethod
    def tearDownClass(cls):
        if hasattr(signal, "alarm"):
            signal.alarm(0)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t1a_"))
        self.event_dir, self.sb_path, self.event_id = _make_event_fixture(self.tmp)
        self.port = _find_free_port()

        # Install the TTS + credentials stubs. Save originals for teardown.
        self._orig_tts = PS._tts_regenerate_for_beat
        self._tts_stub = _TTSStub()
        PS._tts_regenerate_for_beat = self._tts_stub  # type: ignore[assignment]

        # Monkey-patch credentials so load_credentials() returns stub key.
        # production_server imports credentials lazily inside the handler; we
        # patch sys.modules so the `from credentials import load_credentials`
        # statement resolves to our stub.
        import importlib  # noqa: PLC0415
        _libdir = str(TOOLS / "lib")
        if _libdir not in sys.path:
            sys.path.insert(0, _libdir)
        import credentials as _cred_mod  # type: ignore  # noqa: PLC0415
        self._orig_load_creds = _cred_mod.load_credentials
        _cred_mod.load_credentials = _CredStub.load_credentials

        # Clear Tier 1A debounce state between tests
        PS._TTS_REGEN_LAST_TS.clear()
        PS._TTS_DEBOUNCE_AUDIT_LAST_TS.clear()

        # Disable the Directus audit-log thread (we don't want real writes)
        self._orig_async_audit = PS._tier1a_async_log_debounce
        PS._tier1a_async_log_debounce = lambda *_a, **_kw: None  # type: ignore[assignment]
        self._orig_async_text = PS._async_log_text_update
        PS._async_log_text_update = lambda *_a, **_kw: None  # type: ignore[assignment]

        # Start the server
        self.server, self.thread = _start_server(
            self.event_dir, self.sb_path, self.event_id, self.port,
        )

    def tearDown(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        # Restore originals
        PS._tts_regenerate_for_beat = self._orig_tts  # type: ignore[assignment]
        PS._tier1a_async_log_debounce = self._orig_async_audit  # type: ignore[assignment]
        PS._async_log_text_update = self._orig_async_text  # type: ignore[assignment]
        import credentials as _cred_mod  # type: ignore  # noqa: PLC0415
        _cred_mod.load_credentials = self._orig_load_creds
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Test 1: two dialogue updates within 60s → second is debounced
    # ------------------------------------------------------------------
    def test_debounce_blocks_second_regen_within_window(self):
        status1, resp1 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_01", "text": "first edit",
        })
        self.assertEqual(status1, 200, resp1)
        self.assertTrue(resp1.get("ok"), resp1)
        self.assertTrue(
            resp1.get("tts_regen", {}).get("ok"),
            f"first regen should succeed; got {resp1.get('tts_regen')!r}",
        )

        # Second POST within the 60s window
        status2, resp2 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_01", "text": "second edit within window",
        })
        self.assertEqual(status2, 200, resp2)
        self.assertTrue(resp2.get("ok"), resp2)
        tts = resp2.get("tts_regen") or {}
        self.assertFalse(tts.get("ok"), f"expected skip; got {tts!r}")
        self.assertTrue(tts.get("skipped"), f"expected skipped=true; got {tts!r}")
        self.assertEqual(
            tts.get("reason"), "debounced",
            f"expected reason=debounced; got {tts!r}",
        )
        # TTS stub should have been invoked EXACTLY ONCE (first edit)
        self.assertEqual(
            len(self._tts_stub.calls), 1,
            f"expected 1 TTS call, got {len(self._tts_stub.calls)}: "
            f"{self._tts_stub.calls!r}",
        )

    # ------------------------------------------------------------------
    # Test 2: after window expires, regen proceeds again (mock time)
    # ------------------------------------------------------------------
    def test_regen_resumes_after_window_expires(self):
        # First POST — should regen
        status1, resp1 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_02", "text": "first edit beat 2",
        })
        self.assertEqual(status1, 200, resp1)
        self.assertTrue(resp1.get("tts_regen", {}).get("ok"))

        # Simulate 61s of elapsed time by mutating the last-regen timestamp
        # directly — faster and hermetic vs. real signal.alarm sleep.
        PS._TTS_REGEN_LAST_TS["beat_02"] = time.time() - 61.0

        # Second POST AFTER the window — should regen again
        status2, resp2 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_02", "text": "second edit AFTER window",
        })
        self.assertEqual(status2, 200, resp2)
        tts = resp2.get("tts_regen") or {}
        self.assertTrue(
            tts.get("ok"),
            f"second regen should succeed after window expires; got {tts!r}",
        )
        # TTS stub should have been invoked TWICE
        self.assertEqual(
            len(self._tts_stub.calls), 2,
            f"expected 2 TTS calls, got {len(self._tts_stub.calls)}: "
            f"{self._tts_stub.calls!r}",
        )

    # ------------------------------------------------------------------
    # Test 3: per-beat isolation — debounce on beat_01 does NOT block beat_02
    # ------------------------------------------------------------------
    def test_debounce_is_per_beat(self):
        # Regen beat_01 → primes debounce
        s1, r1 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_01", "text": "beat 01 first",
        })
        self.assertEqual(s1, 200)
        self.assertTrue(r1.get("tts_regen", {}).get("ok"))

        # Immediately regen beat_02 — should NOT be blocked
        s2, r2 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_02", "text": "beat 02 first",
        })
        self.assertEqual(s2, 200)
        self.assertTrue(
            r2.get("tts_regen", {}).get("ok"),
            f"beat_02 regen should NOT be debounced by beat_01; got {r2!r}",
        )

    # ------------------------------------------------------------------
    # Test 4: skip_tts_regen=True short-circuits BEFORE the debounce check
    # ------------------------------------------------------------------
    def test_skip_tts_regen_flag_bypasses_regen(self):
        s, r = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_03",
            "text": "save text with skip flag",
            "skip_tts_regen": True,
        })
        self.assertEqual(s, 200)
        tts = r.get("tts_regen") or {}
        self.assertTrue(tts.get("skipped"))
        self.assertEqual(tts.get("reason"), "skip_tts_regen_flag")
        self.assertEqual(
            len(self._tts_stub.calls), 0,
            f"skip_tts_regen=True must NOT invoke TTS; got {self._tts_stub.calls!r}",
        )
        # And because no regen fired, the next edit WITHOUT the flag should regen.
        s2, r2 = _http_post(self.port, "/api/beat/update_text", {
            "beat": "beat_03", "text": "next edit without flag",
        })
        self.assertEqual(s2, 200)
        self.assertTrue(
            r2.get("tts_regen", {}).get("ok"),
            f"regen should fire after skip_tts_regen=True prior edit; got {r2!r}",
        )

    # ------------------------------------------------------------------
    # Test 5: v2 dialogue path forwards skip_tts_regen → legacy handler
    # ------------------------------------------------------------------
    def test_v2_dialogue_forwards_skip_tts_regen(self):
        # POST v2 dialogue with skip_tts_regen=true in the body
        status, resp = _http_post(
            self.port,
            "/api/v2/beat/beat_01/patch",
            {
                "field": "dialogue",
                "value": "dialogue via v2 with skip flag",
                "skip_tts_regen": True,
                "mutation_id": "t1a-v2-fwd-1",
            },
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        # The nested legacy payload must show the flag was honored
        legacy = resp.get("legacy") or {}
        tts = legacy.get("tts_regen") or {}
        self.assertTrue(
            tts.get("skipped"),
            f"legacy handler must see skip flag via v2 forwarding; got {legacy!r}",
        )
        self.assertEqual(
            tts.get("reason"), "skip_tts_regen_flag",
            f"flag forwarding failed — reason was {tts.get('reason')!r}; "
            f"expected skip_tts_regen_flag",
        )
        # TTS stub never invoked
        self.assertEqual(len(self._tts_stub.calls), 0,
                         f"v2 w/ skip_tts_regen must NOT call TTS; "
                         f"got {self._tts_stub.calls!r}")

    # ------------------------------------------------------------------
    # Test 6: v2 dialogue WITHOUT the flag does regen (control case —
    # proves the forwarding test above is meaningful)
    # ------------------------------------------------------------------
    def test_v2_dialogue_regens_without_skip_flag(self):
        status, resp = _http_post(
            self.port,
            "/api/v2/beat/beat_02/patch",
            {
                "field": "dialogue",
                "value": "dialogue via v2 no skip",
                "mutation_id": "t1a-v2-control-1",
            },
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        legacy = resp.get("legacy") or {}
        self.assertTrue(
            legacy.get("tts_regen", {}).get("ok"),
            f"v2 dialogue without skip flag should regen; got {legacy!r}",
        )
        self.assertEqual(len(self._tts_stub.calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

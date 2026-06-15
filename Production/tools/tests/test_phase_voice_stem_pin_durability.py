#!/usr/bin/env python3
"""PHASE_VOICE_STEM_PIN_DURABILITY_V1 — stem pin parity + stale-oracle guards."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers.phases import (  # noqa: E402
    PHASE_VOICE_STEM_PIN_DURABILITY_V1,
    _phase_list_newer_voice_stems_on_disk,
    _phase_lipsync_sidecar_audio_source,
    _phase_resolve_voice_stem_name,
    _phase_set_voice_stem_keys,
    _phase_voice_stem_mirror_drift,
    _phase_voice_stem_pin_issues,
)


class _FakeApp:
    def __init__(self, event_dir: Path):
        self.event_dir = event_dir


class _FakeHandler:
    def __init__(self, event_dir: Path):
        self.app = _FakeApp(event_dir)


class PhaseVoiceStemPinDurabilityTests(unittest.TestCase):
    def test_top_level_wins_over_nested(self):
        state = {
            "phase_a_voice_stem_file": "phase_a_voice_stem_new.mp3",
            "phase_a": {"phase_a_voice_stem_file": "phase_a_voice_stem_old.mp3"},
        }
        self.assertEqual(_phase_resolve_voice_stem_name(state, "a"), "phase_a_voice_stem_new.mp3")

    def test_set_voice_stem_keys_mirrors_nested(self):
        state: dict = {"phase_a": {}}
        _phase_set_voice_stem_keys(state, "a", "phase_a_voice_stem_20260613.mp3", 1710000000)
        self.assertEqual(state["phase_a_voice_stem_file"], "phase_a_voice_stem_20260613.mp3")
        self.assertEqual(
            state["phase_a"]["phase_a_voice_stem_file"],
            "phase_a_voice_stem_20260613.mp3",
        )

    def test_mirror_drift_detected(self):
        state = {
            "phase_a_voice_stem_file": "stem_a.mp3",
            "phase_a": {"phase_a_voice_stem_file": "stem_b.mp3"},
        }
        self.assertEqual(_phase_voice_stem_mirror_drift(state, "a"), "stem_b.mp3")

    def test_newer_stems_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            old = event_dir / "phase_a_voice_stem_20260606.mp3"
            new = event_dir / "phase_a_voice_stem_20260613.mp3"
            old.write_bytes(b"old")
            new.write_bytes(b"new")
            os.utime(old, (1_000_000, 1_000_000))
            os.utime(new, (2_000_000, 2_000_000))
            newer = _phase_list_newer_voice_stems_on_disk(event_dir, "a", old.name)
            self.assertEqual(newer, [new.name])

    def test_pin_stale_issue_when_orphan_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            pinned = event_dir / "phase_a_voice_stem_20260606-234239.mp3"
            orphan = event_dir / "phase_a_voice_stem_20260613-124825.mp3"
            pinned.write_bytes(b"old delivery")
            orphan.write_bytes(b"new delivery")
            t0 = time.time() - 3600
            t1 = time.time()
            os.utime(pinned, (t0, t0))
            os.utime(orphan, (t1, t1))

            h = _FakeHandler(event_dir)
            state = {
                "phase_a_voice_stem_file": pinned.name,
                "phase_a_voice_stem_mtime": int(t0),
                "phase_a": {
                    "phase_a_voice_stem_file": pinned.name,
                    "phase_a_voice_stem_mtime": int(t0),
                },
            }
            issues = _phase_voice_stem_pin_issues(h, state, "a", for_lipsync=True)
            codes = [i["code"] for i in issues]
            self.assertIn("STEM_PIN_STALE", codes)
            stale = next(i for i in issues if i["code"] == "STEM_PIN_STALE")
            self.assertIn(orphan.name, stale["newer_stems"])

    def test_lipsync_lineage_stale_when_sidecar_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            stem = event_dir / "phase_a_voice_stem_new.mp3"
            stem.write_bytes(b"new")
            lipsync = event_dir / "phase_a_lipsync_test.mp4"
            lipsync.write_bytes(b"video")
            sidecar = lipsync.with_suffix(".json")
            sidecar.write_text(
                '{"audio_source": "phase_a_voice_stem_old.mp3"}\n',
                encoding="utf-8",
            )
            h = _FakeHandler(event_dir)
            state = {
                "phase_a_voice_stem_file": stem.name,
                "phase_a_lipsync_file": lipsync.name,
                "phase_a_lipsync_requires_regen": False,
            }
            issues = _phase_voice_stem_pin_issues(h, state, "a", for_lipsync=True)
            codes = [i["code"] for i in issues]
            self.assertIn("LIPSYNC_AUDIO_LINEAGE_STALE", codes)
            self.assertEqual(
                _phase_lipsync_sidecar_audio_source(event_dir, lipsync.name),
                "phase_a_voice_stem_old.mp3",
            )

    def test_preflight_blocks_stale_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            pinned = event_dir / "phase_a_voice_stem_old.mp3"
            newer = event_dir / "phase_a_voice_stem_new.mp3"
            pinned.write_bytes(b"old")
            newer.write_bytes(b"new")
            t0 = time.time() - 100
            t1 = time.time()
            os.utime(pinned, (t0, t0))
            os.utime(newer, (t1, t1))

            from server_handlers import phases as ph  # noqa: E402

            h = mock.Mock()
            h.app = _FakeApp(event_dir)
            h.app.state = mock.Mock()
            h.app.state.read_state.return_value = {
                "phase_a_voice_stem_file": pinned.name,
            }
            sent = {}

            def _capture_send(*args, **kwargs):
                sent["status"] = args[0]
                sent["error_code"] = kwargs.get("error_code")
                sent["extra"] = kwargs.get("extra")
                return None

            h._send_error_v59 = _capture_send
            state = h.app.state.read_state()
            ph._phase_preflight_voice_stem_for_lipsync(h, state, "a")
            self.assertEqual(sent["status"], 409)
            self.assertEqual(sent["error_code"], "PHASE_VOICE_STEM_PIN_STALE")
            self.assertEqual(sent["extra"]["code"], PHASE_VOICE_STEM_PIN_DURABILITY_V1)


if __name__ == "__main__":
    unittest.main()

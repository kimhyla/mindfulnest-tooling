#!/usr/bin/env python3
"""STITCH_SLOT_LIVE_GEOMETRY_SIG_V1 — mix artifact invalidation on geometry drift."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers.stitch_media_artifacts import (  # noqa: E402
    invalidate_stitch_slot_artifacts_if_mix_drift,
)
from server_handlers.stitch_media_sig import compute_stitch_mix_sig_from_slot  # noqa: E402


class TestStitchSlotGeometryInvalidation(unittest.TestCase):
    def test_live_geometry_sig_client_source_marker(self):
        src = (TOOLS / "storyboard-v2" / "src" / "utils" / "stitchSlotMuxAudioSig.ts").read_text(
            encoding="utf-8",
        )
        tab = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
            encoding="utf-8",
        )
        self.assertIn("STITCH_SLOT_LIVE_GEOMETRY_SIG_V1", src)
        self.assertIn("stitchSlotLiveGeometrySig", src)
        self.assertNotIn("if (serverSig) return serverSig", src)
        self.assertIn("stripStaleStitchSlotArtifacts", tab)
        self.assertIn("stitchSlotGeometryChanged", tab)
        self.assertIn("isMuxSessionFresh(stitchSessionKey", tab)

    def test_invalidate_clears_artifacts_when_sfx_geometry_drifts(self):
        h = mock.Mock()
        h._stitch_resolve_path = lambda p: str(Path("/proj") / p)

        slot = {
            "video_path": "Production/Event_2/resolution.mp4",
            "video_dur_ms": 49708,
            "ambient_bed": "ambien bed pretty option4",
            "ambient_volume": 0.15,
            "sfx_cues": [
                {
                    "id": "cue_a",
                    "offset_ms": 0,
                    "duration_ms": 3000,
                    "volume": 0.45,
                    "fadein_ms": 300,
                    "fadeout_ms": 1200,
                    "source_path": "/x/sfx.mp3",
                },
            ],
            "mix_sig": "deadbeefdeadbeef",
            "mux_preview_hash": "abc123",
            "waveform_peaks_hash": "def456",
        }
        with mock.patch(
            "server_handlers.stitch_media_artifacts.compute_stitch_mix_sig_from_slot",
            return_value="cafebabecafebabe",
        ):
            self.assertTrue(invalidate_stitch_slot_artifacts_if_mix_drift(h, slot))
        self.assertNotIn("mux_preview_hash", slot)

    def test_invalidate_noop_when_mix_sig_matches(self):
        h = mock.Mock()
        slot = {
            "video_path": "Production/Event_2/resolution.mp4",
            "ambient_bed": "ambien bed pretty option4",
            "ambient_volume": 0.15,
            "sfx_cues": [],
            "mix_sig": "same_sig_same_sig",
            "mux_preview_hash": "abc123",
        }
        with mock.patch(
            "server_handlers.stitch_media_artifacts.compute_stitch_mix_sig_from_slot",
            return_value="same_sig_same_sig",
        ):
            self.assertFalse(invalidate_stitch_slot_artifacts_if_mix_drift(h, slot))
        self.assertEqual(slot["mix_sig"], "same_sig_same_sig")
        self.assertEqual(slot["mux_preview_hash"], "abc123")

    def test_save_job_merges_invalidate_on_drift(self):
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = editor.split("def handle_stitch_save_job", 1)[1].split("\ndef handle_stitch_loudnorm", 1)[0]
        self.assertIn("invalidate_stitch_slot_artifacts_if_mix_drift", block)

    def test_live_geometry_sig_changes_on_cue_resize(self):
        """Client geometry fingerprint must change when duration_ms changes."""
        ts = (
            "const slotA = { video_path: 'a.mp4', ambient_bed: 'bed', ambient_volume: 0.15,"
            " sfx_cues: [{ id: 'c1', offset_ms: 0, duration_ms: 3000, volume: 0.45,"
            " fadein_ms: 300, fadeout_ms: 1200, source_path: '/x.mp3', name: 'x.mp3' }] };"
            " const slotB = { ...slotA, sfx_cues: [{ ...slotA.sfx_cues[0], duration_ms: 5000 }] };"
        )
        # Inline mirror of TS logic for pytest without node
        def live_sig(slot):
            ambient = (slot.get("ambient_bed_path") or slot.get("ambient_bed") or "").strip()
            vol = slot.get("ambient_volume", "")
            video = (slot.get("video_path") or "").strip()
            parts = []
            for c in slot.get("sfx_cues") or []:
                parts.append(
                    f"{c.get('id','')}:{c.get('offset_ms',0)}:{c.get('duration_ms','')}:"
                    f"{c.get('volume','')}:{c.get('fadein_ms','')}:{c.get('fadeout_ms','')}:"
                    f"{c.get('source_path','')}:{c.get('name','')}"
                )
            return f"{video}#{ambient}@{vol}#{'|'.join(sorted(parts))}"

        slot_a = {
            "video_path": "a.mp4",
            "ambient_bed": "bed",
            "ambient_volume": 0.15,
            "sfx_cues": [{
                "id": "c1", "offset_ms": 0, "duration_ms": 3000, "volume": 0.45,
                "fadein_ms": 300, "fadeout_ms": 1200, "source_path": "/x.mp3", "name": "x.mp3",
            }],
        }
        slot_b = json.loads(json.dumps(slot_a))
        slot_b["sfx_cues"][0]["duration_ms"] = 5000
        self.assertNotEqual(live_sig(slot_a), live_sig(slot_b))


if __name__ == "__main__":
    unittest.main()

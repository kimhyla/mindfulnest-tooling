"""STITCH_SLOT_TIMELINE_ATOMIC_V1 — video_path slots must expose video_dur_ms."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server_handlers import stitch_editor as se


class StitchSlotTimelineAtomicTests(unittest.TestCase):
    def test_marker_in_stitch_editor(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "server_handlers/stitch_editor.py").read_text(
            encoding="utf-8",
        )
        assert "STITCH_SLOT_TIMELINE_ATOMIC_V1" in src
        assert "def ensure_stitch_slot_timeline_dur_ms" in src

    def test_load_job_calls_timeline_atomic(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "server_handlers/stitch_editor.py").read_text(
            encoding="utf-8",
        )
        block = src.split("def handle_stitch_load_job", 1)[1].split(
            "\ndef handle_stitch_serve_module_final", 1,
        )[0]
        assert "ensure_stitch_slot_timeline_dur_ms" in block
        assert "timeline_atomic_changed" in block

    def test_ensure_backfills_from_mux_when_ffprobe_zero(self) -> None:
        class _Handler:
            def _stitch_resolve_path(self, rel: str) -> str:
                return rel

            def _ffprobe_duration_ms(self, _path: str) -> int:
                return 0

        h = _Handler()
        slot = {
            "video_path": "Production/Milestones/m1/assembled/standalone.mp4",
            "mux_preview_duration_ms": 94063,
        }
        self.assertTrue(se.ensure_stitch_slot_timeline_dur_ms(h, slot))
        self.assertEqual(slot["video_dur_ms"], 94063)

    def test_ensure_noop_when_video_dur_present(self) -> None:
        h = object()
        slot = {"video_path": "x.mp4", "video_dur_ms": 5000}
        self.assertFalse(se.ensure_stitch_slot_timeline_dur_ms(h, slot))


if __name__ == "__main__":
    unittest.main()

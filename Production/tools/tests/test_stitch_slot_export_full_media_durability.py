#!/usr/bin/env python3
"""STITCH_SLOT_EXPORT_FULL_MEDIA_V1 — full playable video on stitch slot upsert."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from server_handlers.stitch_editor import (  # noqa: E402
    STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
    stitch_upsert_event_slot,
)


def _make_tone_mp4(path: Path, duration_s: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration_s:.3f}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


class _MockStitchState:
    def __init__(self):
        self.state = {"jobs": {}}

    def read_state(self):
        return self.state

    def mutate_state(self, fn):
        fn(self.state)


class StitchSlotExportFullMediaTests(unittest.TestCase):
    def test_upsert_writes_probed_video_dur_ms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event = root / "Production" / "Event_FULL"
            event.mkdir(parents=True)
            video = event / "phase_a_stitched_test.mp4"
            _make_tone_mp4(video, 38.5)
            rel = f"Production/Event_FULL/{video.name}"

            store = _MockStitchState()
            h = mock.Mock()
            h.app = mock.Mock()
            h.app.stitch_state = store
            # stitch_state_store_for_job prefers _event_stitch_state over stitch_state.
            h.app._event_stitch_state = store
            h.app.event_dir = "Production/Event_FULL"
            h._stitch_project_root = lambda: root
            h._stitch_resolve_path = lambda raw: str(root / raw)
            h._ffprobe_duration_ms = lambda p: int(
                float(
                    subprocess.check_output(
                        [
                            "ffprobe", "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "csv=p=0",
                            str(p),
                        ],
                        text=True,
                    ).strip()
                )
                * 1000
            )

            with mock.patch(
                "server_handlers.stitch_editor.require_media_under_project",
                side_effect=lambda p, **_: str(p),
            ), mock.patch(
                "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
                return_value=False,
            ), mock.patch(
                "server_handlers.stitch_editor.ensure_stitch_slot_canonical_default_sfx_cues",
                return_value=False,
            ), mock.patch(
                "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
                return_value=False,
            ), mock.patch(
                "server_handlers.stitch_slot_playback.bake_slot_playback_mp4",
                return_value=38.5,
            ):
                job_name, probed_ms, _warnings, _playback = stitch_upsert_event_slot(
                    h,
                    "Event_FULL",
                    "intro",
                    {"video_path": rel, "source": "kling_o3_export_pre"},
                )

            slot = store.state["jobs"][job_name]["slots"]["intro"]
            self.assertIn("assembled/intro_playback_", slot["video_path"])
            self.assertGreater(probed_ms, 35_000)
            self.assertEqual(slot["video_dur_ms"], probed_ms)

    def test_upsert_rejects_missing_video_path(self):
        h = mock.Mock()
        h.app = mock.Mock()
        h.app.stitch_state = _MockStitchState()
        with self.assertRaises(ValueError) as ctx:
            stitch_upsert_event_slot(h, "Event_X", "intro", {"source": "test"})
        self.assertIn(STITCH_SLOT_EXPORT_FULL_MEDIA_V1, str(ctx.exception))

    def test_markers_in_source(self):
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        self.assertIn("STITCH_SLOT_EXPORT_FULL_MEDIA_V1", editor)
        self.assertIn("beat map ends at", editor)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""STITCH_SLOT_VIDEO_LINEAGE_V1 — operator export replaces slot; playback follows video_path."""
from __future__ import annotations

import unittest
import unittest.mock as mock
from pathlib import Path

from server_handlers.stitch_editor import (
    STITCH_SLOT_VIDEO_LINEAGE_V1,
    _stitch_should_skip_video_replace,
    stitch_upsert_event_slot,
)


class _MockStitchState:
    def __init__(self, initial=None):
        self.state = initial or {"jobs": {}}

    def read_state(self):
        return self.state

    def mutate_state(self, fn):
        fn(self.state)


class _MockHandler:
    def __init__(self, state=None):
        self.app = type("App", (), {"stitch_state": _MockStitchState(state)})()

    def _stitch_resolve_path(self, path: str) -> str:
        return path

    def _ffprobe_duration_ms(self, _path) -> int:
        return 50_000


class TestStitchSlotVideoLineage(unittest.TestCase):
    def test_marker_constant(self):
        self.assertEqual(STITCH_SLOT_VIDEO_LINEAGE_V1, "STITCH_SLOT_VIDEO_LINEAGE_V1")

    def test_client_source_markers(self):
        tools = Path(__file__).resolve().parents[1]
        tab = (tools / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
            encoding="utf-8",
        )
        bg = (tools / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(
            encoding="utf-8",
        )
        lineage = (
            tools / "storyboard-v2" / "src" / "utils" / "stitchSlotVideoLineage.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("STITCH_SLOT_VIDEO_LINEAGE_V1", lineage)
        self.assertIn("mergeHydratedPreviewUrlsAfterLineage", tab)
        self.assertIn("invalidateStitchSlotPlaybackCaches", tab)
        self.assertIn("stitchExportKeptExistingWarning", bg)
        self.assertIn("data-stitch-slot-video-lineage", tab)

    def test_operator_export_replaces_older_stored_video(self):
        state = {
            "jobs": {
                "Event_2_stitch": {
                    "slots": {
                        "resolution": {
                            "video_path": (
                                "Production/Event_2/assembled/"
                                "resolution_kling_o3_20260621T025509Z.mp4"
                            ),
                            "video_dur_ms": 49_708,
                        },
                    },
                },
            },
        }
        h = _MockHandler(state)
        with mock.patch(
            "server_handlers.stitch_editor.stitch_slot_export_media_preflight",
            return_value=(49_708, []),
        ), mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.apply_stitch_slot_default_ambient_preset",
            return_value=False,
        ), mock.patch(
            "server_handlers.stitch_editor.ensure_stitch_slot_canonical_default_sfx_cues",
            return_value=False,
        ):
            job_name, dur_ms, warnings, _playback = stitch_upsert_event_slot(
                h,
                "Event_2",
                "resolution",
                {
                    "video_path": (
                        "Production/Event_2/assembled/"
                        "resolution_kling_o3_20260618T120000Z.mp4"
                    ),
                    "source": "kling_o3_export_post",
                },
                operator_export=True,
            )
        self.assertEqual(job_name, "Event_2_stitch")
        self.assertEqual(dur_ms, 49_708)
        self.assertFalse(any("kept existing" in w for w in warnings))
        slot = h.app.stitch_state.state["jobs"]["Event_2_stitch"]["slots"]["resolution"]
        self.assertIn("20260618T120000Z", slot["video_path"])

    def test_background_import_still_skips_older_video(self):
        state = {
            "jobs": {
                "Event_2_stitch": {
                    "slots": {
                        "intro": {
                            "video_path": (
                                "Production/Event_2/assembled/"
                                "intro_kling_o3_20260619T193118Z.mp4"
                            ),
                            "video_dur_ms": 177_000,
                        },
                    },
                },
            },
        }
        h = _MockHandler(state)
        old = "Production/Event_2/assembled/intro_kling_o3_20260619T193118Z.mp4"
        new = "Production/Event_2/assembled/intro_kling_o3_20260618T120000Z.mp4"
        self.assertTrue(_stitch_should_skip_video_replace(h, old, new))
        job_name, kept_ms, warnings, _playback = stitch_upsert_event_slot(
            h,
            "Event_2",
            "intro",
            {"video_path": new, "source": "scene_assemble"},
        )
        self.assertTrue(any("kept existing" in w for w in warnings))
        slot = h.app.stitch_state.state["jobs"]["Event_2_stitch"]["slots"]["intro"]
        self.assertIn("20260619T193118Z", slot["video_path"])
        self.assertEqual(kept_ms, 177_000)
        self.assertEqual(job_name, "Event_2_stitch")

    def test_bg_export_passes_operator_export(self):
        src = (Path(__file__).resolve().parents[1] / "server_handlers" / "kling_o3.py").read_text(
            encoding="utf-8",
        )
        block = src.split("def _run_bg_export_to_stitcher_core", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("operator_export=True", block)


if __name__ == "__main__":
    unittest.main()

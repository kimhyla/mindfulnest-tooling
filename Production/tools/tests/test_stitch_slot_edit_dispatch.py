#!/usr/bin/env python3
"""STITCH_SLOT_EDIT_DISPATCH_V1 — tiered stitch_save_job dispatch."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_slot_edit_dispatch as dispatch  # noqa: E402


class StitchSlotEditDispatchTests(unittest.TestCase):
    def test_sfx_only_edit_skips_ambient_rebuild_when_artifact_fresh(self) -> None:
        h = MagicMock()
        h._stitch_cache_dir.return_value = Path("/tmp/cache")
        prev = {
            "video_path": "Production/Milestones/m1/assembled/x.mp4",
            "ambient_bed": "intro_ambient",
            "ambient_volume": 0.15,
            "ambient_mix_sig": "sig123",
            "ambient_mix_hash": "abc123def456",
            "ambient_mix_duration_ms": 94000,
            "sfx_cues": [],
        }
        nxt = {
            **prev,
            "sfx_cues": [
                {
                    "id": "c1",
                    "offset_ms": 1000,
                    "duration_ms": 3000,
                    "source_path": "/sfx/a.mp3",
                },
            ],
        }

        with unittest.mock.patch.object(
            dispatch,
            "ambient_artifact_fresh",
            return_value=True,
        ):
            plan = dispatch.plan_stitch_save_dispatch(
                h,
                prev_slots={"standalone": prev},
                next_slots={"standalone": nxt},
                touched_keys=["standalone"],
                edit_kind_hint=dispatch.EDIT_KIND_SFX_GEOMETRY,
            )

        self.assertEqual(plan["ambient_rebuild_keys"], [])
        self.assertEqual(plan["ambient_skip_keys"], ["standalone"])
        self.assertEqual(plan["mux_rebuild_hint_keys"], ["standalone"])
        self.assertEqual(plan["edit_kind_inferred"], dispatch.EDIT_KIND_SFX_GEOMETRY)

    def test_ambient_dropdown_triggers_ambient_rebuild(self) -> None:
        h = MagicMock()
        prev = {
            "video_path": "Production/Milestones/m1/assembled/x.mp4",
            "ambient_bed": "bed_a",
            "ambient_volume": 0.15,
            "sfx_cues": [],
        }
        nxt = {**prev, "ambient_bed": "bed_b"}

        with unittest.mock.patch.object(
            dispatch,
            "ambient_artifact_fresh",
            return_value=False,
        ):
            plan = dispatch.plan_stitch_save_dispatch(
                h,
                prev_slots={"standalone": prev},
                next_slots={"standalone": nxt},
                touched_keys=["standalone"],
            )

        self.assertIn("standalone", plan["ambient_rebuild_keys"])
        self.assertEqual(plan["edit_kind_inferred"], dispatch.EDIT_KIND_AMBIENT_GEOMETRY)

    def test_handle_stitch_save_job_wires_dispatch(self) -> None:
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def handle_stitch_save_job", 1)[1].split("\ndef handle_stitch_delete_job", 1)[0]
        self.assertIn("STITCH_SLOT_EDIT_DISPATCH_V1", block)
        self.assertIn("plan_stitch_save_dispatch", block)
        self.assertIn("edit_dispatch", block)
        self.assertIn("slot_keys=ambient_keys", block)

    def test_rebuild_empty_slot_keys_skips_all_ambient(self) -> None:
        src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        block = src.split("def rebuild_stitch_ambient_mixes_for_job", 1)[1].split(
            "\ndef handle_stitch_save_job", 1,
        )[0]
        self.assertIn("if slot_keys is not None:", block)


if __name__ == "__main__":
    unittest.main()

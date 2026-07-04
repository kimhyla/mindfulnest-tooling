"""BG_STITCH_EXPORT_PREFLIGHT_V1 — preflight manifest + operator fix instructions."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bg_stitch_export_preflight import (
    BG_STITCH_EXPORT_PREFLIGHT_V1,
    build_bg_stitch_export_preflight_manifest,
    preflight_error_message,
)
from kling_stitch_readiness import beat_stitch_export_derived_fields


class BgStitchExportPreflightTests(unittest.TestCase):
    def test_still_insert_block_includes_fix_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "still.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_arc1_event5_pre_beat_06",
                "pipeline": "still_insert",
                "kling_o3_status": "still_rendered",
                "kling_o3_video_path": str(clip),
            }
            manifest = build_bg_stitch_export_preflight_manifest(
                arc_number=1,
                event_id="5",
                phase="pre",
                slot_key="intro",
                beats=[beat],
                event_dir=tmp_path,
            )
            self.assertEqual(manifest["code"], BG_STITCH_EXPORT_PREFLIGHT_V1)
            self.assertFalse(manifest["ready"])
            row = manifest["beats"][0]
            self.assertEqual(row["block_code"], "STILL_NEEDS_STITCH_APPROVE")
            self.assertIn("Approve still for stitch", row["fix_instruction"])
            msg = preflight_error_message(manifest)
            self.assertIn("beat 06", msg)

    def test_ready_o3_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_test_beat_01",
                "pipeline": "kling_o3_omni",
                "kling_o3_status": "draft",
                "kling_o3_video_path": str(clip),
            }
            manifest = build_bg_stitch_export_preflight_manifest(
                arc_number=1,
                event_id="1",
                phase="pre",
                slot_key="intro",
                beats=[beat],
                event_dir=tmp_path,
            )
            self.assertTrue(manifest["ready"])
            self.assertTrue(manifest["beats"][0]["ready"])

    def test_derived_fields_match_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "still.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_still",
                "pipeline": "still_insert",
                "kling_o3_video_path": str(clip),
            }
            derived = beat_stitch_export_derived_fields(beat, tmp_path)
            self.assertFalse(derived["stitch_export_ready"])
            self.assertEqual(derived["stitch_export_block_label"], "Approve still clip")
            self.assertIn("Approve still for stitch", derived["stitch_export_fix_instruction"] or "")


if __name__ == "__main__":
    unittest.main()

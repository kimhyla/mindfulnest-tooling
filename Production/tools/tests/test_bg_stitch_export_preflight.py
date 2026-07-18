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

    def test_on_disk_av_drift_blocks_preflight(self):
        """Preflight must catch EXPORT_VALIDATION before the async job starts."""
        import subprocess

        from bg_stitch_export_preflight import _on_disk_clip_av_errors

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bad = tmp_path / "intro_tail.mp4"
            # Video 2.0s, audio 2.2s → ~200ms drift (above 50ms export budget).
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2.0",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2.2",
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    str(bad),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            beat = {
                "beat_id": "bg_arc1_event6_pre_beat_17",
                "pipeline": "kling_o3_omni",
                "kling_o3_status": "approved",
                "kling_o3_video_path": str(bad),
            }
            errs = _on_disk_clip_av_errors([beat], tmp_path)
            self.assertTrue(errs)
            self.assertEqual(errs[0]["code"], "EXPORT_VALIDATION")
            self.assertIn("intro_tail.mp4", errs[0]["message"])


if __name__ == "__main__":
    unittest.main()

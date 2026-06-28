"""KLING_STITCH_READINESS_V1 — structural stitch-export contract tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import beat_generator as bg
from kling_stitch_readiness import (
    KLING_STITCH_READINESS_V1,
    beat_kling_stitch_export_ready,
    finalize_kling_delivery_clip,
    sync_kling_stitch_status_from_active_clip,
)

TOOLS = Path(__file__).resolve().parent.parent
BG_STITCH_TS = TOOLS / "storyboard-v2" / "src" / "utils" / "klingStitchReadiness.ts"
BG_TAB = TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
VERIFY_SH = TOOLS.parent / "scripts" / "verify_kling_stitch_readiness_durability.sh"


class KlingStitchReadinessTests(unittest.TestCase):
    def test_contract_marker(self):
        self.assertEqual(KLING_STITCH_READINESS_V1, "KLING_STITCH_READINESS_V1")

    def test_o3_delivery_clip_ready_without_approved_enum(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_test",
                "pipeline": "kling_o3_omni",
                "kling_o3_status": "draft",
                "kling_o3_video_path": str(clip),
            }
            self.assertTrue(beat_kling_stitch_export_ready(beat, tmp_path))

    def test_still_insert_requires_explicit_approve(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "still.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_still",
                "pipeline": "still_insert",
                "kling_o3_status": "still_rendered",
                "kling_o3_video_path": str(clip),
            }
            self.assertFalse(beat_kling_stitch_export_ready(beat, tmp_path))
            beat["kling_o3_still_stitch_approved"] = True
            self.assertTrue(beat_kling_stitch_export_ready(beat, tmp_path))

    def test_sync_promotes_draft_with_active_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_test",
                "pipeline": "kling_o3_omni",
                "kling_o3_status": "draft",
                "status": "draft",
                "kling_o3_video_path": str(clip),
            }
            self.assertTrue(sync_kling_stitch_status_from_active_clip(beat))
            self.assertEqual(beat["kling_o3_status"], "approved")
            self.assertEqual(beat["status"], "approved")

    def test_finalize_delivery_clip_non_still(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "out.mp4"
            clip.write_bytes(b"x")
            beat = {"beat_id": "b1", "pipeline": "kling_o3_omni"}
            finalize_kling_delivery_clip(beat, str(clip))
            self.assertEqual(beat["kling_o3_status"], "approved")
            self.assertEqual(beat["kling_o3_video_path"], str(clip.resolve()))

    def test_beat_has_stitch_export_clip_delegates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_test",
                "kling_o3_status": "completed",
                "kling_o3_video_path": str(clip),
            }
            self.assertTrue(bg.beat_has_stitch_export_clip(beat, tmp_path))

    def test_client_module_parity_markers(self):
        text = BG_STITCH_TS.read_text(encoding="utf-8")
        self.assertIn("beatKlingStitchExportReady", text)
        self.assertIn(KLING_STITCH_READINESS_V1, text)

    def test_bgtab_embeds_contract_marker(self):
        text = BG_TAB.read_text(encoding="utf-8")
        self.assertIn("data-kling-stitch-readiness-v1", text)
        self.assertNotIn("Approve Kling clip", text)

    def test_auto_pin_delegates_to_stitch_contract(self):
        import tempfile
        from beat_generator import auto_pin_approved_kling_o3_delivery

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            clip = tmp_path / "bg_test_g1_element_o3_master_delivery.mp4"
            clip.write_bytes(b"fake")
            beat = {
                "beat_id": "bg_test",
                "pipeline": "kling_o3_omni",
                "kling_o3_status": "draft",
                "kling_o3_video_path": str(clip),
            }
            # Pin path requires pin_kling_o3_beat — mock by checking gate only via readiness
            from kling_stitch_readiness import beat_kling_stitch_export_ready

            self.assertTrue(beat_kling_stitch_export_ready(beat, tmp_path))
            text = Path(__file__).resolve().parent.parent.joinpath("beat_generator.py").read_text(
                encoding="utf-8",
            )
            self.assertIn("beat_kling_stitch_export_ready", text)
            self.assertNotIn(
                'if str(beat.get("kling_o3_status") or "") != "approved":',
                text[text.find("def auto_pin_approved_kling_o3_delivery"):text.find("def restore_pinned")],
            )


if __name__ == "__main__":
    unittest.main()

"""STITCH_AMBIENT_PREVIEW_V1 — ambient preview must not auto-call saveJobSlots (SFX wipe regression)."""

from __future__ import annotations

import unittest
from pathlib import Path

from server_handlers import stitch_editor as se


class StitchAmbientPreviewNoSaveWipeTests(unittest.TestCase):
    def test_stitcher_tab_uses_preview_not_save_for_ambient_queue(self) -> None:
        tab = Path(se.__file__).parent.parent / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
        src = tab.read_text(encoding="utf-8")
        self.assertIn("STITCH_AMBIENT_PREVIEW_V1", src)
        block = src.split("STITCH_AMBIENT_PREVIEW_V1", 1)[1].split("}, [job?.name, ambientBakeTick", 1)[0]
        self.assertIn("buildSlotPreview", block)
        self.assertNotIn("saveJobSlots(", block)

    def test_save_job_slots_guard_present(self) -> None:
        tab = Path(se.__file__).parent.parent / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
        src = tab.read_text(encoding="utf-8")
        self.assertIn("stitchSnapshotReadyForSave", src)
        self.assertIn("STITCH_SFX_PLAYBACK_TRUTH_V1", src)

    def test_ensure_job_slot_defaults_includes_standalone(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def ensure_job_slot_defaults", 1)[1].split("\ndef collect_stitch_job_slot_warnings", 1)[0]
        self.assertIn("STITCH_MILESTONE_SLOT_ORDER", block)

    def test_rebuild_ambient_uses_stitch_state_store_for_job(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def rebuild_stitch_ambient_mixes_for_job", 1)[1].split("\ndef handle_stitch_save_job", 1)[0]
        self.assertIn("stitch_store = stitch_state_store_for_job(h, job_name)", block)
        self.assertIn("stitch_store.mutate_state(clear_ambient)", block)

    def test_rebuild_skips_unchanged_ambient_on_sfx_save(self) -> None:
        src = Path(se.__file__).read_text(encoding="utf-8")
        block = src.split("def rebuild_stitch_ambient_mixes_for_job", 1)[1].split("\ndef handle_stitch_save_job", 1)[0]
        self.assertIn("STITCH_AMBIENT_BAKE_SKIP_UNCHANGED_V1", block)
        self.assertIn('"skipped": True', block)

    def test_save_does_not_bind_ambient_url_when_sfx_present(self) -> None:
        tab = Path(se.__file__).parent.parent / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
        src = tab.read_text(encoding="utf-8")
        self.assertIn("STITCH_SFX_DROP_INSTANT_V1", src)
        block = src.split("if (built._ambient_mix_url)", 1)[1].split("}", 1)[0]
        self.assertIn("stitchSlotRequiresMuxedPreview", block)


if __name__ == "__main__":
    unittest.main()

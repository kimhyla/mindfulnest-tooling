"""BG_EXPORT_STITCHER_NO_GLOBAL_REHYDRATE_V1 — Send to Stitcher must not wipe other tabs."""

from __future__ import annotations

import unittest
from pathlib import Path


class BgExportStitcherRefreshIsolation(unittest.TestCase):
    def test_finish_export_does_not_bump_server_rehydrate(self) -> None:
        src = Path(__file__).resolve().parents[1] / "storyboard-v2/src/components/BgTab.tsx"
        text = src.read_text(encoding="utf-8")
        block = text.split("const finishExportTerminal = useCallback", 1)[1].split(
            "}, [exportScopeKey, stitchSlotForSegment]", 1,
        )[0]
        self.assertIn("stitcherRefreshTick.value += 1", block)
        self.assertNotIn("serverRehydrateTick.value += 1", block)

    def test_phase_export_pattern_unchanged(self) -> None:
        src = Path(__file__).resolve().parents[1] / "storyboard-v2/src/components/phase/PhaseProducer.tsx"
        text = src.read_text(encoding="utf-8")
        self.assertIn("stitcherRefreshTick.value += 1", text)
        self.assertNotIn("serverRehydrateTick.value += 1", text)


if __name__ == "__main__":
    unittest.main()

"""Magic path must follow manual_path point-for-point (polyline), not Bezier smooth."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from magic_compositor import MagicCompositor  # noqa: E402


class MagicPathPolylineTests(unittest.TestCase):
    def _mc(self, path_pts, path_interp="polyline"):
        with tempfile.TemporaryDirectory() as tmp:
            bg = Path(tmp) / "bg.png"
            Image.new("RGB", (720, 544), (40, 40, 40)).save(bg)
            return MagicCompositor(
                background_path=str(bg),
                path_pts=path_pts,
                style="tessa_ori",
                duration=1.0,
                fps=24,
                seed=1,
                output_dir=tmp,
                label="test",
                path_interp=path_interp,
                path_timing="uniform",
            )

    def test_polyline_hits_every_knot(self):
        pts = [(0.1, 0.2), (0.5, 0.8), (0.9, 0.3)]
        mc = self._mc(pts, "polyline")
        for i, expected in enumerate(pts):
            t = i / (len(pts) - 1)
            got = mc._polyline(t)
            self.assertAlmostEqual(got[0], expected[0], places=5)
            self.assertAlmostEqual(got[1], expected[1], places=5)

    def test_bezier_can_miss_interior_knots(self):
        """Bezier is legacy smooth mode — interior points are control points, not on-curve."""
        pts = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]
        mc = self._mc(pts, "bezier")
        mid = mc._bezier(0.5)
        # Interior control at (0.5, 1.0) pulls curve upward but midpoint is not the knot.
        self.assertNotAlmostEqual(mid[1], 1.0, places=2)

    def test_default_interp_is_polyline(self):
        mc = self._mc([(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(mc.path_interp, "polyline")


if __name__ == "__main__":
    unittest.main()

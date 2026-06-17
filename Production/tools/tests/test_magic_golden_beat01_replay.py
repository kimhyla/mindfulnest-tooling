"""Golden replay: beat 1 approved magic_video must match LD-469 polyline+screen contract."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from magic_compositor import MagicCompositor, composite_screen_rgb  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "magic_golden_beat01.json"
DROPBOX = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)


def _extract_frame(video: Path, t: float, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(out)],
        capture_output=True,
        check=True,
    )


def _replay_frame(
    *,
    path_pts: list,
    W: int,
    H: int,
    duration: float,
    fps: int,
    t: float,
    path_interp: str,
    seed: int = 1,
) -> np.ndarray:
    n_frames = max(2, int(duration * fps))
    frame_idx = min(int(t / duration * (n_frames - 1)), n_frames - 1)
    with tempfile.TemporaryDirectory() as tmp:
        black = Path(tmp) / "black.png"
        Image.new("RGB", (W, H), (0, 0, 0)).save(black)
        mc = MagicCompositor(
            background_path=str(black),
            path_pts=path_pts,
            style="tessa_ori",
            duration=duration,
            fps=fps,
            seed=seed,
            output_dir=tmp,
            label="golden_replay",
            path_interp=path_interp,
        )
        mc._gain = 1.0
        return mc._make_trail(frame_idx)


class MagicGoldenBeat01ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.golden = DROPBOX / cls.fixture["golden_mp4"]
        cls.source = DROPBOX / cls.fixture["source_mp4"]
        if not cls.golden.is_file() or not cls.source.is_file():
            raise unittest.SkipTest("Dropbox golden/source MP4 not present")

    def _composite_at_golden_time(self, path_interp: str) -> tuple[float, int]:
        auth = self.fixture["path_authored_against"]
        W, H = auth["width"], auth["height"]
        t = float(self.fixture["sample_time_s"])
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            g_png = tmp_p / "golden.png"
            s_png = tmp_p / "src.png"
            _extract_frame(self.golden, t, g_png)
            _extract_frame(self.source, t, s_png)
            g_arr = np.array(Image.open(g_png).convert("RGB"))
            s_arr = np.array(Image.open(s_png).convert("RGB").resize((W, H)))
            trail = _replay_frame(
                path_pts=self.fixture["magic_manual_path"],
                W=W,
                H=H,
                duration=float(self.fixture["duration_s"]),
                fps=int(self.fixture["fps"]),
                t=t,
                path_interp=path_interp,
            )
            out = composite_screen_rgb(s_arr.astype(np.float32), trail)
            diff = np.abs(g_arr.astype(float) - out.astype(float))
            bright = int((diff.max(axis=2) > 12).sum())
            return float(diff.mean()), bright

    def test_polyline_screen_within_golden_threshold(self):
        mean, _ = self._composite_at_golden_time("polyline")
        self.assertLessEqual(mean, self.fixture["thresholds"]["mean_diff_max"])

    def test_bezier_worse_than_polyline_for_beat01_path(self):
        poly_mean, _ = self._composite_at_golden_time("polyline")
        bez_mean, _ = self._composite_at_golden_time("bezier")
        delta_min = float(self.fixture["thresholds"]["bezier_mean_diff_min_delta"])
        self.assertGreaterEqual(bez_mean - poly_mean, delta_min)

    def test_still_and_video_share_composite_screen_rgb(self):
        bg = np.array([[[200, 180, 160]]], dtype=np.float32)
        trail = np.array([[[50, 40, 20]]], dtype=np.float32)
        out = composite_screen_rgb(bg, trail)
        self.assertEqual(out.shape, (1, 1, 3))
        self.assertGreater(int(out[0, 0, 0]), 200)


class SceneRegistryBeat21Tests(unittest.TestCase):
    def test_beat21_entry_in_tooling_registry(self):
        import yaml

        reg_path = Path(__file__).resolve().parent.parent / "scene_registry.yaml"
        reg = yaml.safe_load(reg_path.read_text())
        key = "m1_e1_res_bg_arc1_event1_post_beat_21"
        self.assertIn(key, reg)
        scene = reg[key]
        self.assertEqual(scene.get("style"), "tessa_ori")
        self.assertEqual(scene.get("beat"), "res_beat_02")
        self.assertGreaterEqual(len(scene.get("manual_path") or []), 20)


if __name__ == "__main__":
    unittest.main()

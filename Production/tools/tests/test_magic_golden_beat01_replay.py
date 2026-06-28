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

    def test_bright_stone_path_fraction_triggers_ambient_widen(self):
        """Orbital nest paths cross enough bright stone to widen ambient pool."""
        auth = self.fixture["path_authored_against"]
        W, H = auth["width"], auth["height"]
        DROPBOX = Path(
            "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            b1_png = tmp_p / "b1.png"
            _extract_frame(DROPBOX / self.fixture["source_mp4"], 1.0, b1_png)
            b1_arr = np.array(Image.open(b1_png).convert("RGB").resize((W, H))).astype(np.float32)
            black = tmp_p / "black.png"
            Image.new("RGB", (W, H), (0, 0, 0)).save(black)
            mc_b1 = MagicCompositor(
                background_path=str(black),
                path_pts=self.fixture["magic_manual_path"],
                style="tessa_ori",
                duration=2.0,
                fps=24,
                seed=1,
                output_dir=tmp,
                label="b1",
                path_interp="polyline",
                path_authored_against=auth,
            )
            mc_b1.set_path_luminance_from_array(b1_arr)
            self.assertFalse(mc_b1._bright_stone_ambient())

            import yaml

            reg = yaml.safe_load(
                (Path(__file__).resolve().parent.parent / "scene_registry.yaml").read_text()
            )
            path21 = reg["m1_e1_res_bg_arc1_event1_post_beat_21"]["manual_path"]
            b21_src = (
                DROPBOX
                / "Production/Event_1/kling_o3_clips/"
                "bg_arc1_event1_post_beat_21_still_insert_1781706877_tts.mp4"
            )
            if not b21_src.is_file():
                self.skipTest("beat 21 source mp4 missing")
            b21_png = tmp_p / "b21.png"
            _extract_frame(b21_src, 1.0, b21_png)
            b21_arr = np.array(Image.open(b21_png).convert("RGB").resize((1280, 720))).astype(
                np.float32
            )
            black21 = tmp_p / "black21.png"
            Image.new("RGB", (1280, 720), (0, 0, 0)).save(black21)
            mc_b21 = MagicCompositor(
                background_path=str(black21),
                path_pts=path21,
                style="tessa_ori",
                duration=2.7,
                fps=24,
                seed=1,
                output_dir=tmp,
                label="b21",
                path_interp="polyline",
                path_authored_against={"width": 1280, "height": 720},
            )
            mc_b21.set_path_luminance_from_array(b21_arr)
            self.assertTrue(mc_b21._bright_stone_ambient())


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

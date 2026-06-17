"""LD-469 visible magic — permanent contract tests (all events/arcs/roles).

See Production/docs/HOW_TO_MAKE_VISIBLE_MAGIC.md
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import magic_render_contract as mrc  # noqa: E402
from magic_compositor import MagicCompositor, composite_screen_rgb  # noqa: E402

BACKGROUND_PY = TOOLS / "server_handlers" / "background.py"
PRODUCTION_SERVER_PY = TOOLS / "production_server.py"
BEAT_MAGIC_TSX = TOOLS / "storyboard-v2" / "src" / "components" / "BeatMagicButtons.tsx"
HOWTO_DOC = TOOLS.parent / "docs" / "HOW_TO_MAKE_VISIBLE_MAGIC.md"
DROPBOX = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)


def _handler_source(fn_name: str) -> str:
    text = BACKGROUND_PY.read_text()
    m = re.search(rf"def {fn_name}\(.*?(?=\n\ndef |\Z)", text, re.DOTALL)
    assert m, f"{fn_name} not found"
    return m.group(0)


def _handler_code_without_comments(fn_name: str) -> str:
    src = _handler_source(fn_name)
    lines = []
    for line in src.splitlines():
        stripped = line.split("#", 1)[0]
        lines.append(stripped)
    return "\n".join(lines)


class MagicRenderContractConstantsTests(unittest.TestCase):
    def test_contract_version_is_frozen_marker(self):
        self.assertEqual(mrc.MAGIC_RENDER_CONTRACT_VERSION, "LD-469-VISIBLE-MAGIC-V2")

    def test_bright_stone_constants_match_compositor_import(self):
        from magic_compositor import BRIGHT_STONE_AMB_MIX  # noqa: WPS433

        self.assertEqual(BRIGHT_STONE_AMB_MIX, mrc.BRIGHT_STONE_AMB_MIX)
        self.assertEqual(mrc.PRODUCTION_PATH_INTERP, "polyline")
        self.assertEqual(mrc.PRODUCTION_GAIN, 1.0)


class MagicHandlerWiringTests(unittest.TestCase):
    def test_magic_still_uses_ld469_contract(self):
        src = _handler_source("handle_magic_still")
        code = _handler_code_without_comments("handle_magic_still")
        for marker in mrc.REQUIRED_STILL_MARKERS:
            self.assertIn(marker, src, f"missing {marker} in handle_magic_still")
        for bad in mrc.FORBIDDEN_HANDLER_PATTERNS:
            self.assertNotIn(bad, code, f"forbidden {bad} in handle_magic_still")

    def test_magic_video_uses_ld469_contract(self):
        src = _handler_source("handle_magic_video")
        code = _handler_code_without_comments("handle_magic_video")
        for marker in mrc.REQUIRED_VIDEO_MARKERS:
            self.assertIn(marker, src, f"missing {marker} in handle_magic_video")
        for bad in mrc.FORBIDDEN_HANDLER_PATTERNS:
            self.assertNotIn(bad, code, f"forbidden {bad} in handle_magic_video")

    def test_production_server_exposes_magic_endpoints(self):
        text = PRODUCTION_SERVER_PY.read_text()
        self.assertIn("_handle_magic_still", text)
        self.assertIn("_handle_magic_video", text)
        self.assertIn("/api/storyboard/magic_still", text)
        self.assertIn("/api/storyboard/magic_video", text)

    def test_storyboard_buttons_target_canonical_endpoints(self):
        text = BEAT_MAGIC_TSX.read_text()
        self.assertIn("/api/storyboard/magic_still", text)
        self.assertIn("/api/storyboard/magic_video", text)
        self.assertIn("scope_video_role", text)

    def test_howto_doc_exists_and_references_contract(self):
        self.assertTrue(HOWTO_DOC.is_file(), "HOW_TO_MAKE_VISIBLE_MAGIC.md missing")
        body = HOWTO_DOC.read_text()
        self.assertIn("magic_render_contract.py", body)
        self.assertIn("composite_screen_rgb", body)
        self.assertIn("set_path_luminance_from_array", body)


class MagicBrightStoneBehaviorTests(unittest.TestCase):
    def test_bright_stone_is_ambient_only_and_visible(self):
        """Bright stone branch = no sparkle layer; must still read on nest stone."""
        import math
        import yaml
        from scipy.ndimage import gaussian_filter

        reg = yaml.safe_load((TOOLS / "scene_registry.yaml").read_text())
        path21 = reg["m1_e1_res_bg_arc1_event1_post_beat_21"]["manual_path"]
        b21_src = (
            DROPBOX
            / "Production/Event_1/kling_o3_clips/"
            "bg_arc1_event1_post_beat_21_still_insert_1781706877_tts.mp4"
        )
        if not b21_src.is_file():
            self.skipTest("beat 21 source mp4 missing")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            src_png = tmp_p / "src.png"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "1", "-i", str(b21_src), "-frames:v", "1", str(src_png)],
                capture_output=True,
                check=True,
            )
            bg = np.array(Image.open(src_png).convert("RGB").resize((1280, 720))).astype(np.float32)
            black = tmp_p / "black.png"
            Image.new("RGB", (1280, 720), (0, 0, 0)).save(black)
            mc = MagicCompositor(
                background_path=str(black),
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
            mc._gain = 1.0
            mc.set_path_luminance_from_array(bg)
            self.assertTrue(mc._bright_stone_ambient())

            frame_idx = 65
            trail = mc._make_trail(frame_idx)

            # Recompute ambient-only layer (sparkle must be zero in bright-stone mode)
            s = mc.s
            W, H = mc.W, mc.H
            t_head = frame_idx / (mc.n_frames - 1)
            amb_acc = np.zeros((H, W, 3), np.float32)
            for (ts, sx_n, sy_n, tw_ph, tw_sp, bmax, dsz, col) in mc._particles:
                if ts > t_head:
                    break
                age = (t_head - ts) / max(t_head, 1e-6)
                fade = 1.0 - age * s["fade_tail"]
                twinkle = 0.35 + 0.65 * math.sin(frame_idx * tw_sp + tw_ph)
                alpha = bmax * fade * twinkle
                if alpha < 0.04:
                    continue
                fx, fy = mc._path_at(ts)
                pw = mc._path_width(fy)
                px = int(fx * W + sx_n * pw * s["scatter_x_frac"])
                py = int(fy * H + sy_n * pw * s["scatter_y_frac"])
                if not (0 <= px < W and 0 <= py < H):
                    continue
                av = alpha * s["ambient_gain"] * mc._gain * mrc.BRIGHT_STONE_AMB_GAIN_MULT
                for c in range(3):
                    amb_acc[py, px, c] += col[c] * av / 255.0
            sy, sx = mrc.BRIGHT_STONE_AMB_BLUR_YX
            for c in range(3):
                amb_acc[:, :, c] = gaussian_filter(amb_acc[:, :, c], sigma=[sy, sx])
            amb_only = np.clip(amb_acc * mrc.BRIGHT_STONE_AMB_MIX, 0, 255)
            self.assertLess(float(np.max(np.abs(trail - amb_only))), 0.01)

            comp = composite_screen_rgb(bg, trail)
            diff = np.abs(comp.astype(float) - bg)
            self.assertGreater(float(diff.mean()), 0.8, "bright-stone magic too faint")
            self.assertGreater(float(diff.max()), 40.0)

    def test_dark_forest_keeps_sparkle_contribution(self):
        FIX = json.loads(
            (Path(__file__).resolve().parent / "fixtures" / "magic_golden_beat01.json").read_text()
        )
        auth = FIX["path_authored_against"]
        W, H = auth["width"], auth["height"]
        src = DROPBOX / FIX["source_mp4"]
        if not src.is_file():
            self.skipTest("beat 1 source missing")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            png = tmp_p / "f.png"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "1", "-i", str(src), "-frames:v", "1", str(png)],
                capture_output=True,
                check=True,
            )
            bg = np.array(Image.open(png).convert("RGB").resize((W, H))).astype(np.float32)
            black = tmp_p / "black.png"
            Image.new("RGB", (W, H), (0, 0, 0)).save(black)
            mc = MagicCompositor(
                background_path=str(black),
                path_pts=FIX["magic_manual_path"],
                style="tessa_ori",
                duration=7.44,
                fps=24,
                seed=1,
                output_dir=tmp,
                label="b1",
                path_interp="polyline",
                path_authored_against=auth,
            )
            mc._gain = 1.0
            mc.set_path_luminance_from_array(bg)
            self.assertFalse(mc._bright_stone_ambient())
            trail = mc._make_trail(int(3 / 7.44 * (int(7.44 * 24) - 1)))
            self.assertGreater(float(trail.max()), 100.0)


class MagicStyleResolverTests(unittest.TestCase):
    def test_default_style_is_tessa_ori_for_unknown_beat(self):
        import beat_generator as bg

        style = bg.resolve_magic_style_for_render(
            "bg_arc99_event9_post_beat_99",
            sidecar={},
            production_state={},
            video_role="resolution",
            manual_path=[[0.5, 0.5]],
            scene_registry={},
        )
        self.assertEqual(style, "tessa_ori")


if __name__ == "__main__":
    unittest.main()

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
BEAT_GENERATOR_PY = TOOLS / "beat_generator.py"
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

    def test_production_compositor_kwargs_match_magic_compositor_init(self):
        import inspect

        from magic_compositor import MagicCompositor

        sig = inspect.signature(MagicCompositor.__init__)
        allowed = set(sig.parameters) - {"self"}
        kwargs = mrc.production_magic_compositor_kwargs(path_authored_against={"width": 1280, "height": 720})
        self.assertEqual(kwargs["path_interp"], mrc.PRODUCTION_PATH_INTERP)
        for key in kwargs:
            self.assertIn(key, allowed, f"production kwargs leak unknown MagicCompositor param {key!r}")

    def test_handlers_do_not_reference_phantom_contract_attrs(self):
        text = BACKGROUND_PY.read_text()
        for match in re.finditer(r"\bmrc\.(\w+)", text):
            name = match.group(1)
            self.assertTrue(
                hasattr(mrc, name),
                f"background.py references mrc.{name} but magic_render_contract has no such attribute",
            )

    def test_handlers_do_not_pass_phantom_compositor_kwargs(self):
        for fn in mrc.PRODUCTION_MAGIC_HANDLER_FUNCTIONS:
            src = _handler_source(fn)
            self.assertNotIn("path_timing", src, f"{fn} must not pass path_timing until compositor supports it")
            self.assertNotIn("PRODUCTION_PATH_TIMING", src, f"{fn} must not reference phantom PRODUCTION_PATH_TIMING")
            self.assertIn(
                "production_magic_compositor_kwargs",
                src,
                f"{fn} must route MagicCompositor kwargs through production_magic_compositor_kwargs",
            )

    def test_beat_generator_run_magic_compositor_uses_factory(self):
        text = BEAT_GENERATOR_PY.read_text()
        self.assertIn("production_magic_compositor_kwargs", text)
        self.assertNotIn("PRODUCTION_PATH_TIMING", text)
        self.assertNotIn("path_timing=", text)
        m = re.search(
            r"def run_magic_compositor\(.*?(?=\n\ndef |\Z)",
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "run_magic_compositor not found")
        self.assertIn("production_magic_compositor_kwargs()", m.group(0))

    def test_no_phantom_production_path_timing_anywhere_in_tools(self):
        for rel in (
            "server_handlers/background.py",
            "beat_generator.py",
            "production_server.py",
        ):
            body = (TOOLS / rel).read_text()
            self.assertNotIn(
                "PRODUCTION_PATH_TIMING",
                body,
                f"{rel} must not reference removed phantom constant PRODUCTION_PATH_TIMING",
            )


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
    def test_sparkle_strength_fades_on_midtones(self):
        self.assertEqual(mrc.sparkle_strength_for_bg_lum(40, bright_stone_mode=False), 1.0)
        self.assertEqual(mrc.sparkle_strength_for_bg_lum(85, bright_stone_mode=False), 1.0)
        mid = mrc.sparkle_strength_for_bg_lum(115, bright_stone_mode=False)
        self.assertGreater(mid, 0.0)
        self.assertLess(mid, 0.5)
        self.assertEqual(mrc.sparkle_strength_for_bg_lum(130, bright_stone_mode=False), 0.0)
        self.assertEqual(mrc.sparkle_strength_for_bg_lum(90, bright_stone_mode=True), 0.0)

    def test_mixed_path_guard_event2_profile(self):
        # Event 2 beat 1: 20% bright, peak ~216 — must trigger mixed guard, not full bright-stone.
        lums = [56.8, 20.9, 63.0, 73.9, 56.9, 40.0, 120.7, 49.0, 14.2, 26.2,
                76.9, 79.3, 215.8, 79.9, 21.4, 45.2, 115.2, 170.2, 184.2, 200.9]
        self.assertFalse(mrc.bright_stone_ambient_from_lums(lums))
        self.assertTrue(mrc.mixed_path_sparkle_guard_from_lums(lums))

    def test_mixed_path_suppresses_sparkle_layer(self):
        """Event 2–style mixed paths: guard fires; render is ambient-only (no sparkle acc)."""
        lums = [56.8, 20.9, 63.0, 73.9, 56.9, 40.0, 120.7, 49.0, 14.2, 26.2,
                76.9, 79.3, 215.8, 79.9, 21.4, 45.2, 115.2, 170.2, 184.2, 200.9]
        self.assertTrue(mrc.mixed_path_sparkle_guard_from_lums(lums))

        e2_src = (
            DROPBOX
            / "Production/Event_2/kling_o3_clips/"
            "bg_arc1_event2_post_beat_01_g1_element_o3_master_delivery.mp4"
        )
        if not e2_src.is_file():
            self.skipTest("Event 2 beat 1 source missing")
        path = [
            (0.586, 0.337), (0.498, 0.261), (0.398, 0.349), (0.352, 0.569),
            (0.435, 0.664), (0.543, 0.701), (0.648, 0.753), (0.674, 0.897),
            (0.562, 0.956), (0.316, 0.995),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            src_png = tmp_p / "src.png"
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(e2_src), "-frames:v", "1", str(src_png)],
                capture_output=True,
                check=True,
            )
            bg = np.array(Image.open(src_png).convert("RGB")).astype(np.float32)
            black = tmp_p / "black.png"
            Image.new("RGB", (1280, 720), (0, 0, 0)).save(black)
            mc = MagicCompositor(
                background_path=str(black),
                path_pts=path,
                style="tessa_ori",
                duration=8.0,
                fps=24,
                seed=99,
                output_dir=tmp,
                label="e2b1",
                path_interp="polyline",
                path_authored_against={"width": 1280, "height": 720},
            )
            mc._gain = 1.0
            mc.set_path_luminance_from_array(bg)
            self.assertTrue(mc._mixed_path_sparkle_guard())
            frame_idx = int(3 / 8 * (mc.n_frames - 1))
            trail = mc._make_trail(frame_idx)
            comp = composite_screen_rgb(bg, trail)
            diff = np.abs(comp.astype(float) - bg)
            H, W = bg.shape[:2]
            face = diff[H // 6 : H // 2, W // 3 : 2 * W // 3]
            # Blocky sparkle regression: face region must not clip to harsh white squares.
            self.assertLess(float(face.max()), 200.0)
            self.assertGreater(float(trail.max()), 20.0, "ambient river must remain visible")

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
                px_lum = mc._pixel_luminance(px, py)
                if px_lum > mrc.BRIGHT_STONE_LUM_THRESHOLD:
                    amb_scale = max(0.0, min(1.0, (170.0 - px_lum) / 40.0))
                    av *= amb_scale
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

    def test_event2_scene_registry_key_primary(self):
        keys = mrc.resolve_magic_scene_registry_keys(
            "bg_arc1_event2_post_beat_01",
            event_id="Event_2",
            video_role="resolution",
        )
        self.assertEqual(keys[0], "m1_e2_res_bg_arc1_event2_post_beat_01")
        self.assertIn("m1_e1_res_bg_arc1_event2_post_beat_01", keys)

    def test_event2_style_from_primary_registry_key(self):
        registry = {
            "m1_e2_res_bg_arc1_event2_post_beat_01": {
                "style": "wide_ori",
                "force_wide_ori": True,
            },
        }
        style = mrc.resolve_magic_style_from_registry(
            "bg_arc1_event2_post_beat_01",
            registry,
            event_id="Event_2",
            video_role="resolution",
        )
        self.assertEqual(style, "wide_ori")

    def test_bgtab_o3_preview_not_gated_on_legacy_source_only(self):
        text = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text()
        self.assertIn("resolveO3TileMagicOverrideUrl", text)
        self.assertNotIn("opt?.source === 'approved_kling_o3_video'", text)
        self.assertIn("overrideVideoUrl ?? playbackUrl", text)

    def test_magic_preview_urls_respect_path_exists(self):
        text = BEAT_MAGIC_TSX.read_text()
        self.assertIn("magic_video_path_exists === false", text)
        self.assertIn("magic_still_path_exists === false", text)

    def test_stitch_export_uses_magic_on_beat_contract(self):
        text = (TOOLS / "beat_generator.py").read_text()
        block = text.split("def resolve_beat_stitch_export_clip_path", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("resolve_active_magic_layer", block)
        self.assertIn("_kling_o3_export_clip_path", block)
        self.assertNotIn("beat_still_insert_kling_stitch_export_ready", block)

    def test_magic_video_allowed_on_still_stitch_approved_beats(self):
        text = (TOOLS / "server_handlers" / "background.py").read_text()
        block = text.split("def handle_magic_video", 1)[1].split("\ndef handle_", 1)[0]
        self.assertNotIn("STILL_STITCH_APPROVED", block)


if __name__ == "__main__":
    unittest.main()

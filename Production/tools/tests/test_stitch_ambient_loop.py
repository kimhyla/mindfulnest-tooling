#!/usr/bin/env python3
"""STITCH_AMBIENT_LOOP_XFADE_V1 — seamless ambient bed loop tests."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "server_handlers"))

from server_handlers.stitch_ambient_loop import (  # noqa: E402
    STITCH_AMBIENT_FULL_PERIOD_TILE_V2,
    STITCH_AMBIENT_LOOP_TRIM_V2,
    STITCH_AMBIENT_LOOP_XFADE_V1,
    ambient_bed_needs_seamless_loop,
    build_ambient_bed_filter_lane,
    build_ambient_bed_filter_lane_for_file,
    clamp_ambient_loop_crossfade_s,
    estimate_ambient_tile_period_s,
    probe_ambient_bed_active_span,
)


class StitchAmbientLoopTests(unittest.TestCase):
    def test_clamp_crossfade_short_bed(self):
        self.assertLessEqual(clamp_ambient_loop_crossfade_s(5.0), 5.0 * 0.35)
        self.assertGreaterEqual(clamp_ambient_loop_crossfade_s(5.0), 0.25)

    def test_needs_seamless_when_slot_longer_than_bed(self):
        self.assertTrue(ambient_bed_needs_seamless_loop(32.0, 65.0))
        self.assertFalse(ambient_bed_needs_seamless_loop(32.0, 30.0))
        self.assertFalse(ambient_bed_needs_seamless_loop(0.5, 10.0))

    def test_filter_uses_full_period_tile_when_looping(self):
        lane = build_ambient_bed_filter_lane(1, 32.808, 65.0, 0.15)
        self.assertIn("acrossfade", lane)
        self.assertIn("[bed]", lane)
        self.assertIn("[amb1tile]aloop=loop=-1", lane)
        self.assertIn("[amb1pre]", lane)
        self.assertIn("[amb1wrap]", lane)
        self.assertIn("concat=n=2:v=0:a=1[amb1tile]", lane)

    def test_filter_not_crossfade_only_tile(self):
        lane = build_ambient_bed_filter_lane(1, 27.35, 49.0, 0.15)
        xf = clamp_ambient_loop_crossfade_s(27.35)
        self.assertNotIn(
            f"acrossfade=d={xf:.3f}:c1=tri:c2=tri[amb1tile];"
            "[amb1tile]aloop",
            lane,
        )
        self.assertAlmostEqual(estimate_ambient_tile_period_s(27.35), 27.35)

    def test_filter_no_acrossfade_when_no_loop(self):
        lane = build_ambient_bed_filter_lane(1, 60.0, 45.0, 0.15)
        self.assertNotIn("acrossfade", lane)
        self.assertIn("atrim=duration=45.000", lane)

    def test_long_bed_uses_xfade_tile_not_raw_aloop(self):
        lane = build_ambient_bed_filter_lane(1, 8.0, 25.0, 0.15)
        self.assertIn("acrossfade", lane)
        self.assertIn("[amb1tile]aloop=loop=-1", lane)
        self.assertIn("[amb1pre]", lane)
        self.assertIn("concat=n=2:v=0:a=1[amb1tile]", lane)
        self.assertNotIn(
            "asetpts=PTS-STARTPTS,aloop=loop=-1",
            lane.replace("[amb1tile]aloop=loop=-1", ""),
        )

    def test_ffmpeg_seamless_loop_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            bed = Path(tmp) / "bed.mp3"
            out = Path(tmp) / "out.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=8",
                    "-ac", "1", "-ar", "44100", str(bed),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            lane = build_ambient_bed_filter_lane(0, 8.0, 25.0, 0.15, out_label="aout")
            cmd = [
                "ffmpeg", "-y", "-i", str(bed),
                "-filter_complex", lane,
                "-map", "[aout]",
                "-ac", "1", "-ar", "44100", str(out),
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            self.assertTrue(out.is_file())
            dur = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout.strip()
            self.assertAlmostEqual(float(dur), 25.0, delta=0.15)

    def test_resolution_bed_trailing_silence_trimmed(self):
        bed = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
            / "Production/assets/sound_library/ambient/ambien bed pretty option4.mp3"
        )
        if not bed.is_file():
            self.skipTest("resolution ambient bed not on disk")
        start, end = probe_ambient_bed_active_span(bed)
        self.assertLess(start, 0.5)
        self.assertLess(end, 33.0)
        self.assertGreater(end, 25.0)
        lane = build_ambient_bed_filter_lane_for_file(0, bed, 35.343, 49.7, 0.15)
        self.assertIn("atrim=start=", lane)
        self.assertIn("acrossfade", lane)

    def test_sig_token_includes_v2_marker(self):
        from server_handlers.stitch_ambient_loop import (
            STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1,
            ambient_loop_sig_token,
        )

        tok = ambient_loop_sig_token()
        self.assertIn(STITCH_AMBIENT_LOOP_TRIM_V2, tok)
        self.assertIn(STITCH_AMBIENT_FULL_PERIOD_TILE_V2, tok)
        self.assertIn(STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1, tok)
        self.assertIn("no_hard_aloop_v1", tok)
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        self.assertIn("build_ambient_bed_filter_lane_for_file", editor)
        self.assertIn("build_ambient_bed_filter_lane_for_file", server)
        self.assertIn("ambient_loop_sig_token", (TOOLS / "server_handlers" / "stitch_media_sig.py").read_text())

    def test_client_ambient_loop_sig_matches_server_token(self):
        from server_handlers.stitch_ambient_loop import ambient_loop_sig_token

        const = (
            TOOLS / "storyboard-v2" / "src" / "utils" / "stitchConstants.ts"
        ).read_text(encoding="utf-8")
        server_tok = ambient_loop_sig_token()
        self.assertIn(server_tok, const)

    def test_mux_preview_export_forces_ambient_rebuild(self):
        editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
        server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        self.assertIn("STITCH_AMBIENT_FORCE_REBUILD_ON_EXPORT_V1", editor)
        self.assertIn("force_ambient_mix_rebuild", editor)
        self.assertIn("force_ambient_mix_rebuild", server)
        export_block = editor.split("def build_stitch_slot_mux_preview_file", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("force_ambient_mix_rebuild", export_block)
        preview = editor.split("def handle_stitch_preview", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("force_ambient_mix_rebuild", preview)
        self.assertIn("four_files_passthrough", preview)


if __name__ == "__main__":
    unittest.main()

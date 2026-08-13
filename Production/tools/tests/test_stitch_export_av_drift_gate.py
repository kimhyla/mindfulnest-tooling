"""Beat Gen Send-to-Stitcher must reject clips with large video/audio drift."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))

from credentials_lib.ffmpeg_stitch import (  # noqa: E402
    STITCH_EXPORT_AV_MAX_DRIFT_S,
    STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S,
    STITCH_EXPORT_NORM_AV_MAX_DRIFT_S,
    assert_stitch_export_clips_av_aligned,
    av_duration_drift_s,
    heal_mp4_video_timeline_authority_if_needed,
)


def _make_aac_frame_drift_mp4(path: Path, *, video_s: float, extra_audio_s: float) -> None:
    """Video re-encode + longer copied audio — mimics magic-on-video AAC-frame drift."""
    audio_s = video_s + extra_audio_s
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={video_s:.3f}",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={audio_s:.3f}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "1",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def _make_misaligned_mp4(path: Path) -> None:
    """Video ~6s, audio ~3s — mimics broken whiteout hold."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=44100:cl=mono",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=3",
            "-filter_complex", "[1:v]tpad=stop_mode=clone:stop_duration=3[v]",
            "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


class StitchExportAvDriftGateTests(unittest.TestCase):
    def test_assert_blocks_misaligned_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "intro_tail.mp4"
            _make_misaligned_mp4(bad)
            with self.assertRaises(ValueError) as ctx:
                assert_stitch_export_clips_av_aligned([bad])
            self.assertIn("intro_tail.mp4", str(ctx.exception))

    def test_concat_export_calls_av_gate(self):
        text = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
        block = text.split("def concat_kling_o3_approved_beats", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("assert_stitch_export_clips_av_aligned", block)

    def test_export_resolves_heal_aac_drift_before_assert(self):
        text = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
        resolve = text.split("def resolve_segment_stitch_export_clip_paths", 1)[1].split(
            "\ndef concat_kling_o3_approved_beats", 1,
        )[0]
        self.assertIn("heal_mp4_video_timeline_authority_if_needed", resolve)
        concat = text.split("def concat_kling_o3_approved_beats", 1)[1].split("\ndef ", 1)[0]
        heal_idx = resolve.index("heal_mp4_video_timeline_authority_if_needed")
        # Heal must run while building clip_paths, which concat then asserts.
        self.assertIn("assert_stitch_export_clips_av_aligned", concat)
        self.assertGreater(heal_idx, 0)

    def test_export_drift_threshold_is_quarter_second(self):
        self.assertEqual(STITCH_EXPORT_AV_MAX_DRIFT_S, 0.25)

    def test_concat_gate_is_fifty_ms_not_quarter_second(self):
        """Event_6 Container 1 magic was 0.052s — over 50ms, under 250ms."""
        self.assertEqual(STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S, 0.05)
        text = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
        block = text.split("def concat_kling_o3_approved_beats", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S", block)

    def test_heal_event6_magic_aac_frame_drift_then_concat_gate_passes(self):
        """Golden: Event_6 resolution beat_01 magic was v=4.917 a=4.969 drift=0.052s."""
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "magic_video_bg_arc1_event6_post_beat_01.mp4"
            _make_aac_frame_drift_mp4(clip, video_s=2.00, extra_audio_s=0.052)
            drift = av_duration_drift_s(clip)
            self.assertGreater(drift, STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S)
            self.assertLessEqual(drift, STITCH_EXPORT_AV_MAX_DRIFT_S)
            with self.assertRaises(ValueError) as ctx:
                assert_stitch_export_clips_av_aligned(
                    [clip],
                    max_drift_s=STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S,
                )
            self.assertIn("misaligned", str(ctx.exception))
            healed = heal_mp4_video_timeline_authority_if_needed(clip)
            self.assertLessEqual(healed, STITCH_EXPORT_NORM_AV_MAX_DRIFT_S)
            assert_stitch_export_clips_av_aligned(
                [clip],
                max_drift_s=STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S,
            )

    def test_heal_does_not_mask_broken_whiteout_hold(self):
        """3s audio / 6s video is the original broken-clip class — still fail loud."""
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "intro_tail.mp4"
            _make_misaligned_mp4(bad)
            before = av_duration_drift_s(bad)
            self.assertGreater(before, STITCH_EXPORT_AV_MAX_DRIFT_S)
            after = heal_mp4_video_timeline_authority_if_needed(bad)
            self.assertGreater(after, STITCH_EXPORT_AV_MAX_DRIFT_S)
            with self.assertRaises(ValueError):
                assert_stitch_export_clips_av_aligned(
                    [bad],
                    max_drift_s=STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S,
                )


if __name__ == "__main__":
    unittest.main()

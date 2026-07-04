"""Fade-through-black with inserted black hold (does not eat clip bodies)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib import ffmpeg_stitch as fs  # noqa: E402


def test_expand_inserts_black_between_clips(tmp_path: Path) -> None:
    clips = []
    for i in range(2):
        p = tmp_path / f"clip_{i}.mp4"
        fs.render_black_pause_clip(2.0, p)
        clips.append(p)
    out = fs.expand_clips_with_black_pause_boundaries(
        clips,
        [2800],
        tmp_path / "scratch",
        visual_out_ms=600,
        visual_in_ms=600,
        fade_audio=False,
    )
    assert len(out) == 3
    assert out[1].name.startswith("black_pause_")


def test_expand_accepts_string_clip_paths(tmp_path: Path) -> None:
    """Stitch pipeline passes str paths from _stitch_resolve_path — must not .stem crash."""
    clips = []
    for i in range(2):
        p = tmp_path / f"clip_{i}.mp4"
        fs.render_black_pause_clip(2.0, p)
        clips.append(str(p))
    out = fs.expand_clips_with_black_pause_boundaries(
        clips,
        [2800],
        str(tmp_path / "scratch"),
        visual_out_ms=600,
        visual_in_ms=600,
        fade_audio=False,
    )
    assert len(out) == 3
    assert all(isinstance(part, Path) for part in out)


def test_allocate_pair_fade_budget_manifest_defaults() -> None:
    out_ms, in_ms, black_ms = fs.allocate_pair_fade_budget(1500)
    assert out_ms == 500
    assert in_ms == 500
    assert black_ms == 500

    out_ms, in_ms, black_ms = fs.allocate_pair_fade_budget(2800)
    assert out_ms == 600
    assert in_ms == 600
    assert black_ms == 1600


def test_intro_export_does_not_clamp_pair_fades_for_black_pause() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    block = src.split("def _ffmpeg_concat_kling_clips_with_pair_fades", 1)[1].split("\ndef ", 1)[0]
    assert "compute_fade_clamp_per_pair" not in block
    assert "expand_clips_with_black_pause_boundaries" in block


def test_stitch_module_preview_uses_manifest_visual_fades() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "_load_intro_fade_out_video_tail_ms" in src
    assert "_load_intro_final_pair_fade_ms" in src

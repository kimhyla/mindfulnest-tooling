"""VIDEO_QUALITY_V1 — single source for H.264 encode constants (all pipelines)."""
from __future__ import annotations

VIDEO_QUALITY_CRF = "18"
VIDEO_QUALITY_PRESET_BAKE = "slow"
VIDEO_QUALITY_PRESET_PREVIEW = "fast"
VIDEO_QUALITY_PRESET_BASE_CLIP = "fast"

# Light gradient smoothing on normalize (fireplace / soft BG). Chained after scale/pad/fps.
VIDEO_QUALITY_GRADFUN_VF = "gradfun=strength=1.2:radius=6"

# Slot trim / dissolve aux encodes (production_server pre-trim, fade head/tail).
AUX_H264_ENCODER_ARGS: tuple[str, ...] = (
    "-c:v",
    "libx264",
    "-preset",
    VIDEO_QUALITY_PRESET_PREVIEW,
    "-crf",
    VIDEO_QUALITY_CRF,
    "-bf",
    "0",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-pix_fmt",
    "yuv420p",
)

# Phase A/B Kling idle base normalize (1280×960 pad).
BASE_CLIP_FFMPEG_VIDEO_ARGS: tuple[str, ...] = (
    "-c:v",
    "libx264",
    "-crf",
    VIDEO_QUALITY_CRF,
    "-preset",
    VIDEO_QUALITY_PRESET_BASE_CLIP,
)

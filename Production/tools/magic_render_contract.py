"""LD-469 visible magic — single production render contract (all events/arcs/roles).

Both Storyboard buttons MUST use this contract:
  - Add magic on still  → POST /api/storyboard/magic_still
  - Add magic on video  → POST /api/storyboard/magic_video

Authoritative doc: Production/docs/HOW_TO_MAKE_VISIBLE_MAGIC.md
"""
from __future__ import annotations

MAGIC_RENDER_CONTRACT_VERSION = "LD-469-VISIBLE-MAGIC-V2"

# ── Shared production invariants (intro + resolution, Event_1..N, all arcs) ──
PRODUCTION_STYLE_DEFAULT = "tessa_ori"
PRODUCTION_PATH_INTERP = "polyline"  # path_picker lineTo — NOT bezier
PRODUCTION_GAIN = 1.0
PRODUCTION_COMPOSITE = "screen_rgb"  # composite_screen_rgb — NOT additive, NOT ffmpeg YUV screen

# Marker strings — CI greps handlers for these; do not rename without updating tests.
HANDLER_MARKER_STILL = "MAGIC_RENDER_CONTRACT_V2_STILL"
HANDLER_MARKER_VIDEO = "MAGIC_RENDER_CONTRACT_V2_VIDEO"

# ── Bright stone branch (nest orbital, light paving, any high-lum path) ───────
BRIGHT_STONE_LUM_THRESHOLD = 130.0
BRIGHT_STONE_PATH_FRACTION = 0.25
BRIGHT_STONE_AMB_BLUR_YX = (3.5, 11.0)
BRIGHT_STONE_AMB_MIX = 300.0
BRIGHT_STONE_AMB_GAIN_MULT = 2.0

# Golden oracle — approved beat 1 resolution magic (never overwrite this file).
GOLDEN_BEAT01_REL = "Production/Event_1/magic_video_beat_01_20260605-211951.mp4"
GOLDEN_BEAT01_SOURCE_REL = (
    "Production/Event_1/kling_o3_clips/bg_arc1_event1_post_beat_01_g0.mp4"
)

# Forbidden in production handlers (tests fail if reintroduced).
FORBIDDEN_HANDLER_PATTERNS = (
    "mc.render_video(black_bg=True",
    "mc.render_video(",
    'blend=all_mode=screen',
    'path_interp="bezier"',
    "path_interp='bezier'",
)

REQUIRED_STILL_MARKERS = (
    HANDLER_MARKER_STILL,
    "render_ld469_on_background",
    f'path_interp="{PRODUCTION_PATH_INTERP}"',
    "gain=1.0",
)

REQUIRED_VIDEO_MARKERS = (
    HANDLER_MARKER_VIDEO,
    "composite_screen_rgb",
    "set_path_luminance_from_array",
    f'path_interp="{PRODUCTION_PATH_INTERP}"',
    "mc._gain = 1.0",
)


def bright_stone_ambient_from_lums(lums: list[float]) -> bool:
    """True when enough of the path crosses bright stone (orbital nest, paving, etc.)."""
    if not lums:
        return False
    above = sum(1 for x in lums if x > BRIGHT_STONE_LUM_THRESHOLD)
    return (above / len(lums)) >= BRIGHT_STONE_PATH_FRACTION

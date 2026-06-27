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

# Sparkle river on dark forest (beat 1 oracle) is full-strength below this lum;
# fade to zero by BRIGHT_STONE_LUM_THRESHOLD so warm fur / stone edges never get
# blocky 1–3px white squares (Event 2 mixed paths, character crossings).
SPARKLE_FULL_BELOW_LUM = 85.0

# Mixed path: some bright hotspots but not enough for full bright-stone branch.
MIXED_PATH_BRIGHT_FRAC_MIN = 0.10
MIXED_PATH_PEAK_LUM_MIN = 175.0

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
    "PRODUCTION_PATH_TIMING",
    "path_timing=",
)

# Production server handlers that construct MagicCompositor — must use production_magic_compositor_kwargs.
PRODUCTION_MAGIC_HANDLER_FUNCTIONS = (
    "handle_magic_still",
    "handle_magic_video",
    "handle_magic_submit_path",
)

REQUIRED_STILL_MARKERS = (
    HANDLER_MARKER_STILL,
    "render_ld469_on_background",
    "production_magic_compositor_kwargs",
    "gain=1.0",
)

REQUIRED_VIDEO_MARKERS = (
    HANDLER_MARKER_VIDEO,
    "composite_screen_rgb",
    "set_path_luminance_from_array",
    "production_magic_compositor_kwargs",
    "mc._gain = 1.0",
)


def production_magic_compositor_kwargs(
    *,
    path_authored_against: dict | None = None,
) -> dict:
    """Canonical MagicCompositor kwargs for production handlers — only params the compositor accepts."""
    out: dict = {"path_interp": PRODUCTION_PATH_INTERP}
    if path_authored_against is not None:
        out["path_authored_against"] = path_authored_against
    return out


def bright_stone_ambient_from_lums(lums: list[float]) -> bool:
    """True when enough of the path crosses bright stone (orbital nest, paving, etc.)."""
    if not lums:
        return False
    above = sum(1 for x in lums if x > BRIGHT_STONE_LUM_THRESHOLD)
    return (above / len(lums)) >= BRIGHT_STONE_PATH_FRACTION


def mixed_path_sparkle_guard_from_lums(lums: list[float]) -> bool:
    """True when path crosses bright hotspots (face, glass, stone) but not full bright-stone."""
    if not lums or bright_stone_ambient_from_lums(lums):
        return False
    bright = sum(1 for x in lums if x > BRIGHT_STONE_LUM_THRESHOLD)
    frac = bright / len(lums)
    peak = max(lums)
    return peak >= MIXED_PATH_PEAK_LUM_MIN and frac >= MIXED_PATH_BRIGHT_FRAC_MIN


def sparkle_strength_for_bg_lum(lum: float, *, bright_stone_mode: bool) -> float:
    """Per-pixel sparkle scale — full on dark forest, zero on bright stone / mid-tone fur."""
    if bright_stone_mode:
        return 0.0
    if lum >= BRIGHT_STONE_LUM_THRESHOLD:
        return 0.0
    if lum <= SPARKLE_FULL_BELOW_LUM:
        return 1.0
    span = BRIGHT_STONE_LUM_THRESHOLD - SPARKLE_FULL_BELOW_LUM
    if span <= 0:
        return 0.0
    return max(0.0, (BRIGHT_STONE_LUM_THRESHOLD - lum) / span)


def _normalize_event_num(event_id: str | int) -> str:
    s = str(event_id).strip()
    if s.lower().startswith("event_"):
        s = s[6:]
    if s.lower().startswith("e") and s[1:].isdigit():
        s = s[1:]
    return s or "1"


def _video_role_registry_token(video_role: str) -> str:
    role = (video_role or "resolution").strip().lower()
    if role in ("resolution", "post"):
        return "res"
    if role in ("intro", "pre"):
        return "pre"
    if role.startswith("phase"):
        return role.replace("_", "")
    return role[:3] or "res"


def resolve_magic_scene_registry_keys(
    bg_beat_id: str,
    *,
    module_id: int = 1,
    event_id: str | int = 1,
    video_role: str = "resolution",
) -> tuple[str, ...]:
    """Candidate scene_registry.yaml keys — primary first, legacy Event_1 aliases after."""
    evt = _normalize_event_num(event_id)
    role_tok = _video_role_registry_token(video_role)
    beat_id = (bg_beat_id or "").strip()
    primary = f"m{module_id}_e{evt}_{role_tok}_{beat_id}"

    short = beat_id
    for prefix in (
        f"bg_arc1_event{evt}_post_",
        f"bg_arc1_event{evt}_pre_",
        "bg_arc1_event1_post_",
        "bg_arc1_event1_pre_",
    ):
        if beat_id.startswith(prefix):
            short = beat_id[len(prefix):]
            break

    legacy_e1_full = f"m1_e1_res_{beat_id}"
    legacy_e1_short = f"m1_e1_res_{short}"
    seen: dict[str, None] = {}
    for key in (primary, legacy_e1_full, legacy_e1_short):
        if key and key not in seen:
            seen[key] = None
    return tuple(seen.keys())


def resolve_magic_scene_registry_entry(
    bg_beat_id: str,
    scene_registry: dict | None,
    *,
    module_id: int = 1,
    event_id: str | int = 1,
    video_role: str = "resolution",
) -> tuple[str | None, dict]:
    """Return (matched_key, scene_dict) from registry for this beat/event/role."""
    if not scene_registry:
        return None, {}
    for key in resolve_magic_scene_registry_keys(
        bg_beat_id,
        module_id=module_id,
        event_id=event_id,
        video_role=video_role,
    ):
        scene = scene_registry.get(key)
        if isinstance(scene, dict):
            return key, scene
    return None, {}


def resolve_magic_style_from_registry(
    bg_beat_id: str,
    scene_registry: dict | None,
    *,
    module_id: int = 1,
    event_id: str | int = 1,
    video_role: str = "resolution",
) -> str:
    """Production default tessa_ori; wide_ori only with explicit force_wide_ori pin."""
    _, scene = resolve_magic_scene_registry_entry(
        bg_beat_id,
        scene_registry,
        module_id=module_id,
        event_id=event_id,
        video_role=video_role,
    )
    style = scene.get("style")
    if isinstance(style, str) and style in ("tessa_ori", "wide_ori"):
        if style == "wide_ori" and scene.get("force_wide_ori"):
            return "wide_ori"
    return PRODUCTION_STYLE_DEFAULT


def resolve_magic_still_duration_from_registry(
    bg_beat_id: str,
    scene_registry: dict | None,
    *,
    module_id: int = 1,
    event_id: str | int = 1,
    video_role: str = "resolution",
    fallback: float = 4.0,
) -> float:
    _, scene = resolve_magic_scene_registry_entry(
        bg_beat_id,
        scene_registry,
        module_id=module_id,
        event_id=event_id,
        video_role=video_role,
    )
    dur = scene.get("magic_still_duration_s")
    if isinstance(dur, (int, float)) and float(dur) > 0:
        return float(dur)
    return float(fallback)

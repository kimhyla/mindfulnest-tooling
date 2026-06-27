"""Canonical smooth Ken Burns render — single filter chain for all still zoom paths."""
from __future__ import annotations

DEFAULT_KEN_BURNS_ZOOM_START = 1.0
DEFAULT_KEN_BURNS_ZOOM_END = 1.06
DEFAULT_KEN_BURNS_FPS = 24


def ken_burns_smooth_vf(
    *,
    pan_x_pct: float = 50.0,
    pan_y_pct: float = 50.0,
    zoom_start: float = DEFAULT_KEN_BURNS_ZOOM_START,
    zoom_end: float = DEFAULT_KEN_BURNS_ZOOM_END,
    duration_s: float,
    out_w: int = 1280,
    out_h: int = 720,
    fps: int = DEFAULT_KEN_BURNS_FPS,
) -> str:
    """Smoothstep-eased zoom via 4K prescale + animated crop (no zoompan jitter)."""
    duration_s = max(float(duration_s), 0.001)
    prescale_w = max(out_w * 3, 3840)
    prescale_h = max(out_h * 3, 2160)
    focal_x = max(0.0, min(1.0, pan_x_pct / 100.0))
    focal_y = max(0.0, min(1.0, pan_y_pct / 100.0))
    delta = zoom_end - zoom_start
    progress = f"min(t/{duration_s:.6f},1)"
    smooth = f"({progress})*({progress})*(3-2*({progress}))"
    zoom_expr = f"({zoom_start:.6f})+({delta:.6f})*({smooth})"
    return (
        f"scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={prescale_w}:{prescale_h},"
        f"crop=w='iw/({zoom_expr})':h='ih/({zoom_expr})':"
        f"x='(iw-ow)*{focal_x:.4f}':y='(ih-oh)*{focal_y:.4f}',"
        f"scale={out_w}:{out_h}:flags=lanczos,fps={fps}"
    )

"""Phase A Arlo green-still Path A — canonical assets + fringe-safe composite.

Kim-approved Gate 0 (2026-07-31): spill-kill + warm edge a* (vJ).
Send / idle / composite MUST use the trimmed still + full_size_3 plate —
never the raw ChatGPT green still (baked neon fringe in fur tips).

Kling start/end idle re-introduces a dark-green cutout "trim" — especially
on the bushy tail. Final idle for Send is post-processed with
``choke_kling_idle_outline``:

- body ring ``body_px`` from true background (all around)
- heavier outer-right ring ``tail_px`` only on rightward-facing edges
  (does NOT rectangular-erode a right half — that severs body↔tail)
- key-spill pass (pure/near key green only — never olive vest green)

Filename still says ``choke_tail6_v4`` (Send pin); algorithm is outer-tail.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

# Relative to Production/
TRIMMED_STILL_REL = (
    "NEW STYLE CHARACTERS/ARLO/arlo_still_green_trimmed_1920x1080_v1.png"
)
TRIMMED_STILL_ALIAS_REL = "NEW STYLE CHARACTERS/ARLO/arlo_still_green_trimmed.png"
PLATE_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_room_plate_background_full_size_3_1920x1080_v1.png"
)
APPROVED_COMPOSITE_REL = (
    "NEW STYLE CHARACTERS/ARLO/arlo_gate0_approved_composite_trimmed_v1.png"
)
# Idle: Kling from trimmed still, then outer-tail choke (Send pin name v4).
# Raw Kling + uniform choke3 left trim; rectangular right-half erode severs
# body↔tail — do not Send those.
IDLE_FROM_TRIMMED_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_gesture_idle_from_trimmed_still_10s_choke_tail6_v4.mp4"
)

# Measured from trimmed still corners (uniform key after Gate 0 pin).
KEY_RGB = (3, 241, 5)

# Outline choke — Kim 2026-07-31: body OK at 3px; outer tail needs heavier.
IDLE_CHOKE_BODY_PX = 3
IDLE_CHOKE_TAIL_PX = 8
IDLE_TAIL_X_FRAC = 0.55  # right-side fraction for extra outer-tail ring

IDLE_PROMPT = (
    "CLOSE MEDIUM SHOT — Arlo the squirrel, warm and friendly, "
    "direct eye contact with camera. "
    "MOUTH LOCK — lips fully sealed closed the entire clip, no talking, "
    "no mouth movement. "
    "HEAD LOCK — head level and steady, no head tilt back. "
    "LOCKED CAMERA — perfect static camera hold, zero zoom, zero pan, "
    "zero dolly, zero Ken Burns. "
    "Solid chroma-green background unchanged — no room, no desk, no props. "
    "Gentle idle only: breathe, blink, tiny ear shifts. No pacing, no large gestures. "
    "Silent video — no music, no dialogue. "
    "No black outline, no cutout stroke, no trim line around the character."
)

IDLE_NEGATIVE = (
    "open mouth, talking, lip sync, chewing, smiling wide, "
    "camera zoom, pan, dolly, Ken Burns, "
    "desk, room, fireplace, books, wizard hat, "
    "white eyes, blank eyes, "
    "black outline, cutout edge, trim line, stroke, border, halo, "
    "human hands, bird, music, soundtrack"
)


def production_root_from_event(event_dir: Path) -> Path:
    return Path(event_dir).expanduser().resolve().parent


def resolve_trimmed_still(production_root: Path) -> Path:
    """Authority still for idle + lipsync character layer."""
    root = Path(production_root)
    for rel in (TRIMMED_STILL_REL, TRIMMED_STILL_ALIAS_REL):
        p = root / rel
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"trimmed Arlo green still missing under {root} "
        f"(expected {TRIMMED_STILL_REL})"
    )


def resolve_plate(production_root: Path) -> Path:
    p = Path(production_root) / PLATE_REL
    if not p.is_file():
        raise FileNotFoundError(f"Arlo plate missing: {p}")
    return p


def resolve_send_idle(production_root: Path) -> Path:
    p = Path(production_root) / IDLE_FROM_TRIMMED_REL
    if not p.is_file():
        raise FileNotFoundError(f"Send idle missing: {p}")
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_send_assets(production_root: Path) -> dict:
    """Fail closed if Send would pick the untrimmed still or raw Kling idle."""
    still = resolve_trimmed_still(production_root)
    plate = resolve_plate(production_root)
    idle = resolve_send_idle(production_root)
    name = still.name.lower()
    if "trimmed" not in name:
        raise RuntimeError(
            f"Send still must be trimmed spill-clean asset, got {still.name}"
        )
    if still.name == "arlo still green background.png":
        raise RuntimeError(
            "refusing raw ChatGPT green still — use arlo_still_green_trimmed*"
        )
    idle_name = idle.name.lower()
    if "choke_tail6_v4" not in idle_name:
        raise RuntimeError(
            f"Send idle must be choke_tail6_v4 (tail trim fixed), got {idle.name}"
        )
    return {
        "still": str(still),
        "still_sha256": sha256_file(still),
        "plate": str(plate),
        "plate_sha256": sha256_file(plate),
        "idle": str(idle),
        "idle_sha256": sha256_file(idle),
        "key_rgb": list(KEY_RGB),
        "idle_choke_body_px": IDLE_CHOKE_BODY_PX,
        "idle_choke_tail_px": IDLE_CHOKE_TAIL_PX,
    }


def _is_key_spill_rgb(
    rgb: np.ndarray,
    key_rgb: tuple[int, int, int] = KEY_RGB,
) -> np.ndarray:
    """Chroma-key / dark-green Kling stroke — not olive costume green."""
    im = rgb.astype(np.float32)
    key = np.array(key_rgb, dtype=np.float32)
    dist = np.linalg.norm(im - key.reshape(1, 1, 3), axis=2)
    r, g, b = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    near_key = dist < 110
    pure_green = (g > 60) & (g > r + 35) & (g > b + 35) & (r < 100)
    return near_key | pure_green


def choke_kling_idle_outline(
    rgb: np.ndarray,
    *,
    body_px: int = IDLE_CHOKE_BODY_PX,
    tail_px: int = IDLE_CHOKE_TAIL_PX,
    tail_x_frac: float = IDLE_TAIL_X_FRAC,
    key_rgb: tuple[int, int, int] = KEY_RGB,
) -> np.ndarray:
    """Remove Kling dark-green cutout trim by eating edge pixels into key.

    Iteratively peels true-background edges (not rectangular right-half
    erosion — that invents a vertical cut and severs body↔tail):

    - first ``body_px`` peels: all silhouette edges
    - further peels through ``tail_px``: rightward-facing edges in the
      right fraction only (outer tail), so the ring walks inward
    - then key-spill crumbs on the new edge → key
    """
    from scipy.ndimage import binary_dilation

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected HxWx3 RGB, got {getattr(rgb, 'shape', None)}")
    out = rgb.astype(np.float32).copy()
    key = np.array(key_rgb, dtype=np.float32)
    body_px = max(1, int(body_px))
    tail_px = max(body_px, int(tail_px))
    xs = np.arange(out.shape[1])[None, :]
    right_half = xs >= int(out.shape[1] * float(tail_x_frac))

    for i in range(tail_px):
        dist = np.linalg.norm(out - key.reshape(1, 1, 3), axis=2)
        fg = dist > 50
        bg = ~fg
        any_face = fg & binary_dilation(bg, iterations=1)
        right_face = fg & (
            np.roll(bg, -1, axis=1)
            | np.roll(bg, -2, axis=1)
            | np.roll(bg, -1, axis=0)
            | np.roll(bg, 1, axis=0)
        )
        if i < body_px:
            out[any_face] = key
        else:
            out[right_face & right_half] = key

    # Key-spill / dark-green stroke crumbs on the new edge (not vest green).
    dist2 = np.linalg.norm(out - key.reshape(1, 1, 3), axis=2)
    fg2 = dist2 > 50
    edge2 = fg2 & binary_dilation(~fg2, iterations=max(2, body_px))
    spill = _is_key_spill_rgb(out, key_rgb=key_rgb)
    out[edge2 & spill] = key
    near_key = binary_dilation(dist2 <= 50, iterations=2)
    out[near_key & (out.mean(axis=2) < 45)] = key
    return out.astype(np.uint8)


def composite_trimmed_still_on_plate(
    still_path: Path | None = None,
    plate_path: Path | None = None,
    *,
    production_root: Path | None = None,
) -> np.ndarray:
    """Kim Gate 0 vJ recipe — spill already in trimmed still; warm edge a*."""
    from scipy.ndimage import binary_dilation, binary_erosion
    from skimage.color import lab2rgb, rgb2lab
    from PIL import Image

    if production_root is not None:
        still_path = still_path or resolve_trimmed_still(production_root)
        plate_path = plate_path or resolve_plate(production_root)
    if still_path is None or plate_path is None:
        raise ValueError("still_path and plate_path required")

    still = np.asarray(Image.open(still_path).convert("RGB")).astype(np.float32)
    plate = np.asarray(Image.open(plate_path).convert("RGB")).astype(np.float32)
    if still.shape != plate.shape:
        raise ValueError(f"size mismatch still {still.shape} plate {plate.shape}")

    key = np.array(KEY_RGB, dtype=np.float32)
    dist = np.linalg.norm(still - key.reshape(1, 1, 3), axis=2)
    alpha = np.clip((dist / 255.0 - 0.10) / 0.08, 0, 1)
    alpha[dist < 55] = 0.0
    hard = alpha > 0.55
    hard2 = binary_erosion(hard, iterations=1)
    a = hard2.astype(np.float32)
    ring = binary_dilation(hard2, iterations=1) & ~hard2
    a[ring] = 0.35

    out = a[..., None] * still + (1.0 - a[..., None]) * plate
    lab = rgb2lab(np.clip(out / 255.0, 0, 1))
    edge = binary_dilation(hard2, iterations=2) & ~binary_erosion(hard2, iterations=1)
    fix = edge & (lab[:, :, 1] < -2)
    lab2 = lab.copy()
    lab2[:, :, 1] = np.where(fix, np.maximum(lab[:, :, 1], 8.0), lab[:, :, 1])
    lab2[:, :, 2] = np.where(fix, lab[:, :, 2] + 5, lab[:, :, 2])
    return np.clip(lab2rgb(lab2) * 255.0, 0, 255).astype(np.uint8)

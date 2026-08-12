"""Phase A Arlo green-still Path A — canonical assets + fringe-safe composite.

Gate 0 still trim (Kim-approved lineage; fringe choke added 2026-08-05):

1. Source still at plate size (1920×1080; lanczos if 16:9 smaller)
2. Measure key from corners
3. Soft spillkill — ``G := min(G, max(R,B))`` globally
4. Aggressive ``G := min(G, R)`` **only on screen-adjacent character ring**
5. Restore pure key on screen (dist < 55)
6. Warm-edge a* on character ring
7. **Fringe choke** — peel greenish screen-touching silhouette into key (``STILL_FRINGE_CHOKE_PX``)
8. Composite: **hard matte** eroded inward (no soft green ring) + Lab/neon scrub → plate

Still + idle **video** frames share ``trim_green_character_frame`` +
``composite_trimmed_rgb_on_plate`` — never ffmpeg chromakey-only for fringe.

Do NOT iterate vA–vI again. Closed-mouth ``…trimmed_1920x1080_v1`` is archive.
Open-mouth Send still is ``…openmouth_trimmed_1920x1080_v1``.

Kling idle outline: ``choke_kling_idle_outline`` (outer-tail iterative peel).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

# Relative to Production/
# Open-mouth still (lipsync-ready). Closed-mouth v1 kept on disk but not Send.
TRIMMED_STILL_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_still_green_openmouth_trimmed_1920x1080_v1.png"
)
TRIMMED_STILL_ALIAS_REL = (
    "NEW STYLE CHARACTERS/ARLO/arlo_still_green_openmouth_trimmed.png"
)
# Archive (closed mouth) — do not prefer for lipsync.
CLOSED_MOUTH_TRIMMED_REL = (
    "NEW STYLE CHARACTERS/ARLO/arlo_still_green_trimmed_1920x1080_v1.png"
)
PLATE_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_room_plate_background_full_size_3_1920x1080_v1.png"
)
APPROVED_COMPOSITE_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_gate0_approved_composite_openmouth_trimmed_v1.png"
)
IDLE_FROM_TRIMMED_REL = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_gesture_idle_from_openmouth_trimmed_10s_choke_v5.mp4"
)

# Default key — overwritten at trim time from open-mouth still corners.
# Closed-mouth Gate0 pin was (3,241,5); open-mouth ChatGPT is ~ (2–4, 234, 6–9).
KEY_RGB = (2, 234, 8)

# Outline choke — Kim 2026-07-31: body OK at 3px; outer tail needs heavier.
IDLE_CHOKE_BODY_PX = 3
IDLE_CHOKE_TAIL_PX = 8
IDLE_TAIL_X_FRAC = 0.55  # right-side fraction for extra outer-tail ring
# Still cutout: peel this many px of greenish screen-edge into key before plate.
STILL_FRINGE_CHOKE_PX = 5
# Plate matte: erode character this many px so fringe cannot show as outline.
COMPOSITE_MATTE_ERODE_PX = 3
# After hard matte, scrub this many px inward of leftover greenish fringe → plate.
COMPOSITE_INNER_SCRUB_PX = 5

# Beat Gen silent-base contract (arlo_o3_voice_pipeline): mouth relaxed for
# later lip sync — NOT sealed MOUTH LOCK (that blocks Kling lipsync).
IDLE_PROMPT = (
    "CLOSE MEDIUM SHOT — Arlo the squirrel, warm and friendly, "
    "direct eye contact with camera. "
    "Arlo is present as a silent visual base for later lip sync. "
    "Mouth relaxed, natural friendly expression — lips soft and slightly "
    "parted or gently closed, never hard-sealed, never talking. "
    "HEAD LOCK — head level and steady, no head tilt back. "
    "LOCKED CAMERA — perfect static camera hold, zero zoom, zero pan, "
    "zero dolly, zero Ken Burns. "
    "Solid chroma-green background unchanged — no room, no desk, no props. "
    "Gentle idle only: breathe, blink, tiny ear shifts. No pacing, no large gestures. "
    "Silent video — no music, no dialogue. "
    "No black outline, no cutout stroke, no trim line around the character."
)

IDLE_NEGATIVE = (
    "hard sealed lips, mouth lock, talking, speaking, lip sync chewing, "
    "smiling wide, open mouth chewing, "
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
    """Fail closed if Send would pick sealed-mouth or untrimmed still."""
    still = resolve_trimmed_still(production_root)
    plate = resolve_plate(production_root)
    idle = resolve_send_idle(production_root)
    name = still.name.lower()
    if "openmouth" not in name or "trimmed" not in name:
        raise RuntimeError(
            f"Send still must be openmouth trimmed spill-clean asset, got {still.name}"
        )
    if still.name == "arlo still green background.png":
        raise RuntimeError(
            "refusing raw ChatGPT green still — run spillkill_warm_edge_vj first"
        )
    idle_name = idle.name.lower()
    if "openmouth" not in idle_name or "choke_v5" not in idle_name:
        raise RuntimeError(
            f"Send idle must be openmouth_trimmed choke_v5, got {idle.name}"
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


def measure_key_rgb(rgb: np.ndarray) -> tuple[int, int, int]:
    """Corner-median key (Gate 0 measurement)."""
    h, w = rgb.shape[:2]
    samples = [
        rgb[8, 8],
        rgb[8, w - 9],
        rgb[h - 9, 8],
        rgb[h - 9, w - 9],
        rgb[8, w // 2],
        rgb[h - 9, w // 2],
    ]
    med = np.median(np.stack(samples, axis=0), axis=0)
    return (int(med[0]), int(med[1]), int(med[2]))


def spillkill_warm_edge_vj(
    rgb: np.ndarray,
    *,
    key_rgb: tuple[int, int, int] | None = None,
    screen_dist: float = 55.0,
    fringe_choke_px: int = STILL_FRINGE_CHOKE_PX,
) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Kim Gate 0 still trim — spillkill + warm-edge a* + fringe choke.

    Global soft G-clamp kills neon where G dominates both R and B.
    Aggressive ``G := min(G, R)`` only on the **screen-adjacent character
    ring** — never on interior costume (blue bandana teal must survive).
    Then peel greenish silhouette into key so plate composite has no green trim.

    Returns (trimmed_uint8, key_rgb_used).
    """
    from scipy.ndimage import binary_dilation, binary_erosion
    from skimage.color import lab2rgb, rgb2lab

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected HxWx3, got {getattr(rgb, 'shape', None)}")
    still = rgb.astype(np.float32)
    key_t = key_rgb or measure_key_rgb(still.astype(np.uint8))
    key = np.array(key_t, dtype=np.float32)
    dist = np.linalg.norm(still - key.reshape(1, 1, 3), axis=2)
    screen = dist < float(screen_dist)
    fg = ~screen
    # Character ring next to screen — fur tips / silhouette only.
    edge = binary_dilation(fg, iterations=3) & ~binary_erosion(fg, iterations=1)

    out = still.copy()
    # Soft global clamp: G cannot exceed max(R,B) (kills pure neon channel).
    out[:, :, 1] = np.minimum(still[:, :, 1], np.maximum(still[:, :, 0], still[:, :, 2]))
    # Aggressive crush ONLY on screen-edge ring (not bandana / vest interior).
    extra = edge & (out[:, :, 1] > out[:, :, 0] + 5)
    out[:, :, 1] = np.where(extra, np.minimum(out[:, :, 1], out[:, :, 0]), out[:, :, 1])
    out[screen] = key

    # Warm-edge a* on character ring only
    lab = rgb2lab(np.clip(out / 255.0, 0, 1))
    fix = edge & (lab[:, :, 1] < -2)
    lab2 = lab.copy()
    lab2[:, :, 1] = np.where(fix, np.maximum(lab[:, :, 1], 8.0), lab[:, :, 1])
    lab2[:, :, 2] = np.where(fix, lab[:, :, 2] + 5, lab[:, :, 2])
    trimmed = np.clip(lab2rgb(lab2) * 255.0, 0, 255).astype(np.float32)
    trimmed[screen] = key

    # Fringe choke: peel greenish screen-touching silhouette into key (all around).
    # Same idea as idle outline choke — removes the green trim Kim still sees on plate.
    peels = max(0, int(fringe_choke_px))
    for _ in range(peels):
        dist2 = np.linalg.norm(trimmed - key.reshape(1, 1, 3), axis=2)
        fg2 = dist2 >= float(screen_dist)
        bg2 = ~fg2
        face = fg2 & binary_dilation(bg2, iterations=1)
        r = trimmed[:, :, 0]
        g = trimmed[:, :, 1]
        b = trimmed[:, :, 2]
        greenish = (g > r + 8) | ((g > b + 5) & (g > r))
        near = dist2 < 130
        trimmed[face & (greenish | near)] = key

    trimmed[np.linalg.norm(trimmed - key.reshape(1, 1, 3), axis=2) < float(screen_dist)] = key
    return trimmed.astype(np.uint8), key_t


def canonicalize_still_to_plate(
    still_path: Path,
    plate_path: Path,
) -> np.ndarray:
    """Lanczos to plate WxH when sizes differ (16:9 only — no stretch crop)."""
    from PIL import Image

    still = Image.open(still_path).convert("RGB")
    plate = Image.open(plate_path).convert("RGB")
    if still.size == plate.size:
        return np.asarray(still)
    sw, sh = still.size
    pw, ph = plate.size
    if abs(sw / sh - pw / ph) > 0.02:
        raise ValueError(
            f"aspect mismatch still {still.size} vs plate {plate.size} — "
            "re-export 16:9; do not stretch"
        )
    return np.asarray(still.resize(plate.size, Image.Resampling.LANCZOS))


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


def _residual_neon_edge_mask(rgb: np.ndarray) -> np.ndarray:
    """Neon green crumbs on a composite (not olive vest, not scene greens)."""
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    return (g > r + 18) & (g > b + 8) & (g > 55) & (r < 90)


def _is_bandana_blue(rgb: np.ndarray) -> np.ndarray:
    """Protect costume blue (teal bandana) from green-fringe scrubs."""
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    return (b > r + 25) & (b > g + 12) & (b > 95)


def trim_green_character_frame(
    rgb: np.ndarray,
    *,
    apply_idle_choke: bool = True,
) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Gate0 still recipe on one RGB frame (still or idle video).

    spillkill_warm_edge_vj → optional Kling outline choke. Same path for
    Kim idle video as for PNG stills — do not substitute ffmpeg chromakey.
    """
    trimmed, key = spillkill_warm_edge_vj(rgb)
    if apply_idle_choke:
        trimmed = choke_kling_idle_outline(trimmed, key_rgb=key)
    return trimmed, key


def composite_trimmed_rgb_on_plate(
    still_u8: np.ndarray,
    plate_u8: np.ndarray,
    *,
    matte_erode_px: int = COMPOSITE_MATTE_ERODE_PX,
    inner_scrub_px: int = COMPOSITE_INNER_SCRUB_PX,
) -> np.ndarray:
    """Gate 0 plate composite — hard choked matte + inward green-fringe scrub.

    Soft 0.35 green rings are forbidden — they reintroduce the silhouette trim.
    Works on stills and idle video frames (same recipe).
    """
    from scipy.ndimage import binary_dilation, binary_erosion
    from skimage.color import lab2rgb, rgb2lab

    if still_u8.shape != plate_u8.shape:
        raise ValueError(f"size mismatch still {still_u8.shape} plate {plate_u8.shape}")
    still = still_u8.astype(np.float32)
    plate = plate_u8.astype(np.float32)
    key = np.array(measure_key_rgb(still_u8), dtype=np.float32)
    dist = np.linalg.norm(still - key.reshape(1, 1, 3), axis=2)

    # Hard matte only — choke inward so leftover fringe pixels never land on plate.
    char = dist >= 60.0
    erode_n = max(1, int(matte_erode_px))
    hard = binary_erosion(char, iterations=erode_n)
    a = hard.astype(np.float32)

    out = a[..., None] * still + (1.0 - a[..., None]) * plate
    lab = rgb2lab(np.clip(out / 255.0, 0, 1))
    edge = binary_dilation(hard, iterations=3) & ~binary_erosion(hard, iterations=1)
    fix = edge & (lab[:, :, 1] < -2)
    lab2 = lab.copy()
    lab2[:, :, 1] = np.where(fix, np.maximum(lab[:, :, 1], 8.0), lab[:, :, 1])
    lab2[:, :, 2] = np.where(fix, lab[:, :, 2] + 5, lab[:, :, 2])
    comp = np.clip(lab2rgb(lab2) * 255.0, 0, 255).astype(np.float32)

    # Inward scrub: green/teal fringe sitting just inside the matte → plate.
    # (1px edge scrub alone left a visible green trim; Kim 2026-08-05.)
    scrub_n = max(1, int(inner_scrub_px))
    inner = hard & binary_dilation(~hard, iterations=scrub_n)
    lab_c = rgb2lab(np.clip(comp / 255.0, 0, 1))
    r = comp[:, :, 0]
    g = comp[:, :, 1]
    b = comp[:, :, 2]
    neon = _residual_neon_edge_mask(comp)
    greenish = (lab_c[:, :, 1] < -1) | ((g > r + 12) & (g > b - 5) & (r < 110))
    bandana = _is_bandana_blue(comp)
    scrub = (inner | edge) & (neon | greenish) & ~bandana
    near_char = binary_dilation(hard, iterations=scrub_n + 2)
    scrub = scrub & near_char
    comp[scrub] = plate[scrub]
    return comp.astype(np.uint8)


def composite_trimmed_still_on_plate(
    still_path: Path | None = None,
    plate_path: Path | None = None,
    *,
    production_root: Path | None = None,
    matte_erode_px: int = COMPOSITE_MATTE_ERODE_PX,
    inner_scrub_px: int = COMPOSITE_INNER_SCRUB_PX,
) -> np.ndarray:
    """Gate 0 plate composite from files — delegates to array recipe."""
    from PIL import Image

    if production_root is not None:
        still_path = still_path or resolve_trimmed_still(production_root)
        plate_path = plate_path or resolve_plate(production_root)
    if still_path is None or plate_path is None:
        raise ValueError("still_path and plate_path required")

    still_u8 = np.asarray(Image.open(still_path).convert("RGB"))
    plate_u8 = np.asarray(Image.open(plate_path).convert("RGB"))
    return composite_trimmed_rgb_on_plate(
        still_u8,
        plate_u8,
        matte_erode_px=matte_erode_px,
        inner_scrub_px=inner_scrub_px,
    )

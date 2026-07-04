#!/usr/bin/env python3
"""Phase A/B module lipsync → kid-facing delivery encode (category parity with beat lipsync).

Kling Sync returns sub-720 full-scene MP4 (~720×544). Beat-level lipsync runs
``voice_first_upscale`` after download (arlo_o3_voice_pipeline). Phase B module
lipsync previously saved raw Kling bytes — this module is the single choke point
for delivery encode on terminal module lipsync writes.

V2 reframe (2026-06-30): strip Avatar Pro side letterbox (4:3 still padded to
16:9 at submit) + crop bottom band where gibberish subtitle bars appear, then
scale-to-fill 1280×720 — no new Kling purchase required for existing clips.

V3 reframe (2026-06-30): wide 16:9 Avatar Pro still contract — top-anchored
bottom sacrifice (subtitle hallucinations; adaptive band detect when present),
nose pinned ~30% from top in final 1280×720, direct scale (no scale-to-fill zoom).
Phase A + Phase B.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE = "voice_first_upscale"
PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1 = "PHASE_MODULE_LIPSYNC_DELIVERY_V1"
PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2 = "PHASE_MODULE_LIPSYNC_DELIVERY_V2"
PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3 = "PHASE_MODULE_LIPSYNC_DELIVERY_V3"
PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT = PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3
PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH = 1280
PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT = 720
# Bottom sacrifice zone — minimum trim; adaptive probe may raise up to MAX.
PHASE_MODULE_LIPSYNC_SACRIFICE_ZONE_RATIO = 0.12
PHASE_MODULE_LIPSYNC_SACRIFICE_ZONE_MIN_RATIO = PHASE_MODULE_LIPSYNC_SACRIFICE_ZONE_RATIO
# Adaptive subtitle crop may exceed 22% on long stems (Event 3 Phase B ~25% at ~180s).
PHASE_MODULE_LIPSYNC_SACRIFICE_ZONE_MAX_RATIO = 0.30
PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_PAD_PX = 24
# Extra rows above band_top — lanczos/unsharp can bleed subtitle ascenders into frame edge.
PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_EXTRA_SAFETY_PX = 16
PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_MIN_RUN = 3
PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_SCAN_START_RATIO = 0.55
# Target nose position in delivered 1280×720 (after sacrifice trim + 16:9 crop).
PHASE_MODULE_LIPSYNC_TARGET_NOSE_Y_RATIO = 0.30
# Negative = shift crop window left (more fireplace); character reads right of center.
PHASE_MODULE_LIPSYNC_HORIZONTAL_BIAS = -0.10
# Fallback when nose probe fails (wide 16:9 still contract).
PHASE_MODULE_LIPSYNC_FALLBACK_NOSE_Y_RATIO = 0.36
# Legacy V2 constants (letterbox path only).
PHASE_MODULE_LIPSYNC_SUBTITLE_CROP_RATIO = 0.09
PHASE_MODULE_LIPSYNC_ASPECT_FILL_Y_BIAS = -0.22
_CROPDETECT_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def _probe_video_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    return int(stream.get("width") or 0), int(stream.get("height") or 0)


def _probe_bitrate(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    try:
        return int(json.loads(result.stdout).get("format", {}).get("bit_rate") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0


def probe_avatar_pro_content_crop(
    path: Path,
    *,
    ss: float = 3.0,
    sample_frames: int = 30,
) -> tuple[int, int, int, int]:
    """Return ``(w, h, x, y)`` active content crop from cropdetect on a mid-clip sample."""
    path = Path(path).resolve()
    frame_w, frame_h = _probe_video_size(path)
    if frame_w <= 0 or frame_h <= 0:
        raise RuntimeError(f"cannot probe video size: {path}")

    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-y",
            "-ss", f"{ss:.3f}",
            "-i", str(path),
            "-vf", "cropdetect=24:16:0",
            "-frames:v", str(sample_frames),
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    crops: list[tuple[int, int, int, int]] = []
    for line in (proc.stderr or "").splitlines():
        match = _CROPDETECT_RE.search(line)
        if match:
            crops.append(tuple(int(g) for g in match.groups()))  # type: ignore[misc]

    if not crops:
        return frame_w, frame_h, 0, 0

    w, h, x, y = crops[-1]
    # No meaningful side letterbox — use full frame width (native 16:9 still path).
    if w >= int(frame_w * 0.95):
        w, x = frame_w, 0
    if h >= int(frame_h * 0.95):
        h, y = frame_h, 0
    return w, h, x, y


def apply_aspect_fill_vertical_bias(
    frame_h: int,
    crop_h: int,
    crop_y: int,
    *,
    bias: float = PHASE_MODULE_LIPSYNC_ASPECT_FILL_Y_BIAS,
) -> int:
    """Nudge crop origin vertically; negative bias moves window up."""
    if crop_h >= frame_h or abs(bias) < 1e-6:
        return crop_y
    excess = frame_h - crop_h
    return max(0, min(frame_h - crop_h, crop_y + int(round(excess * bias))))


def apply_horizontal_crop_bias(
    frame_w: int,
    crop_w: int,
    *,
    bias: float = PHASE_MODULE_LIPSYNC_HORIZONTAL_BIAS,
) -> int:
    """Return crop_x; negative bias includes more left (character reads right of center)."""
    excess = max(0, frame_w - crop_w)
    if excess <= 0:
        return 0
    if abs(bias) < 1e-6:
        return excess // 2
    return max(0, min(excess, int(round(excess * (0.5 + bias)))))


def center_crop_to_169_box(width: int, height: int) -> tuple[int, int, int, int]:
    """Return ``(w, h, x, y)`` crop window for 16:9 aspect without stretch."""
    target_ar = 16 / 9
    if width <= 0 or height <= 0:
        return width, height, 0, 0
    current_ar = width / height
    if abs(current_ar - target_ar) < 0.02:
        return width, height, 0, 0
    if current_ar > target_ar:
        new_w = max(1, int(round(height * target_ar)))
        x = max(0, (width - new_w) // 2)
        return new_w, height, x, 0
    new_h = max(1, int(round(width / target_ar)))
    y = apply_aspect_fill_vertical_bias(height, new_h, max(0, (height - new_h) // 2))
    return width, new_h, 0, y


def _extract_probe_jpeg(path: Path, *, ss: float = 3.0) -> Path:
    """Write a single mid-clip JPEG frame for nose probing."""
    tmp = Path(tempfile.mkstemp(suffix=".png", prefix="lipsync_probe_")[1])
    for t in (ss, 0.5, 0.1, 0.0):
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{t:.3f}",
                "-i", str(path),
                "-frames:v", "1",
                "-update", "1",
                str(tmp),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 128:
            return tmp
    raise RuntimeError(f"probe frame extract failed: {path}")


def probe_avatar_pro_nose_y_px(
    path: Path,
    *,
    ss: float = 3.0,
    max_y: int | None = None,
) -> int | None:
    """Estimate nose row (px from top) on a mid-clip frame; None if probe fails."""
    from PIL import Image  # type: ignore

    probe_path = _extract_probe_jpeg(path, ss=ss)
    try:
        im = Image.open(probe_path).convert("RGB")
        w, h = im.size
        limit = min(h, max_y) if max_y is not None else h
        hair_top: int | None = None
        for y in range(0, max(1, int(limit * 0.5))):
            row = [im.getpixel((x, y)) for x in range(int(w * 0.35), int(w * 0.65))]
            bright = sum(1 for r, g, b in row if r > 185 and g > 175 and b > 160)
            if bright >= max(3, int(len(row) * 0.12)):
                hair_top = y
                break
        start = (hair_top or 0) + max(4, int(h * 0.04))
        for y in range(start, max(start + 1, int(limit * 0.58))):
            row = [im.getpixel((x, y)) for x in range(int(w * 0.46), int(w * 0.54))]
            skin = sum(
                1 for r, g, b in row
                if 105 < r < 215 and 65 < g < 175 and 45 < b < 145 and r > g > b * 0.75
            )
            if skin >= max(2, int(len(row) * 0.45)):
                return y
        return None
    finally:
        try:
            probe_path.unlink()
        except OSError:
            pass


def probe_avatar_pro_subtitle_band_top_y(
    path: Path | None = None,
    *,
    ss: float = 3.0,
    im: "Image.Image | None" = None,
) -> int | None:
    """Return top row (px from top) of burned-in subtitle/gibberish band, or None."""
    from PIL import Image  # type: ignore

    owned_probe: Path | None = None
    try:
        if im is None:
            if path is None:
                return None
            owned_probe = _extract_probe_jpeg(path, ss=ss)
            im = Image.open(owned_probe).convert("RGB")
        else:
            im = im.convert("RGB")
        w, h = im.size
        if h <= 0 or w <= 0:
            return None
        scan_from = int(h * PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_SCAN_START_RATIO)
        min_run = PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_MIN_RUN
        hits: list[int] = []
        for y in range(h - 1, scan_from, -1):
            row = [im.getpixel((x, y)) for x in range(0, w, max(1, w // 640))]
            bright = sum(1 for r, g, b in row if r + g + b > 500)
            step = max(1, w // 640)
            hc = 0
            for x in range(0, w - step, step):
                p1 = im.getpixel((x, y))
                p2 = im.getpixel((x + step, y))
                if sum(abs(a - b) for a, b in zip(p1, p2)) > 110:
                    hc += 1
            score = (bright / max(1, len(row))) + (hc / max(1, len(row)))
            if score > 0.22:
                hits.append(y)
        if len(hits) < min_run:
            return None
        return min(hits)
    finally:
        if owned_probe is not None:
            try:
                owned_probe.unlink()
            except OSError:
                pass


def _probe_duration_s(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    try:
        return max(0.0, float(result.stdout.strip() or "0"))
    except ValueError:
        return 0.0


def probe_avatar_pro_bright_subtitle_top_y(
    path: Path | None = None,
    *,
    ss: float = 3.0,
    im: "Image.Image | None" = None,
) -> int | None:
    """Return top row (px) of high-luminance bottom subtitle/gibberish, if any."""
    from PIL import Image  # type: ignore

    owned_probe: Path | None = None
    try:
        if im is None:
            if path is None:
                return None
            owned_probe = _extract_probe_jpeg(path, ss=ss)
            im = Image.open(owned_probe).convert("RGB")
        else:
            im = im.convert("RGB")
        w, h = im.size
        if h <= 0 or w <= 0:
            return None
        scan_from = int(h * 0.45)
        for y in range(scan_from, h):
            row = [im.getpixel((x, y)) for x in range(0, w, max(1, w // 640))]
            bright = sum(1 for r, g, b in row if r + g + b > 500)
            if bright / max(1, len(row)) > 0.15:
                return y
        return None
    finally:
        if owned_probe is not None:
            try:
                owned_probe.unlink()
            except OSError:
                pass


def resolve_module_lipsync_sacrifice_ratio(
    path: Path,
    frame_h: int,
    *,
    ss: float = 3.0,
) -> tuple[float, str, int | None]:
    """Return ``(sacrifice_ratio, source, band_top_y)`` for V3 bottom trim.

    Scans multiple timestamps — Avatar Pro gibberish often appears late in long stems.
    """
    min_r = PHASE_MODULE_LIPSYNC_SACRIFICE_ZONE_MIN_RATIO
    max_r = PHASE_MODULE_LIPSYNC_SACRIFICE_ZONE_MAX_RATIO
    duration_s = _probe_duration_s(path)
    scan_points: set[float] = {ss}
    for frac in (0.25, 0.50, 0.70, 0.85, 0.92):
        scan_points.add(max(1.0, duration_s * frac))
    scan_points.add(max(1.0, duration_s - 1.0))
    tail_start = max(1.0, duration_s * 0.70)
    step = 3.0
    offset = tail_start
    while offset < duration_s:
        scan_points.add(offset)
        offset += step
    band_top: int | None = None
    for point in sorted(scan_points):
        for probe in (
            probe_avatar_pro_subtitle_band_top_y,
            probe_avatar_pro_bright_subtitle_top_y,
        ):
            hit = probe(path, ss=point)
            if hit is not None and (band_top is None or hit < band_top):
                band_top = hit
    if band_top is None:
        return min_r, "fixed_min", None
    pad = PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_PAD_PX
    extra = PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_EXTRA_SAFETY_PX
    active_h = max(1, band_top - pad - extra)
    ratio = (frame_h - active_h) / max(1, frame_h)
    # Do not floor to min_r when adaptive band found — min floor kept gibberish visible.
    ratio = min(max_r, max(0.0, ratio))
    return ratio, "adaptive_band", band_top


def plan_module_lipsync_reframe_v3(path: Path, *, ss: float = 3.0) -> dict:
    """Wide-still contract: adaptive bottom trim, pin nose ~30%, direct scale."""
    frame_w, frame_h = _probe_video_size(path)
    sacrifice, sacrifice_source, band_top_y = resolve_module_lipsync_sacrifice_ratio(
        path, frame_h, ss=ss,
    )
    if sacrifice_source == "adaptive_band" and band_top_y is not None:
        # Never derive active_h from capped sacrifice ratio — 22% max was leaving
        # subtitle ascenders visible when band_top-pad needed ~25% (Event 3 Phase B).
        pad = PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_PAD_PX
        extra = PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_EXTRA_SAFETY_PX
        active_h = max(1, int(band_top_y) - pad - extra)
        sacrifice = (frame_h - active_h) / max(1, frame_h)
    else:
        active_h = max(1, int(round(frame_h * (1.0 - sacrifice))))
    nose_y = probe_avatar_pro_nose_y_px(path, ss=ss, max_y=active_h)
    if nose_y is None:
        nose_y = int(round(active_h * PHASE_MODULE_LIPSYNC_FALLBACK_NOSE_Y_RATIO))
        nose_source = "fallback_ratio"
    else:
        nose_source = "probe"

    crop_w = frame_w
    ideal_h = max(1, int(round(crop_w * 9 / 16)))
    crop_h = min(active_h, ideal_h)
    crop_w = max(1, int(round(crop_h * 16 / 9)))
    crop_x = apply_horizontal_crop_bias(frame_w, crop_w)
    target = PHASE_MODULE_LIPSYNC_TARGET_NOSE_Y_RATIO
    crop_y = int(round(nose_y - target * crop_h))
    crop_y = max(0, min(active_h - crop_h, crop_y))
    # If nose sits too low, shrink crop_h slightly so we can pin without losing 16:9.
    for _ in range(64):
        if crop_y > 0 or crop_y + crop_h <= active_h:
            break
        if crop_h <= max(1, int(active_h * 0.78)):
            break
        crop_h = max(1, crop_h - 4)
        crop_w = max(1, int(round(crop_h * 16 / 9)))
        crop_x = apply_horizontal_crop_bias(frame_w, crop_w)
        crop_y = int(round(nose_y - target * crop_h))
        crop_y = max(0, min(active_h - crop_h, crop_y))

    return {
        "mode": "canonical_v3",
        "frame_w": frame_w,
        "frame_h": frame_h,
        "active_h": active_h,
        "sacrifice_zone_ratio": sacrifice,
        "sacrifice_source": sacrifice_source,
        "subtitle_band_top_y": band_top_y,
        "nose_y_px": nose_y,
        "nose_source": nose_source,
        "target_nose_y_ratio": target,
        "horizontal_bias": PHASE_MODULE_LIPSYNC_HORIZONTAL_BIAS,
        "crop_w": crop_w,
        "crop_h": crop_h,
        "crop_x": crop_x,
        "crop_y": crop_y,
        "bottom_crop_ratio": sacrifice,
    }


def resolve_module_lipsync_delivery_recipe(lipsync_method: str | None = None) -> str:
    """Avatar/Beat Gen → V3 adaptive; legacy Kling/ByteDance module → V2 letterbox."""
    if str(lipsync_method or "").strip() == "kling_avatar_pro_v1":
        return PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3
    return PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2


def plan_module_lipsync_reframe_v2(path: Path) -> dict:
    """Legacy Kling Sync / ByteDance module output — side letterbox strip + subtitle band."""
    frame_w, frame_h = _probe_video_size(path)
    cw, ch, cx, cy = probe_avatar_pro_content_crop(path)
    has_letterbox = cw < int(frame_w * 0.92) and cx >= int(frame_w * 0.08)
    if has_letterbox:
        return {
            "mode": "letterbox",
            "frame_w": frame_w,
            "frame_h": frame_h,
            "crop_w": cw,
            "crop_h": ch,
            "crop_x": cx,
            "crop_y": cy,
            "bottom_crop_ratio": PHASE_MODULE_LIPSYNC_SUBTITLE_CROP_RATIO,
        }
    if (frame_w, frame_h) == (
        PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH,
        PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT,
    ):
        return {
            "mode": "none",
            "frame_w": frame_w,
            "frame_h": frame_h,
            "crop_w": frame_w,
            "crop_h": frame_h,
            "crop_x": 0,
            "crop_y": 0,
            "bottom_crop_ratio": 0.0,
        }
    cw2, ch2, cx2, cy2 = center_crop_to_169_box(frame_w, frame_h)
    return {
        "mode": "letterbox",
        "frame_w": frame_w,
        "frame_h": frame_h,
        "crop_w": cw2,
        "crop_h": ch2,
        "crop_x": cx2,
        "crop_y": cy2,
        "bottom_crop_ratio": PHASE_MODULE_LIPSYNC_SUBTITLE_CROP_RATIO,
    }


def plan_module_lipsync_reframe(
    path: Path,
    *,
    delivery_recipe: str | None = None,
) -> dict:
    """Route V2 letterbox (legacy module) vs V3 adaptive (Avatar Pro / Beat Gen)."""
    recipe = delivery_recipe or PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3
    if recipe == PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3:
        return plan_module_lipsync_reframe_v3(path)
    return plan_module_lipsync_reframe_v2(path)


def resolve_module_lipsync_reencode_source(event_dir: Path, pinned_name: str) -> Path:
    """Prefer ``*_raw.mp4`` or non-``_reframed`` sibling for delivery reencode."""
    event_dir = event_dir.resolve()
    pinned = (pinned_name or "").strip()
    if not pinned:
        raise FileNotFoundError("pinned lipsync name empty")
    candidates: list[Path] = []
    stem = pinned.replace("_reframed", "")
    if stem.endswith(".mp4"):
        candidates.extend([
            event_dir / stem.replace(".mp4", "_raw.mp4"),
            event_dir / stem,
        ])
    candidates.append(event_dir / pinned)
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no reencode source for pinned lipsync: {pinned_name}")


def build_phase_lipsync_reframe_vf_v3(
    crop_w: int,
    crop_h: int,
    crop_x: int,
    crop_y: int,
) -> str:
    """Sacrifice-trimmed 16:9 crop + direct scale to 1280×720 (no zoom-in)."""
    from video_delivery import DELIVERY_FPS, VOICE_FIRST_UPSCALE_UNSHARP  # noqa: PLC0415

    return (
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH}:{PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT}:"
        "flags=lanczos+accurate_rnd+full_chroma_int,"
        "setsar=1:1,"
        f"fps={DELIVERY_FPS},"
        f"{VOICE_FIRST_UPSCALE_UNSHARP}"
    )


def build_phase_lipsync_reframe_vf(
    crop_w: int,
    crop_h: int,
    crop_x: int,
    crop_y: int,
    *,
    bottom_crop_ratio: float = PHASE_MODULE_LIPSYNC_SUBTITLE_CROP_RATIO,
) -> str:
    """Letterbox strip + subtitle-band crop + scale-to-fill 1280×720."""
    from video_delivery import DELIVERY_FPS, VOICE_FIRST_UPSCALE_UNSHARP  # noqa: PLC0415

    h_trim = max(1, int(crop_h * (1.0 - bottom_crop_ratio)))
    return (
        f"crop={crop_w}:{h_trim}:{crop_x}:{crop_y},"
        f"scale={PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH}:{PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT}:"
        "flags=lanczos+accurate_rnd+full_chroma_int:force_original_aspect_ratio=increase,"
        f"crop={PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH}:{PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT},"
        "setsar=1:1,"
        f"fps={DELIVERY_FPS},"
        f"{VOICE_FIRST_UPSCALE_UNSHARP}"
    )


def finalize_phase_module_lipsync_delivery(
    path: Path,
    *,
    sharpen: bool = True,
    timeout_s: int = 900,
    reframe: bool = True,
    dest_path: Path | None = None,
    delivery_recipe: str | None = None,
    lipsync_method: str | None = None,
) -> dict:
    """Delivery encode on module lipsync MP4; returns delivery metadata.

    When ``dest_path`` is set, copies ``path`` (raw WaveSpeed download) to
    ``dest_path`` and encodes there — raw bytes stay on disk for reencode.
    """
    import shutil

    from video_delivery import (  # noqa: PLC0415
        DELIVERY_BUFSIZE,
        DELIVERY_MAXRATE,
        DELIVERY_VIDEO_BITRATE,
        VOICE_FIRST_DELIVERY_BUFSIZE,
        VOICE_FIRST_DELIVERY_MAXRATE,
        VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS,
        VOICE_FIRST_DELIVERY_VIDEO_BITRATE,
        _has_audio,
        _run_single_delivery_encode,
    )

    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"lipsync file not found: {path}")

    work = path
    if dest_path is not None:
        dest_path = Path(dest_path).resolve()
        if dest_path != path:
            shutil.copy2(path, dest_path)
            work = dest_path

    raw_w, raw_h = _probe_video_size(work)
    tmp = work.with_name(f"{work.stem}.delivery_tmp{work.suffix}")

    recipe = delivery_recipe or resolve_module_lipsync_delivery_recipe(lipsync_method)
    crop_meta: dict[str, int | float | str] = {}
    try:
        if reframe:
            plan = plan_module_lipsync_reframe(work, delivery_recipe=recipe)
            if plan["mode"] == "none":
                from video_delivery import encode_delivery_video  # noqa: PLC0415

                encode_delivery_video(
                    work,
                    tmp,
                    include_audio=True,
                    sharpen=sharpen,
                    delivery_profile=PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
                    timeout_s=timeout_s,
                )
            elif plan["mode"] == "canonical_v3":
                cw, ch, cx, cy = (
                    int(plan["crop_w"]), int(plan["crop_h"]),
                    int(plan["crop_x"]), int(plan["crop_y"]),
                )
                vf = build_phase_lipsync_reframe_vf_v3(cw, ch, cx, cy)
                crop_meta = {
                    "reframe_mode": str(plan["mode"]),
                    "content_crop_w": cw,
                    "content_crop_h": ch,
                    "content_crop_x": cx,
                    "content_crop_y": cy,
                    "sacrifice_zone_ratio": float(plan["sacrifice_zone_ratio"]),
                    "sacrifice_source": str(plan.get("sacrifice_source", "fixed_min")),
                    "subtitle_band_top_y": plan.get("subtitle_band_top_y"),
                    "target_nose_y_ratio": float(plan["target_nose_y_ratio"]),
                    "horizontal_bias": float(plan.get("horizontal_bias", 0.0)),
                    "nose_y_px": int(plan["nose_y_px"]),
                    "nose_source": str(plan["nose_source"]),
                    "active_h": int(plan["active_h"]),
                    "subtitle_crop_ratio": float(plan["bottom_crop_ratio"]),
                }
                last_exc: Exception | None = None
                for v_bitrate, maxrate, bufsize in (
                    (VOICE_FIRST_DELIVERY_VIDEO_BITRATE, VOICE_FIRST_DELIVERY_MAXRATE, VOICE_FIRST_DELIVERY_BUFSIZE),
                    (DELIVERY_VIDEO_BITRATE, DELIVERY_MAXRATE, DELIVERY_BUFSIZE),
                ):
                    try:
                        _run_single_delivery_encode(
                            work,
                            tmp,
                            vf=vf,
                            video_bitrate=v_bitrate,
                            maxrate=maxrate,
                            bufsize=bufsize,
                            max_bitrate_bps=VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS,
                            include_audio=_has_audio(work),
                            use_lean_quality_encode=True,
                            timeout_s=timeout_s,
                        )
                        last_exc = None
                        break
                    except RuntimeError as exc:
                        last_exc = exc
                        if "bitrate" not in str(exc):
                            raise
                if last_exc is not None:
                    raise last_exc
            else:
                cw, ch, cx, cy = (
                    int(plan["crop_w"]), int(plan["crop_h"]),
                    int(plan["crop_x"]), int(plan["crop_y"]),
                )
                bottom = float(plan["bottom_crop_ratio"])
                vf = build_phase_lipsync_reframe_vf(
                    cw, ch, cx, cy, bottom_crop_ratio=bottom,
                )
                crop_meta = {
                    "reframe_mode": str(plan["mode"]),
                    "content_crop_w": cw,
                    "content_crop_h": ch,
                    "content_crop_x": cx,
                    "content_crop_y": cy,
                    "subtitle_crop_ratio": bottom,
                }
                last_exc = None
                for v_bitrate, maxrate, bufsize in (
                    (VOICE_FIRST_DELIVERY_VIDEO_BITRATE, VOICE_FIRST_DELIVERY_MAXRATE, VOICE_FIRST_DELIVERY_BUFSIZE),
                    (DELIVERY_VIDEO_BITRATE, DELIVERY_MAXRATE, DELIVERY_BUFSIZE),
                ):
                    try:
                        _run_single_delivery_encode(
                            work,
                            tmp,
                            vf=vf,
                            video_bitrate=v_bitrate,
                            maxrate=maxrate,
                            bufsize=bufsize,
                            max_bitrate_bps=VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS,
                            include_audio=_has_audio(work),
                            use_lean_quality_encode=True,
                            timeout_s=timeout_s,
                        )
                        last_exc = None
                        break
                    except RuntimeError as exc:
                        last_exc = exc
                        if "bitrate" not in str(exc):
                            raise
                if last_exc is not None:
                    raise last_exc
        else:
            from video_delivery import encode_delivery_video  # noqa: PLC0415

            encode_delivery_video(
                work,
                tmp,
                include_audio=True,
                sharpen=sharpen,
                delivery_profile=PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
                timeout_s=timeout_s,
            )
        os.replace(tmp, work)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    out_w, out_h = _probe_video_size(work)
    if (out_w, out_h) != (PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH, PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT):
        raise RuntimeError(
            f"delivery encode shape {out_w}x{out_h} != "
            f"{PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH}x{PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT}"
        )
    bitrate = _probe_bitrate(work)
    if bitrate <= 0 or bitrate > VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS:
        raise RuntimeError(
            f"delivery bitrate {bitrate:,} bps outside (0, {VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS:,}]"
        )

    return {
        "path": str(work),
        "delivery_profile": PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
        "delivery_recipe": recipe,
        "raw_width": raw_w,
        "raw_height": raw_h,
        "width": out_w,
        "height": out_h,
        "bitrate_bps": bitrate,
        "file_size_bytes": path.stat().st_size,
        "sharpen": sharpen,
        "reframe": reframe,
        **crop_meta,
    }

"""Rhubarb lip-sync phoneme timing + beak sprite compositing.

Cartoon-native path: Preston Blair A–F mouth shapes swapped on a static plate
or video clip. No WaveSpeed / AI lipsync at composite time.

See Production/docs/PHASE_A_CHIPPER_RHUBARB_v1.md
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


def default_rhubarb_bin() -> str:
    """Prefer bundled tooling bin, then PATH."""
    bundled = Path(__file__).resolve().parent / "bin" / "rhubarb"
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("rhubarb")
    if found:
        return found
    return "rhubarb"


def _rhubarb_audio_input(audio_path: Path) -> tuple[Path, Path | None]:
    """Rhubarb accepts .wav/.ogg only — convert mp3/m4a via ffmpeg temp wav."""
    suffix = audio_path.suffix.lower()
    if suffix in {".wav", ".ogg"}:
        return audio_path, None
    tmp_wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(audio_path),
            "-ar", "44100", "-ac", "1",
            str(tmp_wav),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return tmp_wav, tmp_wav


def run_rhubarb(
    audio_path: Path,
    *,
    rhubarb_bin: str | None = None,
    dialog_text: str | None = None,
) -> list[dict[str, Any]]:
    """Run Rhubarb CLI; return mouthCues as [{start, end, value}, ...]."""
    exe = rhubarb_bin or default_rhubarb_bin()
    if not Path(exe).is_file() and shutil.which(exe) is None:
        raise FileNotFoundError(
            f"rhubarb binary not found: {exe!r}. "
            "Install from https://github.com/DanielSWolf/rhubarb-lip-sync/releases "
            "or build for arm64 into Production/tools/bin/rhubarb"
        )

    rhubarb_input, tmp_wav = _rhubarb_audio_input(audio_path)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_json = Path(tmp.name)

    cmd = [exe, "-f", "json", "-o", str(out_json), str(rhubarb_input)]
    if dialog_text:
        cmd.extend(["--dialogFile", "-"])
        proc = subprocess.run(
            cmd,
            input=dialog_text.encode("utf-8"),
            capture_output=True,
            check=False,
            text=False,
        )
    else:
        proc = subprocess.run(cmd, capture_output=True, check=False)

    try:
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
            raise subprocess.CalledProcessError(proc.returncode, cmd, stderr)
        data = json.loads(out_json.read_text(encoding="utf-8"))
        cues = data.get("mouthCues") or []
        if not isinstance(cues, list):
            raise ValueError(f"unexpected rhubarb json shape in {out_json}")
        return cues
    finally:
        out_json.unlink(missing_ok=True)
        if tmp_wav is not None:
            tmp_wav.unlink(missing_ok=True)


def lookup_phoneme(mouth_cues: list[dict[str, Any]], t: float) -> str:
    """Return Preston Blair phoneme at time t (seconds), or X for silence."""
    for cue in mouth_cues:
        start = float(cue["start"])
        end = float(cue["end"])
        if start <= t < end:
            val = str(cue.get("value", "X")).upper()
            return val if val in {"A", "B", "C", "D", "E", "F", "G", "H", "X"} else "X"
    return "X"


def resolve_phoneme_sprite(
    phoneme: str,
    sprites: dict[str, Path],
) -> Path | None:
    """Map Rhubarb phoneme to sprite file; G/H fall back to C/D; X→A."""
    key = phoneme.upper()
    if key in ("G", "H"):
        key = "C" if key == "G" else "D"
    if key == "X":
        key = "A"
    path = sprites.get(key)
    if path and path.is_file():
        return path
    fallback = sprites.get("A")
    return fallback if fallback and fallback.is_file() else None


def _load_sprite_rgba(path: Path, size: tuple[int, int]) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    if img.size != size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    return np.array(img)


def _overlay_rgba_bgr(frame_bgr: np.ndarray, sprite_rgba: np.ndarray, x0: int, y0: int) -> None:
    h, w = sprite_rgba.shape[:2]
    y1 = min(frame_bgr.shape[0], y0 + h)
    x1 = min(frame_bgr.shape[1], x0 + w)
    if y1 <= y0 or x1 <= x0:
        return
    rh, rw = y1 - y0, x1 - x0
    sprite = sprite_rgba[:rh, :rw]
    alpha = sprite[:, :, 3:4].astype(np.float32) / 255.0
    sprite_bgr = sprite[:, :, :3][:, :, ::-1]
    region = frame_bgr[y0:y1, x0:x1].astype(np.float32)
    blended = alpha * sprite_bgr.astype(np.float32) + (1.0 - alpha) * region
    frame_bgr[y0:y1, x0:x1] = blended.clip(0, 255).astype(np.uint8)


def _beak_overlay_rect(
    width: int,
    height: int,
    beak_config: dict[str, Any],
) -> tuple[int, int, int, int]:
    cx = int(float(beak_config["beak_cx_frac"]) * width)
    cy = int(float(beak_config["beak_cy_frac"]) * height)
    sprite_w = int(float(beak_config["sprite_w_frac"]) * width)
    sprite_h = int(float(beak_config["sprite_h_frac"]) * height)
    x0 = max(0, cx - sprite_w // 2)
    y0 = max(0, cy - sprite_h // 2)
    x1 = min(width, x0 + sprite_w)
    y1 = min(height, y0 + sprite_h)
    return x0, y0, x1, y1


def _audio_duration_s(audio_path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip() or "0")


def composite_static_plate_rhubarb(
    *,
    plate_path: Path,
    audio_path: Path,
    beak_config: dict[str, Any],
    sprites: dict[str, Path],
    output_path: Path,
    fps: float = 25.0,
    rhubarb_bin: str | None = None,
    dialog_text: str | None = None,
) -> dict[str, Any]:
    """Composite beak sprites onto a frozen PNG plate for audio duration."""
    mouth_cues = run_rhubarb(
        audio_path,
        rhubarb_bin=rhubarb_bin,
        dialog_text=dialog_text,
    )
    audio_duration = _audio_duration_s(audio_path)
    if mouth_cues:
        audio_duration = max(audio_duration, float(mouth_cues[-1]["end"]))

    plate_rgba = Image.open(plate_path).convert("RGBA")
    w, h = plate_rgba.size
    x0, y0, x1, y1 = _beak_overlay_rect(w, h, beak_config)
    overlay_size = (x1 - x0, y1 - y0)

    sprite_cache: dict[str, np.ndarray] = {}
    for key, path in sprites.items():
        if path.is_file():
            sprite_cache[key.upper()] = _load_sprite_rgba(path, overlay_size)

    n_frames = max(1, int(round(audio_duration * fps)))
    tmp_silent = output_path.with_suffix(".tmp_silent.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_silent), fourcc, fps, (w, h))
    if not writer.isOpened():
        raise OSError(f"Cannot open VideoWriter for {tmp_silent}")

    phoneme_counts: dict[str, int] = {}
    try:
        base_bgr = cv2.cvtColor(np.array(plate_rgba), cv2.COLOR_RGBA2BGR)
        for frame_idx in range(n_frames):
            t = frame_idx / fps
            frame = base_bgr.copy()
            phoneme = lookup_phoneme(mouth_cues, t)
            phoneme_counts[phoneme] = phoneme_counts.get(phoneme, 0) + 1
            sprite_path = resolve_phoneme_sprite(phoneme, sprites)
            if sprite_path:
                key = phoneme.upper()
                if key in ("G", "H"):
                    key = "C" if key == "G" else "D"
                if key == "X":
                    key = "A"
                sprite_rgba = sprite_cache.get(key)
                if sprite_rgba is not None:
                    _overlay_rgba_bgr(frame, sprite_rgba, x0, y0)
            writer.write(frame)
    finally:
        writer.release()

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(tmp_silent),
            "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    tmp_silent.unlink(missing_ok=True)

    return {
        "output_path": str(output_path),
        "duration_s": round(n_frames / fps, 3),
        "phoneme_count": sum(phoneme_counts.values()),
        "phoneme_distribution": phoneme_counts,
        "mouth_cue_count": len(mouth_cues),
    }


def composite_rhubarb_lipsync(
    *,
    clip_path: Path,
    audio_path: Path,
    beak_config: dict[str, Any],
    sprites: dict[str, Path],
    output_path: Path,
    trim_start: float = 0.0,
    rhubarb_bin: str | None = None,
    dialog_text: str | None = None,
) -> dict[str, Any]:
    """Composite beak sprites frame-by-frame onto a video clip (beat pipeline)."""
    mouth_cues = run_rhubarb(
        audio_path,
        rhubarb_bin=rhubarb_bin,
        dialog_text=dialog_text,
    )
    audio_duration = float(mouth_cues[-1]["end"]) if mouth_cues else _audio_duration_s(audio_path)

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        raise OSError(f"Cannot open clip: {clip_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    x0, y0, x1, y1 = _beak_overlay_rect(w, h, beak_config)
    overlay_size = (x1 - x0, y1 - y0)

    sprite_cache: dict[str, np.ndarray] = {}
    for key, path in sprites.items():
        if path.is_file():
            sprite_cache[key.upper()] = _load_sprite_rgba(path, overlay_size)

    tmp_silent = output_path.with_suffix(".tmp_silent.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(tmp_silent), fourcc, fps, (w, h))
    if not writer.isOpened():
        cap.release()
        raise OSError(f"Cannot open VideoWriter for {tmp_silent}")

    phoneme_counts: dict[str, int] = {}
    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            t = frame_idx / fps - trim_start
            if 0.0 <= t <= audio_duration:
                phoneme = lookup_phoneme(mouth_cues, t)
                phoneme_counts[phoneme] = phoneme_counts.get(phoneme, 0) + 1
                sprite_path = resolve_phoneme_sprite(phoneme, sprites)
                if sprite_path:
                    key = phoneme.upper()
                    if key in ("G", "H"):
                        key = "C" if key == "G" else "D"
                    if key == "X":
                        key = "A"
                    sprite_rgba = sprite_cache.get(key)
                    if sprite_rgba is not None:
                        _overlay_rgba_bgr(frame, sprite_rgba, x0, y0)
            writer.write(frame)
            frame_idx += 1
    finally:
        cap.release()
        writer.release()

    delay_ms = int(trim_start * 1000)
    audio_filter = f"adelay={delay_ms}|{delay_ms}" if trim_start > 0.01 else "anull"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(tmp_silent),
            "-i", str(audio_path),
            "-filter_complex", f"[1:a]{audio_filter}[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    tmp_silent.unlink(missing_ok=True)

    return {
        "output_path": str(output_path),
        "duration_s": round(frame_idx / fps, 3),
        "phoneme_count": sum(phoneme_counts.values()),
        "phoneme_distribution": phoneme_counts,
        "mouth_cue_count": len(mouth_cues),
    }

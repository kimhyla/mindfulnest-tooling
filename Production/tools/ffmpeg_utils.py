#!/usr/bin/env python3
"""
ffmpeg_utils.py — Lean FFmpeg utilities for MindfulNest production pipeline.

Two functions:
  strip_audio(path)      — Remove audio track in-place (video copy, no re-encode)
  verify_no_audio(path)  — Assert no audio stream exists (security gate)

Called automatically by production_server.py and generate_animation_options.py
after downloading animation clips from WaveSpeed/Kling/Seedance.

Thread-safe: uses tempfile.NamedTemporaryFile for unique temp paths.
Atomic: os.replace() ensures all-or-nothing file swap.
"""

import os
import subprocess
import tempfile
from pathlib import Path


def _ffmpeg_available() -> bool:
    """Check if ffmpeg is in PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _has_audio(path: str) -> bool:
    """Check if file has an audio stream via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        return "audio" in r.stdout.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def strip_audio(video_path, verbose=True) -> bool:
    """Strip audio from MP4 in-place. Returns True if successful or already clean.

    Process: check for audio → ffmpeg -an -c:v copy to temp → verify → atomic replace.
    If ffmpeg is missing or fails, returns False (original file untouched).
    Thread-safe via NamedTemporaryFile unique paths.

    Args:
        video_path: str or Path to the MP4 file.
        verbose: print progress to stdout.

    Returns:
        True if file is now audio-free (stripped or was already clean).
        False if ffmpeg unavailable or strip failed.
    """
    video_path = Path(video_path)
    name = video_path.name

    if not video_path.is_file():
        if verbose:
            print(f"[ffmpeg] strip_audio: not found: {name}")
        return False

    # Already clean?
    if not _has_audio(str(video_path)):
        if verbose:
            print(f"[ffmpeg] {name}: no audio — already clean")
        return True

    if not _ffmpeg_available():
        if verbose:
            print(f"[ffmpeg] WARNING: ffmpeg not found — cannot strip audio from {name}")
        return False

    # Thread-safe temp file in same directory (for atomic os.replace)
    fd, temp_path = tempfile.mkstemp(suffix=".mp4", dir=str(video_path.parent))
    os.close(fd)

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-an", "-c:v", "copy", "-y", temp_path],
            capture_output=True, timeout=120,
        )

        if result.returncode != 0:
            if verbose:
                print(f"[ffmpeg] {name}: strip failed (code {result.returncode})")
            os.unlink(temp_path)
            return False

        # Verify: temp should have video but no audio
        if _has_audio(temp_path):
            if verbose:
                print(f"[ffmpeg] {name}: audio still present after strip — aborting")
            os.unlink(temp_path)
            return False

        # Atomic swap
        os.replace(temp_path, str(video_path))

        if verbose:
            size_mb = video_path.stat().st_size / (1024 * 1024)
            print(f"[ffmpeg] {name}: audio stripped ✓ ({size_mb:.1f} MB)")
        return True

    except subprocess.TimeoutExpired:
        if verbose:
            print(f"[ffmpeg] {name}: ffmpeg timed out")
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return False
    except Exception as e:
        if verbose:
            print(f"[ffmpeg] {name}: error — {e}")
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return False


def verify_no_audio(video_path) -> None:
    """Assert video has no audio stream. Raises ValueError if audio detected."""
    path = str(video_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    if _has_audio(path):
        raise ValueError(f"Audio track detected in {Path(path).name} — strip before serving")


def get_duration(video_path) -> float:
    """Get video duration in seconds via ffprobe. Returns 0.0 on error."""
    path = str(video_path)
    if not os.path.isfile(path):
        return 0.0
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip()) if r.returncode == 0 else 0.0
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0

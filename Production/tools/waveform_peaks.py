"""Generate normalized waveform peaks JSON for display-only timelines."""
from __future__ import annotations

import json
import math
import struct
import subprocess
import tempfile
from pathlib import Path

PEAKS_SCHEMA_VERSION = 1
DEFAULT_PEAK_BINS = 1200


def generate_peaks_from_audio(
    audio_path: Path,
    *,
    num_bins: int = DEFAULT_PEAK_BINS,
) -> dict:
    """Return WaveSurfer-compatible peaks payload from an audio file."""
    audio_path = Path(audio_path).resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"missing audio for peaks: {audio_path}")

    with tempfile.NamedTemporaryFile(suffix=".f32le", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(audio_path),
            "-ac", "1", "-ar", "8000",
            "-f", "f32le",
            str(tmp_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        raw = tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    if len(raw) < 4:
        return {
            "version": PEAKS_SCHEMA_VERSION,
            "channels": 1,
            "length": 0,
            "data": [],
            "duration_s": 0.0,
        }

    sample_count = len(raw) // 4
    samples = struct.unpack(f"<{sample_count}f", raw[: sample_count * 4])
    duration_s = sample_count / 8000.0
    bins = max(32, int(num_bins))
    block = max(1, sample_count // bins)
    peaks: list[float] = []
    for i in range(bins):
        start = i * block
        end = min(sample_count, start + block)
        if start >= end:
            peaks.append(0.0)
            continue
        chunk = samples[start:end]
        peak = max(abs(v) for v in chunk)
        peaks.append(min(1.0, float(peak)))

    max_peak = max(peaks) if peaks else 1.0
    if max_peak > 0:
        peaks = [round(p / max_peak, 4) for p in peaks]

    return {
        "version": PEAKS_SCHEMA_VERSION,
        "channels": 1,
        "length": len(peaks),
        "data": peaks,
        "duration_s": round(duration_s, 3),
    }


def write_peaks_json(peaks: dict, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(peaks), encoding="utf-8")
    tmp.replace(dest)
    return dest

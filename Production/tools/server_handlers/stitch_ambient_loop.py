"""STITCH_AMBIENT_LOOP_XFADE_V1 — seamless crossfade loop for stitch ambient beds.

Hard ``aloop`` joins expose MP3 encoder padding and non-zero-crossing cuts as audible
gaps when beds repeat under long slot video. Trim head/tail silence from source beds,
build a one-period seamless tile (tail crossfaded into head), then loop to slot duration.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

STITCH_AMBIENT_LOOP_XFADE_V1 = "STITCH_AMBIENT_LOOP_XFADE_V1"
STITCH_AMBIENT_LOOP_TRIM_V2 = "STITCH_AMBIENT_LOOP_TRIM_V2"
STITCH_AMBIENT_LOOP_CROSSFADE_S = 2.5
STITCH_AMBIENT_LOOP_MIN_BED_S = 1.0
STITCH_AMBIENT_LOOP_MIN_XFADE_S = 0.25
STITCH_AMBIENT_SILENCE_THRESHOLD_DB = -45
STITCH_AMBIENT_MIN_SILENCE_S = 0.2
# STITCH_AMBIENT_BED_MIX_FADE_IN_V1 — ramp bed under speech at slot start (avoids mix clicks).
STITCH_AMBIENT_BED_MIX_FADE_IN_V1 = "STITCH_AMBIENT_BED_MIX_FADE_IN_V1"
STITCH_AMBIENT_BED_MIX_FADE_IN_S = 0.5
# Ramp bed out at slot tail — avoids hard ambient stop when video ends.
STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1 = "STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1"
STITCH_AMBIENT_BED_SLOT_FADE_OUT_S = 0.75


def clamp_ambient_loop_crossfade_s(
    bed_dur_s: float,
    crossfade_s: float | None = None,
) -> float:
    """Crossfade length capped so tile construction stays valid for short beds."""
    xf = STITCH_AMBIENT_LOOP_CROSSFADE_S if crossfade_s is None else float(crossfade_s)
    if bed_dur_s <= 0:
        return 0.0
    xf = min(xf, bed_dur_s * 0.35)
    xf = min(xf, max(0.0, bed_dur_s - 0.25))
    return max(0.0, xf)


def probe_ambient_bed_active_span(
    bed_path: str | Path,
    *,
    file_dur_s: float | None = None,
) -> tuple[float, float]:
    """Return (active_start_s, active_end_s) excluding leading/trailing silence."""
    path = Path(bed_path)
    if file_dur_s is None:
        try:
            out = subprocess.check_output(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(path),
                ],
                text=True,
                timeout=15,
            ).strip()
            file_dur_s = float(out)
        except (subprocess.SubprocessError, TypeError, ValueError):
            file_dur_s = 0.0
    if file_dur_s <= 0:
        return 0.0, 0.0

    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "info",
                "-i", str(path),
                "-af", (
                    f"silencedetect=noise={STITCH_AMBIENT_SILENCE_THRESHOLD_DB}dB:"
                    f"d={STITCH_AMBIENT_MIN_SILENCE_S}"
                ),
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.SubprocessError:
        return 0.0, file_dur_s

    log = (proc.stderr or "") + (proc.stdout or "")
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", log)]

    active_start = 0.0
    if starts and starts[0] <= 0.001 and ends:
        active_start = ends[0]

    active_end = file_dur_s
    if starts:
        tail_start = starts[-1]
        if file_dur_s - tail_start >= STITCH_AMBIENT_MIN_SILENCE_S:
            active_end = max(active_start + 0.25, tail_start)

    if active_end <= active_start:
        return 0.0, file_dur_s
    return active_start, active_end


def ambient_bed_needs_seamless_loop(
    bed_dur_s: float,
    slot_dur_s: float,
    crossfade_s: float | None = None,
) -> bool:
    """True when slot exceeds bed length and crossfade tile is safe to build."""
    if slot_dur_s <= bed_dur_s or bed_dur_s < STITCH_AMBIENT_LOOP_MIN_BED_S:
        return False
    xf = clamp_ambient_loop_crossfade_s(bed_dur_s, crossfade_s)
    return xf >= STITCH_AMBIENT_LOOP_MIN_XFADE_S


def _ambient_bed_lane_out(
    inner: str,
    vol: float,
    out_label: str,
    slot_dur_s: float,
) -> str:
    """Fade bed in at t=0 and out at slot tail before volume — prevents amix clicks."""
    slot_s = max(float(slot_dur_s), 0.001)
    fade_in_s = min(STITCH_AMBIENT_BED_MIX_FADE_IN_S, slot_s * 0.25)
    fade_out_s = min(
        STITCH_AMBIENT_BED_SLOT_FADE_OUT_S,
        slot_s * 0.15,
        max(0.0, slot_s - fade_in_s - 0.05),
    )
    chain = f"{inner},afade=t=in:st=0:d={fade_in_s:.3f}"
    if fade_out_s >= 0.05:
        chain += f",afade=t=out:st={slot_s - fade_out_s:.3f}:d={fade_out_s:.3f}"
    return f"{chain},volume={vol:.3f}[{out_label}]"


def build_ambient_bed_filter_lane(
    input_idx: int,
    bed_dur_s: float,
    slot_dur_s: float,
    volume: float,
    *,
    out_label: str = "bed",
    crossfade_s: float | None = None,
    active_start_s: float = 0.0,
    active_end_s: float | None = None,
) -> str:
    """Return one ffmpeg filter_complex lane: mono ambient bed trimmed/looped to slot."""
    vol = float(volume)
    slot_s = max(float(slot_dur_s), 0.001)
    file_s = max(float(bed_dur_s), 0.0)
    start_s = max(0.0, float(active_start_s))
    end_s = file_s if active_end_s is None else min(file_s, max(start_s + 0.25, float(active_end_s)))
    content_s = max(0.0, end_s - start_s)

    base = f"[{input_idx}:a]aresample=44100,aformat=channel_layouts=mono"
    trimmed = (
        f"{base},atrim=start={start_s:.3f}:end={end_s:.3f},asetpts=PTS-STARTPTS"
    )

    if content_s <= 0:
        return _ambient_bed_lane_out(
            f"{base},atrim=duration={slot_s:.3f}", vol, out_label, slot_s,
        )

    if slot_s <= content_s:
        return _ambient_bed_lane_out(
            f"{trimmed},atrim=duration={slot_s:.3f}", vol, out_label, slot_s,
        )

    # Never hard ``aloop`` for beds long enough to tile — only seamless crossfade loops.
    if content_s < STITCH_AMBIENT_LOOP_MIN_BED_S:
        return _ambient_bed_lane_out(
            f"{trimmed},aloop=loop=-1:size=2147483647,atrim=duration={slot_s:.3f}",
            vol,
            out_label,
            slot_s,
        )

    xf = clamp_ambient_loop_crossfade_s(content_s, crossfade_s)
    if xf < STITCH_AMBIENT_LOOP_MIN_XFADE_S:
        xf = STITCH_AMBIENT_LOOP_MIN_XFADE_S
    body_end = content_s - xf
    p = f"amb{input_idx}"

    lane_body = (
        f"{trimmed},asplit=2[{p}full_a][{p}full_b];"
        f"[{p}full_a]asplit=2[{p}main][{p}tailsrc];"
        f"[{p}tailsrc]atrim=start={body_end:.3f}:duration={xf:.3f},"
        f"asetpts=PTS-STARTPTS[{p}tail];"
        f"[{p}full_b]atrim=0:{xf:.3f},asetpts=PTS-STARTPTS[{p}head];"
        f"[{p}tail][{p}head]acrossfade=d={xf:.3f}:c1=tri:c2=tri[{p}glue];"
        f"[{p}main]atrim=0:{body_end:.3f},asetpts=PTS-STARTPTS[{p}body];"
        f"[{p}body][{p}glue]concat=n=2:v=0:a=1[{p}tile];"
        f"[{p}tile]aloop=loop=-1:size=2147483647,atrim=duration={slot_s:.3f}"
    )
    return _ambient_bed_lane_out(lane_body, vol, out_label, slot_s)


def build_ambient_bed_filter_lane_for_file(
    input_idx: int,
    bed_path: str | Path,
    bed_dur_s: float,
    slot_dur_s: float,
    volume: float,
    *,
    out_label: str = "bed",
) -> str:
    """Probe active span then build loop lane (preferred entry point for mix paths)."""
    start_s, end_s = probe_ambient_bed_active_span(bed_path, file_dur_s=bed_dur_s)
    return build_ambient_bed_filter_lane(
        input_idx,
        bed_dur_s,
        slot_dur_s,
        volume,
        out_label=out_label,
        active_start_s=start_s,
        active_end_s=end_s,
    )


def ambient_loop_sig_token(crossfade_s: float | None = None) -> str:
    """Cache-bust token for waveform / slot mix hashes."""
    xf = STITCH_AMBIENT_LOOP_CROSSFADE_S if crossfade_s is None else float(crossfade_s)
    return (
        f"{STITCH_AMBIENT_LOOP_TRIM_V2}:{STITCH_AMBIENT_LOOP_XFADE_V1}:"
        f"{STITCH_AMBIENT_BED_MIX_FADE_IN_V1}:{STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1}:"
        f"{xf:.3f}:{STITCH_AMBIENT_BED_MIX_FADE_IN_S:.3f}:"
        f"{STITCH_AMBIENT_BED_SLOT_FADE_OUT_S:.3f}:no_hard_aloop_v1"
    )

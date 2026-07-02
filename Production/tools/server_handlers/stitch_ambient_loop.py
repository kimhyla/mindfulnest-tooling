"""STITCH_AMBIENT_LOOP_XFADE_V1 — seamless crossfade loop for stitch ambient beds.

Hard ``aloop`` joins expose MP3 encoder padding and non-zero-crossing cuts as audible
gaps when beds repeat under long slot video. Trim head/tail silence from source beds,
build a one-period seamless tile (tail crossfaded into head), then loop to slot duration.
"""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path

STITCH_AMBIENT_LOOP_XFADE_V1 = "STITCH_AMBIENT_LOOP_XFADE_V1"
STITCH_AMBIENT_SINGLE_SEAM_V1 = "STITCH_AMBIENT_SINGLE_SEAM_V1"  # superseded — glue-only tile (~2.5s loop)
STITCH_AMBIENT_FULL_PERIOD_TILE_V2 = "STITCH_AMBIENT_FULL_PERIOD_TILE_V2"
# FF-038 — explicit tile concat replaces hard aloop after period tile (de-click at period boundary).
STITCH_AMBIENT_TILE_CONCAT_LOOP_V1 = "STITCH_AMBIENT_TILE_CONCAT_LOOP_V1"
# FF-039 — acrossfade between period tiles (hard concat restarted bed opening every period).
STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1 = "STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1"
STITCH_AMBIENT_PERIOD_OFFSET_XFADE_V3 = "STITCH_AMBIENT_PERIOD_OFFSET_XFADE_V3"  # superseded — atrim mid-crossfade click at period
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


def estimate_ambient_tile_period_s(
    content_s: float,
    crossfade_s: float | None = None,
) -> float:
    """Expected audible loop period for a tiled bed (full trimmed content length)."""
    return max(0.0, float(content_s))


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


def build_ambient_seamless_period_tile(
    trimmed_prefix: str,
    *,
    prefix_label: str,
    content_s: float,
    crossfade_s: float | None = None,
) -> str:
    """One full-period tile: main body + soft tail→head wrap crossfade (length ≈ content_s).

    STITCH_AMBIENT_FULL_PERIOD_TILE_V2 — ``pre`` body + ``wrap`` crossfade → ``concat`` tile
    → ``aloop``. Operator-verified on Event_1–6 (f817b0c / 389b2ba).
    """
    xf = clamp_ambient_loop_crossfade_s(content_s, crossfade_s)
    if xf < STITCH_AMBIENT_LOOP_MIN_XFADE_S:
        xf = STITCH_AMBIENT_LOOP_MIN_XFADE_S
    body_end = max(0.0, content_s - xf)
    p = prefix_label
    return (
        f"{trimmed_prefix},asplit=2[{p}full_a][{p}full_b];"
        f"[{p}full_a]asplit=2[{p}main][{p}tailsrc];"
        f"[{p}tailsrc]atrim=start={body_end:.3f}:duration={xf:.3f},"
        f"asetpts=PTS-STARTPTS[{p}tail];"
        f"[{p}full_b]atrim=0:{xf:.3f},asetpts=PTS-STARTPTS[{p}head];"
        f"[{p}tail][{p}head]acrossfade=d={xf:.3f}:c1=tri:c2=tri[{p}wrap];"
        f"[{p}main]atrim=0:{body_end:.3f},asetpts=PTS-STARTPTS[{p}pre];"
        f"[{p}pre][{p}wrap]concat=n=2:v=0:a=1[{p}tile]"
    )


def _ambient_period_loop_reps(period_s: float, slot_s: float, junction_xfade_s: float) -> int:
    """How many period tiles to chain (with junction crossfades) to cover ``slot_s``."""
    period = max(float(period_s), 0.001)
    slot = max(float(slot_s), 0.001)
    jxf = max(float(junction_xfade_s), STITCH_AMBIENT_LOOP_MIN_XFADE_S)
    if period <= jxf + 0.01:
        reps = max(2, int(math.ceil(slot / period)) + 1)
    else:
        reps = max(2, int(math.ceil((slot - jxf) / (period - jxf))) + 1)
    return min(reps, 24)


def build_ambient_period_junction_loop(
    tile_label: str,
    period_s: float,
    slot_s: float,
    *,
    junction_xfade_s: float,
) -> str:
    """Repeat period tile via chained ``acrossfade`` — no hard restart at tile junctions."""
    period = max(float(period_s), 0.001)
    slot = max(float(slot_s), 0.001)
    jxf = max(float(junction_xfade_s), STITCH_AMBIENT_LOOP_MIN_XFADE_S)
    reps = _ambient_period_loop_reps(period, slot, jxf)
    loop_label = f"{tile_label}loop"
    if reps < 2:
        return f"[{tile_label}]atrim=duration={slot:.3f}[{loop_label}]"

    split_labels = [f"{tile_label}rep{i}" for i in range(reps)]
    split_targets = "".join(f"[{lab}]" for lab in split_labels)
    parts = [f"[{tile_label}]asplit={reps}{split_targets}"]
    current = split_labels[0]
    for i in range(1, reps):
        out_label = f"{tile_label}jx{i}" if i < reps - 1 else loop_label
        nxt = split_labels[i]
        parts.append(
            f"[{current}][{nxt}]acrossfade=d={jxf:.3f}:c1=tri:c2=tri[{out_label}]"
        )
        current = out_label
    parts.append(f"[{loop_label}]atrim=duration={slot:.3f}")
    return ";".join(parts)


def build_ambient_explicit_tile_concat_loop(
    tile_label: str,
    period_s: float,
    slot_s: float,
) -> str:
    """Deprecated — FF-039 routes to junction crossfade expansion."""
    xf = clamp_ambient_loop_crossfade_s(float(period_s))
    return build_ambient_period_junction_loop(
        tile_label, period_s, slot_s, junction_xfade_s=xf,
    )


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

    p = f"amb{input_idx}"
    # STITCH_AMBIENT_FULL_PERIOD_TILE_V2 — full bed period + soft wrap crossfade at tail only.
    period_tile = build_ambient_seamless_period_tile(
        trimmed, prefix_label=p, content_s=content_s, crossfade_s=crossfade_s,
    )
    tile_label = f"{p}tile"
    jxf = clamp_ambient_loop_crossfade_s(content_s, crossfade_s)
    loop_body = build_ambient_period_junction_loop(
        tile_label, content_s, slot_s, junction_xfade_s=jxf,
    )
    lane_body = f"{period_tile};{loop_body}"
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
        f"{STITCH_AMBIENT_FULL_PERIOD_TILE_V2}:"
        f"{STITCH_AMBIENT_TILE_CONCAT_LOOP_V1}:"
        f"{STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1}:"
        f"{STITCH_AMBIENT_BED_MIX_FADE_IN_V1}:{STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1}:"
        f"{xf:.3f}:{STITCH_AMBIENT_BED_MIX_FADE_IN_S:.3f}:"
        f"{STITCH_AMBIENT_BED_SLOT_FADE_OUT_S:.3f}:period_junction_xfade_v1"
    )

"""Re-assemble segmented Phase B Kling chunks on the full meditation timeline.

PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1: place existing seg_*_kling_raw clips at
their absolute audio positions, insert last-frame holds for meditation silences,
mux the full voice stem, then delivery encode. No new Kling jobs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
_CRED = TOOLS / "credentials_lib"
if str(_CRED) not in sys.path:
    sys.path.insert(0, str(_CRED))

from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402
from phase_b_kling_segmented_lipsync import (  # noqa: E402
    compute_phase_b_kling_segments,
)
from phase_module_lipsync_delivery import finalize_phase_module_lipsync_delivery  # noqa: E402

PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1 = "PHASE_B_SEGMENTED_TIMELINE_ASSEMBLE_V1"
PHASE_B_SEGMENTED_TIMELINE_GAP_XFADE_V2 = "PHASE_B_SEGMENTED_TIMELINE_GAP_XFADE_V2"
GAP_XFADE_S = 0.9
MIN_GAP_S = 0.05


@dataclass(frozen=True)
class TimelinePiece:
    label: str
    path: Path
    duration_s: float


def _run_ffmpeg(cmd: list[str], *, timeout_s: int = 600) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)


def _trim_chunk_to_speech(raw: Path, out: Path, duration_s: float) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(raw),
        "-t", f"{duration_s:.6f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out),
    ])


def _trim_video_only(src: Path, out: Path, *, start_s: float = 0.0, duration_s: float | None = None) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start_s:.6f}",
        "-i", str(src),
    ]
    if duration_s is not None:
        cmd.extend(["-t", f"{duration_s:.6f}"])
    cmd.extend([
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-movflags", "+faststart",
        str(out),
    ])
    _run_ffmpeg(cmd)


def _xfade_video_pair(
    file_a: Path,
    file_b: Path,
    out: Path,
    *,
    dur_a: float,
    fade_s: float,
) -> None:
    fade_s = min(fade_s, dur_a, ffprobe_duration(file_b))
    if fade_s < 0.08:
        raise ValueError(f"xfade too short: {fade_s}")
    offset = max(0.0, dur_a - fade_s)
    norm = "fps=24,setpts=PTS-STARTPTS"
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(file_a),
        "-i", str(file_b),
        "-filter_complex",
        (
            f"[0:v]{norm}[v0];[1:v]{norm}[v1];"
            f"[v0][v1]xfade=transition=fade:duration={fade_s:.6f}:offset={offset:.6f}[v]"
        ),
        "-map", "[v]",
        "-t", f"{fade_s:.6f}",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-movflags", "+faststart",
        str(out),
    ])


def _gap_xfade_s(gap_s: float, chunk_s: float, requested: float) -> float:
    cap = min(requested, gap_s * 0.55, chunk_s * 0.12)
    return max(0.0, min(requested, cap))


def _append_gap_with_xfade(
    pieces: list[TimelinePiece],
    *,
    hold: Path,
    gap_s: float,
    next_chunk: Path,
    chunk_s: float,
    build: Path,
    label: str,
    gap_xfade_s: float,
) -> None:
    xf = _gap_xfade_s(gap_s, chunk_s, gap_xfade_s)
    if xf < 0.12:
        pieces.append(TimelinePiece(label, hold, gap_s))
        return False

    prefix_d = max(0.02, gap_s - xf)
    body_start = xf
    body_d = max(0.02, chunk_s - body_start)

    prefix = build / f"{label}_prefix.mp4"
    bridge = build / f"{label}_xfade.mp4"
    body = build / f"{label}_into_chunk.mp4"

    _trim_video_only(hold, prefix, duration_s=prefix_d)
    _xfade_video_pair(hold, next_chunk, bridge, dur_a=gap_s, fade_s=xf)
    _trim_video_only(next_chunk, body, start_s=body_start, duration_s=body_d)

    pieces.append(TimelinePiece(f"{label}_hold", prefix, prefix_d))
    pieces.append(TimelinePiece(f"{label}_xfade", bridge, xf))
    pieces.append(TimelinePiece(f"{label}_body", body, body_d))
    return True


def _hold_from_tail(src: Path, out: Path, hold_s: float) -> None:
    if hold_s < MIN_GAP_S:
        raise ValueError(f"hold too short: {hold_s}")
    frame = out.with_suffix(".png")
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-sseof", "-1",
        "-i", str(src),
        "-update", "1",
        "-frames:v", "1",
        str(frame),
    ], timeout_s=120)
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "24",
        "-i", str(frame),
        "-t", f"{hold_s:.6f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24", "-an",
        "-movflags", "+faststart",
        str(out),
    ], timeout_s=120)
    try:
        frame.unlink()
    except OSError:
        pass


def _loop_from_tail(src: Path, out: Path, hold_s: float, *, loop_s: float = 2.0) -> None:
    """Gap fill: loop the last ``loop_s`` of ``src`` for ``hold_s`` (Avatar route)."""
    if hold_s < MIN_GAP_S:
        raise ValueError(f"hold too short: {hold_s}")
    src_dur = ffprobe_duration(src)
    seg_s = min(max(loop_s, 0.5), src_dur, hold_s)
    start_s = max(0.0, src_dur - seg_s)
    loop_clip = out.with_name(out.stem + "_loopseg.mp4")
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start_s:.6f}",
        "-i", str(src),
        "-t", f"{seg_s:.6f}",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-movflags", "+faststart",
        str(loop_clip),
    ], timeout_s=120)
    loops = max(1, int(hold_s / seg_s) + 1)
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-stream_loop", str(loops),
        "-i", str(loop_clip),
        "-t", f"{hold_s:.6f}",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-movflags", "+faststart",
        str(out),
    ], timeout_s=120)
    try:
        loop_clip.unlink()
    except OSError:
        pass


def _load_chunk_specs(work_dir: Path, audio: Path) -> tuple[float, list[dict]]:
    audio_dur, specs = compute_phase_b_kling_segments(audio)
    rows: list[dict] = []
    for spec in specs:
        meta_path = work_dir / f"seg_{spec.index}_meta.json"
        raw_path = work_dir / f"seg_{spec.index}_kling_raw.mp4"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            start_s = float(meta.get("start_s", spec.start_s))
            end_s = float(meta.get("end_s", spec.end_s))
        else:
            start_s, end_s = spec.start_s, spec.end_s
        if not raw_path.is_file():
            raise FileNotFoundError(f"missing chunk raw: {raw_path}")
        rows.append({
            "index": spec.index,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": end_s - start_s,
            "raw_path": raw_path,
        })
    return audio_dur, rows


def assemble_segmented_timeline(
    work_dir: Path,
    audio: Path,
    out_path: Path,
    *,
    assemble_work: Path | None = None,
    gap_xfade_s: float = GAP_XFADE_S,
    gap_fill: str = "hold",
    apply_delivery: bool = True,
) -> dict:
    """Build full-timeline Phase B lipsync from existing segmented raws.

    gap_fill: ``hold`` (single-frame, legacy Kling) or ``loop`` (tail loop for Avatar gaps).
    """
    work_dir = work_dir.expanduser().resolve()
    audio = audio.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    build = assemble_work or (work_dir / "_timeline_gap_xfade_work")
    build.mkdir(parents=True, exist_ok=True)

    gap_fill_mode = (gap_fill or "hold").strip().lower()
    if gap_fill_mode not in {"hold", "loop"}:
        raise ValueError(f"gap_fill must be hold or loop, got {gap_fill!r}")

    def _gap_fill(src: Path, dest: Path, gap_s: float) -> None:
        if gap_fill_mode == "loop":
            _loop_from_tail(src, dest, gap_s)
        else:
            _hold_from_tail(src, dest, gap_s)

    audio_dur, chunks = _load_chunk_specs(work_dir, audio)
    trimmed: dict[int, Path] = {}
    trim_dur: dict[int, float] = {}
    for row in chunks:
        idx = int(row["index"])
        dur = float(row["duration_s"])
        path = build / f"chunk_{idx}_trim.mp4"
        _trim_chunk_to_speech(row["raw_path"], path, dur)
        trimmed[idx] = path
        trim_dur[idx] = dur

    pieces: list[TimelinePiece] = []
    gap_xfade_used: list[float] = []
    skip_next_chunk = False

    for i, row in enumerate(chunks):
        idx = int(row["index"])
        if skip_next_chunk:
            skip_next_chunk = False
        else:
            pieces.append(TimelinePiece(f"chunk_{idx}", trimmed[idx], trim_dur[idx]))

        next_row = chunks[i + 1] if i + 1 < len(chunks) else None
        if next_row is None:
            continue
        gap_s = float(next_row["start_s"]) - float(row["end_s"])
        if gap_s < MIN_GAP_S:
            continue
        hold = build / f"gap_after_{idx}.mp4"
        _gap_fill(trimmed[idx], hold, gap_s)
        nidx = int(next_row["index"])
        used_xfade = _append_gap_with_xfade(
            pieces,
            hold=hold,
            gap_s=gap_s,
            next_chunk=trimmed[nidx],
            chunk_s=trim_dur[nidx],
            build=build,
            label=f"gap_{idx}",
            gap_xfade_s=gap_xfade_s,
        )
        if used_xfade:
            gap_xfade_used.append(_gap_xfade_s(gap_s, trim_dur[nidx], gap_xfade_s))
            skip_next_chunk = True
        else:
            pieces.append(TimelinePiece(f"gap_{idx}", hold, gap_s))

    tail_s = audio_dur - float(chunks[-1]["end_s"])
    overlap_pad = sum(gap_xfade_used)
    tail_s += overlap_pad
    if tail_s >= MIN_GAP_S:
        tail_src = pieces[-1].path
        tail = build / "gap_tail.mp4"
        _gap_fill(tail_src, tail, tail_s)
        pieces.append(TimelinePiece("gap_tail", tail, tail_s))

    concat_video = build / "timeline_video.mp4"
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(_write_concat_list(build, pieces)),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24", "-an",
        "-movflags", "+faststart",
        str(concat_video),
    ], timeout_s=900)

    video_dur = ffprobe_duration(concat_video)
    if abs(video_dur - audio_dur) > 0.15:
        pad_s = audio_dur - video_dur
        if pad_s > MIN_GAP_S:
            pad = build / "timeline_pad_tail.mp4"
            _gap_fill(concat_video, pad, pad_s)
            padded = build / "timeline_video_padded.mp4"
            _run_ffmpeg([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(_write_concat_list(build, [
                    TimelinePiece("main", concat_video, video_dur),
                    TimelinePiece("pad", pad, pad_s),
                ])),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", "24", "-an",
                "-movflags", "+faststart",
                str(padded),
            ], timeout_s=600)
            concat_video = padded

    muxed = build / "timeline_mux.mp4"
    _run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(concat_video),
        "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{audio_dur:.6f}",
        str(muxed),
    ])

    if apply_delivery:
        finalize_phase_module_lipsync_delivery(muxed, sharpen=True)
    import os
    os.replace(muxed, out_path)

    out_dur = ffprobe_duration(out_path)
    manifest = {
        "code": PHASE_B_SEGMENTED_TIMELINE_GAP_XFADE_V2,
        "source_work_dir": work_dir.name,
        "source_audio": audio.name,
        "output": out_path.name,
        "audio_duration_s": round(audio_dur, 3),
        "video_duration_s": round(out_dur, 3),
        "chunk_count": len(chunks),
        "piece_count": len(pieces),
        "gap_xfade_s": gap_xfade_s,
        "gap_fill": gap_fill_mode,
        "gap_xfade_applied": [round(x, 3) for x in gap_xfade_used],
        "pieces": [
            {"label": p.label, "duration_s": round(p.duration_s, 3)}
            for p in pieces
        ],
        "chunks": [
            {
                "index": c["index"],
                "start_s": c["start_s"],
                "end_s": c["end_s"],
            }
            for c in chunks
        ],
    }
    manifest_path = out_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _write_concat_list(build: Path, pieces: list[TimelinePiece]) -> Path:
    lst = build / "concat_list.txt"
    lines = [f"file '{p.path.resolve()}'\n" for p in pieces]
    lst.write_text("".join(lines), encoding="utf-8")
    return lst

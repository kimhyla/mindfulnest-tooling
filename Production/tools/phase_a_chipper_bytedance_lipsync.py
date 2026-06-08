#!/usr/bin/env python3
"""Chipper Phase A lipsync — ByteDance LatentSync (raw, no face composite).

Locked policy (Kim 2026-06-01):
  - Phase A / Chipper (birds): ByteDance-tight (§8.5 segment split when >7s)
  - Phase B / Cedric (human): Kling Sync via handle_phase_b_lipsync
  - Do NOT use Kling Sync on birds (human arms/teeth on wings)
  - Do NOT use beak face composite (ghost bird artifact)

See Production/docs/PHASE_A_CHIPPER_PIPELINE_LOCKED_v1.md
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BYTEDANCE_URL = "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video"
BYTEDANCE_MAX_CHUNK_S = 7.0
VIDEO_TRIM_TAILROOM_S = 3.0

HERE = Path(__file__).resolve().parent


def log(msg: str) -> None:
    print(f"[phase_a_bytedance] {msg}", flush=True)


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip() or "0")


def _production_server():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import production_server as ps  # noqa: WPS433

    return ps


def forward_loop(src: Path, dst: Path, target_s: float) -> None:
    """Repeat forward copies only (no reverse) — avoids motion reversal mid-speech."""
    src_dur = ffprobe_duration(src)
    if src_dur <= 0:
        raise ValueError(f"invalid source duration: {src}")
    repeats = max(1, int((target_s / src_dur) + 0.999))
    tmp_dir = dst.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    concat_list = tmp_dir / f"fwd_list_{src.stem}_{os.getpid()}.txt"
    line = "file '" + str(src.resolve()).replace("'", "'\\''") + "'"
    concat_list.write_text("\n".join([line] * repeats) + "\n", encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-t", f"{target_s:.3f}", "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    concat_list.unlink(missing_ok=True)
    log(f"forward loop: {src_dur:.1f}s x {repeats} -> {dst.name} ({ffprobe_duration(dst):.1f}s)")


def prep_audio_bytedance_style(src: Path, tmp_dir: Path) -> Path:
    """Beat pipeline: §8.4 silcomp + loudnorm + auto-preroll for LatentSync."""
    ps = _production_server()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = tmp_dir / f"_tmp_silcomp_bd_phase_a_{ts}.mp3"
    audio_out, meta = ps._silcomp_audio(src, dst, loudnorm=True, auto_preroll=True)
    dur = meta.get("compressed_duration_s", ffprobe_duration(audio_out))
    preroll = (meta.get("preroll_processing") or {}).get("preroll_added_s", 0)
    log(f"audio prep: silcomp+loudnorm+preroll({preroll}s) -> {audio_out.name} ({dur:.1f}s)")
    return audio_out


def chunk_audio_for_bytedance(
    audio_dur: float,
    silences: list[tuple[float, float]],
    *,
    max_chunk_s: float = BYTEDANCE_MAX_CHUNK_S,
) -> list[tuple[float, float]]:
    """Split timeline into ≤max_chunk_s windows at silence boundaries (§8.5)."""
    silences = sorted(silences)
    speech: list[tuple[float, float]] = []
    pos = 0.0
    for s, e in silences:
        if s > pos + 0.05:
            speech.append((pos, s))
        pos = max(pos, e)
    if pos < audio_dur - 0.05:
        speech.append((pos, audio_dur))
    if not speech:
        speech = [(0.0, audio_dur)]

    chunks: list[tuple[float, float]] = []
    cur_start, cur_end = speech[0]
    for seg_start, seg_end in speech[1:]:
        if seg_end - cur_start <= max_chunk_s:
            cur_end = seg_end
        else:
            chunks.append((cur_start, cur_end))
            cur_start, cur_end = seg_start, seg_end
    chunks.append((cur_start, cur_end))

    fixed: list[tuple[float, float]] = []
    for start, end in chunks:
        dur = end - start
        if dur <= max_chunk_s + 0.01:
            fixed.append((start, end))
            continue
        n = int(dur / max_chunk_s) + 1
        step = dur / n
        for i in range(n):
            fixed.append((start + i * step, start + (i + 1) * step))
    return fixed


def extract_audio_segment(src: Path, dst: Path, start_s: float, end_s: float) -> None:
    dur = max(0.05, end_s - start_s)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start_s:.3f}", "-t", f"{dur:.3f}",
            "-i", str(src), "-c:a", "libmp3lame", "-q:a", "2", str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def trim_video_for_lipsync(
    source_video: Path,
    dst: Path,
    audio_duration_s: float,
    *,
    trim_start: float = 0.0,
) -> Path:
    ps = _production_server()
    out, _, _, _ = ps._trim_video_to_audio(
        source_video, dst, audio_duration_s, trim_start=trim_start,
    )
    return out


def concat_videos(parts: list[Path], dest: Path) -> None:
    tmp_dir = dest.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)
    clist = tmp_dir / f"concat_{dest.stem}_{os.getpid()}.txt"
    clist.write_text(
        "\n".join(
            "file '" + str(p.resolve()).replace("'", "'\\''") + "'"
            for p in parts
        ) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(clist),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(dest),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    clist.unlink(missing_ok=True)


def trim_padded_lipsync_segment(
    raw_path: Path,
    dest_path: Path,
    speech_duration_s: float,
) -> Path:
    """Strip pad_audio_for_lipsync margins (+0.5s lead / +2.5s tail per chunk)."""
    import lipsync_sender as ls  # noqa: WPS433

    ps = _production_server()
    out, _, _, _ = ps._trim_video_to_audio(
        raw_path,
        dest_path,
        speech_duration_s,
        trim_start=ls.LIPSYNC_PAD_START,
    )
    log(
        f"trim pad: {raw_path.name} {ffprobe_duration(raw_path):.2f}s "
        f"-> {dest_path.name} {ffprobe_duration(out):.2f}s "
        f"(speech={speech_duration_s:.2f}s)"
    )
    return out


def run_bytedance_lipsync(video: Path, audio: Path, out_path: Path) -> None:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import lipsync_sender as ls  # noqa: WPS433
    from kling_startend_pipeline import load_api_keys  # noqa: WPS433

    ls.LIPSYNC_SUBMIT_URL = BYTEDANCE_URL
    keys = load_api_keys()
    client = ls.LipSyncClient(keys["wavespeed"])

    padded = ls.pad_audio_for_lipsync(audio)
    try:
        log(f"ByteDance submit: video={video.name} audio={audio.name}")
        job_id = client.submit(video, padded)
        result = client.poll_until_done(job_id)
        url = result["outputs"][0]
        client.download(url, out_path)
        log(
            f"ByteDance raw: {out_path.name} "
            f"({out_path.stat().st_size / 1024 / 1024:.1f} MB)"
        )
    finally:
        if padded != audio and padded.exists():
            padded.unlink(missing_ok=True)


def run_bytedance_tight_lipsync(
    base_video: Path,
    audio_raw: Path,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
) -> Path:
    """Raw ByteDance with beat-pipeline audio prep and §8.5 segmentation."""
    work = tmp_dir or (out_path.parent / "_tmp_phase_a_bytedance")
    work.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    audio = prep_audio_bytedance_style(audio_raw, work)
    audio_dur = ffprobe_duration(audio)

    if audio_dur <= BYTEDANCE_MAX_CHUNK_S:
        target_s = audio_dur + VIDEO_TRIM_TAILROOM_S
        looped = work / f"chipper_fwd_{ts}.mp4"
        forward_loop(base_video, looped, target_s)
        trimmed = work / f"chipper_trim_{ts}.mp4"
        trim_video_for_lipsync(looped, trimmed, audio_dur)
        raw_out = work / f"chipper_bd_{ts}.mp4"
        run_bytedance_lipsync(trimmed, audio, raw_out)
        trim_padded_lipsync_segment(raw_out, out_path, audio_dur)
        return out_path

    ps = _production_server()
    silences = ps._detect_silences(audio)
    chunks = chunk_audio_for_bytedance(audio_dur, silences)
    log(f"§8.5 segment split: {len(chunks)} chunks (max {BYTEDANCE_MAX_CHUNK_S}s pre-pad)")

    seg_paths: list[Path] = []
    for i, (t0, t1) in enumerate(chunks):
        chunk_dur = t1 - t0
        seg_audio = work / f"seg_{i}_{ts}.mp3"
        extract_audio_segment(audio, seg_audio, t0, t1)
        target_s = chunk_dur + VIDEO_TRIM_TAILROOM_S
        looped = work / f"seg_{i}_fwd_{ts}.mp4"
        forward_loop(base_video, looped, target_s)
        trimmed = work / f"seg_{i}_trim_{ts}.mp4"
        trim_video_for_lipsync(looped, trimmed, chunk_dur, trim_start=0.0)
        seg_raw = work / f"seg_{i}_bd_{ts}.mp4"
        log(f"  chunk {i + 1}/{len(chunks)}: {t0:.1f}-{t1:.1f}s ({chunk_dur:.1f}s)")
        run_bytedance_lipsync(trimmed, seg_audio, seg_raw)
        seg_trimmed = work / f"seg_{i}_bd_trim_{ts}.mp4"
        trim_padded_lipsync_segment(seg_raw, seg_trimmed, chunk_dur)
        seg_paths.append(seg_trimmed)

    concat_videos(seg_paths, out_path)
    log(f"segmented lipsync: {len(seg_paths)} parts -> {out_path.name}")
    return out_path

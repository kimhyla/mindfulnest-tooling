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

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BYTEDANCE_URL = "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video"
BYTEDANCE_MAX_CHUNK_S = 7.0
VIDEO_TRIM_TAILROOM_S = 3.0
GAP_MIN_S = 0.05
# Tail of pre-speech idle gap used as ByteDance video seed (continuity across chunks).
CHAIN_GAP_TAIL_S = 0.5

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


def compute_bytedance_chunks(audio: Path) -> tuple[float, list[tuple[float, float]]]:
    """Return (audio_dur, speech chunk windows) for §8.5 segmentation."""
    audio_dur = ffprobe_duration(audio)
    ps = _production_server()
    silences = ps._detect_silences(audio)
    chunks = chunk_audio_for_bytedance(audio_dur, silences)
    return audio_dur, chunks


def make_idle_gap_clip(base_video: Path, duration_s: float, out_path: Path) -> Path | None:
    """Idle base loop + silent audio — preserves natural pauses between speech chunks."""
    if duration_s < GAP_MIN_S:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    looped = out_path.with_name(f"{out_path.stem}_loop.mp4")
    forward_loop(base_video, looped, duration_s)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(looped),
            "-f", "lavfi", "-t", f"{duration_s:.3f}",
            "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-shortest", "-movflags", "+faststart",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    looped.unlink(missing_ok=True)
    log(f"idle gap: {duration_s:.2f}s -> {out_path.name}")
    return out_path


    log(f"idle gap: {duration_s:.2f}s -> {out_path.name}")
    return out_path


def build_chained_video_from_gap_end(
    gap_clip: Path,
    target_s: float,
    dst: Path,
    *,
    tail_s: float = CHAIN_GAP_TAIL_S,
) -> Path:
    """Build ByteDance input video continuing from the end of a pre-speech idle gap."""
    gap_dur = ffprobe_duration(gap_clip)
    if gap_dur <= 0:
        raise ValueError(f"invalid gap clip duration: {gap_clip}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tail_use = min(tail_s, max(0.1, gap_dur - 0.05))
    tail_start = max(0.0, gap_dur - tail_use)
    tmp = dst.parent / f"{dst.stem}_tail.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{tail_start:.3f}", "-i", str(gap_clip),
            "-t", f"{tail_use:.3f}", "-an",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(tmp),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    tail_dur = ffprobe_duration(tmp)
    pad_s = max(0.0, target_s - tail_dur)
    if pad_s < 0.01:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(tmp), "-t", f"{target_s:.3f}", "-an",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    else:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(tmp),
                "-vf", f"tpad=stop_mode=clone:stop_duration={pad_s:.3f}",
                "-t", f"{target_s:.3f}", "-an",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    tmp.unlink(missing_ok=True)
    out_dur = ffprobe_duration(dst)
    if abs(out_dur - target_s) > 0.15:
        raise RuntimeError(
            f"chain video duration mismatch: {out_dur:.3f}s != target {target_s:.3f}s"
        )
    log(
        f"chain from gap: {gap_clip.name} tail={tail_use:.2f}s "
        f"-> {dst.name} ({out_dur:.2f}s)"
    )
    return dst


def ensure_timeline_gaps(
    chunks: list[tuple[float, float]],
    base_video: Path,
    work: Path,
    tag: str,
    prebuilt: dict[str | int, Path] | None = None,
) -> dict[str | int, Path]:
    """Build or reuse idle gap clips keyed by 'lead' and inter-chunk indices."""
    gaps: dict[str | int, Path] = dict(prebuilt or {})
    work.mkdir(parents=True, exist_ok=True)
    if chunks and chunks[0][0] > GAP_MIN_S and "lead" not in gaps:
        lead = make_idle_gap_clip(
            base_video, chunks[0][0], work / f"gap_lead_{tag}.mp4",
        )
        if lead:
            gaps["lead"] = lead
    for i in range(len(chunks) - 1):
        gap_dur = chunks[i + 1][0] - chunks[i][1]
        if gap_dur <= GAP_MIN_S or i in gaps:
            continue
        gap = make_idle_gap_clip(
            base_video, gap_dur, work / f"gap_{i}_{tag}.mp4",
        )
        if gap:
            gaps[i] = gap
    return gaps


def build_pieces_with_timeline_gaps(
    chunk_segments: list[Path],
    chunks: list[tuple[float, float]],
    base_video: Path,
    work: Path,
    tag: str,
    *,
    prebuilt_gaps: dict[str | int, Path] | None = None,
) -> list[Path]:
    """Interleave speech segments with idle+silence gaps from prepped audio timeline."""
    if len(chunk_segments) != len(chunks):
        raise ValueError(
            f"segment/chunk count mismatch: {len(chunk_segments)} vs {len(chunks)}"
        )
    work.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    gaps_s: list[float] = []
    gap_files = ensure_timeline_gaps(chunks, base_video, work, tag, prebuilt_gaps)

    if chunks and chunks[0][0] > GAP_MIN_S:
        lead = gap_files.get("lead")
        if lead:
            pieces.append(lead)
            gaps_s.append(chunks[0][0])

    for i, seg in enumerate(chunk_segments):
        pieces.append(seg)
        if i + 1 < len(chunks):
            gap_dur = chunks[i + 1][0] - chunks[i][1]
            if gap_dur > GAP_MIN_S:
                gap = gap_files.get(i)
                if gap is None:
                    gap = make_idle_gap_clip(
                        base_video, gap_dur, work / f"gap_{i}_{tag}.mp4",
                    )
                if gap:
                    pieces.append(gap)
                    gaps_s.append(gap_dur)

    total_gap = sum(gaps_s)
    log(
        f"timeline gaps: {len(gaps_s)} inserts, {total_gap:.2f}s "
        f"({len(pieces)} pieces total)"
    )
    return pieces


def prepare_speech_segments_from_work(
    work: Path,
    chunks: list[tuple[float, float]],
    out_work: Path,
    tag: str,
) -> list[Path]:
    """Re-trim saved ByteDance raw segments to exact speech windows."""
    out_work.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    for i, (t0, t1) in enumerate(chunks):
        speech_s = t1 - t0
        raw_candidates = [
            p for p in sorted(work.glob(f"seg_{i}_bd_*.mp4"))
            if "_bd_trim_" not in p.name
        ]
        raw = raw_candidates[0] if raw_candidates else None
        if raw is None:
            trimmed = sorted(work.glob(f"seg_{i}_bd_trim_*.mp4"))
            raw = trimmed[0] if trimmed else None
        if raw is None:
            raise FileNotFoundError(f"segment {i} not found under {work}")
        dst = out_work / f"seg_{i}_speech_{tag}.mp4"
        trim_padded_lipsync_segment(raw, dst, speech_s)
        segments.append(dst)
    return segments


def reconcat_bytedance_segments_with_gaps(
    base_video: Path,
    audio_prepped: Path,
    chunk_segments: list[Path] | None,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
    segments_work: Path | None = None,
) -> dict:
    """Rebuild segmented middle from existing trim segments — no API calls."""
    work = tmp_dir or (out_path.parent / "_reconcat_gaps")
    work.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    _, chunks = compute_bytedance_chunks(audio_prepped)

    if segments_work and segments_work.is_dir():
        segs = prepare_speech_segments_from_work(segments_work, chunks, work, ts)
    elif chunk_segments:
        segs = chunk_segments
    else:
        raise ValueError("segments_work or chunk_segments required")

    pieces = build_pieces_with_timeline_gaps(
        segs, chunks, base_video, work, ts, prebuilt_gaps=None,
    )
    concat_videos(pieces, out_path)
    meta = {
        "timeline_gaps_preserved": True,
        "chunk_count": len(chunks),
        "gap_insert_count": len(pieces) - len(segs),
        "output_duration_s": round(ffprobe_duration(out_path), 3),
        "prepped_audio_duration_s": round(ffprobe_duration(audio_prepped), 3),
    }
    log(f"reconcat with gaps -> {out_path.name} ({meta['output_duration_s']:.2f}s)")
    return meta


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
    """Strip LipSync pad margins while keeping ByteDance A/V in sync."""
    import lipsync_sender as ls  # noqa: WPS433

    pad_start = ls.LIPSYNC_PAD_START
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{pad_start:.3f}",
            "-i", str(raw_path),
            "-t", f"{speech_duration_s:.3f}",
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart",
            str(dest_path),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    log(
        f"trim pad A/V: {raw_path.name} -> {dest_path.name} "
        f"(speech={speech_duration_s:.2f}s, v={ffprobe_duration(dest_path):.2f}s)"
    )
    return dest_path


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


def detect_work_tag(work: Path) -> str | None:
    """Reuse timestamp tag from an in-progress bytedance_work directory."""
    leads = sorted(work.glob("gap_lead_*.mp4"))
    if not leads:
        manifests = sorted(work.glob("chain_manifest_*.json"))
        if manifests:
            return manifests[-1].stem.replace("chain_manifest_", "")
        return None
    return leads[-1].stem.replace("gap_lead_", "")


def load_existing_gaps(work: Path) -> dict[str | int, Path]:
    gaps: dict[str | int, Path] = {}
    for p in sorted(work.glob("gap_lead_*.mp4")):
        gaps["lead"] = p
    for p in sorted(work.glob("gap_[0-9]_*.mp4")):
        parts = p.stem.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            gaps[int(parts[1])] = p
    return gaps


def find_existing_seg_trim(work: Path, chunk_index: int) -> Path | None:
    cands = sorted(work.glob(f"seg_{chunk_index}_bd_trim_*.mp4"))
    return cands[-1] if cands else None


def run_bytedance_tight_lipsync(
    base_video: Path,
    audio_raw: Path,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
    audio_prepped: bool = False,
    out_meta: dict | None = None,
    chain_chunks: bool = False,
    resume: bool = False,
) -> Path:
    """Raw ByteDance with beat-pipeline audio prep and §8.5 segmentation."""
    work = tmp_dir or (out_path.parent / "_tmp_phase_a_bytedance")
    work.mkdir(parents=True, exist_ok=True)
    resume_tag = detect_work_tag(work) if resume else None
    ts = resume_tag or datetime.now().strftime("%Y%m%d-%H%M%S")
    if resume_tag:
        log(f"resume: reusing work tag {ts}")

    audio = audio_raw if audio_prepped else prep_audio_bytedance_style(audio_raw, work)
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

    _, chunks = compute_bytedance_chunks(audio)
    log(
        f"§8.5 segment split: {len(chunks)} chunks "
        f"(max {BYTEDANCE_MAX_CHUNK_S}s, chain={chain_chunks})"
    )

    prebuilt_gaps = load_existing_gaps(work) if resume_tag else {}
    if not prebuilt_gaps:
        prebuilt_gaps = ensure_timeline_gaps(chunks, base_video, work, ts)
    elif len(prebuilt_gaps) < len(chunks):
        prebuilt_gaps = ensure_timeline_gaps(
            chunks, base_video, work, ts, prebuilt_gaps,
        )
    chain_log: list[dict] = []
    seg_paths: list[Path] = []
    skipped = 0

    for i, (t0, t1) in enumerate(chunks):
        chunk_dur = t1 - t0
        existing = find_existing_seg_trim(work, i) if resume else None
        if existing is not None:
            seg_paths.append(existing)
            skipped += 1
            sidecar = sorted(work.glob(f"seg_{i}_chain_*.json"))
            if sidecar:
                chain_log.append(json.loads(sidecar[-1].read_text()))
            else:
                chain_log.append({
                    "chunk_index": i,
                    "resumed": True,
                    "output": existing.name,
                })
            log(f"  chunk {i + 1}/{len(chunks)}: RESUME {existing.name}")
            continue

        seg_audio = work / f"seg_{i}_{ts}.mp3"
        extract_audio_segment(audio, seg_audio, t0, t1)
        target_s = chunk_dur + VIDEO_TRIM_TAILROOM_S
        looped = work / f"seg_{i}_fwd_{ts}.mp4"
        chain_source = "idle_base_forward_loop"
        chain_gap_key: str | int | None = None

        if chain_chunks and i == 0 and "lead" in prebuilt_gaps:
            build_chained_video_from_gap_end(prebuilt_gaps["lead"], target_s, looped)
            chain_source = "gap_lead_tail"
            chain_gap_key = "lead"
        elif chain_chunks and i > 0 and (i - 1) in prebuilt_gaps:
            build_chained_video_from_gap_end(prebuilt_gaps[i - 1], target_s, looped)
            chain_source = f"gap_{i - 1}_tail"
            chain_gap_key = i - 1
        else:
            forward_loop(base_video, looped, target_s)

        trimmed = work / f"seg_{i}_trim_{ts}.mp4"
        trim_video_for_lipsync(looped, trimmed, chunk_dur, trim_start=0.0)
        seg_raw = work / f"seg_{i}_bd_{ts}.mp4"
        log(f"  chunk {i + 1}/{len(chunks)}: {t0:.1f}-{t1:.1f}s ({chunk_dur:.1f}s)")
        run_bytedance_lipsync(trimmed, seg_audio, seg_raw)
        seg_trimmed = work / f"seg_{i}_bd_trim_{ts}.mp4"
        trim_padded_lipsync_segment(seg_raw, seg_trimmed, chunk_dur)
        seg_paths.append(seg_trimmed)

        chain_entry = {
            "chunk_index": i,
            "timeline_s": [round(t0, 3), round(t1, 3)],
            "speech_duration_s": round(chunk_dur, 3),
            "chain_source": chain_source,
            "chain_gap_key": chain_gap_key,
            "chain_enabled": chain_chunks,
            "video_seed": looped.name,
            "output": seg_trimmed.name,
        }
        chain_log.append(chain_entry)
        (work / f"seg_{i}_chain_{ts}.json").write_text(
            json.dumps(chain_entry, indent=2) + "\n", encoding="utf-8",
        )

    pieces = build_pieces_with_timeline_gaps(
        seg_paths, chunks, base_video, work, ts, prebuilt_gaps=prebuilt_gaps,
    )
    concat_videos(pieces, out_path)
    log(f"segmented lipsync: {len(seg_paths)} chunks + gaps -> {out_path.name}")

    chain_manifest = {
        "chain_chunks": chain_chunks,
        "chunk_count": len(chunks),
        "gap_clip_count": len(prebuilt_gaps),
        "gap_keys": sorted(prebuilt_gaps.keys(), key=str),
        "chunks": chain_log,
        "resumed_chunks": skipped,
        "work_tag": ts,
    }
    (work / f"chain_manifest_{ts}.json").write_text(
        json.dumps(chain_manifest, indent=2) + "\n", encoding="utf-8",
    )

    if out_meta is not None:
        out_meta.update({
            "timeline_gaps_preserved": True,
            "chained_chunks": chain_chunks,
            "chunk_count": len(chunks),
            "gap_insert_count": len(pieces) - len(seg_paths),
            "gap_clip_count": len(prebuilt_gaps),
            "prepped_audio_duration_s": round(audio_dur, 3),
            "chain_manifest": f"chain_manifest_{ts}.json",
            "resumed_chunks": skipped,
        })
    return out_path

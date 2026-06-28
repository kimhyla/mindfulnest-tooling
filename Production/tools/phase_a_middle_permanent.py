#!/usr/bin/env python3
"""Permanent Phase A middle — ByteDance LatentSync on element-bound idle base.

Kling LipSync full-body-regenerates bird wings into gesture hands on excited
speech. ByteDance syncs the face only and preserves base wing pixels.

Canonical entry: scripts/run_phase_a_permanent.py
State method key: base_clip_bytedance_tight_v1
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(HERE))

from phase_a_av_post import (  # noqa: E402
    av_duration_gap,
    ensure_stem_duration_floor,
    pad_video_to_match_audio,
    trim_av_lead_in,
    trim_av_trailing_silence,
    upscale_lipsync_to_bookend,
)
from phase_a_chipper_bytedance_lipsync import (  # noqa: E402
    reconcat_bytedance_segments_with_gaps,
    run_bytedance_tight_lipsync,
)
from phase_a_chipper_kling_lipsync import resolve_lipsync_base  # noqa: E402
from phase_a_chipper_lipsync_base import (  # noqa: E402
    ARLO_ELEMENT_ID,
    DEFAULT_CLIP_ID,
    assert_arlo_element,
)
from production_server import _ffprobe_duration, _silcomp_audio  # noqa: E402

METHOD = "base_clip_bytedance_tight_v1"
METHOD_CHAINED = "base_clip_bytedance_chained_v1"
PROMOTED_BASE_MD5 = "c6ecba216b0a412b34fadbe90d0c1387"
JUN7_CLAW_MD5 = "194a970c8eb17901895c16ee3187dba1"
QA_TIMES_S = (12, 15, 17, 19, 22, 38)


def log(msg: str) -> None:
    print(f"[phase_a_permanent] {msg}", flush=True)


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight(prod: Path, event: Path, bases: Path, state: dict) -> dict:
    """Hard gates before any middle generation."""
    arlo = assert_arlo_element(prod)
    clip_id = state.get("phase_a_chipper_sitting_clip_id") or DEFAULT_CLIP_ID
    base = resolve_lipsync_base(bases, clip_id)
    base_md5 = md5(base)

    if base_md5 == JUN7_CLAW_MD5:
        raise RuntimeError(
            f"FATAL: base {base.name} is jun7 claw archive ({JUN7_CLAW_MD5}) — promote fresh v1 first"
        )
    if base_md5 != PROMOTED_BASE_MD5 and not str(clip_id).startswith("arlo_"):
        log(f"WARNING: base md5 {base_md5} != promoted canonical {PROMOTED_BASE_MD5}")

    audio_name = state.get("phase_a_voice_stem_file")
    if not audio_name:
        raise RuntimeError("FATAL: phase_a_voice_stem_file unset")
    audio = event / audio_name
    if not audio.is_file():
        raise RuntimeError(f"FATAL: voice stem missing: {audio}")

    flyin = state.get("phase_a_flyin_file")
    flyout = state.get("phase_a_flyout_file")
    # Bookends optional after Arlo migration (2026-06) — middle-only stitch.

    return {
        "clip_id": clip_id,
        "base_path": str(base),
        "base_md5": base_md5,
        "base_promoted_ok": base_md5 == PROMOTED_BASE_MD5,
        "audio": audio_name,
        "element_id": arlo.get("element_id"),
        "element_id_ok": str(arlo.get("element_id")) == ARLO_ELEMENT_ID,
        "flyin": flyin,
        "flyout": flyout,
        "bookends_required": False,
        "method": METHOD,
    }


def extract_qa_frames(video: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for t in QA_TIMES_S:
        dst = out_dir / f"lipsync_t{int(t)}s.png"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(t), "-i", str(video), "-frames:v", "1", str(dst),
        ], check=True)


def run_phase_a_base_clip_bytedance_lipsync(
    base_video: Path,
    audio_raw: Path,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
    chain_chunks: bool = False,
    single_pass: bool = True,
    resume: bool = False,
) -> dict:
    """Middle segment: ByteDance on promoted base + miracle bookend post."""
    base_video = base_video.expanduser().resolve()
    audio_raw = audio_raw.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    work = tmp_dir or (out_path.parent / "_tmp_phase_a_permanent")
    work.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log(f"base clip: {base_video.name} md5={md5(base_video)}")
    log(f"audio: {audio_raw.name}")
    log(
        "middle: ByteDance LatentSync (NOT Kling LipSync — preserves wing pixels)"
        + (", single-pass ON" if single_pass else ", single-pass OFF")
        + (", chained chunks ON" if chain_chunks else "")
    )

    raw_dur = _ffprobe_duration(audio_raw)
    tmp_audio = work / f"prepped_audio_{ts}.mp3"
    audio_for_lipsync, audio_proc_meta = _silcomp_audio(
        audio_raw,
        tmp_audio,
        loudnorm=True,
        auto_preroll=True,
        max_audio_s=raw_dur + 2.0,
    )
    pr = audio_proc_meta.get("preroll_processing") or {}
    preroll_s = float(pr.get("preroll_added_s") or 0.0)

    bd_raw = work / f"bytedance_raw_{tag}.mp4"
    bd_meta: dict = {}
    run_bytedance_tight_lipsync(
        base_video,
        audio_for_lipsync,
        bd_raw,
        tmp_dir=work / "bytedance_work",
        audio_prepped=True,
        out_meta=bd_meta,
        chain_chunks=chain_chunks,
        single_pass=single_pass,
        resume=resume,
    )

    bd_up = work / f"bytedance_bookend_{tag}.mp4"
    upscale_lipsync_to_bookend(bd_raw, bd_up)

    padded = work / f"bytedance_padded_{tag}.mp4"
    _, pad_s = pad_video_to_match_audio(bd_up, padded)
    # Leading preroll is already a timeline gap clip — do not trim again.
    lead_trim_s = 0.0 if bd_meta.get("timeline_gaps_preserved") else preroll_s
    lead_out = work / f"bytedance_lead_{tag}.mp4"
    trim_av_lead_in(padded, lead_out, lead_trim_s)
    lead_dur = _ffprobe_duration(lead_out)
    max_trail_trim = max(0.0, lead_dur - raw_dur)
    trimmed_tmp = work / f"bytedance_tailed_{tag}.mp4"
    _, trail_trim_s = trim_av_trailing_silence(
        lead_out,
        trimmed_tmp,
        max_trim_s=max_trail_trim,
    )
    _, stem_pad_s = ensure_stem_duration_floor(trimmed_tmp, out_path, raw_dur)

    sys.path.insert(0, str(HERE / "credentials_lib"))
    from ffmpeg_stitch import rebase_mp4_stream_start_times  # noqa: E402

    rebase_mp4_stream_start_times(out_path)

    v_final, a_final, gap_final = av_duration_gap(out_path)
    method_key = METHOD_CHAINED if chain_chunks else METHOD
    manifest = {
        "pipeline": "phase_a_base_clip_bytedance_tight",
        "base_clip": base_video.name,
        "base_md5": md5(base_video),
        "audio_source": audio_raw.name,
        "stem_duration_s": round(raw_dur, 3),
        "preroll_added_s": round(preroll_s, 3),
        "lead_trim_s": round(lead_trim_s, 3),
        "trailing_trim_s": round(trail_trim_s, 3),
        "stem_floor_pad_s": round(stem_pad_s, 3),
        "timeline_gaps_preserved": bd_meta.get("timeline_gaps_preserved", False),
        "chained_chunks": bd_meta.get("chained_chunks", chain_chunks),
        "single_pass": bd_meta.get("single_pass", single_pass),
        "gap_insert_count": bd_meta.get("gap_insert_count", 0),
        "gap_clip_count": bd_meta.get("gap_clip_count", 0),
        "chunk_count": bd_meta.get("chunk_count", 1),
        "chain_manifest": bd_meta.get("chain_manifest"),
        "prepped_audio_duration_s": bd_meta.get(
            "prepped_audio_duration_s", round(_ffprobe_duration(audio_for_lipsync), 3),
        ),
        "video_pad_s": round(pad_s, 3),
        "final_av_gap_s": round(gap_final, 3),
        "output": out_path.name,
        "method": method_key,
        "zoom": False,
        "upscale_bookend": True,
        "bookend_resolution": "1660x1244",
        "kling_lipsync": False,
        "note": "Permanent middle — ByteDance face-sync only; no Kling LipSync body regen",
    }
    out_path.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    log(f"DONE permanent middle → {out_path.name} (v={v_final:.2f}s a={a_final:.2f}s)")
    return manifest


def complete_run_dir(
    run_dir: Path,
    event: Path,
    prod: Path,
    state: dict,
    *,
    stitch: bool = True,
) -> dict:
    """Stitch, QA frames, audit — for supervisor after middle exists."""
    run_dir = run_dir.expanduser().resolve()
    stem = run_dir.name.replace("phase_a_permanent_", "")
    lipsync_candidates = sorted(run_dir.glob(f"phase_a_lipsync_{stem}.mp4"))
    if not lipsync_candidates:
        raise FileNotFoundError(f"middle lipsync missing in {run_dir}")
    lipsync_out = lipsync_candidates[-1]

    result: dict = {"lipsync": lipsync_out.name, "run_dir": run_dir.name}
    if stitch:
        ts = stem
        stitched_path = stitch_phase_a(event, prod, state, lipsync_out, ts)
        extract_qa_frames(stitched_path, run_dir / "frames_stitched")
        result["stitched"] = stitched_path.name
        result["stitched_path"] = str(stitched_path)

    extract_qa_frames(lipsync_out, run_dir / "frames")
    return result


def rebuild_middle_with_timeline_gaps(
    run_dir: Path,
    *,
    out_suffix: str = "gaps",
) -> dict:
    """Re-stitch middle from saved ByteDance trim segments + idle gap clips."""
    run_dir = run_dir.expanduser().resolve()
    tmp = run_dir / "_tmp_middle"
    work = tmp / "bytedance_work"
    prepped = next(tmp.glob("prepped_audio_*.mp3"), None)
    if not prepped or not prepped.is_file():
        raise FileNotFoundError(f"prepped audio missing under {tmp}")

    state_path = run_dir.parent / "production_state.json"
    clip_id = "chipper_idle_element_v1"
    if state_path.is_file():
        st = json.loads(state_path.read_text())
        clip_id = st.get("phase_a_chipper_sitting_clip_id") or clip_id
    bases = run_dir.parent.parent / "assets/lipsync_bases"
    base = resolve_lipsync_base(bases, clip_id)

    segs = sorted(work.glob("seg_*_bd_*.mp4"))
    segs = [p for p in segs if "_bd_trim_" not in p.name]
    if not segs:
        raise FileNotFoundError(f"raw bd segments missing under {work}")

    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rebuild_dir = run_dir / f"_rebuild_{out_suffix}"
    rebuild_dir.mkdir(parents=True, exist_ok=True)

    bd_raw = rebuild_dir / f"bytedance_concat_{out_suffix}.mp4"
    gap_meta = reconcat_bytedance_segments_with_gaps(
        base,
        prepped,
        None,
        bd_raw,
        tmp_dir=rebuild_dir / "gap_work",
        segments_work=work,
    )

    bd_up = rebuild_dir / f"bytedance_bookend_{out_suffix}.mp4"
    upscale_lipsync_to_bookend(bd_raw, bd_up)
    padded = rebuild_dir / f"bytedance_padded_{out_suffix}.mp4"
    _, pad_s = pad_video_to_match_audio(bd_up, padded)

    stem = run_dir.name.replace("phase_a_permanent_", "")
    out_path = run_dir / f"phase_a_lipsync_{stem}_{out_suffix}.mp4"
    trim_av_lead_in(padded, out_path, 0.0)
    _, trail_trim_s = trim_av_trailing_silence(out_path, out_path)

    v_final, a_final, gap_final = av_duration_gap(out_path)
    manifest = {
        "rebuild": True,
        "source_run": run_dir.name,
        "segment_count": len(segs),
        **gap_meta,
        "lead_trim_s": 0.0,
        "trailing_trim_s": round(trail_trim_s, 3),
        "video_pad_s": round(pad_s, 3),
        "final_av_gap_s": round(gap_final, 3),
        "output": out_path.name,
        "method": METHOD,
    }
    (rebuild_dir / f"rebuild_{out_suffix}.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    log(
        f"REBUILD gaps -> {out_path.name} "
        f"(v={v_final:.2f}s a={a_final:.2f}s prepped={gap_meta.get('prepped_audio_duration_s')}s)"
    )
    return manifest


def stitch_phase_a(
    event: Path,
    prod: Path,
    state: dict,
    lipsync: Path,
    ts: str,
) -> Path:
    """Middle lipsync + ambient bed only (no fly-in/fly-out bookends)."""
    from ffmpeg_stitch import normalize_for_concat

    ambient_id = state.get("phase_a_ambient_preset_id", "meditation_pretty_v1")
    ambient = prod / "assets/ambient_library" / f"{ambient_id}.mp3"

    norm_dir = event / f"_norm_permanent_{ts}"
    norm_dir.mkdir(parents=True, exist_ok=True)
    raw_n = norm_dir / "lipsync.mp4"
    normalize_for_concat(lipsync, raw_n)
    intermediate = raw_n
    stitched = event / f"phase_a_stitched_{ts}.mp4"

    if ambient.is_file():
        total = _ffprobe_duration(intermediate)
        fc = f"[1:a]atrim=0:{total:.3f},volume=0.15[bed];[0:a][bed]amix=inputs=2:duration=first:normalize=0[aout]"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(intermediate), "-stream_loop", "-1", "-i", str(ambient),
            "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart", str(stitched),
        ], check=True, timeout=180)
    else:
        subprocess.run(["cp", str(intermediate), str(stitched)], check=True)

    return stitched

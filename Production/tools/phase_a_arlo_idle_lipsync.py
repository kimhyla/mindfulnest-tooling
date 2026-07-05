#!/usr/bin/env python3
"""Phase A Arlo lipsync — Kling start+end same still → crossfade loop → Kling LipSync.

Kim 2026-07-05: canonical Phase A route for all events. Arlo Element binding +
gaze-forward idle prompt; delivery encode runs in handle_phase_a_lipsync terminal.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
)
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_arlo_contract import resolve_phase_a_arlo_idle_still  # noqa: E402
from phase_a_arlo_lipsync_base import (  # noqa: E402
    ARLO_STILL_PROMPT,
    NEGATIVE,
    assert_arlo_element,
)
from phase_a_av_post import (  # noqa: E402
    DEFAULT_FPS,
    av_duration_gap,
    crossfade_loop_video,
    pad_video_to_match_audio,
    trim_av_lead_in,
)
from production_server import (  # noqa: E402
    KLING_MAX_DURATION_SEC,
    KLING_MIN_DURATION_SEC,
    _AUDIO_SHORT_THRESHOLD_SEC,
    _VIDEO_TRIM_TAILROOM_TARGET_S,
    _ffprobe_duration,
    _silcomp_audio,
    _trim_video_to_audio,
)

METHOD = "idle_kling_lipsync_startend_still"
PIPELINE = "phase_a_arlo_idle_kling_startend_still_v1"


def log(msg: str) -> None:
    print(f"[phase_a_arlo_idle] {msg}", flush=True)


def _kling_idle_duration(audio_duration: float) -> int:
    if audio_duration <= _AUDIO_SHORT_THRESHOLD_SEC:
        return KLING_MIN_DURATION_SEC
    return KLING_MAX_DURATION_SEC


def _still_to_startend_uri(still: Path) -> tuple[str, str]:
    raw = still.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
    return uri, info


def run_phase_a_arlo_idle_lipsync_startend_still(
    audio_raw: Path,
    out_path: Path,
    *,
    event_dir: Path,
    prod_root: Path,
    still: Path | None = None,
    tmp_dir: Path | None = None,
) -> dict:
    """Full Phase A Arlo lipsync: still bookend idle → loop → Kling LipSync → A/V trim."""
    audio_raw = audio_raw.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    event_dir = event_dir.expanduser().resolve()
    prod_root = prod_root.expanduser().resolve()
    still_path = still or resolve_phase_a_arlo_idle_still(event_dir, prod_root)
    work = tmp_dir or (event_dir / "_tmp_phase_a_arlo_startend")
    work.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log(f"still: {still_path.name}")
    log(f"audio: {audio_raw.name}")
    log(f"mode: start_end_same_still ({METHOD})")

    start_uri, still_info = _still_to_startend_uri(still_path)
    log(f"still prep: {still_info}")

    raw_dur = _ffprobe_duration(audio_raw)
    tmp_audio = work / f"audio_prep_{ts}.mp3"
    audio_for_lipsync, audio_meta = _silcomp_audio(
        audio_raw,
        tmp_audio,
        loudnorm=True,
        auto_preroll=True,
        max_audio_s=raw_dur + 2.0,
    )
    preroll_s = float((audio_meta.get("preroll_processing") or {}).get("preroll_added_s") or 0.0)
    audio_dur = float(
        audio_meta.get("compressed_duration_s") or _ffprobe_duration(audio_for_lipsync)
    )
    kling_dur = _kling_idle_duration(audio_dur)

    keys = load_api_keys()
    arlo = assert_arlo_element(prod_root)
    element = {
        "element_id": str(arlo["element_id"]),
        "element_name": arlo.get("element_name", "Arlo"),
    }
    log(f"element={element['element_id']} idle_duration={kling_dur}s")

    task_id = kling_startend_submit(
        start_b64_uri=start_uri,
        end_b64_uri=start_uri,
        prompt=ARLO_STILL_PROMPT,
        negative_prompt=NEGATIVE,
        duration=kling_dur,
        api_key=keys["wavespeed"],
        element_entry=element,
    )
    log(f"kling idle submitted task_id={task_id}")
    result = kling_poll_fresh(task_id, keys["wavespeed"], timeout_s=900)
    if (result.get("status") or "").lower() != "completed":
        raise RuntimeError(f"Kling idle failed: {result}")
    url = (result.get("outputs") or [None])[0]
    if not url:
        raise RuntimeError("Kling idle returned no output URL")

    idle = work / f"idle_startend_{tag}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(idle), url], check=True, timeout=180)
    log(
        f"idle from still: {_ffprobe_duration(idle):.1f}s "
        f"{idle.stat().st_size / 1024 / 1024:.1f}MB"
    )

    target_s = audio_dur + _VIDEO_TRIM_TAILROOM_TARGET_S
    looped = work / f"idle_looped_{tag}.mp4"
    crossfade_loop_video(idle, looped, target_s, fps=DEFAULT_FPS)
    trimmed = work / f"idle_trimmed_{tag}.mp4"
    video_for_lipsync, trimmed_to, _, _ = _trim_video_to_audio(
        looped, trimmed, audio_dur, trim_start=0.0, trim_end=None,
    )
    log(f"looped+trimmed video: {trimmed_to:.2f}s for audio {audio_dur:.2f}s")

    client = LipSyncClient(keys["wavespeed"])
    ls_id = client.submit(video_for_lipsync, audio_for_lipsync)
    log(f"lipsync submitted task_id={ls_id}")
    ls_result = client.poll_until_done(ls_id)
    if (ls_result.get("status") or "").lower() != "completed" or not ls_result.get("outputs"):
        raise RuntimeError(f"Kling LipSync failed: {ls_result}")

    ls_raw = work / f"lipsync_raw_{tag}.mp4"
    client.download(ls_result["outputs"][0], ls_raw)
    padded = work / f"lipsync_padded_{tag}.mp4"
    _, pad_s = pad_video_to_match_audio(ls_raw, padded)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trim_av_lead_in(padded, out_path, preroll_s)

    v_final, a_final, gap_final = av_duration_gap(out_path)
    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline": PIPELINE,
        "still": still_path.name,
        "still_prep": still_info,
        "audio_source": audio_raw.name,
        "audio_duration_s": round(audio_dur, 3),
        "preroll_added_s": round(preroll_s, 3),
        "kling_idle_duration_s": kling_dur,
        "trimmed_video_s": round(trimmed_to, 3),
        "video_pad_s": round(pad_s, 3),
        "final_video_s": round(v_final, 3),
        "final_audio_s": round(a_final, 3),
        "final_av_gap_s": round(gap_final, 3),
        "output": out_path.name,
        "method": METHOD,
        "element_id": element["element_id"],
        "prompt_head": ARLO_STILL_PROMPT[:120],
    }
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"DONE → {out_path.name} (v={v_final:.2f}s a={a_final:.2f}s gap={gap_final:.3f}s)")
    return manifest

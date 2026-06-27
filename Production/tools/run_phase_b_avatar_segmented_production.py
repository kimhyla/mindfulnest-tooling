#!/usr/bin/env python3
"""DEPRECATED operator tool — pause-aligned Avatar chunk assembly with gap holds.

Phase B tab production route is single full-stem Avatar Pro only
(``handle_phase_b_lipsync`` + ``run_phase_b_avatar_full_stem_production.py``).
Do not use for new Event work — gap holds freeze picture during meditation pauses.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from kling_startend_pipeline import (  # noqa: E402
    kling_poll_fresh,
    load_api_keys,
    log,
)
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_chipper_bytedance_lipsync import extract_audio_segment, ffprobe_duration  # noqa: E402
from phase_b_avatar_lipsync import (  # noqa: E402
    PHASE_B_AVATAR_ROUTE_CODE,
    STATIC_BG_PROMPT,
    estimate_avatar_pro_usd,
    resolve_phase_b_cedric_still,
)
from phase_b_kling_segmented_lipsync import (  # noqa: E402
    PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
    compute_phase_b_kling_segments,
)
from phase_b_segmented_timeline_assemble import (  # noqa: E402
    PHASE_B_SEGMENTED_TIMELINE_GAP_XFADE_V2,
    assemble_segmented_timeline,
)
from phase_module_lipsync_delivery import finalize_phase_module_lipsync_delivery  # noqa: E402

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _submit_avatar(client: LipSyncClient, still: Path, audio: Path, prompt: str) -> str:
    """Deprecated segmented path — must share ``submit_avatar_pro`` still prep."""
    log(f"[avatar_seg] still {still.name}")
    task_id = client.submit_avatar_pro(still, audio, prompt)
    log(f"[avatar_seg] submitted task_id={task_id}")
    return task_id


def _install_chunk_raw(
    src: Path,
    work_dir: Path,
    *,
    index: int,
    start_s: float,
    end_s: float,
    task_id: str | None = None,
    source_output: str | None = None,
) -> Path:
    dest = work_dir / f"seg_{index}_kling_raw.mp4"
    shutil.copy2(src, dest)
    meta = {
        "code": PHASE_B_AVATAR_ROUTE_CODE,
        "route": "kling-v2-ai-avatar-pro",
        "index": index,
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": round(end_s - start_s, 6),
        "raw_path": dest.name,
        "task_id": task_id,
        "source_output": source_output or src.name,
    }
    (work_dir / f"seg_{index}_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def _run_chunk_avatar(
    client: LipSyncClient,
    still: Path,
    full_audio: Path,
    work_dir: Path,
    *,
    index: int,
    start_s: float,
    end_s: float,
    prompt: str,
) -> Path:
    chunk_audio = work_dir / f"seg_{index}_audio.mp3"
    extract_audio_segment(full_audio, chunk_audio, start_s, end_s)
    audio_dur = ffprobe_duration(chunk_audio)
    log(f"[avatar_seg] chunk {index}: {start_s:.3f}-{end_s:.3f}s ({audio_dur:.3f}s)")
    est = estimate_avatar_pro_usd(audio_dur)
    log(f"[avatar_seg] chunk {index} est ${est:.2f}")

    task_id = _submit_avatar(client, still, chunk_audio, prompt)
    result = kling_poll_fresh(task_id, client.api_key, timeout_s=3600)
    if (result.get("status") or "").lower() != "completed":
        raise RuntimeError(f"Avatar chunk {index} failed: {result}")
    url = (result.get("outputs") or [None])[0]
    if not url:
        raise RuntimeError(f"Avatar chunk {index} completed with no output: {result}")

    raw = work_dir / f"seg_{index}_avatar_raw.mp4"
    client.download(url, raw)
    delivered = work_dir / f"seg_{index}_avatar_delivered.mp4"
    shutil.copy2(raw, delivered)
    finalize_phase_module_lipsync_delivery(delivered, sharpen=True)
    return _install_chunk_raw(
        delivered,
        work_dir,
        index=index,
        start_s=start_s,
        end_s=end_s,
        task_id=task_id,
        source_output=delivered.name,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event-dir", type=Path, required=True)
    p.add_argument(
        "--chunk0-mp4",
        type=Path,
        required=True,
        help="Operator-approved Avatar chunk 0 MP4 on disk",
    )
    p.add_argument("--first-chunk", type=int, default=1, help="First chunk index to generate (default 1)")
    p.add_argument("--last-chunk", type=int, default=-1, help="Last chunk index inclusive (-1 = all)")
    p.add_argument("--prompt", default=STATIC_BG_PROMPT)
    p.add_argument("--assemble-only", action="store_true", help="Skip Avatar jobs; assemble existing work dir")
    p.add_argument("--work-dir", type=Path, help="Existing work dir (assemble-only or resume)")
    p.add_argument("--pin-preview", action="store_true", help="Pin assembled output to production_state.json")
    args = p.parse_args()

    event_dir = args.event_dir.expanduser().resolve()
    state_path = event_dir / "production_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    audio_name = state.get("phase_b_voice_stem_file")
    if not audio_name:
        raise SystemExit("phase_b_voice_stem_file unset")
    full_audio = event_dir / audio_name
    if not full_audio.is_file():
        raise SystemExit(f"audio missing: {full_audio}")

    audio_dur, specs = compute_phase_b_kling_segments(
        full_audio, strategy=PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
    )
    if not specs:
        raise SystemExit("no pause-aligned segments")
    last_idx = len(specs) - 1 if args.last_chunk < 0 else min(args.last_chunk, len(specs) - 1)

    ts = _ts()
    work_dir = (args.work_dir or (event_dir / f"_work_avatar_segmented_{ts}")).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    chunk0_backup_name: str | None = None

    if not args.assemble_only:
        chunk0 = args.chunk0_mp4.expanduser().resolve()
        if not chunk0.is_file():
            raise SystemExit(f"chunk0 missing: {chunk0}")

        backup_dir = event_dir / ".backups" / "avatar_approved"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_name = f"chunk0_pinned_{ts}_{chunk0.name}"
        backup_path = backup_dir / backup_name
        shutil.copy2(chunk0, backup_path)
        chunk0_backup_name = backup_name
        if chunk0.with_suffix(".json").is_file():
            shutil.copy2(chunk0.with_suffix(".json"), backup_dir / backup_name.replace(".mp4", ".json"))
        log(f"[avatar_seg] backed up chunk0 → {backup_path.name}")

        spec0 = specs[0]
        _install_chunk_raw(
            chunk0,
            work_dir,
            index=0,
            start_s=spec0.start_s,
            end_s=spec0.end_s,
            source_output=chunk0.name,
        )

        still = resolve_phase_b_cedric_still(event_dir.parent)
        keys = load_api_keys()
        client = LipSyncClient(keys["wavespeed"])

        for spec in specs:
            if spec.index < args.first_chunk or spec.index > last_idx:
                continue
            if spec.index == 0:
                continue
            raw_path = work_dir / f"seg_{spec.index}_kling_raw.mp4"
            if raw_path.is_file():
                log(f"[avatar_seg] chunk {spec.index} already present — skip")
                continue
            _run_chunk_avatar(
                client,
                still,
                full_audio,
                work_dir,
                index=spec.index,
                start_s=spec.start_s,
                end_s=spec.end_s,
                prompt=args.prompt,
            )

    missing = [
        i for i in range(len(specs))
        if not (work_dir / f"seg_{i}_kling_raw.mp4").is_file()
    ]
    if missing:
        raise SystemExit(f"work dir missing chunks: {missing}")

    out_name = f"phase_b_lipsync_{ts}_avatar_segmented_timeline_xfade.mp4"
    out_path = event_dir / out_name
    log(f"[avatar_seg] assembling timeline → {out_name}")
    manifest = assemble_segmented_timeline(work_dir, full_audio, out_path)
    manifest["avatar_route"] = PHASE_B_AVATAR_ROUTE_CODE
    if chunk0_backup_name:
        manifest["chunk0_backup"] = chunk0_backup_name
    manifest_path = out_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "output": out_name,
                "work_dir": work_dir.name,
                "audio_duration_s": manifest.get("audio_duration_s"),
                "video_duration_s": manifest.get("video_duration_s"),
                "chunk_count": manifest.get("chunk_count"),
            }
        ),
        flush=True,
    )

    if args.pin_preview:
        backup = event_dir / ".backups" / "state" / f"{ts}_pre_avatar_timeline_pin.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_path, backup)
        state["phase_b_lipsync_file"] = out_name
        state["phase_b_lipsync_mtime"] = int(os.path.getmtime(str(out_path)))
        state["phase_b_lipsync_status"] = "done"
        state["phase_b_lipsync_method"] = "kling_avatar_pro_v1"
        state["phase_b_lipsync_requires_regen"] = False
        state["phase_b_lipsync_segmented_timeline"] = {
            "code": PHASE_B_SEGMENTED_TIMELINE_GAP_XFADE_V2,
            "avatar_route": PHASE_B_AVATAR_ROUTE_CODE,
            "source_work_dir": work_dir.name,
            "manifest": manifest_path.name,
            "chunk0_source": args.chunk0_mp4.name,
            "pinned_at": ts,
        }
        state["phase_b_avatar_segmented"] = {
            "code": PHASE_B_AVATAR_ROUTE_CODE,
            "work_dir": work_dir.name,
            "chunk0_approved": args.chunk0_mp4.name,
            "chunk_count": len(specs),
        }
        nested = state.setdefault("phase_b", {})
        if isinstance(nested, dict):
            for key in (
                "phase_b_voice_stem_file",
                "phase_b_voice_stem_mtime",
                "phase_b_lipsync_file",
                "phase_b_lipsync_mtime",
                "phase_b_lipsync_status",
                "phase_b_lipsync_method",
                "phase_b_lipsync_requires_regen",
                "phase_b_lipsync_delivery_profile",
                "phase_b_lipsync_delivery_recipe",
                "phase_b_lipsync_segmented_timeline",
                "phase_b_avatar_segmented",
            ):
                if key in state:
                    nested[key] = state[key]
            nested["phase_b_lipsync_requires_regen"] = False
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        log(f"[avatar_seg] pinned preview → {out_name}")

    log(f"[avatar_seg] done {out_path}")
    print(out_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

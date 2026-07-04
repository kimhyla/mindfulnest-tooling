"""Phase B segmented Kling lipsync — reset temporal drift on long Cedric meditations.

PHASE_B_KLING_SEGMENTED_LIPSYNC_V1: split voice stem at silence into ≤28s chunks,
crossfade-loop base per chunk, one Kling job each, concat, then delivery encode.
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

from ffmpeg_stitch import concat_with_xfade_clips  # noqa: E402
from kling_startend_pipeline import load_api_keys  # noqa: E402
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_chipper_bytedance_lipsync import (  # noqa: E402
    chunk_audio_for_bytedance,
    extract_audio_segment,
    ffprobe_duration,
)
from phase_b_kling_base_prep import prep_phase_b_kling_base_video  # noqa: E402
from phase_b_kling_pause_aligned_segments import (  # noqa: E402
    PHASE_B_CEDRIC_BASE_15S_CLIP_ID,
    PHASE_B_KLING_PAUSE_ALIGNED_MAX_S,
    PHASE_B_KLING_PAUSE_ALIGNED_V2,
    compute_pause_aligned_segments,
    chunk_audio_pause_aligned,
)
from phase_module_lipsync_delivery import (  # noqa: E402
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2,
    finalize_phase_module_lipsync_delivery,
)

def _detect_silences(audio_path: Path) -> list[tuple[float, float]]:
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import production_server as ps  # noqa: WPS433

    return ps._detect_silences(audio_path)

PHASE_B_KLING_SEGMENTED_LIPSYNC_V1 = "PHASE_B_KLING_SEGMENTED_LIPSYNC_V1"
KLING_SEGMENT_MAX_S = 28.0
PHASE_B_KLING_SINGLE_PASS_MAX_S = 30.0
PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED = "pause_aligned_v2"
PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY = "legacy_28s"
VIDEO_TAILROOM_S = 2.0


@dataclass(frozen=True)
class SegmentSpec:
    index: int
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def resolve_phase_b_segmented_base_clip(bases_dir: Path, clip_id: str) -> Path:
    """Prefer 15s v4 base for pause-aligned segmented lipsync when present."""
    v4 = bases_dir / f"{PHASE_B_CEDRIC_BASE_15S_CLIP_ID}.mp4"
    if v4.is_file():
        return v4
    for ext in ("mp4", "mov"):
        candidate = bases_dir / f"{clip_id}.{ext}"
        if candidate.is_file():
            return candidate
    raw = bases_dir / clip_id
    if raw.is_file():
        return raw
    raise FileNotFoundError(f"Phase B base clip not found: {clip_id} in {bases_dir}")


def compute_phase_b_kling_segments(
    audio: Path,
    *,
    strategy: str = PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
) -> tuple[float, list[SegmentSpec]]:
    audio_dur = ffprobe_duration(audio)
    silences = _detect_silences(audio)
    if strategy == PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY:
        windows = chunk_audio_for_bytedance(
            audio_dur, silences, max_chunk_s=KLING_SEGMENT_MAX_S,
        )
        code = PHASE_B_KLING_SEGMENTED_LIPSYNC_V1
    else:
        windows = chunk_audio_pause_aligned(audio_dur, silences)
        code = PHASE_B_KLING_PAUSE_ALIGNED_V2
    specs = [SegmentSpec(i, start, end) for i, (start, end) in enumerate(windows)]
    return audio_dur, specs


def _run_kling_segment(
    client: LipSyncClient,
    base_video: Path,
    audio_chunk: Path,
    work: Path,
    spec: SegmentSpec,
) -> Path:
    target_video_s = spec.duration_s + VIDEO_TAILROOM_S
    prep_work = work / f"seg_{spec.index}_kling_prep.mp4"
    video_for_kling, prep_meta = prep_phase_b_kling_base_video(
        base_video, target_video_s, prep_work,
    )
    raw_out = work / f"seg_{spec.index}_kling_raw.mp4"
    print(
        f"[phase_b_seg] chunk {spec.index + 1}: {spec.start_s:.1f}-{spec.end_s:.1f}s "
        f"({spec.duration_s:.1f}s) prep={prep_meta.get('strategy')}",
        flush=True,
    )
    job_id = client.submit(video_for_kling, audio_chunk)
    result = client.poll_until_done(job_id)
    status = (result.get("status") or "").lower()
    if status != "completed" or not result.get("outputs"):
        raise RuntimeError(f"segment {spec.index} Kling failed: {result}")
    client.download(result["outputs"][0], raw_out)
    sidecar = work / f"seg_{spec.index}_meta.json"
    sidecar.write_text(
        json.dumps({
            "job_id": job_id,
            "prep": prep_meta,
            "start_s": spec.start_s,
            "end_s": spec.end_s,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    return raw_out


def run_phase_b_kling_segmented_lipsync(
    base_video: Path,
    audio: Path,
    out_path: Path,
    *,
    work_dir: Path | None = None,
    apply_delivery: bool = True,
    segment_strategy: str = PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
) -> dict:
    """Sync segmented Kling pipeline — for experiment CLI and future server wiring."""
    base_video = base_video.expanduser().resolve()
    audio = audio.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    work = work_dir or (out_path.parent / f"_work_{out_path.stem}")
    work.mkdir(parents=True, exist_ok=True)

    audio_dur, specs = compute_phase_b_kling_segments(audio, strategy=segment_strategy)
    seg_code = (
        PHASE_B_KLING_PAUSE_ALIGNED_V2
        if segment_strategy == PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED
        else PHASE_B_KLING_SEGMENTED_LIPSYNC_V1
    )
    print(
        f"[phase_b_seg] {seg_code} strategy={segment_strategy} "
        f"audio={audio_dur:.1f}s chunks={len(specs)} "
        f"max={PHASE_B_KLING_PAUSE_ALIGNED_MAX_S if segment_strategy != PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY else KLING_SEGMENT_MAX_S}s",
        flush=True,
    )

    keys = load_api_keys()
    client = LipSyncClient(keys["wavespeed"])
    segment_paths: list[Path] = []

    for spec in specs:
        chunk_audio = work / f"seg_{spec.index}_audio.mp3"
        extract_audio_segment(audio, chunk_audio, spec.start_s, spec.end_s)
        segment_paths.append(
            _run_kling_segment(client, base_video, chunk_audio, work, spec),
        )

    concat_tmp = work / "segments_concat.mp4"
    concat_with_xfade_clips(segment_paths, concat_tmp, timeout_s=900)
    import os

    os.replace(concat_tmp, out_path)
    delivery_meta: dict = {}
    if apply_delivery:
        delivery_meta = finalize_phase_module_lipsync_delivery(
            out_path,
            sharpen=True,
            delivery_recipe=PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2,
        )

    manifest = {
        "code": seg_code,
        "segment_strategy": segment_strategy,
        "source_audio": audio.name,
        "base_video": base_video.name,
        "output": out_path.name,
        "audio_duration_s": round(audio_dur, 3),
        "chunk_count": len(specs),
        "chunks": [
            {"index": s.index, "start_s": s.start_s, "end_s": s.end_s}
            for s in specs
        ],
        "delivery_profile": delivery_meta.get("delivery_profile"),
    }
    manifest_path = out_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

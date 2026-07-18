"""Phase B segmented Kling lipsync — reset temporal drift on long Cedric meditations.

PHASE_B_KLING_SEGMENTED_LIPSYNC_V1: split voice stem at silence into ≤28s chunks,
crossfade-loop base per chunk, one Kling job each, timeline assemble (gap holds +
full stem mux), then delivery encode.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
_CRED = TOOLS / "credentials_lib"
if str(_CRED) not in sys.path:
    sys.path.insert(0, str(_CRED))

from ffmpeg_stitch import concat_with_xfade_clips, normalize_for_concat  # noqa: E402
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
    chunk_audio_pause_aligned,
)
from phase_b_segmented_timeline_assemble import (  # noqa: E402
    PHASE_B_KLING_TIMELINE_GAP_XFADE_S,
    assemble_segmented_timeline,
)
from phase_module_lipsync_delivery import (  # noqa: E402
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2,
    finalize_phase_module_lipsync_delivery,
)

PHASE_B_SEGMENTED_BASE_AUTHORITY_V1 = "PHASE_B_SEGMENTED_BASE_AUTHORITY_V1"
PHASE_B_V6_BASE_DURATION_S = 10.042
PHASE_B_V4_15S_BASE_DURATION_S = 15.042


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


def _resolve_base_clip_by_id(bases_dir: Path, clip_id: str) -> Path:
    """Resolve ``clip_id`` to a file — never silently swap to a different base."""
    for ext in ("mp4", "mov"):
        candidate = bases_dir / f"{clip_id}.{ext}"
        if candidate.is_file():
            return candidate
    raw = bases_dir / clip_id
    if raw.is_file():
        return raw
    raise FileNotFoundError(f"Phase B base clip not found: {clip_id} in {bases_dir}")


def resolve_phase_b_segmented_base_clip(
    bases_dir: Path,
    clip_id: str,
    *,
    strategy: str = PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED,
) -> Path:
    """Pause-aligned jobs may use the 15s v4 base when that clip is selected."""
    if (
        strategy == PHASE_B_KLING_SEGMENT_STRATEGY_PAUSE_ALIGNED
        and clip_id in (PHASE_B_CEDRIC_BASE_15S_CLIP_ID, "cedric_idle_newstyle_v4")
    ):
        v4 = bases_dir / f"{PHASE_B_CEDRIC_BASE_15S_CLIP_ID}.mp4"
        if v4.is_file():
            return v4
    return _resolve_base_clip_by_id(bases_dir, clip_id)


def infer_phase_b_segmented_base_clip(
    bases_dir: Path,
    clip_id: str,
    work_dir: Path,
) -> Path:
    """Resume-safe base pick — match seg_0 prep, never swap mid-job."""
    meta_path = work_dir / "seg_0_meta.json"
    if meta_path.is_file():
        try:
            prep = json.loads(meta_path.read_text(encoding="utf-8")).get("prep") or {}
            base_dur = float(prep.get("base_duration_s") or 0)
            if abs(base_dur - PHASE_B_V6_BASE_DURATION_S) < 0.5:
                return _resolve_base_clip_by_id(bases_dir, clip_id)
            if abs(base_dur - PHASE_B_V4_15S_BASE_DURATION_S) < 0.5:
                return _resolve_base_clip_by_id(
                    bases_dir, PHASE_B_CEDRIC_BASE_15S_CLIP_ID,
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return _resolve_base_clip_by_id(bases_dir, clip_id)


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
    else:
        windows = chunk_audio_pause_aligned(audio_dur, silences)
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
        base_video,
        target_video_s,
        prep_work,
        bases_dir=base_video.parent,
    )
    raw_out = work / f"seg_{spec.index}_kling_raw.mp4"
    print(
        f"[phase_b_seg] chunk {spec.index + 1}: {spec.start_s:.1f}-{spec.end_s:.1f}s "
        f"({spec.duration_s:.1f}s) prep={prep_meta.get('strategy')} "
        f"base={base_video.name}",
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
            "base_video": base_video.name,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    return raw_out


def phase_b_segmented_work_dir(event_dir: Path, pending_output: str) -> Path:
    """Work folder for a segmented job — ``_work_{stem of pending mp4}``."""
    return event_dir / f"_work_{Path(pending_output).stem}"


def count_segment_raw_clips(work_dir: Path) -> int:
    """Count completed Kling segment raws in a work directory."""
    if not work_dir.is_dir():
        return 0
    return sum(
        1
        for p in work_dir.glob("seg_*_kling_raw.mp4")
        if p.is_file() and p.stat().st_size > 100_000
    )


def phase_b_segmented_work_has_resume_progress(event_dir: Path, pending_output: str) -> bool:
    """True when a segmented job left resumable artifacts on disk."""
    work = phase_b_segmented_work_dir(event_dir, pending_output)
    if count_segment_raw_clips(work) > 0:
        return True
    return bool(list(work.glob("seg_*_audio.mp3"))) if work.is_dir() else False


def _concat_segment_raws(
    segment_paths: list[Path],
    concat_tmp: Path,
    work: Path,
    *,
    timeout_s: int = 900,
) -> None:
    """LD-284: normalize each Kling raw to canonical spec before xfade concat."""
    norm_dir = work / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)
    norm_paths: list[Path] = []
    for raw in segment_paths:
        norm_out = norm_dir / raw.name
        if not norm_out.is_file() or norm_out.stat().st_size < 100_000:
            normalize_for_concat(raw, norm_out, timeout_s=timeout_s)
        norm_paths.append(norm_out)
    concat_with_xfade_clips(norm_paths, concat_tmp, timeout_s=timeout_s)


def resume_phase_b_kling_segmented_lipsync(
    base_video: Path,
    audio: Path,
    out_path: Path,
    *,
    work_dir: Path,
    segment_strategy: str = PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY,
    client: LipSyncClient | None = None,
) -> tuple[list[Path], int]:
    """Resume segmented Kling — reuse existing ``seg_*_kling_raw.mp4`` when present."""
    base_video = base_video.expanduser().resolve()
    audio = audio.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    work = work_dir.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)

    _, specs = compute_phase_b_kling_segments(audio, strategy=segment_strategy)
    if client is None:
        client = LipSyncClient(load_api_keys()["wavespeed"])

    segment_paths: list[Path] = []
    new_jobs = 0
    for spec in specs:
        raw = work / f"seg_{spec.index}_kling_raw.mp4"
        if raw.is_file() and raw.stat().st_size > 100_000:
            print(
                f"[phase_b_seg-resume] seg_{spec.index} reuse "
                f"({raw.stat().st_size} bytes)",
                flush=True,
            )
            segment_paths.append(raw)
            continue
        chunk_audio = work / f"seg_{spec.index}_audio.mp3"
        if not chunk_audio.is_file():
            extract_audio_segment(audio, chunk_audio, spec.start_s, spec.end_s)
        print(
            f"[phase_b_seg-resume] seg_{spec.index} submit "
            f"{spec.start_s:.1f}-{spec.end_s:.1f}s base={base_video.name}",
            flush=True,
        )
        segment_paths.append(
            _run_kling_segment(client, base_video, chunk_audio, work, spec),
        )
        new_jobs += 1

    print(
        f"[phase_b_seg] timeline assemble (meditation gap holds + stem mux) "
        f"→ {out_path.name}",
        flush=True,
    )
    assemble_segmented_timeline(
        work,
        audio,
        out_path,
        apply_delivery=False,
        gap_xfade_s=PHASE_B_KLING_TIMELINE_GAP_XFADE_S,
    )
    return segment_paths, new_jobs


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
        f"max={PHASE_B_KLING_PAUSE_ALIGNED_MAX_S if segment_strategy != PHASE_B_KLING_SEGMENT_STRATEGY_LEGACY else KLING_SEGMENT_MAX_S}s "
        f"base={base_video.name}",
        flush=True,
    )

    resume_phase_b_kling_segmented_lipsync(
        base_video,
        audio,
        out_path,
        work_dir=work,
        segment_strategy=segment_strategy,
    )
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

#!/usr/bin/env python3
"""Backward-compatible Cedric wrapper for the shared layered lipsync engine."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from layered_character_lipsync import (
    CEDRIC_PROFILE,
    DEFAULT_MAX_CHUNK_SECONDS,
    PHASE_B_PATH_A_ROUTE_V1,
    Crop,
    IdleUnit as ProfileIdleUnit,
    LayeredLipsyncQCError,
    QCRegion,
    apply_chunk_boundary_padding,
    atomic_deliver,
    build_idle_track as _build_idle_track,
    composite_on_plate as _composite_on_plate,
    cut_chunks as _cut_chunks,
    detect_chunk_boundaries,
    ffprobe_duration,
    ffprobe_size,
    manifest_path_for,
    pad_concat_lipsync as _pad_concat_lipsync,
    profile_paths,
    qc_pupil_scan as _qc_pupil_scan,
    qc_still_scan as _qc_still_scan,
    resolve_production_root,
    run,
    run_layered_lipsync,
    submit_lipsync_chunks as _submit_lipsync_chunks,
    validate_assets,
    validate_provider_output,
)

TOOLS_DIR = Path(__file__).resolve().parent

# Legacy constants remain importable for the Phase B route and existing tests.
# The shared engine never uses this fallback and contains no machine path.
DROPBOX_PRODUCTION = Path(
    os.environ.get(
        "MN_PRODUCTION_ROOT",
        Path.home()
        / "Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production",
    )
)
PATH_A_PREP = DROPBOX_PRODUCTION / "NEW STYLE CHARACTERS/CEDRIC/path_a_prep"
LIPSYNC_BASES = DROPBOX_PRODUCTION / "assets/lipsync_bases"
CEDRIC_CUTOUT_BLUE_PNG = PATH_A_PREP / "cedric_cutout_blue_1280x720_v1.png"
CEDRIC_ROOM_PLATE_PNG = PATH_A_PREP / "cedric_room_plate_1280x720_v1.png"

CROP_W = CEDRIC_PROFILE.placement.width
CROP_H = CEDRIC_PROFILE.placement.height
CROP_X = CEDRIC_PROFILE.placement.x
CROP_Y = CEDRIC_PROFILE.placement.y
UNIT_DURATION = CEDRIC_PROFILE.idle_units[0].duration
XFADE_SECONDS = CEDRIC_PROFILE.xfade_seconds
LIPSYNC_OUTPUT_SIZE = CEDRIC_PROFILE.provider_output_size.ffmpeg
MAX_CHUNK_SECONDS = DEFAULT_MAX_CHUNK_SECONDS
SILENCE_DETECT_ARGS = "silencedetect=noise=-35dB:d=0.45"
LIPSYNC_POST_FILTERS = CEDRIC_PROFILE.post_filters
CHROMAKEY_BLUE = (
    f"{CEDRIC_PROFILE.chroma_filter},{CEDRIC_PROFILE.despill_filter}"
)
IDLE_BODY_CROP = CEDRIC_PROFILE.idle_body_qc.crop.ffmpeg
COMPOSITE_BODY_CROP = CEDRIC_PROFILE.composite_body_qc.crop.ffmpeg


@dataclass(frozen=True)
class IdleUnit:
    """Legacy absolute-path view of a Cedric idle unit."""

    name: str
    path: Path
    head_trim: float
    tail_trim: float
    duration: float = UNIT_DURATION

    @property
    def trimmed_duration(self) -> float:
        return self.duration - self.head_trim - self.tail_trim


def _legacy_idle(unit: ProfileIdleUnit) -> IdleUnit:
    return IdleUnit(
        unit.name,
        DROPBOX_PRODUCTION / unit.relative_path,
        unit.head_trim,
        unit.tail_trim,
        unit.duration,
    )


IDLE_UNIT_A, IDLE_UNIT_B = tuple(
    _legacy_idle(unit) for unit in CEDRIC_PROFILE.idle_units
)
IDLE_UNIT_C2 = IdleUnit(
    "C2",
    LIPSYNC_BASES
    / "cedric_path_a_gesture_idle_C2_10s_loop_v1_blue_1920x1080.mp4",
    0.5,
    0.7,
)
DEFAULT_ROTATION = (IDLE_UNIT_A, IDLE_UNIT_B)

PhaseBPathAQCError = LayeredLipsyncQCError


def _default_root(
    production_root: Path | None = None,
    *,
    event_dir: Path | None = None,
) -> Path:
    if production_root is not None or event_dir is not None:
        return resolve_production_root(production_root, event_dir=event_dir)
    env = os.environ.get("MN_PRODUCTION_ROOT", "").strip()
    return Path(env).expanduser().resolve() if env else DROPBOX_PRODUCTION


def _profile_for_rotation(
    rotation: tuple[IdleUnit, ...],
    fade: float,
    root: Path,
):
    profile_units = tuple(
        ProfileIdleUnit(
            unit.name,
            os.path.relpath(unit.path, root).replace("\\", "/"),
            unit.duration,
            unit.head_trim,
            unit.tail_trim,
        )
        for unit in rotation
    )
    return replace(
        CEDRIC_PROFILE,
        idle_units=profile_units,
        xfade_seconds=fade,
    )


def build_idle_track(
    dest: Path,
    duration: float,
    rotation: tuple[IdleUnit, ...] = DEFAULT_ROTATION,
    fade: float = XFADE_SECONDS,
) -> list[IdleUnit]:
    root = _default_root()
    profile = _profile_for_rotation(rotation, fade, root)
    sequence = _build_idle_track(profile, root, Path(dest), duration)
    by_name = {unit.name: unit for unit in rotation}
    return [by_name[unit.name] for unit in sequence]


def cut_chunks(stem: Path, idle_track: Path, cuts: list[float], work: Path) -> int:
    durations = _cut_chunks(
        CEDRIC_PROFILE, Path(stem), Path(idle_track), cuts, Path(work)
    )
    # Legacy callers expected the unpadded canonical filenames.
    for index in range(len(durations)):
        (Path(work) / f"chunk_{index}_audio_raw.mp3").replace(
            Path(work) / f"chunk_{index}_audio.mp3"
        )
        (Path(work) / f"chunk_{index}_video_raw.mp4").replace(
            Path(work) / f"chunk_{index}_video.mp4"
        )
    return len(durations)


def submit_lipsync_chunks(
    work: Path,
    n_chunks: int,
    api_key: str,
) -> dict[int, str]:
    records = _submit_lipsync_chunks(
        Path(work),
        n_chunks,
        api_key,
        max_workers=CEDRIC_PROFILE.max_parallel_submissions,
    )
    return {
        index: (
            "ok"
            if record.get("status", "").lower() == "completed"
            and record.get("outputs")
            else f"failed:{record.get('status')}"
        )
        for index, record in records.items()
    }


def qc_pupil_scan(
    path: Path,
    fps: int = 6,
) -> list[tuple[float, float]]:
    region = replace(CEDRIC_PROFILE.provider_eye_qc, fps=fps)
    return _qc_pupil_scan(Path(path), region)


def _parse_crop(crop: str) -> Crop:
    width, height, x, y = (int(value) for value in crop.split(":"))
    return Crop(x, y, width, height)


def qc_still_scan(
    path: Path,
    crop: str = IDLE_BODY_CROP,
    min_still_seconds: float = 0.5,
    fps: int = 12,
    threshold: float = 0.31,
) -> list[tuple[float, float]]:
    region = QCRegion(
        _parse_crop(crop),
        fps=fps,
        threshold=threshold,
        min_span_seconds=min_still_seconds,
    )
    return _qc_still_scan(Path(path), region)


def pad_concat_lipsync(work: Path, n_chunks: int, dest: Path) -> None:
    durations = [
        ffprobe_duration(Path(work) / f"chunk_{index}_audio.mp3")
        for index in range(n_chunks)
    ]
    profile = replace(
        CEDRIC_PROFILE,
        boundary_pad_start=0.0,
        boundary_pad_end=0.0,
    )
    _pad_concat_lipsync(profile, Path(work), durations, Path(dest))


def composite_on_plate(
    lipsync_track: Path,
    stem: Path,
    dest: Path,
) -> None:
    _composite_on_plate(
        CEDRIC_PROFILE,
        _default_root(),
        Path(lipsync_track),
        Path(stem),
        Path(dest),
    )


def count_phase_b_path_a_chunks(
    stem: Path,
    max_chunk: float = MAX_CHUNK_SECONDS,
) -> int:
    return len(detect_chunk_boundaries(Path(stem), max_chunk)) + 1


def validate_path_a_assets(
    production_root: Path | None = None,
    *,
    event_dir: Path | None = None,
) -> None:
    validate_assets(
        CEDRIC_PROFILE,
        _default_root(production_root, event_dir=event_dir),
    )


def run_phase_b_path_a_lipsync(
    audio_path: Path,
    out_path: Path,
    *,
    api_key: str,
    work_dir: Path | None = None,
    production_root: Path | None = None,
    event_dir: Path | None = None,
) -> dict:
    """Run the Cedric profile without changing the established Phase B route."""
    return run_layered_lipsync(
        CEDRIC_PROFILE,
        audio_path,
        out_path,
        api_key=api_key,
        production_root=_default_root(production_root, event_dir=event_dir),
        work_dir=work_dir,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stem", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()

    from credentials_lib.credentials import load_wavespeed_api_key

    try:
        api_key = load_wavespeed_api_key(
            _default_root(args.production_root) / "API_KEYS_MASTER.md"
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        run_phase_b_path_a_lipsync(
            args.stem,
            args.out,
            api_key=api_key,
            work_dir=args.work,
            production_root=args.production_root,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[path_a] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

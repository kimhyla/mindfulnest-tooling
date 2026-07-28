#!/usr/bin/env python3
"""Profile-driven layered character lipsync engine.

The engine builds in a local work directory, validates every provider result
and the final composite, then atomically delivers the video and JSON manifest.
It deliberately has no character-specific absolute paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_MAX_CHUNK_SECONDS = 50.0
SILENCE_DETECT_ARGS = "silencedetect=noise=-35dB:d=0.45"

# Arlo idle SSoT — single looped first-clip unit only. Rejected two-clip
# stitch (red hands in second half) must never be selectable via profile,
# trial CLI, or Phase A prepare/validate.
ARLO_CANONICAL_IDLE_NAME = "full_loop_30s"
ARLO_CANONICAL_IDLE_RELATIVE_PATH = (
    "NEW STYLE CHARACTERS/ARLO/"
    "arlo_gesture_idle_full_loop_30s_green_1920x1080_v1.mp4"
)
ARLO_REJECTED_IDLE_PATH_MARKERS = (
    "full_also",
    "also_27s",
    "idle_also_green",
    "_rejected_red_hands_",
)


@dataclass(frozen=True)
class Crop:
    x: int
    y: int
    width: int
    height: int

    @property
    def ffmpeg(self) -> str:
        return f"{self.width}:{self.height}:{self.x}:{self.y}"


@dataclass(frozen=True)
class Size:
    width: int
    height: int

    @property
    def ffmpeg(self) -> str:
        return f"{self.width}:{self.height}"


@dataclass(frozen=True)
class IdleUnit:
    name: str
    relative_path: str
    duration: float
    head_trim: float = 0.0
    tail_trim: float = 0.0

    @property
    def trimmed_duration(self) -> float:
        return self.duration - self.head_trim - self.tail_trim


@dataclass(frozen=True)
class QCRegion:
    crop: Crop
    fps: int
    threshold: float
    min_span_seconds: float
    min_mean: float = 2.0
    max_mean: float = 253.0
    min_stddev: float = 1.0


@dataclass(frozen=True)
class LayeredLipsyncProfile:
    profile_id: str
    route_id: str
    method_id: str
    provider_content: str
    placement_mode: str
    cutout_mode: str
    key_rgb: tuple[int, int, int]
    plate_relative_path: str
    cutout_relative_path: str
    idle_units: tuple[IdleUnit, ...]
    source_size: Size
    canvas_size: Size
    provider_crop: Crop
    provider_input_size: Size
    provider_output_size: Size
    placement: Crop
    xfade_seconds: float
    chroma_filter: str
    despill_filter: str
    post_filters: str
    provider_eye_qc: QCRegion
    idle_body_qc: QCRegion
    composite_body_qc: QCRegion
    max_chunk_seconds: float = DEFAULT_MAX_CHUNK_SECONDS
    boundary_pad_start: float = 0.5
    boundary_pad_end: float = 0.5
    max_parallel_submissions: int = 3
    fps: int = 24


@dataclass(frozen=True)
class LayeredLipsyncPlan:
    audio_duration: float
    max_provider_seconds: float
    boundary_pad_start: float
    boundary_pad_end: float
    raw_chunk_limit: float
    cuts: tuple[float, ...]
    chunk_durations: tuple[float, ...]
    padded_chunk_durations: tuple[float, ...]

    @property
    def chunk_count(self) -> int:
        return len(self.chunk_durations)

    @property
    def plan_sha256(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PreparedLayeredInputs:
    work_dir: Path
    idle_track: Path
    idle_units: tuple[str, ...]


@dataclass(frozen=True)
class LayeredBuildResult:
    video_path: Path
    build_output_sha256: str
    plan: LayeredLipsyncPlan
    idle_units: tuple[str, ...]
    provider_records: dict[int, dict]


PHASE_B_PATH_A_ROUTE_V1 = "PHASE_B_PATH_A_ROUTE_V1"
CEDRIC_PROFILE = LayeredLipsyncProfile(
    profile_id="cedric",
    route_id=PHASE_B_PATH_A_ROUTE_V1,
    method_id="layered_chromakey_kling_lipsync_v2",
    provider_content="whole_character",
    placement_mode="character_box",
    cutout_mode="static_frame",
    key_rgb=(0, 0, 255),
    plate_relative_path=(
        "NEW STYLE CHARACTERS/CEDRIC/path_a_prep/"
        "cedric_room_plate_1280x720_v1.png"
    ),
    cutout_relative_path=(
        "NEW STYLE CHARACTERS/CEDRIC/path_a_prep/"
        "cedric_cutout_blue_1280x720_v1.png"
    ),
    idle_units=(
        IdleUnit(
            "A",
            "assets/lipsync_bases/"
            "cedric_path_a_gesture_idle_10s_loop_v1_blue_1920x1080.mp4",
            10.041667,
            0.6,
            1.2,
        ),
        IdleUnit(
            "B",
            "assets/lipsync_bases/"
            "cedric_path_a_gesture_idle_B_10s_loop_v1_blue_1920x1080.mp4",
            10.041667,
            1.3,
            0.5,
        ),
    ),
    source_size=Size(1920, 1080),
    canvas_size=Size(1280, 720),
    # Cedric's established provider input is the complete 1920x1080 idle.
    provider_crop=Crop(0, 0, 1920, 1080),
    provider_input_size=Size(1920, 1080),
    provider_output_size=Size(832, 464),
    placement=Crop(292, 150, 832, 468),
    xfade_seconds=0.5,
    chroma_filter="chromakey=0x0000FF:0.28:0.06",
    despill_filter="despill=type=blue",
    post_filters="cas=0.45,eq=contrast=1.03:saturation=1.03",
    provider_eye_qc=QCRegion(Crop(266, 60, 300, 130), 6, 0.4, 0.33),
    idle_body_qc=QCRegion(Crop(800, 700, 560, 190), 12, 0.31, 0.5),
    composite_body_qc=QCRegion(Crop(346, 302, 534, 232), 12, 0.31, 0.5),
)

# Arlo's green idle is a complete-character Path A asset, equivalent to
# Cedric's complete-character blue idle. Provider framing and final placement
# therefore preserve the full 16:9 frame, delivered on the module 1280x720 canvas.
ARLO_PROFILE = LayeredLipsyncProfile(
    profile_id="arlo",
    route_id="PHASE_A_ARLO_LAYERED_ROUTE_V1",
    method_id="layered_fullbody_greenscreen_kling_lipsync_v2",
    provider_content="whole_character",
    placement_mode="full_canvas",
    cutout_mode="key_canvas",
    key_rgb=(6, 239, 10),
    # Chair-study plate at canvas resolution (scaled from Kim still; chair
    # kept centered/prominent). Engine scales plate to canvas_size anyway.
    plate_relative_path=(
        "NEW STYLE CHARACTERS/ARLO/"
        "arlo_room_plate_chair_study_1280x720_v2.png"
    ),
    cutout_relative_path=(
        "NEW STYLE CHARACTERS/ARLO/arlo_key_canvas_1280x720_v1.png"
    ),
    # Single approved full_loop_30s unit — looped for any stem length.
    # Trims (2026-07-28): still-ramp floor + pose-match search on 12fps gray
    # 320x180 (minimize join-frame MSE so 0.35s xfade does not double-expose).
    # Prior 0.2/0.2 + 0.30s xfade left visible jumps/ghosts at self-loop joins.
    idle_units=(
        IdleUnit(
            ARLO_CANONICAL_IDLE_NAME,
            ARLO_CANONICAL_IDLE_RELATIVE_PATH,
            30.0,
            1.75,
            1.08,
        ),
    ),
    source_size=Size(1920, 1080),
    canvas_size=Size(1280, 720),
    # Like Cedric Path A, the provider frame contains the complete character.
    # The green idle is already spatially aligned to the canonical 16:9 still.
    provider_crop=Crop(0, 0, 1920, 1080),
    provider_input_size=Size(1920, 1080),
    provider_output_size=Size(832, 464),
    placement=Crop(0, 0, 1280, 720),
    xfade_seconds=0.35,
    # Measured from the installed idle's corner pixels (median RGB 6,239,10).
    # The tighter tolerance preserves Arlo's olive vest while removing the key.
    chroma_filter="chromakey=0x06EF0A:0.18:0.05",
    despill_filter="despill=type=green",
    post_filters="cas=0.4,eq=contrast=1.02:saturation=1.02",
    # Eyes occupy this band after the complete 1920x1080 frame maps to 832x464.
    provider_eye_qc=QCRegion(Crop(350, 125, 150, 95), 6, 0.4, 0.33),
    idle_body_qc=QCRegion(Crop(650, 530, 600, 430), 12, 0.25, 0.5),
    # 1024x576 composition Crop(346,282,322,230) scaled by 1.25 to 1280x720.
    composite_body_qc=QCRegion(Crop(432, 352, 403, 288), 12, 0.25, 0.5),
    # Match Beat Gen Arlo voice-first face-return padding (not the short 0.5/0.5
    # chunk-context defaults used by Cedric Path A).
    boundary_pad_start=0.7,
    boundary_pad_end=2.5,
)

PROFILES = {"cedric": CEDRIC_PROFILE, "arlo": ARLO_PROFILE}


class LayeredLipsyncQCError(RuntimeError):
    """A fail-closed media or QC gate refused the build."""


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def ffprobe_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def ffprobe_size(path: Path) -> Size:
    result = run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise LayeredLipsyncQCError(f"no video stream: {path}")
    return Size(int(streams[0]["width"]), int(streams[0]["height"]))


def resolve_production_root(
    production_root: Path | None = None,
    *,
    event_dir: Path | None = None,
) -> Path:
    if production_root is not None:
        return Path(production_root).expanduser().resolve()
    env = os.environ.get("MN_PRODUCTION_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if event_dir is not None:
        return Path(event_dir).expanduser().resolve().parent
    raise ValueError(
        "production root required: pass production_root/event_dir or set "
        "MN_PRODUCTION_ROOT"
    )


def profile_paths(profile: LayeredLipsyncProfile, production_root: Path) -> dict:
    root = Path(production_root)
    return {
        "plate": root / Path(profile.plate_relative_path),
        "cutout": root / Path(profile.cutout_relative_path),
        "idle_units": tuple(root / Path(unit.relative_path) for unit in profile.idle_units),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def source_hashes(
    profile: LayeredLipsyncProfile,
    production_root: Path,
    audio_path: Path,
) -> dict[str, object]:
    paths = profile_paths(profile, production_root)
    return {
        "audio": sha256_file(audio_path),
        "plate": sha256_file(paths["plate"]),
        "cutout": sha256_file(paths["cutout"]),
        "idle_units": {
            unit.name: sha256_file(path)
            for unit, path in zip(profile.idle_units, paths["idle_units"])
        },
    }


def _validate_crop(name: str, crop: Crop, size: Size) -> None:
    if min(crop.x, crop.y) < 0 or min(crop.width, crop.height) <= 0:
        raise ValueError(f"{name} has invalid non-positive geometry: {crop}")
    if crop.x + crop.width > size.width or crop.y + crop.height > size.height:
        raise ValueError(f"{name} {crop} exceeds {size}")


def _posix_rel(path: str) -> str:
    return str(path).replace("\\", "/").strip()


def assert_idle_path_not_rejected(path: str) -> None:
    """Fail closed if a path looks like a quarantined / red-hands idle."""
    lowered = _posix_rel(path).lower()
    for marker in ARLO_REJECTED_IDLE_PATH_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"rejected Arlo idle path marker {marker!r} in {path!r} "
                f"(canonical={ARLO_CANONICAL_IDLE_RELATIVE_PATH!r})"
            )


def validate_arlo_idle_contract(profile: LayeredLipsyncProfile) -> None:
    """Arlo must use exactly the single full_loop_30s idle — never full_also."""
    if profile.profile_id != "arlo":
        return
    if len(profile.idle_units) != 1:
        raise ValueError(
            "Arlo idle_units must be exactly one full_loop_30s unit "
            f"(got {len(profile.idle_units)})"
        )
    unit = profile.idle_units[0]
    rel = _posix_rel(unit.relative_path)
    assert_idle_path_not_rejected(rel)
    if unit.name != ARLO_CANONICAL_IDLE_NAME:
        raise ValueError(
            f"Arlo idle unit name must be {ARLO_CANONICAL_IDLE_NAME!r}, "
            f"got {unit.name!r}"
        )
    if rel != ARLO_CANONICAL_IDLE_RELATIVE_PATH:
        raise ValueError(
            "Arlo idle path must be canonical loop idle "
            f"{ARLO_CANONICAL_IDLE_RELATIVE_PATH!r}, got {rel!r}"
        )
    if not rel.endswith("full_loop_30s_green_1920x1080_v1.mp4"):
        raise ValueError(f"Arlo idle path must end with full_loop_30s: {rel!r}")


def validate_profile(profile: LayeredLipsyncProfile) -> None:
    if profile.provider_content not in {"whole_character", "region"}:
        raise ValueError(
            f"unsupported provider_content: {profile.provider_content}"
        )
    if profile.placement_mode not in {"full_canvas", "character_box"}:
        raise ValueError(f"unsupported placement_mode: {profile.placement_mode}")
    if profile.cutout_mode not in {"key_canvas", "static_frame"}:
        raise ValueError(f"unsupported cutout_mode: {profile.cutout_mode}")
    if (
        profile.provider_content == "whole_character"
        and profile.provider_crop
        != Crop(0, 0, profile.source_size.width, profile.source_size.height)
    ):
        raise ValueError(
            "whole_character provider frames must preserve the complete source"
        )
    if (
        profile.placement_mode == "full_canvas"
        and profile.placement
        != Crop(0, 0, profile.canvas_size.width, profile.canvas_size.height)
    ):
        raise ValueError(
            "full_canvas placement must cover the complete output canvas"
        )
    _validate_crop("provider_crop", profile.provider_crop, profile.source_size)
    _validate_crop("placement", profile.placement, profile.canvas_size)
    _validate_crop(
        "provider_eye_qc", profile.provider_eye_qc.crop, profile.provider_output_size
    )
    _validate_crop("idle_body_qc", profile.idle_body_qc.crop, profile.source_size)
    _validate_crop(
        "composite_body_qc", profile.composite_body_qc.crop, profile.canvas_size
    )
    if not profile.idle_units:
        raise ValueError("profile requires at least one idle unit")
    if any(unit.trimmed_duration <= profile.xfade_seconds for unit in profile.idle_units):
        raise ValueError("idle trims must leave more than one xfade duration")
    if (
        profile.max_chunk_seconds
        <= profile.boundary_pad_start + profile.boundary_pad_end
    ):
        raise ValueError("chunk duration must exceed boundary padding")
    if profile.max_parallel_submissions < 1:
        raise ValueError("max_parallel_submissions must be positive")
    validate_arlo_idle_contract(profile)


def validate_key_canvas(path: Path, key_rgb: tuple[int, int, int]) -> None:
    """Reject an occluding foreground asset where a pure key canvas is required."""
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    key = np.asarray(key_rgb, dtype=np.int16)
    distance = np.abs(pixels - key).max(axis=2)
    off_key_ratio = float((distance > 3).mean())
    if off_key_ratio > 0.001:
        raise LayeredLipsyncQCError(
            f"key_canvas contains {off_key_ratio:.2%} non-key pixels: {path}"
        )


def validate_assets(profile: LayeredLipsyncProfile, production_root: Path) -> None:
    validate_profile(profile)
    paths = profile_paths(profile, production_root)
    for unit, path in zip(profile.idle_units, paths["idle_units"]):
        assert_idle_path_not_rejected(str(path))
        assert_idle_path_not_rejected(unit.relative_path)
    required = [paths["plate"], paths["cutout"], *paths["idle_units"]]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("layered lipsync assets missing: " + ", ".join(missing))
    if profile.cutout_mode == "key_canvas":
        validate_key_canvas(paths["cutout"], profile.key_rgb)


def build_idle_track(
    profile: LayeredLipsyncProfile,
    production_root: Path,
    dest: Path,
    duration: float,
) -> list[IdleUnit]:
    """Chain idle units to ``duration``.

    Same-unit self-loops (Arlo full_loop_30s) use a hard join after pose-matched
    trims — xfade on identical unit bookends double-exposes Arlo (visible ghost).
    Distinct adjacent units (Cedric A→B) keep the profile xfade blend.
    """
    paths = profile_paths(profile, production_root)
    sequence: list[IdleUnit] = []
    total = 0.0
    while total < duration:
        unit = profile.idle_units[len(sequence) % len(profile.idle_units)]
        if not sequence:
            total = unit.trimmed_duration
        else:
            prev = sequence[-1]
            # Same-unit self-loop joins hard (no overlap). Distinct units xfade.
            if prev.name == unit.name or profile.xfade_seconds <= 0.001:
                total += unit.trimmed_duration
            else:
                total += unit.trimmed_duration - profile.xfade_seconds
        sequence.append(unit)
        if len(sequence) > 64:
            raise RuntimeError("build_idle_track: too many idle copies")

    inputs: list[str] = []
    filters: list[str] = []
    for index, unit in enumerate(sequence):
        inputs.extend(["-i", str(paths["idle_units"][index % len(profile.idle_units)])])
        filters.append(
            f"[{index}:v]trim=start={unit.head_trim}:"
            f"end={unit.duration - unit.tail_trim},setpts=PTS-STARTPTS,"
            f"fps={profile.fps},scale={profile.source_size.ffmpeg}:flags=lanczos,"
            f"setsar=1:1,settb=AVTB,format=yuv420p[v{index}]"
        )
    previous = "v0"
    offset = 0.0
    for index in range(1, len(sequence)):
        same_unit = sequence[index - 1].name == sequence[index].name
        if same_unit or profile.xfade_seconds <= 0.001:
            # Hard join — pose-matched trims own continuity for self-loops.
            filters.append(
                f"[{previous}][v{index}]concat=n=2:v=1:a=0[x{index}]"
            )
            offset += sequence[index - 1].trimmed_duration
        else:
            offset += sequence[index - 1].trimmed_duration - profile.xfade_seconds
            filters.append(
                f"[{previous}][v{index}]xfade=transition=fade:"
                f"duration={profile.xfade_seconds}:offset={offset:.4f}[x{index}]"
            )
        previous = f"x{index}"
    filters.append(
        f"[{previous}]trim=duration={duration},setpts=PTS-STARTPTS[vout]"
    )
    run(
        [
            "ffmpeg", "-y", "-v", "error", *inputs,
            "-filter_complex", ";".join(filters), "-map", "[vout]", "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
            str(dest),
        ]
    )
    return sequence


def detect_chunk_boundaries(
    stem: Path,
    max_chunk: float = DEFAULT_MAX_CHUNK_SECONDS,
) -> list[float]:
    process = subprocess.run(
        [
            "ffmpeg", "-i", str(stem), "-af", SILENCE_DETECT_ARGS,
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in process.stderr.splitlines():
        match = re.search(r"silence_start: ([\d.]+)", line)
        if match:
            start = float(match.group(1))
        match = re.search(r"silence_end: ([\d.]+)", line)
        if match and start is not None:
            silences.append((start, float(match.group(1))))
            start = None

    total = ffprobe_duration(stem)
    cuts: list[float] = []
    position = 0.0
    while total - position > max_chunk:
        candidates = [
            silence
            for silence in silences
            if position < sum(silence) / 2 <= position + max_chunk
        ]
        if not candidates:
            raise RuntimeError(
                f"no silence found in ({position}, {position + max_chunk}]"
            )
        cut = round(sum(candidates[-1]) / 2, 2)
        cuts.append(cut)
        position = cut
    return cuts


def plan_layered_lipsync(
    profile: LayeredLipsyncProfile,
    audio_path: Path,
) -> LayeredLipsyncPlan:
    """Create the single chunk plan used by budget, preparation, and build."""
    validate_profile(profile)
    audio_path = Path(audio_path)
    total = ffprobe_duration(audio_path)
    raw_limit = (
        profile.max_chunk_seconds
        - profile.boundary_pad_start
        - profile.boundary_pad_end
    )
    cuts = tuple(detect_chunk_boundaries(audio_path, raw_limit))
    bounds = (0.0, *cuts, total)
    raw_durations = tuple(
        end - start for start, end in zip(bounds, bounds[1:])
    )
    padded_durations = tuple(
        duration + profile.boundary_pad_start + profile.boundary_pad_end
        for duration in raw_durations
    )
    if any(
        duration > profile.max_chunk_seconds + 0.05
        for duration in padded_durations
    ):
        raise ValueError("planned padded chunk exceeds provider duration limit")
    return LayeredLipsyncPlan(
        audio_duration=total,
        max_provider_seconds=profile.max_chunk_seconds,
        boundary_pad_start=profile.boundary_pad_start,
        boundary_pad_end=profile.boundary_pad_end,
        raw_chunk_limit=raw_limit,
        cuts=cuts,
        chunk_durations=raw_durations,
        padded_chunk_durations=padded_durations,
    )


def count_layered_lipsync_chunks(
    profile: LayeredLipsyncProfile,
    audio_path: Path,
) -> int:
    return plan_layered_lipsync(profile, audio_path).chunk_count


def cut_chunks(
    profile: LayeredLipsyncProfile,
    stem: Path,
    idle_track: Path,
    cuts: list[float],
    work: Path,
) -> list[float]:
    """Cut the unpadded stem first and tightly crop provider video inputs."""
    total = ffprobe_duration(stem)
    bounds = [0.0, *cuts, total]
    durations: list[float] = []
    for index, (start, end) in enumerate(zip(bounds, bounds[1:])):
        duration = end - start
        durations.append(duration)
        run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", str(stem),
                "-ss", str(start), "-t", str(duration), "-c:a", "libmp3lame",
                "-q:a", "2", str(work / f"chunk_{index}_audio_raw.mp3"),
            ]
        )
        run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", str(idle_track),
                "-ss", str(start), "-t", str(duration),
                "-vf",
                f"crop={profile.provider_crop.ffmpeg},"
                f"scale={profile.provider_input_size.ffmpeg}:flags=lanczos,"
                f"setsar=1:1,fps={profile.fps}",
                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                "-pix_fmt", "yuv420p", str(work / f"chunk_{index}_video_raw.mp4"),
            ]
        )
    return durations


def apply_chunk_boundary_padding(
    profile: LayeredLipsyncProfile,
    work: Path,
    chunk_durations: list[float],
) -> list[float]:
    """Apply boundary context only after silence-aligned chunks exist."""
    padded_durations: list[float] = []
    for index, raw_duration in enumerate(chunk_durations):
        padded_duration = (
            raw_duration + profile.boundary_pad_start + profile.boundary_pad_end
        )
        if padded_duration > profile.max_chunk_seconds + 0.05:
            raise ValueError(
                f"padded chunk {index} is {padded_duration:.3f}s, "
                f"over {profile.max_chunk_seconds:.3f}s"
            )
        run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-t", str(profile.boundary_pad_start),
                "-i", "anullsrc=r=44100:cl=mono",
                "-i", str(work / f"chunk_{index}_audio_raw.mp3"),
                "-f", "lavfi", "-t", str(profile.boundary_pad_end),
                "-i", "anullsrc=r=44100:cl=mono",
                "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
                "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2",
                str(work / f"chunk_{index}_audio.mp3"),
            ]
        )
        run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(work / f"chunk_{index}_video_raw.mp4"),
                "-vf",
                f"tpad=start_mode=clone:start_duration={profile.boundary_pad_start}:"
                f"stop_mode=clone:stop_duration={profile.boundary_pad_end},"
                f"trim=duration={padded_duration},setpts=PTS-STARTPTS",
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "15",
                "-pix_fmt", "yuv420p", str(work / f"chunk_{index}_video.mp4"),
            ]
        )
        padded_durations.append(padded_duration)
    return padded_durations


def submit_lipsync_chunks(
    work: Path,
    n_chunks: int,
    api_key: str,
    *,
    max_workers: int,
    client_factory: Callable[[str], object] | None = None,
) -> dict[int, dict]:
    """Submit bounded parallel jobs and retain task IDs/provider results."""
    if client_factory is None:
        if str(TOOLS_DIR) not in sys.path:
            sys.path.insert(0, str(TOOLS_DIR))
        from lipsync_sender import LipSyncClient, install_public_dns_fallback

        install_public_dns_fallback()
        client_factory = LipSyncClient

    def worker(index: int) -> tuple[int, dict]:
        client = client_factory(api_key)
        task_id: str | None = None
        try:
            task_id = client.submit(
                work / f"chunk_{index}_video.mp4",
                work / f"chunk_{index}_audio.mp3",
                transport="url",
            )
            result = client.poll_until_done(task_id)
            outputs = result.get("outputs") or []
            status = str(result.get("status") or "unknown")
            record = {
                "status": status,
                "task_id": task_id,
                "outputs": list(outputs),
            }
            if status.lower() == "completed" and outputs:
                client.download(
                    outputs[0], work / f"chunk_{index}_lipsync.mp4"
                )
            return index, record
        except Exception as exc:  # noqa: BLE001
            return index, {
                "status": "exception",
                "task_id": task_id,
                "error": f"{type(exc).__name__}: {exc}",
            }

    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, n_chunks)) as executor:
        futures = [executor.submit(worker, index) for index in range(n_chunks)]
        for future in as_completed(futures):
            index, record = future.result()
            results[index] = record
    return results


def _gray_frames(path: Path, region: QCRegion):
    import numpy as np

    crop = region.crop
    raw = run(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-vf", f"fps={region.fps},crop={crop.ffmpeg},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ],
        capture_output=True,
    ).stdout
    pixels = crop.width * crop.height
    count = len(raw) // pixels
    if count < 2:
        raise LayeredLipsyncQCError(
            f"uninformative QC crop ({count} frame(s)): {path}"
        )
    frames = np.frombuffer(raw[: count * pixels], dtype=np.uint8).reshape(
        count, crop.height, crop.width
    )
    mean = float(frames.mean())
    stddev = float(frames.std())
    if (
        mean <= region.min_mean
        or mean >= region.max_mean
        or stddev < region.min_stddev
    ):
        raise LayeredLipsyncQCError(
            f"uninformative QC crop mean={mean:.3f} stddev={stddev:.3f}: {path}"
        )
    return frames


def qc_pupil_scan(
    path: Path,
    region: QCRegion,
) -> list[tuple[float, float]]:
    import numpy as np

    frames = _gray_frames(path, region)
    dark = (frames < 70).sum(axis=(1, 2)).astype(float)
    median = float(np.median(dark))
    if median <= 0:
        raise LayeredLipsyncQCError(f"eye crop has no dark detail: {path}")
    bad = dark < region.threshold * median
    spans: list[tuple[float, float]] = []
    index = 0
    min_frames = max(2, round(region.min_span_seconds * region.fps))
    while index < len(frames):
        if bad[index]:
            end = index
            while end < len(frames) and bad[end]:
                end += 1
            if end - index >= min_frames:
                spans.append(
                    (round(index / region.fps, 2), round(end / region.fps, 2))
                )
            index = end
        else:
            index += 1
    return spans


def qc_still_scan(
    path: Path,
    region: QCRegion,
) -> list[tuple[float, float]]:
    import numpy as np

    frames = _gray_frames(path, region).astype(np.int16)
    differences = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    still = differences < region.threshold
    spans: list[tuple[float, float]] = []
    start: int | None = None
    for index, is_still in enumerate(still):
        if is_still and start is None:
            start = index
        if not is_still and start is not None:
            duration = (index - start) / region.fps
            if duration >= region.min_span_seconds:
                spans.append((round(start / region.fps, 2), round(duration, 2)))
            start = None
    if start is not None:
        duration = (len(frames) - 1 - start) / region.fps
        if duration >= region.min_span_seconds:
            spans.append((round(start / region.fps, 2), round(duration, 2)))
    return spans


def validate_provider_output(
    path: Path,
    profile: LayeredLipsyncProfile,
) -> None:
    actual = ffprobe_size(path)
    if actual != profile.provider_output_size:
        raise LayeredLipsyncQCError(
            f"provider output is {actual}, expected {profile.provider_output_size}"
        )
    run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])


def pad_concat_lipsync(
    profile: LayeredLipsyncProfile,
    work: Path,
    chunk_durations: list[float],
    dest: Path,
) -> None:
    concat_lines: list[str] = []
    for index, raw_duration in enumerate(chunk_durations):
        exact = work / f"chunk_{index}_exact.mp4"
        run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(work / f"chunk_{index}_lipsync.mp4"),
                "-vf",
                f"trim=start={profile.boundary_pad_start},setpts=PTS-STARTPTS,"
                f"fps={profile.fps},scale={profile.placement.width}:"
                f"{profile.placement.height}:flags=lanczos,"
                f"tpad=stop_mode=clone:stop_duration=2,"
                f"trim=duration={raw_duration},setpts=PTS-STARTPTS",
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "15",
                "-pix_fmt", "yuv420p", str(exact),
            ]
        )
        concat_lines.append(f"file '{exact.name}'")
    concat_file = work / "concat_lipsync.txt"
    concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy", str(dest),
        ]
    )
    run(["ffmpeg", "-v", "error", "-i", str(dest), "-f", "null", "-"])


def composite_on_plate(
    profile: LayeredLipsyncProfile,
    production_root: Path,
    lipsync_track: Path,
    stem: Path,
    dest: Path,
) -> None:
    paths = profile_paths(profile, production_root)
    filters = (
        f"[1:v]{profile.post_filters}[ls];"
        f"[0:v]scale={profile.canvas_size.ffmpeg}:flags=lanczos[base];"
        f"[base][ls]overlay={profile.placement.x}:{profile.placement.y}:"
        f"shortest=1[full];"
        f"[full]{profile.chroma_filter},{profile.despill_filter}[keyed];"
        f"[2:v]scale={profile.canvas_size.ffmpeg}:flags=lanczos[plate];"
        f"[plate][keyed]overlay=0:0:shortest=1,"
        f"fps={profile.fps},format=yuv420p[out]"
    )
    run(
        [
            "ffmpeg", "-y", "-loglevel", "fatal", "-stream_loop", "-1",
            "-i", str(paths["cutout"]), "-i", str(lipsync_track),
            "-loop", "1", "-i", str(paths["plate"]), "-i", str(stem),
            "-filter_complex", filters, "-map", "[out]", "-map", "3:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest),
        ]
    )
    run(["ffmpeg", "-v", "error", "-i", str(dest), "-f", "null", "-"])


def manifest_path_for(output: Path) -> Path:
    return output.with_suffix(".json")


def atomic_deliver(
    local_output: Path,
    output: Path,
    manifest: dict,
) -> Path:
    """Install video first and its committed manifest last, with rollback."""
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path_for(output)
    output_fd, output_tmp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(output_fd)
    manifest_fd, manifest_tmp_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(manifest_fd)
    output_tmp = Path(output_tmp_name)
    manifest_tmp = Path(manifest_tmp_name)
    output_backup = output.parent / f".{output.name}.rollback"
    manifest_backup = output.parent / f".{manifest_path.name}.rollback"
    try:
        with local_output.open("rb") as source, output_tmp.open("wb") as target:
            while block := source.read(1024 * 1024):
                target.write(block)
        committed_manifest = dict(manifest)
        committed_manifest["committed"] = True
        manifest_tmp.write_text(
            json.dumps(committed_manifest, indent=2) + "\n", encoding="utf-8"
        )
        output_backup.unlink(missing_ok=True)
        manifest_backup.unlink(missing_ok=True)
        had_output = output.exists()
        had_manifest = manifest_path.exists()
        if had_output:
            shutil.copy2(output, output_backup)
        if had_manifest:
            shutil.copy2(manifest_path, manifest_backup)
        output_installed = False
        manifest_installed = False
        try:
            os.replace(output_tmp, output)
            output_installed = True
            os.replace(manifest_tmp, manifest_path)
            manifest_installed = True
        except Exception:
            if output_installed:
                if had_output and output_backup.exists():
                    os.replace(output_backup, output)
                elif not had_output:
                    output.unlink(missing_ok=True)
            if manifest_installed:
                if had_manifest and manifest_backup.exists():
                    os.replace(manifest_backup, manifest_path)
                elif not had_manifest:
                    manifest_path.unlink(missing_ok=True)
            raise
        output_backup.unlink(missing_ok=True)
        manifest_backup.unlink(missing_ok=True)
    finally:
        output_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        if output_backup.exists() and not output.exists():
            os.replace(output_backup, output)
        if manifest_backup.exists() and not manifest_path.exists():
            os.replace(manifest_backup, manifest_path)
    return manifest_path


def prepare_layered_lipsync_inputs(
    profile: LayeredLipsyncProfile,
    plan: LayeredLipsyncPlan,
    audio_path: Path,
    *,
    production_root: Path,
    work_dir: Path,
) -> PreparedLayeredInputs:
    """Materialize the exact idle/audio/video inputs declared by ``plan``."""
    validate_assets(profile, production_root)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    idle = work / "idle_track.mp4"
    sequence = build_idle_track(
        profile,
        production_root,
        idle,
        plan.audio_duration,
    )
    idle_stills = qc_still_scan(idle, profile.idle_body_qc)
    if idle_stills:
        raise LayeredLipsyncQCError(f"idle still spans: {idle_stills}")
    actual_durations = cut_chunks(
        profile,
        Path(audio_path),
        idle,
        list(plan.cuts),
        work,
    )
    if len(actual_durations) != plan.chunk_count or any(
        abs(actual - expected) > 0.01
        for actual, expected in zip(actual_durations, plan.chunk_durations)
    ):
        raise RuntimeError("materialized chunk durations differ from immutable plan")
    apply_chunk_boundary_padding(profile, work, actual_durations)
    return PreparedLayeredInputs(
        work_dir=work,
        idle_track=idle,
        idle_units=tuple(unit.name for unit in sequence),
    )


def build_layered_lipsync(
    profile: LayeredLipsyncProfile,
    plan: LayeredLipsyncPlan,
    audio_path: Path,
    prepared: PreparedLayeredInputs,
    *,
    production_root: Path,
    provider_records: dict[int, dict],
) -> LayeredBuildResult:
    """Validate provider files and build a local, event-neutral composite."""
    work = prepared.work_dir
    if set(provider_records) != set(range(plan.chunk_count)):
        raise RuntimeError("provider records do not match immutable chunk plan")
    for index in range(plan.chunk_count):
        record = provider_records[index]
        if (
            str(record.get("status") or "").lower() != "completed"
            or not record.get("outputs")
        ):
            raise RuntimeError(f"lipsync chunk {index} not completed: {record}")
        provider_output = work / f"chunk_{index}_lipsync.mp4"
        validate_provider_output(provider_output, profile)
        eye_spans = qc_pupil_scan(provider_output, profile.provider_eye_qc)
        if eye_spans:
            raise LayeredLipsyncQCError(
                f"chunk {index} pupil spans: {eye_spans}"
            )

    lipsync_track = work / "lipsync_full.mp4"
    pad_concat_lipsync(
        profile,
        work,
        list(plan.chunk_durations),
        lipsync_track,
    )
    local_output = work / "composite_local.mp4"
    composite_on_plate(
        profile,
        production_root,
        lipsync_track,
        Path(audio_path),
        local_output,
    )
    final_stills = qc_still_scan(local_output, profile.composite_body_qc)
    if final_stills:
        raise LayeredLipsyncQCError(f"composite still spans: {final_stills}")
    run(["ffmpeg", "-v", "error", "-i", str(local_output), "-f", "null", "-"])
    return LayeredBuildResult(
        video_path=local_output,
        build_output_sha256=sha256_file(local_output),
        plan=plan,
        idle_units=prepared.idle_units,
        provider_records=provider_records,
    )


def deliver_layered_lipsync(
    profile: LayeredLipsyncProfile,
    build: LayeredBuildResult,
    audio_path: Path,
    output_path: Path,
    *,
    production_root: Path,
    manifest_context: dict | None = None,
) -> dict:
    """Deliver build bytes and commit a matching manifest last."""
    manifest = {
        "profile": profile.profile_id,
        "route": profile.route_id,
        "method": profile.method_id,
        "production_root": str(production_root),
        "audio": str(audio_path),
        "output": str(output_path),
        "chunk_count": build.plan.chunk_count,
        "cuts": list(build.plan.cuts),
        "chunk_durations": [
            round(value, 3) for value in build.plan.chunk_durations
        ],
        "padded_chunk_durations": [
            round(value, 3) for value in build.plan.padded_chunk_durations
        ],
        "plan_sha256": build.plan.plan_sha256,
        "units": list(build.idle_units),
        "lipsync": {
            str(index): build.provider_records[index]
            for index in sorted(build.provider_records)
        },
        "profile_config": asdict(profile),
        "source_sha256": source_hashes(profile, production_root, Path(audio_path)),
        "build_output_sha256": build.build_output_sha256,
        "delivery_output_sha256": sha256_file(build.video_path),
        "output_sha256": sha256_file(build.video_path),
    }
    if manifest_context:
        manifest.update(manifest_context)
    atomic_deliver(build.video_path, Path(output_path), manifest)
    manifest["committed"] = True
    return manifest


def run_layered_lipsync(
    profile: LayeredLipsyncProfile,
    audio_path: Path,
    output_path: Path,
    *,
    api_key: str,
    production_root: Path | None = None,
    event_dir: Path | None = None,
    work_dir: Path | None = None,
    client_factory: Callable[[str], object] | None = None,
) -> dict:
    root = resolve_production_root(production_root, event_dir=event_dir)
    audio_path = Path(audio_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    work = (
        Path(work_dir).expanduser().resolve()
        if work_dir is not None
        else Path(tempfile.mkdtemp(prefix=f"layered_{profile.profile_id}_"))
    )
    work.mkdir(parents=True, exist_ok=True)
    plan = plan_layered_lipsync(profile, audio_path)
    prepared = prepare_layered_lipsync_inputs(
        profile,
        plan,
        audio_path,
        production_root=root,
        work_dir=work,
    )
    results = submit_lipsync_chunks(
        work,
        plan.chunk_count,
        api_key,
        max_workers=profile.max_parallel_submissions,
        client_factory=client_factory,
    )
    failed = {
        index: record
        for index, record in results.items()
        if record.get("status", "").lower() != "completed"
        or not record.get("outputs")
    }
    if failed or len(results) != plan.chunk_count:
        raise RuntimeError(f"lipsync chunk failures: {failed or 'missing results'}")
    build = build_layered_lipsync(
        profile,
        plan,
        audio_path,
        prepared,
        production_root=root,
        provider_records=results,
    )
    return deliver_layered_lipsync(
        profile,
        build,
        audio_path,
        output_path,
        production_root=root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES))
    parser.add_argument("--production-root", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()

    from credentials_lib.credentials import load_wavespeed_api_key

    try:
        api_key = load_wavespeed_api_key(
            args.production_root / "API_KEYS_MASTER.md"
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        run_layered_lipsync(
            PROFILES[args.profile],
            args.audio,
            args.output,
            api_key=api_key,
            production_root=args.production_root,
            work_dir=args.work,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"[layered_lipsync] FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

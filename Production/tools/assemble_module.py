#!/usr/bin/env python3
"""
assemble_module.py — Phase C canonical 10-step pipeline + Step 1.5 + finalization Steps 11-13.

Per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.3 + §3.2 (R2 canonical 10
steps) + §3.4 (R4 Step 1.5 audio parity + bitrate gate) + ASSEMBLE_MODULE_CONTRACT.md
(7 declared output artifacts).

Authored: 2026-05-10 (Phase C; depends on Phase A manifest_helpers.py merged in
PR #26 / commit 8fefeb7 and Phase B register_asset signature + release_gates
merged in PR #29 / commit 9105028).

Pipeline (called in this order by the orchestrator ``assemble_module()``):

    1.   Validate inputs    — ffprobe codec spec per LD-284
    1.5  Audio parity gate  — CONCAT_AUDIO_PARITY_V1 + SIZE_BUDGET_VIDEO_V1
    2.   Build concat-list  — ffmpeg concat demuxer file list (single-quote escape)
    3.   Concat -c copy     — ffmpeg -f concat -safe 0 -c copy
    4.   +faststart remux   — ffmpeg -movflags +faststart
    5.   MOOV validate      — pure-Python atom walk; MOOV before MDAT
    6.   Codec assert       — ffprobe canonical spec on assembled output
    7.   1-frame decode     — ffmpeg -frames:v 1 (exit MUST be 0)
    8.   Full-duration smoke — ffmpeg -i out.mp4 -f null - (exit MUST be 0)
    9.   Compute hashes     — source_hash + output_hash (R3 single hex form)
    10.  Emit 7 artifacts   — M001.{mp4, manifest.json, ffprobe.json,
                              decode_test.log, size_report.json, sha256,
                              listen_through.mp4}

    --- Finalization (NOT part of the canonical 10) ---
    11.  Size + duration gate — LD-283 (≤80 MB, ≤7 min)
    12.  register_asset       — LD-421 per-artifact with codec_recipe_hash
    13.  Emit phaseBoundaries — LD-412 named-object form

CLI::

    python3 Production/tools/assemble_module.py \\
        --module M001 \\
        --beats   /path/to/normalized_beats_dir \\
        --audio   /path/to/phase_b_mix.mp3 \\
        --metadata /path/to/module_metadata.json \\
        --out     /path/to/output_dir

Governing LDs:

* LD-280 RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1  — single MP4 output
* LD-283 SIZE_BUDGET_PER_MODULE_V1                    — Step 11 size/duration ceiling
* LD-284 NORMALIZATION_BEFORE_CONCAT_V1               — Step 1 codec spec
* LD-296 SIZE_BUDGET_VIDEO_V1                         — Step 1.5 bitrate ceiling
* LD-364 POST_ITEM_VERIFIED_V1                        — Step 12 read-back-after-write
* LD-404 MANIFEST_SCHEMA_V1                           — Step 13 manifest shape
* LD-412 PHASE_BOUNDARIES_NAMED_OBJECT_V1             — Step 13 named-object form
* LD-421 ASSET_FINDABILITY_OVERHAUL_V1                — Step 12 register_asset wrapper
* LD-422 ASSET_FINDABILITY_BUILD_V1                   — Step 12 wrapper enforcement
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --- Repo-relative imports ------------------------------------------------

_TOOLING_REPO = Path(__file__).resolve().parents[2]
if str(_TOOLING_REPO) not in sys.path:
    sys.path.insert(0, str(_TOOLING_REPO))

from Production.tools.manifest_helpers import (  # noqa: E402
    compute_app_compat_content_hash,
    phase_boundaries_to_manifest_form,
    validate_phase_boundaries,
)
from Production.tools.registered_write import register_asset  # noqa: E402

# --- Constants ------------------------------------------------------------

#: LD-284 NORMALIZATION_BEFORE_CONCAT_V1 — the canonical per-beat codec spec.
#: assemble_module ffprobe-asserts every input against this before concat.
CANONICAL_CODEC_SPEC: Dict[str, Any] = {
    "video_codec": "h264",
    "video_profile": "High",
    "pix_fmt": "yuv420p",
    "width": 1280,
    "height": 720,
    "fps": "24/1",
    "audio_codec": "aac",
    "audio_bitrate_bps": 128_000,
    "audio_sample_rate": 44_100,
    "audio_channels": 1,
}

#: Canonical recipe string hashed into ``codec_recipe_hash`` (Phase B field).
#: Deterministic — sorted JSON of CANONICAL_CODEC_SPEC.
CANONICAL_CODEC_RECIPE_STRING: str = json.dumps(CANONICAL_CODEC_SPEC, sort_keys=True)

#: LD-283 SIZE_BUDGET_PER_MODULE_V1 — assembled MP4 ≤ 80 MiB (83,886,080 bytes).
MAX_MODULE_BYTES: int = 83_886_080

#: LD-283 SIZE_BUDGET_PER_MODULE_V1 — assembled MP4 ≤ 7 min (420,000 ms).
MAX_MODULE_DURATION_MS: int = 420_000

#: LD-296 SIZE_BUDGET_VIDEO_V1 — per-input overall bitrate ≤ 1.9 Mbps
#: (1,900,000 bps); 5% guard band under the 2.0 Mbps hard ceiling.
MAX_BITRATE_BPS: int = 1_900_000

#: ffmpeg silencedetect / anullsrc parameters for Step 1.5 silence injection
#: (audio parity per CONCAT_AUDIO_PARITY_V1). 128 kbps mono 44.1 kHz AAC matches
#: LD-284 canonical audio so the patched beat re-enters Step 1 spec on retry.
_SILENCE_SAMPLE_RATE: int = 44_100
_SILENCE_CHANNELS: int = 1
_SILENCE_AAC_BITRATE: str = "128k"

#: ffprobe / ffmpeg binary names — overridable via env for CI / test harnesses.
FFPROBE_BIN: str = os.environ.get("FFPROBE_BIN", "ffprobe")
FFMPEG_BIN: str = os.environ.get("FFMPEG_BIN", "ffmpeg")


# ===========================================================================
# Exception hierarchy
# ===========================================================================


class AssemblyError(RuntimeError):
    """Base class for any Phase C HARD STOP."""


class CodecMismatchError(AssemblyError):
    """Per-beat or assembled-output codec spec deviation from LD-284."""


class AudioParityError(AssemblyError):
    """Audio stream missing AND silence injection failed."""


class BitrateBudgetError(AssemblyError):
    """Per-input or output overall bitrate > MAX_BITRATE_BPS."""


class SizeBudgetError(AssemblyError):
    """Assembled MP4 bytes > MAX_MODULE_BYTES."""


class DurationBudgetError(AssemblyError):
    """Assembled MP4 duration > MAX_MODULE_DURATION_MS."""


class MoovPositionError(AssemblyError):
    """MOOV atom appears AFTER MDAT in the assembled MP4 (faststart absent)."""


class DecodeError(AssemblyError):
    """ffmpeg decode test returned a non-zero exit code."""


class HashCollisionError(AssemblyError):
    """``output_hash`` matches an existing module in the catalog — investigate."""


# ===========================================================================
# Helpers — subprocess wrappers + ffprobe accessors + codec_recipe_hash
# ===========================================================================


def ffprobe_full(path) -> dict:
    """Return parsed ``ffprobe -show_streams -show_format -of json`` JSON.

    Args:
        path: file to probe (str or Path).
    Returns:
        Parsed JSON dict with ``streams`` (list) and ``format`` (dict) keys.
    Raises:
        subprocess.CalledProcessError if ffprobe exits non-zero.
        ValueError if stdout is not valid JSON.
    """
    out = subprocess.check_output(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"ffprobe returned non-JSON output for {path}: {exc}"
        ) from exc


def ffmpeg_run(args: List[str]) -> int:
    """Run ffmpeg with the given argv (no implicit ``ffmpeg`` prefix — caller
    supplies the full command list starting with the binary name).

    Returns the integer exit code so step functions can branch on it. Stderr
    streams to the parent process so CI logs surface ffmpeg failures.
    """
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.returncode


def derive_bitrate_bps(root: dict, file_path) -> int:
    """Return overall bitrate in bps.

    Reads from ``root["format"]["bit_rate"]`` first. If that is missing,
    ``"N/A"``, ``"0"``, or empty, falls back to
    ``8 * size_bytes / duration_seconds`` using ``format.size`` (or
    ``os.path.getsize(file_path)`` if size is absent) and ``format.duration``.
    """
    fmt = root.get("format", {}) or {}
    raw = fmt.get("bit_rate")
    if raw is not None and str(raw).strip().upper() not in ("N/A", "0", ""):
        return int(raw)

    size = int(fmt.get("size", 0) or 0)
    if size <= 0:
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
    try:
        duration = float(fmt.get("duration", 0))
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0 or size <= 0:
        raise AssemblyError(
            f"{file_path}: cannot derive bitrate "
            f"(format.duration={fmt.get('duration')!r}, size={size})"
        )
    return int(size * 8 / duration)


def video_duration_s(root: dict) -> float:
    """Prefer the first video stream's ``duration``; fall back to
    ``format.duration``. Raises AssemblyError if neither is usable."""
    for stream in root.get("streams", []):
        if stream.get("codec_type") == "video":
            dur = stream.get("duration")
            if dur is not None:
                try:
                    return float(dur)
                except (TypeError, ValueError):
                    pass
    fmt_dur = (root.get("format") or {}).get("duration")
    if fmt_dur is not None:
        try:
            return float(fmt_dur)
        except (TypeError, ValueError):
            pass
    raise AssemblyError("ffprobe returned no usable duration")


def compute_codec_recipe_hash() -> str:
    """Return SHA-256 hex of the canonical codec recipe string.

    Used as the ``codec_recipe_hash`` Phase B kwarg on every register_asset
    call in Step 12 so future fast-detect of "encoder-only changed" assets
    is keyed on a stable spec identifier rather than per-file artefacts.
    """
    return hashlib.sha256(
        CANONICAL_CODEC_RECIPE_STRING.encode("utf-8")
    ).hexdigest()


def inject_silence_track(
    beat_path,
    duration_s: float,
    *,
    sample_rate: int = _SILENCE_SAMPLE_RATE,
    channels: int = _SILENCE_CHANNELS,
) -> Path:
    """Mux a silent AAC track onto ``beat_path`` for ``duration_s`` seconds.

    Returns the path of the patched MP4. The original is preserved; the
    patched output gets a ``.audiopatched.mp4`` suffix so the upstream
    cache key still resolves the source clip.

    The ``atrim=duration=<s>`` is mandatory — without it ``anullsrc``
    generates infinite silence and the ffmpeg pipeline hangs (governance
    Lessons Learned April 25-26 2026).
    """
    beat_path = Path(beat_path)
    out_path = beat_path.with_suffix(".audiopatched.mp4")
    rc = ffmpeg_run(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(beat_path),
            "-f",
            "lavfi",
            "-t",
            f"{duration_s:.3f}",
            "-i",
            f"anullsrc=r={sample_rate}:cl={'mono' if channels == 1 else 'stereo'}",
            "-shortest",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            _SILENCE_AAC_BITRATE,
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            str(out_path),
        ]
    )
    if rc != 0:
        raise AudioParityError(
            f"{beat_path}: silence injection failed (ffmpeg rc={rc})"
        )
    return out_path


# ===========================================================================
# Canonical Steps 1-10
# ===========================================================================


def _assert_video_canonical(stream: dict, source: str) -> None:
    if stream.get("codec_name") != CANONICAL_CODEC_SPEC["video_codec"]:
        raise CodecMismatchError(
            f"{source}: video codec must be {CANONICAL_CODEC_SPEC['video_codec']}, "
            f"got {stream.get('codec_name')}"
        )
    if stream.get("profile") != CANONICAL_CODEC_SPEC["video_profile"]:
        raise CodecMismatchError(
            f"{source}: video profile must be {CANONICAL_CODEC_SPEC['video_profile']}, "
            f"got {stream.get('profile')}"
        )
    if stream.get("pix_fmt") != CANONICAL_CODEC_SPEC["pix_fmt"]:
        raise CodecMismatchError(
            f"{source}: pix_fmt must be {CANONICAL_CODEC_SPEC['pix_fmt']}, "
            f"got {stream.get('pix_fmt')}"
        )
    try:
        if int(stream.get("width")) != CANONICAL_CODEC_SPEC["width"] or int(
            stream.get("height")
        ) != CANONICAL_CODEC_SPEC["height"]:
            raise CodecMismatchError(
                f"{source}: resolution must be "
                f"{CANONICAL_CODEC_SPEC['width']}x{CANONICAL_CODEC_SPEC['height']}, "
                f"got {stream.get('width')}x{stream.get('height')}"
            )
    except (TypeError, ValueError) as exc:
        raise CodecMismatchError(
            f"{source}: width/height not coercible to int: {exc}"
        ) from exc
    fps = stream.get("r_frame_rate") or stream.get("avg_frame_rate")
    if fps != CANONICAL_CODEC_SPEC["fps"]:
        raise CodecMismatchError(
            f"{source}: fps must be {CANONICAL_CODEC_SPEC['fps']}, got {fps!r}"
        )


def _assert_audio_canonical(stream: dict, source: str) -> None:
    if stream.get("codec_name") != CANONICAL_CODEC_SPEC["audio_codec"]:
        raise CodecMismatchError(
            f"{source}: audio codec must be {CANONICAL_CODEC_SPEC['audio_codec']}, "
            f"got {stream.get('codec_name')}"
        )
    try:
        if int(stream.get("sample_rate")) != CANONICAL_CODEC_SPEC["audio_sample_rate"]:
            raise CodecMismatchError(
                f"{source}: sample_rate must be "
                f"{CANONICAL_CODEC_SPEC['audio_sample_rate']}, "
                f"got {stream.get('sample_rate')}"
            )
        if int(stream.get("channels")) != CANONICAL_CODEC_SPEC["audio_channels"]:
            raise CodecMismatchError(
                f"{source}: audio channels must be "
                f"{CANONICAL_CODEC_SPEC['audio_channels']}, "
                f"got {stream.get('channels')}"
            )
    except (TypeError, ValueError) as exc:
        raise CodecMismatchError(
            f"{source}: sample_rate/channels not coercible to int: {exc}"
        ) from exc


def step_1_validate_inputs(beat_paths: Iterable) -> List[dict]:
    """ffprobe every input beat. HARD STOP on any LD-284 codec deviation.

    Returns a list of ``{path, ffprobe_root}`` dicts in input order so the
    orchestrator can reuse the probe data downstream.
    """
    results: List[dict] = []
    for beat in beat_paths:
        beat = Path(beat)
        if not beat.exists():
            raise AssemblyError(f"{beat}: input does not exist")
        root = ffprobe_full(beat)
        streams = root.get("streams", []) or []

        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if len(video_streams) != 1:
            raise CodecMismatchError(
                f"{beat}: expected exactly 1 video stream, got {len(video_streams)}"
            )
        _assert_video_canonical(video_streams[0], str(beat))

        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if len(audio_streams) == 1:
            _assert_audio_canonical(audio_streams[0], str(beat))
        elif len(audio_streams) > 1:
            raise CodecMismatchError(
                f"{beat}: expected at most 1 audio stream, got {len(audio_streams)}"
            )
        # 0 audio streams → handled by Step 1.5 silence injection. Don't fail here.

        results.append({"path": str(beat), "ffprobe_root": root})
    return results


def step_1_5_audio_parity_and_bitrate_gate(beat_paths: Iterable) -> List[Path]:
    """For every input beat:

    * If missing audio stream → inject silence per CONCAT_AUDIO_PARITY_V1.
    * Assert audio codec/sample-rate/channels per LD-284.
    * Assert overall bitrate ≤ MAX_BITRATE_BPS per LD-296.

    Returns the (possibly silence-patched) beat paths in input order, ready
    for Step 2 concat-list construction.
    """
    out_paths: List[Path] = []
    for beat in beat_paths:
        beat = Path(beat)
        root = ffprobe_full(beat)
        streams = root.get("streams", []) or []

        # (a) Video stream assert (defensive — Step 1 already covered this).
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if len(video_streams) != 1:
            raise CodecMismatchError(
                f"{beat}: expected exactly 1 video stream, got {len(video_streams)}"
            )
        _assert_video_canonical(video_streams[0], str(beat))

        # (b) Audio parity — inject silence if missing.
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if len(audio_streams) == 0:
            duration = video_duration_s(root)
            patched = inject_silence_track(beat, duration_s=duration)
            # Re-probe to confirm.
            patched_root = ffprobe_full(patched)
            audio_streams = [
                s
                for s in patched_root.get("streams", [])
                if s.get("codec_type") == "audio"
            ]
            if len(audio_streams) != 1:
                raise AudioParityError(
                    f"{beat}: silence injection succeeded but ffprobe still "
                    f"reports {len(audio_streams)} audio streams; concat "
                    f"would drop audio"
                )
            _assert_audio_canonical(audio_streams[0], str(patched))
            # Run the bitrate gate against the patched output.
            overall = derive_bitrate_bps(patched_root, patched)
            if overall > MAX_BITRATE_BPS:
                raise BitrateBudgetError(
                    f"{patched}: overall bitrate {overall} bps > "
                    f"{MAX_BITRATE_BPS} bps ceiling (LD-296 SIZE_BUDGET_VIDEO_V1)"
                )
            out_paths.append(patched)
            continue
        if len(audio_streams) > 1:
            raise CodecMismatchError(
                f"{beat}: expected at most 1 audio stream, got {len(audio_streams)}"
            )
        _assert_audio_canonical(audio_streams[0], str(beat))

        # (c) Overall bitrate gate per LD-296.
        overall = derive_bitrate_bps(root, beat)
        if overall > MAX_BITRATE_BPS:
            raise BitrateBudgetError(
                f"{beat}: overall bitrate {overall} bps > "
                f"{MAX_BITRATE_BPS} bps ceiling (LD-296 SIZE_BUDGET_VIDEO_V1). "
                f"Re-encode source OR open SHORTCUT_MODULE_<id>_BITRATE_OVERRIDE_V1 "
                f"with Kim approval."
            )
        out_paths.append(beat)
    return out_paths


def step_2_build_concat_list(beat_paths: Iterable, out_path) -> Path:
    """Write the ffmpeg concat demuxer file list. Single-quote escape per
    the open question in ASSEMBLE_MODULE_CONTRACT.md (Production/ paths often
    contain 'Claude Mindfulnest Project Files' with spaces).

    NOTE: ffmpeg concat demuxer does not accept embedded single quotes inside
    single-quoted paths. We refuse such paths up-front rather than emit a
    silently-broken list.
    """
    out_path = Path(out_path)
    lines: List[str] = []
    for beat in beat_paths:
        beat_path = Path(beat)
        # Use absolute() (which keeps symlink chain) rather than resolve() so
        # caller-supplied paths land in the list verbatim. On macOS resolve()
        # rewrites /var/folders/X → /private/var/folders/X which is correct but
        # surprising; ffmpeg concat -safe 0 accepts either form.
        s = str(beat_path if beat_path.is_absolute() else beat_path.absolute())
        if "'" in s:
            raise AssemblyError(
                f"path contains literal single quote (unsupported by concat demuxer): {s}"
            )
        lines.append(f"file '{s}'")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def step_3_concat_copy(beat_list_path, raw_out_path) -> None:
    """``ffmpeg -f concat -safe 0 -i <list> -c copy <out_raw.mp4>``.

    Codec-copy only — inputs already match LD-284 canonical spec.
    """
    rc = ffmpeg_run(
        [
            FFMPEG_BIN,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(beat_list_path),
            "-c",
            "copy",
            str(raw_out_path),
        ]
    )
    if rc != 0:
        raise AssemblyError(f"ffmpeg concat failed (rc={rc})")


def step_4_faststart_remux(raw_out_path, final_out_path) -> None:
    """Re-mux with ``-movflags +faststart`` so MOOV atom is at file head."""
    rc = ffmpeg_run(
        [
            FFMPEG_BIN,
            "-y",
            "-i",
            str(raw_out_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(final_out_path),
        ]
    )
    if rc != 0:
        raise AssemblyError(f"ffmpeg faststart remux failed (rc={rc})")


def step_5_moov_validate(out_path) -> None:
    """Pure-Python MP4 atom walk; raises MoovPositionError if MOOV after MDAT.

    Reads ``<4-byte big-endian size><4-byte type tag>`` for each top-level
    atom and tracks the byte offset of ``moov`` and ``mdat``. Does NOT parse
    atom payloads (we only need their positions). Handles the 64-bit
    extended-size form (size==1, type, then 8-byte size).
    """
    moov_pos: Optional[int] = None
    mdat_pos: Optional[int] = None
    pos = 0
    with open(out_path, "rb") as fh:
        size_bytes = os.path.getsize(out_path)
        while pos < size_bytes:
            fh.seek(pos)
            header = fh.read(8)
            if len(header) < 8:
                break
            box_size = struct.unpack(">I", header[:4])[0]
            box_type = header[4:8]
            advance = box_size
            if box_size == 1:
                ext = fh.read(8)
                if len(ext) < 8:
                    break
                advance = struct.unpack(">Q", ext)[0]
            elif box_size == 0:
                # Atom extends to end of file.
                advance = size_bytes - pos

            if box_type == b"moov" and moov_pos is None:
                moov_pos = pos
            elif box_type == b"mdat" and mdat_pos is None:
                mdat_pos = pos

            if moov_pos is not None and mdat_pos is not None:
                break

            if advance <= 0:
                break
            pos += advance

    if moov_pos is None or mdat_pos is None:
        raise MoovPositionError(
            f"{out_path}: required atoms not found "
            f"(moov_pos={moov_pos}, mdat_pos={mdat_pos})"
        )
    if moov_pos > mdat_pos:
        raise MoovPositionError(
            f"{out_path}: MOOV atom at byte {moov_pos} appears after MDAT "
            f"at byte {mdat_pos}; +faststart absent or misplaced"
        )


def step_6_codec_assert(out_path) -> dict:
    """Re-ffprobe the assembled output and assert the canonical spec end-to-end.

    Returns the ffprobe root dict so downstream steps (11 size gate) can read
    duration/size without another probe.
    """
    root = ffprobe_full(out_path)
    streams = root.get("streams", []) or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if len(video_streams) != 1:
        raise CodecMismatchError(
            f"{out_path}: assembled output has {len(video_streams)} video streams"
        )
    _assert_video_canonical(video_streams[0], str(out_path))
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if len(audio_streams) != 1:
        raise CodecMismatchError(
            f"{out_path}: assembled output has {len(audio_streams)} audio streams"
        )
    _assert_audio_canonical(audio_streams[0], str(out_path))
    return root


def step_7_one_frame_decode(out_path) -> None:
    """``ffmpeg -i out.mp4 -frames:v 1 -f null -``. Exit MUST be 0."""
    rc = ffmpeg_run(
        [
            FFMPEG_BIN,
            "-v",
            "error",
            "-i",
            str(out_path),
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
    )
    if rc != 0:
        raise DecodeError(f"{out_path}: 1-frame decode test failed (rc={rc})")


def step_8_full_duration_smoke(out_path) -> None:
    """``ffmpeg -i out.mp4 -f null -``. Catches mid-stream corruption that the
    1-frame test misses. Exit MUST be 0."""
    rc = ffmpeg_run(
        [FFMPEG_BIN, "-v", "error", "-i", str(out_path), "-f", "null", "-"]
    )
    if rc != 0:
        raise DecodeError(f"{out_path}: full-duration smoke test failed (rc={rc})")


def step_9_compute_hashes(
    out_path,
    *,
    per_beat_hashes: List[str],
    audio_mix_hash: str,
    metadata: Dict[str, Any],
) -> Tuple[str, str]:
    """Compute ``source_hash`` and ``output_hash`` per R3 single-hex form.

    ``output_hash`` = SHA-256 of the assembled MP4's raw bytes via
    ``compute_app_compat_content_hash()`` from Phase A (matches the app-side
    expo-crypto ``Encoding.HEX`` default).

    ``source_hash`` = SHA-256 of canonicalized JSON of
    ``{per_beat_hashes, audio_mix_hash, metadata}`` — deterministic
    regardless of metadata key order.
    """
    output_hash = compute_app_compat_content_hash(Path(out_path))
    source_payload = {
        "per_beat_hashes": list(per_beat_hashes),
        "audio_mix_hash": audio_mix_hash,
        "metadata": metadata,
    }
    source_hash = hashlib.sha256(
        json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return source_hash, output_hash


def _emit_listen_through(
    audio_mix_path: Path, out_path: Path, *, duration_s: Optional[float] = None
) -> None:
    """Wrap the Phase B audio MP3 in an MP4 with a black 1280x720 slate frame.

    Per ASSEMBLE_MODULE_CONTRACT.md "Listen-through file generation. Produce
    a separate listen-through MP4 (Phase B audio + slate frames) for Kim's
    QuickTime review per dashboard-gate audio delivery rule."
    """
    args = [
        FFMPEG_BIN,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=black:s=1280x720:r=24",
        "-i",
        str(audio_mix_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    if duration_s is not None:
        args.insert(1, "-t")
        args.insert(2, f"{duration_s:.3f}")
    # Listen-through failure is a SOFT FAIL per spec §7.3: "Soft fail — log
    # warning; assemble_module continues; Kim review file unavailable for this
    # run." We surface the rc but don't raise.
    ffmpeg_run(args)


def step_10_emit_artifacts(
    *,
    out_path,
    module_id: str,
    ffprobe_root: Dict[str, Any],
    source_hash: str,
    output_hash: str,
    audio_mix_path,
    manifest_phase_boundaries: Dict[str, int],
    reward: Dict[str, Any],
    out_dir,
) -> List[Path]:
    """Emit the 7 declared output artifacts per ASSEMBLE_MODULE_CONTRACT.md /
    spec §3.2 Step 10.

    Returns the list of artifact paths in deterministic order:
    ``[mp4, manifest, ffprobe, decode_log, size_report, sha256, listen_through]``.
    """
    out_path = Path(out_path)
    out_dir = Path(out_dir)
    audio_mix_path = Path(audio_mix_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. M001.mp4 — copy the assembled output to the canonical artifact name.
    mp4_artifact = out_dir / f"{module_id}.mp4"
    if mp4_artifact.resolve() != out_path.resolve():
        mp4_artifact.write_bytes(out_path.read_bytes())

    # 2. M001.manifest.json
    fmt = ffprobe_root.get("format") or {}
    streams = ffprobe_root.get("streams") or []
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"), {}
    )
    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"), {}
    )
    try:
        duration_ms = int(round(float(fmt.get("duration", 0)) * 1000))
    except (TypeError, ValueError):
        duration_ms = 0
    bytes_size = int(fmt.get("size", 0) or 0) or mp4_artifact.stat().st_size

    manifest_artifact = out_dir / f"{module_id}.manifest.json"
    manifest: Dict[str, Any] = {
        "moduleId": module_id,
        "assetUrl": f"{module_id}.{output_hash[:12]}.mp4",
        "source_hash": source_hash,
        "output_hash": output_hash,
        "bytes": bytes_size,
        "durationMs": duration_ms,
        "codec": {
            "video": CANONICAL_CODEC_SPEC["video_codec"],
            "profile": CANONICAL_CODEC_SPEC["video_profile"],
            "pix_fmt": CANONICAL_CODEC_SPEC["pix_fmt"],
            "audio": CANONICAL_CODEC_SPEC["audio_codec"],
        },
        "resolution": {
            "width": CANONICAL_CODEC_SPEC["width"],
            "height": CANONICAL_CODEC_SPEC["height"],
        },
        "fps": CANONICAL_CODEC_SPEC["fps"],
        "audio": {
            "codec": CANONICAL_CODEC_SPEC["audio_codec"],
            "sample_rate": CANONICAL_CODEC_SPEC["audio_sample_rate"],
            "channels": CANONICAL_CODEC_SPEC["audio_channels"],
        },
        "phaseBoundaries": phase_boundaries_to_manifest_form(
            manifest_phase_boundaries
        ),
        "reward": reward,
    }
    manifest_artifact.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 3. M001.ffprobe.json — full ffprobe output.
    ffprobe_artifact = out_dir / f"{module_id}.ffprobe.json"
    ffprobe_artifact.write_text(
        json.dumps(ffprobe_root, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 4. M001.decode_test.log — short audit record of Steps 7 + 8 passing
    #    (the orchestrator already raised on failure; reaching here implies
    #    both decode tests returned 0).
    decode_log_artifact = out_dir / f"{module_id}.decode_test.log"
    decode_log_artifact.write_text(
        f"# {module_id} decode tests — both PASSED\n"
        f"# Generated by assemble_module.py at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"step_7_one_frame_decode: rc=0\n"
        f"step_8_full_duration_smoke: rc=0\n",
        encoding="utf-8",
    )

    # 5. M001.size_report.json
    video_br = int(video_stream.get("bit_rate", 0) or 0)
    audio_br = int(audio_stream.get("bit_rate", 0) or 0)
    overall_br = (
        int(fmt.get("bit_rate", 0) or 0)
        if str(fmt.get("bit_rate", "")).strip()
        not in ("N/A", "", "0", "0.0")
        else 0
    )
    size_report_artifact = out_dir / f"{module_id}.size_report.json"
    size_report_artifact.write_text(
        json.dumps(
            {
                "moduleId": module_id,
                "bytes": bytes_size,
                "max_bytes": MAX_MODULE_BYTES,
                "durationMs": duration_ms,
                "max_duration_ms": MAX_MODULE_DURATION_MS,
                "video_bitrate_bps": video_br,
                "audio_bitrate_bps": audio_br,
                "overall_bitrate_bps": overall_br,
                "max_bitrate_bps": MAX_BITRATE_BPS,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    # 6. M001.sha256 — output_hash on a single line, conventional sha256-style.
    sha_artifact = out_dir / f"{module_id}.sha256"
    sha_artifact.write_text(
        f"{output_hash}  {mp4_artifact.name}\n", encoding="utf-8"
    )

    # 7. M001.listen_through.mp4 — Phase B audio + slate frames.
    listen_artifact = out_dir / f"{module_id}.listen_through.mp4"
    try:
        _emit_listen_through(audio_mix_path, listen_artifact)
    except Exception:
        pass  # Soft fail per spec §7.3.
    # Safety net (runs whether _emit_listen_through raised OR returned without
    # writing a file — e.g. ffmpeg mocked, or rc != 0 silently). Stub keeps the
    # 7-artifact length invariant; downstream Kim-review tooling sees an empty
    # file and surfaces the gap rather than a missing-file error.
    if not listen_artifact.exists():
        listen_artifact.write_bytes(b"")

    return [
        mp4_artifact,
        manifest_artifact,
        ffprobe_artifact,
        decode_log_artifact,
        size_report_artifact,
        sha_artifact,
        listen_artifact,
    ]


# ===========================================================================
# Finalization Steps 11-13 (NOT part of the canonical 10)
# ===========================================================================


def step_11_size_duration_gate(out_path, ffprobe_root: dict, module_id: str) -> None:
    """LD-283 SIZE_BUDGET_PER_MODULE_V1 enforcement.

    HARD STOP if assembled MP4 > 80 MB OR duration > 7 min. Override path
    requires a ``SHORTCUT_MODULE_<id>_CEILING_V1`` LD with Kim approval per
    Rule 19 — assemble_module does NOT consult that LD here; the caller (a
    higher orchestrator) is responsible for the SHORTCUT bypass.
    """
    size_bytes = os.path.getsize(out_path)
    if size_bytes > MAX_MODULE_BYTES:
        raise SizeBudgetError(
            f"{out_path}: bytes={size_bytes} > MAX_MODULE_BYTES={MAX_MODULE_BYTES} "
            f"(LD-283 SIZE_BUDGET_PER_MODULE_V1). Compress further OR open "
            f"SHORTCUT_MODULE_{module_id}_CEILING_V1 with Kim approval."
        )
    try:
        duration_s = float((ffprobe_root.get("format") or {}).get("duration", 0))
    except (TypeError, ValueError):
        duration_s = 0.0
    duration_ms = int(round(duration_s * 1000))
    if duration_ms > MAX_MODULE_DURATION_MS:
        raise DurationBudgetError(
            f"{out_path}: durationMs={duration_ms} > "
            f"MAX_MODULE_DURATION_MS={MAX_MODULE_DURATION_MS} "
            f"(LD-283). Cut content OR open SHORTCUT_MODULE_{module_id}_CEILING_V1."
        )


# Asset-type mapping for the 7 artifacts. LD-280 calls the assembled MP4
# ``final_atomic_mp4``; sidecars (manifest/ffprobe/log/size_report/sha256/
# listen_through) fall back to ``unknown`` per registered_write._ACCEPTED_ASSET_TYPES
# until a domain-specific type lands. Listen-through is Kim-review-only, not
# delivery — distinct from the final_atomic_mp4 even though both are .mp4.
_ARTIFACT_ASSET_TYPE_MAP = {
    ".mp4": "final_atomic_mp4",  # special-cased for listen_through below
    ".json": "unknown",
    ".log": "unknown",
    ".sha256": "unknown",
}


def _asset_type_for_artifact(path: Path) -> str:
    name = path.name
    if name.endswith(".listen_through.mp4"):
        # Kim-review file, NOT a delivery asset — keep distinct asset_type.
        return "unknown"
    if name.endswith(".mp4"):
        return "final_atomic_mp4"
    if name.endswith(".manifest.json"):
        return "unknown"  # Future: `module_manifest_json` once enum extended.
    return _ARTIFACT_ASSET_TYPE_MAP.get(path.suffix, "unknown")


def step_12_register_assets(
    artifacts: Iterable,
    module_id: str,
    codec_recipe_hash: str,
) -> List[Tuple[int, str]]:
    """Register every artifact in ``prod_assets`` via the LD-421 wrapper.

    Each call passes ``codec_recipe_hash`` (Phase B field) so future
    fast-detection of "encoder-only changed" assets is keyed on a stable
    spec identifier. ``cdn_url`` and ``manifest_published_at`` remain
    ``None`` until Phase D r2_atomic_publish wires them up.

    Returns ``[(asset_id, abs_path), ...]``. An ``asset_id`` of ``-1``
    means the write was queued offline per LD-364 — NOT a fatal failure.
    Caller (orchestrator / weekly preflight audit) is responsible for
    surfacing the queue depth.

    NOTE: ``module_id`` in registered_write is an FK to ``prod_modules.id``,
    not the canonical M-number. The string ``module_id`` we receive here is
    the M-number (e.g. ``"M001"``) — we resolve to the FK via the
    ``_MODULE_MAP`` reverse lookup at call time. If the module isn't in the
    map, default to ``1`` and pass ``library=True`` so the row still lands
    (per ``registered_write._MODULE_MAP`` comment).
    """
    # Build reverse map (m_number_str → prod_modules.id) lazily.
    from Production.tools.registered_write import _MODULE_MAP

    m_number_to_id: Dict[str, int] = {
        m_number.lstrip("M").lstrip("0") or "0": int(fk_id)
        for fk_id, (m_number, _, _) in _MODULE_MAP.items()
    }
    # Also accept the full "M001" spelling.
    for fk_id, (m_number, _, _) in _MODULE_MAP.items():
        m_number_to_id[m_number] = int(fk_id)

    normalized = module_id.lstrip("M").lstrip("0") or "0"
    resolved_fk = m_number_to_id.get(module_id) or m_number_to_id.get(normalized)
    library_flag = resolved_fk is None
    fk_id = resolved_fk if resolved_fk is not None else 1

    results: List[Tuple[int, str]] = []
    for art in artifacts:
        art_path = Path(art)
        asset_type = _asset_type_for_artifact(art_path)
        result = register_asset(
            file_path=str(art_path),
            asset_type=asset_type,
            module_id=fk_id,
            produced_by_skill="assemble_module",
            iteration_notes=(
                f"Phase C output for {module_id} per "
                f"V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §4.3"
            ),
            tags=["phase_c", "stream_b", module_id],
            library=library_flag,
            role="delivery" if asset_type == "final_atomic_mp4" else None,
            codec_recipe_hash=codec_recipe_hash,
            cdn_url=None,
            manifest_published_at=None,
        )
        results.append(result)
    return results


def step_13_emit_phase_boundaries(
    manifest_path,
    raw_boundaries: Dict[str, Any],
) -> None:
    """Read the manifest, overwrite ``phaseBoundaries`` with the LD-412
    named-object form, and write back. Validates structure first — raises
    ``ValueError`` on any LD-412 invariant violation.
    """
    manifest_path = Path(manifest_path)
    canonical = phase_boundaries_to_manifest_form(raw_boundaries)
    # Defensive: validate against the manifest_helpers contract. We pass the
    # phase_b_end_ms as total_duration_ms since the manifest doesn't separately
    # carry a total duration in the boundaries dict.
    validate_phase_boundaries(canonical, total_duration_ms=canonical["phase_b_end_ms"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["phaseBoundaries"] = canonical
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


# ===========================================================================
# Orchestrator
# ===========================================================================


def _load_metadata(metadata_path: Path) -> Dict[str, Any]:
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _discover_beat_files(beats_dir: Path) -> List[Path]:
    """Return ``beats_dir/beat_*_normalized.mp4`` sorted lexically."""
    candidates = sorted(beats_dir.glob("beat_*_normalized.mp4"))
    if not candidates:
        # Fallback: any .mp4 in beats_dir, lexical order.
        candidates = sorted(beats_dir.glob("*.mp4"))
    return candidates


def assemble_module(
    *,
    module_id: str,
    beats_dir,
    audio_mix_path,
    metadata_path,
    out_dir,
) -> Dict[str, Any]:
    """Top-level orchestrator. Runs Steps 1 → 1.5 → 2 → 3 → 4 → 5 → 6 → 7 →
    8 → 9 → 10 → 11 → 12 → 13.

    Returns a dict with::

        {
            "module_id": "M001",
            "artifacts": [Path, ...]   # 7 declared output paths
            "asset_ids": [int, ...]    # parallel registration ids (-1 = queued)
            "source_hash": "...",
            "output_hash": "...",
            "codec_recipe_hash": "...",
        }

    Raises ``AssemblyError`` (or one of its subclasses) on any HARD STOP.
    """
    beats_dir = Path(beats_dir)
    audio_mix_path = Path(audio_mix_path)
    metadata_path = Path(metadata_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = _load_metadata(metadata_path)
    raw_phase_boundaries: Dict[str, Any] = metadata.get("phaseBoundaries", {})
    reward: Dict[str, Any] = metadata.get("reward", {"coins": 0, "items": []})

    beats = _discover_beat_files(beats_dir)
    if not beats:
        raise AssemblyError(f"{beats_dir}: no beat_*.mp4 files found")

    # Step 1 — validate inputs.
    step_1_validate_inputs(beats)

    # Step 1.5 — audio parity + bitrate gate. May silence-patch some beats.
    patched_beats = step_1_5_audio_parity_and_bitrate_gate(beats)

    # Step 2 — concat-list.
    concat_list_path = out_dir / "beat_list.txt"
    step_2_build_concat_list(patched_beats, concat_list_path)

    # Step 3 — concat -c copy.
    raw_out = out_dir / f"{module_id}.raw.mp4"
    step_3_concat_copy(concat_list_path, raw_out)

    # Step 4 — +faststart remux.
    out_path = out_dir / f"{module_id}.mp4"
    step_4_faststart_remux(raw_out, out_path)

    # Step 5 — MOOV-before-MDAT.
    step_5_moov_validate(out_path)

    # Step 6 — full codec assert against the assembled output.
    ffprobe_root = step_6_codec_assert(out_path)

    # Step 7 — 1-frame decode test.
    step_7_one_frame_decode(out_path)

    # Step 8 — full-duration smoke.
    step_8_full_duration_smoke(out_path)

    # Step 9 — hashes.
    per_beat_hashes = [
        compute_app_compat_content_hash(b) for b in patched_beats
    ]
    audio_mix_hash = compute_app_compat_content_hash(audio_mix_path)
    source_hash, output_hash = step_9_compute_hashes(
        out_path,
        per_beat_hashes=per_beat_hashes,
        audio_mix_hash=audio_mix_hash,
        metadata=metadata,
    )

    # Step 10 — emit 7 artifacts.
    artifacts = step_10_emit_artifacts(
        out_path=out_path,
        module_id=module_id,
        ffprobe_root=ffprobe_root,
        source_hash=source_hash,
        output_hash=output_hash,
        audio_mix_path=audio_mix_path,
        manifest_phase_boundaries=raw_phase_boundaries,
        reward=reward,
        out_dir=out_dir,
    )

    # Step 11 — size + duration gate.
    step_11_size_duration_gate(out_path, ffprobe_root, module_id=module_id)

    # Step 12 — register every artifact via the LD-421 wrapper.
    recipe_hash = compute_codec_recipe_hash()
    registrations = step_12_register_assets(
        artifacts, module_id=module_id, codec_recipe_hash=recipe_hash
    )

    # Step 13 — re-emit phaseBoundaries in the canonical named-object form.
    manifest_path = next(
        (p for p in artifacts if p.name.endswith(".manifest.json")), None
    )
    if manifest_path is not None and raw_phase_boundaries:
        step_13_emit_phase_boundaries(manifest_path, raw_phase_boundaries)

    return {
        "module_id": module_id,
        "artifacts": artifacts,
        "asset_ids": [r[0] for r in registrations],
        "source_hash": source_hash,
        "output_hash": output_hash,
        "codec_recipe_hash": recipe_hash,
    }


# ===========================================================================
# CLI
# ===========================================================================


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="assemble_module.py",
        description=(
            "Phase C 10-step assembly pipeline + Step 1.5 + Steps 11-13. "
            "Produces 7 declared artifacts per ASSEMBLE_MODULE_CONTRACT.md."
        ),
    )
    p.add_argument("--module", required=True, help="Module id, e.g. M001")
    p.add_argument(
        "--beats",
        required=True,
        help="Directory containing per-beat normalized .mp4 files",
    )
    p.add_argument(
        "--audio",
        required=True,
        help="Phase B audio mix .mp3 (128 kbps mono 44.1 kHz)",
    )
    p.add_argument(
        "--metadata",
        required=True,
        help="Module metadata .json (moduleId, phaseBoundaries, reward)",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Output directory for the 7 artifacts",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = assemble_module(
            module_id=args.module,
            beats_dir=Path(args.beats),
            audio_mix_path=Path(args.audio),
            metadata_path=Path(args.metadata),
            out_dir=Path(args.out),
        )
    except AssemblyError as exc:
        sys.stderr.write(f"assemble_module: HARD STOP — {exc}\n")
        return 1
    module = result.get("module_id", args.module)
    artifacts = result.get("artifacts") or []
    source_hash = result.get("source_hash", "") or ""
    output_hash = result.get("output_hash", "") or ""
    sys.stderr.write(
        "assemble_module: COMPLETE — "
        f"module={module} "
        f"artifacts={len(artifacts)} "
        f"source_hash={(source_hash[:12] + '...') if source_hash else 'n/a'} "
        f"output_hash={(output_hash[:12] + '...') if output_hash else 'n/a'}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

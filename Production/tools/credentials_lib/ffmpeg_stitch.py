"""ffmpeg_stitch — reusable Preview-All-Stitched primitives (LD-285 v2).

Spec: TECH_SPEC_PREVIEW_STITCHED_V2_20260419.md
Authority: LD-285 TRANSITION_EDITOR_MINIMUM_PREVIEW_V1, LD-284 NORMALIZATION_BEFORE_CONCAT_V1
Preflight: 93 (synthesis of 90 4+4 debate; counter findings (a)(d)(f)(i) addressed inline below)

Pipeline:
    snapshot -> resolve_beat_file -> normalize_for_concat (LD-284 codec spec) ->
    trim_normalized -> compute_fade_clamp (2-sided floor-at-0) ->
    render_xfade_pair (one fresh 2-input job per pair, no cumulative offset) ->
    concat_with_xfade_clips (concat demuxer, absolute escaped paths)

Why per-pair xfade clips instead of a single 11-input filter_complex (V1 attempt):
counter C1 of preflight 90 showed cumulative offset arithmetic in a single
filter_complex chain drifts on long sequences. Each per-pair job runs with a
fresh timeline starting at 0, so offsets never accumulate. Concat demuxer with
-c copy then stitches codec-identical pre-renders without re-encoding.

All public helpers raise on failure (fail-loud per Rule 19); callers translate
to HTTP 4xx/5xx with hint-bearing bodies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from video_encode_policy import (
    AUX_H264_ENCODER_ARGS,
    VIDEO_QUALITY_CRF,
    VIDEO_QUALITY_GRADFUN_VF,
    VIDEO_QUALITY_PRESET_BAKE,
    VIDEO_QUALITY_PRESET_PREVIEW,
)

# ---------------------------------------------------------------------------
# Normalization recipe (LD-284) — single source of truth
# ---------------------------------------------------------------------------
# H.264 High / yuv420p / 1280x720 / 24fps / LD-296 capped bitrate
# / AAC 128k mono 44.1k / +faststart.
# Bumping NORMALIZATION_RECIPE_VERSION = bumping NORMALIZATION_RECIPE_HASH = preview cache invalidation.
#
# Split into three constants (preflight 103 / Bug 3 fix):
# - NORMALIZATION_VF_EXPR: the scale/pad/fps filter string. Appended into -vf
#   at simple call sites (normalize_for_concat, trim_normalized, trim_tail)
#   AND chained into filter_complex tails at complex call sites
#   (render_xfade_pair, render_watercolor_overlay) where -vf would otherwise
#   collide with -filter_complex (ffmpeg rc=234).
# - NORMALIZATION_ENCODER_ARGS: codec/audio/mux args only, no -vf. Used at
#   filter_complex call sites. Also the body of NORMALIZATION_FFMPEG_ARGS.
# - NORMALIZATION_FFMPEG_ARGS: canonical form for simple call sites = -vf
#   prefix + ENCODER_ARGS. Preserved for existing simple call sites.
NORMALIZATION_VF_EXPR: str = (
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24,"
    + VIDEO_QUALITY_GRADFUN_VF
)
NORMALIZATION_ENCODER_ARGS: tuple[str, ...] = (
    "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-preset", VIDEO_QUALITY_PRESET_BAKE, "-g", "48", "-bf", "0",
    "-crf", VIDEO_QUALITY_CRF,
    "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
    "-movflags", "+faststart",
)
# Stitch slot mux preview — fast CRF encode (operator rebuild; not kid-facing bake).
PREVIEW_OVERLAY_ENCODER_ARGS: tuple[str, ...] = (
    "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-preset", VIDEO_QUALITY_PRESET_PREVIEW, "-g", "48", "-bf", "0",
    "-crf", VIDEO_QUALITY_CRF,
    "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
    "-movflags", "+faststart",
)
NORMALIZATION_FFMPEG_ARGS: tuple[str, ...] = (
    "-vf", NORMALIZATION_VF_EXPR, *NORMALIZATION_ENCODER_ARGS,
)
# S5.5d (v3 architecture revision, 2026-05-03): code aligned to LD-284
# strict spec — `-preset slow`, `setsar=1:1`, `-g 48`. Version bump from v2 → v3
# forces NORMALIZATION_RECIPE_HASH change which invalidates every cached
# *_normalized.mp4 in normalized_segments/, _normalized_phase_a/, etc.
# Next /api/scene/assemble + preview-stitched paths re-encode from source.
# LD-284 itself unchanged; this is a CODE-ALIGNMENT, not a spec change.
NORMALIZATION_RECIPE_VERSION: str = "v8"  # -bf 0: zero-based video DTS for stitch/browser gates
NORMALIZATION_RECIPE_HASH: str = hashlib.sha256(
    (f"{NORMALIZATION_RECIPE_VERSION}:" + NORMALIZATION_VF_EXPR + "|"
     + " ".join(NORMALIZATION_ENCODER_ARGS)).encode("utf-8"),
).hexdigest()[:16]

# ---------------------------------------------------------------------------
# S5.5d (v3 architecture revision, 2026-05-03): export pipeline recipe
# constants per BEAT_FINALIZE_ENDPOINT_V1 + SCENE_ASSEMBLE_ENDPOINT_V1.
# Stage 1 finalizes each beat (cached); Stage 2 mirrors preview-stitched
# orchestration to assemble the scene + register scene_concat_mp4 asset.
# ---------------------------------------------------------------------------
FINALIZE_RECIPE_VERSION: str = "v2"  # bumped 2026-05-27: magic_still freeze_tail_s support
ASSEMBLE_RECIPE_VERSION: str = "v2"  # FADE_THROUGH_BLACK_20260525: bumped to invalidate

# Fade-through-black canonical defaults (manifest chipper_teleport_intro aligned).
DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS = 600
DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS = 600
DEFAULT_MIN_BLACK_PAUSE_MS = 500
DEFAULT_MODULE_PAIR_FADE_MS = 2800
DEFAULT_PRE_PENULTIMATE_PAIR_FADE_MS = 1500
DEFAULT_FINAL_PAIR_FADE_MS = 2800

# ---------------------------------------------------------------------------
# Watercolor overlay recipe version (V3 MEDIUM-6 fix from preflight 102).
# Bumping this version invalidates all phase_{a,b}_preview caches.
# Bump whenever the overlay filter construction in render_watercolor_overlay
# changes semantics (animation preset easing, chromakey params, scale behavior).
# ---------------------------------------------------------------------------
WATERCOLOR_OVERLAY_RECIPE_VERSION = "wc_v17_fullbleed_rounded_canonical"
# v13 (2026-05-28): Split rub applies to hand pigment only — cream paper +
# black border stay fixed. Fixes v2-class "frame sliced in half" shear.
# v7 (2026-05-28): tpad start alignment + cue_hold_s-derived stop_duration.
#   (1) tpad stop_duration: was hardcoded 300 (→ 7200 frames → 504 timeout).
#       Now passes cue_hold_s = ts_s + dur_s + 2.0 (typically 10-25s) +5s margin.
#   (2) Frame constants in production_server.py corrected for 720×544 lipsync base
#       video → letterboxed to 953×720 in 1280×720 canvas (content x_offset=164).
#       frame_x["b"]: 40→185, frame_y: 180→30, frame_max_w["b"]: 600→340.
# v5 (2026-05-28): Two fixes:
#   (1) chromakey similarity 0.1 → 0.25 — handles YUV quantisation of magenta.
#   (2) Remove -stream_loop -1 for video inputs; add tpad=stop_mode=clone in
#       prefilter — stops baked PIL fade envelope from cycling every 2s.
# v4 (2026-05-27): Switch PIL canvas and chromakey from green (0x00FF00) to
# magenta (0xFF00FF). Green caused edge-eating during fade-in: semi-transparent
# pixels blended toward green and were partially removed by chromakey. Magenta
# doesn't appear in skin tones or watercolor art. Also: safe zone validation is
# now enforce_safe_zone=True ONLY in watercolor animate, not magic trail.
# v3 (2026-05-27): Root-cause fix for invisible overlay. ffmpeg overlay filter
# advances BOTH input streams in parallel regardless of `enable` condition.
# If cue input was limited to -t {dur_s} (e.g. 10.0s), [cN] reached EOF at t=10.0
# BEFORE the enable window opened at t=11.341, making the overlay permanently
# invisible. Fix: cue_hold_s = ts_s + dur_s + 2.0 ensures frames always exist
# at any point in the enable window. Also: switched between() -> gte()*lte()
# for unambiguous inclusive-on-both-ends semantics; added setpts=PTS-STARTPTS
# on base to anchor PTS to zero; fixed ffmpeg fade st= to ts_s not 0.
# v2 (preflight 134, 2026-04-20): scale-to-bbox (no pad), overlay at native aspect.
# Prior v1 padded every cue to 1280x720 centered, which made a 400x400 PNG render
# center-of-frame regardless of frame_x. v2 scales to (frame_max_w, frame_max_h)
# with `force_original_aspect_ratio=decrease` and NO pad, so the overlay lands at
# (frame_x, frame_y) at its native scaled size -- correctly fitting LEFT or RIGHT
# frame. Supersedes LD 304 semantics for overlay placement.
WATERCOLOR_OVERLAY_RECIPE_HASH: str = hashlib.sha256(
    f"{WATERCOLOR_OVERLAY_RECIPE_VERSION}:fade_in=0.3s|slide_in=0.5s|"
    f"gentle_pan=5px_sin|chromakey=0xFF00FF:0.1:0.0|scale=bbox_no_pad".encode("utf-8"),
).hexdigest()[:16]

# Watercolor cue animation presets and allowed cue types (mirror the
# production_server whitelist so misuse fails fast in the library too).
_WC_ANIMATIONS = frozenset({"fade_in", "slide_in", "gentle_pan"})
_WC_CUE_TYPES = frozenset({"png", "video"})
_WC_PNG_EXTS = (".png",)
_WC_VIDEO_EXTS = (".mov", ".mp4")

# ---------------------------------------------------------------------------
# Recipe + cache version constants
# ---------------------------------------------------------------------------
PREVIEW_RECIPE_VERSION = "v2"  # bump on any pipeline change
FADE_CLAMP_BUFFER_S = 0.2  # 2-sided buffer (counter C2 / preflight 90)
DEFAULT_LRU_KEEP = 5
DEFAULT_FFMPEG_TIMEOUT_S = 120


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
def _escape_for_concat(p: Path) -> str:
    """Render a Path as a single-quoted concat-demuxer file entry, escaping
    embedded single quotes per ffmpeg's documented `'\\''` pattern.

    Counter (c) MEDIUM mitigation: current Dropbox path has no apostrophe but
    a future rename to a path containing `'` would silently corrupt concat.txt
    without this. The existing silcomp helper at production_server.py:1932 has
    the same latent issue — flagged separately, not fixed here.
    """
    raw = str(p.resolve())
    escaped = raw.replace("'", "'\\''")
    return f"file '{escaped}'"


# ---------------------------------------------------------------------------
# Beat file resolution (snapshot-based)
# ---------------------------------------------------------------------------
def resolve_beat_file(beat_id: str, state_snapshot: dict,
                      clips_dir: Path) -> Path:
    """Resolve the final playable file for a beat from a state snapshot.

    Resolution priority:
      0. beat.final.file when set AND the file exists on disk. Written by
         _handle_use_as_final (Spec A / LD-139, "use as final, no lipsync").
         Represents an EXPLICIT user override and MUST win over any
         pre-existing or subsequent completed lipsync — otherwise Kim's
         no-lipsync approval is silently shadowed when a stale lipsync
         from an earlier option remains in state.
      1. beat.lipsync.file when beat.lipsync.status == "completed" AND the
         file exists on disk. (Applies to beats with dialogue that have
         been lipsynced and not yet "used as final".)
      2. beat.phase_1.options[selected_option-1].file as fallback. (Applies
         to beats without dialogue, e.g. stage-direction-only establishing
         shots, or beats not yet lipsynced and not yet approved.)

    Raises FileNotFoundError with a hint-bearing message on any miss; caller
    translates to HTTP 400 with a list of missing beats.
    """
    beats = state_snapshot.get("beats") or {}
    beat = beats.get(beat_id)
    if not beat:
        raise FileNotFoundError(f"beat {beat_id!r} not in snapshot.beats")

    # Priority 0: explicit "use as final" approval (Spec A / LD-139).
    # _handle_use_as_final writes beat.final = {source, file, approved_at}
    # when Kim clicks "use as final (no lipsync)". This is the highest-
    # priority source — it overrides any lipsync that may exist for the
    # same beat (e.g. a stale lipsync against a now-removed source option).
    final = beat.get("final") or {}
    final_fname = final.get("file")
    if final_fname:
        final_candidate = (clips_dir / final_fname).resolve()
        if final_candidate.is_file():
            return final_candidate
        # final.file declared but missing on disk → fall through rather than
        # hard-failing, so a stale ref doesn't block preview.
        # final.file declared but missing on disk → fall through rather than
        # hard-failing, so a stale ref doesn't block preview. The lower-
        # priority sources still apply and the activity log captures the
        # mismatch on the next mutation.

    # Priority 1: lipsync finals (Bug 5 fix).
    lipsync = beat.get("lipsync") or {}
    if lipsync.get("status") == "completed":
        ls_fname = lipsync.get("file")
        if ls_fname:
            ls_candidate = (clips_dir / ls_fname).resolve()
            if ls_candidate.is_file():
                return ls_candidate
            # Lipsync file declared but missing on disk -> fall through to
            # phase_1 selection rather than failing, so a stale lipsync ref
            # doesn't block preview. Caller logs via activity log if desired.

    # Priority 2: phase_1 winner (fallback).
    phase1 = beat.get("phase_1") or {}
    selected = phase1.get("selected_option")
    if selected is None:
        raise FileNotFoundError(
            f"beat {beat_id!r} has no selected_option in phase_1 "
            f"and no completed lipsync",
        )
    options = phase1.get("options") or []
    try:
        sel_int = int(selected)
    except (TypeError, ValueError):
        raise FileNotFoundError(
            f"beat {beat_id!r} selected_option {selected!r} is not int-coercible",
        )
    if sel_int < 1 or sel_int > len(options):
        raise FileNotFoundError(
            f"beat {beat_id!r} selected_option {sel_int} out of range "
            f"(have {len(options)} options)",
        )
    fname = (options[sel_int - 1] or {}).get("file")
    if not fname:
        raise FileNotFoundError(
            f"beat {beat_id!r} option {sel_int} has no .file field",
        )
    candidate = (clips_dir / fname).resolve()
    if not candidate.is_file():
        raise FileNotFoundError(
            f"beat {beat_id!r} selected file does not exist: {candidate}",
        )
    return candidate


def beat_is_assemblable(beat: dict, event_dir: "Path | None" = None) -> bool:
    """Return True when Send Out / scene assemble can finalize this beat.

    A beat is assemblable when Kim has committed renderable media via ANY of:
      - phase_1.selected_option (classic animation path)
      - beat.final (use-as-final)
      - completed lipsync
      - magic_still_path / magic_video_path on disk (magic preview path)

    Magic-only beats (e.g. beat_02 with magic still, no selected_option) MUST
    be included — Kim's Storyboard magic preview is the commit signal.
    """
    if not isinstance(beat, dict):
        return False
    phase1 = beat.get("phase_1") or {}
    if phase1.get("selected_option") is not None:
        return True
    final = beat.get("final") or {}
    if final.get("file"):
        return True
    lipsync = beat.get("lipsync") or {}
    if lipsync.get("status") == "completed" and lipsync.get("file"):
        return True
    if event_dir is not None:
        for key in ("magic_still_path", "magic_video_path"):
            rel = beat.get(key)
            if rel and (Path(event_dir) / rel).is_file():
                return True
    return False


# ---------------------------------------------------------------------------
# Normalization (LD-284 recipe)
# ---------------------------------------------------------------------------
def mp4_decodes_cleanly(path: Path, *, timeout_s: int = 120) -> bool:
    """Return True when ffmpeg can decode every frame without H.264/AAC errors.

    Guards stitch preview LRU hits: ffprobe-only checks pass on truncated or
    bitstream-corrupt MP4s that render as a black <video> while WaveSurfer
    audio still plays (STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1).
    """
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "fatal",
                "-i", str(path.resolve()),
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
    ):
        return False
    return proc.returncode == 0 and not (proc.stderr or "").strip()


STITCH_PREVIEW_SKIP_NORMALIZE_V1 = "STITCH_PREVIEW_SKIP_NORMALIZE_V1"


def stitch_preview_can_use_source_directly(path: Path) -> bool:
    """True when slot MP4 is already LD-284-shaped — skip se_norm_* preview re-encode.

    Phase A/B dry exports are normalize_for_concat outputs (1280×720 H.264 + AAC).
    Re-normalizing into stitch_editor_cache only adds latency and poisoned-cache risk.
    """
    path = Path(path)
    if not path.is_file():
        return False
    if not mp4_decodes_cleanly(path, timeout_s=45):
        return False
    if not mp4_operator_playback_timestamps_safe(path):
        return False
    if not _has_audio_stream(path):
        return False
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,pix_fmt",
                "-of", "json", str(path.resolve()),
            ],
            capture_output=True, check=True, text=True, timeout=15,
        )
        data = json.loads(out.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return False
        v = streams[0]
        if (v.get("codec_name") or "").lower() != "h264":
            return False
        if int(v.get("width") or 0) != 1280 or int(v.get("height") or 0) != 720:
            return False
        if (v.get("pix_fmt") or "").lower() != "yuv420p":
            return False
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False
    return True


# H.264 B-frames place the first displayed frame at DTS ≈ -1/fps (e.g. -0.083s at 24fps).
# That is normal and browser-safe; gates target concat drift holes (large positive DTS)
# and deep negative concat offsets — not standard encoder B-frame lead-in.
H264_BFRAME_DTS_TOLERANCE_S = 0.1

# STITCH_MP4_PLAYBACK_TIMESTAMPS_V1 — QuickTime stalls on negative video DTS at file head.
STITCH_MP4_PLAYBACK_TIMESTAMPS_V1 = "STITCH_MP4_PLAYBACK_TIMESTAMPS_V1"


def mp4_first_video_dts_s(path: Path) -> float | None:
    """Return DTS (seconds) of the first video packet, or None when unknown."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_packets",
                "-read_intervals", "0%+0.5",
                "-show_entries", "packet=dts_time",
                "-of", "csv=p=0",
                str(path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            return float(line)
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        ValueError,
    ):
        return None
    return None


def mp4_quicktime_timestamps_safe(path: Path) -> bool:
    """True when first video DTS is not a deep-negative concat offset (QuickTime-safe)."""
    dts = mp4_first_video_dts_s(path)
    if dts is None:
        return False
    return dts >= -H264_BFRAME_DTS_TOLERANCE_S


def mp4_first_video_dts_near_zero(
    path: Path,
    *,
    eps_s: float = H264_BFRAME_DTS_TOLERANCE_S,
) -> bool:
    """True when the first video packet DTS is at timeline zero (Chrome MSE-safe)."""
    dts = mp4_first_video_dts_s(path)
    if dts is None:
        return False
    return -eps_s <= dts <= eps_s


def ffprobe_audio_start_time(path: Path) -> float:
    """Return audio stream start_time in seconds, or 0.0 when absent or unknown."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "a:0",
             "-show_entries", "stream=start_time",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(path.resolve())],
            capture_output=True, timeout=10,
        )
        raw = out.stdout.decode("utf-8", errors="replace").strip()
        val = float(raw)
        return val if val > 0 else 0.0
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return 0.0


def mp4_operator_playback_timestamps_safe(path: Path, *, start_eps_s: float = 0.001) -> bool:
    """True when MP4 is safe for Chrome/HTML5 mid-stream playback.

    Requires first video packet DTS near timeline zero *and* zero-based A/V stream
    start metadata. Chrome stalls on a positive DTS hole (e.g. 1.83s) even when
    stream start_time is 0.
    """
    if not mp4_quicktime_timestamps_safe(path):
        return False
    if not mp4_first_video_dts_near_zero(path, eps_s=start_eps_s):
        return False
    v_start = ffprobe_video_start_time(path)
    if v_start > start_eps_s:
        return False
    a_start = ffprobe_audio_start_time(path)
    return a_start <= start_eps_s


def _remux_mp4_copy_safe(path: Path, *, timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> None:
    """Copy remux with avoid_negative_ts + faststart (no stream rebase)."""
    path = Path(path)
    tmp = path.parent / f"{path.stem}.copy_safe.{os.getpid()}{path.suffix}"
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(path.resolve()),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            timeout=timeout_s,
        )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def normalize_mp4_browser_playback_timeline(
    path: Path,
    *,
    timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S,
) -> Path:
    """In-place heal: QuickTime-safe DTS + Chrome timeline zero + zero-based A/V start."""
    path = Path(path)
    if not path.is_file() or mp4_operator_playback_timestamps_safe(path):
        return path

    if not mp4_quicktime_timestamps_safe(path):
        _remux_mp4_copy_safe(path, timeout_s=timeout_s)
        if mp4_operator_playback_timestamps_safe(path):
            return path

    if not mp4_operator_playback_timestamps_safe(path):
        tmp = path.parent / f"{path.stem}.browser_norm.{os.getpid()}{path.suffix}"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(path.resolve()),
                    "-vf", "setpts=PTS-STARTPTS",
                    "-af", "asetpts=PTS-STARTPTS",
                    *AUX_H264_ENCODER_ARGS,
                    "-movflags", "+faststart",
                    str(tmp),
                ],
                check=True,
                capture_output=True,
                timeout=timeout_s,
            )
            os.replace(tmp, path)
        except subprocess.CalledProcessError:
            # Corrupt/truncated cache — caller decode gate will purge; never raise.
            pass
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    return path


def rebase_mp4_stream_start_times(path: Path, *, timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> Path:
    """Shift all streams to t=0 via copy remux (fixes post-mix non-zero start_time)."""
    path = Path(path)
    offset_s = ffprobe_video_start_time(path)
    if offset_s <= 0.001:
        offset_s = ffprobe_audio_start_time(path)
    if offset_s <= 0.001:
        return path
    tmp = path.parent / f"{path.stem}.rebase.{os.getpid()}{path.suffix}"
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(path.resolve()),
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c", "copy",
                "-output_ts_offset", f"-{offset_s:.6f}",
                "-movflags", "+faststart",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            timeout=timeout_s,
        )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return path


def remux_mp4_playback_safe(path: Path, *, timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> Path:
    """In-place remux: non-negative timestamps + faststart for QuickTime parity."""
    path = Path(path)
    tmp = path.parent / f"{path.stem}.playback_safe.{os.getpid()}{path.suffix}"
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(path.resolve()),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            timeout=timeout_s,
        )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    if not mp4_operator_playback_timestamps_safe(path):
        rebase_mp4_stream_start_times(path, timeout_s=timeout_s)
    return path


def mp4_is_playable(path: Path, *, min_duration_s: float = 0.05) -> bool:
    """Return True when path is a readable MP4 with streams and positive duration.

    Guards stitch-editor LRU caches against partially-written normalize outputs
    (broken moov → nb_streams=0) that otherwise pass ``Path.is_file()``.
    """
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration:stream=codec_type",
                "-of", "json",
                str(path.resolve()),
            ],
            capture_output=True, check=True, text=True, timeout=15,
        )
        payload = json.loads(out.stdout or "{}")
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ):
        return False

    streams = payload.get("streams") or []
    if not streams:
        return False
    try:
        dur = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        return False
    return dur >= min_duration_s


def stitch_audio_cache_is_valid(
    path: Path,
    expected_duration_s: float,
    *,
    min_ratio: float = 0.85,
) -> bool:
    """True when cached stitch waveform extract/mix duration matches source video.

    Guards ``stitch_audio_*.mp3`` LRU hits: interrupted ffmpeg writes can produce
    ~15s extracts while the slot video is ~40s — WaveSurfer then caps linked playback.
    """
    if expected_duration_s <= 0:
        return path.is_file() and path.stat().st_size > 1024
    if not path.is_file():
        return False
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(path.resolve()),
            ],
            capture_output=True, check=True, text=True, timeout=15,
        )
        dur = float((out.stdout or "").strip())
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
    ):
        return False
    return dur >= expected_duration_s * min_ratio


def preview_cache_is_valid(
    path: Path,
    expected_duration_s: float,
    *,
    min_ratio: float = 0.85,
) -> bool:
    """True when cached stitch preview duration matches the pipeline expectation.

    Guards ``stitch_preview_*.mp4`` LRU hits: partial concat writes can produce
    ~1s playable files that pass ``mp4_is_playable`` but freeze the UI player.

    STITCH_MODULE_BAKE_AV_PARITY_V1: also reject when video/audio stream
    durations diverge (format duration follows the longest stream — usually audio).
    """
    if expected_duration_s <= 0:
        return mp4_is_playable(path)
    if not mp4_is_playable(path):
        return False
    if not mp4_decodes_cleanly(
        path,
        timeout_s=stitch_preview_decode_timeout_s(expected_duration_s),
    ):
        return False
    if av_duration_drift_s(path) > STITCH_EXPORT_AV_MAX_DRIFT_S:
        return False
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(path.resolve()),
            ],
            capture_output=True, check=True, text=True, timeout=15,
        )
        dur = float((out.stdout or "").strip())
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
    ):
        return False
    return dur >= expected_duration_s * min_ratio


def _has_audio_stream(src: Path) -> bool:
    """Return True iff src has at least one audio stream. Used to guarantee
    normalized outputs always have an audio track (Bug 4 fix, preflight 103):
    Kling animation clips are generated with `sound: false` per CLAUDE.md §8.1,
    so they arrive audio-less. Without a silent-audio fallback, downstream
    xfade/acrossfade filter graphs fail with 'Stream specifier :a matches no
    streams' (ffmpeg rc=234) once Bug 3's -vf collision is fixed.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", str(src.resolve())],
            capture_output=True, check=True, text=True, timeout=10,
        ).stdout.strip()
        return bool(out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _normalize_to_encoder_spec(
    src: Path,
    dst: Path,
    *,
    encoder_args: tuple[str, ...],
    timeout_s: int,
) -> None:
    """Re-encode src at dst with LD-284 vf + supplied encoder args (atomic tmp+rename)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    has_audio = _has_audio_stream(src)
    video_start_s = ffprobe_video_start_time(src)
    fuse_ss_args: list[str] = []
    if video_start_s > 0.005:
        fuse_ss_args = ["-ss", f"{video_start_s:.3f}"]
    ffmpeg_args = ("-vf", NORMALIZATION_VF_EXPR, *encoder_args)
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            *fuse_ss_args,
            "-i", str(src.resolve()),
        ]
        if not has_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-shortest",
                    "-map", "0:v:0", "-map", "1:a:0"]
        cmd += [*ffmpeg_args, str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def normalize_for_concat(src: Path, dst: Path,
                         timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> None:
    """Re-encode src to the LD-284 canonical codec spec at dst.

    Atomic via tmp+rename on the dst path so a crashed/cancelled run never
    leaves a partially-written normalized file that downstream concat would
    silently use.

    Bug 4 fix (preflight 103): if src lacks an audio stream, inject a silent
    anullsrc input so the output always has audio. Guarantees the invariant
    'every normalized clip has a video stream AND an audio stream' for all
    downstream filter graphs (xfade, concat demuxer).
    """
    _normalize_to_encoder_spec(
        src, dst,
        encoder_args=NORMALIZATION_ENCODER_ARGS,
        timeout_s=timeout_s,
    )


# Stitch slot preview — fast CRF encode; separate cache key (_pv suffix) at caller.
STITCH_PREVIEW_NORMALIZE_TIMEOUT_S = 300
STITCH_PREVIEW_NORMALIZE_V1 = "STITCH_PREVIEW_NORMALIZE_V1"


def normalize_for_stitch_preview(
    src: Path,
    dst: Path,
    *,
    timeout_s: int = STITCH_PREVIEW_NORMALIZE_TIMEOUT_S,
) -> None:
    """Preview-only normalize: same 1280×720 vf as LD-284, fast CRF for mux rebuild."""
    _normalize_to_encoder_spec(
        src, dst,
        encoder_args=PREVIEW_OVERLAY_ENCODER_ARGS,
        timeout_s=timeout_s,
    )


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------
def translate_trim_for_source(
    beat: dict,
    source_file_name: str,
    source_file_path: Path,
    trim_start: float | None,
    trim_end: float | None,
    trim_back: float | None = None,
) -> tuple[float | None, float | None]:
    """Translate phase_1 trim_start/trim_end from the ORIGINAL TTS timeline
    into the ACTUAL source file's timeline.

    Why: trim_start/trim_end were authored against the original Kling clip
    (5s or 10s duration matching trim window). After lipsync, the source file
    becomes the lipsync mp4, which has a DIFFERENT timeline — ByteDance
    prepends preroll and we extend the tail by 1.5s. Applying the absolute
    trim_end directly to the lipsync mp4 cuts off speech mid-word (Kim
    symptom 2026-05-21 on beat_05: trim_end=3.35 hit '...mindfuln-' instead
    of '...mindfulnest' because lipsync mp4 was 4.36s long and speech ran
    ~0.4s → ~3.76s within the mp4 timeline).

    Translation rules (lipsync mp4 case ONLY — raw_option / still_image
    finals keep their original timeline since trim_end was authored against
    the same source):

      back_offset_s   = audio_duration_s - trim_end_absolute     # user input
      new_trim_end    = lipsync_mp4_duration - back_offset_s
      gen_ls_start    = lipsync.audio_processing.trim_start      # ts_used at generation
      new_trim_start  = max(0, trim_start - gen_ls_start)

    STITCH_FRONT_TRIM_FIX_20260524: trim_start is now also translated into
    the lipsync file's timeline using the same delta used by the UI preview
    (LIPSYNC_SEEK_FIX_20260524). gen_ls_start = the lipsync_start at
    generation time (ts_used = trim_start + audio_delay_sec), stored as
    beat.lipsync.audio_processing.trim_start. Examples:
      beat_09: gen=0, current=3  → new_trim_start=3  (trims 3s off existing file)
      beat_03: gen=1.5, current=1.5 → new_trim_start=0 (no double-trim after resend)
      old files (no audio_processing): gen=0 → new_trim_start=current_trim_start (unchanged)

    Returns (translated_trim_start, translated_trim_end). When translation
    isn't applicable (no lipsync, missing audio_duration_s, source isn't the
    lipsync mp4), returns the inputs unchanged.
    """
    if trim_end is None:
        # trim_back support: "remove N seconds from the end of the source file".
        # trim_back is ALWAYS relative to the resolved source file's own timeline
        # (whether raw Kling clip or lipsync mp4 — it was authored while Kim
        # watched that specific file). So no lipsync-timeline translation is
        # needed here; we just compute effective_trim_end = src_dur - trim_back.
        if trim_back is not None and float(trim_back) > 0:
            try:
                src_dur = ffprobe_duration(source_file_path)
            except Exception:
                return (trim_start, None)
            effective_end = max(
                float(trim_start or 0.0) + 0.01,
                src_dur - float(trim_back),
            )
            return (trim_start, effective_end)
        return (trim_start, None)
    lipsync_block = (beat or {}).get("lipsync") or {}
    lipsync_file = lipsync_block.get("file")
    if not lipsync_file:
        return (trim_start, trim_end)
    if Path(source_file_name).name != Path(lipsync_file).name:
        return (trim_start, trim_end)
    if lipsync_block.get("status") != "completed":
        return (trim_start, trim_end)
    audio_dur = beat.get("audio_duration_s")
    try:
        audio_dur_f = float(audio_dur) if audio_dur is not None else None
    except (TypeError, ValueError):
        audio_dur_f = None
    if audio_dur_f is None or audio_dur_f <= 0:
        return (trim_start, trim_end)
    try:
        lipsync_dur = ffprobe_duration(source_file_path)
    except Exception:
        return (trim_start, trim_end)
    # STITCH_FRONT_TRIM_FIX_20260524: translate trim_start into lipsync timeline.
    # gen_ls_start = lipsync_start at generation time (ts_used, stored as
    # audio_processing.trim_start by vendor_jobs.py mark_done).
    gen_ls_start = float(
        (lipsync_block.get("audio_processing") or {}).get("trim_start") or 0
    )
    new_trim_start: float | None
    if trim_start is None:
        new_trim_start = None
    else:
        new_trim_start = max(0.0, float(trim_start) - gen_ls_start)
    back_offset = max(0.0, audio_dur_f - float(trim_end))
    new_end = max(float(new_trim_start or 0.0) + 0.01, lipsync_dur - back_offset)
    return (new_trim_start, new_end)


def trim_normalized(src: Path, dst: Path,
                    trim_start: float | None,
                    trim_end: float | None,
                    audio_delay: float = 0.0,
                    mix_audio_path: "Path | None" = None,
                    freeze_tail_s: float = 0.0,
                    timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> float:
    """Trim src to [trim_start, trim_end] window at dst. Returns effective duration.

    None on either bound means "no trim on that side". Re-encodes (libx264) so
    the trim is frame-accurate, matching LIPSYNC_TRIM_WINDOW_HONORED at
    production_server.py:1985-1993.

    audio_delay (April 26 2026 — wired through per Kim's call after slider
    appeared inert in Preview-All-Stitched): if > 0, applies an `adelay` audio
    filter so the audio stream starts at t=audio_delay seconds. Video plays
    from t=0 of the trim window with no audio for the lead-in period, then
    audio enters. Mirrors the per-beat Preview Beat client-side behavior at
    storyboard_v46_prod.html where vid plays muted while audio is delayed
    by setTimeout. Audio that extends past the trim window is naturally
    clipped by ffmpeg's -t duration cap (mp4 ends when video ends).

    freeze_tail_s (2026-05-27 — magic_still tail fix): when > 0 and
    mix_audio_path is provided, probes the audio duration and ensures the
    output is at least audio_dur + freeze_tail_s long. If the source video
    is shorter than that target, freeze-extends the last frame via tpad.
    Used for magic_still beats (is_magic_source=True) so the still image
    holds on screen for freeze_tail_s seconds after speech ends.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_dur = ffprobe_duration(src)
    start = float(trim_start) if trim_start is not None else 0.0
    end = float(trim_end) if trim_end is not None else src_dur
    if start < 0:
        start = 0.0
    if end > src_dur:
        end = src_dur
    if end <= start:
        raise ValueError(
            f"trim_normalized({src.name}): trim_end ({end}) must be > "
            f"trim_start ({start}); src_dur={src_dur:.3f}",
        )
    duration = end - start
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    try:
        if mix_audio_path is not None and mix_audio_path.is_file():
            # Raw-option beat: the source clip has no audio (generated with
            # sound: false per CLAUDE.md §8.1). Mix the speech MP3 in place
            # of the silent anullsrc, offset to audio_delay seconds into the
            # output clip. apad pads the audio stream to the full output
            # duration so the codec doesn't truncate early.
            # Note: -vf cannot coexist with -map when using -filter_complex;
            # src is already at canonical codec from normalize_for_concat so
            # we skip the VF re-pass and use NORMALIZATION_ENCODER_ARGS only.
            delay_ms = int(round(float(audio_delay) * 1000))

            # freeze_tail_s: for magic_still beats, ensure output covers
            # audio_dur + freeze_tail_s. If source video is too short, tpad
            # freezes the last frame to fill the gap.
            target_duration = duration
            extra_freeze = 0.0
            if freeze_tail_s > 0:
                audio_dur = ffprobe_duration(mix_audio_path)
                target_duration = max(duration, audio_dur + float(freeze_tail_s))
                extra_freeze = max(0.0, target_duration - duration)

            if extra_freeze > 0.01:
                # One-pass: freeze-extend video + mix audio, all in filter_complex.
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.3f}",
                    "-i", str(src.resolve()),
                    "-i", str(mix_audio_path.resolve()),
                    "-filter_complex",
                    f"[0:v]tpad=stop_mode=clone:stop_duration={extra_freeze:.3f}[v];"
                    f"[1:a]adelay={delay_ms}:all=1,apad[a]",
                    "-map", "[v]",
                    "-map", "[a]",
                    "-t", f"{target_duration:.3f}",
                    *NORMALIZATION_ENCODER_ARGS,
                    str(tmp),
                ]
            else:
                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.3f}",
                    "-i", str(src.resolve()),
                    "-i", str(mix_audio_path.resolve()),
                    "-t", f"{target_duration:.3f}",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-af", f"adelay={delay_ms}:all=1,apad",
                    *NORMALIZATION_ENCODER_ARGS,
                    str(tmp),
                ]
        else:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{start:.3f}",
                "-i", str(src.resolve()),
                "-t", f"{duration:.3f}",
            ]
            if audio_delay and audio_delay > 0:
                delay_ms = int(round(float(audio_delay) * 1000))
                # adelay=ms:all=1 delays every audio channel uniformly. Mono
                # output (-ac 1 in NORMALIZATION_FFMPEG_ARGS) means one channel
                # but :all=1 is a safe no-op on mono and future-proofs against
                # a stereo bump.
                cmd += ["-af", f"adelay={delay_ms}:all=1"]
            cmd += [*NORMALIZATION_FFMPEG_ARGS, str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return ffprobe_duration(dst)


def trim_body(src: Path, dst: Path,
              head_remove_s: float, tail_remove_s: float,
              timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> float:
    """Remove head_remove_s from the start AND tail_remove_s from the end
    of src in a single ffmpeg pass. Returns new duration.

    Preflight 118 fix: the mixed-fade pipeline (per-beat fade_after_ms) needs
    to head-trim the INCOMING side of each xfade pair — the first fade_s
    seconds of the incoming beat are already carried by the xfade_pair clip,
    so leaving them in the body makes them play twice at the concat boundary.
    This function handles both head and tail trims atomically per beat.

    Either trim value can be 0; if both are 0, callers should short-circuit
    and use the source file directly rather than call this (saves an ffmpeg
    pass).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_dur = ffprobe_duration(src)
    new_start = max(0.0, float(head_remove_s))
    new_end = max(new_start, src_dur - max(0.0, float(tail_remove_s)))
    new_dur = new_end - new_start
    if new_dur <= 0:
        raise ValueError(
            f"trim_body({src.name}): head={head_remove_s}s tail={tail_remove_s}s "
            f"would empty the clip (src_dur={src_dur:.3f})",
        )
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{new_start:.3f}",
            "-i", str(src.resolve()),
            "-t", f"{new_dur:.3f}",
            *NORMALIZATION_FFMPEG_ARGS,
            str(tmp),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return new_dur


def trim_body_with_fade(
    src: Path, dst: Path,
    head_remove_s: float, tail_remove_s: float,
    fade_in_s: float = 0.0, fade_out_s: float = 0.0,
    *,
    fade_audio: bool = True,
    timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S,
) -> float:
    """Trim head/tail AND apply fade-through-black filters in one ffmpeg pass.

    FADE_THROUGH_BLACK_20260525: handles the "fade through black" transition
    pattern where pause_after_ms>0 is combined with a per-pair crossfade value.
    Unlike xfade (which overlaps both clips simultaneously and shows ghost frames
    during the pause), this fades each beat's body independently to/from black so
    the pause clip is pure black with no double-exposure artifacts.

    head_remove_s / tail_remove_s: same semantics as trim_body() — can be 0
    fade_in_s:  fade-from-black on the trimmed clip's START  (0 = skip)
    fade_out_s: fade-to-black   on the trimmed clip's END    (0 = skip)
    fade_audio: when False, only video fades (audio full level until hard cut;
                matches Stitcher dissolve with audio_xfade_ms=0).
    Returns new duration after trimming (fade filters do not remove frames).
    """
    src_dur = ffprobe_duration(src)
    new_start = max(0.0, float(head_remove_s))
    new_end = max(new_start, src_dur - max(0.0, float(tail_remove_s)))
    new_dur = new_end - new_start
    if new_dur <= 0:
        raise ValueError(
            f"trim_body_with_fade({src.name}): head={head_remove_s}s "
            f"tail={tail_remove_s}s would empty the clip (src_dur={src_dur:.3f})",
        )

    vf_parts: list[str] = []
    af_parts: list[str] = []
    if fade_in_s > 0:
        vf_parts.append(f"fade=t=in:st=0:d={fade_in_s:.3f}")
        if fade_audio:
            af_parts.append(f"afade=t=in:st=0:d={fade_in_s:.3f}")
    if fade_out_s > 0:
        # fade_out_start is relative to the OUTPUT (trimmed) timeline.
        fade_out_start = max(0.0, new_dur - fade_out_s)
        vf_parts.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_out_s:.3f}")
        if fade_audio:
            af_parts.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_s:.3f}")

    # Chain fade filters before normalization (scale/pad/fps/setsar).
    vf_chain = (
        ",".join(vf_parts + [NORMALIZATION_VF_EXPR])
        if vf_parts else NORMALIZATION_VF_EXPR
    )

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{new_start:.3f}",
            "-i", str(src.resolve()),
            "-t", f"{new_dur:.3f}",
            "-vf", vf_chain,
        ]
        if af_parts:
            cmd += ["-af", ",".join(af_parts)]
            cmd += [*NORMALIZATION_ENCODER_ARGS, str(tmp)]
        else:
            cmd += [
                "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-preset", VIDEO_QUALITY_PRESET_BAKE, "-g", "48",
                "-crf", VIDEO_QUALITY_CRF,
                "-c:a", "copy",
                "-movflags", "+faststart",
                str(tmp),
            ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return new_dur


def render_black_pause_clip(
    duration_s: float,
    dest: Path,
    *,
    timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S,
) -> Path:
    """Silent black filler at LD-284 codec (inserted BETWEEN clips, not inside them)."""
    duration_s = max(0.05, float(duration_s))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f"{dest.stem}.tmp.{os.getpid()}{dest.suffix}"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=24",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
        "-t", f"{duration_s:.3f}",
        "-shortest",
        "-map", "0:v:0", "-map", "1:a:0",
        *NORMALIZATION_ENCODER_ARGS,
        str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dest


def module_slot_start_offsets_ms(
    slot_durations_ms: list[int],
    pair_fades_ms: list[int],
    *,
    visual_out_ms: int = DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS,
    visual_in_ms: int = DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS,
) -> list[int]:
    """Start offset of each logical slot inside a module preview after black-pause inserts."""
    if not slot_durations_ms:
        return []
    starts = [0]
    acc = 0
    for i in range(len(slot_durations_ms) - 1):
        acc += int(slot_durations_ms[i])
        pair = int(pair_fades_ms[i]) if i < len(pair_fades_ms) else 0
        if pair > 0:
            _, _, black_ms = allocate_pair_fade_budget(
                pair,
                visual_out_ms=visual_out_ms,
                visual_in_ms=visual_in_ms,
            )
            acc += black_ms
        starts.append(acc)
    return starts


def allocate_pair_fade_budget(
    pair_ms: int,
    *,
    visual_out_ms: int = DEFAULT_FADE_THROUGH_BLACK_VISUAL_OUT_MS,
    visual_in_ms: int = DEFAULT_FADE_THROUGH_BLACK_VISUAL_IN_MS,
    min_black_ms: int = DEFAULT_MIN_BLACK_PAUSE_MS,
) -> tuple[int, int, int]:
    """Split boundary budget: short clip fades + black hold (does not eat dialogue).

    Black-pause inserts time *between* clips. Do not clamp ``pair_ms`` to beat
    duration — that was the xfade-overlap bug that eliminated black holds on
    shorter beats and dimmed speech tails.
    """
    pair_ms = max(0, int(pair_ms))
    if pair_ms <= 0:
        return 0, 0, 0
    target_black = min(min_black_ms, max(0, pair_ms - 200))
    visual_budget = max(0, pair_ms - target_black)
    out_ms = min(visual_out_ms, visual_budget // 2 if visual_budget else 0)
    in_ms = min(visual_in_ms, max(0, visual_budget - out_ms))
    black_ms = max(0, pair_ms - out_ms - in_ms)
    return out_ms, in_ms, black_ms


def expand_clips_with_black_pause_boundaries(
    clips: list[Path],
    pair_fades_ms: list[int],
    scratch_dir: Path,
    *,
    visual_out_ms: int = 600,
    visual_in_ms: int = 600,
    visual_out_ms_by_pair: list[int] | None = None,
    fade_audio: bool = False,
) -> list[Path]:
    """Fade-through-black with inserted black hold — does not eat dialogue time.

    pair_fades_ms[i] is the total boundary budget between clips[i] and clips[i+1]:
    short fade-out on clip i, optional black hold, short fade-in on clip i+1.
    """
    if not clips:
        return []
    scratch_dir.mkdir(parents=True, exist_ok=True)
    n = len(clips)
    if len(pair_fades_ms) != max(0, n - 1):
        raise ValueError(
            f"expand_clips_with_black_pause_boundaries: len(pair_fades_ms)="
            f"{len(pair_fades_ms)} expected {max(0, n - 1)}",
        )
    parts: list[Path] = []
    for i, clip in enumerate(clips):

        def _pair_visual_out(pair_idx: int) -> int:
            if (
                visual_out_ms_by_pair is not None
                and 0 <= pair_idx < len(visual_out_ms_by_pair)
            ):
                return int(visual_out_ms_by_pair[pair_idx])
            return visual_out_ms

        fade_in_ms = (
            allocate_pair_fade_budget(
                pair_fades_ms[i - 1],
                visual_out_ms=_pair_visual_out(i - 1),
                visual_in_ms=visual_in_ms,
            )[1]
            if i > 0 and pair_fades_ms[i - 1] > 0 else 0
        )
        fade_out_ms = (
            allocate_pair_fade_budget(
                pair_fades_ms[i],
                visual_out_ms=_pair_visual_out(i),
                visual_in_ms=visual_in_ms,
            )[0]
            if i < n - 1 and pair_fades_ms[i] > 0 else 0
        )
        fade_in_s = fade_in_ms / 1000.0
        fade_out_s = fade_out_ms / 1000.0
        if fade_in_s > 0.0 or fade_out_s > 0.0:
            body = scratch_dir / (
                f"black_pause_body_{i:02d}_{clip.stem}_"
                f"fi{fade_in_s:.3f}_fo{fade_out_s:.3f}.mp4"
            )
            trim_body_with_fade(
                clip, body,
                head_remove_s=0.0,
                tail_remove_s=0.0,
                fade_in_s=fade_in_s,
                fade_out_s=fade_out_s,
                fade_audio=fade_audio,
            )
            parts.append(body)
        else:
            parts.append(clip)
        if i < n - 1 and pair_fades_ms[i] > 0:
            _, _, black_ms = allocate_pair_fade_budget(
                pair_fades_ms[i],
                visual_out_ms=_pair_visual_out(i),
                visual_in_ms=visual_in_ms,
            )
            if black_ms > 0:
                black = scratch_dir / f"black_pause_{i:02d}_{black_ms}ms.mp4"
                render_black_pause_clip(black_ms / 1000.0, black)
                parts.append(black)
    return parts


def trim_tail(src: Path, dst: Path, tail_remove_s: float,
              timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> float:
    """Remove tail_remove_s seconds from the end of src. Returns new duration.

    Used to produce beat_NN_body files that have the trailing fade region
    removed so the xfade pair clip carries the only copy of those frames
    (avoids duplicate frames at concat).

    Counter (f) CRITICAL mitigation: only call this on beats 0..N-2; the LAST
    beat keeps its full trimmed duration so the preview ends on the actual
    final frame, not chopped mid-word.

    Preflight 118: `trim_body(src, dst, 0, tail_remove_s)` is an equivalent
    modern replacement for this — kept for backward compatibility with all-
    fades-global pipeline.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_dur = ffprobe_duration(src)
    new_dur = max(0.0, src_dur - max(0.0, tail_remove_s))
    if new_dur <= 0:
        raise ValueError(
            f"trim_tail({src.name}): tail_remove_s={tail_remove_s} would "
            f"empty the clip (src_dur={src_dur:.3f})",
        )
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src.resolve()),
            "-t", f"{new_dur:.3f}",
            *NORMALIZATION_FFMPEG_ARGS,
            str(tmp),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return new_dur


# ---------------------------------------------------------------------------
# Fade clamp (2-sided, floor at 0)
# ---------------------------------------------------------------------------
def compute_fade_clamp(durations: list[float], fade_ms: int) -> int:
    """Return the effective fade duration in ms, 2-sided clamped.

    Counter (b) MEDIUM mitigations rolled in:
      * Empty durations => raise ValueError (caller maps to 400).
      * fade_ms <= 0 => return 0 (caller fast-paths to plain concat, no xfade).
      * Negative result floored at 0 (avoids ffmpeg xfade duration<=0 error).
    """
    if not durations:
        raise ValueError("compute_fade_clamp: empty durations list")
    fade_s = max(0.0, float(fade_ms) / 1000.0)
    if fade_s == 0.0:
        return 0
    min_dur = min(durations)
    max_safe_s = max(0.0, min_dur - FADE_CLAMP_BUFFER_S)
    effective_s = min(fade_s, max_safe_s)
    return int(round(effective_s * 1000.0))


# ---------------------------------------------------------------------------
# Per-pair xfade render (no cumulative offset drift)
# ---------------------------------------------------------------------------
def render_xfade_pair(file_a: Path, file_b: Path, fade_ms: int,
                      dst: Path, dur_a: float,
                      timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> None:
    """Render a 2-input ffmpeg xfade pair clip at dst (~fade_ms of footage).

    offset = dur_a - fade_s (the moment within file_a when the crossfade
    begins). Fresh subprocess per pair, so offsets never accumulate across
    multiple pair renders.
    """
    if fade_ms <= 0:
        raise ValueError(
            f"render_xfade_pair: fade_ms={fade_ms} must be > 0; caller should "
            "fast-path to plain concat instead",
        )
    fade_s = fade_ms / 1000.0
    offset = max(0.0, dur_a - fade_s)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    try:
        # We render only the crossfade window itself: -t fade_s on the output.
        # acrossfade is paired with xfade so the audio and video transitions
        # stay phase-aligned.
        # Bug 3 fix (preflight 103): -vf cannot coexist with -filter_complex on
        # the same stream (ffmpeg rc=234). Chain NORMALIZATION_VF_EXPR into
        # the filter_complex tail so scale/pad/fps still run on every output
        # frame (defense-in-depth preserved), then use ENCODER_ARGS (no -vf)
        # at the cmd level.
        filter_complex = (
            f"[0:v][1:v]xfade=transition=fade:duration={fade_s:.3f}:offset={offset:.3f}[vx];"
            f"[vx]{NORMALIZATION_VF_EXPR}[v];"
            f"[0:a][1:a]acrossfade=d={fade_s:.3f}[a]"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(file_a.resolve()),
            "-i", str(file_b.resolve()),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", f"{fade_s:.3f}",  # only the crossfade window
            "-ss", f"{offset:.3f}",  # start at the offset (carve the window)
            *NORMALIZATION_ENCODER_ARGS,
            str(tmp),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Concat demuxer (absolute escaped paths)
# ---------------------------------------------------------------------------
def _concat_demuxer_mp4(
    parts: list[Path],
    output_path: Path,
    *,
    copy_streams: bool,
    timeout_s: int,
) -> None:
    """Write ``output_path`` from concat demuxer list (atomic tmp+rename)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = output_path.with_suffix(output_path.suffix + ".concat.txt")
    concat_list.write_text(
        "\n".join(_escape_for_concat(p) for p in parts) + "\n",
        encoding="utf-8",
    )
    tmp = output_path.parent / f"{output_path.stem}.tmp.{os.getpid()}{output_path.suffix}"
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list.resolve()),
        ]
        if copy_streams:
            cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        else:
            cmd += ["-vf", NORMALIZATION_VF_EXPR, *NORMALIZATION_ENCODER_ARGS]
        cmd += ["-movflags", "+faststart", str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, output_path)
    finally:
        for p in (concat_list, tmp):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


def concat_with_xfade_clips(parts: list[Path], output_path: Path,
                            timeout_s: int = DEFAULT_FFMPEG_TIMEOUT_S) -> Path:
    """Concat a list of pre-rendered, codec-identical mp4 parts into output_path.

    Reuses the proven concat-demuxer pattern at production_server.py:1926-1945
    (absolute paths via Path.resolve(), single-quoted with embedded-quote escape).

    Atomic via tmp+rename on output_path so partial writes never serve.

    STITCH_MODULE_BAKE_AV_PARITY_V1: ``-c copy`` can truncate video while audio
    continues; verify stream parity and fall back to LD-284 re-encode concat.
    """
    if not parts:
        raise ValueError("concat_with_xfade_clips: parts list is empty")
    _concat_demuxer_mp4(parts, output_path, copy_streams=True, timeout_s=timeout_s)

    # Forward refs — defined below in this module; resolved at call time.
    drift_s = av_duration_drift_s(output_path)
    if drift_s <= STITCH_EXPORT_AV_MAX_DRIFT_S:
        if not mp4_quicktime_timestamps_safe(output_path):
            remux_mp4_playback_safe(output_path, timeout_s=timeout_s)
        return output_path

    try:
        output_path.unlink()
    except OSError:
        pass

    reencode_timeout_s = max(timeout_s, 600)
    _concat_demuxer_mp4(
        parts,
        output_path,
        copy_streams=False,
        timeout_s=reencode_timeout_s,
    )
    drift_s = av_duration_drift_s(output_path)
    if drift_s > STITCH_EXPORT_AV_MAX_DRIFT_S:
        try:
            output_path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            "stitch concat blocked — module preview audio/video misaligned after "
            f"copy and re-encode fallback (drift {drift_s:.3f}s, "
            f"max {STITCH_EXPORT_AV_MAX_DRIFT_S}s)",
        )
    if not mp4_quicktime_timestamps_safe(output_path):
        remux_mp4_playback_safe(output_path, timeout_s=reencode_timeout_s)
    return output_path


# ---------------------------------------------------------------------------
# ffprobe duration (small wrapper)
# ---------------------------------------------------------------------------
STITCH_EXPORT_AV_MAX_DRIFT_S = 0.25


def stitch_preview_decode_timeout_s(duration_s: float) -> int:
    """ffmpeg null-decode budget scaled to clip length (module previews exceed 45s)."""
    if duration_s <= 0:
        return 45
    return max(45, min(600, int(duration_s * 0.5) + 30))


def ffprobe_stream_duration_s(path: Path, stream: str) -> float:
    """Return duration seconds for ``v`` (video) or ``a`` (audio); 0 if missing."""
    selector = "v:0" if stream == "v" else "a:0"
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", selector,
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return 0.0
        raw = (out.stdout or "").strip()
        return float(raw) if raw else 0.0
    except (ValueError, subprocess.TimeoutExpired):
        return 0.0


STITCH_EXPORT_AV_MAX_DRIFT_S = 0.25
STITCH_EXPORT_TIMELINE_AUTHORITY_V1 = "STITCH_EXPORT_TIMELINE_AUTHORITY_V1"
STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S = 0.05


def export_clip_timeline_duration_s(path: Path) -> float:
    """Single authority for concat boundaries and stitch slot geometry."""
    video_s = ffprobe_stream_duration_s(path, "v")
    audio_s = ffprobe_stream_duration_s(path, "a")
    if video_s > 0.0 and audio_s > 0.0:
        return min(video_s, audio_s)
    fmt = ffprobe_duration(path)
    return fmt if fmt > 0.0 else max(video_s, audio_s)


def assert_stitch_export_cumulative_av_aligned(
    clip_paths: list[Path],
    *,
    max_join_drift_s: float = STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S,
) -> None:
    """Simulate concat cursor using video stream ends — catch cumulative lipsync drift."""
    cursor_s = 0.0
    for clip in clip_paths:
        video_s = ffprobe_stream_duration_s(clip, "v")
        timeline_s = export_clip_timeline_duration_s(clip)
        if video_s > 0.0 and timeline_s > 0.0:
            drift = abs(timeline_s - video_s)
            if drift > max_join_drift_s:
                raise ValueError(
                    f"stitch export blocked — cumulative A/V drift at {clip.name}: "
                    f"{drift:.3f}s > {max_join_drift_s:.3f}s",
                )
        cursor_s += timeline_s


def av_duration_drift_s(path: Path) -> float:
    """Absolute video vs audio stream duration delta in seconds."""
    video_s = ffprobe_stream_duration_s(path, "v")
    audio_s = ffprobe_stream_duration_s(path, "a")
    if video_s <= 0.0 or audio_s <= 0.0:
        return 0.0
    return abs(video_s - audio_s)


def assert_stitch_export_clips_av_aligned(
    clip_paths: list[Path],
    *,
    max_drift_s: float = STITCH_EXPORT_AV_MAX_DRIFT_S,
) -> None:
    """Raise ValueError when any export clip has misaligned A/V streams."""
    bad: list[str] = []
    for clip in clip_paths:
        drift = av_duration_drift_s(clip)
        if drift > max_drift_s:
            bad.append(f"{clip.name} (drift {drift:.3f}s)")
    if bad:
        raise ValueError(
            "stitch export blocked — clip audio/video misaligned: "
            + "; ".join(bad),
        )


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path.resolve())],
        check=True, capture_output=True, timeout=30,
    )
    raw = out.stdout.decode("utf-8", errors="replace").strip()
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"ffprobe returned non-numeric duration {raw!r} for {path}")


def ffprobe_video_start_time(path: Path) -> float:
    """Return the PTS start_time of the first video stream in seconds, or 0.0.

    AV_FUSE_SS_20260525: ByteDance lipsync outputs have video.start_time≈22ms
    with audio.start_time=0.000. Used by normalize_for_concat() to detect this
    offset so it can fuse A/V streams at the demuxer level via -ss before -i.

    Returns 0.0 on any error (N/A, missing stream, timeout) so callers can
    treat 0 as "no offset needed" without special-casing exceptions.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=start_time",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(path.resolve())],
            capture_output=True, timeout=10,
        )
        raw = out.stdout.decode("utf-8", errors="replace").strip()
        val = float(raw)
        return val if val > 0 else 0.0
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# LRU cleanup (caller holds the dir-level lock — counter (d) HIGH)
# ---------------------------------------------------------------------------
_PREVIEW_FINAL_RE = re.compile(r"^preview_stitched_[0-9a-f]+\.mp4$")
# April 26 2026 audit: full_module_*.mp4 (and its norm/norm_audio side files)
# accumulated forever because the original LRU regex only matched
# preview_stitched_*. This pattern is opt-in via the `pattern=` kwarg so
# existing callers see no behavior change.
_FULL_MODULE_RE = re.compile(
    r"^full_module_[0-9a-f]+(?:_[A-Za-z_]+_norm(?:_audio)?)?\.mp4$"
)


def lru_cleanup(preview_dir: Path, keep: int = DEFAULT_LRU_KEEP,
                pattern: "re.Pattern | None" = None,
                pin_stems: "set[str] | None" = None) -> list[Path]:
    """Evict all but the `keep` most-recently-modified files matching
    `pattern` (defaults to preview_stitched_*.mp4) in preview_dir.
    Excludes .tmp and .lock files entirely.

    Pass pattern=_FULL_MODULE_RE for the timeline_cache directory, which
    holds full_module_*.mp4 plus its per-segment norm side files.

    Returns the list of evicted paths.

    CRITICAL: caller MUST hold the directory-level fcntl lock around BOTH the
    write that rotated in a new file AND this call. Otherwise two concurrent
    requests can both list, both pick the same victim, and one will
    FileNotFoundError on unlink (counter (d) HIGH).
    """
    if keep < 1:
        raise ValueError("lru_cleanup: keep must be >= 1")
    if not preview_dir.is_dir():
        return []
    pat = (re.compile(pattern) if isinstance(pattern, str) else pattern) if pattern is not None else _PREVIEW_FINAL_RE
    candidates: list[Path] = []
    for entry in preview_dir.iterdir():
        if not entry.is_file():
            continue
        if not pat.match(entry.name):
            continue
        candidates.append(entry)
    if len(candidates) <= keep:
        return []
    # Sort by st_mtime DESC (newest first); evict the tail.
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    to_evict = candidates[keep:]
    pinned = pin_stems or set()
    evicted: list[Path] = []
    for victim in to_evict:
        if pinned:
            stem = victim.stem
            for prefix in ("stitch_preview_", "stitch_peaks_", "stitch_audio_"):
                if stem.startswith(prefix):
                    stem = stem[len(prefix):]
                    break
            if stem in pinned:
                continue
        try:
            victim.unlink()
            evicted.append(victim)
        except FileNotFoundError:
            pass  # raced with another cleanup or manual removal
        except OSError:
            pass  # best-effort eviction; don't crash the request path
    return evicted


# ---------------------------------------------------------------------------
# Cache hash (one place — used both by tests and by the server endpoint)
# ---------------------------------------------------------------------------
def compute_cache_hash(state_snapshot: dict, fade_ms: int,
                       beat_ids_sorted: list[str],
                       clips_dir: Path) -> tuple[str, list[dict]]:
    """Compute the preview cache hash AND return per-beat resolution metadata.

    Tuple return: (hex_sha256, [{beat_id, file, mtime, trim_start, trim_end,
                                  pause_after_ms, selected_option}, ...])

    Counter (a) HIGH: file existence is verified by resolve_beat_file BEFORE
    any os.path.getmtime call; missing files raise FileNotFoundError so the
    caller short-circuits to a 400 with hint listing the missing beats.

    Counter (h) MEDIUM: pause_after_ms is included in the hash for cache
    safety (if v2.1 begins inserting silences between beats, an old cached
    file with the new hash semantics MUST NOT be served as-if-correct).
    Removing pause_after_ms from this hash without ALSO inserting silences in
    the recipe is a forbidden combination — see TECH_SPEC §pain-point map.
    """
    beats = state_snapshot.get("beats") or {}
    parts: list[str] = [
        f"recipe:{PREVIEW_RECIPE_VERSION}",
        f"fade:{fade_ms}",
        f"norm:{NORMALIZATION_RECIPE_HASH}",
    ]
    metadata: list[dict] = []
    for beat_id in beat_ids_sorted:
        beat = beats.get(beat_id) or {}
        phase1 = beat.get("phase_1") or {}
        path = resolve_beat_file(beat_id, state_snapshot, clips_dir)  # raises on miss
        mtime = os.path.getmtime(str(path))  # safe — existence already verified
        trim_start = phase1.get("trim_start", 0.0)
        trim_end = phase1.get("trim_end")  # None == no trim
        trim_back = phase1.get("trim_back")  # back-trim (None = not set)
        pause_after_ms = phase1.get("pause_after_ms", 0)
        selected = phase1.get("selected_option")
        # Per-item fade override (PER_ITEM_FADE_AFTER_OVERRIDE_V1, April 19 2026).
        # None == inherit global fade_ms; int == that pair's override. Folded
        # into the hash so a change to ANY beat's fade_after_ms invalidates the
        # preview cache. Without this, Kim would drag a slider and keep seeing
        # the old cached preview.
        fade_after_ms = phase1.get("fade_after_ms")
        # Per-beat audio_delay (Video Lead-in slider) — wired through April 26
        # 2026 per Kim's directive. Pre-fix: phase_1.audio_delay was written
        # by the slider but never read by the stitcher → silent no-op in
        # Preview-All-Stitched. Now in the cache hash so slider drags
        # correctly invalidate the cache, and applied via adelay filter
        # in trim_normalized below.
        audio_delay = phase1.get("audio_delay", 0.0) or 0.0
        parts.append(
            f"{beat_id}:{path}:{mtime:.6f}:{trim_start}:{trim_end}:{pause_after_ms}:"
            f"fade_after:{fade_after_ms}:audio_delay:{audio_delay}:trim_back:{trim_back}",
        )
        metadata.append({
            "beat_id": beat_id,
            "file": str(path),
            "mtime": mtime,
            "trim_start": trim_start,
            "trim_end": trim_end,
            "trim_back": trim_back,
            "pause_after_ms": pause_after_ms,
            "selected_option": selected,
            "fade_after_ms": fade_after_ms,
            "audio_delay": audio_delay,
        })
    digest = hashlib.sha256(";".join(parts).encode("utf-8")).hexdigest()
    return digest, metadata


# ---------------------------------------------------------------------------
# Per-pair fade resolution + clamping — ITEM-AGNOSTIC helpers
# (LD PER_ITEM_FADE_AFTER_OVERRIDE_V1, April 19 2026)
# ---------------------------------------------------------------------------
# These helpers operate on a generic list of metadata dicts. Each dict MUST
# have a `fade_after_ms` key (may be None = inherit). Today the caller passes
# per-beat metadata from compute_cache_hash(). V4 will pass per-module-segment
# metadata for the 7-segment atomic MP4 assembly (opening scene / buy-in /
# Phase A / Phase B / resolution / win / map-return) UNCHANGED. Do not rename
# these helpers to `*_for_beats`; the item-agnostic contract is load-bearing.
# ---------------------------------------------------------------------------
def resolve_pair_fades(items_meta: list[dict], global_fade_ms: int) -> list[int]:
    """Return per-pair effective fade ms. Length = len(items_meta) - 1.

    Pair i (from item i to item i+1) uses items_meta[i]['fade_after_ms']
    when set (not None), else global_fade_ms. The LAST item's
    fade_after_ms is never read — there is no outgoing transition after
    the final item, and enforcing that here means V4 segment assembly
    gets the same no-trailing-fade guarantee for free.
    """
    if not items_meta:
        return []
    fades: list[int] = []
    for i in range(len(items_meta) - 1):
        override = items_meta[i].get("fade_after_ms")
        if override is None:
            fades.append(int(global_fade_ms))
        else:
            fades.append(int(override))
    return fades


def compute_fade_clamp_per_pair(durations: list[float],
                                pair_fades: list[int]) -> list[int]:
    """Clamp each pair's fade to its two adjacent trimmed durations.

    durations: per-item duration in seconds (length N).
    pair_fades: per-pair requested fade in ms (length N-1; output of
                resolve_pair_fades).

    Returns a list of clamped fades (length N-1). Each pair i is bounded by
    BOTH durations[i] AND durations[i+1] minus FADE_CLAMP_BUFFER_S (the same
    2-sided buffer compute_fade_clamp uses for the all-global case), floored
    at 0. A 0 output signals "hard cut" — the caller MUST fast-path to plain
    concat for that pair rather than invoking render_xfade_pair with fade=0
    (which raises ValueError by design).

    Item-agnostic: caller hands per-item durations. V4 segment composer will
    pass the 7 Phase/segment durations unchanged.
    """
    if not durations:
        raise ValueError("compute_fade_clamp_per_pair: empty durations list")
    expected_pairs = len(durations) - 1
    if len(pair_fades) != expected_pairs:
        raise ValueError(
            f"compute_fade_clamp_per_pair: len(pair_fades)={len(pair_fades)} "
            f"must equal len(durations)-1={expected_pairs}",
        )
    clamped: list[int] = []
    for i, requested_ms in enumerate(pair_fades):
        requested_s = max(0.0, float(requested_ms) / 1000.0)
        if requested_s == 0.0:
            clamped.append(0)
            continue
        max_safe_s = max(
            0.0,
            min(
                durations[i] - FADE_CLAMP_BUFFER_S,
                durations[i + 1] - FADE_CLAMP_BUFFER_S,
            ),
        )
        effective_s = min(requested_s, max_safe_s)
        clamped.append(int(round(effective_s * 1000.0)))
    return clamped


# ---------------------------------------------------------------------------
# V3 Watercolor overlay (LD-preflight 102 Call 4)
# ---------------------------------------------------------------------------
def resolve_watercolor_asset(library_dir: Path, key: str, cue_type: str) -> Path:
    """Resolve a watercolor cue key to an existing file on disk.

    Delegates to lib.watercolor_assets.resolve_watercolor_path (canonical contract).
    """
    if cue_type not in _WC_CUE_TYPES:
        raise ValueError(
            f"cue_type {cue_type!r} not in {sorted(_WC_CUE_TYPES)}",
        )
    if not key or not isinstance(key, str):
        raise ValueError(f"key must be non-empty string, got {key!r}")
    try:
        from lib.watercolor_assets import resolve_watercolor_path as _resolve_wc
    except ImportError:
        _resolve_wc = None
    prefer_animation = cue_type == "video"
    if _resolve_wc is not None:
        return _resolve_wc(library_dir, key, prefer_animation=prefer_animation)
    exts = _WC_PNG_EXTS if cue_type == "png" else _WC_VIDEO_EXTS
    # Accept key with or without extension.
    key_path = Path(key)
    if key_path.suffix:
        candidate = library_dir / key_path
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(
            f"watercolor asset not found: {candidate} "
            f"(key={key!r} cue_type={cue_type!r})",
        )
    for ext in exts:
        candidate = library_dir / f"{key}{ext}"
        if candidate.is_file():
            return candidate
    # Fallback: if the primary extension set didn't match, try the other set.
    # This handles stale cue_type="png" for keys that only have an MP4 on disk
    # (animated keys stored before the validator auto-correct was added).
    fallback_exts = _WC_VIDEO_EXTS if cue_type == "png" else _WC_PNG_EXTS
    for ext in fallback_exts:
        candidate = library_dir / f"{key}{ext}"
        if candidate.is_file():
            return candidate
    tried = [str(library_dir / f"{key}{e}") for e in (*exts, *fallback_exts)]
    raise FileNotFoundError(
        f"watercolor asset not found for key={key!r} cue_type={cue_type!r}; "
        f"tried: {tried}",
    )


def _wc_build_cue_prefilter(input_idx: int, cue: dict,
                            chromakey_for_video: bool,
                            frame_max_w: int = 600,
                            frame_max_h: int = 540,
                            cue_hold_s: float = 20.0) -> str:
    """Return the pre-overlay filter fragment for a cue, producing label [cN].

    Counter HIGH-4 resolution: chromakey only applied when cue_type=="video"
    AND chromakey_for_video=True. PNG cues skip chromakey entirely (their
    alpha is already present; applying chromakey on alpha PNGs corrupts them).

    Preflight 134 (v2_native_aspect): scale to (frame_max_w, frame_max_h) bbox
    with `force_original_aspect_ratio=decrease` and NO pad. The overlay lands
    at (frame_x, frame_y) at its native scaled size -- correctly fitting the
    LEFT or RIGHT frame. Prior v1 padded to 1280x720 centered which made all
    overlays render center-of-frame regardless of frame_x.
    """
    cue_type = cue.get("cue_type") or "png"
    label = f"c{input_idx}"
    # ts_s needed so fade-in starts at the cue's absolute time (not t=0).
    # If fade st=0, the fade fires at global t=0 and is long gone by the time
    # the overlay enable window opens at ts_s — the overlay would appear with
    # no entrance animation. Using st=ts_s ties the fade to the enable window.
    ts_s = float(cue.get("timestamp_ms") or 0) / 1000.0
    chain = []
    if cue_type == "video" and chromakey_for_video:
        chain.append("chromakey=0xFF00FF:0.25:0.0")
    # Scale-to-bbox with aspect preserved. No pad -> overlay is native-aspect
    # sized image, placed at (frame_x, frame_y) directly by the overlay filter.
    # NOTE: the 2× canvas has the SAME aspect ratio as the source PNG, so the
    # scale-to-bbox result is the same size as the PNG would produce, and the
    # path position mapping is correct (canvas [0,1] ≡ PNG [0,1]).
    chain.append(
        f"scale=w={frame_max_w}:h={frame_max_h}:force_original_aspect_ratio=decrease"
    )
    # Apply animation preset's entrance effect (0.3s fade-in for fade_in and
    # slide_in; gentle_pan layers a slow x oscillation).
    # Use st=ts_s so the fade fires at the cue's global start time, not t=0.
    # IMPORTANT: skip ffmpeg fade for cue_type=="video" — the PIL renderer
    # already bakes a 0.5s opacity ramp into the MP4 frames. Applying a
    # second ffmpeg alpha fade multiplies the two opacities (PIL_alpha *
    # ffmpeg_alpha), producing near-invisible onset for the first 0.3s.
    animation = cue.get("animation") or "fade_in"
    if cue_type != "video":
        # Image/PNG cues: apply ffmpeg entrance fade (PIL baking doesn't apply)
        if animation == "fade_in":
            chain.append(f"fade=t=in:st={ts_s:.3f}:d=0.3:alpha=1")
        elif animation == "slide_in":
            # Short fade so opacity isn't binary.
            chain.append(f"fade=t=in:st={ts_s:.3f}:d=0.15:alpha=1")
        elif animation == "gentle_pan":
            chain.append(f"fade=t=in:st={ts_s:.3f}:d=0.5:alpha=1")
    else:
        # wc_v8: loop the baked rub clip for the full enable window. Motion is in
        # the MP4 pixels — no tpad alignment, no ffmpeg fade (loop-friendly encode).
        pass
    joined = ",".join(chain)
    return f"[{input_idx}:v]{joined}[{label}]"


def _wc_overlay_x_expr(cue: dict, frame_x: int) -> str:
    """Overlay x-expression per animation preset.

    fade_in    -> static x = frame_x
    slide_in   -> x slides from -W to frame_x over 0.5s relative to cue start
    gentle_pan -> x = frame_x + 5*sin(2*PI*t_rel) for micro-motion (PNG only)
    """
    cue_type = cue.get("cue_type") or "png"
    # wc_v8: animated video cues bake motion in PIL — panning the whole tile made
    # the magenta bounding box bounce while hands looked static inside it.
    if cue_type == "video":
        return str(frame_x)

    animation = cue.get("animation") or "fade_in"
    timestamp_s = float(cue.get("timestamp_ms") or 0) / 1000.0
    if animation == "slide_in":
        # Slide in from off-screen LEFT (negative x) to frame_x over 0.5s.
        # slide_start = -(frame_max_w + 50) ensures the asset starts fully
        # off the left edge before sweeping to its resting position at frame_x.
        # Prior code used frame_x - 300, meaning the asset started on-screen
        # and appeared to barely move — not a real slide-in. (2026-05-27 fix)
        # We use -700 as a safe off-left value for any reasonable frame_max_w.
        slide_start = -700
        return (
            f"'if(lt(t,{timestamp_s + 0.5:.3f}),"
            f"{slide_start}+({frame_x}-({slide_start}))*(t-{timestamp_s:.3f})/0.5,"
            f"{frame_x})'"
        )
    if animation == "gentle_pan":
        return f"'{frame_x}+5*sin(2*PI*(t-{timestamp_s:.3f}))'"
    return str(frame_x)  # fade_in default: static


def render_watercolor_overlay(
    base_video_path: Path,
    cues: list[dict],
    frame_x: int,
    frame_y: int,
    output_path: Path,
    library_dir: Path = Path("Production/assets/watercolor_library"),
    chromakey_for_video: bool = True,
    timeout_s: int = 600,
    frame_max_w: int = 600,
    frame_max_h: int = 540,
    encoder_args: tuple[str, ...] | None = None,
) -> Path:
    """Compose base_video with N watercolor cues via linear ffmpeg filter_complex.

    Design decision A1 (preflight 98): linear filter_complex wins on fidelity
    (sub-frame timing precision, native easing, blend modes) vs A4 Python
    compositor. C4 parameterization: frame_x/frame_y parameters mean one
    function serves Phase A (RIGHT frame, frame_x=800) and Phase B (LEFT
    frame, frame_x=40). Chromakey branch applies only to cue_type=="video"
    AND chromakey_for_video=True.

    cues: list of {timestamp_ms, key, animation, duration_ms, cue_type}
        cue_type in {"png", "video"}
        animation in {"fade_in", "slide_in", "gentle_pan"}

    Returns output_path on success. Raises FileNotFoundError on missing cue
    asset (pre-checked BEFORE any ffmpeg invocation -- HIGH-3 fail-loud).
    Raises subprocess.CalledProcessError on ffmpeg failure.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    enc_args = encoder_args if encoder_args is not None else NORMALIZATION_ENCODER_ARGS
    # Sort cues by timestamp_ms for deterministic stacking (later cue on top).
    cues_sorted = sorted(cues or [], key=lambda c: int(c.get("timestamp_ms") or 0))

    # Pre-resolve every asset (HIGH-3 fail-loud).
    cue_paths: list[Path] = []
    for cue in cues_sorted:
        path = resolve_watercolor_asset(
            library_dir,
            cue.get("key") or "",
            cue.get("cue_type") or "png",
        )
        cue_paths.append(path)

    # Validate cue timestamps against base video duration (LOW fix, 2026-05-27).
    # A cue at ts > video_duration silently never appears — no ffmpeg error,
    # no output error, overlay just absent. Fail loudly instead.
    base_video_duration = ffprobe_duration(base_video_path)
    if base_video_duration > 0:
        for cue in cues_sorted:
            ts_s = float(cue.get("timestamp_ms") or 0) / 1000.0
            if ts_s >= base_video_duration:
                raise ValueError(
                    f"Cue timestamp {ts_s:.3f}s (id={cue.get('id')!r}) exceeds "
                    f"base video duration {base_video_duration:.3f}s. "
                    f"The overlay would never appear. Check production_state.json "
                    f"phase_b_watercolor_cues_json timestamp_ms values."
                )

    # Build ffmpeg command.
    cmd: list[str] = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(base_video_path.resolve()),
    ]
    effective_cues: list[dict] = []
    for cue_path, cue in zip(cue_paths, cues_sorted):
        # Decide input flags by ACTUAL FILE EXTENSION, not stored cue_type.
        # cue_type in the dict may be stale (e.g., "png" for a key that resolved
        # via fallback to an .mp4). -loop 1 is valid ONLY for image demuxers
        # (png/jpg/gif). Applying it to an .mp4 input causes ffmpeg to exit with
        # "Option not found" (observed: returncode=8 on macOS ARM).
        is_image_input = cue_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp")
        # Patch the in-memory cue dict so downstream filter builders
        # (_wc_build_cue_prefilter) see the correct effective type.
        effective_cue = dict(cue)
        effective_cue["cue_type"] = "png" if is_image_input else "video"
        effective_cues.append(effective_cue)
        # cue_hold_s: how long the looped input must run so its frames exist
        # at the cue's enable-window start (ts_s). With just -t dur_s, the
        # stream was exhausted at t=dur_s — before the enable window opened
        # at ts_s. ffmpeg overlay filter advances both input streams in
        # parallel regardless of the enable condition, so [cN] is at EOF by
        # the time the first overlay frame is requested at t=ts_s.
        # Fix: hold for ts_s + dur_s + 2.0s (2s safety margin for stream-end
        # lag).  Bounded by ~(ts_s+dur_s+2), typically <30s, not 3600s.
        _cue_ts_s = float(cue.get("timestamp_ms") or 0) / 1000.0
        _cue_dur_s = float(cue.get("duration_ms") or 1000) / 1000.0
        cue_hold_s = _cue_ts_s + _cue_dur_s + 2.0
        if is_image_input:
            cmd.extend(["-loop", "1",
                        "-t", f"{cue_hold_s:.3f}",
                        "-i", str(cue_path.resolve())])
        else:
            # wc_v8: loop tight alpha MP4 for full enable window (rub repeats).
            cmd.extend(["-stream_loop", "-1",
                        "-t", f"{cue_hold_s:.3f}",
                        "-i", str(cue_path.resolve())])

    # Tmp target computed once (counter 102 LOW fix).
    tmp = output_path.parent / f"{output_path.stem}.tmp.{os.getpid()}{output_path.suffix}"

    # Bug 3 fix (preflight 103): -vf cannot coexist with -filter_complex on
    # the same stream (ffmpeg rc=234). Additionally, base_video_path has no
    # pre-normalization contract (lipsync output from ByteDance is NOT run
    # through normalize_for_concat) and PNG cues with -loop 1 synthesize at
    # ffmpeg's default 25fps, not 24. Solution: normalize base via a prepended
    # [0:v]VF_EXPR[base] stage, then overlay off [base] instead of [0:v], then
    # tail-chain VF_EXPR again so enable='between()' timestamps are canonical
    # 24fps-quantized. Use ENCODER_ARGS (no -vf) at cmd level.
    if not cues_sorted:
        # No cues -> use filter_complex to keep behavior uniform and avoid a
        # branch that could regress with -vf + -filter_complex in future edits.
        filter_complex = f"[0:v]{NORMALIZATION_VF_EXPR}[vout]"
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",
            *enc_args,
        ])
    else:
        # Normalize the base input first, then chain overlays off [base].
        # setpts=PTS-STARTPTS ensures base PTS starts at 0 regardless of any
        # CTTS offset or edit-list atom in the source MP4. Required so that
        # the cue enable condition (gte(t,ts_s)*lte(t,...)) evaluates against
        # a zero-anchored timeline matching the cue timestamps_ms values.
        prefilters: list[str] = [f"[0:v]{NORMALIZATION_VF_EXPR},setpts=PTS-STARTPTS[base]"]
        overlays: list[str] = []
        prev_label = "base"
        for i, cue in enumerate(effective_cues):
            input_idx = i + 1  # base video is 0
            # Hoist ts_s/dur_s before prefilter call so cue_hold_s can be passed.
            # (wc_v6: tpad stop_duration is derived from cue_hold_s, not hardcoded 300.)
            ts_s = float(cue.get("timestamp_ms") or 0) / 1000.0
            dur_s = float(cue.get("duration_ms") or 1000) / 1000.0
            cue_hold_s = ts_s + dur_s + 2.0
            prefilters.append(_wc_build_cue_prefilter(
                input_idx, cue, chromakey_for_video,
                frame_max_w=frame_max_w, frame_max_h=frame_max_h,
                cue_hold_s=cue_hold_s))
            x_expr = _wc_overlay_x_expr(cue, frame_x)
            out_label = f"v{i+1}"
            # Use gte()*lte() instead of between(): between() exclusivity
            # semantics vary by ffmpeg version and fail at exact boundary frames.
            # gte/lte are unambiguously inclusive on both sides.
            # Root-cause fix for invisible overlay (v3, 2026-05-27):
            # between(t,11.341,21.341) silently failed because [cN] was limited
            # to -t {dur_s} (10.0s), reaching EOF at t=10.0 BEFORE the enable
            # window opened at t=11.341. Fix: cue input uses
            # cue_hold_s = ts_s + dur_s + 2.0 (see input construction above),
            # ensuring frames exist at any point in the enable window.
            overlays.append(
                f"[{prev_label}][c{input_idx}]overlay="
                f"x={x_expr}:y={frame_y}:"
                f"enable='gte(t,{ts_s:.3f})*lte(t,{ts_s + dur_s:.3f})'"
                f"[{out_label}]"
            )
            prev_label = out_label
        # Tail VF pass (C2 fix): force fps=24 after overlay composition so
        # PNG -loop 1 default-25fps synthesis can't leak into output.
        overlays.append(f"[{prev_label}]{NORMALIZATION_VF_EXPR}[vout]")
        filter_complex = ";".join(prefilters + overlays)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",  # pass base audio if present
            *enc_args,
        ])
    # Cap output to base duration — looped cue inputs use cue_hold_s (ts+dur+2s)
    # which can exceed the base clip; without -t the longest input wins (~3s on
    # a 2s base). Preview/stitch expect overlay output to match lipsync length.
    if base_video_duration > 0:
        cmd.extend(["-t", f"{base_video_duration:.3f}"])
    cmd.append(str(tmp))
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return output_path


# ---------------------------------------------------------------------------
# S5.5d (v3 architecture revision, 2026-05-03): export pipeline helpers per
# BEAT_FINALIZE_ENDPOINT_V1 + SCENE_ASSEMBLE_ENDPOINT_V1.
# ---------------------------------------------------------------------------
def compute_finalize_args_hash(slim_snapshot: dict, beat_id: str,
                               clips_dir: Path,
                               event_dir: "Path | None" = None) -> tuple[str, dict]:
    """Compute the per-beat finalize cache hash + per-beat resolution metadata.

    Per Cursor Q1 (v3 spec §3.5 Stage 1): excludes fade_after_ms +
    pause_after_ms (those are Stage 2 concerns; same beat MP4 is reused
    across multiple scene assemblies with different fade configurations).

    Hash inputs:
      - beat_id
      - resolved input file abs path (via resolve_beat_file, or magic path)
      - resolved input file mtime
      - phase_1.selected_option
      - phase_1.trim_start, trim_end
      - phase_1.audio_delay
      - image_overrides[<role>][<beat_id>] — deterministic JSON
      - selected_lipsync_path if beat.lipsync.status == "completed", else None
      - magic_still_path / magic_video_path (None when not set)
      - is_magic_still_source / is_magic_video_source flags
      - NORMALIZATION_RECIPE_HASH (per-codec)
      - FINALIZE_RECIPE_VERSION

    Returns:
        (hex_sha256, {beat_id, file, mtime, trim_start, trim_end,
                      audio_delay, selected_option, lipsync_path,
                      image_override, is_magic_still_source, is_magic_video_source})

    Magic source priority (highest):
      When both magic_still_path and magic_video_path exist on disk, the newer
      file mtime wins (resolve_active_magic_layer in beat_generator).
      magic_still_path: silent composite — caller MUST mix TTS (is_magic_still_source).
      magic_video_path: lipsync audio is baked in at composite time (handle_magic_video
      maps source lipsync audio). Do NOT re-mix TTS on top (is_magic_video_source).
    """
    beats = slim_snapshot.get("beats") or {}
    image_overrides = slim_snapshot.get("image_overrides") or {}
    beat = beats.get(beat_id) or {}
    phase1 = beat.get("phase_1") or {}

    # Priority 0a: magic composite — newest on-disk layer wins when both exist.
    magic_still = beat.get("magic_still_path")
    magic_video = beat.get("magic_video_path")
    is_magic_still_source = False
    is_magic_video_source = False
    magic_path_used: "str | None" = None
    path: "Path | None" = None
    if event_dir:
        import beat_generator as _bg  # lazy — beat_generator imports ffmpeg_stitch lazily too

        layer = _bg.resolve_active_magic_layer(beat, event_dir)
        if layer == "still":
            still_clip = _bg.beat_magic_still_clip_path(beat, event_dir)
            if still_clip is not None:
                path = still_clip
                is_magic_still_source = True
                magic_path_used = magic_still
        elif layer == "video":
            video_clip = _bg.beat_magic_video_clip_path(beat, event_dir)
            if video_clip is not None:
                path = video_clip
                is_magic_video_source = True
                magic_path_used = magic_video

    if path is None and not is_magic_still_source and not is_magic_video_source:
        path = resolve_beat_file(beat_id, slim_snapshot, clips_dir)  # raises FNF

    mtime = os.path.getmtime(str(path))
    trim_start = phase1.get("trim_start", 0.0) or 0.0
    trim_end = phase1.get("trim_end")
    trim_back = phase1.get("trim_back")  # relative back-trim (None = not set)
    audio_delay = phase1.get("audio_delay", 0.0) or 0.0
    selected_option = phase1.get("selected_option")
    lipsync = beat.get("lipsync") or {}
    lipsync_path = (
        lipsync.get("file") if lipsync.get("status") == "completed" else None
    )
    image_override = image_overrides.get(beat_id) if isinstance(
        image_overrides, dict
    ) else None
    image_override_json = json.dumps(image_override, sort_keys=True) if image_override is not None else "null"

    parts = [
        f"recipe:{FINALIZE_RECIPE_VERSION}",
        f"norm:{NORMALIZATION_RECIPE_HASH}",
        f"beat:{beat_id}",
        f"path:{str(path)}",
        f"mtime:{mtime:.6f}",
        f"trim_start:{trim_start}",
        f"trim_end:{trim_end}",
        f"trim_back:{trim_back}",  # back-trim (None = not set); included so cache
        # invalidates when Kim adjusts the trim-back slider (split-brain fix).
        f"audio_delay:{audio_delay}",
        f"selected_option:{selected_option}",
        f"lipsync_path:{lipsync_path}",
        f"image_override:{image_override_json}",
        f"magic_still:{magic_still}",    # cache invalidates when magic applied/removed
        f"magic_video:{magic_video}",
        f"is_magic_still_source:{is_magic_still_source}",
        f"is_magic_video_source:{is_magic_video_source}",
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    metadata = {
        "beat_id": beat_id,
        "file": str(path),
        "mtime": mtime,
        "trim_start": trim_start,
        "trim_end": trim_end,
        "trim_back": trim_back,
        "audio_delay": audio_delay,
        "selected_option": selected_option,
        "lipsync_path": lipsync_path,
        "image_override": image_override,
        "is_magic_still_source": is_magic_still_source,
        "is_magic_video_source": is_magic_video_source,
        "is_magic_source": is_magic_still_source,  # legacy alias: silent magic only
        "magic_path_used": magic_path_used,
    }
    return digest, metadata


def _scene_lock_path(scope_type: str, scope_root: Path, role: str) -> Path:
    """Resolve the assemble lock path per scope type (v3 spec §3.5 Stage 2).

    Event scope:     <event_dir>/scene_assemble_<role>.lock
    Milestone scope: <milestone_dir>/scene_assemble_<role>.lock

    Both paths use the same naming so a future generic helper can resolve
    by scope-type alone without conditional logic at every call site.
    """
    if scope_type not in ("event", "milestone"):
        raise ValueError(f"_scene_lock_path: invalid scope_type={scope_type!r}")
    return scope_root / f"scene_assemble_{role}.lock"

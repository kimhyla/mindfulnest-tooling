#!/usr/bin/env python3
"""Generate Phase B Cedric lipsync base clip from a wizard-desk still PNG.

Submits Kling single-image idle (no Cedric Element — human wizard not in registry),
normalizes to 1280×720 (16:9 module playback), writes assets/lipsync_bases/<clip_id>.mp4.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    RULE8_ANTI_LIPSYNC,
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)
from phase_b_cedric_contract import (  # noqa: E402
    PHASE_B_BOOKEND_POSE_LOCK,
    PHASE_B_CAMERA_GAZE_LOCK,
    PHASE_B_DESK_PROPS_LOCK,
    PHASE_B_FIREPLACE_SMOKE_LOCK,
    PHASE_B_GESTURE_LOCK,
    PHASE_B_MOUTH_FROZEN_LOCK,
    PHASE_B_MUG_PLACEMENT_LOCK,
    PHASE_B_MUG_STEAM_LOCK,
    PHASE_B_ROBE_STABILITY_LOCK,
)

_CEDRIC_IDLE_SHARED = (
    f"{PHASE_B_MOUTH_FROZEN_LOCK} "
    f"{PHASE_B_CAMERA_GAZE_LOCK} "
    f"{PHASE_B_FIREPLACE_SMOKE_LOCK} "
    "Warm firelight may flicker softly on stone walls only — fireplace masonry stays fixed. "
    f"{PHASE_B_MUG_STEAM_LOCK} "
    f"{PHASE_B_MUG_PLACEMENT_LOCK} "
    f"{PHASE_B_DESK_PROPS_LOCK} "
    f"{PHASE_B_ROBE_STABILITY_LOCK} "
    f"{PHASE_B_GESTURE_LOCK} "
    "STATIC CAMERA — locked frame, zero zoom, zero dolly, zero pan, zero Ken Burns."
)

_CEDRIC_IDLE_CORE = (
    "Cedric the elderly wizard sits at a wooden desk in a firelit cozy stone study, "
    "facing the camera in a relaxed neutral rest pose — both hands empty and resting "
    "near the desk, one wooden coffee mug sitting in a fixed spot on the desk. "
    f"{_CEDRIC_IDLE_SHARED} "
    "Natural idle body motion active from frame one — immediate soft blinks, subtle "
    "breathing, and relaxed shoulders from the very start; no slow ramp-up, no frozen "
    "opening hold, no statue stillness at the beginning."
)

_CEDRIC_BOOKEND_CORE = (
    "Cedric the elderly wizard sits at a wooden desk in a firelit cozy stone study. "
    f"{PHASE_B_BOOKEND_POSE_LOCK} "
    f"{_CEDRIC_IDLE_SHARED}"
)

_CEDRIC_SIP_SEGMENT = (
    "This segment: at most ONE calm coffee sip — lift the same mug once, one gentle sip, "
    "return mug to its exact desk home spot, then neutral empty-hands rest."
)

_CEDRIC_NO_SIP_SEGMENT = (
    "This segment: DO NOT touch, lift, or sip from the mug — hands stay off the coffee "
    "cup entirely; blinks, breathing, and small gestures only."
)

_CEDRIC_HANDS_RESTING = (
    "HANDS RESTING: both hands stay calmly on the desk at all times — fingers still "
    "and natural, no waving, no gestures, no reaching, no extra fingers, no hand "
    "morphing. DO NOT touch or lift the mug."
)


def build_cedric_idle_prompt(
    *,
    allow_sip: bool,
    bookend_pose: bool = False,
    hands_resting: bool = False,
) -> str:
    """Assemble Kling idle prompt; alternate sip/no-sip segments reduce sip spam."""
    core = _CEDRIC_BOOKEND_CORE if bookend_pose else _CEDRIC_IDLE_CORE
    if hands_resting:
        return f"{core} {_CEDRIC_HANDS_RESTING}"
    if not allow_sip:
        return f"{core} {_CEDRIC_NO_SIP_SEGMENT}"
    return f"{core} {_CEDRIC_SIP_SEGMENT}"


# Back-compat for tests / imports expecting a single static prompt.
CEDRIC_STILL_PROMPT = build_cedric_idle_prompt(allow_sip=True)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "mouth movement, lip movement, jaw movement, talking, speaking, mumbling, chewing, "
    "lip sync, lipsync, mouthing words, speech animation, jaw articulation, "
    "open mouth, lip parting, smile with teeth, teeth, fangs, dental, "
    "bird, magpie, beak, wing, flapping, extra limbs, zoom in, camera move, "
    "pacing, walking, young face, head turn away from camera, "
    "smoke billowing, heavy smoke, smoke filling room, smoke outside fireplace, "
    "smoke crossing hearth, chimney smoke blast, "
    "mug steam, coffee steam, cup steam, mug vapor, mug wisps, steam from mug, "
    "steam puff, steam obscuring face, "
    "potion steam, bottle steam, bottle vapor, prop steam, shelf steam, "
    "mug teleport, mug floating, mug sliding by itself, mug jumping into hands, "
    "second mug, duplicate mug, two mugs, extra coffee cup, twin cups, "
    "cup holder, cupholder, coaster appearing, black disc, black coaster, "
    "prop appearing, object spawn, new object on desk, "
    "frozen opening, slow start, statue stillness, "
    "diagonal pleats, fabric morphing, robe rippling, embroidery shifting, cloth folding, "
    "checkerboard pattern, moire, fabric grid, weave artifact, harsh stare"
)

DEFAULT_CLIP_ID = "cedric_idle_newstyle_v6"
PHASE_B_BASE_CLIP_DURATION_S = 10
PHASE_B_BASE_DURATION_CHOICES = (5, 10, 15)


def _event_dir() -> Path:
    env = os.environ.get("MN_EVENT_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    dropbox = (
        Path.home()
        / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    )
    if (dropbox / "Event_1").is_dir():
        return dropbox / "Event_1"
    return HERE.parent / "Event_1"


def _prod_root(event: Path) -> Path:
    return event.parent


def stitch_two_idle_clips(
    part_a: Path,
    part_b: Path,
    out: Path,
    *,
    xfade_s: float = 0.7,
) -> None:
    """Join two native idle halves with one crossfade (bookended parts blend cleanly)."""
    from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402

    part_a = part_a.expanduser().resolve()
    part_b = part_b.expanduser().resolve()
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    dur_a = ffprobe_duration(part_a)
    # Slightly longer blend when both clips end/start on the same neutral still.
    xf = min(xfade_s, dur_a * 0.12, 1.2)
    offset = max(0.0, dur_a - xf)
    norm = "fps=24,setpts=PTS-STARTPTS"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(part_a),
        "-i", str(part_b),
        "-filter_complex",
        (
            f"[0:v]{norm}[v0];[1:v]{norm}[v1];"
            f"[v0][v1]xfade=transition=fade:duration={xf:.3f}:offset={offset:.3f}[v]"
        ),
        "-map", "[v]",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24",
        "-movflags", "+faststart",
        str(out),
    ], check=True, timeout=300)


def _normalize(src: Path, dst: Path) -> None:
    _cred = HERE / "credentials_lib"
    if str(_cred) not in sys.path:
        sys.path.insert(0, str(_cred))
    from video_encode_policy import BASE_CLIP_FFMPEG_VIDEO_ARGS, VIDEO_QUALITY_GRADFUN_VF  # noqa: E402

    vf = (
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24,"
        + VIDEO_QUALITY_GRADFUN_VF
    )
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", vf,
        *BASE_CLIP_FFMPEG_VIDEO_ARGS,
        "-c:a", "aac", "-ar", "44100", "-ac", "1", "-movflags", "+faststart",
        str(dst),
    ], check=True, timeout=180)


def _default_still_candidates(event: Path, prod: Path) -> list[Path]:
    return [
        prod / "NEW STYLE CHARACTERS" / "CEDRIC"
        / "ChatGPT Image Jul 4, 2026, 04_04_56 PM.png",
        prod / "NEW STYLE CHARACTERS" / "CEDRIC"
        / "ChatGPT Image Jun 21, 2026, 10_45_20 PM.png",
        event / "cedric_phase_b_canonical_still.png",
        event / "cedric_at_desk_phase_b_canonical_frame.png",
        prod / "NEW STYLE CHARACTERS" / "CEDRIC" / "CEDRIC.png",
    ]


def _part_count_for_target(
    *,
    target_s: float,
    native_s: float = 15.0,
    trim_s: float = 0.0,
    xfade_s: float = 0.7,
) -> int:
    """Parts needed when each native clip contributes (native - 2*trim) minus xfade overlap."""
    if trim_s > 0:
        usable = native_s - 2.0 * trim_s
        if usable <= 0.5:
            raise ValueError(f"bookend trim {trim_s}s too large for {native_s}s native parts")
        step = usable - xfade_s
        if step <= 0.05:
            raise ValueError("usable segment shorter than xfade overlap")
        return max(2, math.ceil((target_s - xfade_s) / step))
    return max(2, math.ceil(target_s / native_s))


def _trim_part_bookends(
    src: Path,
    dst: Path,
    *,
    head_s: float,
    tail_s: float,
) -> None:
    """Drop frozen bookend zones from each native part before stitch."""
    from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402

    src = src.expanduser().resolve()
    dst = dst.expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dur = ffprobe_duration(src)
    keep = dur - head_s - tail_s
    if keep <= 0.5:
        raise ValueError(f"trim {head_s}+{tail_s}s leaves nothing in {dur:.1f}s clip")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{head_s:.3f}", "-i", str(src),
        "-t", f"{keep:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an", "-r", "24",
        "-movflags", "+faststart",
        str(dst),
    ], check=True, timeout=120)


def stitch_idle_clips(parts: list[Path], out: Path, *, xfade_s: float = 0.7) -> None:
    """Sequentially xfade-stitch native idle clips (e.g. 4×15s → ~60s)."""
    if len(parts) < 2:
        raise ValueError("stitch_idle_clips needs at least two parts")
    work = out.parent / f"_stitch_work_{out.stem}"
    work.mkdir(parents=True, exist_ok=True)
    current = parts[0].expanduser().resolve()
    for i, nxt in enumerate(parts[1:], start=1):
        step = work / f"join_{i}.mp4"
        stitch_two_idle_clips(current, nxt.expanduser().resolve(), step, xfade_s=xfade_s)
        current = step
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(current), "-c", "copy", str(out),
    ], check=True, timeout=120)


def _stitch_multipart_cli(
    args: argparse.Namespace,
    *,
    part_count: int,
    auto_scale_for_trim: bool = False,
    force_no_sip: bool = False,
) -> int:
    """Generate N×15s Kling idles and stitch into one native base (~180s target)."""
    if part_count < 2:
        log("FATAL: part_count must be >= 2")
        return 1
    bookend = bool(getattr(args, "bookend_neutral", False))
    trim_s = float(getattr(args, "bookend_trim_s", 0.0) or 0.0)
    if trim_s > 0 and not bookend:
        log("FATAL: --bookend-trim-s requires --bookend-neutral")
        return 1
    if trim_s > 0 and auto_scale_for_trim:
        part_count = _part_count_for_target(target_s=178.0, trim_s=trim_s)
        log(
            f"Bookend trim {trim_s:.1f}s/side → {part_count}×15s parts "
            f"(~{15 - 2 * trim_s:.0f}s motion each before xfade)"
        )

    event = _event_dir()
    prod = _prod_root(event)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)
    still = _resolve_still(args, event, prod)
    if still is None:
        log(f"FATAL: no still for {part_count}×15s stitch")
        return 1

    mode_label = f"bookend trim {trim_s:.0f}s" if trim_s > 0 else (
        "bookend" if bookend else "single-image"
    )

    parts: list[Path] = []
    for idx in range(part_count):
        part_id = f"_tmp_{args.clip_id}_p{idx}"
        part_path = bases / f"{part_id}.mp4"
        if part_path.is_file() and not args.regenerate_parts:
            log(f"Reusing existing {part_path.name}")
        else:
            allow_sip = (not force_no_sip) and (idx % 2 == 1)
            sip_label = "sip ok" if allow_sip else "no-sip"
            log(f"Generating 15s part {idx + 1}/{part_count} ({mode_label}, {sip_label})…")
            rc = _generate_idle_clip(
                still=still,
                bases=bases,
                clip_id=part_id,
                duration=15,
                bookend_neutral=bookend,
                allow_sip=allow_sip,
                hands_resting=force_no_sip,
            )
            if rc != 0:
                return rc
        parts.append(part_path)

    stitch_parts: list[Path] = []
    trimmed_tmp: list[Path] = []
    if trim_s > 0:
        for part in parts:
            trimmed = bases / f"{part.stem}_trim{part.suffix}"
            _trim_part_bookends(part, trimmed, head_s=trim_s, tail_s=trim_s)
            stitch_parts.append(trimmed)
            trimmed_tmp.append(trimmed)
    else:
        stitch_parts = parts

    joined = bases / f"_tmp_{args.clip_id}_joined.mp4"
    stitch_idle_clips(stitch_parts, joined)
    out = bases / f"{args.clip_id}.mp4"
    _normalize(joined, out)
    work = bases / f"_stitch_work_{joined.stem}"
    for tmp in [joined, *parts, *trimmed_tmp, work]:
        if isinstance(tmp, Path) and tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
        elif isinstance(tmp, Path):
            try:
                tmp.unlink()
            except OSError:
                pass
    from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402

    dur = ffprobe_duration(out)
    log(f"✓ Saved {part_count}×15s native base {out} ({dur:.1f}s)")
    print(json.dumps({
        "clip_id": args.clip_id,
        "mp4": out.name,
        "duration_s": round(dur, 3),
        "part_count": part_count,
        "bookend_neutral": bookend,
        "bookend_trim_s": trim_s,
        "mode": mode_label,
    }))
    return 0


def _stitch_60s_cli(args: argparse.Namespace) -> int:
    return _stitch_multipart_cli(args, part_count=4)


def _stitch_180s_cli(args: argparse.Namespace) -> int:
    return _stitch_multipart_cli(args, part_count=12, auto_scale_for_trim=True)


def _stitch_2x15_cli(args: argparse.Namespace) -> int:
    """Quick 2×15s bookend join test (~30s output)."""
    if not args.bookend_neutral:
        args.bookend_neutral = True
    if getattr(args, "bookend_no_trim", False):
        args.bookend_trim_s = 0.0
    elif not getattr(args, "bookend_trim_s", 0.0):
        args.bookend_trim_s = 2.0
    return _stitch_multipart_cli(
        args, part_count=2, auto_scale_for_trim=False, force_no_sip=True,
    )


def _stitch_30s_cli(args: argparse.Namespace) -> int:
    event = _event_dir()
    prod = _prod_root(event)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)
    part_a = args.part_a
    if part_a is None:
        part_a = bases / "cedric_idle_newstyle_v7.mp4"
    part_a = part_a.expanduser().resolve()
    if not part_a.is_file():
        log(f"FATAL: missing part-a: {part_a}")
        return 1
    part_b = args.part_b
    if part_b is None:
        log("Generating part-b (15s Kling idle) before stitch…")
        event = _event_dir()
        prod = _prod_root(event)
        still = _resolve_still(args, event, prod)
        if still is None:
            log("FATAL: no still for part-b generation")
            return 1
        part_b_id = f"_tmp_{args.clip_id}_part_b"
        rc = _generate_idle_clip(still=still, bases=bases, clip_id=part_b_id, duration=15)
        if rc != 0:
            return rc
        part_b = bases / f"{part_b_id}.mp4"
    part_b = part_b.expanduser().resolve()
    if not part_b.is_file():
        log(f"FATAL: missing part-b: {part_b}")
        return 1
    joined = bases / f"_tmp_{args.clip_id}_joined.mp4"
    stitch_two_idle_clips(part_a, part_b, joined)
    out = bases / f"{args.clip_id}.mp4"
    _normalize(joined, out)
    for tmp in (joined, bases / f"_tmp_{args.clip_id}_part_b.mp4"):
        try:
            tmp.unlink()
        except OSError:
            pass
    from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402

    log(f"✓ Saved 30s base {out} ({ffprobe_duration(out):.1f}s)")
    print(json.dumps({"clip_id": args.clip_id, "mp4": out.name, "duration_s": round(ffprobe_duration(out), 3)}))
    return 0


def _generate_idle_clip(
    *,
    still: Path,
    bases: Path,
    clip_id: str,
    duration: int,
    bookend_neutral: bool = False,
    allow_sip: bool = True,
    hands_resting: bool = False,
) -> int:
    raw = still.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"Start frame: {still.name} — {info}")
    start_uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
    # Same still as end frame so each subsection lands on a shared neutral pose
    # before stitch (reduces mug/hand jumps at joins). Mid-clip motion may be milder.
    end_uri = start_uri if bookend_neutral else None
    prompt = build_cedric_idle_prompt(
        allow_sip=allow_sip,
        bookend_pose=bookend_neutral,
        hands_resting=hands_resting,
    )

    keys = load_api_keys()
    mode = "start-end neutral bookend" if bookend_neutral else "single-image"
    sip_note = "sip-segment" if allow_sip else "no-sip-segment"
    log(f"Submitting Kling {mode} idle ({duration}s, {sip_note}) clip_id={clip_id}")
    task_id = kling_startend_submit(
        start_uri, end_uri,
        prompt=prompt, negative_prompt=NEGATIVE,
        duration=duration, api_key=keys["wavespeed"],
        element_entry=None,
    )
    log(f"task_id={task_id}")
    result = kling_poll_fresh(task_id, keys["wavespeed"], timeout_s=900)
    if result.get("status") != "completed":
        log(f"FATAL: {result}")
        return 1
    url = (result.get("outputs") or [None])[0]
    if not url:
        log("FATAL: no output url")
        return 1

    staging = bases / f"_tmp_{clip_id}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(staging), url], check=True, timeout=180)
    out = bases / f"{clip_id}.mp4"
    _normalize(staging, out)
    staging.unlink(missing_ok=True)
    log(f"✓ Saved {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(json.dumps({
        "clip_id": clip_id,
        "mp4": out.name,
        "still": still.name,
        "size_mb": round(out.stat().st_size / 1024 / 1024, 1),
    }))
    return 0


def _resolve_still(args: argparse.Namespace, event: Path, prod: Path) -> Path | None:
    still = args.still
    if still is None:
        for candidate in _default_still_candidates(event, prod):
            if candidate.is_file():
                return candidate.expanduser().resolve()
        return None
    still = still.expanduser().resolve()
    return still if still.is_file() else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--still", type=Path, help="Source PNG (default: canonical Cedric still)")
    p.add_argument("--clip-id", default=DEFAULT_CLIP_ID)
    p.add_argument(
        "--duration",
        type=int,
        default=PHASE_B_BASE_CLIP_DURATION_S,
        choices=PHASE_B_BASE_DURATION_CHOICES,
    )
    p.add_argument(
        "--stitch-60s",
        action="store_true",
        help="Generate 4×15s Kling idles and stitch into one ~60s base",
    )
    p.add_argument(
        "--stitch-2x15",
        action="store_true",
        help="Generate 2×15s bookend clips (2s trim/side) and stitch — quick join test",
    )
    p.add_argument(
        "--stitch-180s",
        action="store_true",
        help="Generate 12×15s Kling idles and stitch into one ~180s native base",
    )
    p.add_argument(
        "--stitch-30s",
        action="store_true",
        help="Join --part-a and --part-b (or generate --part-b) into one ~30s base",
    )
    p.add_argument(
        "--regenerate-parts",
        action="store_true",
        help="With --stitch-60s/--stitch-180s, ignore cached _tmp_* part clips on disk",
    )
    p.add_argument(
        "--bookend-neutral",
        action="store_true",
        help="Each 15s part uses same still as start+end (smoother joins, slower motion at edges)",
    )
    p.add_argument(
        "--bookend-no-trim",
        action="store_true",
        help="Keep full bookend clips before stitch (join at ~15s matching pose)",
    )
    p.add_argument(
        "--bookend-trim-s",
        type=float,
        default=0.0,
        help="Trim N seconds from head/tail of each bookend part before stitch",
    )
    p.add_argument("--part-a", type=Path, help="First 15s half for --stitch-30s")
    p.add_argument("--part-b", type=Path, help="Second 15s half for --stitch-30s")
    args = p.parse_args()

    if args.stitch_2x15:
        return _stitch_2x15_cli(args)
    if args.stitch_180s:
        return _stitch_180s_cli(args)
    if args.stitch_60s:
        return _stitch_60s_cli(args)
    if args.stitch_30s:
        return _stitch_30s_cli(args)

    event = _event_dir()
    prod = _prod_root(event)
    os.environ["MN_PROD_ROOT"] = str(prod)
    bases = prod / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)

    still = _resolve_still(args, event, prod)
    if still is None:
        log(f"FATAL: no Cedric still found under {event} or Production/NEW STYLE CHARACTERS/CEDRIC")
        return 1

    return _generate_idle_clip(
        still=still,
        bases=bases,
        clip_id=args.clip_id,
        duration=args.duration,
    )


if __name__ == "__main__":
    sys.exit(main())

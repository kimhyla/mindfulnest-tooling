#!/usr/bin/env python3
"""Teleport Intro Kit — Option B (Clip A variable + Clip B locked master).

Build once:
  clip_b_master.mp4  = mirror line + LD-737 whiteout + hold

Per module:
  clip_a_{module}.mp4 = Kling O3 Element (module-specific patter)
  intro_teleport_tail.mp4 = concat(A, B)

Usage:
  python3 Production/tools/teleport_intro_kit.py plan
  doppler run -- python3 Production/tools/teleport_intro_kit.py build-clip-b [--dry-run]
  doppler run -- python3 Production/tools/teleport_intro_kit.py build-clip-a --module tessa --script "..."
  python3 Production/tools/teleport_intro_kit.py assemble --module tessa [--write-stitch-slot] [--event Event_1]

See Production/docs/TELEPORT_INTRO_KIT_v1.md
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
PROD_DIR = TOOLS_DIR.parent
sys.path.insert(0, str(PROD_DIR))
sys.path.insert(0, str(TOOLS_DIR))

try:
    from lib.paths import dropbox_root
except Exception:
    dropbox_root = lambda: Path(  # type: ignore[misc, assignment]
        os.environ.get(
            "MN_DROPBOX_ROOT",
            "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files",
        )
    )

MANIFEST_REL = "Production/templates/chipper_teleport_intro/manifest.json"

CLIP_A_STAGING = (
    "Chipper — Module intro. Perched facing camera on plain warm studio background; "
    "no mirror, no second character. Static locked eye-level medium shot."
)

CLIP_B_STAGING = (
    "Chipper — Teleport mirror. Holds ornate teleport mirror facing camera; "
    "plain warm studio background. Static locked eye-level medium shot."
)


def log(msg: str) -> None:
    print(f"[teleport_intro] {msg}", flush=True)


def fail(msg: str, code: int = 1) -> None:
    log(f"FATAL: {msg}")
    sys.exit(code)


def project_root() -> Path:
    return dropbox_root()


def manifest_path(*, guide: str | None = None) -> Path:
    env = os.environ.get("TELEPORT_INTRO_MANIFEST")
    if env:
        return Path(env)
    root = project_root()
    try:
        from teleport_intro_canonical import (
            ARLO_MANIFEST_REL,
            CHIPPER_MANIFEST_REL,
            active_manifest_path,
            active_registry_rel,
        )

        guide_use = (guide or os.environ.get("TELEPORT_INTRO_GUIDE") or "").strip() or None
        if guide_use:
            return active_manifest_path(root, guide=guide_use)
        reg = active_registry_rel(root)
        if "arlo_teleport_intro" in reg:
            return root / ARLO_MANIFEST_REL
        if "chipper_teleport_intro" in reg:
            return root / CHIPPER_MANIFEST_REL
        active = active_manifest_path(root)
        if active.is_file():
            return active
    except Exception:
        pass
    dropbox = root / MANIFEST_REL
    if dropbox.is_file():
        return dropbox
    return PROD_DIR / "templates" / "chipper_teleport_intro" / "manifest.json"


def load_manifest(*, guide: str | None = None) -> dict[str, Any]:
    path = manifest_path(guide=guide)
    if not path.is_file():
        fail(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_asset(manifest: dict, key: str) -> Path:
    rel = (manifest.get("assets") or {}).get(key)
    if not rel:
        fail(f"manifest assets.{key} missing")
    p = project_root() / rel
    if not p.is_file():
        fail(f"asset missing: {p}")
    return p


def _path_rel_to_root(path: Path, root: Path) -> str:
    p = path.resolve()
    base = root.resolve()
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(path)


def _manifest_whiteout_hold_s(manifest: dict) -> float:
    raw = manifest.get("clip_b_whiteout_hold_s")
    if raw is None:
        return 2.5
    return max(0.0, float(raw))


def _manifest_burst_use_s(manifest: dict, burst_path: Path) -> float:
    """Cap LD-737 burst segment length at compose time (WYSIWYG — not export trim)."""
    block = manifest.get("intro_canonical_beats") or {}
    raw = block.get("canonical_burst_max_s")
    if raw is None:
        tg = manifest.get("teleport_glass") or {}
        raw = tg.get("duration_s")
    burst_dur = ffprobe_duration(burst_path)
    if raw is None:
        return burst_dur
    try:
        cap = max(0.5, float(raw))
    except (TypeError, ValueError):
        return burst_dur
    return min(burst_dur, cap)


def resolve_output(manifest: dict, key: str) -> Path:
    rel = (manifest.get("outputs") or {}).get(key)
    if not rel:
        fail(f"manifest outputs.{key} missing")
    return project_root() / rel


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def ffprobe_video_size(path: Path) -> tuple[int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    parts = r.stdout.strip().split("x")
    if len(parts) == 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return 1920, 1080


def ffmpeg_burst_overlay_on_frozen_speak(
    speak: Path,
    burst: Path,
    dest: Path,
    *,
    scratch: Path,
) -> None:
    """Overlay existing LD-737 burst ON the speak clip's frozen last frame (no new Kling)."""
    from teleport_glass_inserter import extract_last_frame  # noqa: WPS433

    dest.parent.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    sw, sh = ffprobe_video_size(speak)
    burst_dur = ffprobe_duration(burst)
    frozen_png = scratch / f"{speak.stem}_frozen_last.png"
    extract_last_frame(speak, frozen_png)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "24", "-t", f"{burst_dur:.3f}",
        "-i", str(frozen_png),
        "-i", str(burst.resolve()),
        "-filter_complex",
        (
            f"[0:v]scale={sw}:{sh},setsar=1[fz];"
            f"[1:v]scale={sw}:{sh},setsar=1[br];"
            f"[fz][br]blend=all_mode=lighten:shortest=1[outv]"
        ),
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        fail(f"burst overlay on frozen frame failed: {r.stderr[:500]}")


def ffprobe_stream_duration_s(path: Path, stream: str) -> float:
    """Stream duration in seconds (`v` or `a`); 0.0 when missing/unreadable."""
    sel = "v:0" if stream.startswith("v") else "a:0"
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", sel,
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        return 0.0


def lock_intro_tail_av_to_video_timeline(src: Path, dest: Path | None = None) -> Path:
    """Pad/trim audio to video stream duration (FF-040 timeline authority).

    AAC loudnorm / re-encode can leave ~1–3 AAC frames of A/V drift. Send to Stitcher
    rejects that via ``assert_stitch_export_clips_av_aligned`` — bake alignment here
    so the shared canonical asset never fails export after compose.
    """
    src = src.expanduser().resolve()
    if not src.is_file():
        fail(f"intro_tail timeline lock input missing: {src}")
    out = (dest if dest is not None else src).expanduser().resolve()
    video_s = ffprobe_stream_duration_s(src, "v")
    if video_s <= 0.0:
        if src != out:
            shutil.copy2(src, out)
        return out
    target_s = max(0.04, float(video_s))
    tmp = out.with_name(f"{out.stem}.timeline_tmp{out.suffix}")
    audio_fc = (
        f"[0:a]aresample=44100,aformat=sample_fmts=s16:channel_layouts=mono,"
        f"atrim=end={target_s:.6f},asetpts=PTS-STARTPTS,"
        f"apad=whole_dur={target_s:.6f}[aout]"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-filter_complex", audio_fc,
        "-map", "0:v:0", "-c:v", "copy",
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-ac", "1", "-ar", "44100",
        "-t", f"{target_s:.6f}",
        "-movflags", "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size <= 0:
        tmp.unlink(missing_ok=True)
        fail(f"intro_tail timeline lock failed: {(r.stderr or '')[:500]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, out)
    return out


def apply_intro_tail_speech_loudnorm(src: Path, dest: Path | None = None) -> Path:
    """Level canonical intro_tail speech to the AUTO_LOUDNORM_V1 speech bus (−19 LUFS).

    Body Kling delivery clips land near this target; the composed tail (speak + silent
    burst/hold) historically shipped ~5–6 dB quieter in the speak window, so the final
    intro beat sounded soft next to the rest of the module. Bake leveling into the
    shared asset so Beat Gen preview, Send to Stitcher, and every event stay matched.

    After loudnorm, audio is locked to the video timeline so AAC padding cannot leave
    export-blocking A/V drift on the shared intro_tail.mp4.
    """
    # Keep constants aligned with server_handlers.speech_loudnorm (avoid importing the
    # stitch credential stack from this CLI module — path/import fragile in kit runs).
    target_lufs = -19.0
    target_tp = -1.5
    target_lra = 11.0

    src = src.expanduser().resolve()
    if not src.is_file():
        fail(f"intro_tail loudnorm input missing: {src}")
    out = (dest if dest is not None else src).expanduser().resolve()
    tmp = out.with_name(f"{out.stem}.loudnorm_tmp{out.suffix}")
    af = f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}:print_format=summary"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-af", af,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not tmp.is_file() or tmp.stat().st_size <= 0:
        tmp.unlink(missing_ok=True)
        fail(f"intro_tail speech loudnorm failed: {(r.stderr or '')[:500]}")
    # INTRO_TAIL_COMPOSE_AV_PUBLISH_GATE_V1 — same numeric budget as
    # credentials_lib.ffmpeg_stitch.STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S (0.05).
    # Kit avoids importing the stitch credential stack (path/import fragile in CLI runs).
    INTRO_TAIL_COMPOSE_AV_PUBLISH_GATE_V1 = "INTRO_TAIL_COMPOSE_AV_PUBLISH_GATE_V1"
    _EXPORT_AV_MAX_DRIFT_S = 0.05
    try:
        lock_intro_tail_av_to_video_timeline(tmp, out)
        video_s = ffprobe_stream_duration_s(out, "v")
        audio_s = ffprobe_stream_duration_s(out, "a")
        if video_s > 0.0 and audio_s > 0.0:
            drift = abs(video_s - audio_s)
            if drift > _EXPORT_AV_MAX_DRIFT_S:
                fail(
                    f"intro_tail compose A/V drift {drift:.3f}s exceeds export budget "
                    f"{_EXPORT_AV_MAX_DRIFT_S}s [{INTRO_TAIL_COMPOSE_AV_PUBLISH_GATE_V1}]"
                )
    finally:
        tmp.unlink(missing_ok=True)
    return out


def ffmpeg_compose_intro_tail(
    speak: Path,
    burst_overlay: Path,
    dest: Path,
    *,
    hold_s: float,
    scratch: Path,
    burst_method: str = "overlay_on_frozen_frame",
    burst_use_s: float | None = None,
) -> None:
    """Speak + burst tail + whiteout hold + speech loudnorm (−19 LUFS).

    ``kling_from_frozen_frame``: burst MP4 was generated from this speak clip's
    frozen last frame — concat directly (never lighten-blend onto the freeze again;
    that duplicates Chipper and causes the ghost/double-exposure artifact).

    ``overlay_on_frozen_frame``: shared/generic LD-737 burst overlaid on freeze only.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    joined = scratch / "_joined.mp4"
    held = scratch / "_held.mp4"
    burst_cap = burst_use_s if burst_use_s is not None else ffprobe_duration(burst_overlay)
    if burst_method == "kling_from_frozen_frame":
        ffmpeg_concat_speak_and_burst(speak, burst_overlay, joined, burst_use_s=burst_cap)
    else:
        burst_seg = scratch / "_burst_on_freeze.mp4"
        ffmpeg_burst_overlay_on_frozen_speak(speak, burst_overlay, burst_seg, scratch=scratch)
        ffmpeg_concat_speak_and_burst(speak, burst_seg, joined, burst_use_s=burst_cap)
        burst_seg.unlink(missing_ok=True)
    hold_last_frame(joined, held, hold_s)
    joined.unlink(missing_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    apply_intro_tail_speech_loudnorm(held, dest)
    held.unlink(missing_ok=True)


def ffmpeg_concat_speak_and_burst(
    speak: Path,
    burst: Path,
    dest: Path,
    *,
    burst_use_s: float | None = None,
) -> None:
    """Append burst segment after speak (same frame size)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sw, sh = ffprobe_video_size(speak)
    bw, bh = ffprobe_video_size(burst)
    burst_dur = ffprobe_duration(burst)
    if burst_use_s is not None:
        burst_dur = min(burst_dur, max(0.5, float(burst_use_s)))
    scale_burst = ""
    if (bw, bh) != (sw, sh):
        scale_burst = f"[1:v:0]scale={sw}:{sh},setsar=1[bv];"
        burst_ref = "[bv]"
    else:
        scale_burst = "[1:v:0]setsar=1[bv];"
        burst_ref = "[bv]"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(speak.resolve()),
        "-t", f"{burst_dur:.3f}",
        "-i", str(burst.resolve()),
        "-f", "lavfi", "-t", f"{burst_dur:.3f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex",
        (
            f"[0:v:0]setsar=1,fps=24[sv];"
            f"{scale_burst}"
            f"{burst_ref}[2:a:0]concat=n=1:v=1:a=1[bx][ba];"
            f"[sv][0:a:0][bx][ba]concat=n=2:v=1:a=1[outv][outa]"
        ),
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        fail(f"ffmpeg speak+burst concat failed: {r.stderr[:500]}")


def ffmpeg_concat_videos(parts: list[Path], dest: Path) -> None:
    """Concat 2+ clips. For speak+burst pair, delegates to size-matched concat."""
    if not parts:
        fail("ffmpeg_concat_videos: no inputs")
    if len(parts) == 2:
        ffmpeg_concat_speak_and_burst(parts[0], parts[1], dest)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_file = dest.with_suffix(".concat.txt")
    lines = [f"file '{p.resolve()}'" for p in parts]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        fail(f"ffmpeg concat failed: {r.stderr[:500]}")
    list_file.unlink(missing_ok=True)


def hold_last_frame(src: Path, dest: Path, hold_s: float) -> None:
    """Extend video with cloned last frame; pad audio with silence to match."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    hold_s = max(0.0, float(hold_s))
    if hold_s <= 0.0:
        shutil.copy2(src, dest)
        return
    tmp = dest.with_suffix(".hold_tmp.mp4")
    libdir = str(TOOLS_DIR / "credentials_lib")
    if libdir not in sys.path:
        sys.path.insert(0, libdir)
    from credentials_lib.ffmpeg_stitch import _has_audio_stream  # noqa: WPS433

    if _has_audio_stream(src):
        fc = (
            f"[0:v]tpad=stop_mode=clone:stop_duration={hold_s:.3f}[v];"
            f"[0:a]apad=pad_dur={hold_s:.3f},aresample=44100,aformat=channel_layouts=stereo[a]"
        )
    else:
        total_s = ffprobe_duration(src) + hold_s
        fc = (
            f"[0:v]tpad=stop_mode=clone:stop_duration={hold_s:.3f}[v];"
            f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={total_s:.3f}[a]"
        )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not tmp.is_file():
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        fail(f"hold_last_frame failed: {(r.stderr or '')[:400]}")
    os.replace(tmp, dest)


def build_chipper_voice_prompt(staging: str, spoken: str) -> str:
    from beat_generator import (  # noqa: WPS433
        KLING_O3_CAMERA_LOCK,
        KLING_O3_CHIPPER_SOLO_BIRD_LOCK,
        KLING_O3_CHIPPER_VOICE_DELIVERY,
        _append_kling_o3_submit_locks,
    )

    voice = (
        f"Chipper speaks in a {KLING_O3_CHIPPER_VOICE_DELIVERY}: "
        f'"{spoken.strip()}"'
    )
    raw = (
        f"@Image1 (Chipper) {staging}. Scene from @Image2.\n\n"
        f"{KLING_O3_CAMERA_LOCK}\n\n"
        f"{KLING_O3_CHIPPER_SOLO_BIRD_LOCK}\n\n"
        f"{voice}\n\n"
        "Children's illustrated fantasy storybook style, warm golden studio light."
    )
    return _append_kling_o3_submit_locks(raw, speaker="Chipper", spoken=spoken.strip())


def run_kling_o3_clip(
    *,
    prompt: str,
    char_path: Path,
    bg_path: Path,
    dest: Path,
    duration: int,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        log(f"DRY-RUN kling_o3 → {dest.name} ({duration}s, char={char_path.name})")
        return {"ok": True, "dry_run": True, "video_path": str(dest)}

    from lib.credential_store import get_secret  # noqa: WPS433
    from kling_o3_client import run_beat_generation  # noqa: WPS433

    api_key = get_secret("WAVESPEED_API_KEY")
    if not api_key:
        fail("WAVESPEED_API_KEY not configured")

    dest.parent.mkdir(parents=True, exist_ok=True)
    result = run_beat_generation(
        api_key, prompt, char_path, bg_path, dest,
        duration=duration, speaker="Chipper",
    )
    if not result.get("ok"):
        fail(f"Kling O3 failed: {result!r}")
    return result


def run_teleport_glass(dest: Path, start_image: Path, dry_run: bool) -> Path:
    if dry_run:
        log(f"DRY-RUN teleport_glass → {dest.name}")
        return dest

    from teleport_glass_inserter import (  # noqa: WPS433
        generate_end_frame,
        image_dimensions,
        kling_poll_with_dns_workaround,
        kling_submit,
        load_wavespeed_key,
        download_clip,
    )

    scratch = dest.parent
    end_frame = scratch / "_tmp_white_end_frame.png"
    w, h = image_dimensions(start_image)
    generate_end_frame(end_frame, width=w, height=h)
    api_key = load_wavespeed_key()
    task_id = kling_submit(start_image, end_frame, api_key)
    url = kling_poll_with_dns_workaround(task_id, api_key)
    download_clip(url, dest)
    return dest


def run_teleport_burst_from_speak(speak_video: Path, dest: Path, dry_run: bool) -> Path:
    """Generate LD-737 mirror burst from the speak clip's frozen last frame."""
    if dry_run:
        log(f"DRY-RUN burst-from-speak → {dest.name}")
        return dest
    from teleport_glass_inserter import run_burst_from_frozen_speak_frame  # noqa: WPS433

    scratch = dest.parent / "_burst_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    log(f"LD-737 burst from frozen last frame of {speak_video.name}")
    return run_burst_from_frozen_speak_frame(
        speak_video, dest, scratch_dir=scratch, dry_run=False,
    )


def cmd_plan(_args: argparse.Namespace) -> int:
    m = load_manifest()
    root = project_root()
    log(f"project_root={root}")
    log(f"manifest={manifest_path()}")
    log(f"variant={m.get('variant')} clip_b_locked_line={m.get('clip_b_locked_line')!r}")
    for k in ("mirror_char", "studio_bg", "neutral_char"):
        p = resolve_asset(m, k)
        log(f"  asset {k}: {p} ({p.stat().st_size:,} B)")
    clip_b = resolve_output(m, "clip_b_master")
    log(f"  clip_b_master: {clip_b} exists={clip_b.is_file()}")
    modules_dir = resolve_output(m, "modules_dir")
    if modules_dir.is_dir():
        mods = sorted(modules_dir.iterdir())
        log(f"  modules: {[x.name for x in mods if x.is_dir()]}")
    else:
        log("  modules: (none yet)")
    return 0


def cmd_build_clip_b(args: argparse.Namespace) -> int:
    m = load_manifest()
    mirror = resolve_asset(m, "mirror_char")
    bg = resolve_asset(m, "studio_bg")
    locked = str(m.get("clip_b_locked_line") or "").strip()
    if not locked:
        fail("clip_b_locked_line empty in manifest")

    speak_out = resolve_output(m, "clip_b_speak")
    glass_out = resolve_output(m, "clip_b_glass")
    master_out = resolve_output(m, "clip_b_master")
    scratch = master_out.parent / "_scratch"
    speak_out = scratch / "clip_b_speak.mp4"
    glass_out = scratch / "clip_b_glass.mp4"

    duration = int(m.get("clip_b_kling_duration_s") or 6)
    hold_s = _manifest_whiteout_hold_s(m)

    prompt = build_chipper_voice_prompt(CLIP_B_STAGING, locked)
    log(f"Clip B speak ({duration}s): {locked!r}")
    run_kling_o3_clip(
        prompt=prompt, char_path=mirror, bg_path=bg,
        dest=speak_out, duration=duration, dry_run=args.dry_run,
    )

    log("Clip B teleport-glass (LD-737)")
    run_teleport_glass(glass_out, mirror, args.dry_run)

    if args.dry_run:
        log("DRY-RUN complete — no concat/hold")
        return 0

    joined = scratch / "clip_b_joined.mp4"
    ffmpeg_concat_videos([speak_out, glass_out], joined)
    hold_last_frame(joined, master_out, hold_s)
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "clip_b_locked_line": locked,
        "parts": [str(speak_out), str(glass_out)],
        "hold_s": hold_s,
        "duration_s": ffprobe_duration(master_out),
    }
    master_out.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    log(f"✓ clip_b_master → {master_out} ({meta['duration_s']:.2f}s)")
    return 0


def cmd_build_clip_a(args: argparse.Namespace) -> int:
    m = load_manifest()
    if not args.module:
        fail("--module required")
    script = (args.script or "").strip()
    if not script:
        fail("--script required (module-specific patter for Clip A)")

    neutral = resolve_asset(m, "neutral_char")
    bg = resolve_asset(m, "studio_bg")
    modules_dir = resolve_output(m, "modules_dir")
    mod_dir = modules_dir / args.module
    mod_dir.mkdir(parents=True, exist_ok=True)
    dest = mod_dir / "clip_a.mp4"

    duration = int(args.duration or m.get("clip_a_default_duration_s") or 8)
    prompt = build_chipper_voice_prompt(CLIP_A_STAGING, script)
    log(f"Clip A module={args.module!r} ({duration}s)")
    run_kling_o3_clip(
        prompt=prompt, char_path=neutral, bg_path=bg,
        dest=dest, duration=duration, dry_run=args.dry_run,
    )
    if not args.dry_run:
        meta = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "module": args.module,
            "script": script,
            "duration_s": ffprobe_duration(dest),
        }
        (mod_dir / "clip_a.json").write_text(json.dumps(meta, indent=2) + "\n")
        log(f"✓ clip_a → {dest}")
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    m = load_manifest()
    if not args.module:
        fail("--module required")

    clip_b = resolve_output(m, "clip_b_master")
    if not clip_b.is_file():
        fail(f"clip_b_master missing — run build-clip-b first: {clip_b}")

    clip_a = resolve_output(m, "modules_dir") / args.module / "clip_a.mp4"
    if not clip_a.is_file():
        fail(f"clip_a missing — run build-clip-a --module {args.module}: {clip_a}")

    out = resolve_output(m, "modules_dir") / args.module / "intro_teleport_tail.mp4"
    if args.dry_run:
        log(f"DRY-RUN assemble {clip_a.name} + {clip_b.name} → {out.name}")
        return 0

    ffmpeg_concat_videos([clip_a, clip_b], out)
    dur = ffprobe_duration(out)
    log(f"✓ intro_teleport_tail → {out} ({dur:.2f}s)")

    if args.write_stitch_slot:
        event = args.event or "Event_1"
        _write_stitch_slot(event, out, args.module)
    return 0


def _write_stitch_slot(event: str, video_path: Path, module: str) -> None:
    """Upsert intro stitch slot with teleport tail (manual review before anchor)."""
    event_dir = project_root() / "Production" / (
        event if event.startswith("Event_") else f"Event_{event}"
    )
    if not event_dir.is_dir():
        fail(f"event dir not found: {event_dir}")

    log(f"Stitch slot hint: import {video_path.name} into Stitcher intro slot for {event}")
    log("  Then: python3 Production/scripts/save_intro_stitch_anchor.py")
    sidecar = event_dir / "intro" / "TELEPORT_INTRO_TAIL.json"
    sidecar.write_text(json.dumps({
        "module": module,
        "video_path": str(video_path),
        "source": "teleport_intro_kit",
        "written_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    log(f"  Sidecar pointer → {sidecar}")


def _canonical_dir(manifest: dict, slot: int) -> Path:
    base = resolve_output(manifest, "canonical_dir")
    return base / f"variant_{slot}"


def _shared_glass_path(manifest: dict) -> Path:
    return resolve_output(manifest, "clip_b_glass")


def cmd_build_shared_glass(args: argparse.Namespace) -> int:
    """Build LD-737 whiteout once — reused for all 3 canonical variants."""
    m = load_manifest()
    mirror = resolve_asset(m, "mirror_char")
    glass_out = _shared_glass_path(m)
    log("Shared teleport-glass (LD-737)")
    run_teleport_glass(glass_out, mirror, args.dry_run)
    if not args.dry_run:
        log(f"✓ shared glass → {glass_out} ({ffprobe_duration(glass_out):.2f}s)")
    return 0


def _load_beat_for_canonical_trim(beat_id: str, speak_path: Path) -> dict | None:
    """Resolve trim settings from sidecar, else preserved Beat Gen snapshot."""
    if not beat_id:
        return None
    try:
        import beat_generator as bg  # noqa: WPS433

        sidecar_path = project_root() / "Production" / "beat_generator_state.json"
        if sidecar_path.is_file():
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            _, beat = bg.find_beat(sidecar, beat_id)
            if beat:
                return dict(beat)
    except Exception:
        pass
    event_dir = speak_path.parent.parent
    preserved = (
        event_dir / "kling_o3_clips" / "_preserved" / "latest" / f"{beat_id}.json"
    )
    if preserved.is_file():
        try:
            return json.loads(preserved.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# Canonical mirror compose must use the full Element O3 speak master. Beat-row
# trim_back trims the finished intro_tail for stitch export only — applying it at
# compose time truncates dialogue before the LD-737 burst (e.g. trim_back=4 on
# a 6s speak → "ready? jus-" then explosion).
MIN_CANONICAL_INTRO_TAIL_DURATION_S = 10.0


def _resolve_speak_clip_for_canonical(speak_path: Path, beat_id: str, scratch: Path) -> Path:
    """Return full speak_source for mirror compose — never apply Beat Gen export trims."""
    if beat_id:
        log(f"  canonical speak for {beat_id}: using full clip (export trims not applied at compose)")
    return speak_path


def cmd_build_canonical_variants(args: argparse.Namespace) -> int:
    """Build intro tails from existing Beat Gen speak clips + burst overlay (no new Kling by default)."""
    from teleport_intro_canonical import (  # noqa: WPS433
        load_registry,
        save_registry,
        upsert_variant,
    )

    m = load_manifest(guide=getattr(args, "guide", None))
    root = project_root()
    kit_guide = str(m.get("guide") or getattr(args, "guide", None) or "").strip() or None
    hold_s = _manifest_whiteout_hold_s(m)
    burst_overlay = Path(args.burst_overlay) if args.burst_overlay else _shared_glass_path(m)
    if not burst_overlay.is_absolute():
        burst_overlay = (root / burst_overlay).resolve()
    if not args.dry_run and not args.force_glass and not burst_overlay.is_file():
        fail(f"burst overlay missing (build-shared-glass once, or pass --burst-overlay): {burst_overlay}")

    sources: list[tuple[int, Path, str, str]] = []

    if args.speak:
        for i, pstr in enumerate(args.speak):
            p = Path(pstr)
            if not p.is_file():
                fail(f"speak clip missing: {p}")
            sources.append((i, p, args.label[i] if args.label and i < len(args.label) else f"v{i}", ""))
    else:
        reg = load_registry(root, guide=kit_guide)
        for v in sorted(reg.get("variants") or [], key=lambda x: int(x.get("slot", 0))):
            sp = Path(str(v.get("speak_source") or ""))
            if not sp.is_file():
                fail(f"registry speak_source missing for slot {v.get('slot')}: {sp}")
            sources.append((
                int(v["slot"]),
                sp,
                str(v.get("label") or f"variant_{v['slot']}"),
                str(v.get("beat_id") or ""),
            ))

    if not sources:
        fail("no speak sources — pass --speak a.mp4 b.mp4 c.mp4 or populate canonical_registry.json")

    reg = load_registry(root, guide=kit_guide)
    slot_filter = set(args.slots) if getattr(args, "slots", None) else None

    trim_scratch = root / "Production/templates/arlo_teleport_intro/_scratch/_speak_trim"
    compose_scratch = root / "Production/templates/arlo_teleport_intro/_scratch/_compose"
    kit_root = manifest_path().parent
    if kit_root.name == "chipper_teleport_intro" or kit_root.name == "arlo_teleport_intro":
        trim_scratch = kit_root / "_scratch/_speak_trim"
        compose_scratch = kit_root / "_scratch/_compose"
    trim_scratch.mkdir(parents=True, exist_ok=True)
    for slot, speak_path, label, beat_id in sources:
        if slot_filter is not None and slot not in slot_filter:
            continue
        out_dir = _canonical_dir(m, slot)
        out_dir.mkdir(parents=True, exist_ok=True)
        tail = out_dir / "intro_tail.mp4"
        rel_tail = tail.relative_to(root)
        slot_scratch = compose_scratch / f"variant_{slot}"

        speak_for_concat = _resolve_speak_clip_for_canonical(speak_path, beat_id, trim_scratch)
        log(f"Canonical variant {slot} ({label}): {speak_path.name} + overlay burst → intro_tail.mp4")
        if args.dry_run:
            continue

        if args.force_glass:
            burst = out_dir / "glass_burst.mp4"
            run_teleport_burst_from_speak(speak_for_concat, burst, dry_run=False)
            overlay_src = burst
            burst_method = "kling_from_frozen_frame"
        else:
            overlay_src = burst_overlay
            burst_method = "overlay_on_frozen_frame"

        burst_use_s = _manifest_burst_use_s(m, overlay_src)
        log(f"  burst cap: {burst_use_s:.2f}s (manifest canonical_burst_max_s / teleport_glass.duration_s)")
        ffmpeg_compose_intro_tail(
            speak_for_concat,
            overlay_src,
            tail,
            hold_s=hold_s,
            scratch=slot_scratch,
            burst_method=burst_method,
            burst_use_s=burst_use_s,
        )

        tail_dur = ffprobe_duration(tail)
        if tail_dur < MIN_CANONICAL_INTRO_TAIL_DURATION_S:
            fail(
                f"intro_tail too short ({tail_dur:.2f}s < {MIN_CANONICAL_INTRO_TAIL_DURATION_S}s) "
                f"for slot {slot} — speak may have been truncated; use full speak_source"
            )

        meta = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "slot": slot,
            "label": label,
            "speak_source": str(speak_path),
            "burst_overlay": str(overlay_src),
            "burst_method": burst_method,
            "burst_use_s": round(burst_use_s, 3),
            "duration_s": tail_dur,
            "speech_loudnorm": {
                "applied": True,
                "target_i_lufs": -19.0,
                "target_tp_dbtp": -1.5,
                "target_lra_lu": 11.0,
                "recipe": "STITCH_SPEECH_LOUDNORM_V1",
            },
        }
        (out_dir / "intro_tail.json").write_text(json.dumps(meta, indent=2) + "\n")
        upsert_variant(
            reg,
            slot=slot,
            speak_source=str(speak_path),
            intro_tail_rel=str(rel_tail),
            label=label,
            beat_id=beat_id,
        )
        for vi, vr in enumerate(reg.get("variants") or []):
            if int(vr.get("slot", -1)) == slot:
                reg["variants"][vi]["built_at"] = meta["built_at"]
                break
        log(f"  ✓ {tail} ({meta['duration_s']:.2f}s)")

    if not args.dry_run:
        reg["built_at"] = datetime.now(timezone.utc).isoformat()
        if args.force_glass:
            reg["burst_method"] = "kling_from_frozen_frame"
            reg.pop("burst_overlay_rel", None)
        else:
            reg["burst_method"] = "overlay_on_frozen_frame"
            reg["burst_overlay_rel"] = (
                _path_rel_to_root(burst_overlay, root) if burst_overlay.is_file() else None
            )
        save_registry(root, reg, guide=kit_guide)
        log("✓ canonical_registry updated")
    return 0


def cmd_register_canonical_sources(args: argparse.Namespace) -> int:
    """Seed canonical_registry.json from Beat Gen clip paths (before whiteout build)."""
    from teleport_intro_canonical import load_registry, save_registry, upsert_variant

    if len(args.speak) != 3:
        fail("register-canonical-sources requires exactly 3 --speak paths (slots 0,1,2)")

    root = project_root()
    reg = load_registry(root)
    m = load_manifest()
    labels = args.label or ["event1_tail", "event2_tail", "event3_tail"]
    beat_ids = args.beat_id or ["", "", ""]

    for slot, (pstr, label, bid) in enumerate(zip(args.speak, labels, beat_ids)):
        p = Path(pstr)
        if not p.is_file():
            fail(f"speak clip missing: {p}")
        tail = _canonical_dir(m, slot) / "intro_tail.mp4"
        rel_tail = tail.relative_to(root)
        upsert_variant(
            reg,
            slot=slot,
            speak_source=str(p.resolve()),
            intro_tail_rel=str(rel_tail),
            label=label,
            beat_id=bid,
        )
    save_registry(root, reg)
    log(f"Registered 3 speak sources → {registry_path(root)}")
    log("Next: doppler run -- python3 Production/tools/teleport_intro_kit.py build-canonical-variants")
    return 0


def cmd_plan_canonical(_args: argparse.Namespace) -> int:
    from teleport_intro_canonical import (
        intro_tail_variant_index,
        load_registry,
        parse_event_number,
        resolve_canonical_tail_for_event,
    )

    root = project_root()
    reg = load_registry(root)
    log("=== Canonical intro tails (3-variant rotation) ===")
    log(f"registry: {registry_path(root)}")
    for v in reg.get("variants") or []:
        slot = v.get("slot")
        tail = root / str(v.get("intro_tail_rel") or "")
        log(f"  slot {slot} {v.get('label')}: tail exists={tail.is_file()} speak={Path(v.get('speak_source','')).name}")
    for ev in ("Event_1", "Event_2", "Event_3", "Event_4"):
        n = parse_event_number(ev)
        if reg.get("single_canonical"):
            slot = 0
            tail = resolve_canonical_tail_for_event(ev, root, phase="pre")
            log(f"  {ev} (n={n}) → single canonical slot 0 tail={'OK' if tail else 'MISSING'}")
        else:
            slot = intro_tail_variant_index(n)
            tail = resolve_canonical_tail_for_event(ev, root, phase="pre")
            log(f"  {ev} (n={n}) → slot {slot} tail={'OK' if tail else 'MISSING'}")
    return 0


def registry_path(root: Path) -> Path:
    from teleport_intro_canonical import registry_path as rp
    return rp(root)


def cmd_apply_intro_tail(args: argparse.Namespace) -> int:
    from teleport_intro_canonical import parse_event_number, resolve_canonical_tail_for_event

    event = args.event or "Event_1"
    tail = resolve_canonical_tail_for_event(event, project_root(), phase="pre")
    if not tail or not tail.is_file():
        fail(f"no canonical intro tail for {event} — build variants first")
    _write_stitch_slot(event, tail, args.module or "chipper_teleport")
    n = parse_event_number(event)
    log(f"Applied slot {(n - 1) % 3} tail for {event}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chipper teleport intro kit (Option B)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Show manifest paths and build status")
    p_plan.set_defaults(func=cmd_plan)

    p_b = sub.add_parser("build-clip-b", help="Build locked Clip B master (once)")
    p_b.add_argument("--dry-run", action="store_true")
    p_b.set_defaults(func=cmd_build_clip_b)

    p_a = sub.add_parser("build-clip-a", help="Build variable Clip A for one module")
    p_a.add_argument("--module", required=True, help="e.g. tessa, luna")
    p_a.add_argument("--script", required=True, help="Module-specific spoken patter")
    p_a.add_argument("--duration", type=int, default=None)
    p_a.add_argument("--dry-run", action="store_true")
    p_a.set_defaults(func=cmd_build_clip_a)

    p_asm = sub.add_parser("assemble", help="Concat clip_a + clip_b_master")
    p_asm.add_argument("--module", required=True)
    p_asm.add_argument("--event", default="Event_1")
    p_asm.add_argument("--write-stitch-slot", action="store_true")
    p_asm.add_argument("--dry-run", action="store_true")
    p_asm.set_defaults(func=cmd_assemble)

    p_glass = sub.add_parser("build-shared-glass", help="Build shared LD-737 whiteout (once)")
    p_glass.add_argument("--dry-run", action="store_true")
    p_glass.set_defaults(func=cmd_build_shared_glass)

    p_reg = sub.add_parser(
        "register-canonical-sources",
        help="Register 3 Beat Gen speak clips in canonical_registry.json",
    )
    p_reg.add_argument("--speak", nargs=3, required=True, help="3 speak MP4 paths (slots 0,1,2)")
    p_reg.add_argument("--label", nargs=3, default=None)
    p_reg.add_argument("--beat-id", nargs=3, default=None, dest="beat_id")
    p_reg.set_defaults(func=cmd_register_canonical_sources)

    p_cv = sub.add_parser(
        "build-canonical-variants",
        help="Build intro_tail.mp4 per slot (Beat Gen speak + burst overlay on frozen frame)",
    )
    p_cv.add_argument(
        "--guide",
        default=None,
        help="Teleport intro guide character (Arlo | Chipper); default from registry",
    )
    p_cv.add_argument("--speak", nargs="*", help="Override: 3 speak MP4s in slot order")
    p_cv.add_argument("--label", nargs="*", default=None)
    p_cv.add_argument("--burst-overlay", default=None, dest="burst_overlay",
                        help="LD-737 burst MP4 to overlay (default: shared clip_b_glass_shared.mp4)")
    p_cv.add_argument("--dry-run", action="store_true")
    p_cv.add_argument("--force-glass", action="store_true",
                        help="Regenerate per-variant Kling burst from frozen frame (costs $0.45 each)")
    p_cv.add_argument(
        "--slots",
        nargs="*",
        type=int,
        default=None,
        help="Rebuild only these slot indices (0, 1, 2); default all registered slots",
    )
    p_cv.set_defaults(func=cmd_build_canonical_variants)

    p_pc = sub.add_parser("plan-canonical", help="Show rotation map + build status")
    p_pc.set_defaults(func=cmd_plan_canonical)

    p_apply = sub.add_parser("apply-intro-tail", help="Write TELEPORT_INTRO_TAIL.json for an event")
    p_apply.add_argument("--event", default="Event_1")
    p_apply.add_argument("--module", default="chipper_teleport")
    p_apply.set_defaults(func=cmd_apply_intro_tail)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

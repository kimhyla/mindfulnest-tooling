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


def manifest_path() -> Path:
    env = os.environ.get("TELEPORT_INTRO_MANIFEST")
    if env:
        return Path(env)
    try:
        from teleport_intro_canonical import active_manifest_path

        active = active_manifest_path(project_root())
        if active.is_file():
            return active
    except Exception:
        pass
    dropbox = project_root() / MANIFEST_REL
    if dropbox.is_file():
        return dropbox
    return PROD_DIR / "templates" / "chipper_teleport_intro" / "manifest.json"


def load_manifest() -> dict[str, Any]:
    path = manifest_path()
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


def ffmpeg_compose_intro_tail(
    speak: Path,
    burst_overlay: Path,
    dest: Path,
    *,
    hold_s: float,
    scratch: Path,
    burst_method: str = "overlay_on_frozen_frame",
) -> None:
    """Speak + burst tail + whiteout hold.

    ``kling_from_frozen_frame``: burst MP4 was generated from this speak clip's
    frozen last frame — concat directly (never lighten-blend onto the freeze again;
    that duplicates Chipper and causes the ghost/double-exposure artifact).

    ``overlay_on_frozen_frame``: shared/generic LD-737 burst overlaid on freeze only.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    joined = scratch / "_joined.mp4"
    if burst_method == "kling_from_frozen_frame":
        ffmpeg_concat_speak_and_burst(speak, burst_overlay, joined)
    else:
        burst_seg = scratch / "_burst_on_freeze.mp4"
        ffmpeg_burst_overlay_on_frozen_speak(speak, burst_overlay, burst_seg, scratch=scratch)
        ffmpeg_concat_speak_and_burst(speak, burst_seg, joined)
        burst_seg.unlink(missing_ok=True)
    hold_last_frame(joined, dest, hold_s)
    joined.unlink(missing_ok=True)


def ffmpeg_concat_speak_and_burst(speak: Path, burst: Path, dest: Path) -> None:
    """Append burst segment after speak (same frame size)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sw, sh = ffprobe_video_size(speak)
    bw, bh = ffprobe_video_size(burst)
    burst_dur = ffprobe_duration(burst)
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".hold_tmp.mp4")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-vf", f"tpad=stop_mode=clone:stop_duration={hold_s:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
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
    hold_s = float(m.get("clip_b_whiteout_hold_s") or 2.5)

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


def _resolve_speak_clip_for_canonical(speak_path: Path, beat_id: str, scratch: Path) -> Path:
    """Use Beat Gen trim settings when beat_id is known (sidecar or preserved beat)."""
    if not beat_id:
        return speak_path
    try:
        import beat_generator as bg  # noqa: WPS433

        beat = _load_beat_for_canonical_trim(beat_id, speak_path)
        if not beat:
            return speak_path
        beat = dict(beat)
        beat["kling_o3_video_path"] = str(speak_path)
        dest = scratch / f"{beat_id}_speak_trim.mp4"
        trimmed = bg.materialize_kling_o3_trimmed_clip(beat, dest, source_path=speak_path)
        if trimmed != speak_path and trimmed.is_file():
            log(f"  trim applied for {beat_id}: start={beat.get('kling_o3_trim_start', 0)} "
                f"back={beat.get('kling_o3_trim_back')}")
        return trimmed
    except Exception as exc:
        log(f"  trim skipped for {beat_id}: {exc}")
        return speak_path


def cmd_build_canonical_variants(args: argparse.Namespace) -> int:
    """Build intro tails from existing Beat Gen speak clips + burst overlay (no new Kling by default)."""
    from teleport_intro_canonical import (  # noqa: WPS433
        load_registry,
        save_registry,
        upsert_variant,
    )

    m = load_manifest()
    root = project_root()
    kit_guide = str(m.get("guide") or "").strip() or None
    hold_s = float(m.get("clip_b_whiteout_hold_s") or 2.5)
    burst_overlay = Path(args.burst_overlay) if args.burst_overlay else _shared_glass_path(m)
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

        ffmpeg_compose_intro_tail(
            speak_for_concat,
            overlay_src,
            tail,
            hold_s=hold_s,
            scratch=slot_scratch,
            burst_method=burst_method,
        )

        meta = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "slot": slot,
            "label": label,
            "speak_source": str(speak_path),
            "burst_overlay": str(overlay_src),
            "burst_method": burst_method,
            "duration_s": ffprobe_duration(tail),
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
                str(burst_overlay.relative_to(root)) if burst_overlay.is_file() else None
            )
        save_registry(root, reg, guide=kit_guide)
        log(f"✓ canonical_registry → {registry_path(root, guide=kit_guide)}")
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

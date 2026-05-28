#!/usr/bin/env python3
"""Teleport-glass magic transition inserter.

Per LD-741 TELEPORT_GLASS_INSERTER_TOOL_V1 (locked 2026-05-17,
SHIPPED 2026-05-20 after fabrication-scan caught LD-741 as locked-without-
implementation per Kim 2026-05-20 directive). Recipe constants are
verbatim from LD-737 TELEPORT_GLASS_TRANSITION_RECIPE_V1.

Generates the canonical magic transition (Chipper holds mirror →
brilliant golden-white light explodes → engulfs frame in whiteout)
used at the end of every Phase-A-bound module. Auto-injects the
resulting clip as the next available option on the named beat.

CLI:
    --beat        REQUIRED, e.g. beat_19
    --event       default Event_1
    --video       default resolution; one of resolution|intro
    --start-image override default chipper-mirror-forward PNG
    --end-image   override programmatic white-glow end frame
    --no-insert   submit + download only; skip state mutation
    --dry-run     resolve paths + plan; no API call, no state mutation

USAGE EXAMPLES:
    # Dry-run (no cost, no mutation)
    python3 Production/tools/teleport_glass_inserter.py --beat beat_19 --dry-run

    # Real submission ($0.45 + 2-3 min) — beat must exist in state.json
    python3 Production/tools/teleport_glass_inserter.py --beat beat_19 --event Event_1

Cost: $0.45/submission. Latency: ~2-3 min Kling inference.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────
# LD-737 recipe constants — DO NOT MODIFY without superseding LD-737.
# ────────────────────────────────────────────────────────────────────────
KLING_ENDPOINT = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
KLING_DURATION_S = 5
KLING_CFG_SCALE = 0.5
KLING_DIM_W = 1448
KLING_DIM_H = 1086
WAVESPEED_IP = "49.51.190.24"  # api.wavespeed.ai real Tencent IP per LD-379
LUMINANCE_PASS_THRESHOLD = 0.95  # tail frame must be >=95% white

POSITIVE_PROMPT = (
    "Cinematic teleport magic transition: blue bird holds a glowing mirror. "
    "Brilliant golden-white magical light EXPLODES outward from the mirror's "
    "surface in radiating waves of pure energy, growing blindingly bright. "
    "The light expands rapidly outward, engulfing the entire frame, "
    "dissolving every forest detail into pure radiant whiteout. By the end "
    "the screen is completely filled with pure white light, all environment "
    "elements have dissolved into the brilliant glow, total magical whiteout "
    "transformation. Cinematic 4:3 composition. Beak at rest, no dialogue "
    "in video. Silent magical light explosion, natural interpolation between "
    "the two provided frames."
)

NEGATIVE_PROMPT = (
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing"
)

# ────────────────────────────────────────────────────────────────────────
# Path resolution. CODE tree lookups vs runtime DATA root (LD-505).
# ────────────────────────────────────────────────────────────────────────
TOOLS_DIR = Path(__file__).resolve().parent
PROD_DIR = TOOLS_DIR.parent
sys.path.insert(0, str(PROD_DIR))
try:
    from lib.paths import dropbox_root  # type: ignore
    DROPBOX_ROOT = dropbox_root()
except Exception:
    # Fallback when running outside repo: hardcoded default per LD-505 pattern.
    DROPBOX_ROOT = Path(
        os.environ.get(
            "MN_DROPBOX_ROOT",
            "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files",
        )
    )

DEFAULT_START_IMAGE = (
    DROPBOX_ROOT / "Production" / "Guide_Bird" / "poses"
    / "chipper in woods with mirror face forward final.png"
)


def log(msg: str) -> None:
    print(f"[teleport_glass] {msg}", flush=True)


def fail(msg: str, code: int = 1) -> None:
    log(f"FATAL: {msg}")
    sys.exit(code)


# ────────────────────────────────────────────────────────────────────────
# End-frame generation (LD-737 §INPUT 2 verbatim).
# ────────────────────────────────────────────────────────────────────────
def generate_end_frame(out_path: Path) -> Path:
    """Programmatic white-glow end frame. Deterministic; safe to re-run."""
    try:
        from PIL import Image, ImageFilter, ImageDraw  # type: ignore
    except ImportError:
        fail("Pillow required. pip install Pillow.")
    w, h = KLING_DIM_W, KLING_DIM_H
    end = Image.new("RGB", (w, h), (255, 254, 250))
    draw = ImageDraw.Draw(end)
    cx, cy = w // 2, h // 2
    for r in range(min(w, h) // 3, 0, -20):
        alpha = int(8 * (r / (min(w, h) // 3)))
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(255, 248 - alpha, 230 - alpha * 2),
        )
    end = end.filter(ImageFilter.GaussianBlur(radius=120))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    end.save(out_path, "PNG")
    log(f"end frame generated → {out_path} ({out_path.stat().st_size:,} B)")
    return out_path


def png_to_data_uri(p: Path) -> str:
    b = p.read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


# ────────────────────────────────────────────────────────────────────────
# WaveSpeed API. Credentials parsed from API_KEYS_MASTER.md (preserved
# fix per LD-741 — avoids production_server import-time deadlock).
# ────────────────────────────────────────────────────────────────────────
def load_wavespeed_key() -> str:
    candidates = [
        DROPBOX_ROOT / "Production" / "API_KEYS_MASTER.md",
        PROD_DIR / "API_KEYS_MASTER.md",
    ]
    for p in candidates:
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            low = line.lower()
            if "wavespeed" in low and "key" in low:
                # tolerate "key: VALUE", "key=VALUE", "key VALUE"
                for sep in [":", "=", " "]:
                    if sep in line:
                        candidate = line.split(sep, 1)[1].strip().strip("`'\"")
                        if candidate and not candidate.lower().startswith("wavespeed"):
                            return candidate
    fail("WaveSpeed API key not found in API_KEYS_MASTER.md")
    return ""  # unreachable


def kling_submit(start_image: Path, end_image: Path, api_key: str) -> str:
    """POST start+end frames to Kling. Returns task_id."""
    import urllib.request

    body = {
        "duration": KLING_DURATION_S,
        "cfg_scale": KLING_CFG_SCALE,
        "sound": False,
        "image": png_to_data_uri(start_image),
        "end_image": png_to_data_uri(end_image),
        "negative_prompt": NEGATIVE_PROMPT,
        "prompt": POSITIVE_PROMPT,
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        KLING_ENDPOINT,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    log(f"submitting to {KLING_ENDPOINT} (body {len(data):,} B)")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    task_id = (result.get("data") or {}).get("id") or result.get("id")
    if not task_id:
        fail(f"no task_id in response: {result!r}")
    log(f"task_id = {task_id}")
    return task_id


def kling_poll_with_dns_workaround(task_id: str, api_key: str, timeout_s: int = 300) -> str:
    """Poll Kling via curl --resolve (per LD-737 — kling_poll_fresh hangs)."""
    url = f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        proc = subprocess.run(
            [
                "curl", "-sS",
                "--resolve", f"api.wavespeed.ai:443:{WAVESPEED_IP}",
                "-H", f"Authorization: Bearer {api_key}",
                url,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            log(f"poll curl error rc={proc.returncode}: {proc.stderr.strip()}")
            time.sleep(5); continue
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            log(f"poll non-json: {proc.stdout[:200]}"); time.sleep(5); continue
        data = payload.get("data") or payload
        status = data.get("status", "")
        log(f"poll status={status}")
        if status == "completed":
            outputs = data.get("outputs") or []
            if outputs:
                return outputs[0]
            output_url = data.get("output") or data.get("url")
            if output_url:
                return output_url
            fail(f"completed but no output URL: {payload!r}")
        if status == "failed":
            fail(f"Kling submission failed: {payload!r}")
        time.sleep(8)
    fail(f"poll timeout after {timeout_s}s")
    return ""  # unreachable


def download_clip(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    dest.write_bytes(data)
    log(f"downloaded {len(data):,} B → {dest}")


# ────────────────────────────────────────────────────────────────────────
# State mutation — atomic write + DS-22 read-back verify.
# ────────────────────────────────────────────────────────────────────────
def insert_option(
    state_path: Path,
    video_role: str,
    beat_id: str,
    clip_filename: str,
    task_id: str,
) -> int:
    """Append clip as next available option on the named beat. Returns new option_index (1-based)."""
    backup = state_path.with_suffix(
        f".bak_teleport_glass_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    shutil.copy2(state_path, backup)
    log(f"pre-mutation backup → {backup.name}")

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    partition = state.setdefault("videos", {}).setdefault(video_role, {})
    beats = partition.setdefault("beats", {})
    beat = beats.get(beat_id)
    if not beat:
        fail(f"beat {beat_id} not found in videos.{video_role}.beats")

    phase_1 = beat.setdefault("phase_1", {})
    options = phase_1.setdefault("options", [])
    new_idx = len(options) + 1  # 1-based
    options.append({
        "task_id": task_id,
        "status": "completed",
        "file": clip_filename,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "submitted_at_epoch": int(time.time()),
        "source": "teleport_glass_inserter",
        "recipe_ld": "LD-737",
        "retries": 0,
        "last_error": None,
    })
    beat["_version"] = int(beat.get("_version", 0) or 0) + 1
    beat["text_last_updated_at"] = datetime.now(timezone.utc).isoformat()

    tmp = state_path.with_suffix(".json.teleport_tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, state_path)
    log(f"state mutated: appended option_{new_idx} to {video_role}.{beat_id}")

    # DS-22 read-back verify
    with open(state_path, encoding="utf-8") as f:
        verify = json.load(f)
    v_beat = verify["videos"][video_role]["beats"][beat_id]
    v_opt = v_beat["phase_1"]["options"][new_idx - 1]
    if v_opt.get("task_id") != task_id or v_opt.get("recipe_ld") != "LD-737":
        fail(f"DS-22 read-back failed: {v_opt!r}")
    log(f"DS-22 verify OK (task_id + recipe_ld match)")
    return new_idx


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--beat", required=True, help="e.g. beat_19")
    ap.add_argument("--event", default="Event_1")
    ap.add_argument("--video", default="resolution", choices=["resolution", "intro"])
    ap.add_argument("--start-image", default=None)
    ap.add_argument("--end-image", default=None)
    ap.add_argument("--no-insert", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    event_dir = DROPBOX_ROOT / "Production" / args.event
    state_path = event_dir / "production_state.json"
    if not state_path.is_file():
        fail(f"state.json not found at {state_path}")

    # Resolve beat to confirm it exists
    with open(state_path) as f:
        state = json.load(f)
    partition = (state.get("videos") or {}).get(args.video) or {}
    beat = (partition.get("beats") or {}).get(args.beat)
    if not beat:
        fail(f"beat {args.beat} not found in videos.{args.video}.beats — available: "
             f"{sorted((partition.get('beats') or {}).keys())[:10]}")

    options = (beat.get("phase_1") or {}).get("options") or []
    next_idx = len(options) + 1
    clip_filename = f"{args.beat}_option_{next_idx}.mp4"
    clips_dir = event_dir / "animation_clips"
    clip_path = clips_dir / clip_filename

    start_image = Path(args.start_image) if args.start_image else DEFAULT_START_IMAGE
    if not start_image.is_file():
        fail(f"start image not found: {start_image}")
    end_image_path = Path(args.end_image) if args.end_image else (
        event_dir / "_temp_images" / "_tmp_white_end_frame.png"
    )

    log(f"PLAN: video={args.video} beat={args.beat} next_option_idx={next_idx}")
    log(f"      start_image={start_image}")
    log(f"      end_image={end_image_path}")
    log(f"      target_clip={clip_path}")
    log(f"      beat._version bump: {beat.get('_version', 0)} → {int(beat.get('_version', 0) or 0) + 1}")

    if args.dry_run:
        log("DRY-RUN: no API call, no state mutation. Exit.")
        return 0

    api_key = load_wavespeed_key()

    # Generate end frame if needed
    if not args.end_image:
        generate_end_frame(end_image_path)
    elif not end_image_path.is_file():
        fail(f"explicit end-image not found: {end_image_path}")

    # Submit + poll + download
    task_id = kling_submit(start_image, end_image_path, api_key)
    output_url = kling_poll_with_dns_workaround(task_id, api_key)
    download_clip(output_url, clip_path)

    if args.no_insert:
        log("--no-insert: skipping state mutation. Done.")
        return 0

    new_idx = insert_option(
        state_path, args.video, args.beat, clip_filename, task_id
    )
    log(f"SUCCESS: {args.beat} option_{new_idx} inserted. File: {clip_filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

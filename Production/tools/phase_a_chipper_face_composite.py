#!/usr/bin/env python3
"""Composite Kling lipsync face region onto frozen Chipper body plate.

Reads Production/Event_1/phase_a_chipper_composite.yaml (face_polygon from path_picker).
Reusable for all Phase A Chipper modules once mask is locked.

Usage:
  python3 phase_a_chipper_face_composite.py \\
    --lipsync Event_1/phase_a_idle_candidates/chipper_lipsync_h_kling_20260608T031500Z.mp4 \\
    --out Event_1/phase_a_idle_candidates/chipper_lipsync_h_composite_v1.mp4
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

DROPBOX_PROD = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)


def log(msg: str) -> None:
    print(f"[phase_a_composite] {msg}", flush=True)


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML required: pip install PyYAML") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid yaml root in {path}")
    return data


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip() or "0")


def build_polygon_mask(
    polygon: list[list[float]],
    width: int,
    height: int,
    feather_px: int,
    out_path: Path,
) -> None:
    from PIL import Image, ImageDraw, ImageFilter

    if len(polygon) < 3:
        raise ValueError("face_polygon needs ≥3 points")

    pts = [(int(x * width), int(y * height)) for x, y in polygon]
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(pts, fill=255)
    if feather_px > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_px))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(out_path)
    log(f"mask: {out_path.name} ({width}x{height}, feather={feather_px}px, {len(pts)} pts)")


def run_composite(
    *,
    body_png: Path,
    lipsync_mp4: Path,
    mask_png: Path,
    out_mp4: Path,
    width: int,
    height: int,
) -> Path:
    dur = _ffprobe_duration(lipsync_mp4)
    if dur <= 0:
        raise ValueError(f"invalid lipsync duration: {lipsync_mp4}")

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_body = out_mp4.parent / f"_tmp_body_loop_{out_mp4.stem}.mp4"

    # Static body plate looped to lipsync duration.
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1", "-t", f"{dur:.3f}", "-i", str(body_png),
            "-vf", f"scale={width}:{height}:flags=lanczos,fps=25,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
            str(tmp_body),
        ],
        check=True,
        timeout=120,
    )

    # maskedmerge: mask white → lipsync face; black → frozen body.
    filter_complex = (
        f"[1:v]scale={width}:{height}:flags=lanczos,fps=25,format=yuv420p[ls];"
        f"[2:v]scale={width}:{height}:flags=lanczos,format=gray[msk];"
        f"[0:v][ls][msk]maskedmerge[v]"
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(tmp_body),
            "-i", str(lipsync_mp4),
            "-i", str(mask_png),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "1:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest",
            str(out_mp4),
        ],
        check=True,
        timeout=600,
    )
    tmp_body.unlink(missing_ok=True)
    log(
        f"composite: {out_mp4.name} "
        f"({out_mp4.stat().st_size / 1024 / 1024:.1f} MB, {dur:.1f}s)"
    )
    return out_mp4


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event-dir", type=Path, default=DROPBOX_PROD / "Event_1")
    p.add_argument("--config", type=Path, help="composite yaml (default: event-dir/phase_a_chipper_composite.yaml)")
    p.add_argument("--lipsync", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    event = args.event_dir.expanduser().resolve()
    cfg_path = (args.config or event / "phase_a_chipper_composite.yaml").expanduser().resolve()
    cfg = _load_yaml(cfg_path)

    canvas = cfg.get("canvas") or {}
    width = int(canvas.get("width") or 1280)
    height = int(canvas.get("height") or 960)
    feather = int(cfg.get("feather_px") or 6)
    polygon = cfg.get("face_polygon")
    if not polygon:
        log(f"FATAL: face_polygon unset in {cfg_path}")
        return 1

    body_name = cfg.get("body_plate") or "phase_a_chipper_body_plate_v1.png"
    body_png = event / body_name
    if not body_png.is_file():
        log(f"FATAL: body plate not found: {body_png}")
        return 1

    lipsync = args.lipsync.expanduser()
    if not lipsync.is_absolute():
        lipsync = DROPBOX_PROD / lipsync
    if not lipsync.is_file():
        log(f"FATAL: lipsync not found: {lipsync}")
        return 1

    out = args.out.expanduser()
    if not out.is_absolute():
        out = DROPBOX_PROD / out

    mask_png = event / "phase_a_chipper_face_mask_v1.png"
    build_polygon_mask(polygon, width, height, feather, mask_png)
    run_composite(
        body_png=body_png,
        lipsync_mp4=lipsync,
        mask_png=mask_png,
        out_mp4=out,
        width=width,
        height=height,
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

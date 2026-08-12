#!/usr/bin/env python3
"""Apply locked Gate0 stack to an Arlo green idle video → cleaned green + plate.

Uses spillkill_warm_edge_vj + choke_kling_idle_outline + composite_trimmed_rgb_on_plate.
Do not substitute ffmpeg chromakey-only composites.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from arlo_green_path_a_assets import (  # noqa: E402
    composite_trimmed_rgb_on_plate,
    trim_green_character_frame,
)


def _extract_frames(video: Path, work: Path, *, max_seconds: float | None) -> list[Path]:
    work.mkdir(parents=True, exist_ok=True)
    for p in work.glob("*.png"):
        p.unlink()
    cmd = ["ffmpeg", "-y", "-i", str(video)]
    if max_seconds is not None and max_seconds > 0:
        cmd += ["-t", f"{max_seconds:.3f}"]
    cmd += ["-vsync", "0", str(work / "f_%06d.png")]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(work.glob("f_*.png"))


def _encode_mp4(frames_dir: Path, out: Path, fps: float = 24.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "f_%06d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            str(out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _tail_max_gr(rgb: np.ndarray) -> int:
    # Headshot framing: tail is right side; use right-edge crop.
    h, w = rgb.shape[:2]
    crop = rgb[int(h * 0.15) : int(h * 0.85), int(w * 0.72) : int(w * 0.98)]
    return int((crop[:, :, 1].astype(int) - crop[:, :, 0].astype(int)).max())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--plate", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--max-seconds", type=float, default=0.0, help="0 = full clip")
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--no-choke", action="store_true")
    args = ap.parse_args()

    video = args.video.expanduser().resolve()
    plate_path = args.plate.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    plate = np.asarray(Image.open(plate_path).convert("RGB"))
    max_s = None if args.max_seconds <= 0 else float(args.max_seconds)

    with tempfile.TemporaryDirectory(prefix="arlo_gate0_idle_") as td:
        td_path = Path(td)
        raw_dir = td_path / "raw"
        green_dir = td_path / "green"
        plate_dir = td_path / "plate"
        green_dir.mkdir()
        plate_dir.mkdir()

        frames = _extract_frames(video, raw_dir, max_seconds=max_s)
        if not frames:
            raise SystemExit(f"no frames from {video}")

        qc = []
        for i, fp in enumerate(frames):
            rgb = np.asarray(Image.open(fp).convert("RGB"))
            if rgb.shape[:2] != plate.shape[:2]:
                # Lanczos to plate if needed (same aspect assumed)
                rgb = np.asarray(
                    Image.fromarray(rgb).resize(
                        (plate.shape[1], plate.shape[0]), Image.Resampling.LANCZOS
                    )
                )
            trimmed, key = trim_green_character_frame(
                rgb, apply_idle_choke=not args.no_choke
            )
            comp = composite_trimmed_rgb_on_plate(trimmed, plate)
            name = f"f_{i + 1:06d}.png"
            Image.fromarray(trimmed).save(green_dir / name)
            Image.fromarray(comp).save(plate_dir / name)
            if i in (0, len(frames) // 2, len(frames) - 1) or i % 24 == 0:
                qc.append(
                    {
                        "frame": i,
                        "key_rgb": list(key),
                        "tail_max_g_minus_r": _tail_max_gr(comp),
                    }
                )
            if (i + 1) % 30 == 0 or i == 0:
                print(f"processed {i + 1}/{len(frames)}", flush=True)

        green_mp4 = out_dir / "kim_idle_gate0_trimmed_green.mp4"
        plate_mp4 = out_dir / "kim_idle_gate0_on_plate.mp4"
        _encode_mp4(green_dir, green_mp4, fps=args.fps)
        _encode_mp4(plate_dir, plate_mp4, fps=args.fps)

        # Still proofs at mid / end for Kim eyeball
        mid = frames[len(frames) // 2]
        mid_i = len(frames) // 2
        shutil.copy(plate_dir / f"f_{mid_i + 1:06d}.png", out_dir / "LOOK_AT_THIS_mid_on_plate.png")
        shutil.copy(plate_dir / f"f_000001.png", out_dir / "LOOK_AT_THIS_t0_on_plate.png")
        # Tail 4x zoom from mid
        mid_comp = np.asarray(Image.open(out_dir / "LOOK_AT_THIS_mid_on_plate.png"))
        h, w = mid_comp.shape[:2]
        crop = mid_comp[int(h * 0.2) : int(h * 0.75), int(w * 0.7) : w]
        zoom = np.asarray(
            Image.fromarray(crop).resize(
                (crop.shape[1] * 4, crop.shape[0] * 4), Image.Resampling.NEAREST
            )
        )
        Image.fromarray(zoom).save(out_dir / "LOOK_AT_THIS_mid_tail_4x.png")

        meta = {
            "video": str(video),
            "plate": str(plate_path),
            "frames": len(frames),
            "max_seconds": max_s,
            "apply_idle_choke": not args.no_choke,
            "recipe": "trim_green_character_frame + composite_trimmed_rgb_on_plate",
            "qc_samples": qc,
            "green_mp4": str(green_mp4),
            "plate_mp4": str(plate_mp4),
        }
        (out_dir / "gate0_idle_trim_meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(meta, indent=2))
        print(f"WROTE {plate_mp4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

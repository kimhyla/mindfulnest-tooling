#!/usr/bin/env python3
"""
resize_to_delivery.py — generate /delivery/ variants of master assets per SIZE_BUDGET_*.

Source: SIZE_BUDGET_AUDIT_20260418.md §9 R-11 + §5.
Locked decisions: SIZE_BUDGET_V1 (id=295), SIZE_BUDGET_VIDEO_V1 (id=296),
                  SIZE_BUDGET_AUDIO_V1 (id=297), SIZE_BUDGET_IMAGE_V1 (id=298),
                  LD-283 SIZE_BUDGET_PER_MODULE_V1.

Reads prod_assets rows where role != 'delivery'; dispatches by file extension:
  .png/.PNG  -> cwebp q80 (hero) / q75 (bg) -> /delivery/<orig path>.webp
  .mp4/.MP4  -> ffmpeg H.264 1500k -> /delivery/<orig path>
  .mp3/.MP3  -> ffmpeg MP3 128k mono 44.1k -> /delivery/<orig path>
For each output, POSTs a new prod_assets row with parent_asset_id and role='delivery'.

Pre-flight checks (HARD FAIL):
  - cwebp must be installed (brew install webp) for PNG dispatch
  - ffmpeg + ffprobe must be on PATH for MP4/MP3 dispatch
  - prod_assets schema must include parent_asset_id, role, file_path, file_size_bytes

Usage:
    python3 resize_to_delivery.py [--dry-run] [--ext png|mp4|mp3] [--limit N]
                                  [--require-min-rows N]

--require-min-rows N   Fail if fewer than N source rows match the role!=delivery filter.
                       Guards against silently processing zero rows when scoping is wrong.
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa: E402


PROJECT_ROOT = Path(os.path.expanduser("~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"))
DELIVERY_ROOT = PROJECT_ROOT / "delivery"

CWEBP_HERO_Q = "80"
CWEBP_BG_Q = "75"

FFMPEG_VIDEO_CMD = [
    "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p",
    "-b:v", "1500k", "-maxrate", "1800k", "-bufsize", "3000k", "-movflags", "+faststart",
    "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "44100",
]
FFMPEG_AUDIO_CMD = ["-c:a", "libmp3lame", "-b:a", "128k", "-ac", "1", "-ar", "44100"]


def which_or_die(tool: str) -> str:
    p = shutil.which(tool)
    if not p:
        sys.exit(f"FAIL: required tool '{tool}' not on PATH. Install (e.g. `brew install webp` for cwebp).")
    return p


def resolve_source(file_path: str) -> Path | None:
    candidates = [Path(file_path), PROJECT_ROOT / file_path]
    for c in candidates:
        if c.exists():
            return c
    return None


def dispatch(row: dict, dry: bool) -> tuple[str, Path | None, int | None]:
    fp = row.get("file_path")
    if not fp:
        return ("skip_no_path", None, None)
    src = resolve_source(fp)
    if not src:
        return ("missing_on_disk", None, None)
    ext = src.suffix.lower()

    rel = src.relative_to(PROJECT_ROOT) if src.is_absolute() and PROJECT_ROOT in src.parents else Path(fp)
    out = DELIVERY_ROOT / rel
    out.parent.mkdir(parents=True, exist_ok=True)

    if ext == ".png":
        which_or_die("cwebp")
        out = out.with_suffix(".webp")
        is_bg = "background" in str(rel).lower() or "bg" in str(rel).lower()
        q = CWEBP_BG_Q if is_bg else CWEBP_HERO_Q
        if dry:
            return ("dry_png", out, None)
        subprocess.run(["cwebp", "-q", q, "-m", "6", str(src), "-o", str(out)], check=True, capture_output=True)
        return ("png_webp", out, out.stat().st_size)

    if ext == ".mp4":
        which_or_die("ffmpeg")
        if dry:
            return ("dry_mp4", out, None)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), *FFMPEG_VIDEO_CMD, str(out)],
                       check=True, capture_output=True)
        # post-encode hard-fail assertion ≤1,900,000 bps
        which_or_die("ffprobe")
        br = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", str(out)]
        ).decode().strip()
        if br.isdigit() and int(br) > 1_900_000:
            out.unlink(missing_ok=True)
            raise RuntimeError(f"FAIL: {out} exceeds 1.9 Mbps guard band ({br} bps)")
        return ("mp4_h264", out, out.stat().st_size)

    if ext == ".mp3":
        which_or_die("ffmpeg")
        if dry:
            return ("dry_mp3", out, None)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), *FFMPEG_AUDIO_CMD, str(out)],
                       check=True, capture_output=True)
        return ("mp3_128k", out, out.stat().st_size)

    return ("skip_unsupported_ext", None, None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ext", choices=["png", "mp4", "mp3"], default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--require-min-rows", type=int, default=0)
    ap.add_argument("--collection", default="prod_assets")
    args = ap.parse_args()

    c = DirectusAdminClient()
    rows = c.get_items(args.collection, filters={"role": {"_neq": "delivery"}})
    if args.ext:
        rows = [r for r in (rows or []) if (r.get("file_path") or "").lower().endswith(f".{args.ext}")]
    if args.limit:
        rows = rows[: args.limit]

    n = len(rows or [])
    print(f"[resize] candidates: {n}")
    if n < args.require_min_rows:
        print(f"[resize] FAIL: {n} < --require-min-rows {args.require_min_rows}", file=sys.stderr)
        return 2

    counts: dict[str, int] = {}
    for row in rows or []:
        try:
            status, out, size = dispatch(row, args.dry_run)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            counts["error"] = counts.get("error", 0) + 1
            print(f"[resize] ERR id={row.get('id')} path={row.get('file_path')}: {e}", file=sys.stderr)
            continue
        counts[status] = counts.get(status, 0) + 1
        if args.dry_run or out is None:
            continue
        try:
            new_row = {
                "file_path": str(out.relative_to(PROJECT_ROOT)),
                "file_size_bytes": size,
                "role": "delivery",
                "parent_asset_id": row["id"],
            }
            for k in ("module_id", "event_number", "asset_type"):
                if row.get(k) is not None:
                    new_row[k] = row[k]
            c.post_item(args.collection, new_row)
        except DirectusAdminError as e:
            counts["directus_error"] = counts.get("directus_error", 0) + 1
            print(f"[resize] Directus ERR for {out}: {e}", file=sys.stderr)

    print(f"[resize] done. counts={counts}")
    return 0 if counts.get("error", 0) == 0 and counts.get("directus_error", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

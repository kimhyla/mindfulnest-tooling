#!/usr/bin/env python3
"""Seed shared baseline image library from Kim's canonical manifest (SHARED_BASELINE_IMAGE_LIBRARY_V1)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLING_ROOT = HERE.parent.parent
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

from Production.lib.paths import DROPBOX_ROOT  # noqa: E402
from Production.lib.event_library import (  # noqa: E402
    baseline_images_dir,
    baseline_registry_path,
)

DEFAULT_MANIFEST = (
    TOOLING_ROOT / "Production" / "assets" / "image_library" / "kim_canonical_manifest_v2.json"
)
DEFAULT_ASSETS = Path.home() / ".cursor/projects/Users-kimberlysmith-Projects-MindfulNest/assets"


def _load_manifest(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _resolve_assets_dir(manifest: dict, override: Path | None) -> Path:
    if override is not None:
        return override.expanduser()
    rel = manifest.get("source_assets_dir")
    if rel:
        candidate = (DEFAULT_MANIFEST.parent / rel).resolve()
        if candidate.is_dir():
            return candidate
    if DEFAULT_ASSETS.is_dir():
        return DEFAULT_ASSETS
    raise FileNotFoundError(
        f"assets dir not found — pass --assets-dir (tried manifest relative + {DEFAULT_ASSETS})"
    )


def _wipe_baseline_dir(dest_dir: Path, dry_run: bool) -> int:
    removed = 0
    if not dest_dir.is_dir():
        return 0
    for fp in dest_dir.iterdir():
        if not fp.is_file():
            continue
        if fp.name.startswith("."):
            continue
        print(f"[remove] {fp}")
        if not dry_run:
            fp.unlink()
        removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--assets-dir", type=Path, default=None)
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser()
    if not manifest_path.is_file():
        print(f"[error] missing manifest: {manifest_path}", file=sys.stderr)
        return 1

    manifest = _load_manifest(manifest_path)
    assets_dir = _resolve_assets_dir(manifest, args.assets_dir)
    prod = DROPBOX_ROOT / "Production"
    dest_dir = baseline_images_dir(prod)

    removed = _wipe_baseline_dir(dest_dir, args.dry_run)
    registry_images: list[dict] = []
    installed = 0

    for entry in manifest.get("images") or []:
        src_name = entry.get("source_file")
        dest_name = entry.get("filename")
        key = entry.get("key")
        if not src_name or not dest_name or not key:
            print(f"[error] invalid manifest entry: {entry}", file=sys.stderr)
            return 1
        src = assets_dir / src_name
        dest = dest_dir / dest_name
        if not src.is_file():
            print(f"[error] missing source asset: {src}", file=sys.stderr)
            return 1
        print(f"[baseline] {src_name} -> {dest}")
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        installed += 1
        registry_images.append({
            "key": key,
            "filename": dest_name,
            "display_name": entry.get("display_name") or key,
            "tags": entry.get("tags") or ["baseline", "shared"],
            "source_note": f"Kim canonical upload v2 — {src_name}",
        })

    registry = {
        "version": manifest.get("version", 2),
        "id": manifest.get("id", "kim_canonical_upload_v2"),
        "apply_to_all_events": manifest.get("apply_to_all_events", True),
        "images": registry_images,
    }

    reg_tooling = TOOLING_ROOT / "Production" / "baseline_image_registry.json"
    reg_dropbox = baseline_registry_path(prod)
    print(f"[registry] {reg_tooling}")
    print(f"[registry] {reg_dropbox}")
    if not args.dry_run:
        for reg_path in (reg_tooling, reg_dropbox):
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            reg_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "dry_run": args.dry_run,
        "removed_old": removed,
        "installed": installed,
        "baseline_dir": str(dest_dir),
        "assets_dir": str(assets_dir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Remove Element-byte-contaminated library sources (legacy heal overwrite artifacts)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLING_ROOT = HERE.parent.parent
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

from Production.lib.paths import DROPBOX_ROOT  # noqa: E402

CONTAMINATED_FILENAMES = (
    "ChatGPT Image Jun 3, 2026, 04_49_48 PM (3).png",
    "ChatGPT Image Jun 14, 2026, 04_36_22 AM.png",
    "ChatGPT Image Jun 2, 2026, 12_50_43 PM.png",
    "ChatGPT Image Jun 25, 2026, 03_05_40 PM (1).png",
    "ChatGPT Image Jun 3, 2026, 12_03_16 PM (1).png",
    "40edc382-c44c-4a0b-a9bc-6a6147e60ad3.png",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _element_pose_hashes(prod: Path) -> set[str]:
    hashes: set[str] = set()
    for child in prod.iterdir():
        if not child.is_dir():
            continue
        poses = child / "poses"
        if not poses.is_dir():
            continue
        for fp in poses.glob("*"):
            if fp.is_file():
                hashes.add(_sha256(fp))
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    prod = DROPBOX_ROOT / "Production"
    element_hashes = _element_pose_hashes(prod)
    deleted: list[str] = []

    for ev_dir in sorted(prod.glob("Event_*")):
        if not ev_dir.is_dir():
            continue
        src_dir = ev_dir / "library" / "images" / "sources"
        if not src_dir.is_dir():
            continue
        for fname in CONTAMINATED_FILENAMES:
            fp = src_dir / fname
            if not fp.is_file():
                continue
            digest = _sha256(fp)
            if digest not in element_hashes:
                print(f"[skip] {fp} — hash does not match Element pose (manual review)")
                continue
            print(f"[delete] {fp}")
            if not args.dry_run:
                fp.unlink()
            deleted.append(str(fp))

    print(json.dumps({"ok": True, "dry_run": args.dry_run, "deleted": deleted}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

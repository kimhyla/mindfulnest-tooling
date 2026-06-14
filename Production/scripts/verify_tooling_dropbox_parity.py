#!/usr/bin/env python3
"""LD-O3-DUAL-ROOT-PARITY-V1 — fail if tooling and Dropbox critical files diverge.

Usage:
  python3 Production/scripts/verify_tooling_dropbox_parity.py
  MN_TOOLING_ROOT=... MN_DROPBOX_ROOT=... python3 Production/scripts/verify_tooling_dropbox_parity.py
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

CRITICAL_REL_PATHS: tuple[str, ...] = (
    "Production/tools/beat_generator.py",
    "Production/tools/kling_o3_prompt.py",
    "Production/tools/kling_character_registry.py",
    "Production/tools/production_server.py",
    "Production/tools/kling_o3_element_beat_pipeline.py",
    "Production/tools/arlo_o3_voice_pipeline.py",
    "Production/tools/server_handlers/background.py",
    "Production/tools/server_handlers/kling_o3.py",
    "Production/tools/kling_o3_job_store.py",
    "Production/tools/teleport_intro_kit.py",
    "Production/tools/teleport_intro_canonical.py",
    "Production/tools/credentials_lib/ffmpeg_stitch.py",
    "Production/tools/server_handlers/stitch_editor.py",
    "Production/scripts/verify_tooling_dropbox_parity.py",
    "Production/scripts/verify_o3_intro_contract.sh",
    "Production/scripts/post_tooling_change_smoke.sh",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    tooling = Path(
        os.environ.get(
            "MN_TOOLING_ROOT",
            "/Users/kimberlysmith/Projects/mindfulnest-tooling",
        )
    )
    dropbox = Path(
        os.environ.get(
            "MN_DROPBOX_ROOT",
            "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files",
        )
    )
    mismatches: list[str] = []
    missing: list[str] = []
    verified = 0
    for rel in CRITICAL_REL_PATHS:
        src = tooling / rel
        dst = dropbox / rel
        if not src.is_file():
            missing.append(f"missing tooling: {rel}")
            continue
        if not dst.is_file():
            missing.append(f"missing dropbox: {rel}")
            continue
        src_sha = _sha256(src)
        dst_sha = _sha256(dst)
        if src_sha != dst_sha:
            mismatches.append(f"{rel}\n  tooling: {src_sha}\n  dropbox: {dst_sha}")
        else:
            verified += 1
            print(f"OK  {rel}  {src_sha[:12]}…")
    if missing:
        print("\nMISSING:", file=sys.stderr)
        for line in missing:
            print(f"  {line}", file=sys.stderr)
    if mismatches:
        print("\nSHA256 MISMATCH (tooling ≠ Dropbox):", file=sys.stderr)
        for block in mismatches:
            print(f"  {block}", file=sys.stderr)
        print(
            "\nFix: bash Production/scripts/deploy_storyboard_v59.sh "
            "(or rsync tooling → Dropbox for the listed paths).",
            file=sys.stderr,
        )
        return 1
    if missing:
        return 1
    print(f"\nparity ok — {verified} critical file(s) match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

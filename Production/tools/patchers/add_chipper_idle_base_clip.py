#!/usr/bin/env python3
"""Path B JS-only patch: add Chipper idle-on-empty-desk to the
BASE_CLIPS_LIBRARY dropdown in the production storyboard HTML, and
copy the source mp4 into Production/assets/lipsync_bases/ so the
lipsync endpoint can resolve it.

Run: python3 add_chipper_idle_base_clip.py [--dry-run]
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent.parent  # Production/
SRC_MP4 = PROD / "Event_1" / "phase_a_closeup_idle_v2_20260420T230615Z.mp4"
BASES_DIR = PROD / "assets" / "lipsync_bases"
CLIP_ID = "chipper_idle_on_empty_desk_v2"
DEST_MP4 = BASES_DIR / f"{CLIP_ID}.mp4"

HTML = PROD / "Event_1" / "storyboard_v38_prod.html"

OLD = 'var BASE_CLIPS_LIBRARY = ["placeholder_cedric_base_v1"];'
NEW = f'var BASE_CLIPS_LIBRARY = ["placeholder_cedric_base_v1", "{CLIP_ID}"];'

def main() -> int:
    dry = "--dry-run" in sys.argv
    if not SRC_MP4.is_file():
        print(f"FAIL: source mp4 missing: {SRC_MP4}")
        return 1
    if not HTML.is_file():
        print(f"FAIL: storyboard html missing: {HTML}")
        return 1

    html_text = HTML.read_text()
    if NEW.split("[")[1].split("]")[0] in html_text and CLIP_ID in html_text:
        print(f"SKIP: dropdown already contains {CLIP_ID}")
        html_patched = html_text
    else:
        count = html_text.count(OLD)
        if count != 1:
            print(f"FAIL: expected 1 occurrence of BASE_CLIPS_LIBRARY line, found {count}")
            return 1
        html_patched = html_text.replace(OLD, NEW)

    print(f"[plan] copy {SRC_MP4.name} -> {DEST_MP4}")
    print(f"[plan] patch dropdown in {HTML.name}: add '{CLIP_ID}'")

    if dry:
        print("DRY RUN — no changes written")
        return 0

    BASES_DIR.mkdir(parents=True, exist_ok=True)
    if DEST_MP4.exists():
        print(f"[copy] already exists, overwriting: {DEST_MP4}")
    shutil.copy2(SRC_MP4, DEST_MP4)
    print(f"[copy] ok ({DEST_MP4.stat().st_size:,} bytes)")

    if html_patched != html_text:
        bak = HTML.with_suffix(HTML.suffix + ".bak_base_clips_lib")
        shutil.copy2(HTML, bak)
        HTML.write_text(html_patched)
        print(f"[patch] ok (backup: {bak.name})")
    else:
        print("[patch] no-op")

    # Verify the new clip ID appears exactly where expected
    verify = HTML.read_text()
    if CLIP_ID not in verify:
        print("FAIL: post-patch verification did not find clip id")
        return 1
    print("OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())

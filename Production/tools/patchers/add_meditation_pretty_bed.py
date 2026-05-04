#!/usr/bin/env python3
"""Register 'ambient bed pretty option2.mp3' into the production ambient
library as meditation_pretty_v1 and add it to the AMBIENT_LIBRARY
dropdown in storyboard_v38_prod.html. Path B JS-only patch.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent.parent  # Production/
PROJ = PROD.parent
SRC = PROJ / "Claude ElevenLabs Phase B Module Sounds" / "ambient bed pretty option2.mp3"
LIB_DIR = PROD / "assets" / "ambient_library"
KEY = "meditation_pretty_v1"
DEST = LIB_DIR / f"{KEY}.mp3"

HTML = PROD / "Event_1" / "storyboard_v38_prod.html"
OLD = 'var AMBIENT_LIBRARY = ["ambient_silent_60s", "meditation_fireplace_v1"];'
NEW = f'var AMBIENT_LIBRARY = ["ambient_silent_60s", "meditation_fireplace_v1", "{KEY}"];'


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not SRC.is_file():
        print(f"FAIL: source missing: {SRC}")
        return 1
    if not HTML.is_file():
        print(f"FAIL: storyboard html missing: {HTML}")
        return 1

    html = HTML.read_text()
    if KEY in html:
        print(f"SKIP: {KEY} already in library")
        patched = html
    else:
        n = html.count(OLD)
        if n != 1:
            print(f"FAIL: expected 1 AMBIENT_LIBRARY line, found {n}")
            return 1
        patched = html.replace(OLD, NEW)

    print(f"[plan] copy {SRC.name} -> {DEST}")
    print(f"[plan] add '{KEY}' to AMBIENT_LIBRARY in {HTML.name}")
    if dry:
        print("DRY RUN"); return 0

    LIB_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DEST)
    print(f"[copy] ok ({DEST.stat().st_size:,} bytes)")

    if patched != html:
        bak = HTML.with_suffix(HTML.suffix + ".bak_ambient_pretty")
        shutil.copy2(HTML, bak)
        HTML.write_text(patched)
        print(f"[patch] ok (backup: {bak.name})")
    else:
        print("[patch] no-op")

    if KEY not in HTML.read_text():
        print("FAIL: verification — key not in file")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

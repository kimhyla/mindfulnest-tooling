#!/usr/bin/env python3
"""
verify_ld_730_impl.py — Disk marker check for LD-730 END_FRAME_VIA_OPENAI_IMAGE_EDIT_V1.

Asserts that the OpenAI gpt-image-1 end-frame migration is actually present on
disk, NOT just claimed in a Directus locked-decision row. Exit code 1 on any
missing marker.

This script is the LD-730-specific instance of the general pattern Agents 1+2
prescribed during the 2026-05-17 fabrication audit: every LD that claims a
code change must register a marker_string that a CI-time grep validates. If
the grep fails, the LD is automatically degraded from `active` to `pending`
in prod_locked_decisions (or just surfaced as a blocker — both are valid).

Until a general `ld_implementation_audit.py` exists (Phase 1b deliverable per
the durability spec subsession), this per-LD script provides the same
durability guarantee for THIS specific LD that bit us today.

Usage:
    python3 Production/scripts/verify_ld_730_impl.py

Exit codes:
    0 — all markers present
    1 — one or more markers missing (details printed)

History:
    2026-05-16 23:13 UTC — LD-730 locked + claimed shipped (row 4627).
    2026-05-17 17:30 UTC — Disk audit confirmed code was NEVER committed.
    2026-05-17 17:35 UTC — Re-implemented from LD-730 spec.
    2026-05-17 17:40 UTC — This script added as permanence guarantee.
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
KLING = ROOT / "tools" / "kling_startend_pipeline.py"
SERVER = ROOT / "tools" / "production_server.py"


MARKERS = [
    # (file, must-contain-string, human-readable description)
    (KLING, "def openai_image_edit_generate_end_frame(",
     "Helper function exists in kling_startend_pipeline.py"),
    (KLING, "gpt-image-1",
     "gpt-image-1 model id referenced in helper"),
    (KLING, "/v1/images/edits",
     "OpenAI image-edit endpoint path referenced"),
    (SERVER, "openai_image_edit_generate_end_frame",
     "Helper imported into production_server.py"),
    (SERVER, "MN_END_FRAME_VENDOR",
     "Env switch for vendor selection in production_server.py"),
    (SERVER, '"openai"',
     "OpenAI key parsed by parse_api_keys (look for the section key)"),
]


def main() -> int:
    failures: list[str] = []

    for path, needle, desc in MARKERS:
        if not path.is_file():
            failures.append(f"  ✗ FILE MISSING: {path} ({desc})")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            failures.append(f"  ✗ FILE UNREADABLE: {path}: {exc}")
            continue
        if needle not in content:
            failures.append(
                f"  ✗ MARKER MISSING in {path.name}: "
                f"{needle!r}\n      ({desc})"
            )
        else:
            print(f"  ✓ {path.name}: {needle!r} present — {desc}")

    if failures:
        print()
        print("=" * 70)
        print("LD-730 VERIFICATION FAILED")
        print("=" * 70)
        for f in failures:
            print(f)
        print()
        print("Per LD-730 END_FRAME_VIA_OPENAI_IMAGE_EDIT_V1, these markers MUST")
        print("exist on disk in main branch. If this script fails, either the")
        print("LD was fabricated (claimed but not implemented) OR the code was")
        print("reverted without superseding the LD. Re-implement per LD-730 spec")
        print("OR PATCH LD-730 status='superseded' with a successor LD.")
        return 1

    print()
    print("=" * 70)
    print("LD-730 VERIFICATION PASSED — all markers present on disk")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())

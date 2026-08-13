#!/usr/bin/env python3
"""Multipass static verification for stitcher canonical job + overlay export lock-ins."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "Production" / "tools"))

CHECKS: list[tuple[str, Path, str]] = [
    (
        "stitch_upsert_event_slot defined",
        _REPO / "Production/tools/server_handlers/stitch_editor.py",
        "def stitch_upsert_event_slot",
    ),
    (
        "legacy migration defined",
        _REPO / "Production/tools/server_handlers/stitch_editor.py",
        "def stitch_migrate_legacy_to_canonical",
    ),
    (
        "merge_slots support",
        _REPO / "Production/tools/server_handlers/stitch_editor.py",
        "merge_slots",
    ),
    (
        "scene_assemble uses canonical upsert",
        _REPO / "Production/tools/production_server.py",
        "stitch_upsert_event_slot",
    ),
    (
        "phase export handler",
        _REPO / "Production/tools/server_handlers/phases.py",
        "def handle_phase_export_stitcher",
    ),
    (
        "overlay ensure helper",
        _REPO / "Production/tools/server_handlers/phases.py",
        "def _phase_ensure_overlay_mp4",
    ),
    (
        "export route registered",
        _REPO / "Production/tools/production_server.py",
        "/api/phase/export_stitcher",
    ),
    (
        "client export endpoint",
        _REPO / "Production/tools/storyboard-v2/src/api/endpoints.ts",
        "phase_export_stitcher",
    ),
    (
        "PhaseProducer uses server export",
        _REPO / "Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx",
        "phase_export_stitcher",
    ),
    (
        "StitcherTab canonical load",
        _REPO / "Production/tools/storyboard-v2/src/components/StitcherTab.tsx",
        "canonicalName",
    ),
    (
        "StitcherTab merge_slots save",
        _REPO / "Production/tools/storyboard-v2/src/components/StitcherTab.tsx",
        "merge_slots: true",
    ),
    (
        "unit tests present",
        _REPO / "Production/tools/tests/test_stitch_canonical_job.py",
        "test_upsert_does_not_drop_other_slots",
    ),
    (
        "playback bake durable Dropbox commit",
        _REPO / "Production/tools/server_handlers/stitch_slot_playback.py",
        "STITCH_PLAYBACK_BAKE_LOCAL_COMMIT_V1",
    ),
    (
        "playback bake uses copy_file_durable",
        _REPO / "Production/tools/server_handlers/stitch_slot_playback.py",
        "copy_file_durable",
    ),
]

FAIL = 0
for label, path, needle in CHECKS:
    if not path.is_file():
        print(f"FAIL {label}: missing file {path}")
        FAIL += 1
        continue
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        print(f"FAIL {label}: '{needle}' not found in {path.relative_to(_REPO)}")
        FAIL += 1
    else:
        print(f"OK   {label}")

if FAIL:
    print(f"\n{FAIL} check(s) failed.")
    raise SystemExit(1)

print(f"\nAll {len(CHECKS)} multipass checks passed.")
raise SystemExit(0)

#!/usr/bin/env python3
"""Restore Event_1 Phase B stem + lipsync + watercolor cues after accidental amber trim."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

EVENT_DIR = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1"
)
STATE_PATH = EVENT_DIR / "production_state.json"
ORIG_STEM = "phase_b_voice_stem_20260525-180459.mp3"
ORIG_STEM_MTIME = 1779746699
ORIG_LIPSYNC = "phase_b_lipsync_20260605-132651.mp4"
ORIG_LIPSYNC_MTIME = 1780681370
ARCHIVED_LIPSYNC = (
    EVENT_DIR
    / "_rejected_lipsync"
    / "phase_b_lipsync_rejected_20260612-005240_phase_b_lipsync_20260605-132651.mp4"
)
# Canonical watercolor cues (top-level field from pre-cut state).
WATERCOLOR_CUES_JSON = (
    '[{"animation":"fade_in","cue_type":"png","duration_ms":6768,"id":"cue_hyy7jt02",'
    '"key":"spell_title","timestamp_ms":9070,"volume":1.0},'
    '{"animation":"fade_in","cue_type":"video","duration_ms":10108,"id":"cue_52h4z6ii",'
    '"key":"hands_rubbing_animated_20260528-153431","timestamp_ms":21015,"volume":1.0},'
    '{"animation":"fade_in","cue_type":"png","duration_ms":17939,"id":"cue_kw4drcwt",'
    '"key":"hands_original","timestamp_ms":34864,"volume":1.0},'
    '{"animation":"fade_in","cue_type":"png","duration_ms":12160,"id":"cue_un6zp6u4",'
    '"key":"hands_close","timestamp_ms":52701,"volume":1.0},'
    '{"animation":"fade_in","cue_type":"png","duration_ms":8616,"id":"cue_1069fn5g",'
    '"key":"hands_far","timestamp_ms":64885,"volume":1.0}]'
)


def main() -> None:
    if not STATE_PATH.is_file():
        raise SystemExit(f"missing state: {STATE_PATH}")
    if not (EVENT_DIR / ORIG_STEM).is_file():
        raise SystemExit(f"missing original stem: {ORIG_STEM}")
    if not ARCHIVED_LIPSYNC.is_file():
        raise SystemExit(f"missing archived lipsync: {ARCHIVED_LIPSYNC}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = EVENT_DIR / ".backups" / f"phase_b_pre_cut_restore_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATE_PATH, backup_dir / "production_state.json.before")

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    (backup_dir / "production_state.json.parsed.before.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    state["phase_b_voice_stem_file"] = ORIG_STEM
    state["phase_b_voice_stem_mtime"] = ORIG_STEM_MTIME
    state["phase_b_voice_stem"] = ORIG_STEM
    state["phase_b_lipsync_file"] = ORIG_LIPSYNC
    state["phase_b_lipsync_mtime"] = ORIG_LIPSYNC_MTIME
    state["phase_b_lipsync_status"] = "done"
    state["phase_b_lipsync_requires_regen"] = False
    state["phase_b_watercolor_cues_json"] = WATERCOLOR_CUES_JSON

    for key in list(state.keys()):
        if key.startswith("phase_b_voice_stem_trim_") or key.startswith(
            "phase_b_voice_stem_cut_",
        ):
            state.pop(key, None)

    nested = state.setdefault("phase_b", {})
    if isinstance(nested, dict):
        nested["phase_b_watercolor_cues_json"] = WATERCOLOR_CUES_JSON
        nested["phase_b_lipsync_requires_regen"] = False
        nested["phase_b_lipsync_file"] = ORIG_LIPSYNC
        nested["phase_b_lipsync_mtime"] = ORIG_LIPSYNC_MTIME
        nested["phase_b_lipsync_status"] = "done"

    state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1

    shutil.copy2(ARCHIVED_LIPSYNC, EVENT_DIR / ORIG_LIPSYNC)

    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (backup_dir / "production_state.json.after.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )
    print(f"OK restored Phase B → stem={ORIG_STEM} lipsync={ORIG_LIPSYNC}")
    print(f"backup: {backup_dir}")


if __name__ == "__main__":
    main()

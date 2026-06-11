#!/usr/bin/env python3
"""Deep audit for the Chipper-to-Arlo Event_1 intro migration.

This catches the specific class of error where non-target beats (Tessa) appear
visually restored but lose their real approved video state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROD = Path(__file__).resolve().parent.parent
BACKUP = PROD / "Event_1" / "_arlo_migration_backups" / "20260610T050627Z" / "beat_generator_state.json"
SIDE = PROD / "beat_generator_state.json"
EVENT_STATE = PROD / "Event_1" / "production_state.json"
EVENT_HTML = PROD / "Event_1" / "storyboard_v59_prod.html"
ARLO_PIPELINE = PROD / "tools" / "arlo_o3_voice_pipeline.py"

ARLO_BEATS = {
    "bg_arc1_event1_pre_beat_01",
    "bg_arc1_event1_pre_beat_05",
    "bg_arc1_event1_pre_beat_07",
    "bg_arc1_event1_pre_beat_09",
    "bg_arc1_event1_pre_beat_10",
    "bg_arc1_event1_pre_beat_11",
}

GENERATED_ARLO_BEATS = {
    "bg_arc1_event1_pre_beat_01",
    "bg_arc1_event1_pre_beat_05",
}

FORBIDDEN_ACTIVE_TERMS = (
    "Chipper/poses",
    "master_chipper",
    "312987294498500",
    "312924252190306",
    "Guide Bird",
    "assistant bird",
    "Pip",
    "magpie",
    " beak",
    " wing",
    " wings",
    " feather",
    " feathers",
    "canonical_mirror_video",
    "templates/chipper_teleport_intro",
)


def _beats(sc: dict) -> list[dict]:
    return sc["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"]


def _strip_archive(value):
    if isinstance(value, dict):
        return {k: _strip_archive(v) for k, v in value.items() if k != "arlo_migration_archive"}
    if isinstance(value, list):
        return [_strip_archive(v) for v in value]
    return value


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    backup = json.loads(BACKUP.read_text(encoding="utf-8"))
    current = json.loads(SIDE.read_text(encoding="utf-8"))
    backup_by_id = {b["beat_id"]: b for b in _beats(backup)}
    current_by_id = {b["beat_id"]: b for b in _beats(current)}

    # Non-target intro/pre beats must match the backup exactly, except Chipper
    # beats intentionally migrated to Arlo.
    for bid, before in backup_by_id.items():
        if bid in ARLO_BEATS:
            continue
        after = current_by_id.get(bid)
        if after != before:
            failures.append(f"non-target beat drifted from backup: {bid}")
    checks.append("non-target intro/pre beats exact-match backup")

    # Target Arlo beats are either still staged for regeneration or, once run
    # through the Arlo O3 path, approved with a real MP4 on disk.
    for bid in sorted(ARLO_BEATS):
        beat = current_by_id.get(bid)
        if not beat:
            failures.append(f"missing Arlo beat: {bid}")
            continue
        if beat.get("speaker") != "Arlo":
            failures.append(f"{bid}: speaker={beat.get('speaker')!r}, expected Arlo")
        if bid in GENERATED_ARLO_BEATS:
            if beat.get("status") != "approved":
                failures.append(f"{bid}: status={beat.get('status')!r}, expected approved")
            if beat.get("kling_o3_status") != "approved":
                failures.append(f"{bid}: kling_o3_status={beat.get('kling_o3_status')!r}, expected approved")
            path = Path(beat.get("kling_o3_video_path") or "")
            if not path.is_file():
                failures.append(f"{bid}: generated Arlo video missing on disk: {path}")
            if not beat.get("kling_o3_task_id"):
                failures.append(f"{bid}: missing Arlo O3 task id")
            if beat.get("kling_o3_voice_fix_voice_id") != "7o9pyvsN0ob5GO6LBQp6":
                failures.append(f"{bid}: missing Chipper ElevenLabs voice id metadata")
            if "_sharp" not in path.stem:
                failures.append(f"{bid}: expected sharpened active Arlo video")
        else:
            if beat.get("status") != "arlo_needs_regen":
                failures.append(f"{bid}: status={beat.get('status')!r}, expected arlo_needs_regen")
            if beat.get("kling_o3_status") != "not_submitted":
                failures.append(f"{bid}: kling_o3_status={beat.get('kling_o3_status')!r}, expected not_submitted")
            for key in ("kling_o3_video_path", "accepted_video_path", "kling_o3_task_id"):
                if beat.get(key):
                    failures.append(f"{bid}: stale {key} still active")
        text = json.dumps(_strip_archive(beat), ensure_ascii=False)
        for term in FORBIDDEN_ACTIVE_TERMS:
            if term in text:
                failures.append(f"{bid}: active Arlo beat contains {term!r}")
    checks.append("Arlo beats staged or generated through O3 as expected")

    # Tessa approved O3 videos must exist exactly as they existed in backup.
    for bid, before in backup_by_id.items():
        if before.get("speaker") != "Tessa":
            continue
        after = current_by_id.get(bid) or {}
        if after != before:
            failures.append(f"Tessa beat not exact restored: {bid}")
        path = Path(before.get("kling_o3_video_path") or "")
        if not path.is_file():
            failures.append(f"Tessa approved video missing on disk: {bid}: {path}")
    checks.append("Tessa approved O3 videos exist and match backup")

    state = json.loads(EVENT_STATE.read_text(encoding="utf-8"))
    resolution = ((state.get("videos") or {}).get("resolution") or {})
    beat3 = ((resolution.get("beats") or {}).get("beat_03") or {})
    if (beat3.get("speaker") or (beat3.get("phase_1") or {}).get("speaker")) != "Arlo":
        failures.append("resolution beat_03 not migrated to Arlo")
    if beat3.get("audio_file"):
        failures.append("resolution beat_03 still has old Chipper audio_file")
    checks.append("resolution active Chipper beat staged for Arlo regeneration")

    html = EVENT_HTML.read_text(encoding="utf-8", errors="ignore")
    if '"Cedric","Chipper","Tessa"' in html:
        failures.append("deployed Event_1 HTML still exposes old Chipper speaker roster")
    if '"Cedric","Arlo","Tessa"' not in html:
        failures.append("deployed Event_1 HTML missing Arlo speaker roster")
    if "submit-arlo-o3-voice" not in html or "poll-arlo-o3-voice-status" not in html:
        failures.append("deployed Event_1 HTML missing durable Arlo O3 endpoint wiring")
    if not ARLO_PIPELINE.is_file():
        failures.append("durable Arlo O3 voice pipeline script missing")
    checks.append("deployed Event_1 HTML speaker roster patched")

    result = {"ok": not failures, "checks": checks, "failures": failures}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

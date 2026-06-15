#!/usr/bin/env python3
"""Audit active Arlo migration state for stale Chipper/bird references."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

PROD = Path(__file__).resolve().parent.parent
EVENT = PROD / "Event_1"
ARLO_PIPELINE = PROD / "tools" / "arlo_o3_voice_pipeline.py"
GENERATED_ARLO_BEATS = {
    "bg_arc1_event1_pre_beat_01",
    "bg_arc1_event1_pre_beat_05",
}
OLD_ELEMENT_IDS = {"312987294498500", "312924252190306"}
FORBIDDEN_ACTIVE = (
    "Chipper/poses",
    "master_chipper",
    "Guide Bird",
    "assistant bird",
    "Pip",
    "magpie",
    " beak",
    " beaks",
    " wing",
    " wings",
    " feather",
    " feathers",
    "Exactly one bird",
    "canonical_mirror_video",
    "canonical_intro_tail",
    "templates/chipper_teleport_intro",
)


def _strip_archives(value):
    if isinstance(value, dict):
        return {
            k: _strip_archives(v)
            for k, v in value.items()
            if k not in {"arlo_migration_archive", "arlo_migration_pruned_overrides"}
        }
    if isinstance(value, list):
        return [_strip_archives(v) for v in value]
    return value


def _contains_forbidden(label: str, value, failures: list[str]) -> None:
    text = json.dumps(_strip_archives(value), ensure_ascii=False)
    for term in FORBIDDEN_ACTIVE:
        if term in text:
            failures.append(f"{label}: contains {term!r}")
    for eid in OLD_ELEMENT_IDS:
        if eid in text:
            failures.append(f"{label}: contains old Chipper element_id {eid}")


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    subjects = json.loads((PROD / "character_subjects.json").read_text(encoding="utf-8"))
    arlo = (subjects.get("characters") or {}).get("Arlo")
    if not arlo:
        failures.append("character_subjects: missing Arlo")
    else:
        checks.append(f"Arlo element_id={arlo.get('element_id')}")
        if arlo.get("status") != "active":
            failures.append(f"character_subjects: Arlo status={arlo.get('status')!r}, expected active")
        if not arlo.get("element_id"):
            failures.append("character_subjects: Arlo element_id missing")
        if str(arlo.get("element_id")) in OLD_ELEMENT_IDS:
            failures.append("character_subjects: Arlo reuses old Chipper element_id")
        _contains_forbidden("character_subjects.Arlo", arlo, failures)

    for rel in [
        "Arlo/poses/arlo_canonical_neutral_vest.png",
        "Arlo/poses/arlo_happy_vest.png",
        "Arlo/poses/arlo_confident_vest.png",
        "Arlo/poses/arlo_wizard_room_empty_background.png",
    ]:
        if not (PROD / rel).is_file():
            failures.append(f"asset missing: {rel}")

    sidecar = json.loads((PROD / "beat_generator_state.json").read_text(encoding="utf-8"))
    pre = (((sidecar.get("arcs") or {}).get("arc_1") or {}).get("segments") or {}).get("event_1_pre") or {}
    pre_beats = pre.get("beats") or []
    arlo_pre = [b for b in pre_beats if b.get("speaker") == "Arlo"]
    chipper_pre = [b.get("beat_id") for b in pre_beats if b.get("speaker") == "Chipper"]
    checks.append(f"intro/pre Arlo beats={len(arlo_pre)}")
    if chipper_pre:
        failures.append(f"intro/pre still has Chipper speaker beats: {chipper_pre}")
    for beat in arlo_pre:
        label = f"beat_generator_state.event_1_pre.{beat.get('beat_id')}"
        _contains_forbidden(label, beat, failures)
        if beat.get("beat_id") in GENERATED_ARLO_BEATS:
            video_path = Path(beat.get("kling_o3_video_path") or "")
            if beat.get("kling_o3_status") != "approved" or not video_path.is_file():
                failures.append(f"{label}: expected approved Arlo O3 video on disk")
            if beat.get("kling_o3_voice_fix_voice_id") != "7o9pyvsN0ob5GO6LBQp6":
                failures.append(f"{label}: missing Chipper ElevenLabs voice id metadata")
            if "_sharp" not in video_path.stem:
                failures.append(f"{label}: expected sharpened active Arlo video")
        else:
            if beat.get("accepted_video_path") or beat.get("kling_o3_video_path"):
                failures.append(f"{label}: old generated video path still active")
            if beat.get("kling_o3_status") != "not_submitted":
                failures.append(f"{label}: expected kling_o3_status=not_submitted")

    state = json.loads((EVENT / "production_state.json").read_text(encoding="utf-8"))
    for role in ("intro", "resolution"):
        part = ((state.get("videos") or {}).get(role) or {})
        _contains_forbidden(f"production_state.videos.{role}", part, failures)
        for bid, beat in (part.get("beats") or {}).items():
            speaker = beat.get("speaker") or (beat.get("phase_1") or {}).get("speaker")
            if speaker == "Chipper":
                failures.append(f"production_state.videos.{role}.{bid}: speaker still Chipper")

    if not ARLO_PIPELINE.is_file():
        failures.append("durable Arlo O3 voice pipeline script missing")
    html = (EVENT / "storyboard_v59_prod.html").read_text(encoding="utf-8", errors="ignore")
    if "submit-arlo-o3-voice" not in html or "poll-arlo-o3-voice-status" not in html:
        failures.append("deployed Storyboard missing durable Arlo O3 endpoint wiring")

    result = {
        "ok": not failures,
        "checks": checks,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

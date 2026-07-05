"""Production map next-options and creation validation helpers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.production_event_map import (
    all_arc_numbers,
    iter_module_slots,
    iter_slots,
    slot_by_m_number,
    slot_by_suggested_milestone_id,
    suggested_event_folder_id,
)

# Legacy on-disk folder names → production_event_map suggested_milestone_id.
_MILESTONE_DISK_ALIASES: dict[str, str] = {
    "milestone1_arc1": "oliver_meet",
}

_DEV_MILESTONE_RE = re.compile(
    r"^(test_|e2e_|valid_test|verify_test|e\d+test|.*test[a-f0-9]{6,}$)",
    re.I,
)


def _is_dev_milestone_id(milestone_id: str) -> bool:
    mid = str(milestone_id or "").strip()
    if not mid:
        return True
    if _DEV_MILESTONE_RE.match(mid):
        return True
    if mid.startswith("e") and "test" in mid.lower():
        return True
    return False


def _is_tbd(value: str | None) -> bool:
    raw = str(value or "").strip()
    if not raw or raw.upper() == "TBD":
        return True
    if raw.endswith("— TBD") or raw.endswith("- TBD"):
        return True
    return False


def _load_milestone_skeleton_refs(milestones_root: Path) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    if not milestones_root.is_dir():
        return refs
    for d in milestones_root.iterdir():
        if not d.is_dir():
            continue
        state_path = d / "state.json"
        if not state_path.is_file():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        skel = state.get("skeleton_ref") or {}
        refs[d.name.lower()] = {
            "milestone_id": d.name,
            "skeleton_ref": skel,
            "label": state.get("milestone_label"),
        }
    return refs


def _milestone_slot_created(
    slot: dict[str, Any],
    milestone_refs: dict[str, dict[str, Any]],
) -> bool:
    suggested = str(slot.get("suggested_milestone_id") or "").strip().lower()
    if suggested and suggested in milestone_refs:
        return True
    # Fallback: any milestone folder whose skeleton_ref event_id matches label slug
    event_id = str(slot.get("label") or "").strip().lower()
    for ref in milestone_refs.values():
        skel = ref.get("skeleton_ref") or {}
        if str(skel.get("event_id") or "").strip().lower() == event_id:
            return True
    return False


def _module_slot_created(
    arc_number: int,
    slot: dict[str, Any],
    *,
    production_root: Path,
    prod_modules_by_m: dict[int, dict],
    event_folders: set[str],
    bg_module=None,
) -> bool:
    m_number = int(slot["m_number"])
    pm = prod_modules_by_m.get(m_number) or {}
    if not _is_tbd(pm.get("creature_name")) and not _is_tbd(pm.get("spell_name")):
        return True

    from lib.module_event_id import resolve_m_number_from_production_folder

    for folder_name in event_folders:
        resolved = resolve_m_number_from_production_folder(folder_name, bg_module=bg_module)
        if resolved and resolved[2] == m_number:
            return True

    expected_folder = suggested_event_folder_id(arc_number, m_number)
    if expected_folder and (production_root / expected_folder).is_dir():
        return True
    return False


def compute_next_options(
    *,
    production_root: Path,
    prod_modules: list[dict] | None,
    arc_filter: int | None = None,
    bg_module=None,
) -> dict[str, Any]:
    """Return expected-but-not-yet-created slots per arc."""
    prod_modules_by_m = {
        int(r["m_number"]): r for r in (prod_modules or []) if r.get("m_number") is not None
    }
    event_folders = {
        p.name
        for p in production_root.iterdir()
        if p.is_dir() and p.name.lower().startswith("event_")
    }
    milestones_root = production_root / "Milestones"
    milestone_refs = _load_milestone_skeleton_refs(milestones_root)

    options: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    for arc_number, slot in iter_slots(arc_number=arc_filter):
        kind = str(slot.get("kind") or "")
        if kind == "module":
            created = _module_slot_created(
                arc_number,
                slot,
                production_root=production_root,
                prod_modules_by_m=prod_modules_by_m,
                event_folders=event_folders,
                bg_module=bg_module,
            )
            if created:
                continue
            m_number = int(slot["m_number"])
            suggested_id = suggested_event_folder_id(arc_number, m_number)
            options.append(
                {
                    "kind": "module",
                    "arc_number": arc_number,
                    "m_number": m_number,
                    "label": slot.get("label") or f"M{m_number}",
                    "suggested_id": suggested_id,
                    "creature": slot.get("creature"),
                    "spell_name": slot.get("spell_name"),
                    "confidence": slot.get("confidence", "confirmed"),
                }
            )
        elif kind == "milestone":
            if _milestone_slot_created(slot, milestone_refs):
                continue
            suggested_id = slot.get("suggested_milestone_id")
            options.append(
                {
                    "kind": "milestone",
                    "arc_number": arc_number,
                    "label": slot.get("label") or suggested_id,
                    "suggested_id": suggested_id,
                    "creature": slot.get("creature"),
                    "confidence": slot.get("confidence", "confirmed"),
                }
            )

    # Drift detection: on-disk Event folders that resolve to unexpected m_numbers
    from lib.module_event_id import resolve_m_number_from_production_folder

    for folder_name in sorted(event_folders):
        if folder_name.lower() in ("event_0",):
            continue
        resolved = resolve_m_number_from_production_folder(folder_name, bg_module=bg_module)
        if not resolved:
            continue
        arc, _play, m_num = resolved
        expected = slot_by_m_number(m_num)
        if expected is None:
            anomalies.append(
                {
                    "type": "unknown_m_number_on_disk",
                    "event_folder": folder_name,
                    "m_number": m_num,
                    "arc_number": arc,
                }
            )

    return {"ok": True, "options": options, "anomalies": anomalies}


def match_expected_module_create(
    event_id: str,
    *,
    bg_module=None,
) -> tuple[int, dict[str, Any]] | None:
    """Return (arc, slot) when event_id matches the next expected module folder."""
    from lib.module_event_id import is_numbered_event_folder_id, resolve_m_number_from_production_folder

    eid = str(event_id or "").strip()
    if not is_numbered_event_folder_id(eid):
        return None
    resolved = resolve_m_number_from_production_folder(eid, bg_module=bg_module)
    if not resolved:
        return None
    _arc, _play, m_number = resolved
    hit = slot_by_m_number(m_number)
    if not hit:
        return None
    arc, slot = hit
    expected_folder = suggested_event_folder_id(arc, m_number)
    if expected_folder and expected_folder.lower() != eid.lower():
        return None
    return arc, slot


def match_expected_milestone_create(milestone_id: str) -> tuple[int, dict[str, Any]] | None:
    return slot_by_suggested_milestone_id(milestone_id)


def validate_creation_allowed(
    *,
    kind: str,
    requested_id: str,
    unexpected: bool,
    production_root: Path,
    prod_modules: list[dict] | None,
    bg_module=None,
) -> tuple[bool, dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
    """Soft-warn validation. Returns (allowed, error_payload, matched_slot)."""
    next_data = compute_next_options(
        production_root=production_root,
        prod_modules=prod_modules,
        bg_module=bg_module,
    )
    options = next_data.get("options") or []
    rid = str(requested_id or "").strip()
    rid_lower = rid.lower()

    matched_slot: tuple[int, dict[str, Any]] | None = None
    for opt in options:
        if kind == "event" and opt.get("kind") == "module":
            suggested = str(opt.get("suggested_id") or "").strip()
            if suggested.lower() == rid_lower:
                hit = slot_by_m_number(int(opt["m_number"]))
                if hit:
                    matched_slot = hit
                break
        elif kind == "milestone" and opt.get("kind") == "milestone":
            suggested = str(opt.get("suggested_id") or "").strip()
            if suggested.lower() == rid_lower:
                hit = slot_by_suggested_milestone_id(rid)
                if hit:
                    matched_slot = hit
                break

    if matched_slot:
        return True, None, matched_slot

    if unexpected:
        return True, None, None

    return False, {
        "ok": False,
        "error_code": "UNEXPECTED_CREATION",
        "error_message": (
            "Requested ID does not match the next expected slot. "
            "Pass unexpected: true to create anyway."
        ),
        "expected_options": options[:20],
    }, None


def backfill_prod_module_from_slot(
    slot: dict[str, Any],
    *,
    arc_number: int,
    prod_modules_by_m: dict[int, dict],
    client,
) -> None:
    """PATCH (or POST) creature_name/spell_name from map data (Judgment Call 1)."""
    from lib.directus import try_post_or_queue

    m_number = int(slot["m_number"])
    creature = str(slot.get("creature") or "TBD")
    spell = str(slot.get("spell_name") or "TBD")
    technique = str(slot.get("technique_name") or "TBD")
    existing = prod_modules_by_m.get(m_number)
    if existing:
        patch = {}
        if _is_tbd(existing.get("creature_name")) and creature != "TBD":
            patch["creature_name"] = creature
        if _is_tbd(existing.get("spell_name")) and spell != "TBD":
            patch["spell_name"] = spell
        if _is_tbd(existing.get("technique_name")) and technique != "TBD":
            patch["technique_name"] = technique
        if patch:
            client.patch_item("prod_modules", existing["id"], patch)
        return

    module_index = sum(
        1
        for _a, s in iter_module_slots(arc_number=arc_number)
        if int(s.get("m_number") or 0) <= m_number
    )
    payload = {
        "m_number": m_number,
        "arc_number": arc_number,
        "module_index": module_index,
        "creature_name": creature,
        "spell_name": spell,
        "technique_name": technique,
        "video_role": "intro",
        "current_stage": "intake",
        "stage_status": "not_started",
    }
    try_post_or_queue("prod_modules", payload)


def _milestone_role_state(mdir: Path) -> tuple[str, int]:
    """Return (standalone role state, bg beat count) for a milestone folder."""
    state_path = mdir / "state.json"
    state_videos: dict = {}
    skel: dict = {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state_videos = state.get("videos") or {}
        skel = state.get("skeleton_ref") or {}
    except (OSError, json.JSONDecodeError):
        state_videos = {}

    standalone_part = state_videos.get("standalone") if isinstance(state_videos, dict) else {}
    do = standalone_part.get("display_order") if isinstance(standalone_part, dict) else None
    beats = standalone_part.get("beats") if isinstance(standalone_part, dict) else {}
    if not isinstance(standalone_part, dict):
        role_state = "absent"
    elif isinstance(do, list) and len(do) == 0:
        role_state = "empty"
    elif isinstance(do, list) and len(do) > 0:
        mp4s = list(mdir.glob("*_final.mp4")) + list(mdir.glob("standalone_*.mp4"))
        role_state = "complete" if mp4s else "in_progress"
    elif isinstance(beats, dict) and beats:
        role_state = "in_progress"
    else:
        role_state = "empty"

    bg_beats = 0
    sidecar_path = mdir / "beat_generator_sidecar.json"
    if sidecar_path.is_file():
        try:
            sc = json.loads(sidecar_path.read_text(encoding="utf-8"))
            arc = int(skel.get("arc_number") or 1)
            eid = str(skel.get("event_id") or mdir.name)
            ph = str(skel.get("phase") or "full")
            seg_key = f"event_{eid}_{ph}"
            seg_entry = (
                (sc.get("arcs") or {})
                .get(f"arc_{arc}", {})
                .get("segments", {})
                .get(seg_key, {})
            )
            bg_beats = len(seg_entry.get("beats") or [])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            bg_beats = 0
    return role_state, bg_beats


def _index_production_milestones(production_root: Path) -> tuple[dict[str, dict], list[dict]]:
    """Index on-disk milestones by planned suggested_id; return (index, dev_fixtures)."""
    from lib.milestone_store import list_milestones

    by_planned_id: dict[str, dict] = {}
    dev_fixtures: list[dict] = []
    for ms in list_milestones(production_root):
        mid = str(ms.get("milestone_id") or "")
        if _is_dev_milestone_id(mid):
            dev_fixtures.append(ms)
            continue
        keys = {mid.lower()}
        alias = _MILESTONE_DISK_ALIASES.get(mid)
        if alias:
            keys.add(alias.lower())
        skel = ms.get("skeleton_ref") or {}
        suggested = str(ms.get("suggested_milestone_id") or "").strip().lower()
        if suggested:
            keys.add(suggested)
        for key in keys:
            if key and key not in by_planned_id:
                by_planned_id[key] = ms
    return by_planned_id, dev_fixtures


def build_production_map_milestones(production_root: Path) -> tuple[list[dict], list[dict]]:
    """Planned milestone rows (Production Event Map order) + unplanned dev folders."""
    by_planned, dev_fixtures = _index_production_milestones(production_root)
    planned_rows: list[dict] = []
    matched_disk_ids: set[str] = set()

    for arc_number in all_arc_numbers():
        pos = 0
        for _arc, slot in iter_slots(arc_number=arc_number):
            pos += 1
            if slot.get("kind") != "milestone":
                continue
            suggested = str(slot.get("suggested_milestone_id") or "").strip()
            suggested_key = suggested.lower()
            disk = by_planned.get(suggested_key) if suggested_key else None

            row: dict[str, Any] = {
                "kind": "milestone",
                "planned": True,
                "arc_number": arc_number,
                "play_order": pos,
                "label": slot.get("label") or suggested,
                "suggested_milestone_id": suggested or None,
                "creature": slot.get("creature"),
                "confidence": slot.get("confidence", "confirmed"),
                "created": disk is not None,
            }

            if disk:
                mid = str(disk["milestone_id"])
                matched_disk_ids.add(mid)
                mdir = Path(disk["path"])
                role_state, bg_beats = _milestone_role_state(mdir)
                skel = disk.get("skeleton_ref") or {}
                row.update(
                    {
                        "milestone_id": mid,
                        "milestone_label": disk.get("milestone_label"),
                        "skeleton_ref": skel,
                        "path": str(mdir),
                        "scope_type": "milestone",
                        "videos_by_role": {
                            "standalone": {
                                "state": role_state,
                                "bg_beat_count": bg_beats,
                            },
                        },
                    }
                )
            else:
                row.update(
                    {
                        "milestone_id": suggested or f"arc{arc_number}_pos{pos}",
                        "milestone_label": None,
                        "skeleton_ref": {},
                        "path": None,
                        "videos_by_role": {
                            "standalone": {"state": "absent", "bg_beat_count": 0},
                        },
                    }
                )
            planned_rows.append(row)

    # On-disk production folders not matched to any planned slot (e.g. opening_storybook).
    extra_fixtures: list[dict] = []
    for ms in by_planned.values():
        mid = str(ms.get("milestone_id") or "")
        if mid in matched_disk_ids:
            continue
        mdir = Path(ms["path"])
        role_state, bg_beats = _milestone_role_state(mdir)
        extra_fixtures.append(
            {
                "kind": "milestone",
                "planned": False,
                "milestone_id": mid,
                "milestone_label": ms.get("milestone_label"),
                "skeleton_ref": ms.get("skeleton_ref") or {},
                "path": str(mdir),
                "scope_type": "milestone",
                "videos_by_role": {
                    "standalone": {"state": role_state, "bg_beat_count": bg_beats},
                },
            }
        )

    for ms in dev_fixtures:
        mdir = Path(ms["path"])
        role_state, bg_beats = _milestone_role_state(mdir)
        extra_fixtures.append(
            {
                "kind": "milestone",
                "planned": False,
                "dev_fixture": True,
                "milestone_id": ms.get("milestone_id"),
                "milestone_label": ms.get("milestone_label"),
                "skeleton_ref": ms.get("skeleton_ref") or {},
                "path": str(mdir),
                "scope_type": "milestone",
                "videos_by_role": {
                    "standalone": {"state": role_state, "bg_beat_count": bg_beats},
                },
            }
        )

    return planned_rows, extra_fixtures


def _next_module_event_folder(arc_number: int, start_pos: int) -> str | None:
    """Return Event_N folder for the next module slot in this arc (for placement hints)."""
    pos = 0
    for arc, slot in iter_slots(arc_number=arc_number):
        pos += 1
        if pos <= start_pos:
            continue
        if slot.get("kind") == "module":
            m_num = int(slot["m_number"])
            return suggested_event_folder_id(arc, m_num)
    return None


def build_module_map_row(
    production_root: Path,
    prod_module: dict[str, Any],
    slot: dict[str, Any],
    arc_number: int,
) -> dict[str, Any]:
    """Build per-module status row with correct Event_N folder from play-order index."""
    import json

    m_num = int(slot["m_number"])
    event_folder = suggested_event_folder_id(arc_number, m_num)
    edir: Path | None = None
    if event_folder:
        candidate = production_root / event_folder
        if candidate.is_dir():
            edir = candidate

    segments: dict[str, dict] = {}
    videos_by_role: dict[str, dict] = {}
    if edir:
        phase_a = list(edir.glob("phase_a_stitched_*.mp4"))
        phase_b = list(edir.glob("phase_b_lipsync_*.mp4"))
        final_concat = list(edir.glob(f"M{m_num}_*_final.mp4"))
        segments = {
            "phase_a": {
                "status": "ready" if phase_a else "missing",
                "count": len(phase_a),
                "latest": phase_a[0].name if phase_a else None,
            },
            "phase_b": {
                "status": "ready" if phase_b else "missing",
                "count": len(phase_b),
                "latest": phase_b[0].name if phase_b else None,
            },
            "final_concat": {
                "status": "ready" if final_concat else "missing",
                "count": len(final_concat),
            },
        }

        state_path = edir / "production_state.json"
        state_videos: dict = {}
        try:
            with open(state_path, encoding="utf-8") as _f:
                state_videos = (json.load(_f).get("videos") or {})
        except (FileNotFoundError, json.JSONDecodeError):
            state_videos = {}

        final_concat_present = bool(final_concat)
        for _role in ("intro", "resolution", "standalone"):
            partition = state_videos.get(_role)
            if not isinstance(partition, dict):
                videos_by_role[_role] = {"state": "absent"}
                continue
            do = partition.get("display_order")
            beats = partition.get("beats") or {}
            if isinstance(do, list):
                is_empty = len(do) == 0
            else:
                is_empty = len(beats) == 0
            if is_empty:
                videos_by_role[_role] = {"state": "empty"}
                continue
            role_dir = edir / _role
            if role_dir.is_dir():
                role_mp4s = (
                    list(role_dir.glob(f"scene_{_role}_*.mp4"))
                    + list(role_dir.glob(f"{_role}_atomic*.mp4"))
                )
            else:
                role_mp4s = (
                    list(edir.glob(f"scene_{_role}_*.mp4"))
                    + list(edir.glob(f"{_role}_atomic*.mp4"))
                )
            if role_mp4s:
                if final_concat_present:
                    videos_by_role[_role] = {
                        "state": "final",
                        "completed_mp4": role_mp4s[0].name,
                    }
                else:
                    videos_by_role[_role] = {
                        "state": "complete",
                        "completed_mp4": role_mp4s[0].name,
                    }
            else:
                videos_by_role[_role] = {"state": "in_progress"}

    creature = prod_module.get("creature_name") or slot.get("creature") or "TBD"
    return {
        "kind": "module",
        "m_number": m_num,
        "creature_name": creature,
        "video_role": prod_module.get("video_role") or "intro",
        "event_dir": event_folder,
        "event_folder_expected": event_folder,
        "segments": segments,
        "videos_by_role": videos_by_role,
    }


def build_production_map_timeline(
    production_root: Path,
    prod_modules: list[dict] | None,
) -> tuple[list[dict], list[dict]]:
    """Interleaved play-order timeline (modules + milestones + narratives) per arc."""
    by_m = {
        int(r["m_number"]): r for r in (prod_modules or []) if r.get("m_number") is not None
    }
    by_planned, dev_fixtures = _index_production_milestones(production_root)
    timeline: list[dict] = []
    last_module_event: str | None = None
    global_idx = 0

    for arc_number in all_arc_numbers():
        pos = 0
        for _arc, slot in iter_slots(arc_number=arc_number):
            pos += 1
            kind = str(slot.get("kind") or "")
            placement: dict[str, Any] = {
                "after_event": last_module_event,
                "before_event": _next_module_event_folder(arc_number, pos),
            }

            if kind == "module":
                global_idx += 1
                pm = by_m.get(int(slot["m_number"]), {})
                row = build_module_map_row(production_root, pm, slot, arc_number)
                row.update(
                    {
                        "arc_number": arc_number,
                        "play_order": pos,
                        "global_module_index": global_idx,
                        "label": slot.get("label") or f"M{slot['m_number']}",
                        "confidence": slot.get("confidence", "confirmed"),
                        **placement,
                    }
                )
                if row.get("event_folder_expected"):
                    last_module_event = row["event_folder_expected"]
                timeline.append(row)

            elif kind == "milestone":
                suggested = str(slot.get("suggested_milestone_id") or "").strip()
                suggested_key = suggested.lower()
                disk = by_planned.get(suggested_key) if suggested_key else None
                row: dict[str, Any] = {
                    "kind": "milestone",
                    "planned": True,
                    "arc_number": arc_number,
                    "play_order": pos,
                    "label": slot.get("label") or suggested,
                    "suggested_milestone_id": suggested or None,
                    "creature": slot.get("creature"),
                    "confidence": slot.get("confidence", "confirmed"),
                    "created": disk is not None,
                    **placement,
                }
                if disk:
                    mid = str(disk["milestone_id"])
                    mdir = Path(disk["path"])
                    role_state, bg_beats = _milestone_role_state(mdir)
                    row.update(
                        {
                            "milestone_id": mid,
                            "milestone_label": disk.get("milestone_label"),
                            "skeleton_ref": disk.get("skeleton_ref") or {},
                            "path": str(mdir),
                            "scope_type": "milestone",
                            "videos_by_role": {
                                "standalone": {
                                    "state": role_state,
                                    "bg_beat_count": bg_beats,
                                },
                            },
                        }
                    )
                else:
                    row.update(
                        {
                            "milestone_id": suggested or f"arc{arc_number}_pos{pos}",
                            "milestone_label": None,
                            "skeleton_ref": {},
                            "path": None,
                            "videos_by_role": {
                                "standalone": {"state": "absent", "bg_beat_count": 0},
                            },
                        }
                    )
                timeline.append(row)

            elif kind == "narrative":
                timeline.append(
                    {
                        "kind": "narrative",
                        "arc_number": arc_number,
                        "play_order": pos,
                        "label": slot.get("label"),
                        "creature": slot.get("creature"),
                        "confidence": slot.get("confidence", "confirmed"),
                        **placement,
                    }
                )

    return timeline, dev_fixtures

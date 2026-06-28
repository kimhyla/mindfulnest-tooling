#!/usr/bin/env python3
"""Merge recovered Event_2 beat rows from snapshots / preserved JSON into live sidecar."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_TOOLS = _SCRIPT.parent.parent / "tools"
_ROOT = _SCRIPT.parent.parent
for p in (_TOOLS, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import beat_generator as bg  # noqa: E402
from lib.paths import dropbox_root  # noqa: E402

PROD = dropbox_root() / "Production"
EVENT_DIR = PROD / "Event_2"
JUN21 = (
    Path(__file__).resolve().parent.parent
    / ".production_snapshots/archive/20260621T235135Z/global/beat_generator_state.json"
)
SESSION_TMP = PROD / "tmp23ngf_fn.tmp"
PRESERVED_27 = (
    EVENT_DIR
    / "kling_o3_clips/_preserved/latest/bg_arc1_event2_pre_beat_27.json"
)

INCOMING_PRE = [
    "bg_arc1_event2_pre_beat_24",
    "bg_arc1_event2_pre_beat_27",
    "bg_arc1_event2_pre_beat_31",
    "bg_arc1_event2_pre_beat_32",
]
INCOMING_POST = ["bg_arc1_event2_post_beat_08"]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_beat_in_tree(obj, beat_id: str) -> dict | None:
    if isinstance(obj, dict):
        if obj.get("beat_id") == beat_id:
            return obj
        for v in obj.values():
            hit = _find_beat_in_tree(v, beat_id)
            if hit:
                return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = _find_beat_in_tree(item, beat_id)
            if hit:
                return hit
    return None


def _beat_from_jun21(beat_id: str) -> dict | None:
    if not JUN21.is_file():
        return None
    data = _load_json(JUN21)
    seg_key = "event_2_post" if "_post_" in beat_id else "event_2_pre"
    for beat in data["arcs"]["arc_1"]["segments"][seg_key]["beats"]:
        if beat.get("beat_id") == beat_id:
            return copy.deepcopy(beat)
    return None


def _beat_from_session_tmp(beat_id: str) -> dict | None:
    if not SESSION_TMP.is_file():
        return None
    data = _load_json(SESSION_TMP)
    hit = _find_beat_in_tree(data, beat_id)
    return copy.deepcopy(hit) if hit else None


def _beat_from_preserved(beat_id: str) -> dict | None:
    path = EVENT_DIR / "kling_o3_clips/_preserved/latest" / f"{beat_id}.json"
    if not path.is_file():
        return None
    return copy.deepcopy(_load_json(path))


def _resolve_incoming(beat_id: str) -> dict | None:
    if beat_id == "bg_arc1_event2_pre_beat_27":
        return _beat_from_preserved(beat_id) or _beat_from_jun21(beat_id)
    if beat_id in ("bg_arc1_event2_pre_beat_31", "bg_arc1_event2_pre_beat_32"):
        return _beat_from_session_tmp(beat_id) or _beat_from_jun21(beat_id)
    return _beat_from_jun21(beat_id) or _beat_from_session_tmp(beat_id)


def _merge_segment_beats(existing: list[dict], incoming_rows: list[dict]) -> tuple[list[dict], list[str]]:
    merged_map = {b["beat_id"]: copy.deepcopy(b) for b in existing if b.get("beat_id")}
    added: list[str] = []
    for row in incoming_rows:
        bid = row.get("beat_id")
        if not bid:
            continue
        if bid in merged_map:
            merged = copy.deepcopy(row)
            saved = merged_map[bid]
            for field in bg.SIDECAR_MERGE_PRESERVE_FIELDS:
                val = saved.get(field)
                if val not in (None, "", [], {}):
                    merged[field] = val
            merged_map[bid] = merged
        else:
            merged_map[bid] = copy.deepcopy(row)
            added.append(bid)
    return bg.normalize_segment_beat_order(list(merged_map.values())), added


def main() -> int:
    bg.init_bg_paths(EVENT_DIR)
    incoming_pre = []
    incoming_post = []
    missing_sources: list[str] = []

    for bid in INCOMING_PRE:
        row = _resolve_incoming(bid)
        if row:
            incoming_pre.append(row)
        else:
            missing_sources.append(bid)

    for bid in INCOMING_POST:
        row = _resolve_incoming(bid)
        if row:
            incoming_post.append(row)
        else:
            missing_sources.append(bid)

    if missing_sources:
        print(f"WARN: no source rows for: {missing_sources}", flush=True)

    added_all: list[str] = []

    def _mutator(sidecar: dict) -> None:
        nonlocal added_all
        arc = sidecar.setdefault("arcs", {}).setdefault("arc_1", {})
        segments = arc.setdefault("segments", {})
        pre_seg = segments.setdefault("event_2_pre", {"name": "", "beats": []})
        post_seg = segments.setdefault("event_2_post", {"name": "", "beats": []})

        pre_seg["beats"], added_pre = _merge_segment_beats(pre_seg.get("beats") or [], incoming_pre)
        post_seg["beats"], added_post = _merge_segment_beats(post_seg.get("beats") or [], incoming_post)
        added_all = added_pre + added_post

        sidecar["active_context"] = {"arc_number": 1, "event_id": "2", "phase": "pre"}

    sidecar = bg.mutate_sidecar_locked(_mutator)
    bg.flush_sidecar_mirror_export()

    pre_n = len(sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"])
    post_n = len(sidecar["arcs"]["arc_1"]["segments"]["event_2_post"]["beats"])
    print(
        json.dumps(
            {
                "ok": True,
                "added": added_all,
                "event_2_pre": pre_n,
                "event_2_post": post_n,
                "missing_sources": missing_sources,
            },
            indent=2,
        )
    )
    return 0 if not missing_sources else 1


if __name__ == "__main__":
    raise SystemExit(main())

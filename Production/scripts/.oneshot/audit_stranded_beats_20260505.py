#!/usr/bin/env python3
"""Δ-C2.5 stranded-beat audit (read-only).

Per Kim 2026-05-05: the beats flagged by clean_orphan_beats_v3 dry-run as
"orphans" are NOT orphans to evict. They are real authored content
cross-event scrambled (likely by the broken 'Accept all beats' button
copying instead of moving). They need to be RELOCATED to their rightful
Event_<N>/, not deleted.

This tool is read-only. It prints each stranded beat with full context
in the format Kim requested:

    === <scope> / videos.<role> / <beat_id> ===
    speaker: <speaker>
    text:    <full text, multi-line preserved>
    CURRENT location: <scope>/<role>/beats[<beat_id>] (NOT in display_order)
    PROPOSED target: ??? (Kim to decide)

Bonus: cross-event text-match scan — for each stranded beat, searches
all OTHER scopes' display_order'd beats for matching text. If a match
is found, flags it as a possible cross-event-copy footprint that may
inform the redistribution mapping (or expose duplicates Kim should know
about).

Default scope: all Production/Event_*/ + Production/Milestones/*/.
Override via MINDFULNEST_PRODUCTION_ROOT env var.

USAGE
    MINDFULNEST_PRODUCTION_ROOT="$DROPBOX/Production" \\
        python3 Production/scripts/audit_stranded_beats_20260505.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()


def _production_root() -> Path:
    override = os.environ.get("MINDFULNEST_PRODUCTION_ROOT")
    if override:
        return Path(override)
    return _THIS.parent.parent  # Production/


def _walk_state_files(prod_root: Path) -> list[tuple[Path, str, str]]:
    """Yield (state_path, kind, scope_label) for events + milestones."""
    out: list[tuple[Path, str, str]] = []
    for p in sorted(prod_root.glob("Event_*/production_state.json")):
        out.append((p, "event", p.parent.name))  # e.g. "Event_1"
    milestones_root = prod_root / "Milestones"
    if milestones_root.is_dir():
        for p in sorted(milestones_root.glob("*/state.json")):
            out.append((p, "milestone", f"milestone:{p.parent.name}"))
    return out


def _stranded_beats_in_state(state: dict, scope_label: str) -> list[dict]:
    """Find beats present in beats{} but missing from a list-shaped display_order.

    Same logic clean_orphan_beats_v3._identify_orphans uses, but flagged as
    'stranded' (Kim's term — these may be misplaced authored content, not
    deletion targets).

    Returns: list of {scope_label, role, beat_id, payload, display_order_snapshot}
    """
    found: list[dict] = []
    videos = (state or {}).get("videos") or {}
    if not isinstance(videos, dict):
        return found
    for role, part in videos.items():
        if not isinstance(part, dict):
            continue
        do = part.get("display_order")
        if not isinstance(do, list):
            continue
        beats = part.get("beats")
        if not isinstance(beats, dict):
            continue
        allowed = set(do)
        for bid, payload in beats.items():
            if bid not in allowed:
                found.append({
                    "scope_label": scope_label,
                    "role": role,
                    "beat_id": bid,
                    "payload": payload,
                    "display_order_snapshot": list(do),
                })
    return found


def _all_anchored_beats(prod_root: Path) -> list[dict]:
    """Catalog every beat that IS in its partition's display_order list,
    across all events + milestones. Used for the cross-event text-match scan.

    Returns: list of {scope_label, role, beat_id, text}
    """
    catalog: list[dict] = []
    for state_path, _kind, scope_label in _walk_state_files(prod_root):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        videos = (state or {}).get("videos") or {}
        if not isinstance(videos, dict):
            continue
        for role, part in videos.items():
            if not isinstance(part, dict):
                continue
            do = part.get("display_order")
            if not isinstance(do, list):
                continue
            beats = part.get("beats") or {}
            for bid in do:
                bdata = beats.get(bid) if isinstance(beats, dict) else None
                text = (bdata or {}).get("text") or ""
                catalog.append({
                    "scope_label": scope_label,
                    "role": role,
                    "beat_id": bid,
                    "text": text,
                })
    return catalog


def _normalize_text(s: str) -> str:
    """Light normalization for cross-event text-match: lowercase, collapse whitespace."""
    return " ".join((s or "").lower().split())


def _find_text_duplicates(
    stranded: dict,
    anchored: list[dict],
) -> list[dict]:
    """Search anchored catalog for beats whose text matches the stranded beat.

    Match criterion: normalized text equality OR substring containment in
    either direction (handles minor edits across events). Only flags
    matches in scopes OTHER than the stranded beat's own scope.
    """
    target_text = _normalize_text((stranded.get("payload") or {}).get("text") or "")
    if not target_text or len(target_text) < 12:
        return []
    out: list[dict] = []
    for a in anchored:
        if a["scope_label"] == stranded["scope_label"] and a["role"] == stranded["role"]:
            continue
        a_text = _normalize_text(a.get("text") or "")
        if not a_text:
            continue
        if a_text == target_text or a_text in target_text or target_text in a_text:
            out.append(a)
    return out


def _print_block(stranded: dict, anchored: list[dict]) -> None:
    payload = stranded.get("payload") or {}
    speaker = payload.get("speaker") or "(none)"
    text = payload.get("text") or ""
    do_snap = stranded["display_order_snapshot"]
    print(f"=== {stranded['scope_label']} / videos.{stranded['role']} / {stranded['beat_id']} ===")
    print(f"speaker: {speaker}")
    print(f"text:    {text!r}")
    print(f"CURRENT location: {stranded['scope_label']}/{stranded['role']}/beats[{stranded['beat_id']}]")
    print(f"  (NOT in display_order; current display_order has {len(do_snap)} entries: {do_snap})")
    # Bonus context: text-match search across other anchored partitions.
    dups = _find_text_duplicates(stranded, anchored)
    if dups:
        print(f"  TEXT-MATCH FOOTPRINT: same/similar text found in {len(dups)} other "
              f"anchored beat(s):")
        for d in dups[:5]:  # cap output to first 5
            print(f"    - {d['scope_label']}/{d['role']}/{d['beat_id']}")
        if len(dups) > 5:
            print(f"    - ... and {len(dups) - 5} more")
    else:
        print(f"  TEXT-MATCH FOOTPRINT: no matching anchored text found in other "
              f"scopes — likely unique to this scope")
    print(f"PROPOSED target: ??? (Kim to decide — fill mapping table)")
    print()


def main() -> int:
    prod_root = _production_root()
    print(f"Δ-C2.5 stranded-beat audit (read-only)")
    print(f"  production_root: {prod_root}")
    print()

    targets = _walk_state_files(prod_root)
    print(f"  scanned {len(targets)} state file(s):")
    for p, _kind, label in targets:
        print(f"    - {label} ({p})")
    print()

    # Build the anchored-beat catalog for the cross-event text-match scan.
    print(f"  building anchored-beat catalog for text-match scan...")
    anchored = _all_anchored_beats(prod_root)
    print(f"    catalog size: {len(anchored)} anchored beat(s)")
    print()

    # Find stranded beats per state file.
    stranded_total: list[dict] = []
    for state_path, _kind, scope_label in targets:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  {scope_label}: SKIP (could not read: {type(exc).__name__}: {exc})")
            continue
        s = _stranded_beats_in_state(state, scope_label)
        stranded_total.extend(s)

    if not stranded_total:
        print("=" * 60)
        print(f"AUDIT_OK: 0 stranded beats found across {len(targets)} scope(s).")
        return 0

    print("=" * 60)
    print(f"STRANDED BEATS — {len(stranded_total)} total across "
          f"{len(set(s['scope_label'] for s in stranded_total))} scope(s):")
    print()
    for s in stranded_total:
        _print_block(s, anchored)

    # Tail summary table for Kim's mapping reference.
    print("=" * 60)
    print(f"SUMMARY TABLE (for Kim's mapping fill-in):")
    print()
    print(f"  {'beat_id':<14} {'source_scope':<28} {'source_role':<10} → target?  position?")
    for s in stranded_total:
        print(f"  {s['beat_id']:<14} {s['scope_label']:<28} {s['role']:<10}")
    print()
    print(f"AUDIT_OK: {len(stranded_total)} stranded beat(s) presented for "
          "redistribution mapping. NO mutations performed (read-only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

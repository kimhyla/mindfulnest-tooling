"""Milestone on-disk state helpers (MILESTONE_STANDALONE_INDEPENDENT_V1)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.atomic_json_write import atomic_json_write

# Known milestone → arc skeleton segment (extend as new milestones are authored).
MILESTONE_SKELETON_CATALOG: dict[str, dict[str, Any]] = {
    "milestone1_arc1": {
        "arc_number": 1,
        "event_id": "3b",
        "phase": "full",
        "library_event_id": "Event_1",
        "display_name": "EVENT 3b: OLIVER MEET",
    },
    "opening_storybook": {
        "arc_number": 1,
        "event_id": "0",
        "phase": "full",
        "library_event_id": "Event_0",
        "display_name": "EVENT 0: OPENING VIDEO SEQUENCE",
    },
}

_LABEL_OLIVER_RE = re.compile(r"oliver", re.I)


def load_milestone_state(milestone_dir: Path) -> dict:
    path = milestone_dir / "state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_milestone_state(milestone_dir: Path, state: dict) -> None:
    atomic_json_write(str(milestone_dir / "state.json"), state)


def resolve_milestone_skeleton_ref(state: dict, milestone_id: str) -> dict[str, Any]:
    """Return {arc_number, event_id, phase, library_event_id?, display_name?}."""
    explicit = state.get("skeleton_ref")
    if isinstance(explicit, dict) and explicit.get("event_id"):
        return {
            "arc_number": int(explicit.get("arc_number") or 1),
            "event_id": str(explicit["event_id"]),
            "phase": str(explicit.get("phase") or "full"),
            "library_event_id": explicit.get("library_event_id"),
            "display_name": explicit.get("display_name"),
        }
    if milestone_id in MILESTONE_SKELETON_CATALOG:
        return dict(MILESTONE_SKELETON_CATALOG[milestone_id])
    label = str(state.get("milestone_label") or "")
    if _LABEL_OLIVER_RE.search(label) or _LABEL_OLIVER_RE.search(milestone_id):
        return dict(MILESTONE_SKELETON_CATALOG["milestone1_arc1"])
    # Fallback: arc from id pattern milestoneN_arcM
    m = re.search(r"arc(\d+)", milestone_id, re.I)
    arc = int(m.group(1)) if m else 1
    return {
        "arc_number": arc,
        "event_id": milestone_id,
        "phase": "main",
        "library_event_id": f"Event_{arc}",
    }


def ensure_milestone_runtime_fields(milestone_dir: Path) -> dict:
    """Hydrate skeleton_ref + library_event_id on existing milestones; return state."""
    state = load_milestone_state(milestone_dir)
    if not state:
        return state
    mid = str(state.get("milestone_id") or milestone_dir.name)
    skel = resolve_milestone_skeleton_ref(state, mid)
    changed = False
    if not state.get("skeleton_ref"):
        state["skeleton_ref"] = {
            "arc_number": skel["arc_number"],
            "event_id": skel["event_id"],
            "phase": skel["phase"],
        }
        changed = True
    if not state.get("library_event_id"):
        state["library_event_id"] = skel.get("library_event_id") or f"Event_{skel['arc_number']}"
        changed = True
    if changed:
        state["updated_at"] = state.get("updated_at")
        save_milestone_state(milestone_dir, state)
    return state


def milestone_segment_triple(skeleton_ref: dict[str, Any]) -> tuple[int, str, str]:
    """Return (arc_number, event_id, phase) for a milestone skeleton ref."""
    return (
        int(skeleton_ref.get("arc_number") or 1),
        str(skeleton_ref.get("event_id") or ""),
        str(skeleton_ref.get("phase") or "full"),
    )


def milestone_sidecar_seg_key(skeleton_ref: dict[str, Any]) -> str:
    _arc, event_id, phase = milestone_segment_triple(skeleton_ref)
    return f"event_{event_id}_{phase}"


def milestone_sidecar_is_polluted(sidecar: dict, skeleton_ref: dict[str, Any]) -> bool:
    """True when sidecar holds Event-scope segments instead of the milestone skeleton only."""
    arc, event_id, phase = milestone_segment_triple(skeleton_ref)
    seg_key = f"event_{event_id}_{phase}"
    arc_key = f"arc_{arc}"
    arcs = sidecar.get("arcs") or {}
    if not arcs:
        return False
    if set(arcs.keys()) - {arc_key}:
        return True
    segments = (arcs.get(arc_key) or {}).get("segments") or {}
    if set(segments.keys()) - {seg_key}:
        return True
    ctx = sidecar.get("active_context") or {}
    if ctx.get("event_id") != event_id or (ctx.get("phase") or "full") != phase:
        return True
    if ctx.get("arc_number") not in (None, arc):
        return True
    return False


def isolate_milestone_sidecar(sidecar: dict, skeleton_ref: dict[str, Any]) -> bool:
    """Keep only the milestone skeleton segment; drop global Event sidecar pollution.

    Returns True when the sidecar dict was modified.
    """
    if not skeleton_ref or not skeleton_ref.get("event_id"):
        return False
    arc, event_id, phase = milestone_segment_triple(skeleton_ref)
    seg_key = f"event_{event_id}_{phase}"
    arc_key = f"arc_{arc}"
    if not milestone_sidecar_is_polluted(sidecar, skeleton_ref):
        return False

    milestone_seg: dict[str, Any] = {"name": "", "beats": []}
    for av in (sidecar.get("arcs") or {}).values():
        hit = (av.get("segments") or {}).get(seg_key)
        if isinstance(hit, dict):
            milestone_seg = dict(hit)
            break

    sidecar["active_context"] = {
        "arc_number": arc,
        "event_id": event_id,
        "phase": phase,
    }
    sidecar["arcs"] = {
        arc_key: {"segments": {seg_key: milestone_seg}},
    }
    return True


def milestone_stitch_state_path(milestone_dir: Path) -> Path:
    return milestone_dir / "stitch_state.json"


def list_milestones(prod_root: Path) -> list[dict[str, Any]]:
    root = prod_root / "Milestones"
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        state = ensure_milestone_runtime_fields(d)
        skel = resolve_milestone_skeleton_ref(state, d.name)
        out.append({
            "milestone_id": d.name,
            "milestone_label": state.get("milestone_label"),
            "path": str(d),
            "skeleton_ref": state.get("skeleton_ref") or skel,
            "library_event_id": state.get("library_event_id"),
        })
    return out

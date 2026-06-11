"""Canonical intro teleport tails — 3 Chipper speak variants + shared whiteout.

Rotation: intro videos only (phase=pre). Within each arc, event position N uses
variant (N-1) % 3. Arc number is ignored — Event 1 in arc 2 resets to slot 0
same as Event 1 in arc 1. Event 4 → slot 0, Event 5 → slot 1, etc.

Resolution (phase=post) never uses this path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CHIPPER_REGISTRY_REL = "Production/templates/chipper_teleport_intro/canonical_registry.json"
ARLO_REGISTRY_REL = "Production/templates/arlo_teleport_intro/canonical_registry.json"
CHIPPER_MANIFEST_REL = "Production/templates/chipper_teleport_intro/manifest.json"
ARLO_MANIFEST_REL = "Production/templates/arlo_teleport_intro/manifest.json"
CANONICAL_REGISTRY_REL = CHIPPER_REGISTRY_REL  # legacy default
DEFAULT_VARIANT_COUNT = 3


def _registry_has_variants(project_root: Path, rel: str) -> bool:
    path = project_root / rel
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("variants"))


def _manifest_rel_for_guide(guide: str | None) -> str:
    g = (guide or "").strip().lower()
    if g == "arlo":
        return ARLO_MANIFEST_REL
    if g == "chipper":
        return CHIPPER_MANIFEST_REL
    return CHIPPER_MANIFEST_REL


def _registry_rel_for_guide(guide: str | None) -> str:
    g = (guide or "").strip().lower()
    if g == "arlo":
        return ARLO_REGISTRY_REL
    if g == "chipper":
        return CHIPPER_REGISTRY_REL
    return CHIPPER_REGISTRY_REL


def active_manifest_path(project_root: Path, *, guide: str | None = None) -> Path:
    import os

    env = os.environ.get("TELEPORT_INTRO_MANIFEST")
    if env:
        return Path(env)
    env_guide = os.environ.get("TELEPORT_INTRO_GUIDE")
    return project_root / _manifest_rel_for_guide(guide or env_guide)


def active_registry_rel(project_root: Path, *, guide: str | None = None) -> str:
    """Resolve canonical registry for a guide character (default Chipper legacy)."""
    import os

    env = os.environ.get("TELEPORT_INTRO_REGISTRY")
    if env:
        return env
    env_guide = os.environ.get("TELEPORT_INTRO_GUIDE")
    rel = _registry_rel_for_guide(guide or env_guide)
    if (project_root / rel).is_file():
        return rel
    if _registry_has_variants(project_root, CHIPPER_REGISTRY_REL):
        return CHIPPER_REGISTRY_REL
    if _registry_has_variants(project_root, ARLO_REGISTRY_REL):
        return ARLO_REGISTRY_REL
    return CHIPPER_REGISTRY_REL


def parse_event_number(event: str) -> int:
    """Arc-local event index: Event_1 → 1, '4' → 4, event_3b → 3."""
    raw = re.sub(r"^event_", "", (event or "").strip(), flags=re.IGNORECASE)
    m = re.match(r"(\d+)", raw)
    if not m:
        raise ValueError(f"cannot parse event number from {event!r}")
    return int(m.group(1))


def intro_tail_variant_index(event_number: int, variant_count: int = DEFAULT_VARIANT_COUNT) -> int:
    """0-based slot for intro tail rotation."""
    if variant_count < 1:
        raise ValueError("variant_count must be >= 1")
    return (event_number - 1) % variant_count


def registry_path(project_root: Path, *, guide: str | None = None) -> Path:
    return project_root / active_registry_rel(project_root, guide=guide)


def load_registry(project_root: Path, *, guide: str | None = None) -> dict[str, Any]:
    path = registry_path(project_root, guide=guide)
    if not path.is_file():
        return {"schema_version": 1, "variant_count": DEFAULT_VARIANT_COUNT, "variants": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(project_root: Path, data: dict[str, Any], *, guide: str | None = None) -> Path:
    path = registry_path(project_root, guide=guide)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def variant_entry(registry: dict, slot: int) -> dict | None:
    for v in registry.get("variants") or []:
        if int(v.get("slot", -1)) == slot:
            return v
    return None


def resolve_canonical_tail_for_event(
    event: str,
    project_root: Path,
    *,
    phase: str | None = None,
    event_id: str | None = None,
    guide: str | None = None,
) -> Path | None:
    """Return intro_tail.mp4 for arc-local event when phase is intro/pre."""
    if phase is not None and str(phase).lower() in ("post", "resolution"):
        return None
    reg = load_registry(project_root, guide=guide)
    count = int(reg.get("variant_count") or DEFAULT_VARIANT_COUNT)
    if not reg.get("variants"):
        return None
    if reg.get("single_canonical"):
        slot = 0
    else:
        key = event_id if event_id is not None else event
        try:
            n = parse_event_number(str(key))
        except ValueError:
            return None
        slot = intro_tail_variant_index(n, count)
    entry = variant_entry(reg, slot)
    if not entry:
        return None
    rel = entry.get("intro_tail_rel") or entry.get("intro_tail")
    if not rel:
        return None
    p = project_root / str(rel)
    return p if p.is_file() else None


def upsert_variant(
    registry: dict,
    *,
    slot: int,
    speak_source: str,
    intro_tail_rel: str,
    label: str = "",
    beat_id: str = "",
    dialogue: str = "",
) -> dict:
    variants = list(registry.get("variants") or [])
    row = {
        "slot": slot,
        "label": label or f"variant_{slot}",
        "speak_source": speak_source,
        "intro_tail_rel": intro_tail_rel,
        "beat_id": beat_id,
        "dialogue": dialogue,
        "built_at": None,
    }
    replaced = False
    for i, v in enumerate(variants):
        if int(v.get("slot", -1)) == slot:
            variants[i] = {**v, **row}
            replaced = True
            break
    if not replaced:
        variants.append(row)
    variants.sort(key=lambda x: int(x.get("slot", 0)))
    registry["variants"] = variants
    registry["variant_count"] = int(registry.get("variant_count") or DEFAULT_VARIANT_COUNT)
    registry["rotation"] = {
        "applies_to": "intro_only",
        "phase_keys": ["pre", "intro"],
        "formula": "(arc_local_event_number - 1) % variant_count",
        "arc_number_ignored": True,
        "event_1_uses_slot": 0,
    }
    return registry

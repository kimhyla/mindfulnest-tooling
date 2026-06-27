"""Canonical module event_id (M<n>E<m>) helpers.

Per PB_2_THERAPEUTIC_SOURCES_LOAD_V1 + Arc Skeleton play-order convention:
  Production folder ``Event_N`` = skeleton **play-order event N** (NOT M-number N).
  Arc 1 example: Event_1→M1 Tessa, Event_2→M2 Luna, Event_3→M4 Ember,
  Event_4→M6 Bramble, Event_5→M3 Benson, Event_6→M5 Bork.

  Canonical ``production_state.json`` event_id stores ``M{m_number}E1`` where
  ``m_number`` is the creature assignment from the skeleton Module Structure Table.

Suggest Script resolves ``m_number`` via skeleton play-order lookup, then loads
the Therapeutic Note for that module from ``ARC_XX_SKELETON_FINAL.md``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_MODULE_EVENT_ID_RE = re.compile(r"^M(\d+)E(\d+)$", re.IGNORECASE)
_NUMBERED_EVENT_DIR_RE = re.compile(r"^Event_(\d+)$", re.IGNORECASE)


def parse_m_form_event_identity(event_id_str: str) -> tuple[int, int] | None:
    """Return ``(m_number, event_number)`` from canonical ``M<n>E<m>`` id only."""
    raw = str(event_id_str or "").strip()
    m = _MODULE_EVENT_ID_RE.match(raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def production_folder_to_arc_play_order(folder_id: str) -> tuple[int, int] | None:
    """Map ``Event_N`` folder → ``(arc_number, play_order_within_arc)``.

    Six modules per arc: Event_1–6 = Arc 1 play 1–6, Event_7–12 = Arc 2 play 1–6, …
    """
    raw = str(folder_id or "").strip()
    m = _NUMBERED_EVENT_DIR_RE.match(raw)
    if not m:
        return None
    n = int(m.group(1))
    if n < 1:
        return None
    arc_number = ((n - 1) // 6) + 1
    play_order = ((n - 1) % 6) + 1
    return arc_number, play_order


def is_numbered_event_folder_id(event_id_str: str) -> bool:
    return bool(_NUMBERED_EVENT_DIR_RE.match(str(event_id_str or "").strip()))


def resolve_m_number_from_production_folder(folder_id: str, *, bg_module=None) -> tuple[int, int, int] | None:
    """Resolve ``(arc_number, play_order, m_number)`` from ``Event_N`` via Arc Skeleton.

    Returns None when folder is not ``Event_<N>`` or skeleton lookup fails.
    """
    arc_play = production_folder_to_arc_play_order(folder_id)
    if not arc_play:
        return None
    arc_number, play_order = arc_play
    if bg_module is None:
        import sys
        from pathlib import Path

        tools = Path(__file__).resolve().parent.parent / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import beat_generator as bg_module  # noqa: PLC0415
    m_number = bg_module.find_m_number_for_play_order_event(arc_number, play_order)
    if m_number is None:
        return None
    return arc_number, play_order, m_number


def canonical_module_event_id(
    event_id_str: str,
    *,
    production_folder_id: str | None = None,
    bg_module=None,
) -> str | None:
    """Normalize to ``M{m_number}E1`` using skeleton play-order when possible."""
    folder = production_folder_id or (
        event_id_str if is_numbered_event_folder_id(event_id_str) else None
    )
    if folder:
        resolved = resolve_m_number_from_production_folder(folder, bg_module=bg_module)
        if resolved:
            _arc, _play, m_number = resolved
            return f"M{m_number}E1"
    parsed = parse_m_form_event_identity(event_id_str)
    if parsed:
        m_num, e_num = parsed
        return f"M{m_num}E{e_num}"
    return None


def heal_production_state_event_id(state_manager, *, bg_module=None) -> bool:
    """Rewrite ``production_state.json`` event_id to skeleton-backed ``M{m}E1``.

    Uses the event folder name (``Event_N``) as authoritative play-order source.
    Returns True when state was updated on disk.
    """
    state_path: Path = state_manager.state_path
    if not state_path.is_file():
        return False
    try:
        state = state_manager.read_state()
    except Exception:
        return False
    folder_id = str(getattr(state_manager, "event_dir", "") or "")
    if folder_id:
        from pathlib import Path as _Path

        folder_id = _Path(folder_id).name
    current = str(state.get("event_id") or "").strip() or folder_id
    canonical = canonical_module_event_id(
        current,
        production_folder_id=folder_id or None,
        bg_module=bg_module,
    )
    if not canonical or canonical.upper() == current.upper():
        return False
    state["event_id"] = canonical
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state_manager.write_state(state)
    state_manager.event_id = canonical
    print(
        f"[module_event_id] healed production_state event_id "
        f"{current!r} → {canonical!r} ({state_path})",
        flush=True,
    )
    return True

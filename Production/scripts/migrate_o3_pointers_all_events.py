#!/usr/bin/env python3
"""M1 — Clear stale O3 job cache pointers when terminal proves attempt finished.

Scans global beat_generator_state.json beats + Event_*/arlo_o3_jobs terminals.
When terminal status is done/done_with_warning/cancelled/failed, clears lifecycle
cache fields (not gallery options).

Usage:
  python3 Production/scripts/migrate_o3_pointers_all_events.py --dry-run
  python3 Production/scripts/migrate_o3_pointers_all_events.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLING_ROOT = HERE.parent.parent
TOOLS = TOOLING_ROOT / "Production" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from o3_job_status_contract import (  # noqa: E402
    INTENT_TERMINAL_STATUSES,
    O3_JOB_CACHE_FIELDS,
    clear_o3_job_cache_fields,
    resolve_o3_current_job_id,
)
from o3_generation_intent import (  # noqa: E402
    intent_event_dir_for_beat,
    load_intent_terminal,
    terminal_path_for_job,
)


def _prod_root() -> Path:
    dropbox = Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    if dropbox.is_dir():
        return dropbox
    return TOOLING_ROOT / "Production"


def _iter_beats(sidecar: dict):
    for arc in (sidecar.get("arcs") or {}).values():
        if not isinstance(arc, dict):
            continue
        for seg in (arc.get("segments") or {}).values():
            if not isinstance(seg, dict):
                continue
            for beat in seg.get("beats") or []:
                if isinstance(beat, dict):
                    yield beat


def _beat_has_cache_pointer(beat: dict) -> bool:
    return any(beat.get(k) for k in O3_JOB_CACHE_FIELDS)


def _terminal_for_beat(beat: dict) -> dict | None:
    beat_id = str(beat.get("beat_id") or "").strip()
    job_id = resolve_o3_current_job_id(beat)
    if not beat_id or not job_id:
        return None
    try:
        event_dir = intent_event_dir_for_beat(beat_id)
    except Exception:
        return None
    term_path = terminal_path_for_job(job_id, event_dir)
    if not term_path.is_file():
        return None
    try:
        return load_intent_terminal(term_path)
    except Exception:
        return None


def migrate_sidecar(sidecar: dict, *, apply: bool) -> list[str]:
    changed: list[str] = []
    for beat in _iter_beats(sidecar):
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id or not _beat_has_cache_pointer(beat):
            continue
        terminal = _terminal_for_beat(beat)
        if not terminal:
            continue
        status = str(terminal.get("status") or "").strip()
        if status not in INTENT_TERMINAL_STATUSES:
            continue
        before = {k: beat.get(k) for k in O3_JOB_CACHE_FIELDS if beat.get(k)}
        if not before:
            continue
        if apply:
            clear_o3_job_cache_fields(beat)
            if status in ("done", "done_with_warning") and str(beat.get("kling_o3_status") or "") == "approved":
                beat["status"] = "approved"
                beat["kling_o3_voice_fix_status"] = "approved"
        changed.append(f"{beat_id} terminal={status} cleared={list(before.keys())}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate stale O3 job cache pointers")
    parser.add_argument("--apply", action="store_true", help="Write sidecar (default dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default)")
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=None,
        help="Path to beat_generator_state.json",
    )
    args = parser.parse_args()
    apply = bool(args.apply)
    sidecar_path = args.sidecar or (_prod_root() / "beat_generator_state.json")
    if not sidecar_path.is_file():
        print(f"FATAL: sidecar not found: {sidecar_path}", file=sys.stderr)
        return 1
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    rows = migrate_sidecar(sidecar, apply=apply)
    print(f"[migrate_o3_pointers] sidecar={sidecar_path} apply={apply} changed={len(rows)}")
    for row in rows[:50]:
        print(f"  {row}")
    if len(rows) > 50:
        print(f"  ... and {len(rows) - 50} more")
    if apply and rows:
        backup = sidecar_path.with_suffix(".json.pre_o3_pointer_migrate")
        if not backup.is_file():
            backup.write_text(sidecar_path.read_text(encoding="utf-8"), encoding="utf-8")
        sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        print(f"[migrate_o3_pointers] wrote {sidecar_path} (backup {backup.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# S1 — Beat Gen arc soak: all beats idle when terminal done exists on disk.
#
# Scans global sidecar + Event_*/arlo_o3_jobs terminals. Fails when:
#   - terminal status is done/done_with_warning but beat.job_busy would be true
#   - beat has running voice_fix status but terminal is terminal
#
# Usage:
#   bash Production/scripts/bg_arc_soak.sh
#   MN_EVENT_ID=Event_2 bash Production/scripts/bg_arc_soak.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING_ROOT="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}"
EVENT_FILTER="${MN_EVENT_ID:-}"
export MN_TOOLING_ROOT="${TOOLING_ROOT}"

cd "${TOOLING_ROOT}/Production/tools"

export MN_SOAK_DROPBOX="${DROPBOX}"
export MN_SOAK_EVENT_FILTER="${EVENT_FILTER}"

python3 <<'PY'
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

tools = Path(os.environ["MN_TOOLING_ROOT"]) / "Production" / "tools"
sys.path.insert(0, str(tools))
dropbox = Path(os.environ["MN_SOAK_DROPBOX"])
event_filter = os.environ.get("MN_SOAK_EVENT_FILTER", "").strip()

from o3_job_status_contract import (
    INTENT_TERMINAL_STATUSES,
    O3_VOICE_FIX_RUNNING_STATUSES,
    beat_job_busy,
    resolve_o3_current_job_id,
)
from o3_generation_intent import intent_event_dir_for_beat, load_intent_terminal, terminal_path_for_job

sidecar_path = dropbox / "beat_generator_state.json"
if not sidecar_path.is_file():
    print(f"FATAL: missing sidecar {sidecar_path}", file=sys.stderr)
    sys.exit(1)

sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
failures = []
checked = 0
terminal_done = 0
idle = 0

def beat_event_num(beat_id: str) -> Optional[str]:
    m = re.search(r"_event(\d+)_", beat_id)
    return m.group(1) if m else None

for arc in (sidecar.get("arcs") or {}).values():
    if not isinstance(arc, dict):
        continue
    for seg in (arc.get("segments") or {}).values():
        if not isinstance(seg, dict):
            continue
        for beat in seg.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            beat_id = str(beat.get("beat_id") or "").strip()
            if not beat_id:
                continue
            ev_num = beat_event_num(beat_id)
            if event_filter and ev_num and f"Event_{ev_num}" != event_filter and event_filter != f"Event_{ev_num}":
                if event_filter.replace("Event_", "") != ev_num:
                    continue
            checked += 1
            try:
                event_dir = intent_event_dir_for_beat(beat_id)
            except Exception:
                event_dir = dropbox / f"Event_{ev_num}" if ev_num else None
            job_id = resolve_o3_current_job_id(beat)
            terminal = None
            if job_id and event_dir:
                tp = terminal_path_for_job(job_id, event_dir)
                if tp.is_file():
                    try:
                        terminal = load_intent_terminal(tp)
                    except Exception:
                        terminal = None
            term_status = str((terminal or {}).get("status") or "")
            if term_status in INTENT_TERMINAL_STATUSES:
                terminal_done += 1
                busy = beat_job_busy(beat, event_dir)
                voice = str(beat.get("kling_o3_voice_fix_status") or "")
                if busy and term_status in ("done", "done_with_warning", "cancelled", "failed"):
                    failures.append(f"{beat_id}: terminal={term_status} but job_busy=True")
                if voice in O3_VOICE_FIX_RUNNING_STATUSES and term_status in ("done", "done_with_warning"):
                    failures.append(f"{beat_id}: terminal={term_status} but voice_fix={voice}")
            else:
                busy = beat_job_busy(beat, event_dir)
                if not busy:
                    idle += 1

print("=== bg_arc_soak ===")
print(f"  sidecar:       {sidecar_path}")
print(f"  event_filter:  {event_filter or 'all'}")
print(f"  beats_checked: {checked}")
print(f"  terminal_done: {terminal_done}")
print(f"  idle_no_job:   {idle}")
print(f"  failures:      {len(failures)}")
for f in failures[:20]:
    print(f"  FAIL: {f}")
if failures:
    sys.exit(1)
print("PASS: bg_arc_soak")
PY

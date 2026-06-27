#!/usr/bin/env bash
# BEATGEN_PER_EVENT_SQLITE_V1 — multipass proof for event-scoped beat stores.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"
TOOLS="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}/Production/tools"
STATE="${HOME}/.mindfulnest/state"
JSON="${MN_DROPBOX_PRODUCTION:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}/beat_generator_state.json"

echo "=== beatgen per-event sqlite durability ==="

grep -q 'reconcile_event_sidecar_after_milestone_exit' "${TOOLS}/production_server.py" \
  || { echo "FATAL: production_server startup reconcile missing" >&2; exit 1; }

cd "${TOOLS}"
REPO_ROOT="$(cd "${TOOLS}/../.." && pwd)"
PYTHONPATH="${REPO_ROOT}/Production:${REPO_ROOT}" python3 -m pytest \
  tests/test_event_load_sidecar_reconcile.py \
  tests/test_beatgen_per_event_sqlite.py \
  -q

check_port() {
  local event_id="$1"
  local port="$2"
  local db="${STATE}/beatgen_$(python3 -c "print(''.join('${event_id}'.split('_')).lower())").db"
  local base="http://127.0.0.1:${port}"
  echo "--- ${event_id} :${port} db=${db} ---"
  curl -sf "${base}/api/event/current" >/dev/null
  local beats
  beats="$(curl -sf "${base}/api/bg/session-state?scope_event_id=${event_id}&scope_video_role=intro" \
    | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('beats') or []))")"
  echo "intro beats=${beats}"
  if [[ ! -f "${db}" ]]; then
    echo "FATAL: missing per-event db ${db}" >&2
    exit 1
  fi
  local integrity count
  integrity="$(sqlite3 "${db}" 'PRAGMA integrity_check;')"
  count="$(sqlite3 "${db}" 'SELECT COUNT(*) FROM beats;')"
  echo "integrity=${integrity} total_beats=${count}"
  if [[ "${integrity}" != "ok" ]]; then
    echo "FATAL: integrity failed for ${db}" >&2
    exit 1
  fi
  if [[ "${event_id}" == "Event_3" && "${beats}" -lt 6 ]]; then
    echo "FATAL: Event_3 expected >=6 intro beats, got ${beats}" >&2
    exit 1
  fi
  if [[ "${event_id}" == "Event_3" ]]; then
    mirror_beats="$(python3 - "$JSON" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
d = json.loads(p.read_text())
segs = (d.get("arcs") or {}).get("arc_1", {}).get("segments") or {}
seg = segs.get("event_3_pre") or {}
print(len(seg.get("beats") or []))
PY
)"
    if [[ "${beats}" -lt "${mirror_beats}" ]]; then
      echo "FATAL: Event_3 intro beats=${beats} < mirror=${mirror_beats} (JSON union bootstrap failed)" >&2
      exit 1
    fi
  fi
  if [[ "${event_id}" == "Event_2" && "${beats}" -lt 1 ]]; then
    echo "FATAL: Event_2 intro beats empty" >&2
    exit 1
  fi
}

check_port Event_2 5112
check_port Event_3 5113
check_port Event_4 5114

python3 - <<PY
import json, sys
from pathlib import Path
p = Path("${JSON}")
d = json.loads(p.read_text())
segs = d.get("arcs", {}).get("arc_1", {}).get("segments", {})
e2 = len((segs.get("event_2_pre") or {}).get("beats") or [])
e3 = len((segs.get("event_3_pre") or {}).get("beats") or [])
print(f"mirror event_2_pre={e2} event_3_pre={e3}")
if e2 < 1 or e3 < 6:
    sys.exit("FATAL: global mirror missing cross-event segments")
PY

echo "OK: beatgen per-event sqlite durability passed"

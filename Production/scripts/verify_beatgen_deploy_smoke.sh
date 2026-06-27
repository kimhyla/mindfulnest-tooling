#!/usr/bin/env bash
# Beatgen SQLite deploy smoke — integrity + beat count before/after server restart.
# BEATGEN_CATEGORY_FIX_ARC_V1 — per-event MN_BEATGEN_DB_PATH + dedicated-port relaunch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

PORT="${1:-5112}"
EVENT_ID="$(port_to_event_id "${PORT}")"
EVENT_SLUG="$(python3 -c "import sys; print(''.join(sys.argv[1].split('_')).lower())" "${EVENT_ID}")"
DB="${MN_BEATGEN_DB_PATH:-${HOME}/.mindfulnest/state/beatgen_${EVENT_SLUG}.db}"
BASE="http://127.0.0.1:${PORT}"
DROPBOX_PROD="${MN_DROPBOX_PRODUCTION:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}"
TOOL_SERVER="${MN_TOOLING_SERVER:-$HOME/Projects/mindfulnest-tooling/Production/tools/production_server.py}"
LOG="/tmp/mindfulnest_server_${EVENT_SLUG}.log"

echo "=== beatgen deploy smoke (port ${PORT} event=${EVENT_ID}) ==="
echo "db: ${DB}"

if [[ ! -f "${DB}" ]]; then
  echo "WARN: ${DB} missing — skip integrity (milestone-only servers may not need it)"
else
  INTEGRITY="$(sqlite3 "${DB}" 'PRAGMA integrity_check;' 2>&1 || true)"
  COUNT="$(sqlite3 "${DB}" 'SELECT COUNT(*) FROM beats;' 2>&1 || echo 0)"
  echo "before restart: integrity=${INTEGRITY} beats=${COUNT}"
  if [[ "${INTEGRITY}" != "ok" ]]; then
    echo "FATAL: beatgen.db integrity_check failed: ${INTEGRITY}" >&2
    exit 1
  fi
fi

HTTP="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/" || echo 000)"
if [[ "${HTTP}" != "200" ]]; then
  echo "FATAL: server not up at ${BASE} (HTTP ${HTTP})" >&2
  exit 1
fi

curl -s -X POST "${BASE}/api/server/restart" >/dev/null || true
HTTP2="000"
for _i in $(seq 1 30); do
  sleep 2
  HTTP2="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/" 2>/dev/null || echo 000)"
  if [[ "${HTTP2}" == "200" ]]; then
    break
  fi
done

if [[ "${HTTP2}" != "200" ]] && [[ -f "${TOOL_SERVER}" ]]; then
  echo "WARN: :${PORT} did not recover after restart API — relaunching ${EVENT_ID} server"
  nohup python3 "${TOOL_SERVER}" \
    --event-dir "${DROPBOX_PROD}/${EVENT_ID}" \
    --storyboard storyboard_v59_prod.html \
    --event-id "${EVENT_ID}" \
    --port "${PORT}" >> "${LOG}" 2>&1 &
  for _i in $(seq 1 20); do
    sleep 2
    HTTP2="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/" 2>/dev/null || echo 000)"
    if [[ "${HTTP2}" == "200" ]]; then
      break
    fi
  done
fi

if [[ "${HTTP2}" != "200" ]]; then
  echo "FATAL: server down after restart (HTTP ${HTTP2})" >&2
  exit 1
fi

if [[ -f "${DB}" ]]; then
  INTEGRITY2="$(sqlite3 "${DB}" 'PRAGMA integrity_check;' 2>&1 || true)"
  COUNT2="$(sqlite3 "${DB}" 'SELECT COUNT(*) FROM beats;' 2>&1 || echo 0)"
  echo "after restart: integrity=${INTEGRITY2} beats=${COUNT2}"
  if [[ "${INTEGRITY2}" != "ok" ]]; then
    echo "FATAL: beatgen.db integrity_check failed after restart: ${INTEGRITY2}" >&2
    exit 1
  fi
fi

# Event intro session-state (dedicated port)
INTRO_STATE="$(curl -s "${BASE}/api/bg/session-state?scope_event_id=${EVENT_ID}&scope_video_role=intro")"
INTRO_BEATS="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('beats') or []))" <<<"${INTRO_STATE}")"
INTRO_ERR="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error_message') or '')" <<<"${INTRO_STATE}")"
echo "event intro session-state beats=${INTRO_BEATS} error=${INTRO_ERR:-none}"
if [[ "${INTRO_BEATS}" -lt 1 ]] && [[ "${EVENT_ID}" != "Event_4" ]]; then
  echo "FATAL: ${EVENT_ID} intro Beat Gen empty after restart" >&2
  exit 1
fi
if [[ -n "${INTRO_ERR}" ]]; then
  echo "FATAL: intro session-state error: ${INTRO_ERR}" >&2
  exit 1
fi

# S3: warn on orphan kling clips (disk without sidecar pointer) — ops visibility only
EVENT_DIR="${DROPBOX_PROD}/${EVENT_ID}"
if [[ -d "${EVENT_DIR}/kling_o3_clips" ]]; then
  ORPHANS="$(PYTHONPATH="${SCRIPT_DIR}/../tools:${SCRIPT_DIR}/../:${HOME}/Projects/mindfulnest-tooling/Production/tools" \
    python3 -c "
import json, os, sqlite3, sys
from pathlib import Path
from beatgen_sidecar_health import find_orphan_kling_clips
event_dir = Path(sys.argv[1])
db = Path(os.path.expanduser(sys.argv[2]))
known = set()
if db.is_file():
    con = sqlite3.connect(str(db))
    for (blob,) in con.execute('SELECT beat_json FROM beats'):
        try:
            b = json.loads(blob)
        except Exception:
            continue
        vp = b.get('kling_o3_video_path') or ''
        if vp:
            known.add(str(Path(vp).expanduser().resolve()))
        for o in b.get('kling_o3_options') or []:
            if isinstance(o, dict) and o.get('video_path'):
                known.add(str(Path(o['video_path']).expanduser().resolve()))
    con.close()
orphans = find_orphan_kling_clips(event_dir, sidecar_paths=known)
for p in orphans[:5]:
    print(p)
" "${EVENT_DIR}" "${DB}" 2>/dev/null || true)"
  if [[ -n "${ORPHANS}" ]]; then
    echo "WARN: orphan kling_o3_clips (not in sidecar/db):"
    echo "${ORPHANS}"
  fi
fi

# Omni default — no avatar_pro on intro beats when Avatar disabled (server env pin)
curl -sf "${BASE}/api/bg/session-state?scope_event_id=${EVENT_ID}&scope_video_role=intro" \
  | python3 -c "
import json, os, sys
d = json.load(sys.stdin)
avatar_disabled = os.environ.get('MN_BEATGEN_AVATAR_DISABLED', '1').strip().lower() not in ('0', 'false', 'no')
if avatar_disabled:
    for b in d.get('beats') or []:
        if (b.get('o3_generate_mode') or '').strip() == 'avatar_pro':
            sys.exit(f'FATAL: avatar_pro beat on intro when Avatar disabled: {b.get(\"beat_id\")}')
"

# Milestone user path — load milestone scope first (event scope returns video_role_invalid)
if [[ "${PORT}" == "5112" ]]; then
  MS_LOAD="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE}/api/milestones/load" \
    -H "Content-Type: application/json" \
    -d '{"milestone_id":"milestone1_arc1"}' || echo 000)"
  if [[ "${MS_LOAD}" == "200" ]]; then
    STATE="$(curl -s "${BASE}/api/bg/session-state?scope_event_id=Event_2&scope_milestone_id=milestone1_arc1&scope_type=milestone&scope_video_role=full&scope_arc_number=1&scope_phase=full")"
    BEATS="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('beats') or []))" <<<"${STATE}")"
    ERR="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error_message') or '')" <<<"${STATE}")"
    echo "milestone session-state beats=${BEATS} error=${ERR:-none}"
    if [[ "${BEATS}" -lt 1 ]]; then
      echo "FATAL: milestone Beat Gen empty after restart" >&2
      exit 1
    fi
    if [[ -n "${ERR}" ]]; then
      echo "FATAL: milestone session-state error: ${ERR}" >&2
      exit 1
    fi
  else
    echo "WARN: milestone load HTTP ${MS_LOAD} — skip milestone beat check"
  fi
  curl -s -X POST "${BASE}/api/event/load" \
    -H "Content-Type: application/json" \
    -d '{"event_id":"Event_2"}' >/dev/null || true
fi

echo "OK: beatgen deploy smoke passed (${EVENT_ID} :${PORT})"

#!/usr/bin/env bash
# restore_beatgen_event_snapshot.sh — S4 (H7) per-event beatgen SQLite restore.
#
# Usage:
#   bash Production/scripts/restore_beatgen_event_snapshot.sh Event_3 [latest|YYYY-MM-DD_HHMMSSZ]
#
# Restores from Production/Event_N/.backups/state/*_beatgen_beatgen_eventN.db
# Sets MN_BEATGEN_DB_PATH before any bootstrap (fail-closed shard pin).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

EVENT_ID="${1:?Event_id required e.g. Event_3}"
WHEN="${2:-latest}"
EVENT_SLUG="$(python3 -c "import sys; print(''.join(sys.argv[1].split('_')).lower())" "${EVENT_ID}")"
PORT="$(event_server_port "${EVENT_ID}")"

DROPBOX_PROD="${MN_DROPBOX_PRODUCTION:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}"
EVENT_DIR="${DROPBOX_PROD}/${EVENT_ID}"
BACKUPS="${EVENT_DIR}/.backups/state"
TARGET_DB="${MN_BEATGEN_DB_PATH:-${HOME}/.mindfulnest/state/beatgen_${EVENT_SLUG}.db}"

if [[ ! -d "${BACKUPS}" ]]; then
  echo "FATAL: no backups dir ${BACKUPS}" >&2
  exit 1
fi

if [[ "${WHEN}" == "latest" ]]; then
  SRC="$(ls -t "${BACKUPS}"/*_beatgen_beatgen_${EVENT_SLUG}.db 2>/dev/null | head -1 || true)"
else
  SRC="${BACKUPS}/${WHEN}_beatgen_beatgen_${EVENT_SLUG}.db"
fi

if [[ -z "${SRC}" || ! -f "${SRC}" ]]; then
  echo "FATAL: beatgen backup not found for ${EVENT_ID} (when=${WHEN})" >&2
  exit 1
fi

mkdir -p "$(dirname "${TARGET_DB}")"
cp -f "${SRC}" "${TARGET_DB}"
chmod 600 "${TARGET_DB}" 2>/dev/null || true

echo "restored ${SRC} -> ${TARGET_DB}"

export MN_BEATGEN_DB_PATH="${TARGET_DB}"
export MN_SIDECAR_ALLOW_FULL_REPLACE=1

HTTP="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" 2>/dev/null || echo 000)"
if [[ "${HTTP}" == "200" ]]; then
  curl -s -X POST "http://127.0.0.1:${PORT}/api/server/restart" >/dev/null || true
  for _ in $(seq 1 20); do
    sleep 2
    HTTP="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" 2>/dev/null || echo 000)"
    [[ "${HTTP}" == "200" ]] && break
  done
fi

if [[ "${HTTP}" != "200" ]]; then
  echo "WARN: server :${PORT} not up — restore copied; restart launchd manually" >&2
  exit 0
fi

bash "${SCRIPT_DIR}/verify_beatgen_deploy_smoke.sh" "${PORT}"
echo "[restore_beatgen_event_snapshot] OK — ${EVENT_ID} on :${PORT}"

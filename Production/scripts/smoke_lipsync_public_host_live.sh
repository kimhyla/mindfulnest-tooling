#!/usr/bin/env bash
# smoke_lipsync_public_host_live.sh — live proof that Event servers expose lipsync host readiness
#
# Default: informational (passes when R2 not yet configured — reports ready=false).
# Strict:  MN_LIPSYNC_SMOKE_STRICT=1 → fail unless lipsync_public_host_ready=true on all ports.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
PYTHON="${MN_PYTHON:-${HOME}/.pyenv/versions/3.12.7/bin/python3}"
STRICT="${MN_LIPSYNC_SMOKE_STRICT:-0}"
EVENTS=(Event_1 Event_2 Event_4)

fail() { echo "[lipsync-smoke] FAIL: $1" >&2; exit 1; }

echo "[lipsync-smoke] credential probe (Dropbox load_credentials)..."
CREDS_JSON="$("$PYTHON" - <<PY
import json, sys
sys.path.insert(0, "${DROPBOX}/Production/tools")
sys.path.insert(0, "${DROPBOX}/Production/tools/credentials_lib")
from credentials import load_credentials
from lipsync_public_host import probe_lipsync_public_host_capabilities
c = load_credentials()
print(json.dumps({"creds_r2": probe_lipsync_public_host_capabilities(creds=c)}))
PY
)"
echo "  load_credentials → $(printf '%s' "$CREDS_JSON" | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin)["creds_r2"]; print("ready="+str(d.get("lipsync_public_host_ready")), "r2="+str(d.get("lipsync_r2_configured")))')"

all_ready=1
for event_id in "${EVENTS[@]}"; do
  port="$(event_id_to_port "$event_id")"
  url="http://localhost:${port}/api/bg/session-state?scope_event_id=${event_id}&scope_video_role=intro"
  body="$(curl -sS --max-time 15 "$url" 2>/dev/null || true)"
  if [[ -z "$body" ]]; then
    fail "${event_id} :${port} session-state empty (server down?)"
  fi
  read -r ready r2 msg <<<"$("$PYTHON" -c "
import json, sys
d = json.loads(sys.argv[1])
cap = d.get('capabilities') or {}
ready = cap.get('lipsync_public_host_ready')
r2 = cap.get('lipsync_r2_configured')
msg = cap.get('lipsync_public_host_message') or ''
print('true' if ready else 'false', 'true' if r2 else 'false', msg.replace('\n',' ')[:120])
" "$body")"
  echo "  ${event_id} :${port} → lipsync_public_host_ready=${ready} r2_configured=${r2}"
  if [[ "$ready" != "true" ]]; then
    all_ready=0
    if [[ -n "$msg" && "$msg" != "None" ]]; then
      echo "    message: ${msg}"
    fi
  fi
  if [[ "$ready" != "true" && "$STRICT" == "1" ]]; then
    fail "${event_id} :${port} lipsync_public_host_ready=false (strict mode)"
  fi
done

if [[ "$STRICT" == "1" && "$all_ready" == "1" ]]; then
  echo "[lipsync-smoke] R2 upload probe (PUT)..."
  UPLOAD_JSON="$("$PYTHON" - <<PY
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, "${DROPBOX}/Production/scripts")
import r2_upload
path = Path(tempfile.mkstemp(suffix=".bin")[1])
path.write_bytes(b"lipsync-smoke-probe")
result = r2_upload.upload(path, "lipsync-smoke/probe.bin", "application/octet-stream", "public, max-age=3600", log=False)
print(json.dumps({"status": result.get("status"), "key": result.get("key")}))
PY
  )"
  echo "  r2_upload.upload → ${UPLOAD_JSON}"
  if [[ -n "${MN_R2_CDN_BASE_URL:-}" ]]; then
    pub_url="${MN_R2_CDN_BASE_URL%/}/lipsync-smoke/probe.bin"
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 20 "$pub_url" 2>/dev/null || echo "000")"
    echo "  CDN GET ${pub_url} → HTTP ${code}"
    if [[ "$code" != "200" && "$code" != "206" ]]; then
      fail "CDN public GET returned HTTP ${code}"
    fi
  fi
fi

if [[ "$all_ready" == "1" ]]; then
  echo "[lipsync-smoke] OK — lipsync public host ready on all Event servers"
else
  echo "[lipsync-smoke] OK (informational) — R2 not configured; ready=false as expected"
fi

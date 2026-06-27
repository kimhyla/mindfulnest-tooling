#!/usr/bin/env bash
# verify_deploy_option_b_live.sh — post-deploy multipass proof (STORYBOARD_OPTION_B_V1).
#
# Verifies with positive evidence (no assumed state):
#   1) tooling↔Dropbox parity
#   2) Dropbox storyboard HTML build-sha == git HEAD
#   3) live server build-sha == git HEAD on dedicated event port
#   4) HTTP 200 + event/load pin
#   5) UI-visible app-build-sha marker in served HTML
#   6) X-Tooling-Sha on API responses == git HEAD
#   7) O3 session-state busy inventory (job_busy + job_id contract)
#
# Usage:
#   bash Production/scripts/verify_deploy_option_b_live.sh --event Event_2
#   MN_EVENT_ID=Event_2 bash Production/scripts/verify_deploy_option_b_live.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

SRC_TOOLING="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DEST_DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"

EVENT_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --event)
      EVENT_ID="${2#Event_}"
      EVENT_ID="Event_${EVENT_ID#Event_}"
      shift 2
      ;;
    --event=*)
      EVENT_ID="${1#--event=}"
      [[ "$EVENT_ID" == Event_* ]] || EVENT_ID="Event_${EVENT_ID}"
      shift
      ;;
    *)
      echo "FATAL: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$EVENT_ID" ]]; then
  EVENT_ID="${MN_EVENT_ID:-}"
fi
if [[ -z "$EVENT_ID" ]]; then
  PIN_FILE="$DEST_DROPBOX/Production/server_event_pin.json"
  if [[ -f "$PIN_FILE" ]]; then
    EVENT_ID="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print((d.get('event_id') or '').strip())" "$PIN_FILE" 2>/dev/null || true)"
  fi
fi
EVENT_ID="${EVENT_ID:-Event_1}"

PORT="${MN_SERVER_PORT:-$(event_id_to_port "$EVENT_ID")}"
EVENT_DIR="$DEST_DROPBOX/Production/${EVENT_ID}"
STORYBOARD_HTML="$EVENT_DIR/storyboard_v59_prod.html"
BASE_URL="http://localhost:${PORT}/"
HEAD_SHA="$(cd "$SRC_TOOLING" && git rev-parse --short HEAD)"

fail() {
  echo "[verify_option_b] FATAL: $1" >&2
  exit 1
}

echo "[verify_option_b] event=$EVENT_ID port=$PORT HEAD=$HEAD_SHA"

echo "[verify_option_b] (1/5) tooling↔Dropbox parity ..."
MN_TOOLING_ROOT="$SRC_TOOLING" MN_DROPBOX_ROOT="$DEST_DROPBOX" \
  python3 "$SRC_TOOLING/Production/scripts/verify_tooling_dropbox_parity.py" \
  || fail "parity check failed"

echo "[verify_option_b] (2/5) Dropbox storyboard build-sha ..."
[[ -f "$STORYBOARD_HTML" ]] || fail "missing $STORYBOARD_HTML"
DROPBOX_SHA="$(python3 - <<PY
import re, pathlib
html = pathlib.Path("${STORYBOARD_HTML}").read_text(encoding="utf-8", errors="replace")
m = re.search(r'name="build-sha" content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
)"
[[ -n "$DROPBOX_SHA" ]] || fail "Dropbox HTML missing build-sha meta"
[[ "$DROPBOX_SHA" == "$HEAD_SHA" ]] || fail "Dropbox build-sha $DROPBOX_SHA != HEAD $HEAD_SHA"
echo "  Dropbox HTML build-sha=$DROPBOX_SHA OK"

echo "[verify_option_b] (3/5) live server HTTP + build-sha ..."
HTTP_CODE="$(curl -sS -o /tmp/mn_option_b_served.html -w "%{http_code}" --max-time 15 "$BASE_URL" || echo "000")"
[[ "$HTTP_CODE" == "200" ]] || fail "GET $BASE_URL returned HTTP $HTTP_CODE"
LIVE_SHA="$(python3 - <<'PY'
import re, pathlib
html = pathlib.Path("/tmp/mn_option_b_served.html").read_text(encoding="utf-8", errors="replace")
m = re.search(r'name="build-sha" content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
)"
[[ -n "$LIVE_SHA" ]] || fail "live HTML missing build-sha meta"
[[ "$LIVE_SHA" == "$HEAD_SHA" ]] || fail "live build-sha $LIVE_SHA != HEAD $HEAD_SHA"
MARKER_OK="$(python3 -c "import re,pathlib;html=pathlib.Path('/tmp/mn_option_b_served.html').read_text(encoding='utf-8',errors='replace');pat=re.compile(r'data-testid[\"\\x27]?\\s*[=:]\\s*[\"\\x27]app-build-sha[\"\\x27]');print('1' if pat.search(html) else '0')")"
[[ "$MARKER_OK" == "1" ]] || fail "served HTML missing data-testid=app-build-sha"
echo "  live build-sha=$LIVE_SHA app-build-sha marker OK"

echo "[verify_option_b] (4/5) event/load pin ..."
LOAD_HTTP="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 \
  -X POST "${BASE_URL}api/event/load" \
  -H "Content-Type: application/json" \
  -d "{\"event_id\":\"${EVENT_ID}\"}" || echo "000")"
[[ "$LOAD_HTTP" == "200" ]] || fail "POST /api/event/load returned HTTP $LOAD_HTTP"

echo "[verify_option_b] (5/7) stitcher durability markers in bundle ..."
grep -q 'STITCH_SLOT_REQUIRES_MUXED_PREVIEW_V1' /tmp/mn_option_b_served.html \
  || fail "missing STITCH_SLOT_REQUIRES_MUXED_PREVIEW_V1 in served HTML"
grep -q 'STITCH_SLOT_MUX_AUDIO_SIG_V1' /tmp/mn_option_b_served.html \
  || fail "missing STITCH_SLOT_MUX_AUDIO_SIG_V1 in served HTML"

echo "[verify_option_b] (6/7) Python X-Tooling-Sha ..."
PY_SHA="$(curl -sS -D /tmp/mn_option_b_headers.txt -o /dev/null --max-time 15 \
  -X POST "${BASE_URL}api/event/load" \
  -H "Content-Type: application/json" \
  -d "{\"event_id\":\"${EVENT_ID}\"}" \
  && python3 - <<'PY'
import re, pathlib
text = pathlib.Path("/tmp/mn_option_b_headers.txt").read_text(encoding="utf-8", errors="replace")
m = re.search(r"(?i)x-tooling-sha:\s*(\S+)", text)
print(m.group(1) if m else "")
PY
)"
[[ -n "$PY_SHA" ]] || fail "missing X-Tooling-Sha response header"
[[ "$PY_SHA" == "$HEAD_SHA" ]] || fail "X-Tooling-Sha $PY_SHA != HEAD $HEAD_SHA"
echo "  X-Tooling-Sha=$PY_SHA OK"

echo "[verify_option_b] (7/7) O3 busy inventory post-restart ..."
SESSION_URL="${BASE_URL}api/bg/session-state?scope_event_id=${EVENT_ID}&scope_video_role=resolution"
python3 - <<PY
import json, sys, urllib.request
url = "${SESSION_URL}"
try:
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = json.load(resp)
except Exception as exc:
    sys.exit(f"FATAL: session-state fetch failed: {exc}")
beats = data.get("beats") or []
busy = [b for b in beats if b.get("job_busy") is True]
for b in busy:
    jid = (b.get("o3_current_job_id") or "").strip()
    if not jid:
        sys.exit(f"FATAL: job_busy true without o3_current_job_id on {b.get('beat_id')}")
print(f"  session-state beats={len(beats)} job_busy={len(busy)} OK")
PY

echo ""
echo "=== STORYBOARD_OPTION_B_V1 PROOF ==="
echo "  event:        $EVENT_ID"
echo "  url:          ${BASE_URL}?event=${EVENT_ID}"
echo "  port:         $PORT"
echo "  git HEAD:     $HEAD_SHA"
echo "  dropbox sha:  $DROPBOX_SHA"
echo "  live sha:     $LIVE_SHA"
echo "  python sha:   $PY_SHA"
echo "  parity:       OK"
echo "  event/load:   HTTP 200"
echo "=== verify_deploy_option_b_live: ALL PASSED ==="

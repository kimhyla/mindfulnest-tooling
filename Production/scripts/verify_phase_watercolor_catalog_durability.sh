#!/usr/bin/env bash
# verify_phase_watercolor_catalog_durability.sh — merged watercolor catalog + URL contract.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PORT="${MN_SERVER_PORT:-5112}"
BASE="http://localhost:${PORT}"
EVENT="${MN_WATERCOLOR_SMOKE_EVENT:-Event_2}"

fail() { echo "[phase-watercolor-durability] FATAL: $*" >&2; exit 1; }

echo "[phase-watercolor-durability] unit tests..."
(cd "${TOOLING}/Production/tools" && python3 -m pytest \
  tests/test_watercolor_assets.py \
  tests/test_phase_b_watercolor_serve.py -q) || fail "pytest failed"

echo "[phase-watercolor-durability] server HTTP..."
curl -sf "${BASE}/" >/dev/null || fail "server not up on ${BASE}"

BUILD_SHA="$(curl -sf "${BASE}/" | rg -o 'build [a-f0-9]{7,40}' -m1 | awk '{print $2}' || true)"
HEAD_SHA="$(cd "${TOOLING}" && git rev-parse --short HEAD)"
if [[ -n "${BUILD_SHA}" && "${BUILD_SHA}" != "${HEAD_SHA}" ]]; then
  echo "[phase-watercolor-durability] WARN build-sha ${BUILD_SHA} != HEAD ${HEAD_SHA} (deploy/restart may be pending)"
fi

echo "[phase-watercolor-durability] cr_library watercolor rows..."
WC_ROWS="$(curl -sf "${BASE}/api/cr/library?event_id=${EVENT}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
imgs = d.get('images') or []
print(sum(1 for i in imgs if i.get('tier') == 'watercolor'))
")"
PHASE_COUNT="$(curl -sf "${BASE}/api/phase/watercolor_list" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))")"
[[ "${WC_ROWS}" -gt 0 ]] || fail "cr_library watercolor tier empty (phase count=${PHASE_COUNT})"
[[ "${WC_ROWS}" == "${PHASE_COUNT}" ]] || fail "catalog mismatch cr=${WC_ROWS} phase=${PHASE_COUNT}"

KEY="$(curl -sf "${BASE}/api/phase/watercolor_list" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('items') or []
print(items[0]['key'] if items else '')
")"
[[ -n "${KEY}" ]] || fail "no watercolor key in phase list"

ENC="$(python3 -c "import urllib.parse; print(urllib.parse.quote('''${KEY}'''))")"
HTTP="$(curl -s -o /tmp/mn_wc_durability.bin -w '%{http_code}' "${BASE}/api/phase_b/watercolor/${ENC}")"
[[ "${HTTP}" == "200" ]] || fail "phase_b/watercolor HTTP ${HTTP} for key=${KEY}"
[[ "$(wc -c < /tmp/mn_wc_durability.bin)" -gt 100 ]] || fail "empty watercolor body"

THUMB="$(curl -sf "${BASE}/api/phase/watercolor_list" | python3 -c "
import sys, json
print((json.load(sys.stdin).get('items') or [{}])[0].get('thumb_url',''))
")"
curl -sf "${BASE}${THUMB}" >/dev/null || fail "thumb_url fetch failed: ${THUMB}"

echo "[phase-watercolor-durability] OK — cr_library watercolors=${WC_ROWS} serve=200 thumb=200"

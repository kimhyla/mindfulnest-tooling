#!/usr/bin/env bash
# verify_event_catalog_invariants_durability.sh — EVENT_CATALOG_INVARIANTS_V1 (G3 / RC13)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PORT="${MN_SERVER_PORT:-5114}"
BASE="http://localhost:${PORT}"
EVENT="${MN_CATALOG_EVENT:-Event_4}"
MIN_WC="${MN_WATERCOLOR_MIN_COUNT:-1}"

fail() { echo "[event-catalog-invariants] FATAL: $*" >&2; exit 1; }

echo "[event-catalog-invariants] disk bootstrap check for ${EVENT} ..."
python3 "${SCRIPT_DIR}/bootstrap_event_watercolors.py" --event "${EVENT}" \
  || fail "bootstrap_event_watercolors failed"

WC_DIR="${MN_EVENT_DIR:-}"
if [[ -z "$WC_DIR" ]]; then
  DROPBOX="${MN_DROPBOX_ROOT:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
  WC_DIR="${DROPBOX}/Production/${EVENT}/library/watercolors"
fi
[[ -d "$WC_DIR" ]] || fail "watercolors dir missing: $WC_DIR"
WC_FILES="$(find "$WC_DIR" -maxdepth 1 -type f \( -name '*.png' -o -name '*.webp' -o -name '*.mov' -o -name '*.mp4' \) 2>/dev/null | wc -l | tr -d ' ')"
[[ "${WC_FILES}" -ge "${MIN_WC}" ]] || fail "disk watercolors empty (${WC_FILES} files in ${WC_DIR})"

curl -sf "${BASE}/" >/dev/null || fail "server not up on ${BASE}"

echo "[event-catalog-invariants] HTTP parity cr_library vs phase/watercolor_list ..."
WC_ROWS="$(curl -sf "${BASE}/api/cr/library?event_id=${EVENT}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
imgs = d.get('images') or []
print(sum(1 for i in imgs if i.get('tier') == 'watercolor'))
")"
PHASE_COUNT="$(curl -sf "${BASE}/api/phase/watercolor_list" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))")"
[[ "${WC_ROWS}" -ge "${MIN_WC}" ]] || fail "cr_library watercolor tier empty (${WC_ROWS})"
[[ "${WC_ROWS}" == "${PHASE_COUNT}" ]] || fail "catalog mismatch cr=${WC_ROWS} phase=${PHASE_COUNT}"

LIB_PANEL="$TOOLING/Production/tools/storyboard-v2/src/components/LibraryPanel.tsx"
grep -q 'mn.library.items.v4' "$LIB_PANEL" || fail "LibraryPanel cache key must be v4"
grep -q 'phase_watercolor_list' "$LIB_PANEL" || fail "LibraryPanel must reconcile phase watercolor count (G3)"

echo "[event-catalog-invariants] OK — ${EVENT} disk=${WC_FILES} cr=${WC_ROWS} phase=${PHASE_COUNT}"

#!/usr/bin/env bash
# verify_library_panel_contract_durability.sh — LIBRARY_PANEL_CLASSIFICATION_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONTRACT="${REPO_ROOT}/Production/lib/library_panel_contract.py"
CROPPER="${REPO_ROOT}/Production/tools/server_handlers/cropper.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_library_panel_contract.py"
SPEC="${REPO_ROOT}/Production/docs/TECH_SPEC_LIBRARY_PANEL_CLASSIFICATION_V1.md"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

fail() { echo "[library-panel-contract] FAIL: $1" >&2; exit 1; }

[[ -f "$CONTRACT" ]] || fail "missing library_panel_contract.py"
[[ -f "$CROPPER" ]] || fail "missing cropper.py"
[[ -f "$TEST" ]] || fail "missing test_library_panel_contract.py"
[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_LIBRARY_PANEL_CLASSIFICATION_V1.md"

grep -q 'attach_panel_tabs_all' "$CROPPER" \
  || fail "cropper must attach panel_tabs on cr_library rows"
grep -q 'prod_asset_type' "$CROPPER" \
  || fail "Directus enrich must not overwrite disk-scan asset_type"
grep -q 'libraryItemMatchesPanelTab' \
  "${REPO_ROOT}/Production/tools/storyboard-v2/src/components/LibraryPanel.tsx" \
  || fail "LibraryPanel must filter on panel_tabs contract"

python3 -m pytest "$TEST" -q

check_port() {
  local event_id="$1"
  local port
  port="$(event_id_to_port "$event_id")"
  if ! curl -sf --max-time 5 "http://localhost:${port}/api/event/current" >/dev/null 2>&1; then
    echo "[library-panel-contract] SKIP live — :${port} (${event_id}) down"
    return 0
  fi
  local head_sha served_sha
  head_sha="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
  served_sha="$(curl -sf --max-time 10 "http://localhost:${port}/" \
    | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p' | head -1)"
  if [[ -n "$head_sha" && -n "$served_sha" && "$served_sha" != "$head_sha" ]]; then
    echo "[library-panel-contract] SKIP live — :${port} (${event_id}) build-sha=${served_sha} != HEAD=${head_sha}"
    return 0
  fi
  local body filtered_body
  body="$(event_curl_json "http://localhost:${port}/api/cr/library?event_id=${event_id}")" \
    || return 1
  filtered_body="$(event_curl_json "http://localhost:${port}/api/cr/library?event_id=${event_id}&panel=images")" \
    || return 1
  python3 -c "
import json, sys
d = json.loads(sys.argv[1])
items = d.get('images') or []
if not items:
    print('skip_empty')
    sys.exit(0)
missing = [i for i in items if not i.get('panel_tabs')]
if missing:
    raise SystemExit(f'{len(missing)} rows missing panel_tabs')
images_count = sum(1 for i in items if 'images' in (i.get('panel_tabs') or []))
if images_count < 1:
    raise SystemExit(f'zero images-tab rows (total={len(items)})')
filtered = json.loads(sys.argv[2])
fitems = filtered.get('images') or []
if filtered.get('panel_filter') != 'images':
    raise SystemExit('panel_filter missing on ?panel=images response')
if fitems and not all('images' in (i.get('panel_tabs') or []) for i in fitems):
    raise SystemExit('panel=images returned non-images rows')
print(f'ok total={len(items)} images_tab={images_count} filtered={len(fitems)}')
" "$body" "$filtered_body" || return 1
  echo "[library-panel-contract] OK live ${event_id} :${port}"
}

for ev in Event_1 Event_2 Event_3 Event_4; do
  if [[ -n "${MN_LIBRARY_PANEL_LIVE_EVENT:-}" && "$ev" != "$MN_LIBRARY_PANEL_LIVE_EVENT" ]]; then
    continue
  fi
  check_port "$ev" || fail "live check failed for $ev"
done

echo "[library-panel-contract] OK — pytest + source guards + live panel_tabs"

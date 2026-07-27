#!/usr/bin/env bash
# verify_storyboard_fleet_bundle_parity.sh — STORYBOARD_FLEET_BUNDLE_PARITY_V1
#
# Every Production/Event_N/storyboard_v59_prod.html fanout and every live dedicated
# port must match git HEAD build-sha and carry waveform drag-seek durability markers
# (WTA + WAVEFORM_DRAG_SEEK_V2) on all Phase A/B waveforms.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

ROOT="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
DIST="${ROOT}/Production/tools/storyboard-v2/dist/index.html"

HEAD="${MN_EXPECT_BUILD_SHA:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)}"
[[ -n "$HEAD" ]] || { echo "[fleet-bundle-parity] FATAL: cannot resolve HEAD build-sha" >&2; exit 1; }
[[ -f "$DIST" ]] || { echo "[fleet-bundle-parity] FATAL: missing dist/index.html" >&2; exit 1; }

CANONICAL_SHA="$(shasum -a 256 "$DIST" | awk '{print $1}')"

fail() { echo "[fleet-bundle-parity] FATAL: $1" >&2; exit 1; }

read_build_sha() {
  python3 - "$1" <<'PY'
import re, sys
html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r'name="build-sha"\s+content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
}

check_waveform_markers_file() {
  local label="$1"
  local path="$2"
  grep -q 'resolvePausedPlayheadMs' "$path" \
    || fail "${label} missing resolvePausedPlayheadMs (WTA)"
  grep -q 'WAVEFORM_DRAG_SEEK_V2' "$path" \
    || fail "${label} missing WAVEFORM_DRAG_SEEK_V2 drag-seek bind marker"
  grep -q 'WAVEFORM_DROP_CAPTURE_V1' "$path" \
    || fail "${label} missing WAVEFORM_DROP_CAPTURE_V1 drop marker"
}

check_waveform_markers_html() {
  local label="$1"
  local path="$2"
  grep -q 'resolvePausedPlayheadMs' "$path" \
    || fail "${label} missing resolvePausedPlayheadMs (WTA)"
  grep -q 'WAVEFORM_DRAG_SEEK_V2' "$path" \
    || fail "${label} missing WAVEFORM_DRAG_SEEK_V2 drag-seek bind marker"
  grep -q 'WAVEFORM_DROP_CAPTURE_V1' "$path" \
    || fail "${label} missing WAVEFORM_DROP_CAPTURE_V1 drop marker"
}

FLEET_EVENTS=(Event_1 Event_2 Event_3 Event_4 Event_5 Event_6 Event_7)
fanout_count=0

echo "[fleet-bundle-parity] HEAD=${HEAD} canonical_sha256=${CANONICAL_SHA:0:12}..."

for event_id in "${FLEET_EVENTS[@]}"; do
  html="${DROPBOX}/Production/${event_id}/storyboard_v59_prod.html"
  [[ -f "$html" ]] || continue
  fanout_sha="$(shasum -a 256 "$html" | awk '{print $1}')"
  [[ "$fanout_sha" == "$CANONICAL_SHA" ]] \
    || fail "${event_id} Dropbox fanout sha256 mismatch (stale partial deploy)"
  build="$(read_build_sha "$html")"
  [[ -n "$build" ]] || fail "${event_id} fanout missing build-sha meta"
  [[ "$build" == "$HEAD" ]] \
    || fail "${event_id} fanout build-sha=${build} != HEAD=${HEAD}"
  check_waveform_markers_file "${event_id} fanout" "$html"
  fanout_count=$((fanout_count + 1))
  echo "[fleet-bundle-parity] Dropbox ${event_id} ok (build-sha=${build})"
done
[[ "$fanout_count" -ge 1 ]] || fail "no Event_* fanout files found under Dropbox"

live_count=0
live_tmp="$(mktemp -t mn-fleet-parity.XXXXXX)"
trap 'rm -f "$live_tmp"' EXIT
for event_id in "${FLEET_EVENTS[@]}"; do
  port="$(event_id_to_port "$event_id")" || continue
  [[ -d "${DROPBOX}/Production/${event_id}" ]] || continue
  if ! curl -sf --max-time 5 "http://localhost:${port}/api/event/current" >/dev/null 2>&1; then
    fail ":${port} ${event_id} server down after fleet restart (required for parity)"
  fi
  if ! curl -sf --max-time 30 "http://localhost:${port}/" >"$live_tmp" 2>/dev/null; then
    fail ":${port} ${event_id} failed to fetch served HTML"
  fi
  [[ -s "$live_tmp" ]] || fail ":${port} ${event_id} served empty HTML"
  build="$(read_build_sha "$live_tmp")"
  [[ -n "$build" ]] || fail ":${port} ${event_id} served HTML missing build-sha"
  [[ "$build" == "$HEAD" ]] \
    || fail ":${port} ${event_id} live build-sha=${build} != HEAD=${HEAD}"
  check_waveform_markers_html ":${port} ${event_id} live" "$live_tmp"
  live_count=$((live_count + 1))
  echo "[fleet-bundle-parity] live :${port} ${event_id} ok (build-sha=${build})"
done
[[ "$live_count" -ge 1 ]] || fail "no live dedicated ports responded"

echo "[fleet-bundle-parity] OK — fanout=${fanout_count} live=${live_count} HEAD=${HEAD}"

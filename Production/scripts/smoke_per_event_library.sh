#!/usr/bin/env bash
# Multipass smoke: per-event library scoping + metadata-only list + on-demand thumbs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

if [[ -n "${MN_STORYBOARD_BASE:-}" ]]; then
  BASE="${MN_STORYBOARD_BASE}"
elif [[ -n "${MN_SERVER_PORT:-}" ]]; then
  BASE="http://localhost:${MN_SERVER_PORT}"
elif [[ -n "${MN_EVENT_ID:-}" ]]; then
  BASE="http://localhost:$(event_id_to_port "$MN_EVENT_ID")"
else
  BASE="http://localhost:5111"
fi

load_event() {
  local ev="$1"
  local attempt
  for attempt in 1 2 3; do
    if curl -sf --max-time 30 -X POST "$BASE/api/event/load" \
      -H 'Content-Type: application/json' \
      -d "{\"event_id\":\"$ev\"}" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "FAIL: event/load $ev failed after 3 attempts (base=$BASE)" >&2
  return 1
}

count_images() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('images',[])))"
}

count_watercolors() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count', len(d.get('items',[]))))"
}

assert_metadata_only_file() {
  python3 - "$1" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
assert d.get("metadata_only") is True, "metadata_only flag missing"
for i in d.get("images", []):
    assert "thumb_b64" not in i, "thumb_b64 must not be in list payload"
    assert "gallery_b64" not in i, "gallery_b64 must not be in list payload"
    if i.get("tier") == "canonical":
        raise SystemExit("canonical tier must not appear in library list")
    if i.get("abs_path"):
        assert i.get("thumb_url"), "abs_path rows need thumb_url"
print("metadata_ok")
PY
}

first_thumb_url_file() {
  python3 - "$1" <<'PY'
import json, sys, urllib.parse
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
for i in d.get("images", []):
    ap = i.get("abs_path")
    if ap:
        print("/api/cr/thumb?abs_path=" + urllib.parse.quote(ap, safe=""))
        break
PY
}

# Emit up to 8 thumb URLs — Dropbox/PIL can fail a single source transiently.
thumb_urls_file() {
  python3 - "$1" <<'PY'
import json, sys, urllib.parse
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
n = 0
for i in d.get("images", []):
    ap = i.get("abs_path")
    if not ap:
        continue
    print("/api/cr/thumb?abs_path=" + urllib.parse.quote(ap, safe=""))
    n += 1
    if n >= 8:
        break
PY
}

probe_thumb_ok() {
  local base="$1"
  local list_file="$2"
  local url http_code
  while IFS= read -r url; do
    [[ -z "$url" ]] && continue
    THUMB_TMP=$(mktemp /tmp/cr_thumb_smoke.XXXXXX)
    http_code=$(curl -s -o "$THUMB_TMP" -w '%{http_code}' --max-time 90 "${base}${url}" || echo 000)
    if [[ "$http_code" == "200" ]] && file "$THUMB_TMP" | grep -qi 'jpeg'; then
      rm -f "$THUMB_TMP"
      echo "thumb endpoint OK ($url)"
      return 0
    fi
    rm -f "$THUMB_TMP"
    echo "WARN: thumb probe failed http=${http_code} ($url)" >&2
  done < <(thumb_urls_file "$list_file")
  echo "FAIL: no library thumb succeeded after probing up to 8 abs_path rows" >&2
  return 1
}

curl_json() {
  # Dropbox File Provider on macOS can take >60s for Event library walks
  # after cold boot / vacation return — keep smoke aligned with that class.
  curl -sf --max-time 120 "$@"
}

cleanup() {
  rm -f ${E1_TMP:+"$E1_TMP"} ${E2_TMP:+"$E2_TMP"} ${E4_TMP:+"$E4_TMP"} ${THUMB_TMP:+"$THUMB_TMP"}
}
trap cleanup EXIT

E1_TMP=""
E2_TMP=""
E4_TMP=""
THUMB_TMP=""

echo "=== per-event library smoke === (base=$BASE)"

PORT_FROM_BASE=""
if [[ "$BASE" =~ :([0-9]+)(/|$) ]]; then
  PORT_FROM_BASE="${BASH_REMATCH[1]}"
fi
DEDICATED_EVENT=""
if [[ -n "$PORT_FROM_BASE" ]] && (( PORT_FROM_BASE >= 5111 )); then
  DEDICATED_EVENT="$(port_to_event_id "$PORT_FROM_BASE" 2>/dev/null || true)"
fi

if [[ -n "$DEDICATED_EVENT" ]]; then
  echo "dedicated port :${PORT_FROM_BASE} → ${DEDICATED_EVENT} (no cross-event event/load)"
  E2_TMP=$(mktemp /tmp/cr_lib_smoke_e2.XXXXXX)
  curl_json "$BASE/api/cr/library?event_id=${DEDICATED_EVENT}" >"$E2_TMP"
  assert_metadata_only_file "$E2_TMP"
  E2_IMAGES=$(cat "$E2_TMP" | count_images)
  E2_WC=$(curl_json "$BASE/api/phase/watercolor_list" | count_watercolors)
  E2_BYTES=$(wc -c <"$E2_TMP" | tr -d ' ')
  echo "${DEDICATED_EVENT} images=$E2_IMAGES watercolors=$E2_WC list_bytes=$E2_BYTES"
  if grep -q '"abs_path"' "$E2_TMP"; then
    probe_thumb_ok "$BASE" "$E2_TMP" || exit 1
  else
    echo "WARN: no abs_path in ${DEDICATED_EVENT} library — skip thumb fetch"
  fi
  SFX=$(curl_json "$BASE/api/stitch_editor/library" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('sfx',[])))")
  echo "shared sfx count=$SFX"
  fail=0
  [[ "$E2_IMAGES" -ge "1" ]] || { echo "FAIL: ${DEDICATED_EVENT} expected >=1 library images, got $E2_IMAGES"; fail=1; }
  [[ "$E2_WC" -ge "0" ]] || { echo "FAIL: ${DEDICATED_EVENT} watercolor count invalid: $E2_WC"; fail=1; }
  [[ "$E2_BYTES" -lt "250000" ]] || { echo "FAIL: ${DEDICATED_EVENT} library JSON too large: $E2_BYTES bytes"; fail=1; }
  [[ "$SFX" -ge "1" ]] || { echo "FAIL: shared sfx library empty"; fail=1; }
  [[ "$fail" -ne 0 ]] && exit 1
  echo "PASS: per-event library smoke (dedicated ${DEDICATED_EVENT})"
  exit 0
fi

load_event Event_1
E1_TMP=$(mktemp /tmp/cr_lib_smoke_e1.XXXXXX)
curl_json "$BASE/api/cr/library?event_id=Event_1" >"$E1_TMP"
assert_metadata_only_file "$E1_TMP"
E1_IMAGES=$(cat "$E1_TMP" | count_images)
E1_WC=$(curl_json "$BASE/api/phase/watercolor_list" | count_watercolors)
E1_BYTES=$(wc -c <"$E1_TMP" | tr -d ' ')
echo "Event_1 images=$E1_IMAGES watercolors=$E1_WC list_bytes=$E1_BYTES"

load_event Event_2
E2_TMP=$(mktemp /tmp/cr_lib_smoke_e2.XXXXXX)
curl_json "$BASE/api/cr/library?event_id=Event_2" >"$E2_TMP"
assert_metadata_only_file "$E2_TMP"
E2_IMAGES=$(cat "$E2_TMP" | count_images)
E2_WC=$(curl_json "$BASE/api/phase/watercolor_list" | count_watercolors)
E2_BYTES=$(wc -c <"$E2_TMP" | tr -d ' ')
echo "Event_2 images=$E2_IMAGES watercolors=$E2_WC list_bytes=$E2_BYTES"

if grep -q '"abs_path"' "$E2_TMP"; then
  probe_thumb_ok "$BASE" "$E2_TMP" || exit 1
else
  echo "WARN: no abs_path in Event_2 library — skip thumb fetch"
fi

# Shared audio unchanged
SFX=$(curl_json "$BASE/api/stitch_editor/library" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('sfx',[])))")
echo "shared sfx count=$SFX"

fail=0
[[ "$E2_IMAGES" -ge "1" ]] || { echo "FAIL: Event_2 expected >=1 library images, got $E2_IMAGES"; fail=1; }
[[ "$E1_IMAGES" -ge "1" ]] || { echo "FAIL: Event_1 expected >=1 library images, got $E1_IMAGES"; fail=1; }
[[ "$E2_WC" -ge "0" ]] || { echo "FAIL: Event_2 watercolor count invalid: $E2_WC"; fail=1; }
[[ "$E1_WC" -ge "0" ]] || { echo "FAIL: Event_1 watercolor count invalid: $E1_WC"; fail=1; }
[[ "$E2_BYTES" -lt "250000" ]] || { echo "FAIL: Event_2 library JSON too large: $E2_BYTES bytes"; fail=1; }
[[ "$E1_BYTES" -lt "250000" ]] || { echo "FAIL: Event_1 library JSON too large: $E1_BYTES bytes"; fail=1; }

load_event Event_4
E4_TMP=$(mktemp /tmp/cr_lib_smoke_e4.XXXXXX)
curl_json "$BASE/api/cr/library?event_id=Event_4" >"$E4_TMP"
assert_metadata_only_file "$E4_TMP"
E4_IMAGES=$(cat "$E4_TMP" | count_images)
E4_BYTES=$(wc -c <"$E4_TMP" | tr -d ' ')
echo "Event_4 images=$E4_IMAGES list_bytes=$E4_BYTES"
[[ "$E4_IMAGES" -ge "1" ]] || { echo "FAIL: Event_4 expected >=1 images, got $E4_IMAGES"; fail=1; }
[[ "$E4_BYTES" -lt "250000" ]] || { echo "FAIL: Event_4 library JSON too large: $E4_BYTES bytes"; fail=1; }

[[ "$SFX" -ge "1" ]] || { echo "FAIL: shared sfx library empty"; fail=1; }

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "PASS: per-event library smoke"

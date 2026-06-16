#!/usr/bin/env bash
# Multipass smoke: per-event library scoping + canonical injection.
set -euo pipefail

BASE="${MN_STORYBOARD_BASE:-http://localhost:5111}"

load_event() {
  local ev="$1"
  curl -sf -X POST "$BASE/api/event/load" \
    -H 'Content-Type: application/json' \
    -d "{\"event_id\":\"$ev\"}" >/dev/null
}

count_images() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('images',[])))"
}

count_watercolors() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count', len(d.get('items',[]))))"
}

canonical_keys() {
  python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(sorted(i.get('key','') for i in d.get('images',[]) if i.get('tier')=='canonical')))"
}

echo "=== per-event library smoke ==="

load_event Event_1
E1_IMAGES=$(curl -sf "$BASE/api/cr/library?event_id=Event_1" | count_images)
E1_WC=$(curl -sf "$BASE/api/phase/watercolor_list" | count_watercolors)
E1_CANON=$(curl -sf "$BASE/api/cr/library?event_id=Event_1" | canonical_keys)
echo "Event_1 images=$E1_IMAGES watercolors=$E1_WC canonical=[$E1_CANON]"

load_event Event_2
E2_IMAGES=$(curl -sf "$BASE/api/cr/library?event_id=Event_2" | count_images)
E2_WC=$(curl -sf "$BASE/api/phase/watercolor_list" | count_watercolors)
E2_CANON=$(curl -sf "$BASE/api/cr/library?event_id=Event_2" | canonical_keys)
echo "Event_2 images=$E2_IMAGES watercolors=$E2_WC canonical=[$E2_CANON]"

# Shared audio unchanged
SFX=$(curl -sf "$BASE/api/stitch_editor/library" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('sfx',[])))")
echo "shared sfx count=$SFX"

fail=0
[[ "$E2_IMAGES" -ge "6" ]] || { echo "FAIL: Event_2 expected >=6 images (canonical baseline), got $E2_IMAGES"; fail=1; }
[[ "$E1_IMAGES" -ge "6" ]] || { echo "FAIL: Event_1 expected >=6 images (canonical baseline), got $E1_IMAGES"; fail=1; }
[[ "$E2_WC" -ge "0" ]] || { echo "FAIL: Event_2 watercolor count invalid: $E2_WC"; fail=1; }
[[ "$E1_WC" -ge "0" ]] || { echo "FAIL: Event_1 watercolor count invalid: $E1_WC"; fail=1; }
[[ "$E1_CANON" == "$E2_CANON" ]] || { echo "FAIL: canonical keys differ Event_1 vs Event_2"; fail=1; }

load_event Event_4
E4_IMAGES=$(curl -sf "$BASE/api/cr/library?event_id=Event_4" | count_images)
E4_CANON=$(curl -sf "$BASE/api/cr/library?event_id=Event_4" | canonical_keys)
echo "Event_4 images=$E4_IMAGES canonical=[$E4_CANON]"
[[ "$E4_IMAGES" -ge "7" ]] || { echo "FAIL: Event_4 expected >=7 images (canonical baseline), got $E4_IMAGES"; fail=1; }
[[ "$E4_CANON" == "$E1_CANON" ]] || { echo "FAIL: Event_4 canonical keys differ from Event_1"; fail=1; }

[[ "$SFX" -ge "1" ]] || { echo "FAIL: shared sfx library empty"; fail=1; }

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "PASS: per-event library smoke"

#!/usr/bin/env bash
# STITCH_DRY_MEDIA_FAIL_LOUD_V1 — silent black Stitcher player must not recur.
# Bug class (Event_3, 2026-07-18): dry_export_path /files Format error on Dropbox
# dataless masters showed black video with no operator banner because inactive
# pool errors were ignored and slot-switch cleared composerVideoError.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SB="$ROOT/Production/tools/storyboard-v2/src"
UTIL="$SB/utils/stitchSlotVideoLoadError.ts"
TAB="$SB/components/StitcherTab.tsx"
TEST="$SB/utils/__tests__/stitchSlotVideoLoadError.test.ts"

fail() { echo "FATAL: $*" >&2; exit 1; }

grep -q "STITCH_DRY_MEDIA_FAIL_LOUD_V1" "$UTIL" \
  || fail "marker missing from stitchSlotVideoLoadError.ts"
grep -q "formatStitchSlotVideoLoadError" "$UTIL" \
  || fail "formatStitchSlotVideoLoadError missing"
grep -q "resolveActiveSlotVideoError" "$UTIL" \
  || fail "resolveActiveSlotVideoError missing"
grep -q "Dropbox File Provider" "$UTIL" \
  || fail "File Provider operator guidance missing"

grep -q "STITCH_DRY_MEDIA_FAIL_LOUD_V1" "$TAB" \
  || fail "marker missing from StitcherTab.tsx"
grep -q "slotVideoErrors" "$TAB" \
  || fail "per-slot error map missing from StitcherTab"
grep -q "SLOT_VIDEO_LOAD_FAILED" "$TAB" \
  || fail "SLOT_VIDEO_LOAD_FAILED audit event missing"
grep -q "retryComposerSlotVideo" "$TAB" \
  || fail "Retry handler missing"
grep -q "data-stitch-dry-media-fail-loud" "$TAB" \
  || fail "fail-loud DOM marker missing"
# Must NOT ignore inactive pool errors (the silent-black class).
if grep -n "onPoolSlotError" -A20 "$TAB" | grep -q "if (slot !== viewerSlotRef.current) return;" ; then
  # Early return is OK only AFTER recording the error — verify setSlotVideoErrors precedes it.
  python3 - "$TAB" <<'PY' || fail "onPoolSlotError must record before active-slot gate"
import re, sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
m = re.search(r"const onPoolSlotError = \(slot: StitchSessionSlotKey\) => \{([\s\S]*?)\n  \};", src)
if not m:
    raise SystemExit("onPoolSlotError not found")
body = m.group(1)
rec = body.find("setSlotVideoErrors")
gate = body.find("if (slot !== viewerSlotRef.current) return;")
if rec < 0:
    raise SystemExit("setSlotVideoErrors not in onPoolSlotError")
if gate >= 0 and gate < rec:
    raise SystemExit("active-slot gate returns before recording error")
PY
fi

grep -q "STITCH_DRY_MEDIA_FAIL_LOUD_V1" "$TEST" \
  || fail "marker missing from unit test"

(
  cd "$ROOT/Production/tools/storyboard-v2"
  node --experimental-strip-types --test src/utils/__tests__/stitchSlotVideoLoadError.test.ts
) || fail "stitchSlotVideoLoadError unit tests failed"

echo "OK: STITCH_DRY_MEDIA_FAIL_LOUD_V1 durability gate"

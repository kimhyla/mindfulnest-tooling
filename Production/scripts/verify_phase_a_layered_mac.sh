#!/usr/bin/env bash
# Verify Mac readiness for Phase A layered Send (PHASE_A_ARLO_LAYERED_ROUTE_V2).
# Usage: bash Production/scripts/verify_phase_a_layered_mac.sh [Event_N]
# Default event: Event_6
set -euo pipefail

EVENT="${1:-Event_6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
PROD="${DROPBOX}/Production"
ARLO="${PROD}/NEW STYLE CHARACTERS/ARLO"
EVENT_DIR="${PROD}/${EVENT}"
PHASES="${TOOLING}/Production/tools/server_handlers/phases.py"
fail=0
warn() { echo "WARN: $*"; }
die() { echo "FAIL: $*"; fail=1; }
ok() { echo "OK: $*"; }

echo "=== Phase A layered Mac verify (V2 Gate0 headshot) ==="
echo "tooling=${TOOLING}"
echo "dropbox=${DROPBOX}"
echo "event=${EVENT}"

cd "${TOOLING}"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "branch=${branch} sha=${sha}"

if [[ -f "${TOOLING}/Production/tools/layered_character_lipsync.py" ]] \
  && [[ -f "${TOOLING}/Production/tools/layered_lipsync_jobs.py" ]]; then
  ok "layered engine modules present on disk"
else
  die "missing layered_character_lipsync.py / layered_lipsync_jobs.py"
fi

if [[ ! -f "${PHASES}" ]]; then
  die "missing ${PHASES}"
else
  block="$(python3 - <<'PY' "${PHASES}"
import pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
block = src.split("def handle_phase_a_lipsync", 1)[1].split("def _handle_phase_a_lipsync_layered", 1)[0]
print(block)
PY
)"
  if echo "${block}" | grep -q "return _handle_phase_a_lipsync_layered"; then
    ok "handle_phase_a_lipsync defaults to layered"
  else
    die "handle_phase_a_lipsync does not default to layered"
  fi
  if echo "${block}" | grep -qi "bytedance\|MN_PHASE_A_BYTEDANCE"; then
    die "ByteDance still present on Phase A Send dispatcher"
  else
    ok "ByteDance absent from Phase A Send dispatcher"
  fi
  if echo "${block}" | grep -q "PHASE_A_ARLO_LAYERED_ROUTE_V2"; then
    ok "PHASE_A_ARLO_LAYERED_ROUTE_V2 mentioned in handler"
  else
    die "PHASE_A_ARLO_LAYERED_ROUTE_V2 missing from handle_phase_a_lipsync"
  fi
fi

need_arlo=(
  "arlo_gesture_idle_kim_gate0_pinned_15s_v1.mp4"
  "arlo_room_plate_headshot_close_1280x720_v1.png"
  "arlo_key_canvas_headshot_1280x720_v1.png"
)
if [[ ! -d "${ARLO}" ]]; then
  die "ARLO asset dir missing: ${ARLO}"
else
  for f in "${need_arlo[@]}"; do
    p="${ARLO}/${f}"
    if [[ -f "${p}" ]]; then
      sz="$(wc -c < "${p}" | tr -d ' ')"
      ok "ARLO asset ${f} (${sz} bytes)"
    else
      die "missing ARLO asset ${p}"
    fi
  done
fi

if [[ -d "${EVENT_DIR}" ]]; then
  ok "event dir ${EVENT_DIR}"
else
  warn "event dir missing: ${EVENT_DIR}"
fi

export PYTHONPATH="${TOOLING}/Production:${TOOLING}/Production/tools:${PYTHONPATH:-}"
python3 - <<'PY'
from layered_character_lipsync import ARLO_PROFILE, validate_arlo_idle_contract, validate_profile
assert ARLO_PROFILE.route_id == "PHASE_A_ARLO_LAYERED_ROUTE_V2"
assert ARLO_PROFILE.idle_units[0].name == "kim_gate0_pinned"
assert ARLO_PROFILE.key_rgb == (11, 243, 7)
validate_arlo_idle_contract(ARLO_PROFILE)
validate_profile(ARLO_PROFILE)
print("OK: ARLO_PROFILE Gate0 contract validates")
PY

if [[ "${fail}" -ne 0 ]]; then
  echo "=== FAIL (${fail}) ==="
  exit 1
fi
echo "=== ALL OK ==="

#!/usr/bin/env bash
# Verify Mac readiness for Phase A layered Send (PHASE_A_ARLO_LAYERED_ROUTE_V1).
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
MIN_SHA="2e80ce8"

fail=0
warn() { echo "WARN: $*"; }
die() { echo "FAIL: $*"; fail=1; }
ok() { echo "OK: $*"; }

echo "=== Phase A layered Mac verify ==="
echo "tooling=${TOOLING}"
echo "dropbox=${DROPBOX}"
echo "event=${EVENT}"

# --- git / route ---
cd "${TOOLING}"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
full="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "branch=${branch} sha=${sha}"

if git merge-base --is-ancestor "${MIN_SHA}" HEAD 2>/dev/null; then
  ok "HEAD contains layered default commit ${MIN_SHA} (or later)"
else
  die "HEAD is missing ${MIN_SHA}. Run: git fetch && git checkout feature/phase-ab-beatgen-layered-durability && git pull"
fi

if [[ ! -f "${PHASES}" ]]; then
  die "missing ${PHASES}"
else
  block="$(python3 - <<'PY' "${PHASES}"
import pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
block = src.split("def handle_phase_a_lipsync", 1)[1].split("\ndef _handle_phase_a_lipsync_layered", 1)[0]
print(block)
PY
)"
  if echo "${block}" | grep -q "return _handle_phase_a_lipsync_layered"; then
    ok "handle_phase_a_lipsync defaults to layered"
  else
    die "handle_phase_a_lipsync does not default to layered"
  fi
  if echo "${block}" | grep -q "MN_PHASE_A_BYTEDANCE"; then
    ok "ByteDance remains opt-in via MN_PHASE_A_BYTEDANCE"
  else
    warn "MN_PHASE_A_BYTEDANCE marker not found in handler block"
  fi
  if echo "${block}" | grep -q "PHASE_A_ARLO_LAYERED_ROUTE_V1"; then
    ok "PHASE_A_ARLO_LAYERED_ROUTE_V1 mentioned in handler"
  else
    die "PHASE_A_ARLO_LAYERED_ROUTE_V1 missing from handle_phase_a_lipsync"
  fi
fi

# --- Dropbox ARLO assets (Category-2, shared) ---
need_arlo=(
  "arlo_gesture_idle_full_loop_30s_green_1920x1080_v1.mp4"
  "arlo_room_plate_chair_study_1280x720_v2.png"
  "arlo_key_canvas_1280x720_v1.png"
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
      die "ARLO asset MISSING: ${p}"
    fi
  done
fi

# --- Event transfer media (optional but checked for Event_6) ---
if [[ -d "${EVENT_DIR}" ]]; then
  ok "event dir exists: ${EVENT_DIR}"
  for f in \
    "phase_a_voice_stem_20260723-094806.mp3" \
    "phase_a_lipsync_20260723-110753.mp4" \
    "phase_a_lipsync_20260723-110753.json"
  do
    p="${EVENT_DIR}/${f}"
    if [[ -f "${p}" ]]; then
      sz="$(wc -c < "${p}" | tr -d ' ')"
      ok "event media ${f} (${sz} bytes)"
    else
      if [[ "${EVENT}" == "Event_6" ]]; then
        die "Event_6 media missing: ${p} — copy from Production/_TRANSFER_TO_MAC/Event_6_phase_a_20260723/ or unzip Downloads zip"
      else
        warn "optional named media not present for ${EVENT}: ${f}"
      fi
    fi
  done
else
  die "event dir missing: ${EVENT_DIR}"
fi

# --- operator next steps ---
echo ""
echo "=== Next steps on Mac (cannot be done from Windows) ==="
echo "1. git fetch && git checkout feature/phase-ab-beatgen-layered-durability && git pull"
echo "2. bash Production/scripts/deploy_option_b.sh --event ${EVENT}"
echo "   (or: bash Production/scripts/start_event_server.sh ${EVENT})"
echo "3. Hard-refresh http://localhost:$((5110 + ${EVENT#Event_}))/?event=${EVENT}"
echo "4. Do NOT set MN_PHASE_A_BYTEDANCE=1 unless intentionally testing ByteDance"
echo "HEAD=${full}"

if [[ "${fail}" -ne 0 ]]; then
  echo ""
  echo "RESULT: FAIL — fix missing items above before Phase A Send"
  exit 1
fi
echo ""
echo "RESULT: PASS — layered Phase A assets + route look ready"
exit 0

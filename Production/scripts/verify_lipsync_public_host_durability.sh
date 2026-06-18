#!/usr/bin/env bash
# verify_lipsync_public_host_durability.sh — LIPSYNC_PUBLIC_HOST_V1
#
# Voice-first Generate must preflight public lipsync hosting (R2 or public staging)
# before spending on TTS/O3. This script grep-gates the wiring so deploy cannot
# regress to localhost staging or missing credential injection.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
BG="${TOOLS}/server_handlers/background.py"
LPH="${TOOLS}/lipsync_public_host.py"
CREDS="${TOOLS}/credentials_lib/credentials.py"
START="${REPO_ROOT}/Production/scripts/start_event_server.sh"
BGTAB="${TOOLS}/storyboard-v2/src/components/BgTab.tsx"
O3_CONTRACT="${REPO_ROOT}/Production/scripts/verify_o3_intro_contract.sh"

fail() { echo "[lipsync-public-host-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$LPH" ]] || fail "missing lipsync_public_host.py"
[[ -f "$BG" ]] || fail "missing background.py"
[[ -f "$CREDS" ]] || fail "missing credentials.py"
[[ -f "$START" ]] || fail "missing start_event_server.sh"
[[ -f "$BGTAB" ]] || fail "missing BgTab.tsx"
[[ -f "$O3_CONTRACT" ]] || fail "missing verify_o3_intro_contract.sh"

grep -q 'LIPSYNC_HOSTING_NOT_CONFIGURED' "$BG" \
  || fail "background.py must block voice-first submit when lipsync host not ready"
grep -q 'inject_lipsync_r2_env' "$BG" \
  || fail "background.py must inject R2 env into O3 subprocess"
grep -q 'lipsync_public_host_ready' "$BG" \
  || fail "background.py must call lipsync_public_host_ready before voice-first submit"

grep -q 'cloudflare' "$CREDS" \
  || fail "credentials.py must parse Cloudflare R2 rows from API_KEYS_MASTER.md"
grep -q 'r2_access_key_id' "$CREDS" \
  || fail "credentials.py must expose r2_access_key_id"

grep -q 'lipsync_public_host.py' "$START" \
  || fail "start_event_server.sh must export lipsync R2 env before server launch"
grep -q '\-\-shell-export' "$START" \
  || fail "start_event_server.sh must call lipsync_public_host.py --shell-export"

grep -q 'voiceFirstLipsyncHostBlocked' "$BGTAB" \
  || fail "BgTab must gate Generate when lipsync public host is not ready"
grep -q 'isStaleLipsyncHostingFailure' "$BGTAB" \
  || fail "BgTab must hide stale pre-R2 hosting failure banners"
grep -q 'reconcile_stale_lipsync_hosting_failures' "$BG" \
  || fail "background.py must reconcile stale pre-R2 lipsync failures on session load"
grep -q 'update_beat_locked' "$BG" \
  || fail "background.py must use update_beat_locked for beat-scoped patches"
grep -q 'handle_bg_accept_lib_image' "$BG" \
  || fail "background.py must implement accept-lib-image handler"
accept_block="$(awk '/def handle_bg_accept_lib_image/,/^def handle_bg_groups/' "$BG")"
echo "$accept_block" | grep -q 'update_beat_locked' \
  || fail "accept-lib-image must patch via update_beat_locked"
echo "$accept_block" | grep -q 'SIDECAR_LOCK_CONTENTION' \
  || fail "accept-lib-image must return retry_safe lock contention"
grep -q 'copy_file_durable' "${REPO_ROOT}/Production/tools/beat_generator.py" \
  || fail "beat_generator.py must export copy_file_durable for Dropbox pose copies"
grep -q 'subprocess_running_for_o3_job' "${REPO_ROOT}/Production/tools/o3_generation_intent.py" \
  || fail "o3_generation_intent must skip stale terminal when subprocess still running"
grep -q 'mn-bg-lipsync-host-setup' "$BGTAB" \
  || fail "BgTab must render full-width lipsync setup banner"

grep -q 'test_lipsync_public_host.py' "$O3_CONTRACT" \
  || fail "verify_o3_intro_contract.sh must run test_lipsync_public_host.py"

[[ -x "${SCRIPT_DIR}/configure_r2_lipsync_hosting.sh" ]] \
  || fail "configure_r2_lipsync_hosting.sh must exist and be executable"
[[ -x "${SCRIPT_DIR}/smoke_lipsync_public_host_live.sh" ]] \
  || fail "smoke_lipsync_public_host_live.sh must exist and be executable"

echo "[lipsync-public-host-durability] OK — voice-first lipsync hosting gate wired"

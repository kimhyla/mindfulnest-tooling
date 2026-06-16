#!/usr/bin/env bash
# install_production_server_launchagent.sh — sync launchd pin with server_event_pin.json
#
# EVENT_LAUNCHAGENT_SYNC_V1 — the production server KeepAlive agent lived outside the
# repo and hardcoded Event_1 while Kim works Event_2, fighting persisted pin + deploy.
#
# Usage:
#   bash Production/scripts/install_production_server_launchagent.sh [Event_N]
#
# Event resolution order: CLI arg → MN_ACTIVE_EVENT → Production/server_event_pin.json → Event_1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
PROD_ROOT="${DROPBOX}/Production"
LABEL="com.mindfulnest.production-server"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PYTHON="${MN_PYTHON:-${HOME}/.pyenv/versions/3.12.7/bin/python3}"
SERVER="${PROD_ROOT}/tools/production_server.py"
STORYBOARD="${MN_STORYBOARD:-storyboard_v59_prod.html}"

resolve_event_id() {
  local arg="${1:-}"
  if [[ -n "$arg" ]]; then
    echo "$arg"
    return
  fi
  if [[ -n "${MN_ACTIVE_EVENT:-}" ]]; then
    echo "${MN_ACTIVE_EVENT}"
    return
  fi
  local pin="${PROD_ROOT}/server_event_pin.json"
  if [[ -f "$pin" ]]; then
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print((d.get('event_id') or '').strip())" "$pin" 2>/dev/null || true
    return
  fi
  echo "Event_1"
}

EVENT_ID="$(resolve_event_id "${1:-}")"
if [[ -z "$EVENT_ID" ]]; then
  EVENT_ID="Event_1"
fi
EVENT_DIR="Production/${EVENT_ID}"
EVENT_PORT="$(event_id_to_port "$EVENT_ID")"

[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
[[ -f "$SERVER" ]] || { echo "FATAL: missing $SERVER" >&2; exit 1; }

# Preserve secrets/env from an existing plist (never commit keys to git).
PRESERVE_ENV=""
if [[ -f "$PLIST" ]]; then
  PRESERVE_ENV="$(python3 - "$PLIST" <<'PY'
import plistlib, sys
path = sys.argv[1]
try:
    with open(path, "rb") as f:
        d = plistlib.load(f)
except Exception:
    sys.exit(0)
env = d.get("EnvironmentVariables") or {}
skip = {"HOME", "PATH", "LANG", "LC_ALL", "PYENV_VERSION", "PRODUCTION_SERVER_SINGLE_MACHINE", "MN_EVENT_PIN_IGNORE"}
for k, v in env.items():
    if k in skip or not v:
        continue
    print(f"\t\t<key>{k}</key>\n\t\t<string>{v}</string>")
PY
)"
fi

mkdir -p "${HOME}/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>${LABEL}</string>
	<key>ProgramArguments</key>
	<array>
		<string>${PYTHON}</string>
		<string>${SERVER}</string>
		<string>--event-dir</string>
		<string>${EVENT_DIR}</string>
		<string>--storyboard</string>
		<string>${STORYBOARD}</string>
		<string>--event-id</string>
		<string>${EVENT_ID}</string>
		<string>--port</string>
		<string>${EVENT_PORT}</string>
	</array>
	<key>WorkingDirectory</key>
	<string>${DROPBOX}</string>
	<key>KeepAlive</key>
	<true/>
	<key>RunAtLoad</key>
	<true/>
	<key>ThrottleInterval</key>
	<integer>10</integer>
	<key>StandardOutPath</key>
	<string>/tmp/mindfulnest_server.log</string>
	<key>StandardErrorPath</key>
	<string>/tmp/mindfulnest_server_err.log</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>HOME</key>
		<string>${HOME}</string>
		<key>PATH</key>
		<string>${HOME}/.pyenv/shims:${HOME}/.pyenv/versions/3.12.7/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
		<key>LANG</key>
		<string>en_US.UTF-8</string>
		<key>LC_ALL</key>
		<string>en_US.UTF-8</string>
		<key>PYENV_VERSION</key>
		<string>3.12.7</string>
		<key>PRODUCTION_SERVER_SINGLE_MACHINE</key>
		<string>1</string>
		<key>MN_EVENT_PIN_IGNORE</key>
		<string>1</string>
${PRESERVE_ENV}
	</dict>
</dict>
</plist>
PLIST

chmod 644 "$PLIST"

# Reload agent (bootstrap on newer macOS, load fallback).
UID_NUM="$(id -u)"
launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null \
  || launchctl unload "$PLIST" 2>/dev/null \
  || true
sleep 1
if launchctl bootstrap "gui/${UID_NUM}" "$PLIST" 2>/dev/null; then
  :
else
  launchctl load "$PLIST"
fi

echo "[launchagent] OK — ${LABEL} → ${EVENT_ID} (${EVENT_DIR}) port ${EVENT_PORT}"
echo "[launchagent] URL: $(event_storyboard_url "${EVENT_ID}")"
echo "[launchagent] plist: ${PLIST}"

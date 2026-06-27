#!/usr/bin/env bash
# install_production_server_launchagent.sh — sync launchd pin with server_event_pin.json
#
# EVENT_LAUNCHAGENT_SYNC_V1 — the production server KeepAlive agent lived outside the
# repo and hardcoded Event_1 while Kim works Event_2, fighting persisted pin + deploy.
#
# SERVER_LAUNCHD_SINGLE_OWNER_V1 — launchd is the ONLY supervisor for dedicated ports.
# Deploy/start scripts must NOT also nohup-spawn production_server.py (dual owner = restart storm).
#
# LD-505_TOOLING_CODE_ROOT_V1 — ProgramArguments use mindfulnest-tooling
# production_server.py; --event-dir points at Dropbox Production/Event_N (data only).
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
TOOLING="${MN_TOOLING_ROOT:-${REPO_ROOT}}"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
PROD_ROOT="${DROPBOX}/Production"
PYTHON="${MN_PYTHON:-${HOME}/.pyenv/versions/3.12.7/bin/python3}"
SERVER="${TOOLING}/Production/tools/production_server.py"
STORYBOARD="${MN_STORYBOARD:-storyboard_v59_prod.html}"

[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

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
EVENT_DIR_ABS="${PROD_ROOT}/${EVENT_ID}"
EVENT_PORT="$(event_id_to_port "$EVENT_ID")"
# One KeepAlive agent per port — never reuse generic label on dedicated Event_N servers.
EVENT_SLUG="$(python3 -c "import sys; print(''.join(sys.argv[1].split('_')).lower())" "$EVENT_ID")"
LABEL="com.mindfulnest.production-server-${EVENT_SLUG}"
LEGACY_LABEL="com.mindfulnest.production-server"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PLIST_NEW="${PLIST}.new"
LEGACY_PLIST="${HOME}/Library/LaunchAgents/${LEGACY_LABEL}.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

[[ -f "$SERVER" ]] || { echo "FATAL: missing tooling server at $SERVER" >&2; exit 1; }
[[ -d "$EVENT_DIR_ABS" ]] || { echo "FATAL: missing Dropbox event dir $EVENT_DIR_ABS" >&2; exit 1; }

wait_for_server_http() {
  local attempts="${1:-15}"
  local i
  for (( i = 1; i <= attempts; i++ )); do
    if curl -sf --max-time 5 "http://localhost:${EVENT_PORT}/api/event/current" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

kickstart_agent() {
  if launchctl kickstart -k "${DOMAIN}/${LABEL}" 2>/dev/null; then
    return 0
  fi
  launchctl bootstrap "${DOMAIN}" "$PLIST" 2>/dev/null \
    || launchctl load "$PLIST" 2>/dev/null \
    || true
}

# Preserve secrets/env from an existing plist (never commit keys to git).
# EVENT_LAUNCHAGENT_SECRET_INHERIT_V1 — new Event_N agents (Event_3+) had no prior
# plist, so PRESERVE_ENV was empty and Beat Gen extract failed with
# ANTHROPIC_API_KEY_MISSING. Seed from any sibling dedicated-server plist.
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
skip = {
    "HOME", "PATH", "LANG", "LC_ALL", "PYENV_VERSION",
    "PRODUCTION_SERVER_SINGLE_MACHINE", "MN_EVENT_PIN_IGNORE",
    "MN_LAUNCHD_MANAGED", "MN_TOOLING_ROOT", "MN_DROPBOX_ROOT",
    "MN_O3_GENERATE_MODE", "MN_BEATGEN_AVATAR_DISABLED",
}
for k, v in env.items():
    if k in skip or not v:
        continue
    print(f"\t\t<key>{k}</key>\n\t\t<string>{v}</string>")
PY
)"
fi
if [[ -z "$PRESERVE_ENV" ]]; then
  PRESERVE_ENV="$(python3 - "$PLIST" "$HOME/Library/LaunchAgents" <<'PY'
import glob, plistlib, sys
from pathlib import Path

target = Path(sys.argv[1])
agents_dir = Path(sys.argv[2])
skip = {
    "HOME", "PATH", "LANG", "LC_ALL", "PYENV_VERSION",
    "PRODUCTION_SERVER_SINGLE_MACHINE", "MN_EVENT_PIN_IGNORE",
    "MN_LAUNCHD_MANAGED", "MN_TOOLING_ROOT", "MN_DROPBOX_ROOT",
    "MN_O3_GENERATE_MODE", "MN_BEATGEN_AVATAR_DISABLED",
}
merged: dict[str, str] = {}
for candidate in sorted(agents_dir.glob("com.mindfulnest.production-server-event*.plist")):
    if candidate.resolve() == target.resolve():
        continue
    try:
        with candidate.open("rb") as f:
            env = (plistlib.load(f).get("EnvironmentVariables") or {})
    except Exception:
        continue
    for k, v in env.items():
        if k in skip or not v or k in merged:
            continue
        merged[k] = str(v)
if not merged:
    sys.exit(0)
for k, v in sorted(merged.items()):
    print(f"\t\t<key>{k}</key>\n\t\t<string>{v}</string>")
PY
)"
  if [[ -n "$PRESERVE_ENV" ]]; then
    echo "[launchagent] seeded secrets from sibling dedicated-server plist(s)"
  fi
fi

mkdir -p "${HOME}/Library/LaunchAgents"

TOOLS_DIR="$(dirname "$SERVER")"
LIPSYNC_R2_PLIST=""
while IFS= read -r line; do
  [[ "$line" =~ ^export\ ([A-Z0-9_]+)=(.+)$ ]] || continue
  key="${BASH_REMATCH[1]}"
  val="${BASH_REMATCH[2]}"
  val="${val#\'}"; val="${val%\'}"
  LIPSYNC_R2_PLIST+=$'\t\t<key>'"${key}"$'</key>\n\t\t<string>'"${val}"$'</string>\n'
done < <("$PYTHON" "$TOOLS_DIR/lipsync_public_host.py" --shell-export 2>/dev/null || true)

cat > "$PLIST_NEW" <<PLIST
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
		<string>${EVENT_DIR_ABS}</string>
		<string>--storyboard</string>
		<string>${STORYBOARD}</string>
		<string>--event-id</string>
		<string>${EVENT_ID}</string>
		<string>--port</string>
		<string>${EVENT_PORT}</string>
	</array>
	<key>WorkingDirectory</key>
	<string>${TOOLS_DIR}</string>
	<key>KeepAlive</key>
	<true/>
	<key>RunAtLoad</key>
	<true/>
	<key>ThrottleInterval</key>
	<integer>10</integer>
	<key>StandardOutPath</key>
	<string>/tmp/mindfulnest_server_${EVENT_SLUG}.log</string>
	<key>StandardErrorPath</key>
	<string>/tmp/mindfulnest_server_${EVENT_SLUG}_err.log</string>
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
		<key>MN_LAUNCHD_MANAGED</key>
		<string>1</string>
		<key>MN_TOOLING_ROOT</key>
		<string>${TOOLING}</string>
		<key>MN_DROPBOX_ROOT</key>
		<string>${DROPBOX}</string>
		<key>MN_O3_GENERATE_MODE</key>
		<string>element_native</string>
		<key>MN_BEATGEN_AVATAR_DISABLED</key>
		<string>1</string>
		<key>MN_BEATGEN_DB_PATH</key>
		<string>${HOME}/.mindfulnest/state/beatgen_${EVENT_SLUG}.db</string>
${PRESERVE_ENV}${LIPSYNC_R2_PLIST}	</dict>
</dict>
</plist>
PLIST

chmod 644 "$PLIST_NEW"

# Category fix: legacy generic agent also bound Event_2:5112 — boot it out permanently.
launchctl bootout "${DOMAIN}/${LEGACY_LABEL}" 2>/dev/null \
  || launchctl unload "$LEGACY_PLIST" 2>/dev/null \
  || true
if [[ -f "$LEGACY_PLIST" ]]; then
  mv "$LEGACY_PLIST" "${LEGACY_PLIST}.disabled.$(date +%Y%m%dT%H%M%S)" 2>/dev/null || rm -f "$LEGACY_PLIST"
fi

PLIST_CHANGED=1
if [[ -f "$PLIST" ]] && cmp -s "$PLIST" "$PLIST_NEW"; then
  PLIST_CHANGED=0
  rm -f "$PLIST_NEW"
  echo "[launchagent] plist unchanged — skip bootout/bootstrap (${LABEL})"
  if wait_for_server_http 3; then
    echo "[launchagent] server healthy on :${EVENT_PORT}"
  else
    echo "[launchagent] server down — kickstart ${LABEL}"
    kickstart_agent
    wait_for_server_http 15 || {
      echo "FATAL: server not reachable on :${EVENT_PORT} after kickstart" >&2
      exit 1
    }
  fi
else
  mv "$PLIST_NEW" "$PLIST"
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null \
    || launchctl unload "$PLIST" 2>/dev/null \
    || true
  sleep 1
  kickstart_agent
  wait_for_server_http 15 || {
    echo "FATAL: server not reachable on :${EVENT_PORT} after launch agent reload" >&2
    exit 1
  }
fi

echo "[launchagent] OK — ${LABEL} → ${EVENT_ID} (${EVENT_DIR_ABS}) port ${EVENT_PORT}"
echo "[launchagent] legacy ${LEGACY_LABEL} disabled (one agent per port)"
echo "[launchagent] URL: $(event_storyboard_url "${EVENT_ID}")"
echo "[launchagent] plist: ${PLIST}  changed=${PLIST_CHANGED}"

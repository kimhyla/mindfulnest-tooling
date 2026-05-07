#!/usr/bin/env bash
#
# install_backup_crons.sh — one-time launchd registration for backup jobs.
#
# Spec v2 §C15 + LD-127 (launchd preferred over Claude scheduled-tasks for reliability-critical jobs).
#
# Run ONCE as Kim from Terminal. Requires no sudo (user-level launchd agents).
#
# Creates these launchd agents in ~/Library/LaunchAgents/:
#   com.mindfulnest.daily-backup.plist       — runs daily_backup.sh at 03:15 local
#   com.mindfulnest.weekly-snapshot.plist    — runs weekly_directus_snapshot.py Sunday 04:00 local
#   com.mindfulnest.firestore-export.plist   — runs firestore_export.sh Sunday 04:30 local (requires gcloud)
#
# Unregister: `launchctl unload ~/Library/LaunchAgents/com.mindfulnest.*.plist && rm …`

set -euo pipefail

PROJECT_DIR="${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
SCRIPTS_DIR="${PROJECT_DIR}/Production/scripts"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/MindfulNestBackups/launchd-logs"

mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"
chmod +x "${SCRIPTS_DIR}/daily_backup.sh"
chmod +x "${SCRIPTS_DIR}/weekly_directus_snapshot.py"

write_plist() {
  local label="$1"
  local plist_path="${LAUNCH_AGENTS_DIR}/${label}.plist"
  local program="$2"
  local hour="$3"
  local minute="$4"
  local weekday="${5:-}"   # optional: 0-6 (Sun-Sat)

  local weekday_xml=""
  if [ -n "${weekday}" ]; then
    weekday_xml="<key>Weekday</key><integer>${weekday}</integer>"
  fi

  cat > "${plist_path}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${program}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>${hour}</integer>
    <key>Minute</key><integer>${minute}</integer>
    ${weekday_xml}
  </dict>
  <key>StandardOutPath</key><string>${LOG_DIR}/${label}.out.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/${label}.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
PLIST

  launchctl unload "${plist_path}" 2>/dev/null || true
  launchctl load "${plist_path}"
  echo "INSTALLED ${label}: ${program} @ ${hour}:${minute}${weekday:+ weekday=${weekday}}"
}

write_plist "com.mindfulnest.daily-backup" "${SCRIPTS_DIR}/daily_backup.sh" 3 15 ""
write_plist "com.mindfulnest.weekly-snapshot" "/usr/bin/env" 4 0 "0"  # placeholder — plist doesn't accept multi-arg easily; use wrapper

# Simpler: wrap python3 invocation in a shell script for launchd
cat > "${SCRIPTS_DIR}/_weekly_snapshot_wrapper.sh" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
exec /usr/bin/python3 Production/scripts/weekly_directus_snapshot.py
WRAPPER
chmod +x "${SCRIPTS_DIR}/_weekly_snapshot_wrapper.sh"

# Re-register weekly-snapshot using the wrapper
WS_PLIST="${LAUNCH_AGENTS_DIR}/com.mindfulnest.weekly-snapshot.plist"
cat > "${WS_PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mindfulnest.weekly-snapshot</string>
  <key>ProgramArguments</key>
  <array>
    <string>${SCRIPTS_DIR}/_weekly_snapshot_wrapper.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>4</integer>
    <key>Minute</key><integer>0</integer>
    <key>Weekday</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>${LOG_DIR}/com.mindfulnest.weekly-snapshot.out.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/com.mindfulnest.weekly-snapshot.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
PLIST
launchctl unload "${WS_PLIST}" 2>/dev/null || true
launchctl load "${WS_PLIST}"

echo ""
echo "Installed launchd agents:"
launchctl list | grep -i mindfulnest || echo "  (none listed — check ${LAUNCH_AGENTS_DIR})"
echo ""
echo "NOTE: Firestore export job (gcloud firestore export) requires separate install after"
echo "Firebase Auth integration (APP-09) is wired. Deferred to Stage 3 kickoff."

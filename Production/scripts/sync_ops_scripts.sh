#!/usr/bin/env bash
#
# sync_ops_scripts.sh — keep ~/MindfulNestOps/scripts/ in sync with canonical Production/scripts/
#
# Why this script exists:
#   The macOS launchd daily-backup job runs ~/MindfulNestOps/scripts/daily_backup.sh
#   (NOT the canonical Production/scripts/daily_backup.sh in CloudStorage), because
#   CloudStorage paths trip TCC/Full-Disk-Access permissions for launchd. So we keep
#   two copies and need a sync mechanism to prevent drift.
#
# Canonical: Production/scripts/daily_backup.sh (committed in git, in CloudStorage)
# Mirror:    ~/MindfulNestOps/scripts/daily_backup.sh (what launchd actually runs)
#
# This script is a one-way pull from canonical → mirror. SHA-compared, executable bit
# preserved, idempotent (no-op when SHAs match). Wired into .git/hooks/post-commit so
# every commit auto-syncs. Can also be run manually.
#
# Authority: LD SUPABASE_DB_USER_DIRECT_OPTION_B_V1 (id=590) follow-up; Rule 35 read-back-after-write.
#
# Exit codes:
#   0 — already in sync, or sync succeeded
#   1 — canonical missing
#   2 — mirror dir missing and could not be created
#   3 — copy failed
#
# Usage:
#   bash Production/scripts/sync_ops_scripts.sh             # quiet on no-op, verbose on sync
#   bash Production/scripts/sync_ops_scripts.sh --verbose   # always verbose

set -euo pipefail

VERBOSE=0
if [[ "${1:-}" == "--verbose" ]]; then
  VERBOSE=1
fi

# Resolve canonical path: this script lives in <repo>/Production/scripts/, so canonical
# daily_backup.sh sits next to it.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
CANONICAL="${SCRIPT_DIR}/daily_backup.sh"
MIRROR_DIR="${HOME}/MindfulNestOps/scripts"
MIRROR="${MIRROR_DIR}/daily_backup.sh"

log() {
  if [[ $VERBOSE -eq 1 || "${2:-}" == "force" ]]; then
    echo "[sync_ops_scripts] $1"
  fi
}

if [[ ! -f "$CANONICAL" ]]; then
  echo "[sync_ops_scripts] ERROR: canonical not found at $CANONICAL" >&2
  exit 1
fi

if [[ ! -d "$MIRROR_DIR" ]]; then
  log "creating mirror dir $MIRROR_DIR" force
  mkdir -p "$MIRROR_DIR" || { echo "[sync_ops_scripts] ERROR: could not create $MIRROR_DIR" >&2; exit 2; }
fi

# Compare SHAs
canonical_sha="$(shasum -a 256 "$CANONICAL" | awk '{print $1}')"
if [[ -f "$MIRROR" ]]; then
  mirror_sha="$(shasum -a 256 "$MIRROR" | awk '{print $1}')"
else
  mirror_sha="(missing)"
fi

if [[ "$canonical_sha" == "$mirror_sha" ]]; then
  log "in sync (sha=${canonical_sha:0:12}...)"
  exit 0
fi

log "drift detected — canonical=${canonical_sha:0:12}... mirror=${mirror_sha:0:12}... — syncing" force

# Atomic copy: write to a temp file in the same dir, then rename.
tmp="${MIRROR}.tmp.$$"
cp "$CANONICAL" "$tmp" || { echo "[sync_ops_scripts] ERROR: cp failed" >&2; rm -f "$tmp"; exit 3; }
chmod +x "$tmp"
mv "$tmp" "$MIRROR" || { echo "[sync_ops_scripts] ERROR: mv failed" >&2; rm -f "$tmp"; exit 3; }

# Read-back verification (Rule 35 spirit applied to filesystem write)
new_mirror_sha="$(shasum -a 256 "$MIRROR" | awk '{print $1}')"
if [[ "$new_mirror_sha" != "$canonical_sha" ]]; then
  echo "[sync_ops_scripts] ERROR: post-write SHA mismatch ($new_mirror_sha vs $canonical_sha)" >&2
  exit 3
fi

# Confirm executable bit
if [[ ! -x "$MIRROR" ]]; then
  echo "[sync_ops_scripts] ERROR: mirror not executable after copy" >&2
  exit 3
fi

log "synced canonical → mirror (sha=${canonical_sha:0:12}..., +x preserved)" force
exit 0

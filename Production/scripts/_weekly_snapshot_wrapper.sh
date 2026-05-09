#!/usr/bin/env bash
# LD-227 Phase 1 (2026-05-08): wrap with `doppler run --` so the snapshot job
# inherits live Doppler secrets (Doppler project `mindfulnest`, config `dev`).
# Absolute path /opt/homebrew/bin/doppler is REQUIRED — launchd default PATH
# (/usr/bin:/bin:/usr/sbin:/sbin) does NOT include /opt/homebrew/bin, and the
# weekly-snapshot plist has no EnvironmentVariables.PATH override.
# MN_DROPBOX_ROOT: LD-505 — project root for `cd` must follow the mounted media tree.
set -euo pipefail
: "${MN_DROPBOX_ROOT:=${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
cd "$MN_DROPBOX_ROOT"
exec /opt/homebrew/bin/doppler run -- /usr/bin/python3 Production/scripts/weekly_directus_snapshot.py

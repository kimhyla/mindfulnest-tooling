#!/usr/bin/env bash
set -euo pipefail
cd "${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
exec /usr/bin/python3 Production/scripts/weekly_directus_snapshot.py

#!/usr/bin/env bash
# copy-to-event.sh — promote the Vite single-file build to a versioned
# Production/Event_N/storyboard_v<N>_prod.html that production_server.py can
# serve via --storyboard <filename>.
#
# Usage (from this scripts/ dir or the repo root):
#   bash Production/tools/storyboard-v2/scripts/copy-to-event.sh
#   EVENT_DIR=Production/Event_1 STORYBOARD_VERSION=v59 \
#     bash Production/tools/storyboard-v2/scripts/copy-to-event.sh
#
# Mitigation M7 (Cursor): keeps last good storyboard_v<N>_prod.html backed up
# next to the new one with a UTC timestamp suffix so a broken build doesn't
# lock Kim out. Example: storyboard_v59_prod.html ->
# storyboard_v59_prod_PRECOPY_BACKUP_<UTC>.html.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROD_TOOLS_DIR="$(cd "$APP_DIR/.." && pwd)"
PROD_DIR="$(cd "$PROD_TOOLS_DIR/.." && pwd)"

# Defaults — override via env.
EVENT_DIR_REL="${EVENT_DIR:-Production/Event_1}"
STORYBOARD_VERSION="${STORYBOARD_VERSION:-v59}"
EVENT_DIR_ABS="$(cd "$PROD_DIR/.." && pwd)/$EVENT_DIR_REL"

if [[ ! -d "$EVENT_DIR_ABS" ]]; then
  echo "error: event dir not found: $EVENT_DIR_ABS" >&2
  exit 1
fi

SOURCE_HTML="$APP_DIR/dist/index.html"
TARGET_NAME="storyboard_${STORYBOARD_VERSION}_prod.html"
TARGET_HTML="$EVENT_DIR_ABS/$TARGET_NAME"

if [[ ! -f "$SOURCE_HTML" ]]; then
  echo "error: build artifact not found: $SOURCE_HTML" >&2
  echo "Run 'npm run build' from $APP_DIR first." >&2
  exit 1
fi

# Backup the existing target if any (M7 — never lock Kim out).
if [[ -f "$TARGET_HTML" ]]; then
  TS="$(date -u +%Y%m%d_%H%M%SZ)"
  BACKUP="$EVENT_DIR_ABS/storyboard_${STORYBOARD_VERSION}_prod_PRECOPY_BACKUP_${TS}.html"
  cp -p "$TARGET_HTML" "$BACKUP"
  echo "Pre-copy backup: $BACKUP"
fi

# Copy the build artifact in place.
cp -p "$SOURCE_HTML" "$TARGET_HTML"
echo "Copied:"
echo "  $SOURCE_HTML"
echo "  -> $TARGET_HTML"

# Sanity: file is non-empty + has the doctype (basic sanity, not invariant audit).
if [[ ! -s "$TARGET_HTML" ]]; then
  echo "error: copied file is empty: $TARGET_HTML" >&2
  exit 2
fi
if ! head -c 64 "$TARGET_HTML" | grep -qi 'doctype html'; then
  echo "error: copied file does not start with <!doctype html>: $TARGET_HTML" >&2
  exit 3
fi

echo "OK. Sanity checks passed."
echo
echo "Next:"
echo "  python3 \"$PROD_TOOLS_DIR/production_server.py\" \\"
echo "      --event-dir \"$EVENT_DIR_REL\" \\"
echo "      --storyboard \"$TARGET_NAME\" \\"
echo "      --event-id Event_1"

#!/usr/bin/env bash
# Create a dated read-only-style backup of the golden storyboard (copy, never edit backup).
# Usage (from repo root or Production):
#   bash Production/scripts/backup_golden_storyboard.sh
#   STORYBOARD=storyboard_v58_prod.html bash Production/scripts/backup_golden_storyboard.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EVENT_DIR="${EVENT_DIR:-$PROD_DIR/Event_1}"
STORYBOARD="${STORYBOARD:-storyboard_v58_prod.html}"
TS="$(date +%Y%m%d_%H%M%S)"
SRC="$EVENT_DIR/$STORYBOARD"
DST="$EVENT_DIR/${STORYBOARD%.html}_GOLDEN_BACKUP_${TS}.html"

if [[ ! -f "$SRC" ]]; then
  echo "error: missing $SRC" >&2
  exit 1
fi

cp -p "$SRC" "$DST"
echo "Backed up:"
echo "  $DST"
echo "Do not edit *_GOLDEN_BACKUP_* files; restore with: cp \"$DST\" \"$SRC\""

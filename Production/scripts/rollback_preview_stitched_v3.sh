#!/bin/bash
# Rollback Preview Stitched V3 (LD 20260419)
# Per counter MEDIUM-7: also scrub new state.json fields so pre-V3 server
# doesn't emit them into sidecar.
#
# Usage:
#   bash Production/scripts/rollback_preview_stitched_v3.sh [TIMESTAMP]
# If TIMESTAMP omitted, reads /tmp/backup_ts_v3.txt.

set -euo pipefail

cd "$(dirname "$0")/../.."

TS="${1:-$(cat /tmp/backup_ts_v3.txt 2>/dev/null || echo '')}"
if [ -z "$TS" ]; then
  echo "ERROR: no backup timestamp. Pass as arg or populate /tmp/backup_ts_v3.txt"
  exit 2
fi

echo "[rollback_v3] restoring from timestamp: $TS"

PS_BAK="Production/tools/production_server.py.bak_phase_b_${TS}"
HTML_BAK="Production/Event_1/storyboard_v38_prod.html.bak_phase_b_${TS}"
FS_BAK="Production/tools/lib/ffmpeg_stitch.py.bak_phase_b_${TS}"

for f in "$PS_BAK" "$HTML_BAK" "$FS_BAK"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: backup not found: $f"; exit 3
  fi
done

# Restore governed files.
cp "$PS_BAK" Production/tools/production_server.py
cp "$HTML_BAK" Production/Event_1/storyboard_v38_prod.html
cp "$FS_BAK" Production/tools/lib/ffmpeg_stitch.py
echo "[rollback_v3] restored 3 governed files."

# Remove new V3 files.
rm -f Production/tools/patch_v38_phase_b.py
rm -f Production/tools/tests/test_phase_b_panel.py
echo "[rollback_v3] removed V3 patcher + test file."

# MEDIUM-7: scrub new state.json fields so old server doesn't echo them
# back into the sidecar L[] JSON (harmless to read but unused).
STATE_JSON="Production/Event_1/production_state.json"
if [ -f "$STATE_JSON" ]; then
  python3 -c "
import json, sys
from pathlib import Path
p = Path('$STATE_JSON')
s = json.loads(p.read_text())
removed = []
for key in list(s.keys()):
    if key.startswith('phase_a_') or key.startswith('phase_b_'):
        removed.append(key); del s[key]
p.write_text(json.dumps(s, indent=2))
print(f'[rollback_v3] scrubbed {len(removed)} phase_* fields: {removed}')
"
else
  echo "[rollback_v3] WARN: $STATE_JSON not found; skipping scrub."
fi

# Placeholder assets are left on disk (harmless).
echo "[rollback_v3] V3 rolled back. V2 preview_stitched still active."
echo "[rollback_v3] Restart server via: curl -X POST http://localhost:5111/api/server/restart || (pkill -HUP -f production_server.py)"

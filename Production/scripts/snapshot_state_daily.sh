#!/usr/bin/env bash
# snapshot_state_daily.sh — daily backup of Event_*/production_state.json
#
# Per LD-455 PATH_C_REWRITE_V1 (locked, SHIPPED 2026-05-20 after fabrication
# scan caught the missing script). Snapshots all Event_*/production_state.json
# files to a timestamped dir so single-day disasters are recoverable.
#
# Intended to run via launchd / cron once daily. Idempotent — safe to re-run.
#
# Exit codes:
#   0 — all snapshots ok
#   1 — at least one snapshot failed (still snapshots the rest)
#   2 — Dropbox root not reachable

set -euo pipefail

DROPBOX_ROOT="${MN_DROPBOX_ROOT:-/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
PRODUCTION_DIR="$DROPBOX_ROOT/Production"

if [[ ! -d "$PRODUCTION_DIR" ]]; then
    echo "[state_snapshot] FATAL: Production/ not found at $PRODUCTION_DIR" >&2
    exit 2
fi

UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
SNAPSHOT_ROOT="$DROPBOX_ROOT/.state_snapshots/$UTC_TS"
mkdir -p "$SNAPSHOT_ROOT"

failed=0
count=0
for event_dir in "$PRODUCTION_DIR"/Event_*; do
    [[ -d "$event_dir" ]] || continue
    event_name="$(basename "$event_dir")"
    state="$event_dir/production_state.json"
    if [[ ! -f "$state" ]]; then
        continue
    fi
    dst="$SNAPSHOT_ROOT/$event_name/production_state.json"
    mkdir -p "$(dirname "$dst")"
    if cp "$state" "$dst"; then
        sz=$(wc -c < "$dst")
        echo "[state_snapshot] $event_name: $sz bytes → $dst"
        count=$((count + 1))
    else
        echo "[state_snapshot] FAIL $event_name → $dst" >&2
        failed=$((failed + 1))
    fi
done

# Also snapshot beat_generator_state.json sidecar
bg_state="$DROPBOX_ROOT/Production/beat_generator_state.json"
if [[ -f "$bg_state" ]]; then
    cp "$bg_state" "$SNAPSHOT_ROOT/beat_generator_state.json"
    sz=$(wc -c < "$SNAPSHOT_ROOT/beat_generator_state.json")
    echo "[state_snapshot] beat_generator_state: $sz bytes"
    count=$((count + 1))
fi

# Rotation: keep 30 days. Older snapshots get pruned.
PRUNE_DAYS="${MN_STATE_SNAPSHOT_RETAIN_DAYS:-30}"
PRUNE_ROOT="$DROPBOX_ROOT/.state_snapshots"
if [[ -d "$PRUNE_ROOT" ]]; then
    # macOS find: -mtime in days
    pruned=$(find "$PRUNE_ROOT" -maxdepth 1 -mindepth 1 -type d -mtime +"$PRUNE_DAYS" -print -exec rm -rf {} \; 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$pruned" -gt 0 ]]; then
        echo "[state_snapshot] pruned $pruned snapshot(s) older than $PRUNE_DAYS days"
    fi
fi

echo "[state_snapshot] total snapshotted: $count file(s); failed: $failed"
if [[ "$failed" -gt 0 ]]; then
    exit 1
fi
exit 0

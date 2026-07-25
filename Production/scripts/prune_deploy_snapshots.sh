#!/usr/bin/env bash
# prune_deploy_snapshots.sh — keep .deploy_backups small and bounded.
#
# Every deploy writes a rollback snapshot to <dropbox>/.deploy_backups/<UTC_TS>.
# Without enforcement that tree grows without bound and each snapshot can carry
# a full node_modules copy, which is how .deploy_backups reached ~132 GB in
# Dropbox. This script is the single enforcement point for both problems:
#
#   1. retention  — delete all but the newest N snapshots (default 5)
#   2. slimming   — strip regenerable build artifacts from the snapshots kept
#
# It runs from deploy_storyboard_v59.sh step (a.5) and is also safe to run by
# hand for a one-off cleanup:
#
#   bash Production/scripts/prune_deploy_snapshots.sh <backup_root> [keep]
#   MN_DEPLOY_SNAPSHOT_KEEP=3 bash Production/scripts/prune_deploy_snapshots.sh <backup_root>
#
# Snapshot dir names are UTC timestamps, so lexicographic sort == chronological.

set -euo pipefail

BACKUP_ROOT="${1:-${MN_DEPLOY_BACKUP_ROOT:-}}"
KEEP="${2:-${MN_DEPLOY_SNAPSHOT_KEEP:-5}}"

# Build artifacts that are regenerable from the repo and must never be
# preserved in a rollback snapshot.
PRUNE_DIR_NAMES=(node_modules dist __pycache__ .venv node_modules.bak)

if [[ -z "$BACKUP_ROOT" ]]; then
    echo "FATAL: backup root not given (arg 1 or MN_DEPLOY_BACKUP_ROOT)" >&2
    exit 2
fi

# Safety: only ever operate on a path that is literally a .deploy_backups dir.
# Prevents a mis-wired caller from handing us a real content tree.
if [[ "$(basename "$BACKUP_ROOT")" != ".deploy_backups" ]]; then
    echo "FATAL: refusing to prune '$BACKUP_ROOT' — basename must be .deploy_backups" >&2
    exit 2
fi

if [[ ! "$KEEP" =~ ^[0-9]+$ ]] || [[ "$KEEP" -lt 1 ]]; then
    echo "FATAL: keep count must be a positive integer, got '$KEEP'" >&2
    exit 2
fi

if [[ ! -d "$BACKUP_ROOT" ]]; then
    echo "[prune] no snapshot root at $BACKUP_ROOT — nothing to do"
    exit 0
fi

echo "[prune] root=$BACKUP_ROOT keep=$KEEP"

seen=0
pruned=0
slimmed=0

# macOS ships bash 3.2 — no mapfile/readarray.
while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    # Hard guards — never act on traversal or relative entries.
    if [[ "$name" == "." || "$name" == ".." || "$name" == *"/"* ]]; then
        echo "  SKIP unsafe snapshot name: '$name'" >&2
        continue
    fi
    target="$BACKUP_ROOT/$name"
    [[ -d "$target" ]] || continue

    seen=$((seen + 1))
    if [[ "$seen" -gt "$KEEP" ]]; then
        rm -rf "$target"
        pruned=$((pruned + 1))
        echo "  pruned old snapshot: $name"
        continue
    fi

    # Retained snapshot — strip regenerable artifacts left by pre-fix deploys.
    for artifact in "${PRUNE_DIR_NAMES[@]}"; do
        while IFS= read -r hit; do
            [[ -n "$hit" ]] || continue
            rm -rf "$hit"
            slimmed=$((slimmed + 1))
            echo "  slimmed: ${hit#"$BACKUP_ROOT"/}"
        done < <(find "$target" -type d -name "$artifact" -prune 2>/dev/null)
    done
done < <(ls -1 "$BACKUP_ROOT" 2>/dev/null | sort -r)

echo "[prune] done — snapshots seen=$seen kept=$((seen - pruned)) pruned=$pruned artifacts_slimmed=$slimmed"

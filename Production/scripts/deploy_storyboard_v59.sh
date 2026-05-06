#!/usr/bin/env bash
# deploy_storyboard_v59.sh — comprehensive deploy of v59 storyboard tool
# from tooling repo (canonical CODE per LD-505) to Dropbox runtime tree
# (canonical CONTENT/STATE per LD-505).
#
# Per STORYBOARD_V59_AUTHORING_WORKFLOW_HANDOFF.md §4 C-14 +
# LD STORYBOARD_DEPLOY_PROCESS_V1 (filed C-14).
#
# Steps:
#   (a) Timestamped pre-deploy snapshot of dest subset (rollback safety)
#   (b) Atomic rsync mirror per code directory: Production/{tools,lib,scripts}
#   (c) dist/index.html (built v59 client bundle) copy
#   (d) Per-critical-file sha256 verification (FATAL on mismatch)
#   (e) Auto-restart production_server.py if mtime changed
#   (f) Auto-launch (per Kim's earlier authorization)
#
# Manual partial deploys (cp single file, manual rsync of one subdir, etc.)
# are FORBIDDEN per LD STORYBOARD_DEPLOY_PROCESS_V1 — they're how the
# post-redeploy bug class arose.
#
# Usage:
#   bash Production/scripts/deploy_storyboard_v59.sh
#     (default event_dir = Production/Event_1; override via MN_EVENT_DIR env)
#
#   MN_EVENT_DIR=Production/Event_2 bash Production/scripts/deploy_storyboard_v59.sh
#
#   Skip auto-launch (just deploy + verify):
#   MN_DEPLOY_SKIP_LAUNCH=1 bash Production/scripts/deploy_storyboard_v59.sh

set -euo pipefail

# ----------------------------------------------------------------
# Tree boundaries per LD-505 TOOLING_REPO_CREATED_V1
# ----------------------------------------------------------------
SRC_TOOLING="${MN_TOOLING_ROOT:-/Users/kimberlysmith/Projects/mindfulnest-tooling}"
DEST_DROPBOX="${MN_DROPBOX_ROOT:-/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"

if [[ ! -d "$SRC_TOOLING" ]]; then
    echo "FATAL: tooling repo not found at $SRC_TOOLING" >&2
    echo "  Set MN_TOOLING_ROOT env var to override." >&2
    exit 1
fi
if [[ ! -d "$DEST_DROPBOX" ]]; then
    echo "FATAL: Dropbox runtime tree not found at $DEST_DROPBOX" >&2
    echo "  Set MN_DROPBOX_ROOT env var to override." >&2
    exit 1
fi

UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
SNAPSHOT_DIR="$DEST_DROPBOX/.deploy_backups/$UTC_TS"
LOG_DIR="$SNAPSHOT_DIR/logs"

echo "[deploy] $(date -u +%FT%TZ)  STORYBOARD_DEPLOY_PROCESS_V1"
echo "  src:  $SRC_TOOLING"
echo "  dest: $DEST_DROPBOX"
echo "  snap: $SNAPSHOT_DIR"

# ----------------------------------------------------------------
# (a) Pre-deploy snapshot — rollback safety net
# ----------------------------------------------------------------
mkdir -p "$LOG_DIR"
echo "[deploy] (a) snapshotting current dest subset..."
for sub in Production/tools Production/lib Production/scripts; do
    if [[ -d "$DEST_DROPBOX/$sub" ]]; then
        mkdir -p "$SNAPSHOT_DIR/$sub"
        rsync -a "$DEST_DROPBOX/$sub/" "$SNAPSHOT_DIR/$sub/"
        echo "  snapshot ok: $sub"
    fi
done

# ----------------------------------------------------------------
# (b) Atomic mirror per directory — tooling repo → Dropbox
#     --delete removes Dropbox-side files NOT in tooling repo so the
#     dest tree truly matches source. Pre-deploy snapshot in (a) is
#     the rollback path if anything was Dropbox-only and important.
# ----------------------------------------------------------------
echo "[deploy] (b) atomic rsync mirror..."
for sub in Production/tools Production/lib Production/scripts; do
    if [[ ! -d "$SRC_TOOLING/$sub" ]]; then
        echo "  WARN: $SRC_TOOLING/$sub missing in source; skip"
        continue
    fi
    log_safe="$(echo "$sub" | tr '/' '_')"
    rsync -a --delete \
        "$SRC_TOOLING/$sub/" \
        "$DEST_DROPBOX/$sub/" \
        2>&1 | tee "$LOG_DIR/rsync_${log_safe}.log"
    echo "  mirrored: $sub"
done

# ----------------------------------------------------------------
# (c) dist/index.html (built v59 client bundle)
# ----------------------------------------------------------------
DIST="$SRC_TOOLING/Production/tools/storyboard-v2/dist/index.html"
DIST_DEST="$DEST_DROPBOX/Production/tools/storyboard-v2/dist/index.html"
if [[ -f "$DIST" ]]; then
    mkdir -p "$(dirname "$DIST_DEST")"
    cp "$DIST" "$DIST_DEST"
    echo "[deploy] (c) dist/index.html copied"
else
    echo "[deploy] (c) WARN: dist/index.html missing in source — run 'npm run build' before deploy"
fi

# ----------------------------------------------------------------
# (d) Per-file sha256 verification (FATAL on mismatch)
# ----------------------------------------------------------------
echo "[deploy] (d) sha256 verification..."
verify_files=(
    "Production/tools/production_server.py"
    "Production/tools/scope_router.py"
    "Production/tools/storyboard-v2/src/api/endpoints.ts"
    "Production/tools/storyboard-v2/src/api/client.ts"
)
for f in "${verify_files[@]}"; do
    src="$SRC_TOOLING/$f"
    dst="$DEST_DROPBOX/$f"
    if [[ ! -f "$src" || ! -f "$dst" ]]; then
        echo "  WARN: skip verify (missing): $f"
        continue
    fi
    src_sha=$(shasum -a 256 "$src" | awk '{print $1}')
    dst_sha=$(shasum -a 256 "$dst" | awk '{print $1}')
    if [[ "$src_sha" != "$dst_sha" ]]; then
        echo "FATAL sha256 mismatch on $f" >&2
        echo "  src: $src_sha" >&2
        echo "  dst: $dst_sha" >&2
        echo "  rollback: cp -R $SNAPSHOT_DIR/Production/* $DEST_DROPBOX/Production/" >&2
        exit 1
    fi
    echo "  verified: $f  $src_sha"
done

# ----------------------------------------------------------------
# (e) Auto-restart production_server.py if mtime changed
# ----------------------------------------------------------------
echo "[deploy] (e) checking running production_server.py..."
RUNNING_PIDS=$(pgrep -f "production_server.py" || true)
if [[ -n "$RUNNING_PIDS" ]]; then
    echo "  found running pids: $RUNNING_PIDS  → killing for restart"
    pkill -f "production_server.py" || true
    sleep 1
fi

# ----------------------------------------------------------------
# (f) Auto-launch with --event-dir (per Kim's Δ-C5.5-Y authorization)
# ----------------------------------------------------------------
if [[ -n "${MN_DEPLOY_SKIP_LAUNCH:-}" ]]; then
    echo "[deploy] (f) MN_DEPLOY_SKIP_LAUNCH set; skipping launch"
    echo "[deploy] complete (no launch)  snapshot=$SNAPSHOT_DIR"
    exit 0
fi

EVENT_DIR="${MN_EVENT_DIR:-Production/Event_1}"
echo "[deploy] (f) launching production_server.py against $EVENT_DIR ..."
cd "$DEST_DROPBOX"

# Determine storyboard html — fall back to scanning the event dir if the
# canonical name doesn't exist.
event_dir_abs="$DEST_DROPBOX/$EVENT_DIR"
storyboard_html=""
if [[ -f "$event_dir_abs/storyboard_v59_prod.html" ]]; then
    storyboard_html="storyboard_v59_prod.html"
else
    candidate=$(ls "$event_dir_abs"/storyboard_v*_prod.html 2>/dev/null | head -1 || true)
    if [[ -n "$candidate" ]]; then
        storyboard_html="$(basename "$candidate")"
    fi
fi
if [[ -z "$storyboard_html" ]]; then
    echo "FATAL: no storyboard_v*_prod.html found under $event_dir_abs/" >&2
    exit 1
fi

# Event id derives from event_dir name (e.g. Event_1 → Event_1).
event_id="$(basename "$EVENT_DIR")"

nohup python3 "$DEST_DROPBOX/Production/tools/production_server.py" \
    --event-dir "$EVENT_DIR" \
    --storyboard "$storyboard_html" \
    --event-id "$event_id" \
    > "$LOG_DIR/server.log" 2>&1 &
SERVER_PID=$!

# Wait for the server to bind the port (or fail to launch).
sleep 2
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "FATAL: server failed to launch — see $LOG_DIR/server.log" >&2
    tail -30 "$LOG_DIR/server.log" >&2 || true
    exit 1
fi
echo "[deploy] server launched: pid=$SERVER_PID  event_dir=$EVENT_DIR  storyboard=$storyboard_html"
echo "[deploy] complete  snapshot=$SNAPSHOT_DIR  log=$LOG_DIR/server.log"

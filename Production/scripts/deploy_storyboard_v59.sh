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
#     (defaults: MN_TOOLING_ROOT = this Mac's tooling checkout;
#               MN_DROPBOX_ROOT = Dropbox "Claude Mindfulnest Project Files" — overrides per LD-505 / LD-541)
#     (default event_dir = persisted server_event_pin.json when present, else Production/Event_1;
#      override via --event flag or MN_EVENT_DIR env)
#     Event_0 is intentionally excluded from fanout — it is a Milestone (opening_storybook).
#
#   bash Production/scripts/deploy_storyboard_v59.sh --event Event_2
#   MN_EVENT_DIR=Production/Event_2 bash Production/scripts/deploy_storyboard_v59.sh  (legacy)
#
#   Skip auto-launch (just deploy + verify):
#   MN_DEPLOY_SKIP_LAUNCH=1 bash Production/scripts/deploy_storyboard_v59.sh

set -euo pipefail

# ----------------------------------------------------------------
# Argument parsing — --event Event_N overrides the default Event_1 pin.
# ----------------------------------------------------------------
_ARG_EVENT_DIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --event)
            _ARG_EVENT_DIR="Production/${2:?'--event requires an event name, e.g. Event_2'}"
            shift 2
            ;;
        --event=*)
            _ARG_EVENT_DIR="Production/${1#--event=}"
            shift
            ;;
        *)
            echo "FATAL: unknown argument: $1" >&2
            echo "Usage: bash deploy_storyboard_v59.sh [--event Event_N]" >&2
            exit 1
            ;;
    esac
done

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

# ----------------------------------------------------------------
# (pre-A) Pre-deploy git-clean gate — LD CLAIM_TO_COMMIT_ENFORCEMENT_GATE_V1
# Closes the LD-738/766/767 fabrication class (M1 + M2 per Agent 1 audit
# 2026-05-17 ~17:30 UTC). Premise: BUILD_SHA at step (g) is derived from
# `git rev-parse --short HEAD`, which IGNORES uncommitted working-tree
# changes. A dirty tree deploys files that contain code never committed,
# under a build-sha that points at a stale HEAD. The pre-commit hook
# blocks Dropbox-tree edits but does NOT block the deploy from the tooling
# tree itself; this gate closes that gap.
#
# Per CLAUDE.md Rule 19 (no shortcuts): bypass requires MN_ALLOW_DIRTY_DEPLOY=1
# AND a SHORTCUT LD per the escape-hatch protocol.
# ----------------------------------------------------------------
(
    cd "$SRC_TOOLING"
    if [[ -n "$(git status --porcelain)" ]]; then
        echo "FATAL: tooling tree dirty — uncommitted edits will deploy under a stale build-sha" >&2
        echo "  (build-sha = git rev-parse --short HEAD, which does NOT see working-tree changes)" >&2
        git status --short >&2
        echo "  Resolve: commit/stash the listed paths, or set MN_ALLOW_DIRTY_DEPLOY=1" >&2
        echo "  Bypass requires SHORTCUT LD per CLAUDE.md Rule 19." >&2
        if [[ "${MN_ALLOW_DIRTY_DEPLOY:-}" == "1" ]]; then
            echo "[deploy] (pre-A) MN_ALLOW_DIRTY_DEPLOY=1 — gate bypassed (SHORTCUT LD required)" >&2
            exit 0
        fi
        exit 1
    fi
) || exit 1
echo "[deploy] (pre-A) git-clean gate ok — tooling tree clean"

UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
SNAPSHOT_DIR="$DEST_DROPBOX/.deploy_backups/$UTC_TS"
LOG_DIR="$SNAPSHOT_DIR/logs"

echo "[deploy] $(date -u +%FT%TZ)  STORYBOARD_DEPLOY_PROCESS_V1"
echo "  src:  $SRC_TOOLING"
echo "  dest: $DEST_DROPBOX"
echo "  snap: $SNAPSHOT_DIR"

# ----------------------------------------------------------------
# (a-pre) Build the v59 client bundle from source. Without this step,
# dist/index.html in tooling repo can drift behind src/ — manual partial
# deploys (the bug class LD STORYBOARD_DEPLOY_PROCESS_V1 prevents) often
# arose precisely from forgetting to rebuild. The script is the canonical
# gate; rebuilding here closes the gap.
# Skip via MN_DEPLOY_SKIP_BUILD=1 (e.g. when invoking from CI which has
# already built dist).
# ----------------------------------------------------------------
if [[ -z "${MN_DEPLOY_SKIP_BUILD:-}" ]]; then
    echo "[deploy] (a-pre) npm run build ..."
    (
        cd "$SRC_TOOLING/Production/tools/storyboard-v2"
        npm run build 2>&1 | tail -10
    )
fi

# ----------------------------------------------------------------
# (a-pre.5) Pre-deploy stale-build detection
# Per V59_CICD_GAP_FIX_SPEC_v1.md Phase A / LD DEPLOY_VERIFICATION_GATE_V1.
# Detect uncompiled .tsx/.ts edits — any source file newer than dist/index.html
# means dist is stale (build failed silently OR MN_DEPLOY_SKIP_BUILD=1 was set
# while source had moved on). FATAL on stale.
# ----------------------------------------------------------------
DIST_HTML_SRC="$SRC_TOOLING/Production/tools/storyboard-v2/dist/index.html"
if [[ ! -f "$DIST_HTML_SRC" ]]; then
    echo "FATAL: $DIST_HTML_SRC missing — run: cd Production/tools/storyboard-v2 && npm run build" >&2
    exit 1
fi
DIST_MTIME=$(stat -f %m "$DIST_HTML_SRC" 2>/dev/null || stat -c %Y "$DIST_HTML_SRC")
SRC_TSX_DIR="$SRC_TOOLING/Production/tools/storyboard-v2/src"
TSX_COUNT=$(find "$SRC_TSX_DIR" \( -name "*.tsx" -o -name "*.ts" \) -type f 2>/dev/null | wc -l | tr -d ' ')
if [[ "$TSX_COUNT" -lt 1 ]]; then
    echo "FATAL: no .tsx/.ts files found under $SRC_TSX_DIR — directory layout broken; surface to Kim" >&2
    exit 1
fi
STALE_FOUND=0
while IFS= read -r tsx; do
    [[ -z "$tsx" ]] && continue
    TSX_MTIME=$(stat -f %m "$tsx" 2>/dev/null || stat -c %Y "$tsx")
    if [[ "$TSX_MTIME" -gt "$DIST_MTIME" ]]; then
        echo "FATAL: ${tsx#$SRC_TOOLING/} is newer than dist/index.html — uncompiled changes." >&2
        STALE_FOUND=1
    fi
done < <(find "$SRC_TSX_DIR" \( -name "*.tsx" -o -name "*.ts" \) -type f 2>/dev/null)
if [[ "$STALE_FOUND" -eq 1 ]]; then
    echo "Run: cd Production/tools/storyboard-v2 && npm run build" >&2
    exit 1
fi
echo "[deploy] (a-pre.5) stale-build check ok ($TSX_COUNT .tsx/.ts source file(s) all older than dist/index.html)"

# ----------------------------------------------------------------
# (a-pre.6) Storyboard UI Feature Regression Guard — LD-766
# Greps dist/index.html for critical-feature markers before deploy.
# Fails loud (exit 1) if any feature regressed silently.
# Set MN_SKIP_REGRESSION_GUARD=1 to bypass (audit-trail only, NOT for normal use).
# ----------------------------------------------------------------
if [[ "${MN_SKIP_REGRESSION_GUARD:-0}" != "1" ]]; then
    GUARD_SCRIPT="$SRC_TOOLING/Production/scripts/check_storyboard_critical_features.sh"
    if [[ -x "$GUARD_SCRIPT" ]]; then
        if ! bash "$GUARD_SCRIPT"; then
            echo "[deploy] FATAL: regression guard failed — refusing to deploy." >&2
            echo "[deploy] Fix the missing marker(s) above OR set MN_SKIP_REGRESSION_GUARD=1 with audit reason." >&2
            exit 1
        fi
        echo "[deploy] (a-pre.6) LD-766 regression guard ok"
    else
        echo "[deploy] WARN: regression guard script missing at $GUARD_SCRIPT — skipping" >&2
    fi
    SESSION_DURABILITY_SCRIPT="$SRC_TOOLING/Production/scripts/verify_storyboard_session_durability.sh"
    if [[ -x "$SESSION_DURABILITY_SCRIPT" ]]; then
        if ! bash "$SESSION_DURABILITY_SCRIPT"; then
            echo "[deploy] FATAL: storyboard session durability guard failed." >&2
            exit 1
        fi
        echo "[deploy] (a-pre.6b) session durability ok (waveform, producer, seek, library audio, phase fades + pytest)"
    fi
else
    echo "[deploy] (a-pre.6) LD-766 regression guard SKIPPED (MN_SKIP_REGRESSION_GUARD=1)"
fi

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
        --exclude 'stitch_editor_state.json' \
        "$SRC_TOOLING/$sub/" \
        "$DEST_DROPBOX/$sub/" \
        2>&1 | tee "$LOG_DIR/rsync_${log_safe}.log"
    echo "  mirrored: $sub"
done

# ----------------------------------------------------------------
# (b.2) Per-file sync for Production/ root-level manifests.
# Blocker #160: smoke_test_manifest.yaml lived at Production/smoke_test_manifest.yaml
# (root of Production/, not under tools/lib/scripts subtrees) and was therefore
# silently EXCLUDED from the (b) rsync set. Result: manifest drift between
# tooling main and Dropbox runtime — event_smoke_test.sh on the Dropbox side
# would consume a stale manifest after the next tooling-side LD lock.
#
# Fix: explicit per-file cp for known Production/ root-level manifests. Add
# new manifests to this list when they're introduced; same dependency-order
# rule as the rsync subdirs above.
# ----------------------------------------------------------------
for manifest in smoke_test_manifest.yaml character_subjects.json; do
    src="$SRC_TOOLING/Production/$manifest"
    dest="$DEST_DROPBOX/Production/$manifest"
    if [[ -f "$src" ]]; then
        cp "$src" "$dest"
        echo "  mirrored: Production/$manifest"
    else
        echo "  WARN: $src missing in source; skip"
    fi
done

# ----------------------------------------------------------------
# (c) dist/index.html (built v59 client bundle) — copy to TWO destinations:
#   1. Production/tools/storyboard-v2/dist/index.html (canonical bundle path)
#   2. Each Production/Event_<N>/storyboard_v59_prod.html (the file
#      production_server.py serves at GET /). Without this per-event copy,
#      the deployed server still serves the old bundle.
# ----------------------------------------------------------------
DIST="$SRC_TOOLING/Production/tools/storyboard-v2/dist/index.html"
DIST_DEST="$DEST_DROPBOX/Production/tools/storyboard-v2/dist/index.html"
if [[ -f "$DIST" ]]; then
    mkdir -p "$(dirname "$DIST_DEST")"
    cp "$DIST" "$DIST_DEST"
    echo "[deploy] (c) dist/index.html copied to canonical bundle path"

    # Also fan out to each Event_*/storyboard_v59_prod.html in Dropbox.
    # production_server.py reads $event_dir/storyboard_v59_prod.html and
    # serves it at GET /. Each event must have a fresh copy of the bundle.
    fanout_count=0
    for ev_html in "$DEST_DROPBOX"/Production/Event_*/storyboard_v59_prod.html; do
        # Glob may be literal if no matches; guard with -e.
        # Glob may be literal if no matches; guard with -e.
        [[ -e "$ev_html" || -L "$ev_html" ]] || continue
        # Event_0 is a Milestone (opening_storybook) — exclude from Event fanout.
        [[ "$(basename "$(dirname "$ev_html")")" == "Event_0" ]] && continue
        cp "$DIST" "$ev_html"
        echo "  fanout: ${ev_html#$DEST_DROPBOX/}"
        fanout_count=$((fanout_count + 1))
    done
    # Also fan out to any Event_*/storyboard_v59_prod.html that doesn't yet
    # exist but the parent Event_* dir does — first-time deploy of a new event.
    for ev_dir in "$DEST_DROPBOX"/Production/Event_*/; do
        ev_dir="${ev_dir%/}"
        [[ -d "$ev_dir" ]] || continue
        # Event_0 is a Milestone (opening_storybook) — exclude from Event fanout.
        [[ "$(basename "$ev_dir")" == "Event_0" ]] && continue
        target="$ev_dir/storyboard_v59_prod.html"
        if [[ ! -e "$target" ]]; then
            cp "$DIST" "$target"
            echo "  fanout (first-time): ${target#$DEST_DROPBOX/}"
            fanout_count=$((fanout_count + 1))
        fi
    done
    echo "  total Event_* fanout: $fanout_count file(s)"
else
    echo "[deploy] (c) FATAL: dist/index.html missing in source — npm run build did not produce dist" >&2
    exit 1
fi

# ----------------------------------------------------------------
# (c.5) Post-deploy fanout sha256 verification
# Per V59_CICD_GAP_FIX_SPEC_v1.md Phase A / LD DEPLOY_VERIFICATION_GATE_V1.
# Confirms every Dropbox-side Event_*/storyboard_v59_prod.html matches the
# canonical dist/index.html sha256. Catches the "one fanout silently old"
# case (e.g. a copy interrupted by Dropbox sync conflict).
# ----------------------------------------------------------------
CANONICAL_SHA=$(shasum -a 256 "$DIST" | awk '{print $1}')
echo "[deploy] (c.5) canonical dist sha256: $CANONICAL_SHA"
fanout_verify_count=0
fanout_verify_failed=0
for fanout in "$DEST_DROPBOX"/Production/Event_*/storyboard_v59_prod.html; do
    [[ -f "$fanout" ]] || continue
    # Event_0 is a Milestone — excluded from fanout, so skip its SHA check too.
    [[ "$(basename "$(dirname "$fanout")")" == "Event_0" ]] && continue
    FANOUT_SHA=$(shasum -a 256 "$fanout" | awk '{print $1}')
    if [[ "$FANOUT_SHA" != "$CANONICAL_SHA" ]]; then
        echo "FATAL: ${fanout#$DEST_DROPBOX/} sha256 mismatch" >&2
        echo "  expected: $CANONICAL_SHA" >&2
        echo "  got:      $FANOUT_SHA" >&2
        fanout_verify_failed=1
    else
        fanout_verify_count=$((fanout_verify_count + 1))
    fi
done
if [[ "$fanout_verify_failed" -eq 1 ]]; then
    echo "Fanout sha256 mismatch — refusing to leave a partial deploy live." >&2
    exit 1
fi
echo "[deploy] (c.5) all $fanout_verify_count fanout copy(ies) match canonical sha256"

# ----------------------------------------------------------------
# (d) Per-file sha256 verification (FATAL on mismatch)
# ----------------------------------------------------------------
echo "[deploy] (d) sha256 verification..."
verify_files=(
    "Production/tools/production_server.py"
    "Production/tools/scope_router.py"
    "Production/tools/beat_generator.py"
    "Production/tools/kling_o3_element_beat_pipeline.py"
    "Production/tools/arlo_o3_voice_pipeline.py"
    "Production/tools/server_handlers/background.py"
    "Production/tools/server_handlers/kling_o3.py"
    "Production/tools/kling_o3_job_store.py"
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
# (d.5) Full-tree sha256 parity for O3 + intro critical paths
# ----------------------------------------------------------------
echo "[deploy] (d.5) tooling↔Dropbox parity check..."
MN_TOOLING_ROOT="$SRC_TOOLING" MN_DROPBOX_ROOT="$DEST_DROPBOX" \
    python3 "$SRC_TOOLING/Production/scripts/verify_tooling_dropbox_parity.py"

# ----------------------------------------------------------------
# (d.6) O3 + intro contract pytest gate (blocks partial backup restores)
# ----------------------------------------------------------------
echo "[deploy] (d.6) O3/intro contract gate..."
bash "$SRC_TOOLING/Production/scripts/verify_o3_intro_contract.sh"

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

EVENT_DIR="${_ARG_EVENT_DIR:-${MN_EVENT_DIR:-}}"
if [[ -z "$EVENT_DIR" ]]; then
    PIN_FILE="$DEST_DROPBOX/Production/server_event_pin.json"
    if [[ -f "$PIN_FILE" ]]; then
        PIN_EVENT="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); e=(d.get('event_id') or '').strip(); print(f'Production/{e}' if e else '')" "$PIN_FILE" 2>/dev/null || true)"
        if [[ -n "$PIN_EVENT" ]]; then
            EVENT_DIR="$PIN_EVENT"
            echo "[deploy] (f) default event from server_event_pin.json → $EVENT_DIR"
        fi
    fi
fi
EVENT_DIR="${EVENT_DIR:-Production/Event_1}"
# MN_EVENT_DIR is sometimes set to an absolute Dropbox path; production_server
# expects a path relative to the Dropbox runtime root.
if [[ "$EVENT_DIR" == "$DEST_DROPBOX/"* ]]; then
    EVENT_DIR="${EVENT_DIR#"$DEST_DROPBOX/"}"
elif [[ "$EVENT_DIR" == /* && "$EVENT_DIR" =~ /Production/(Event_[^/]+)$ ]]; then
    EVENT_DIR="Production/${BASH_REMATCH[1]}"
fi
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

nohup env PRODUCTION_SERVER_SINGLE_MACHINE=1 python3 "$DEST_DROPBOX/Production/tools/production_server.py" \
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

# ----------------------------------------------------------------
# (g) Post-deploy curl smoke — verify served HTML carries fresh build-sha
# Per V59_CICD_GAP_FIX_SPEC_v1.md Phase A / LD DEPLOY_VERIFICATION_GATE_V1.
# CRITICAL: URL is /, NOT /storyboard_v59_prod.html. production_server.py
# serves the SPA at root; the filename CLI arg is the disk path it READS,
# never part of the URL. A probe against the filename path returns 404
# {"error":"not found"} by design (per feedback_storyboard_url_serves_at_root.md
# after 2026-05-07 sidefix bug).
# ----------------------------------------------------------------
SERVER_PORT="${MN_SERVER_PORT:-5111}"
BUILD_SHA="$(cd "$SRC_TOOLING" && git rev-parse --short HEAD 2>/dev/null || git log -1 --pretty=%h 2>/dev/null || true)"
if [[ -z "$BUILD_SHA" ]]; then
    echo "FATAL: could not determine BUILD_SHA from git rev-parse or git log" >&2
    exit 1
fi
echo "[deploy] (g) post-deploy curl smoke: probing http://localhost:${SERVER_PORT}/ for build-sha=$BUILD_SHA"
sleep 2  # let server settle after restart
SERVED="$(curl -sS --max-time 10 "http://localhost:${SERVER_PORT}/" 2>/dev/null || true)"
if [[ -z "$SERVED" ]]; then
    echo "[deploy] (g) curl returned empty; retrying once after 5s ..."
    sleep 5
    SERVED="$(curl -sS --max-time 10 "http://localhost:${SERVER_PORT}/" 2>/dev/null || true)"
fi
MARKER_COUNT=$(printf "%s" "$SERVED" | grep -c "build-sha.*$BUILD_SHA" || true)
if [[ "$MARKER_COUNT" -lt 1 ]]; then
    echo "FATAL: served HTML at http://localhost:${SERVER_PORT}/ does not contain build-sha=$BUILD_SHA (matches=$MARKER_COUNT)" >&2
    echo "  Server may be serving stale content. Verify:" >&2
    echo "    (1) URL is /, NOT /storyboard_v59_prod.html (production_server.py serves SPA at root)" >&2
    echo "    (2) build emitted <meta name='build-sha' content='$BUILD_SHA'> into dist/index.html" >&2
    echo "    (3) deploy step actually copied dist → Event_*/storyboard_v59_prod.html (see (c) above)" >&2
    echo "  Diagnostic dump:" >&2
    lsof -ti:"$SERVER_PORT" >&2 || true
    pgrep -fl production_server.py >&2 || true
    exit 1
fi
echo "[deploy] (g) curl smoke ok — server serving fresh build (sha=$BUILD_SHA, marker_matches=$MARKER_COUNT)"

# ----------------------------------------------------------------
# (g.5) Pin runtime event to deployed event dir (not stale launch argv)
# ----------------------------------------------------------------
echo "[deploy] (g.5) post-restart event/load pin for $event_id ..."
LOAD_HTTP=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 \
    -X POST "http://localhost:${SERVER_PORT}/api/event/load" \
    -H "Content-Type: application/json" \
    -d "{\"event_id\":\"${event_id}\"}" || echo "000")
if [[ "$LOAD_HTTP" != "200" ]]; then
    echo "FATAL: /api/event/load for $event_id returned HTTP $LOAD_HTTP" >&2
    tail -20 "$LOG_DIR/server.log" >&2 || true
    exit 1
fi
echo "[deploy] (g.5) event/load ok — runtime pinned to $event_id"

# ----------------------------------------------------------------
# (g.6) Sync launchd KeepAlive agent to deployed event (EVENT_LAUNCHAGENT_SYNC_V1)
# ----------------------------------------------------------------
echo "[deploy] (g.6) syncing production-server launch agent for $event_id ..."
chmod +x "$SRC_TOOLING/Production/scripts/install_production_server_launchagent.sh"
bash "$SRC_TOOLING/Production/scripts/install_production_server_launchagent.sh" "$event_id"
echo "[deploy] (g.6) launch agent ok"

# ----------------------------------------------------------------
# (h) Post-restart O3 sidecar API smoke — server must expose lock API live
# ----------------------------------------------------------------
echo "[deploy] (h) O3 capability smoke via /api/bg/session-state ..."
O3_OK=$(curl -sS --max-time 15 \
    "http://localhost:${SERVER_PORT}/api/bg/session-state?scope_event_id=${event_id}&scope_video_role=intro" \
    | python3 -c "import sys,json; c=json.load(sys.stdin).get('capabilities') or {}; print('ok' if c.get('update_beat_locked') and c.get('sidecar_file_lock') else 'fail')" \
    2>/dev/null || echo "fail")
if [[ "$O3_OK" != "ok" ]]; then
    echo "FATAL: live server capabilities missing update_beat_locked/sidecar_file_lock (got: $O3_OK)" >&2
    tail -20 "$LOG_DIR/server.log" >&2 || true
    exit 1
fi
echo "[deploy] (h) O3 capability smoke ok"

# ----------------------------------------------------------------
# (h.5) Post-restart Kling canonical prompt shape — migrate heal on session-state
# ----------------------------------------------------------------
echo "[deploy] (h.5) Kling canonical prompt shape live smoke (Event_2) ..."
chmod +x "$SRC_TOOLING/Production/scripts/smoke_kling_canonical_prompt_shape_live.sh"
if ! bash "$SRC_TOOLING/Production/scripts/smoke_kling_canonical_prompt_shape_live.sh"; then
    echo "FATAL: Kling canonical prompt shape live smoke failed after restart" >&2
    tail -30 "$LOG_DIR/server.log" >&2 || true
    exit 1
fi
echo "[deploy] (h.5) Kling canonical prompt shape ok"

# ----------------------------------------------------------------
# (i) Write .last_deploy timestamp sentinel
# Per V59_CICD_GAP_FIX_SPEC_v1.md Phase G — pre-commit hook reads this
# to detect "Dropbox runtime tree edited after last deploy" divergence.
# ----------------------------------------------------------------
date +%s > "$SRC_TOOLING/.last_deploy"
echo "[deploy] (i) .last_deploy timestamp written: $(cat "$SRC_TOOLING/.last_deploy")"

echo "[deploy] complete  snapshot=$SNAPSHOT_DIR  log=$LOG_DIR/server.log"

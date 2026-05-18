#!/usr/bin/env bash
# event_smoke_test.sh — Layer 1 verification gate for storyboard feature symbols.
# Per LD-782 EVENT_SMOKE_TEST_LAYER1_V1 (locked 2026-05-17).
#
# Greps the deployed event bundle for symbols listed in
# Production/smoke_test_manifest.yaml. Writes a prod_activity_log row via
# try_post_or_queue per run (read-back-after-write, Rule 35 symmetric).
#
# Usage:
#   bash event_smoke_test.sh                       # default Event_1
#   bash event_smoke_test.sh Event_2
#   bash event_smoke_test.sh Event_1 --no-sentinel # skip deploy-marker wait
#   bash event_smoke_test.sh --manifest X --bundle Y --source Z
#   bash event_smoke_test.sh --no-directus         # skip Directus write (dev)
#
# Exit codes:
#   0  all green
#   1  manifest missing/unreadable
#   2  bundle missing/unreadable
#   3  required symbol absent (FATAL — block deploy)
#   4  known_red entry now present (WARN — allow but log)
#   5  Directus write failed (FATAL — no green claim without row)

set -euo pipefail

EVENT="Event_1"
MANIFEST=""
BUNDLE=""
SOURCE=""
SKIP_SENTINEL=0
SKIP_DIRECTUS=0
SENTINEL_TIMEOUT_S=30

while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest)     MANIFEST="$2"; shift 2 ;;
        --bundle)       BUNDLE="$2"; shift 2 ;;
        --source)       SOURCE="$2"; shift 2 ;;
        --no-sentinel)  SKIP_SENTINEL=1; shift ;;
        --no-directus)  SKIP_DIRECTUS=1; shift ;;
        --help|-h)
            grep '^#' "$0" | head -30
            exit 0 ;;
        Event_*)        EVENT="$1"; shift ;;
        *)
            echo "FATAL: unknown arg: $1" >&2
            exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

[[ -z "$MANIFEST" ]] && MANIFEST="$PROJECT_ROOT/Production/smoke_test_manifest.yaml"
[[ -z "$BUNDLE"   ]] && BUNDLE="$PROJECT_ROOT/Production/$EVENT/storyboard_v59_prod.html"
if [[ ! -f "$BUNDLE" ]]; then
    _fixture_bundle="$PROJECT_ROOT/Production/Event_e2e_fixture/storyboard_v59_prod.html"
    if [[ -f "$_fixture_bundle" ]]; then
        echo "[smoke] bundle fallback: $_fixture_bundle (primary absent: $BUNDLE)" >&2
        BUNDLE="$_fixture_bundle"
    fi
fi
[[ -z "$SOURCE"   ]] && SOURCE="$PROJECT_ROOT/Production/tools/storyboard-v2/src/components/StoryboardTab.tsx"
# LD-730 cross-thread integration (2026-05-17): server + kling targets so the
# OpenAI gpt-image-1 end-frame vendor swap is gated by the same Layer-1 grep
# manifest. Implementation lives in production_server.py + kling_startend_pipeline.py,
# not StoryboardTab.tsx, so the existing source target won't reach it. Additive
# only — does not affect any existing manifest entry.
SERVER_PY="$PROJECT_ROOT/Production/tools/production_server.py"
KLING_PY="$PROJECT_ROOT/Production/tools/kling_startend_pipeline.py"

if [[ ! -f "$MANIFEST" ]]; then
    echo "FATAL: manifest not found: $MANIFEST" >&2
    exit 1
fi
if [[ ! -f "$BUNDLE" ]]; then
    _primary_bundle="$PROJECT_ROOT/Production/$EVENT/storyboard_v59_prod.html"
    _fixture_bundle="$PROJECT_ROOT/Production/Event_e2e_fixture/storyboard_v59_prod.html"
    echo "FATAL: bundle not found: $BUNDLE" >&2
    echo "FATAL: tried primary ($_primary_bundle) and fixture ($_fixture_bundle)" >&2
    echo "FATAL: pass --bundle <path> or generate storyboard_v59_prod.html" >&2
    exit 2
fi

# ----------------------------------------------------------------
# Anti-self-reference (Counter 1 hardening item 4) — manifest path
# excluded from grep target list; assert distinct inodes.
# ----------------------------------------------------------------
manifest_inode=$(stat -f %i "$MANIFEST" 2>/dev/null || stat -c %i "$MANIFEST" 2>/dev/null || echo "")
bundle_inode=$(stat -f %i "$BUNDLE" 2>/dev/null || stat -c %i "$BUNDLE" 2>/dev/null || echo "")
if [[ -n "$manifest_inode" ]] && [[ "$manifest_inode" == "$bundle_inode" ]]; then
    echo "FATAL: manifest and bundle are the same inode (config error)" >&2
    exit 1
fi

# ----------------------------------------------------------------
# Deploy-completion sentinel wait (hardening item 4).
# If $EVENT/.deploy_complete exists, wait up to ${SENTINEL_TIMEOUT_S}s
# for its mtime to be >= bundle mtime. No sentinel = no wait.
# ----------------------------------------------------------------
if [[ "$SKIP_SENTINEL" -eq 0 ]]; then
    SENTINEL="$PROJECT_ROOT/Production/$EVENT/.deploy_complete"
    if [[ -f "$SENTINEL" ]]; then
        bundle_mtime=$(stat -f %m "$BUNDLE" 2>/dev/null || stat -c %Y "$BUNDLE")
        elapsed=0
        while [[ "$elapsed" -lt "$SENTINEL_TIMEOUT_S" ]]; do
            sentinel_mtime=$(stat -f %m "$SENTINEL" 2>/dev/null || stat -c %Y "$SENTINEL")
            if [[ "$sentinel_mtime" -ge "$bundle_mtime" ]]; then
                break
            fi
            sleep 1
            elapsed=$((elapsed + 1))
        done
        if [[ "$elapsed" -ge "$SENTINEL_TIMEOUT_S" ]]; then
            echo "WARN: deploy sentinel did not catch up to bundle mtime within ${SENTINEL_TIMEOUT_S}s — proceeding anyway" >&2
        fi
    fi
fi

BUNDLE_SHA=$(shasum -a 256 "$BUNDLE" | awk '{print $1}')
MANIFEST_SHA=$(shasum -a 256 "$MANIFEST" | awk '{print $1}')

# ----------------------------------------------------------------
# Parse manifest entries (flow-style YAML).
# Python parser — BSD awk on macOS lacks 3-arg match() (GNU-only).
# Per DS-22 catch 2026-05-17 (awk parser silently produced 0 entries +
# false-green). [CONFIRMED against bash session log
# Production/docs/morph_fix_a_v2_evidence_20260518/awk_parser_failure.log
# — the awk version of this loop returned exit 0 with CHECKED=0, masking
# all marker failures.] Python is robust + cross-platform + already in
# dep chain.
# Each line: - { ld: X, symbol: 'Y', kind: Z, [target: T,] [status: S,] ... }
# ----------------------------------------------------------------
parse_entries() {
    PARSE_PY="${MN_PYENV_PY:-$HOME/.pyenv/versions/3.12.7/bin/python3}"
    [[ -x "$PARSE_PY" ]] || PARSE_PY="$(command -v python3)"
    "$PARSE_PY" - "$MANIFEST" <<'PYEOF'
import re, sys
with open(sys.argv[1], encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        stripped = line.strip()
        if not stripped.startswith("- {"):
            continue
        def get(key, default=""):
            # Try single-quoted value first; fall back to unquoted
            m = re.search(rf"\b{key}:\s*'([^']*)'", line)
            if m:
                return m.group(1)
            m = re.search(rf"\b{key}:\s*([^,}}]+)", line)
            if m:
                return m.group(1).strip()
            return default
        ld = get("ld")
        sym = get("symbol")
        kind = get("kind")
        target = get("target", "bundle")
        status = get("status", "active")
        regex_flag = get("regex", "false")
        min_matches = get("min_matches", "1")
        if not sym:
            continue
        # TAB delimiter — pipe `|` collides with regex patterns like
        # `tile-tier.*(master|delivery)` (DS-22 catch 2026-05-17).
        print("\t".join([ld, sym, kind, target, status, regex_flag, min_matches]))
PYEOF
}

MISSING=()
STALE_RED=()
CHECKED=0
PASSED=0

echo "[smoke] event=$EVENT bundle=$(basename "$BUNDLE") manifest=$(basename "$MANIFEST")"
echo "[smoke] bundle_sha=${BUNDLE_SHA:0:12}  manifest_sha=${MANIFEST_SHA:0:12}"

while IFS=$'\t' read -r ld sym kind target status regex_flag min_matches; do
    [[ -z "$sym" ]] && continue
    CHECKED=$((CHECKED + 1))

    case "$target" in
        source) tgt_file="$SOURCE" ;;
        server) tgt_file="$SERVER_PY" ;;
        kling)  tgt_file="$KLING_PY" ;;
        both)   tgt_file="$BUNDLE" ;;
        bundle|*) tgt_file="$BUNDLE" ;;
    esac

    # Defensive guard: min_matches must be numeric (catches IFS-shift bugs).
    if ! [[ "$min_matches" =~ ^[0-9]+$ ]]; then
        echo "WARN: $ld $sym min_matches='$min_matches' non-numeric — defaulting to 1" >&2
        min_matches=1
    fi

    if [[ ! -f "$tgt_file" ]]; then
        echo "  SKIP      $ld $sym (target file missing: $(basename "$tgt_file"))"
        continue
    fi

    if [[ "$regex_flag" == "true" ]]; then
        cnt=$(grep -cE "$sym" "$tgt_file" 2>/dev/null || true)
    else
        cnt=$(grep -cF "$sym" "$tgt_file" 2>/dev/null || true)
    fi
    [[ -z "$cnt" ]] && cnt=0

    if [[ "$cnt" -ge "$min_matches" ]]; then
        if [[ "$status" =~ ^known_red ]]; then
            echo "  STALE-RED $ld $sym (now present in $(basename "$tgt_file") — manifest needs update)"
            STALE_RED+=("$ld:$sym")
        else
            PASSED=$((PASSED + 1))
            echo "  ok        $ld $sym ($cnt matches in $(basename "$tgt_file"))"
        fi
    else
        if [[ "$status" =~ ^known_red ]]; then
            echo "  known_red $ld $sym (expected absent in $(basename "$tgt_file"))"
        else
            echo "  MISSING   $ld $sym in $(basename "$tgt_file")"
            MISSING+=("$ld:$sym")
        fi
    fi
done < <(parse_entries)

echo "[smoke] checked=$CHECKED passed=$PASSED missing=${#MISSING[@]} stale_red=${#STALE_RED[@]}"

EXIT_CODE=0
if [[ "${#MISSING[@]}" -gt 0 ]]; then
    EXIT_CODE=3
elif [[ "${#STALE_RED[@]}" -gt 0 ]]; then
    EXIT_CODE=4
fi

# ----------------------------------------------------------------
# Mandatory Directus write — Counter 1 hardening item 3.
# No row = no green claim. Closes the smoke-result-fabrication class.
# ----------------------------------------------------------------
if [[ "$SKIP_DIRECTUS" -eq 0 ]]; then
    UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)

    PYENV_PY="${MN_PYENV_PY:-$HOME/.pyenv/versions/3.12.7/bin/python3}"
    [[ -x "$PYENV_PY" ]] || PYENV_PY="$(command -v python3)"

    DETAILS_FILE=$(mktemp /tmp/smoke_details.XXXXXX.json)
    trap 'rm -f "$DETAILS_FILE"' EXIT

    # Build details JSON in pure bash (avoid heredoc array-passing quirks).
    {
        printf '{\n'
        printf '  "event": "%s",\n' "$EVENT"
        printf '  "bundle_sha256": "%s",\n' "$BUNDLE_SHA"
        printf '  "manifest_sha256": "%s",\n' "$MANIFEST_SHA"
        printf '  "bundle_path": "%s",\n' "$BUNDLE"
        printf '  "manifest_path": "%s",\n' "$MANIFEST"
        printf '  "checked": %d,\n' "$CHECKED"
        printf '  "passed": %d,\n' "$PASSED"
        printf '  "exit_code": %d,\n' "$EXIT_CODE"
        printf '  "ld_governing": "LD-782 EVENT_SMOKE_TEST_LAYER1_V1",\n'
        printf '  "missing": ['
        first=1
        for m in ${MISSING[@]+"${MISSING[@]}"}; do
            [[ $first -eq 1 ]] && first=0 || printf ', '
            printf '"%s"' "$m"
        done
        printf '],\n'
        printf '  "stale_red": ['
        first=1
        for s in ${STALE_RED[@]+"${STALE_RED[@]}"}; do
            [[ $first -eq 1 ]] && first=0 || printf ', '
            printf '"%s"' "$s"
        done
        printf ']\n'
        printf '}\n'
    } > "$DETAILS_FILE"

    echo "[smoke] writing event_smoke_test_run_${UTC_TS} to prod_activity_log..."
    if ! "$PYENV_PY" "$SCRIPT_DIR/_smoke_directus_writer.py" \
            --action "event_smoke_test_run_${UTC_TS}" \
            --details-file "$DETAILS_FILE"; then
        echo "FATAL: Directus write failed — NO GREEN CLAIM per LD-782" >&2
        echo "  Check pending_directus_writes.json for queued payload" >&2
        EXIT_CODE=5
    fi
fi

case "$EXIT_CODE" in
    0) echo "[smoke] GREEN (event=$EVENT, $PASSED/$CHECKED checks passed)" ;;
    3) echo "[smoke] FATAL exit=3: ${#MISSING[@]} required symbol(s) missing" >&2 ;;
    4) echo "[smoke] WARN  exit=4: ${#STALE_RED[@]} known_red entry now present — update manifest" >&2 ;;
    5) echo "[smoke] FATAL exit=5: Directus write failed" >&2 ;;
esac

exit "$EXIT_CODE"

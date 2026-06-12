#!/usr/bin/env bash
# check_storyboard_critical_features.sh — pre-deploy marker check
#
# Per LD-766 STORYBOARD_UI_FEATURE_REGRESSION_GUARD_V1 (locked 2026-05-17,
# SHIPPED 2026-05-20 after fabrication-scan caught LD-766 as locked-without-
# implementation per Kim 2026-05-20 directive).
#
# Greps the freshly-built dist/index.html for a curated list of literal UI
# markers each tied to a shipped feature LD. If any marker is missing, the
# deploy aborts with exit 1 and names the missing LD.
#
# CALLED BY: Production/scripts/deploy_storyboard_v59.sh AFTER stale-build
# validation and BEFORE the pre-deploy snapshot (per LD-766 §1).
#
# CONTRACT for new LDs: Every NEW UI feature LD must add its marker to the
# MARKERS array in the same change that ships the feature. Superseded
# markers are removed in the same change that supersedes the LD.
#
# Exit codes:
#   0 — all markers found
#   1 — one or more markers missing (prints which + names the LD)
#   2 — dist/index.html not found

set -euo pipefail

# Resolve repo root from script location (Production/scripts/ → tooling root).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST="${REPO_ROOT}/Production/tools/storyboard-v2/dist/index.html"

if [[ ! -f "${DIST}" ]]; then
    echo "[regression-guard] FATAL: dist/index.html not found at ${DIST}" >&2
    echo "[regression-guard] Run 'npm run build' in Production/tools/storyboard-v2/ first." >&2
    exit 2
fi

# MARKERS array — each entry is "LD_TAG|literal_string_to_grep_for"
# The literal must appear in dist/index.html (post-Vite-build, inlined JS/CSS).
# Keep markers SHORT + DISTINCTIVE — common words risk false matches.
#
# IMPORTANT — marker selection rules:
# Vite minifies/mangles JS variable + function + class names. ONLY use
# strings that survive the build:
#   - data-testid values (string literals, not mangled)
#   - CSS class names (string literals)
#   - Displayed UI text (string literals in JSX)
#   - State-key strings used in object literals
# DO NOT use:
#   - Function names (e.g. guardedClick, onApplyTrim) — mangled
#   - State variable names (e.g. trimFrontSec) — mangled
#   - React/Preact component class names — mangled
#
MARKERS=(
    # LD-139 / LD-763 — Use as Final + Undo Final (displayed text)
    "LD-139|Use as Final"
    "LD-763|Undo Final"
    # LD-729 — Suggest parenthetical (displayed text)
    "LD-729|Suggest"
    # LD-746 — Kim done checkbox (data-testid)
    "LD-746|kim-done"
    # LD-755 — Preview Trim button (displayed text)
    "LD-755|Preview Trim"
    # LD-756 — Trim seconds-from-front/back (displayed text + data-testid)
    "LD-756|Trim front"
    "LD-756|trim-front"
    "LD-756|trim-back"
    # LD-784 — MASTER/DELIVERY tile-tier badge (CSS class names)
    "LD-784|mn-badge-master"
    "LD-784|mn-badge-delivery"
    # LD-809 — stale lipsync image_changed flag + displayed badge
    "LD-809|image_changed"
    "LD-809|stale lipsync"
    "LD-809|mn-btn-stale"
    # LD-826 — Stitcher multi-phase track + persisted selection
    "LD-826|stitcher-multiphase-track"
    "LD-826|selection persists per event"
    # LD-827 — Stitcher viewer instant /files fallback while module preview bakes
    "LD-827|LD-827 instant slot preview"
    # Phase stem trim + reject lipsync (2026-06-10)
    "PHASE_STEM_TRIM|waveform-stem-cut-block"
    "PHASE_STEM_TRIM|Reject lipsync"
    "PHASE_STEM_TRIM|Trim voice stem"
    "PHASE_STEM_TRIM|Clear selection"
    "PHASE_STEM_TRIM|Apply Cut"
    "PHASE_STEM_TRIM|Drag gold handles · amber = section to remove"
    "PHASE_STEM_TRIM|waveform-seek-layer"
    # Phase lipsync tab-switch durability (2026-06-12)
    "PHASE_LIPSYNC|Safe to switch tabs"
    "PHASE_LIPSYNC|Lipsync in progress"
    "PHASE_LIPSYNC|pane-phase-a-keepalive"
    "PHASE_LIPSYNC|pane-phase-b-keepalive"
    # Baseline buttons — every beat should have these (displayed text)
    "BASELINE|Regen Audio"
    "BASELINE|Regenerate B"
)

missing_count=0
missing_list=()

for entry in "${MARKERS[@]}"; do
    ld_tag="${entry%%|*}"
    needle="${entry#*|}"
    if ! grep -q -- "${needle}" "${DIST}"; then
        echo "[regression-guard] MISSING ${ld_tag}: marker '${needle}' not found in dist/index.html" >&2
        missing_list+=("${ld_tag}:'${needle}'")
        missing_count=$((missing_count + 1))
    fi
done

if [[ ${missing_count} -gt 0 ]]; then
    echo "" >&2
    echo "[regression-guard] FAIL: ${missing_count} marker(s) missing from dist/index.html:" >&2
    for m in "${missing_list[@]}"; do
        echo "  - ${m}" >&2
    done
    echo "" >&2
    echo "[regression-guard] This means a UI feature regressed between the prior" >&2
    echo "[regression-guard] working build and this one. DO NOT DEPLOY." >&2
    echo "[regression-guard] Either restore the feature OR update the MARKERS" >&2
    echo "[regression-guard] array in this script if the LD was intentionally" >&2
    echo "[regression-guard] superseded (and reference the new LD)." >&2
    exit 1
fi

echo "[regression-guard] OK — all ${#MARKERS[@]} markers present in dist/index.html"
exit 0

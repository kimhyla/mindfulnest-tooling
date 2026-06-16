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
    # LD-827 — processed per-slot preview in composer (raw /files fallback while baking)
    "LD-827|building processed preview"
    # LD-828 — single slot composer (multi-phase track switches processed preview)
    "LD-828|STITCHER_SINGLE_COMPOSER_V1"
    "LD-828|click a phase to switch slot review"
    # LD-829 — Phase A tab single canonical player (stitched when fresh; no duplicate video)
    "LD-829|PHASE_A_SINGLE_PLAYER_V1"
    "LD-829|Preview (canonical stitched — lipsync + ambient bed):"
    # STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1 — decode-validated preview cache + black-video fallback
    "STITCH_SLOT_PREVIEW|STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1"
    # STITCH_CANONICAL_TRANSITIONS_V1 + boundary magic SFX on dissolve
    "STITCH_CANONICAL_TRANSITIONS|STITCH_CANONICAL_TRANSITIONS_V1"
    "STITCH_CANONICAL_TRANSITIONS|STITCH_CANONICAL_TRANSITION_SFX_V1"
    # Library audio preview (sfx/ambient/transitions tiers)
    "LIBRARY_AUDIO_PREVIEW|LIBRARY_AUDIO_PREVIEW_V1"
    "LIBRARY_AUDIO_PREVIEW|library-preview-audio"
    # Stitcher SFX timeline blocks (WaveformTimeline parity — Phase 2)
    "STITCHER_SFX_TIMELINE|STITCHER_SFX_TIMELINE_V1"
    "STITCHER_SFX_TIMELINE|mn-stitcher-sfx-cue-block"
    # Stitcher slot composer — synced video + waveform (Phase A/B parity)
    "STITCHER_SLOT_COMPOSER|STITCHER_SLOT_COMPOSER_V1"
    "STITCHER_SLOT_COMPOSER|stitcher-slot-composer"
    "STITCHER_SLOT_COMPOSER|stitcher-composer-video"
    "STITCHER_SLOT_COMPOSER|Video + waveform stay in sync"
    # STITCHER_AMBIENT — ambient preset mixed into composer waveform extract
    "STITCHER_AMBIENT|STITCHER_AMBIENT_WAVEFORM_V1"
    "STITCHER_AMBIENT|data-stitcher-ambient-waveform"
    "STITCHER_AMBIENT|STITCH_AMBIENT_BED_VOLUME_V1"
    "STITCHER_AMBIENT|STITCH_SLOT_AUDIO_MIX_V1"
    "STITCHER_AMBIENT|STITCH_DEFAULT_AMBIENT_BEDS_V1"
    "STITCHER_AMBIENT|STITCH_AMBIENT_VOLUME_PERSIST_V1"
    # Stitcher SFX timeline — video_dur hydration + remix gating (2026-06-12)
    "STITCHER_SFX|STITCH_SLOT_VIDEO_DUR_V1"
    "STITCHER_SFX|data-mix-extracting"
    "STITCHER_SFX|Remixing slot audio"
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
    # Phase waveform playback — keep-alive mounts A+B; pause hidden + playback bus (2026-06-12)
    "PHASE_WAVEFORM_PLAY|Playback failed"
    "PHASE_WAVEFORM_PLAY|mn-waveform-source-label"
    "PHASE_WAVEFORM_PLAY|do not drag the waveform at the same time"
    "PHASE_WAVEFORM_PLAY|waveform-play-btn"
    "PHASE_WAVEFORM_PLAY|attributeFilter"
    "PHASE_WAVEFORM_PLAY|stop-all-audio-btn"
    "PHASE_WAVEFORM_PLAY|PHASE_WAVEFORM_PAUSE_V1"
    # Phase A/B producer overlay + animated chromakey canvas (2026-06-12)
    "PHASE_WATERCOLOR_OVERLAY|PHASE_WATERCOLOR_OVERLAY_V1"
    "PHASE_WATERCOLOR_OVERLAY|watercolor-anim-overlay"
    "PHASE_PRODUCER_AB|PHASE_PRODUCER_AB_V1"
    "PHASE_PRODUCER_AB|phase-producer-"
    "PHASE_PRODUCER_AB|onPlayStateChange"
    # Baseline buttons — every beat should have these (displayed text)
    "BASELINE|Regen Audio"
    "BASELINE|Regenerate B"
    # O3 generation intent snapshot — prompt lock + submit audit strip (2026-06-15)
    "O3_INTENT_SNAPSHOT|mn-bg-o3-intent-audit"
    "O3_INTENT_SNAPSHOT|bg-o3-intent-audit"
    "O3_INTENT_SNAPSHOT|Generation in progress — prompt locked to submitted intent."
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

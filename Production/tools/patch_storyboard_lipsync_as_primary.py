#!/usr/bin/env python3
"""
Path B patch (Rule 7): when a beat has a completed lipsync, show the lipsync
video as the PRIMARY video in the .mn-anim-opt.selected slot — replacing the
raw Kling clip (which has no audio).

Behavior changes (runtime):
 1. For each beat where lipsync.status === "completed" AND lipsync.url exists:
      - The <video> inside .mn-anim-opt.selected has its src swapped to the
        lipsync file (SERVER + lipsync.url).
      - A small "✨ with lipsync" label is appended below the selected card.
      - Non-selected option cards are untouched — user can still click them
        and the radio onchange will fire selectBeat() → server updates
        selected_option → next pollStatus rebuilds the section and the swap
        re-applies (or doesn't, if the new selection doesn't match
        lipsync.source_option).
 2. If lipsync.source_option is set AND does not match the currently selected
    option, the swap is SKIPPED for that beat — raw Kling stays visible and
    the existing "source_changed" lipsync button UI surfaces the "Re-run"
    prompt as before.
 3. Beats without a completed lipsync: no change.
 4. The existing "✅ Lip Sync Done — Preview" button + preview row stay
    untouched so the user can still toggle between raw and lipsynced via
    that button if desired.

JS injection strategy (keeps existing Tier 5 IIFE intact):
  A. Two in-place edits to the existing lip-sync IIFE:
       - applyCompletedButtonState(): after it sets video.src for the preview,
         also call window._swapVideoSrcForLipsync() so status transitions
         (polling → done) propagate to the main video.
       - createLipSyncRow(): after it registers _lipsyncRows[beatKey], also
         call window._swapVideoSrcForLipsync() so first-render is correct.
  B. Append a NEW IIFE at the end of the <script> block that defines
     window._swapVideoSrcForLipsync, wraps injectAnimationsFromStatus so the
     swap re-applies after every /api/animate/status poll re-renders the
     .mn-anim-section, and runs an independent 10s /api/lipsync/status
     refresher.

Verifies base64 image count + byte-identical content before writing output.
"""
import re
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# JS to inject
# ----------------------------------------------------------------------------

# Single-line additions inside the existing IIFE.
# 1) After the video.src = ... line in applyCompletedButtonState
APPLY_STATE_MARKER = "if (video && bs.url) video.src = SERVER + bs.url;"
APPLY_STATE_REPLACEMENT = (
    "if (video && bs.url) video.src = SERVER + bs.url;\n"
    "        if (window._swapVideoSrcForLipsync) "
    "window._swapVideoSrcForLipsync({ beats: (function(){ var o={}; o[beatKey]=bs; return o; })() });"
)

# 2) After the _lipsyncRows[beatKey] = {...}; line in createLipSyncRow
REGISTRY_MARKER = "_lipsyncRows[beatKey] = {"
# We insert a new line AFTER the closing "};" of that object literal.
# To avoid matching the closing brace of the function, we target the exact
# multi-line block.
REGISTRY_BLOCK_OLD = (
    "_lipsyncRows[beatKey] = {\n"
    "            btn: lsBtn, stat: lsStat, video: lsVideo, preview: lsPreview,\n"
    "        };"
)
REGISTRY_BLOCK_NEW = (
    "_lipsyncRows[beatKey] = {\n"
    "            btn: lsBtn, stat: lsStat, video: lsVideo, preview: lsPreview,\n"
    "        };\n"
    "        // Path B (April 17 2026): swap the main .mn-anim-opt.selected video to\n"
    "        // the lipsync file on first-render if status is already completed.\n"
    "        if (window._swapVideoSrcForLipsync) window._swapVideoSrcForLipsync(statusData);"
)

# New IIFE appended right after the existing lip-sync IIFE.
NEW_IIFE = """

// === LIP SYNC VIDEO-SRC SWAP (Path B, April 17 2026) ===
// When a beat has a completed lipsync, show the lipsync video as the primary
// video (inside .mn-anim-opt.selected) instead of the raw Kling option.
// Idempotent: safe to call on every pollStatus() re-render.
(function() {
    var SERVER = "http://localhost:5111";
    var POLL_INTERVAL = 10000;
    var SWAP_MARKER_ATTR = "data-lipsync-swapped";
    var INDICATOR_CLASS = "mn-lipsync-indicator";

    function findSelectedVideo(rowIdx) {
        var row = document.getElementById("r" + rowIdx);
        if (!row) return null;
        var section = row.querySelector(".mn-anim-section");
        if (!section) return null;
        // Prefer .selected; fall back to first video (single-option beats)
        var sel = section.querySelector(".mn-anim-opt.selected video");
        if (!sel) sel = section.querySelector(".mn-anim-single video");
        if (!sel) sel = section.querySelector("video");
        return sel;
    }

    function findSelectedCard(rowIdx) {
        var row = document.getElementById("r" + rowIdx);
        if (!row) return null;
        var section = row.querySelector(".mn-anim-section");
        if (!section) return null;
        return section.querySelector(".mn-anim-opt.selected")
            || section.querySelector(".mn-anim-single")
            || section;
    }

    function ensureIndicator(card) {
        if (!card) return;
        if (card.querySelector("." + INDICATOR_CLASS)) return;
        var tag = document.createElement("div");
        tag.className = INDICATOR_CLASS;
        tag.textContent = "\\u2728 with lipsync";
        tag.style.cssText = "margin-top:4px;font-size:11px;color:#22c55e;"
            + "background:#0f2419;border:1px solid #1f6b3f;border-radius:4px;"
            + "padding:2px 6px;display:inline-block;font-weight:600;";
        card.appendChild(tag);
    }

    function removeIndicator(card) {
        if (!card) return;
        var tag = card.querySelector("." + INDICATOR_CLASS);
        if (tag) tag.remove();
    }

    function swapOneBeat(beatKey, bs, selectedOptFromAnimStatus) {
        // Derive rowIdx from beatKey (beat_01 -> 0)
        var m = /^beat_(\\d+)$/.exec(beatKey);
        if (!m) return;
        var rowIdx = parseInt(m[1], 10) - 1;

        var vid = findSelectedVideo(rowIdx);
        var card = findSelectedCard(rowIdx);
        if (!vid) return;

        var hasCompletedLipsync = bs && bs.status === "completed" && bs.url;

        // If lipsync.source_option is defined and doesn't match the user's
        // current selection, do NOT swap — raw Kling stays visible and the
        // "Re-run Lip Sync" button in the lipsync row surfaces the warning.
        if (hasCompletedLipsync
            && bs.source_option != null
            && selectedOptFromAnimStatus != null
            && bs.source_option !== selectedOptFromAnimStatus) {
            // Revert any prior swap on this vid back to raw (handled by the
            // next pollStatus re-render, since it rebuilds src from opt.url)
            removeIndicator(card);
            return;
        }

        if (!hasCompletedLipsync) {
            removeIndicator(card);
            return;
        }

        var desired = SERVER + bs.url;
        if (vid.getAttribute(SWAP_MARKER_ATTR) === desired && vid.src === desired) {
            // already swapped to the same file — nothing to do
            ensureIndicator(card);
            return;
        }

        // Preserve the raw src in a data attribute in case a later pass needs
        // to restore it (e.g. if lipsync is cleared server-side).
        if (!vid.getAttribute("data-raw-src")) {
            vid.setAttribute("data-raw-src", vid.src || "");
        }
        vid.src = desired;
        vid.setAttribute(SWAP_MARKER_ATTR, desired);
        ensureIndicator(card);
    }

    function applySwap(lipsyncStatus, animStatus) {
        if (!lipsyncStatus || !lipsyncStatus.beats) return;
        var lsBeats = lipsyncStatus.beats;
        var animBeats = (animStatus && animStatus.beats) || {};
        Object.keys(lsBeats).forEach(function(beatKey) {
            var bs = lsBeats[beatKey];
            var ab = animBeats[beatKey];
            var selOpt = ab ? ab.selected_option : null;
            swapOneBeat(beatKey, bs, selOpt);
        });
    }

    // Cache of latest statuses so a swap triggered by one endpoint can use
    // the other endpoint's data without an extra fetch.
    var _latestLipsync = null;
    var _latestAnim = null;

    function fetchBothAndSwap() {
        var p1 = fetch(SERVER + "/api/lipsync/status").then(function(r) { return r.json(); }).catch(function() { return null; });
        var p2 = fetch(SERVER + "/api/animate/status").then(function(r) { return r.json(); }).catch(function() { return null; });
        Promise.all([p1, p2]).then(function(arr) {
            if (arr[0]) _latestLipsync = arr[0];
            if (arr[1]) _latestAnim = arr[1];
            applySwap(_latestLipsync, _latestAnim);
        });
    }

    // Primary entry point: used by the existing lip-sync IIFE after status
    // transitions, and by the injectAnimationsFromStatus wrapper below.
    // Accepts an optional status object; if omitted, uses cached data.
    window._swapVideoSrcForLipsync = function(maybeLipsyncStatus) {
        if (maybeLipsyncStatus && maybeLipsyncStatus.beats) {
            // Merge partial updates into cache (the applyCompletedButtonState
            // caller passes a single-beat object).
            if (!_latestLipsync) _latestLipsync = { beats: {} };
            Object.keys(maybeLipsyncStatus.beats).forEach(function(k) {
                _latestLipsync.beats[k] = maybeLipsyncStatus.beats[k];
            });
        }
        // If we have anim status cached, apply immediately; otherwise fetch.
        if (_latestAnim) {
            applySwap(_latestLipsync, _latestAnim);
        } else {
            fetchBothAndSwap();
        }
    };

    // Wrap injectAnimationsFromStatus — it rebuilds .mn-anim-section on every
    // /api/animate/status poll, so any prior swap is wiped and must be
    // re-applied.
    function installAnimWrap() {
        if (typeof window.injectAnimationsFromStatus === "function"
            && !window.injectAnimationsFromStatus._lipsyncWrapped) {
            var orig = window.injectAnimationsFromStatus;
            var wrapped = function(s) {
                var ret = orig.apply(this, arguments);
                _latestAnim = s;
                // Re-apply swap after re-render. Use a microtask so the DOM
                // write has settled.
                Promise.resolve().then(function() {
                    applySwap(_latestLipsync, _latestAnim);
                });
                return ret;
            };
            wrapped._lipsyncWrapped = true;
            window.injectAnimationsFromStatus = wrapped;
        }
    }

    // injectAnimationsFromStatus is defined inside an IIFE in the main
    // script, so it's NOT on window. Intercept via the pollStatus pipeline
    // instead: patch fetch to observe /api/animate/status responses and
    // re-apply swap right after.
    var origFetch = window.fetch;
    window.fetch = function(input, init) {
        var url = (typeof input === "string") ? input : (input && input.url) || "";
        var p = origFetch.apply(this, arguments);
        if (url.indexOf("/api/animate/status") !== -1) {
            p.then(function(resp) {
                // Clone so the original caller still gets the body
                resp.clone().json().then(function(data) {
                    _latestAnim = data;
                    // Wait a tick for injectAnimationsFromStatus to have
                    // rebuilt the DOM, then swap.
                    setTimeout(function() { applySwap(_latestLipsync, _latestAnim); }, 50);
                }).catch(function() {});
            }).catch(function() {});
        } else if (url.indexOf("/api/lipsync/status") !== -1) {
            p.then(function(resp) {
                resp.clone().json().then(function(data) {
                    _latestLipsync = data;
                    applySwap(_latestLipsync, _latestAnim);
                }).catch(function() {});
            }).catch(function() {});
        }
        return p;
    };

    // Periodic safety net: if neither endpoint fires for a while (e.g. user
    // leaves the tab open), fetch and re-apply every POLL_INTERVAL.
    setInterval(fetchBothAndSwap, POLL_INTERVAL);

    // First pass on DOM ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fetchBothAndSwap);
    } else {
        setTimeout(fetchBothAndSwap, 1500);
    }

    // Try the direct-wrap too in case injectAnimationsFromStatus IS exposed
    installAnimWrap();
    setTimeout(installAnimWrap, 2000);
})();
"""

# ----------------------------------------------------------------------------
# Patch driver
# ----------------------------------------------------------------------------

def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")

    LIPSYNC_IIFE_MARKER = "// === LIP SYNC BUTTON INJECTION"
    if LIPSYNC_IIFE_MARKER not in html:
        print(f"ERROR: Could not find '{LIPSYNC_IIFE_MARKER}' in {html_path.name}")
        sys.exit(1)

    # Count base64 images BEFORE any edits
    old_b64 = re.findall(r'data:image/[^"]{100,}', html)

    # --- Edit 1: applyCompletedButtonState — add swap call after src set ---
    if APPLY_STATE_MARKER not in html:
        print(f"ERROR: Marker for applyCompletedButtonState swap not found: {APPLY_STATE_MARKER!r}")
        sys.exit(1)
    occurrences_1 = html.count(APPLY_STATE_MARKER)
    if occurrences_1 != 1:
        print(f"ERROR: Expected exactly 1 occurrence of applyCompletedButtonState marker, found {occurrences_1}")
        sys.exit(1)
    # Guard against re-running the patch
    if "window._swapVideoSrcForLipsync({ beats: (function(){ var o={}; o[beatKey]=bs" in html:
        print("WARNING: swap call already present in applyCompletedButtonState — already patched?")
        sys.exit(1)
    html_step1 = html.replace(APPLY_STATE_MARKER, APPLY_STATE_REPLACEMENT, 1)

    # --- Edit 2: createLipSyncRow — add swap call after registry write ---
    if REGISTRY_BLOCK_OLD not in html_step1:
        print(f"ERROR: Registry block not found (exact multi-line match needed):")
        print(f"--- EXPECTED ---\n{REGISTRY_BLOCK_OLD}\n--- END ---")
        sys.exit(1)
    occurrences_2 = html_step1.count(REGISTRY_BLOCK_OLD)
    if occurrences_2 != 1:
        print(f"ERROR: Expected exactly 1 occurrence of registry block, found {occurrences_2}")
        sys.exit(1)
    html_step2 = html_step1.replace(REGISTRY_BLOCK_OLD, REGISTRY_BLOCK_NEW, 1)

    # --- Edit 3: append new IIFE AFTER the end of the existing lip-sync IIFE ---
    # Find the closing `})();` of the existing lip-sync IIFE. Walk from the
    # marker forward, count braces in the function body, find the matching
    # close, then find the })(); pattern.
    marker_idx = html_step2.index(LIPSYNC_IIFE_MARKER)
    # Find the `(function() {` that opens the IIFE — it's before the marker.
    # But simpler: find the LAST })(); that sits inside the same <script>
    # block as the marker — that's the close of the lip-sync IIFE.
    # Strategy: from marker, scan forward counting braces starting at the
    # next "(function() {" AFTER the marker is inside the IIFE already.
    # Since the marker is INSIDE the IIFE body, we count from the "{" of
    # the outer function.
    # Easiest: find the first occurrence of `})();\n` AFTER the marker
    # where the depth returns to zero. We rely on the existing patch file's
    # structure (known: the IIFE ends with `})();` at column 0).
    # Look for the exact closing pattern.
    close_re = re.compile(r'\n\}\)\(\);\s*(?:\n|$)')
    search_start = marker_idx
    close_match = close_re.search(html_step2, search_start)
    if not close_match:
        print("ERROR: Could not locate closing })(); of lip-sync IIFE")
        sys.exit(1)
    insert_at = close_match.end()

    html_final = html_step2[:insert_at] + NEW_IIFE + html_step2[insert_at:]

    # --- Verification: base64 images preserved ---
    new_b64 = re.findall(r'data:image/[^"]{100,}', html_final)
    if len(old_b64) != len(new_b64):
        print(f"ERROR: base64 image count changed. Before: {len(old_b64)}, After: {len(new_b64)}")
        sys.exit(1)
    for i, (a, b) in enumerate(zip(old_b64, new_b64)):
        if a != b:
            print(f"ERROR: base64 image {i} content changed. Aborting.")
            sys.exit(1)
    print(f"Verified: {len(old_b64)} base64 images preserved byte-identical")

    # --- Verification: expected string markers present in output ---
    checks = [
        "window._swapVideoSrcForLipsync",
        "LIP SYNC VIDEO-SRC SWAP (Path B, April 17 2026)",
        "data-lipsync-swapped",
        "mn-lipsync-indicator",
        "\\u2728 with lipsync",
    ]
    for needle in checks:
        if needle not in html_final:
            print(f"ERROR: expected marker missing from output: {needle!r}")
            sys.exit(1)
    print("Verified: all expected swap markers present in output")

    output_path.write_text(html_final, encoding="utf-8")
    size_diff = len(html_final) - len(html)
    print(f"Patched: {html_path.name} -> {output_path.name} ({size_diff:+d} chars)")
    print("Behavior change: beats with completed lipsync now show lipsync video")
    print("                 as the primary .mn-anim-opt.selected video, with a")
    print("                 \"\\u2728 with lipsync\" indicator. Raw Kling options")
    print("                 remain selectable — switching selection clears the")
    print("                 swap and the next pollStatus re-render restores raw.")


if __name__ == "__main__":
    event_dir = Path(__file__).parent.parent / "Event_1"
    src = event_dir / "storyboard_v37_prod.html"
    dst = event_dir / "storyboard_v38_prod.html"
    if not src.exists():
        print(f"ERROR: source not found: {src}")
        sys.exit(1)
    patch(src, dst)

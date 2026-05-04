#!/usr/bin/env python3
"""
Path B patch: Rewrite lip sync button injection to target ALL storyboard rows.

Problem: The old code attached lip sync buttons only to .mn-anim-section elements,
which only exist for beats that have animation clips loaded. Beats without animations
got no button.

Fix: Target .lr rows directly by ID (#r0..#r10), mapping row index to beat number.
Every row gets a lip sync button. The server returns helpful errors if a beat lacks
a selected clip or TTS audio — the user sees the error, not a missing button.

This is a JS-only patch (Path B per CLAUDE.md Rule 7).
"""
import re
import sys
from pathlib import Path

def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")

    # The old lip sync injection block
    OLD_MARKER = "// === LIP SYNC BUTTON INJECTION ==="

    if OLD_MARKER not in html:
        print(f"ERROR: Could not find '{OLD_MARKER}' in {html_path.name}")
        sys.exit(1)

    # Find the start of the old block and its enclosing IIFE
    idx = html.index(OLD_MARKER)
    # Walk back to find the newline before it
    block_start = html.rfind("\n", 0, idx)

    # Find the end of the IIFE: the closing })(); after the injection block
    # The block is wrapped in (function() { ... })();
    # Search for the closing pattern after the marker
    # We need to find the matching })(); — count braces
    search_start = idx
    brace_depth = 0
    found_open = False
    end_idx = None
    for i in range(search_start, len(html)):
        if html[i] == '{':
            brace_depth += 1
            found_open = True
        elif html[i] == '}':
            brace_depth -= 1
            if found_open and brace_depth == 0:
                # Found the closing brace of the IIFE function body
                # Now find the ")();" after it
                rest = html[i+1:i+20]
                m = re.match(r'\s*\)\s*\(\s*\)\s*;', rest)
                if m:
                    end_idx = i + 1 + m.end()
                    break
                # Or just the closing brace of another structure
                # Keep going

    if end_idx is None:
        # Fallback: find the LAST })(); in the script block
        # Search from the marker forward
        pattern = re.compile(r'\}\s*\)\s*\(\s*\)\s*;')
        matches = list(pattern.finditer(html, idx))
        if matches:
            end_idx = matches[0].end()
        else:
            print("ERROR: Could not find end of lip sync IIFE block")
            sys.exit(1)

    old_block = html[block_start:end_idx]
    print(f"Found old lip sync block: {len(old_block)} chars (lines ~{html[:block_start].count(chr(10))+1}-{html[:end_idx].count(chr(10))+1})")

    NEW_BLOCK = """
// === LIP SYNC BUTTON INJECTION (v3 — Tier 5 re-run detection) ===
// v3: decision 153 (LIPSYNC_UI_MUST_SUPPORT_RERUN, April 17 2026) — when
// the user switches clip selection after a lipsync completes, the button
// flips to "🔁 Re-run Lip Sync" via the source_changed flag surfaced by
// /api/lipsync/status. A 10s refresher keeps already-rendered buttons in
// sync with server-side state.
(function() {
    var SERVER = "http://localhost:5111";
    var POLL_INTERVAL = 5000;
    var TOTAL_BEATS = 11;

    // Registry so refreshAllLipSyncButtons() can re-render completed rows
    // when source_changed transitions after initial injection.
    var _lipsyncRows = {};

    function applyCompletedButtonState(beatKey, bs, btn, stat, video, preview) {
        if (bs.source_changed) {
            btn.textContent = "\\uD83D\\uDD01 Re-run Lip Sync";
            btn.className = "mn-lipsync-btn";
            stat.textContent = "Selected clip changed — re-run recommended (was opt " +
                (bs.source_option != null ? bs.source_option : "?") + ")";
        } else {
            btn.textContent = "\\u2705 Lip Sync Done \\u2014 Preview";
            btn.className = "mn-lipsync-btn done";
            stat.textContent = "File: " + (bs.file || "ready");
        }
        btn.disabled = false;
        if (video && bs.url) video.src = SERVER + bs.url;
        if (preview) preview.classList.add("visible");
    }

    function refreshAllLipSyncButtons() {
        fetch(SERVER + "/api/lipsync/status").then(function(r) { return r.json(); }).then(function(d) {
            var beats = d.beats || {};
            Object.keys(_lipsyncRows).forEach(function(beatKey) {
                var ref = _lipsyncRows[beatKey];
                if (!ref || !ref.btn) return;
                var bs = beats[beatKey];
                if (!bs || bs.status !== "completed" || !bs.url) return;
                var isDone = ref.btn.classList.contains("done");
                var wantDone = !bs.source_changed;
                if (isDone !== wantDone) {
                    applyCompletedButtonState(beatKey, bs, ref.btn, ref.stat, ref.video, ref.preview);
                }
            });
        }).catch(function() { /* swallow */ });
    }

    function startPolling(beatKey, btn, stat, video, preview) {
        var interval = setInterval(function() {
            fetch(SERVER + "/api/lipsync/status").then(function(r) { return r.json(); }).then(function(d) {
                var bs = (d.beats || {})[beatKey];
                if (!bs) return;
                if (bs.status === "completed" && bs.url) {
                    clearInterval(interval);
                    applyCompletedButtonState(beatKey, bs, btn, stat, video, preview);
                } else if (bs.status === "failed") {
                    clearInterval(interval);
                    btn.disabled = false;
                    btn.textContent = "\\u274C Retry Lip Sync";
                    btn.className = "mn-lipsync-btn";
                    stat.textContent = "Failed: " + (bs.last_error || "unknown").substring(0, 80);
                } else {
                    stat.textContent = "Processing... (" + bs.status + ")";
                }
            }).catch(function() {
                stat.textContent = "Polling... (server may be busy)";
            });
        }, POLL_INTERVAL);
    }

    function createLipSyncRow(beatKey, parentRow, statusData) {
        if (parentRow.querySelector(".mn-lipsync-row")) return;

        var lsRow = document.createElement("div");
        lsRow.className = "mn-lipsync-row";

        var lsBtn = document.createElement("button");
        lsBtn.className = "mn-lipsync-btn";

        var lsStat = document.createElement("span");
        lsStat.className = "mn-lipsync-status";

        var lsPreview = document.createElement("div");
        lsPreview.className = "mn-lipsync-preview";
        var lsVideo = document.createElement("video");
        lsVideo.controls = true;
        lsVideo.preload = "metadata";
        lsPreview.appendChild(lsVideo);

        var beatStatus = (statusData.beats || {})[beatKey];
        if (beatStatus && beatStatus.status === "completed" && beatStatus.url) {
            applyCompletedButtonState(beatKey, beatStatus, lsBtn, lsStat, lsVideo, lsPreview);
        } else if (beatStatus && (beatStatus.status === "polling" || beatStatus.status === "submitting")) {
            lsBtn.textContent = "\\u23F3 Lip Sync Processing...";
            lsBtn.className = "mn-lipsync-btn polling";
            lsBtn.disabled = true;
            startPolling(beatKey, lsBtn, lsStat, lsVideo, lsPreview);
        } else if (beatStatus && beatStatus.status === "failed") {
            lsBtn.textContent = "\\u274C Retry Lip Sync";
            lsStat.textContent = "Failed: " + (beatStatus.last_error || "unknown").substring(0, 80);
        } else {
            lsBtn.textContent = "\\uD83D\\uDC44 Send for Lip Sync";
        }

        lsBtn.addEventListener("click", function() {
            if (lsBtn.disabled) return;
            if (lsBtn.classList.contains("done")) {
                lsPreview.classList.toggle("visible");
                return;
            }
            if (!confirm("Send " + beatKey + " for lip sync? Cost: ~$0.15.\\nThis submits the selected clip + TTS audio to ByteDance LipSync.")) return;

            lsBtn.disabled = true;
            lsBtn.textContent = "\\u23F3 Submitting...";
            lsBtn.className = "mn-lipsync-btn polling";
            lsStat.textContent = "Sending to ByteDance LipSync...";

            fetch(SERVER + "/api/lipsync", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ beat: beatKey })
            }).then(function(resp) { return resp.json(); }).then(function(data) {
                if (data.error) {
                    lsBtn.disabled = false;
                    lsBtn.textContent = "\\u274C Retry Lip Sync";
                    lsBtn.className = "mn-lipsync-btn";
                    lsStat.textContent = "Error: " + data.error;
                    return;
                }
                lsBtn.textContent = "\\u23F3 Processing (" + (data.clip || beatKey) + ")...";
                lsStat.textContent = "Submitted. Audio: " + (data.audio || "?") + ". Polling for result...";
                startPolling(beatKey, lsBtn, lsStat, lsVideo, lsPreview);
            }).catch(function(err) {
                lsBtn.disabled = false;
                lsBtn.textContent = "\\u274C Retry Lip Sync";
                lsBtn.className = "mn-lipsync-btn";
                lsStat.textContent = "Network error: " + err.message;
            });
        });

        lsRow.appendChild(lsBtn);
        lsRow.appendChild(lsStat);
        parentRow.appendChild(lsRow);
        parentRow.appendChild(lsPreview);

        _lipsyncRows[beatKey] = {
            btn: lsBtn, stat: lsStat, video: lsVideo, preview: lsPreview,
        };
    }

    function injectLipSyncButtons() {
        // Target ALL storyboard rows by ID (#r0..#r10 = beat_01..beat_11)
        var firstRow = document.getElementById("r0");
        if (!firstRow) {
            setTimeout(injectLipSyncButtons, 500);
            return;
        }

        fetch(SERVER + "/api/lipsync/status").then(function(r) { return r.json(); }).then(function(statusData) {
            for (var i = 0; i < TOTAL_BEATS; i++) {
                var row = document.getElementById("r" + i);
                if (!row) continue;
                var beatKey = "beat_" + String(i + 1).padStart(2, "0");
                createLipSyncRow(beatKey, row, statusData);
            }
        }).catch(function(err) {
            // Server not running — inject buttons anyway, they'll work once server starts
            for (var i = 0; i < TOTAL_BEATS; i++) {
                var row = document.getElementById("r" + i);
                if (!row) continue;
                var beatKey = "beat_" + String(i + 1).padStart(2, "0");
                createLipSyncRow(beatKey, row, { beats: {} });
            }
        });
    }

    // Expose for render() hook
    window._injectLipSyncButtons = injectLipSyncButtons;

    // Run after a short delay to let the storyboard render
    setTimeout(injectLipSyncButtons, 1000);

    // Tier 5 (decision 153): refresh completed-button state every 10s so
    // source_changed transitions propagate without needing a page reload.
    setInterval(refreshAllLipSyncButtons, 10000);
})();"""

    html_new = html[:block_start] + NEW_BLOCK + html[end_idx:]

    # Verify: count base64 images before and after
    import re as re2
    old_b64 = re2.findall(r'data:image/[^"]{100,}', html)
    new_b64 = re2.findall(r'data:image/[^"]{100,}', html_new)
    if len(old_b64) != len(new_b64):
        print(f"WARNING: base64 image count changed! Before: {len(old_b64)}, After: {len(new_b64)}")
        print("Aborting to prevent image loss")
        sys.exit(1)

    # Verify base64 content is identical
    for i, (a, b) in enumerate(zip(old_b64, new_b64)):
        if a != b:
            print(f"WARNING: base64 image {i} content changed! Aborting.")
            sys.exit(1)
    print(f"Verified: {len(old_b64)} base64 images preserved byte-identical")

    output_path.write_text(html_new, encoding="utf-8")
    size_diff = len(html_new) - len(html)
    print(f"Patched: {html_path.name} -> {output_path.name} ({size_diff:+d} chars)")
    print(f"Change: lip sync buttons now injected on ALL {TOTAL_BEATS} rows (was: only animation sections)")


if __name__ == "__main__":
    event_dir = Path(__file__).parent.parent / "Event_1"
    src = event_dir / "storyboard_v27_prod.html"
    dst = event_dir / "storyboard_v28_prod.html"
    patch(src, dst)

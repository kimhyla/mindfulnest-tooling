#!/usr/bin/env python3
"""
patch_animation_layer.py — Path B JS/CSS-only patch for storyboard

Integrates animation video players INTO each storyboard beat row, replacing
the full-screen production overlay with a thin status bar at top.

This is a PATH B patch (CLAUDE.md Rule 7): modifies ONLY <script> and <style>
blocks. All base64 image/audio data is verified byte-identical before and after.

Usage:
    python3 patch_animation_layer.py \
        --input storyboard_v22_prod.html \
        --output storyboard_v23_prod.html

Author: Claude (Path B patcher)
Date: April 15, 2026
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path


def extract_base64_checksums(html: str) -> dict[str, str]:
    """Extract all base64 data URIs and return {index: sha256} for verification."""
    checksums = {}
    for i, m in enumerate(re.finditer(r'data:(image|audio)/[^;]+;base64,[A-Za-z0-9+/=]+', html)):
        checksums[f"b64_{i}"] = hashlib.sha256(m.group(0).encode()).hexdigest()
    return checksums


def patch(input_path: Path, output_path: Path) -> None:
    html = input_path.read_text(encoding="utf-8")

    # --- Step 1: Checksum all base64 data BEFORE patching ---
    pre_checksums = extract_base64_checksums(html)
    print(f"[patch] Found {len(pre_checksums)} base64 data URIs in source")

    # --- Step 2: Find the overlay boundaries ---
    overlay_start = html.find("<!-- BEGIN PRODUCTION OVERLAY (injected) -->")
    overlay_end = html.find("<!-- END PRODUCTION OVERLAY (injected) -->")
    if overlay_start == -1 or overlay_end == -1:
        print("[ERROR] Could not find overlay injection markers")
        sys.exit(1)

    # Everything before the overlay (the main storyboard)
    pre_overlay = html[:overlay_start]
    # Everything after the overlay end marker through end of file
    post_overlay_marker = html[overlay_end:]
    post_close = post_overlay_marker.find("</body>")
    # We'll reconstruct: pre_overlay + new_overlay + closing tags

    # --- Step 3: Find the render hook point ---
    # The existing code at the end of the main script has:
    #   var _baseRender=render;
    #   render=function(){_baseRender();initDrag();setupDropZones();};
    #   render();
    # We need to add our animation injection after initDrag/setupDropZones
    hook_pattern = "render=function(){_baseRender();initDrag();setupDropZones();};"
    if hook_pattern not in pre_overlay:
        print("[ERROR] Could not find render hook pattern")
        sys.exit(1)

    # Replace the hook to also call our animation injector
    new_hook = "render=function(){_baseRender();initDrag();setupDropZones();if(window._injectAnimations)window._injectAnimations();};"
    pre_overlay = pre_overlay.replace(hook_pattern, new_hook)

    # --- Step 4: Build new overlay CSS ---
    new_css = """
<!-- BEGIN PRODUCTION OVERLAY (injected) -->
<style>
/* --- Production Overlay CSS (v23 — integrated animation layer) --- */

/* Thin status bar at top instead of full-screen overlay */
#mn-prod-overlay {
    position: sticky; top: 0; left: 0; right: 0;
    background: #1c1f26; color: #e8ecf1;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 8px 18px; z-index: 99999;
    border-bottom: 2px solid #3b82f6;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4);
    font-size: 13px; line-height: 1.45;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
#mn-prod-overlay h2 { margin: 0; font-size: 14px; font-weight: 600; white-space: nowrap; }
#mn-prod-overlay button {
    background: #3b82f6; color: white; border: none;
    padding: 6px 12px; border-radius: 6px; font-weight: 600;
    cursor: pointer; font-size: 12px;
}
#mn-prod-overlay button:disabled { opacity: 0.5; cursor: not-allowed; }
#mn-prod-overlay button.mn-secondary {
    background: transparent; border: 1px solid #3b82f6; color: #3b82f6;
}
#mn-prod-overlay .mn-health {
    font-size: 11px; padding: 3px 6px;
    border-radius: 4px; background: #2a2f3a;
}
#mn-prod-overlay .mn-health.ok  { color: #22c55e; }
#mn-prod-overlay .mn-health.bad { color: #ef4444; }
#mn-prod-overlay .mn-progress {
    height: 6px; background: #2a2f3a; border-radius: 4px;
    flex: 1; min-width: 120px; overflow: hidden;
}
#mn-prod-overlay .mn-progress-bar {
    height: 100%; background: linear-gradient(90deg, #3b82f6, #22c55e);
    width: 0%; transition: width 0.4s ease;
}
#mn-status-line { font-size: 11px; color: #aaa; white-space: nowrap; }

/* Animation options inside beat rows */
.mn-anim-section {
    margin-top: 8px;
    padding: 8px;
    background: #0d1b2a;
    border: 1px solid #1b4965;
    border-radius: 8px;
}
.mn-anim-section .mn-anim-title {
    font-size: 12px; font-weight: 600; color: #48cae4;
    margin-bottom: 6px;
}
.mn-anim-options {
    display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-start;
}
.mn-anim-opt {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    padding: 6px; border-radius: 6px; border: 2px solid transparent;
    background: #16213e; cursor: pointer; transition: all 0.2s;
}
.mn-anim-opt:hover { border-color: #48cae4; }
.mn-anim-opt.selected { border-color: #22c55e; background: #1a3a2a; }
.mn-anim-opt video {
    width: 240px; max-width: 240px; height: auto;
    border-radius: 4px; background: #000;
}
.mn-anim-opt .mn-opt-label {
    font-size: 11px; font-weight: 600; color: #e0c3fc;
}
.mn-anim-opt .mn-opt-size {
    font-size: 10px; color: #666;
}
.mn-anim-opt input[type="radio"] {
    accent-color: #22c55e; width: 16px; height: 16px;
}
.mn-anim-single video {
    width: 320px; max-width: 100%; height: auto;
    border-radius: 4px; background: #000; margin-top: 4px;
}
.mn-anim-single .mn-anim-check {
    font-size: 11px; color: #22c55e; margin-top: 4px;
}
</style>
"""

    # --- Step 5: Build new overlay JavaScript ---
    new_js = """<script>
/* --- Production Overlay JS (v23 — integrated animation layer) --- */
(function () {
    "use strict";
    var SERVER = "http://localhost:5111";
    var EVENT_ID = "M1E1";
    var videoPlaying = false;
    var queuedUpdate = null;
    var statusTimer = null;
    var healthTimer = null;
    var latestStatus = null;

    function el(tag, attrs, kids) {
        var e = document.createElement(tag);
        if (attrs) {
            for (var k in attrs) {
                if (k === "style") { e.setAttribute("style", attrs[k]); }
                else if (k.indexOf("on") === 0) { e[k] = attrs[k]; }
                else { e.setAttribute(k, attrs[k]); }
            }
        }
        (kids || []).forEach(function (k) {
            if (k == null) return;
            e.appendChild(typeof k === "string" ? document.createTextNode(k) : k);
        });
        return e;
    }
    function api(path, opts) {
        return fetch(SERVER + path, opts || {}).then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
        });
    }
    function setStatus(msg) {
        var b = document.getElementById("mn-status-line");
        if (b) b.textContent = msg;
    }

    /* --- Thin status bar mount --- */
    function mount() {
        var root = el("div", { id: "mn-prod-overlay" });

        var title = el("h2", null, ["Production"]);
        var health = el("span", { id: "mn-health", "class": "mn-health" }, ["..."]);

        var exportBtn = el("button", {
            id: "mn-export-btn",
            "class": "mn-secondary",
            onclick: exportSelections,
            disabled: "disabled"
        }, ["Export Selections"]);

        var progressWrap = el("div", { "class": "mn-progress" }, [
            el("div", { id: "mn-progress-bar", "class": "mn-progress-bar" })
        ]);
        var statusLine = el("span", { id: "mn-status-line" }, ["Loading..."]);

        root.appendChild(title);
        root.appendChild(health);
        root.appendChild(progressWrap);
        root.appendChild(statusLine);
        root.appendChild(exportBtn);

        document.body.insertBefore(root, document.body.firstChild);
    }

    /* --- Health polling --- */
    function pollHealth() {
        api("/api/health").then(function (r) {
            var h = document.getElementById("mn-health");
            h.textContent = "Online";
            h.className = "mn-health ok";
        }).catch(function () {
            var h = document.getElementById("mn-health");
            h.textContent = "Offline";
            h.className = "mn-health bad";
        });
    }

    /* --- Status polling --- */
    function pollStatus() {
        api("/api/animate/status").then(function (s) {
            latestStatus = s;
            if (videoPlaying) { queuedUpdate = s; return; }
            renderStatusBar(s);
            injectAnimationsFromStatus(s);
        }).catch(function () {});
    }

    function renderStatusBar(s) {
        var pct = s.total_beats ? Math.round(100 * s.completed / s.total_beats) : 0;
        var bar = document.getElementById("mn-progress-bar");
        if (bar) bar.style.width = pct + "%";

        var allSelected = true;
        var beats = s.beats || {};
        var keys = Object.keys(beats);
        keys.forEach(function(k) {
            var b = beats[k];
            if (b.selected_option == null) allSelected = false;
        });

        setStatus(
            s.completed + "/" + s.total_beats + " ready — " +
            (allSelected ? "All selected!" : "Select animations below")
        );

        var expBtn = document.getElementById("mn-export-btn");
        if (expBtn) expBtn.disabled = !allSelected;
    }

    /* --- Inject animation videos into storyboard beat rows --- */
    function injectAnimationsFromStatus(s) {
        var beats = s.beats || {};
        var keys = Object.keys(beats).sort();

        // Map beat keys (beat_01..beat_11) to row indices (0..10)
        keys.forEach(function(k) {
            var beatNum = parseInt(k.replace("beat_", ""), 10);
            var rowIdx = beatNum - 1; // beat_01 = row 0
            var row = document.getElementById("r" + rowIdx);
            if (!row) return;

            var b = beats[k];
            if (b.status !== "completed" || !b.options || b.options.length === 0) return;

            // Remove any existing animation section in this row
            var existing = row.querySelector(".mn-anim-section");
            if (existing) existing.remove();

            var section = el("div", { "class": "mn-anim-section" });

            if (b.options.length === 1) {
                // Single animation — just show it with a checkmark
                var titleText = "Animation";
                if (b.selected_option) titleText += " ✓";
                section.appendChild(el("div", { "class": "mn-anim-title" }, [titleText]));
                var wrapper = el("div", { "class": "mn-anim-single" });
                var vid = el("video", {
                    src: SERVER + b.options[0].url,
                    controls: "controls",
                    preload: "metadata"
                });
                vid.addEventListener("play",  function () { videoPlaying = true; });
                vid.addEventListener("pause", function () { flushQueued(); });
                vid.addEventListener("ended", function () { flushQueued(); });
                wrapper.appendChild(vid);
                if (b.selected_option) {
                    wrapper.appendChild(el("div", { "class": "mn-anim-check" }, ["✓ Auto-selected (only option)"]));
                }
                section.appendChild(wrapper);
            } else {
                // Multiple options — show side by side with radio buttons
                var needsPick = (b.selected_option == null);
                var titleStr = "Animation Options" + (needsPick ? " — PICK ONE" : " ✓");
                section.appendChild(el("div", { "class": "mn-anim-title" }, [titleStr]));

                var optionsRow = el("div", { "class": "mn-anim-options" });
                b.options.forEach(function(opt, i) {
                    var optNum = i + 1;
                    var isSelected = (b.selected_option === optNum);
                    var optCard = el("div", {
                        "class": "mn-anim-opt" + (isSelected ? " selected" : "")
                    });

                    var vid = el("video", {
                        src: SERVER + opt.url,
                        controls: "controls",
                        preload: "metadata"
                    });
                    vid.addEventListener("play",  function () { videoPlaying = true; });
                    vid.addEventListener("pause", function () { flushQueued(); });
                    vid.addEventListener("ended", function () { flushQueued(); });
                    optCard.appendChild(vid);

                    var label = el("div", { "class": "mn-opt-label" }, [
                        "Option " + String.fromCharCode(64 + optNum)
                    ]);
                    optCard.appendChild(label);

                    if (opt.size_mb) {
                        optCard.appendChild(el("div", { "class": "mn-opt-size" }, [
                            opt.size_mb + " MB"
                        ]));
                    }

                    var radio = el("input", {
                        type: "radio",
                        name: "sel-" + k,
                        value: String(optNum)
                    });
                    if (isSelected) radio.checked = true;
                    (function(beatKey, on) {
                        radio.onchange = function() { selectBeat(beatKey, on); };
                    })(k, optNum);
                    optCard.appendChild(radio);

                    optionsRow.appendChild(optCard);
                });
                section.appendChild(optionsRow);
            }

            row.appendChild(section);
        });
    }

    /* --- Expose injection function for render() hook --- */
    window._injectAnimations = function() {
        if (latestStatus) {
            injectAnimationsFromStatus(latestStatus);
        }
    };

    function flushQueued() {
        videoPlaying = false;
        if (queuedUpdate) {
            renderStatusBar(queuedUpdate);
            injectAnimationsFromStatus(queuedUpdate);
            queuedUpdate = null;
        }
    }

    /* --- Select / Export --- */
    function selectBeat(beat, option) {
        api("/api/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ beat: beat, selected_option: option })
        }).then(pollStatus);
    }
    function exportSelections() {
        fetch(SERVER + "/api/export", { method: "POST" })
            .then(function (r) { return r.blob(); })
            .then(function (blob) {
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url; a.download = "animation_selections.json"; a.click();
                URL.revokeObjectURL(url);
                setStatus("Exported to Downloads folder.");
            });
    }

    /* --- Boot --- */
    function boot() {
        mount();
        pollHealth();
        healthTimer = setInterval(pollHealth, 30000);
        pollStatus();
        statusTimer = setInterval(pollStatus, 15000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
</script>
<!-- END PRODUCTION OVERLAY (injected) -->
</body></html>
"""

    # --- Step 6: Assemble the patched HTML ---
    patched = pre_overlay + new_css + new_js

    # --- Step 7: Verify base64 integrity ---
    post_checksums = extract_base64_checksums(patched)
    print(f"[patch] Found {len(post_checksums)} base64 data URIs in output")

    if pre_checksums != post_checksums:
        print("[ERROR] BASE64 INTEGRITY CHECK FAILED!")
        print(f"  Before: {len(pre_checksums)} URIs")
        print(f"  After:  {len(post_checksums)} URIs")
        # Find which ones differ
        for k in pre_checksums:
            if k not in post_checksums:
                print(f"  MISSING: {k}")
            elif pre_checksums[k] != post_checksums[k]:
                print(f"  CHANGED: {k}")
        for k in post_checksums:
            if k not in pre_checksums:
                print(f"  NEW: {k}")
        sys.exit(1)

    print("[patch] ✓ All base64 data URIs verified byte-identical")

    # --- Step 8: Write output ---
    output_path.write_text(patched, encoding="utf-8")
    in_size = input_path.stat().st_size
    out_size = output_path.stat().st_size
    print(f"[patch] Written: {output_path}")
    print(f"[patch] Size: {in_size:,} → {out_size:,} bytes (delta: {out_size - in_size:+,})")
    print(f"[patch] ✓ Path B patch complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Path B patch: integrate animations into storyboard")
    parser.add_argument("--input", required=True, help="Source storyboard HTML")
    parser.add_argument("--output", required=True, help="Output patched HTML")
    args = parser.parse_args()
    patch(Path(args.input), Path(args.output))

#!/usr/bin/env python3
"""
Path B JS/CSS Patch — Audio Delay + Clip Trim Controls
=======================================================
Injects per-beat audio delay slider and clip trim controls into the
storyboard HTML. Modifies ONLY <script> and <style> blocks.

Safety: Verifies all base64 image/audio data is byte-identical before/after.

Usage:
  python3 patch_delay_trim.py <input.html> <output.html>
  python3 patch_delay_trim.py storyboard_v23_prod.html storyboard_v24_prod.html
"""

import sys, re, hashlib
from pathlib import Path


def extract_base64_data(html: str) -> list[str]:
    """Extract all base64 data URIs from HTML for integrity verification."""
    return re.findall(r'data:[^"]+;base64,[A-Za-z0-9+/=]+', html)


def patch_css(html: str) -> str:
    """Inject delay/trim control CSS into the second <style> block."""
    new_css = """
/* --- Audio Delay + Clip Trim Controls (Path B patch) --- */
.mn-timing-controls {
    margin-top: 8px; padding: 8px 10px;
    background: #111827; border: 1px solid #374151;
    border-radius: 6px; display: flex; gap: 16px; flex-wrap: wrap;
    align-items: center;
}
.mn-timing-controls label {
    font-size: 11px; color: #9ca3af; font-weight: 600;
    display: flex; align-items: center; gap: 6px;
}
.mn-timing-controls input[type="range"] {
    width: 100px; height: 4px; accent-color: #f59e0b;
    cursor: pointer;
}
.mn-timing-controls .mn-val {
    font-size: 11px; color: #fbbf24; font-family: monospace;
    min-width: 32px; text-align: right;
}
.mn-timing-controls .mn-trim-group {
    display: flex; gap: 12px; align-items: center;
}
.mn-timing-controls .mn-trim-group label {
    color: #7dd3fc;
}
.mn-timing-controls .mn-trim-group .mn-val {
    color: #7dd3fc;
}
.mn-timing-controls .mn-trim-group input[type="range"] {
    accent-color: #38bdf8;
}
.mn-timing-toggle {
    font-size: 10px; color: #6b7280; cursor: pointer;
    margin-top: 4px; user-select: none;
}
.mn-timing-toggle:hover { color: #9ca3af; }
.mn-preview-btn {
    background: #f59e0b; color: #000; border: none;
    padding: 5px 14px; border-radius: 5px; font-weight: 700;
    font-size: 11px; cursor: pointer; white-space: nowrap;
}
.mn-preview-btn:hover { background: #fbbf24; }
.mn-preview-btn.playing { background: #ef4444; color: #fff; }
.mn-regen-btn {
    background: #6366f1; color: #fff; border: none;
    padding: 5px 14px; border-radius: 5px; font-weight: 700;
    font-size: 11px; cursor: pointer; white-space: nowrap;
}
.mn-regen-btn:hover { background: #818cf8; }
.mn-regen-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mn-regen-btn.running { background: #a855f7; animation: mn-pulse 1.5s ease-in-out infinite; }
@keyframes mn-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
.mn-regen-row {
    display: flex; gap: 8px; margin-top: 6px; align-items: center;
}
.mn-regen-status {
    font-size: 10px; color: #a5b4fc; font-style: italic;
}
.mn-trim-bar {
    position: relative; height: 4px; background: #374151;
    border-radius: 2px; margin-top: 6px; overflow: visible;
}
.mn-trim-bar .mn-trim-active {
    position: absolute; height: 100%; background: #38bdf8;
    border-radius: 2px; transition: left 0.15s, width 0.15s;
}
.mn-trim-bar .mn-trim-playhead {
    position: absolute; top: -4px; width: 3px; height: 12px;
    background: #f59e0b; border-radius: 1px;
    transition: left 0.1s linear;
}
.mn-trim-info {
    font-size: 10px; color: #6b7280; margin-top: 4px;
    font-family: monospace;
}
"""
    # Insert before the closing </style> of the second style block
    # Find second </style>
    idx1 = html.find('</style>')
    if idx1 == -1:
        raise ValueError("No </style> found")
    idx2 = html.find('</style>', idx1 + 1)
    if idx2 == -1:
        raise ValueError("Second </style> not found")
    return html[:idx2] + new_css + html[idx2:]


def patch_playline(html: str) -> str:
    """Patch playLine() to respect audio delay from beat metadata.

    Original: plays audio immediately when beat starts.
    Patched: if window._beatDelays[i] > 0, delays audio start by that many seconds.
    Also handles clip trim: seeks video to trim_start and stops at trim_end.
    """
    # We inject a new wrapper after the existing playLine definition.
    # The original playLine (lines 188-197) will be wrapped.

    # Find the playLine function
    marker = "function playLine(i){"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("playLine function not found")

    # Find the end of the playLine function — it ends with "}}" followed by newline
    # The function is: function playLine(i){...cA.onended=function(){...};}
    # We need to find its closing
    # Rather than parsing JS, inject a delay-aware wrapper BEFORE playLine

    inject = """
/* --- Audio delay + clip trim support (Path B patch) --- */
window._beatDelays = {};
window._beatTrims = {};
window._delayTimers = [];

var _origPlayLine;
"""

    # Insert the setup code before playLine
    html = html[:idx] + inject + html[idx:]

    # Now wrap playLine by injecting override code AFTER the full playLine + playAllAudio + stopAll block
    # Find stopAll's closing
    stop_marker = 'var p=document.getElementById("pab");if(p)p.innerHTML="&#9654; Play All (audio lines)";}'
    stop_idx = html.find(stop_marker)
    if stop_idx == -1:
        raise ValueError("stopAll end marker not found")
    stop_end = stop_idx + len(stop_marker)

    override = """

/* Override playLine to support audio delay and clip trim */
_origPlayLine = playLine;
playLine = function(i) {
    // Clear any pending delay timers
    while (window._delayTimers.length) clearTimeout(window._delayTimers.pop());

    stopAll();
    var k = L[i].a;
    if (!k || !AU[k]) return;

    var delay = (window._beatDelays[i] || 0);
    var trim = window._beatTrims[i] || {};

    // Set up the audio
    cA = new Audio(AU[k]);
    var b = document.getElementById("pb" + i);
    var r = document.getElementById("r" + i);
    b.className = "pb playing"; b.innerHTML = "&#9632;"; r.classList.add("act");

    // Start video at trim point if applicable
    var vid = r.querySelector(".mn-anim-section video");
    if (vid && trim.start) {
        vid.currentTime = trim.start;
    }
    if (vid) vid.play().catch(function(){});

    // Handle trim_end — pause video when it reaches trim_end
    if (vid && trim.end) {
        var checkTrimEnd = setInterval(function() {
            if (vid.currentTime >= trim.end) {
                vid.pause();
                clearInterval(checkTrimEnd);
            }
        }, 100);
        window._delayTimers.push(checkTrimEnd);
    }

    // Audio chain callback (same logic as original)
    cA.onended = function() {
        b.className = "pb green"; b.innerHTML = "&#9654;"; r.classList.remove("act");
        cA = null;
        if (paA && paI === i) {
            setTimeout(function() {
                if (!paA) return;
                var n = i + 1;
                while (n < L.length && (!L[n].a || !AU[L[n].a])) n++;
                if (n < L.length) { paI = n; playLine(n); }
                else { paA = false; document.getElementById("pab").innerHTML = "&#9654; Play All (audio lines)"; }
            }, L[i].p * 1000);
        }
    };

    // Play audio after delay
    if (delay > 0) {
        var t = setTimeout(function() {
            if (cA) cA.play().catch(function(e) { console.error(e); });
        }, delay * 1000);
        window._delayTimers.push(t);
    } else {
        cA.play().catch(function(e) { console.error(e); });
    }
};

/* Patch stopAll to also clear delay timers */
var _origStopAll = stopAll;
stopAll = function() {
    while (window._delayTimers.length) clearTimeout(window._delayTimers.pop());
    _origStopAll();
};
"""
    html = html[:stop_end] + override + html[stop_end:]
    return html


def patch_inject_animations(html: str) -> str:
    """Extend injectAnimationsFromStatus() to render delay/trim controls per beat."""

    # Find the end of the injectAnimationsFromStatus function where it appends section to row
    marker = "            row.appendChild(section);\n        });\n    }"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("injectAnimationsFromStatus section append not found")

    # Insert timing controls rendering BEFORE row.appendChild(section)
    inject = """
            // --- Audio Delay + Clip Trim controls (Path B patch v2) ---
            var audioDelay = b.audio_delay || 0;
            var trimStart = b.trim_start || 0;
            var trimEnd = b.trim_end || null;

            // Store in global lookup for playLine
            window._beatDelays[rowIdx] = audioDelay;
            window._beatTrims[rowIdx] = { start: trimStart, end: trimEnd };

            var tc = el("div", { "class": "mn-timing-controls" });

            // Find the selected video element for this beat
            var vidEl = section.querySelector(".mn-anim-opt.selected video") || section.querySelector("video");

            // ===== PREVIEW BUTTON =====
            var prevBtn = el("button", { "class": "mn-preview-btn" }, ["\\u25B6 Preview Beat"]);

            // ===== AUDIO DELAY SLIDER =====
            var delayLabel = el("label", {}, ["Video Lead-in:"]);
            var delaySlider = el("input", {
                type: "range", min: "0", max: "5", step: "0.1",
                value: String(audioDelay)
            });
            var delayVal = el("span", { "class": "mn-val" }, [audioDelay.toFixed(1) + "s"]);

            // ===== TRIM SLIDERS =====
            var trimGroup = el("div", { "class": "mn-trim-group" });
            var maxDur = 10;

            var tsLabel = el("label", {}, ["Trim Start:"]);
            var tsSlider = el("input", {
                type: "range", min: "0", max: "10", step: "0.1",
                value: String(trimStart)
            });
            var tsVal = el("span", { "class": "mn-val" }, [trimStart.toFixed(1) + "s"]);

            var teLabel = el("label", {}, ["Trim End:"]);
            var teSlider = el("input", {
                type: "range", min: "0", max: "10", step: "0.1",
                value: String(trimEnd || 0)
            });
            var teVal = el("span", { "class": "mn-val" }, [trimEnd ? trimEnd.toFixed(1) + "s" : "full"]);

            // ===== VISUAL TRIM BAR =====
            var trimBar = el("div", { "class": "mn-trim-bar" });
            var trimActive = el("div", { "class": "mn-trim-active" });
            var trimPlayhead = el("div", { "class": "mn-trim-playhead" });
            trimBar.appendChild(trimActive);
            trimBar.appendChild(trimPlayhead);
            var trimInfo = el("div", { "class": "mn-trim-info" });

            (function(bk, ri, tss, tes, tsv, tev, vid, dSlider, dVal, pBtn, tBar, tActive, tPlayhead, tInfo) {
                var dur = 10;
                var previewTimers = [];

                function clearPreviewTimers() {
                    while (previewTimers.length) {
                        var t = previewTimers.pop();
                        clearTimeout(t); clearInterval(t);
                    }
                    pBtn.textContent = "\\u25B6 Preview Beat";
                    pBtn.classList.remove("playing");
                }

                function updateTrimBar() {
                    var ts = window._beatTrims[ri].start || 0;
                    var te = window._beatTrims[ri].end || dur;
                    var leftPct = (ts / dur) * 100;
                    var widthPct = ((te - ts) / dur) * 100;
                    tActive.style.left = leftPct + "%";
                    tActive.style.width = widthPct + "%";
                    var usable = te - ts;
                    var dl = window._beatDelays[ri] || 0;
                    var audioTime = Math.max(0, usable - dl);
                    tInfo.textContent = "Clip: " + ts.toFixed(1) + "s \\u2192 " + te.toFixed(1) + "s (" + usable.toFixed(1) + "s usable) | Lead-in: " + dl.toFixed(1) + "s silent, then " + audioTime.toFixed(1) + "s with audio";
                }

                // Constrain video playback to trim window
                // ONLY update dur/max/trim_end from the SELECTED video.
                // Bug fix (April 17 2026): previously attached to ALL videos,
                // which caused the shortest clip (e.g. Option A 5s) to clamp
                // trim_end to 5s even when Option B (10s) was selected.
                // Every pollStatus re-render re-fired the metadata listener
                // and reset the user's trim_end to match Option A's duration.
                function attachVideoListeners(v) {
                    v.addEventListener("loadedmetadata", function() {
                        var selVid = section.querySelector(".mn-anim-opt.selected video") || section.querySelector("video");
                        if (v !== selVid) return;  // skip non-selected
                        dur = v.duration;
                        tss.max = String(dur);
                        tes.max = String(dur);
                        dSlider.max = String(Math.min(dur, 10));
                        if (!window._beatTrims[ri].end || window._beatTrims[ri].end > dur) {
                            tes.value = String(dur);
                            window._beatTrims[ri].end = dur;
                            tev.textContent = "full";
                        }
                        var ts = window._beatTrims[ri].start || 0;
                        if (ts > 0) v.currentTime = ts;
                        updateTrimBar();
                    });
                }
                // Attach to all existing videos
                var allVids = section.querySelectorAll("video");
                for (var vi = 0; vi < allVids.length; vi++) attachVideoListeners(allVids[vi]);
                // Also observe for newly added videos (from generation)
                var secObs = new MutationObserver(function(muts) {
                    muts.forEach(function(m) {
                        m.addedNodes.forEach(function(n) {
                            if (n.tagName === "VIDEO") attachVideoListeners(n);
                            if (n.querySelectorAll) n.querySelectorAll("video").forEach(function(v2) { attachVideoListeners(v2); });
                        });
                    });
                });
                secObs.observe(section, { childList: true, subtree: true });
                // Update dur from selected video on click (option selection)
                section.addEventListener("click", function() {
                    setTimeout(function() {
                        var selVid = section.querySelector(".mn-anim-opt.selected video") || section.querySelector("video");
                        if (selVid && selVid.duration && isFinite(selVid.duration)) {
                            dur = selVid.duration;
                            tss.max = String(dur);
                            tes.max = String(dur);
                            dSlider.max = String(Math.min(dur, 10));
                            updateTrimBar();
                        }
                    }, 100);
                });
                if (vid) {
                    // Enforce trim boundaries during normal playback
                    vid.addEventListener("timeupdate", function() {
                        var ts = window._beatTrims[ri].start || 0;
                        var te = window._beatTrims[ri].end || dur;
                        if (vid.currentTime < ts) vid.currentTime = ts;
                        if (vid.currentTime >= te) { vid.pause(); vid.currentTime = te - 0.05; }
                        // Update playhead position
                        var pct = (vid.currentTime / dur) * 100;
                        tPlayhead.style.left = pct + "%";
                    });
                }

                // === Preview button: plays the FULL experience ===
                pBtn.onclick = function() {
                    if (pBtn.classList.contains("playing")) {
                        clearPreviewTimers();
                        if (vid) vid.pause();
                        if (cA) { cA.pause(); cA = null; }
                        return;
                    }
                    clearPreviewTimers();
                    pBtn.textContent = "\\u25A0 Stop Preview";
                    pBtn.classList.add("playing");

                    var ts = window._beatTrims[ri].start || 0;
                    var te = window._beatTrims[ri].end || dur;
                    var dl = window._beatDelays[ri] || 0;

                    // Start video at trim start
                    if (vid) {
                        vid.currentTime = ts;
                        vid.play().catch(function(){});
                    }

                    // After delay, start audio
                    var audioKey = L[ri] ? L[ri].a : null;
                    if (audioKey && AU[audioKey] && dl > 0) {
                        var t1 = setTimeout(function() {
                            if (!pBtn.classList.contains("playing")) return;
                            cA = new Audio(AU[audioKey]);
                            cA.play().catch(function(){});
                            cA.onended = function() { cA = null; };
                        }, dl * 1000);
                        previewTimers.push(t1);
                    } else if (audioKey && AU[audioKey]) {
                        cA = new Audio(AU[audioKey]);
                        cA.play().catch(function(){});
                        cA.onended = function() { cA = null; };
                    }

                    // Stop at trim end
                    var clipLen = (te - ts) * 1000;
                    var t2 = setTimeout(function() {
                        if (vid) vid.pause();
                        if (cA) { cA.pause(); cA = null; }
                        clearPreviewTimers();
                    }, clipLen + 200);
                    previewTimers.push(t2);
                };

                // === Delay slider ===
                dSlider.oninput = function() {
                    var v = parseFloat(this.value);
                    dVal.textContent = v.toFixed(1) + "s";
                    window._beatDelays[ri] = v;
                    if (vid) { vid.pause(); vid.currentTime = (window._beatTrims[ri].start || 0) + v; }
                    updateTrimBar();
                };
                dSlider.onchange = function() {
                    var v = parseFloat(this.value);
                    fetch(SERVER + "/api/beat/delay", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ beat: bk, audio_delay: v })
                    }).catch(function(e) { console.error("delay save:", e); });
                };

                // === Trim Start slider ===
                tss.oninput = function() {
                    var v = parseFloat(this.value);
                    tsv.textContent = v.toFixed(1) + "s";
                    window._beatTrims[ri].start = v;
                    if (vid) { vid.pause(); vid.currentTime = v; }
                    updateTrimBar();
                };
                tss.onchange = function() {
                    var v = parseFloat(this.value);
                    var endV = window._beatTrims[ri].end || null;
                    fetch(SERVER + "/api/beat/trim", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ beat: bk, trim_start: v, trim_end: endV })
                    }).catch(function(e) { console.error("trim save:", e); });
                };

                // === Trim End slider ===
                tes.oninput = function() {
                    var v = parseFloat(this.value);
                    tev.textContent = v.toFixed(1) + "s";
                    window._beatTrims[ri].end = v;
                    if (vid) { vid.pause(); vid.currentTime = v; }
                    updateTrimBar();
                };
                tes.onchange = function() {
                    var v = parseFloat(this.value);
                    var startV = window._beatTrims[ri].start || 0;
                    fetch(SERVER + "/api/beat/trim", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ beat: bk, trim_start: startV, trim_end: v })
                    }).catch(function(e) { console.error("trim save:", e); });
                };

                updateTrimBar();
            })(k, rowIdx, tsSlider, teSlider, tsVal, teVal, vidEl, delaySlider, delayVal, prevBtn, trimBar, trimActive, trimPlayhead, trimInfo);

            // ===== REGENERATE BUTTON =====
            var regenRow = el("div", { "class": "mn-regen-row" });
            var regenBtn = el("button", { "class": "mn-regen-btn" });
            var regenStatus = el("span", { "class": "mn-regen-status" });

            // Dynamic label: "Generate B + C" if single option, "Regenerate All" if multiple
            if (b.options.length <= 1) {
                regenBtn.textContent = "\\uD83C\\uDFAC Generate B + C";
            } else {
                regenBtn.textContent = "\\uD83D\\uDD04 Regenerate B + C";
            }

            (function(bk, ri, btn2, stat2, hasMultiple) {
                btn2.onclick = function() {
                    if (btn2.classList.contains("running")) return;
                    var msg = hasMultiple
                        ? "Replace B + C for Beat " + (ri + 1) + "? Option A will be kept."
                        : "Generate B + C options for Beat " + (ri + 1) + "? Option A will be kept.";
                    if (!confirm(msg)) return;

                    btn2.classList.add("running");
                    btn2.disabled = true;
                    btn2.textContent = "\\u23F3 Submitting...";
                    stat2.textContent = "Sending request to server (keeping Option A)...";

                    fetch(SERVER + "/api/beat/add_options", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ beat: bk, count: 2 })
                    }).then(function(resp) {
                        return resp.json();
                    }).then(function(data) {
                        // Item 7 (Tier 1, April 16 2026): detect silent failure.
                        // Server now returns 500 on all-failed, 200 with
                        // partial:true on mixed. Legacy clients only checked
                        // data.error — now also check new_submitted === 0.
                        if (data.error || data.new_submitted === 0) {
                            var errMsg = data.error
                              || (data.submit_errors && data.submit_errors[0])
                              || "All submissions failed — check server logs";
                            btn2.classList.remove("running");
                            btn2.disabled = false;
                            btn2.textContent = "\\u274C Retry — " + errMsg.substring(0, 60);
                            stat2.textContent = "Error: " + errMsg;
                            return;
                        }
                        if (data.partial) {
                            btn2.textContent = "\\u26A0\\uFE0F Partial: " + data.new_submitted + "/" + (data.new_submitted + (data.submit_errors || []).length);
                            stat2.textContent = "Partial success: " + data.new_submitted + " submitted, " + (data.submit_errors || []).length + " failed. Polling the ones that worked.";
                        } else {
                            btn2.textContent = "\\u23F3 Generating... (polling)";
                            stat2.textContent = "Submitted " + (data.new_submitted || "?") + " new jobs. Option A safe. Server is polling WaveSpeed.";
                        }

                        // Track this beat for NEW badge
                        if (!window._regenBeats) window._regenBeats = {};
                        window._regenBeats[bk] = Date.now();
                    }).catch(function(err) {
                        btn2.classList.remove("running");
                        btn2.disabled = false;
                        btn2.textContent = "\\u274C Retry Generate";
                        stat2.textContent = "Network error: " + err.message;
                    });
                };
            })(k, rowIdx, regenBtn, regenStatus, b.options.length > 1);

            regenRow.appendChild(regenBtn);
            regenRow.appendChild(regenStatus);

            // ===== NEW BADGE on freshly regenerated clips =====
            if (window._regenBeats && window._regenBeats[k]) {
                var regenTime = window._regenBeats[k];
                b.options.forEach(function(opt2, i2) {
                    if (i2 > 0) { // Options B and C (index 1, 2)
                        var optCards = section.querySelectorAll(".mn-anim-opt");
                        if (optCards && optCards[i2]) {
                            var badge = el("span", {
                                style: "position:absolute;top:4px;right:4px;background:#22c55e;color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold;z-index:10;"
                            }, ["\\u2728 NEW"]);
                            optCards[i2].style.position = "relative";
                            optCards[i2].appendChild(badge);
                        }
                    }
                });
            }

            // Assemble controls
            tc.appendChild(prevBtn);
            tc.appendChild(delayLabel);
            tc.appendChild(delaySlider);
            tc.appendChild(delayVal);

            trimGroup.appendChild(tsLabel);
            trimGroup.appendChild(tsSlider);
            trimGroup.appendChild(tsVal);
            trimGroup.appendChild(teLabel);
            trimGroup.appendChild(teSlider);
            trimGroup.appendChild(teVal);
            tc.appendChild(trimGroup);

            section.appendChild(regenRow);
            section.appendChild(tc);
            section.appendChild(trimBar);
            section.appendChild(trimInfo);

"""
    html = html[:idx] + inject + html[idx:]
    return html


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 patch_delay_trim.py <input.html> <output.html>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.is_file():
        print(f"ERROR: {input_path} not found")
        sys.exit(1)

    html = input_path.read_text(encoding="utf-8")

    # Extract base64 data for integrity check
    before_b64 = extract_base64_data(html)
    before_hash = hashlib.sha256("||".join(before_b64).encode()).hexdigest()
    print(f"[patch] Input: {input_path.name} ({len(html):,} chars, {len(before_b64)} base64 blocks)")

    # Apply patches
    html = patch_css(html)
    print("[patch] CSS injected ✓")

    html = patch_playline(html)
    print("[patch] playLine() patched with delay/trim support ✓")

    html = patch_inject_animations(html)
    print("[patch] injectAnimationsFromStatus() extended with controls ✓")

    # Verify base64 integrity
    after_b64 = extract_base64_data(html)
    after_hash = hashlib.sha256("||".join(after_b64).encode()).hexdigest()

    if before_hash != after_hash:
        print(f"ERROR: base64 data integrity FAILED!")
        print(f"  Before: {len(before_b64)} blocks, hash {before_hash[:16]}...")
        print(f"  After:  {len(after_b64)} blocks, hash {after_hash[:16]}...")
        sys.exit(1)

    print(f"[patch] Base64 integrity verified ✓ ({len(after_b64)} blocks, hash match)")

    # Write output
    output_path.write_text(html, encoding="utf-8")
    print(f"[patch] Output: {output_path.name} ({len(html):,} chars)")
    print("[patch] Done ✓")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Path B patch: Add GPT Stills mode button + poll loop to Beat Generator UI.

Fix-N:
  1. Adds global BG_GEN_MODE state ('gpt' | 'flux')
  2. Adds "Mode: GPT ✨" toggle button next to "Generate All Stills"
  3. Overrides _bgSubmitBatch to route to GPT or FLUX based on mode
  4. Adds _bgSubmitGptBatch() + 5s poll loop → POST /api/bg/submit-gpt-batch
  5. Patches _bgRenderBeats to show gpt_options || flux_options (spec GPT-5)

Input:  storyboard_v48_prod.html (if exists) or storyboard_v47_prod.html
Output: storyboard_v49_prod.html

Safety: SHA256 of all base64 blobs verified identical before/after.
"""
import hashlib, re, sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"

# Use v48 if it exists (sidebar-left fix applied), otherwise v47
SRC = _EVENT_DIR / "storyboard_v48_prod.html"
if not SRC.exists():
    SRC = _EVENT_DIR / "storyboard_v47_prod.html"
DEST = _EVENT_DIR / "storyboard_v49_prod.html"

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")


def b64_hash(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs:
        h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_hash(html)
print(f"Base64 blobs before: {count_before}, hash: {hash_before[:16]}…")

FIX_N = r"""
<script>
// ══════════════════════════════════════════════════════════════════════════
// Fix-N: GPT Stills mode button + poll loop (2026-04-26)
// Spec GPT-1 through GPT-12 (see GPT_STILLS_TECH_SPEC_v1.md)
// Routes Beat Generator stills to GPT or FLUX based on BG_GEN_MODE toggle.
// ══════════════════════════════════════════════════════════════════════════
(function () {
  "use strict";
  if (window._gptStillsInited) return;
  window._gptStillsInited = true;

  // ── 1. Global mode state ────────────────────────────────────────────────
  window.BG_GEN_MODE = 'gpt';  // 'gpt' | 'flux'

  // ── 2. Add mode toggle button next to "Generate All Stills" ─────────────
  function _addModeToggleBtn() {
    var genAllBtn = document.getElementById("bg-gen-all-btn");
    if (!genAllBtn || document.getElementById("bg-gen-mode-btn")) return;
    var btn = document.createElement("button");
    btn.id = "bg-gen-mode-btn";
    btn.className = "b";
    btn.style.cssText = "margin-left:8px;";
    btn.textContent = "Mode: GPT ✨";
    btn.addEventListener("click", function () {
      BG_GEN_MODE = (BG_GEN_MODE === 'gpt') ? 'flux' : 'gpt';
      btn.textContent = BG_GEN_MODE === 'gpt' ? "Mode: GPT ✨" : "Mode: FLUX ⚗️";
    });
    genAllBtn.parentNode.insertBefore(btn, genAllBtn.nextSibling);
  }

  // ── 3. Override _bgSubmitBatch to route by mode ──────────────────────────
  var _origSubmitBatch = window._bgSubmitBatch;
  window._bgSubmitBatch = function (beatIds) {
    if (window.BG_GEN_MODE === 'gpt') {
      window._bgSubmitGptBatch(beatIds);
    } else if (typeof _origSubmitBatch === 'function') {
      _origSubmitBatch(beatIds);
    }
  };

  // ── 4. GPT batch submit + poll ───────────────────────────────────────────
  window._bgSubmitGptBatch = function (beatIds) {
    var genBtn = document.getElementById("bg-gen-all-btn");
    if (genBtn) { genBtn.disabled = true; genBtn.textContent = "⏳ GPT Running…"; }

    fetch(BG_SERVER + "/api/bg/submit-gpt-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ beat_ids: beatIds })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.ok) {
        alert("GPT submit error: " + (d.error || "unknown"));
        if (genBtn) { genBtn.disabled = false; genBtn.textContent = "⚡ Generate All Stills"; }
        return;
      }
      var jobId = d.job_id;
      beatIds.forEach(function (bid) {
        var sp = document.getElementById("bg-status-" + bid);
        if (sp) sp.textContent = "GPT pending…";
      });
      if (genBtn) { genBtn.disabled = false; genBtn.textContent = "⚡ Generate All Stills"; }

      // Poll loop — 5s cadence matching FLUX poll
      var pollTimer = setInterval(function () {
        fetch(BG_SERVER + "/api/bg/poll-gpt-status?job_id=" + jobId)
        .then(function (r) { return r.json(); })
        .then(function (poll) {
          if (poll.error) { clearInterval(pollTimer); return; }

          Object.keys(poll.results || {}).forEach(function (bid) {
            var opts = poll.results[bid] || [];
            opts.forEach(function (opt, i) {
              if (!opt || !opt.thumb_b64) return;
              // Inject thumb into TH so future _bgRenderBeats finds it
              if (typeof TH !== 'undefined') TH[opt.key] = opt.thumb_b64;
              // Direct DOM update for instant display
              var slot = document.getElementById("bg-opt-" + bid + "-" + i);
              if (slot && !slot.querySelector("img")) {
                var img = document.createElement("img");
                var lbl = slot.querySelector(".bg-opt-lbl");
                if (lbl) { slot.insertBefore(img, lbl); } else { slot.prepend(img); }
                img.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:3px;cursor:pointer;";
                img.title = "Click to accept this option";
                img.src = opt.thumb_b64;
                img.onclick = (function (b, k) {
                  return function (e) {
                    e.stopPropagation();
                    fetch(BG_SERVER + "/api/bg/accept-option", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ beat_id: b, option_key: k })
                    }).then(function (r) { return r.json(); })
                    .then(function (d) {
                      if (d.ok && typeof _bgLoadState === 'function') _bgLoadState();
                    });
                  };
                }(bid, opt.key));
              }
              var sp = document.getElementById("bg-status-" + bid);
              if (sp) sp.textContent = poll.status === 'done' ? "GPT done" : "GPT running…";
            });
          });

          if (poll.status === "done") {
            clearInterval(pollTimer);
            if (typeof _bgLoadState === 'function') _bgLoadState();
          }
        })
        .catch(function (e) { console.warn("[GPT poll]", e); });
      }, 5000);
    })
    .catch(function (e) {
      alert("GPT submit failed: " + e);
      if (genBtn) { genBtn.disabled = false; genBtn.textContent = "⚡ Generate All Stills"; }
    });
  };

  // ── 5. Patch _bgRenderBeats: gpt_options || flux_options (spec GPT-5) ────
  var _origRenderBeats = window._bgRenderBeats;
  if (typeof _origRenderBeats === 'function') {
    window._bgRenderBeats = function (beats) {
      var patchedBeats = (beats || []).map(function (b) {
        if (b.gpt_options && b.gpt_options.length > 0) {
          if (typeof TH !== 'undefined') {
            b.gpt_options.forEach(function (opt) {
              if (opt && opt.key && opt.thumb_b64) TH[opt.key] = opt.thumb_b64;
            });
          }
          var clone = Object.assign({}, b);
          clone.flux_options = b.gpt_options;
          return clone;
        }
        return b;
      });
      return _origRenderBeats(patchedBeats);
    };
  }

  // ── 6. Wire up ───────────────────────────────────────────────────────────
  function _gptInit() { _addModeToggleBtn(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _gptInit);
  } else {
    _gptInit();
    setTimeout(_gptInit, 800);
  }
})();
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found"); sys.exit(1)

patched = html[:pos] + FIX_N + html[pos:]
print(f"Injected Fix-N ({len(FIX_N):,} chars) before </html>")

hash_after, count_after = b64_hash(patched)
if hash_before != hash_after or count_before != count_after:
    print("INTEGRITY FAIL"); sys.exit(1)
print(f"Base64 integrity verified: {count_after} blobs ✓")

DEST.write_text(patched, encoding="utf-8")
print(f"Wrote {DEST.name}")

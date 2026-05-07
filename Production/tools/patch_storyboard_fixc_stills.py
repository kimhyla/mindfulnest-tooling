#!/usr/bin/env python3
"""
Path B patch — Fix-C static stills (2026-04-25)
Appends a <script> block to storyboard_v43_prod.html that:
  1. Replaces _bgLoadState with refresh-safe version (rehydrates from local_path URL)
  2. Wraps _bgRenderBeats to render option slots from /bg-stills/ URLs
  3. Replaces _bgPollStatus so it always updates existing img.src (not just creates)
  4. Updates _crLoadImage to fall back to /bg-stills/ URL when TH[key] missing
  5. Wraps _bgSubmitBatch for click feedback (spinner + toast)
  6. Adds _bgReconcilePolls for stale _task_rids handling

Rule 7 compliance:
  - Only appends a new <script> block — no existing content changed
  - Authored base64 image data is byte-identical before/after
  - Run --audit-previous after to confirm feature parity
"""

import hashlib
import re
import sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixc_backup.html"

def sha256_b64(html: str) -> tuple[int, str]:
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    digest = hashlib.sha256(("".join(b64s)).encode()).hexdigest()
    return len(b64s), digest

PATCH_SCRIPT = """\

<script>
// =====================================================================
// FIX-C STATIC STILLS PATCH (2026-04-25)
// Root cause: TH (browser-memory thumbnail cache) is ephemeral — dies
// on every page refresh. Option slots render as black boxes even when
// PNGs are already on disk.
// Fix: persisted flux_options use /bg-stills/<filename> static URLs.
//      TH fallback retained for in-flight (not-yet-downloaded) options.
// Authored storyboard base64 images (dialogue cells) are NOT touched.
// Changes in this patch:
//   C2  _bgRenderBeats wrap   — URL render + button labels
//   C3  _crLoadImage override — XHR fallback to /bg-stills/ when TH empty
//   C4  _bgPollStatus replace — always update existing img.src (not skip)
//   C5  _bgLoadState replace  — reconcile polls on load
//   C6  _bgSubmitBatch wrap   — spinner + toast feedback
// =====================================================================
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // C5: Replace _bgLoadState — rehydrates slots via _bgRenderBeats (which
  //     now uses URLs), then reconciles any stale pending poll tasks.
  // ------------------------------------------------------------------
  window._bgLoadState = function () {
    fetch(BG_SERVER + "/api/bg/session-state")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.beats && d.beats.length) {
          BG_BEATS = d.beats;
          _bgRenderBeats(BG_BEATS);          // C2 wrapper runs here
          var acceptBtn = document.getElementById("bg-accept-btn");
          if (acceptBtn) acceptBtn.disabled = false;
          _bgReconcilePolls();               // C5 helper
        }
        if (d.active_context) {
          BG_ARC = d.active_context.arc_number;
          document.querySelectorAll(".bg-arc-btn").forEach(function (b) {
            if (parseInt(b.getAttribute("data-arc"), 10) === BG_ARC) {
              b.classList.add("sel");
              _bgLoadSegments(BG_ARC);
            }
          });
        }
      })
      .catch(function () {});
  };

  // C5 helper: restore BG_TASK_MAP from _task_rids so fresh jobs keep polling
  window._bgReconcilePolls = function () {
    var needsPoll = false;
    (BG_BEATS || []).forEach(function (beat) {
      if (!beat._task_rids || !beat._task_rids.length) return;
      // Always restore — even if local_path exists, a regen may be in flight
      BG_TASK_MAP[beat.beat_id] = beat._task_rids.slice();
      needsPoll = true;
    });
    if (needsPoll && !BG_POLL_ID) {
      BG_POLL_ID = setInterval(_bgPollStatus, 5000);
    }
  };

  // ------------------------------------------------------------------
  // C2: Wrap _bgRenderBeats — after the existing render, overwrite option
  //     slot imgs that have local_path with a /bg-stills/ URL, and update
  //     button labels.
  // ------------------------------------------------------------------
  var _bgRenderBeats_prev = _bgRenderBeats;
  _bgRenderBeats = function (beats) {
    _bgRenderBeats_prev(beats || BG_BEATS);

    (beats || BG_BEATS).forEach(function (beat) {
      var opts = beat.flux_options || [];

      // Update option slot images
      opts.forEach(function (fopt, o) {
        if (!fopt || !fopt.local_path) return;
        var fname = fopt.local_path.split("/").pop();
        if (!fname) return;
        // cache-buster: request_id is unique per generation run
        var url = BG_SERVER + "/bg-stills/" + encodeURIComponent(fname)
                + "?v=" + encodeURIComponent(fopt.request_id || "0");
        var slot = document.getElementById("bg-opt-" + beat.beat_id + "-" + o);
        if (!slot) return;
        var img = slot.querySelector("img");
        if (!img) {
          img = document.createElement("img");
          slot.insertBefore(img, slot.firstChild);
        }
        // Only update src if it differs (avoid unnecessary reloads)
        if (img.getAttribute("data-fixc-url") !== url) {
          img.setAttribute("data-fixc-url", url);
          img.src = url;
        }
        if (fopt.key && fopt.key === beat.accepted_image_key) {
          slot.classList.add("chosen");
        }
      });

      // Button label
      var card = document.getElementById("bg-card-" + beat.beat_id);
      if (!card) return;
      var btn = card.querySelector(".bg-gen-btn");
      if (!btn) return;
      var hasExisting = opts.some(function (o) { return o && o.local_path; });
      btn.textContent = hasExisting ? "\\u21ba Regenerate Stills" : "\\u26a1 Generate Stills";
    });
  };

  // ------------------------------------------------------------------
  // C4: Replace _bgPollStatus — always update existing img.src when a
  //     fresh FLUX job completes (original only created if !existing).
  // ------------------------------------------------------------------
  _bgPollStatus = function () {
    var pending = [];
    Object.keys(BG_TASK_MAP).forEach(function (bid) {
      (BG_TASK_MAP[bid] || []).forEach(function (rid) {
        if (rid) pending.push(rid);
      });
    });
    if (!pending.length) {
      clearInterval(BG_POLL_ID);
      BG_POLL_ID = null;
      return;
    }

    fetch(BG_SERVER + "/api/bg/poll-flux-status?request_ids=" + pending.join(","))
      .then(function (r) { return r.json(); })
      .then(function (results) {
        var allDone = true;
        Object.keys(BG_TASK_MAP).forEach(function (bid) {
          (BG_TASK_MAP[bid] || []).forEach(function (rid, optIdx) {
            if (!rid) return;
            var r = results[rid];
            if (r && r.status === "ready") {
              // Populate TH and gallery for in-session use
              if (r.key && r.thumb_b64 && r.gallery_b64) {
                _injectImage(r.key, r.filename || r.key, r.thumb_b64, r.gallery_b64);
              }
              // Always update slot img.src (C4 fix: was if(!existing) only)
              var slot = document.getElementById("bg-opt-" + bid + "-" + optIdx);
              if (slot && r.thumb_b64) {
                var existing = slot.querySelector("img");
                if (existing) {
                  existing.src = r.thumb_b64;          // transition URL→data-URI
                  existing.removeAttribute("data-fixc-url"); // clear URL marker
                } else {
                  var img = document.createElement("img");
                  img.src = r.thumb_b64;
                  slot.insertBefore(img, slot.firstChild);
                }
              }
              // Update in-memory beat record
              var beat = (BG_BEATS || []).find(function (b) { return b.beat_id === bid; });
              if (beat) {
                beat.flux_options = beat.flux_options || [];
                beat.flux_options[optIdx] = { key: r.key, request_id: rid };
                var sp = document.getElementById("bg-status-" + bid);
                if (sp) sp.textContent = "stills ready";
              }
              BG_TASK_MAP[bid][optIdx] = null;
            } else if (r && r.status === "error") {
              BG_TASK_MAP[bid][optIdx] = null;
            } else {
              allDone = false;
            }
          });
        });
        if (allDone) {
          clearInterval(BG_POLL_ID);
          BG_POLL_ID = null;
        }
      })
      .catch(function (e) { console.warn("[BG] poll error:", e); });
  };

  // ------------------------------------------------------------------
  // C3: Override _crLoadImage — if TH[key] is empty (post-refresh),
  //     fetch the PNG from /bg-stills/, convert to data URL, populate
  //     TH, then call original. Only fires on cache miss.
  //     Only FLUX still keys match pattern bg_*_opt* → .png
  // ------------------------------------------------------------------
  var _crLoadImage_orig = _crLoadImage;
  _crLoadImage = function (key, beatId) {
    if (TH[key]) {
      // TH populated (in-flight or already fetched) — original path
      _crLoadImage_orig(key, beatId);
      return;
    }
    // Cache miss: try /bg-stills/
    var url = BG_SERVER + "/bg-stills/" + encodeURIComponent(key + ".png")
            + "?v=" + Date.now();
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.responseType = "blob";
    xhr.onload = function () {
      if (xhr.status === 200) {
        var reader = new FileReader();
        reader.onload = function () {
          TH[key] = reader.result;           // populate TH from disk
          _crLoadImage_orig(key, beatId);    // original function works normally
        };
        reader.readAsDataURL(xhr.response);
      } else {
        alert("Image not found on disk: " + key);
      }
    };
    xhr.onerror = function () { alert("Failed to load image: " + key); };
    xhr.send();
  };

  // ------------------------------------------------------------------
  // C6: Wrap _bgSubmitBatch — spinner on click, toast on success
  // ------------------------------------------------------------------
  var _bgSubmitBatch_prev = _bgSubmitBatch;
  _bgSubmitBatch = function (beatIds) {
    // Immediate feedback: disable + spinner
    beatIds.forEach(function (bid) {
      var card = document.getElementById("bg-card-" + bid);
      if (!card) return;
      var btn = card.querySelector(".bg-gen-btn");
      if (btn) { btn.disabled = true; btn.textContent = "\\u23f3 Submitting\\u2026"; }
    });

    fetch(BG_SERVER + "/api/bg/submit-flux-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ beat_ids: beatIds })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) {
          alert("Submit error: " + d.error);
          _fixc_restoreBtns(beatIds);
          return;
        }
        Object.assign(BG_TASK_MAP, d.task_map || {});
        beatIds.forEach(function (bid) {
          var sp = document.getElementById("bg-status-" + bid);
          if (sp) sp.textContent = "pending\\u2026";
        });
        if (!BG_POLL_ID) BG_POLL_ID = setInterval(_bgPollStatus, 5000);
        _fixc_restoreBtns(beatIds);
        _fixc_toast("\\u2713 Submitted " + (beatIds.length * 3) + " jobs \\u2014 images appear in ~30s");
      })
      .catch(function (e) {
        alert("Submit failed: " + e);
        _fixc_restoreBtns(beatIds);
      });
  };

  function _fixc_restoreBtns(beatIds) {
    beatIds.forEach(function (bid) {
      var card = document.getElementById("bg-card-" + bid);
      if (!card) return;
      var btn = card.querySelector(".bg-gen-btn");
      if (!btn) return;
      btn.disabled = false;
      var beat = (BG_BEATS || []).find(function (b) { return b.beat_id === bid; });
      var has = beat && (beat.flux_options || []).some(function (o) { return o && o.local_path; });
      btn.textContent = has ? "\\u21ba Regenerate Stills" : "\\u26a1 Generate Stills";
    });
  }

  window._fixc_toast = function (msg) {
    var t = document.createElement("div");
    t.style.cssText = [
      "position:fixed", "bottom:24px", "right:24px",
      "background:#1b4332", "color:#b7e4c7",
      "padding:10px 18px", "border-radius:8px",
      "font-size:12px", "z-index:9999",
      "box-shadow:0 2px 10px rgba(0,0,0,.5)"
    ].join(";");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () {
      if (t.parentNode) t.parentNode.removeChild(t);
    }, 4000);
  };

})();
// === END FIX-C STATIC STILLS PATCH ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")

    # Pre-patch base64 audit
    b64_count_before, b64_hash_before = sha256_b64(html)
    print(f"  Base64 blocks before: {b64_count_before}, sha256: {b64_hash_before}")

    # Check not already patched
    if "FIX-C STATIC STILLS PATCH" in html:
        print("ERROR: patch marker already present — refusing to double-patch.")
        sys.exit(1)

    # Backup
    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup written: {BACKUP_PATH.name}")

    # Apply: insert before </body>
    if "</body>" not in html:
        print("ERROR: </body> tag not found.")
        sys.exit(1)

    patched = html.replace("</body>", PATCH_SCRIPT, 1)

    # Post-patch base64 audit
    b64_count_after, b64_hash_after = sha256_b64(patched)
    print(f"  Base64 blocks after:  {b64_count_after}, sha256: {b64_hash_after}")

    if b64_hash_before != b64_hash_after or b64_count_before != b64_count_after:
        print("ABORT: base64 content changed — patch corrupted authored images.")
        sys.exit(1)
    print("  ✓ Base64 byte-identical — no authored images touched")

    # Write
    HTML_PATH.write_text(patched, encoding="utf-8")
    size_kb = HTML_PATH.stat().st_size // 1024
    print(f"  ✓ Written: {HTML_PATH.name} ({size_kb} KB)")
    print("Done.")

if __name__ == "__main__":
    main()

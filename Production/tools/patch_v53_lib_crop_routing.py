#!/usr/bin/env python3
"""
Path B patch: storyboard v52 → v53 — library-image Crop button routing.

Fix-R:
  Enables the "Crop" button on beat slots that hold library-dropped images
  (which v51's Fix-P deliberately disabled with comment "Library images are
  not FLUX stills — the BG cropper operates on .png files in BG_STILLS_DIR
  only. Kim can crop separately via Cropper tab").

  Approach:
    1. Wrap window._bgHandleLibSlotDrop (which is Fix-P's wrapper at install
       time) — after the original runs (and disables the cropBtn), re-enable
       cropBtn and set title="Crop this library image".
    2. Add a capture-phase document-level click listener on .bg-opt-crop:
       - If clicked button's slot contains <img data-lib-key="...">:
         * preventDefault + stopPropagation + stopImmediatePropagation
           (belt-and-suspenders for Safari capture-phase compliance)
         * Look up libItem in MN_LIB_DATA by lib key
         * If abs_path empty: trigger _mnLibFetch() then retry once at 500ms
         * GET /api/cr/full?abs_path=... (existing endpoint, verified server
           handler at production_server.py L5183-5208)
         * On success: load data_uri into CR_IMG, default 4:3 CR_CROP_BOX,
           set CR_BEAT_ID = slot.getAttribute('data-beat') (NOT null —
           this routes the cropped result back to the slot via existing
           _crSaveCrop V5 at v52 L7263-7369), set CR_SRC_KEY = libKey,
           call _crDraw(), enable cr-save-btn, switch to Cropper tab
           via _bgSwitchTab('cr', null)
         * On error: alert with server's error field
       - Otherwise: do nothing (let inline onclick fire — flux path
         unchanged)

Counter-agent (Phase 0 zero-error-qa) findings addressed at root cause:
  CRIT — CR_BEAT_ID routing: set to slot data-beat, NOT null; existing
         _crSaveCrop V5 handles save → library + BG_BEATS update + preview
         inject correctly
  CRIT — Post-crop return path: ALREADY DEFINED by _crSaveCrop V5 at
         v52 L7263-7369; fires _injectAcceptedPreview after save
  HIGH — data-lib-key zombie race: working-as-designed (cleared slots
         fall through to flux 404 alert path)
  HIGH — Race lib-drop POST vs Crop click: not a race — data-lib-key set
         synchronously at v52 L6351 BEFORE accept-lib-image POST fires
  HIGH — Fix-P wrap order: verified inline Fix-P at L6361 runs before
         this IIFE injection point; Fix-R captures Fix-P's wrapper as
         "original" — correct sequence
  MED  — Repeat-click after cropper abandon: each click freshly sets state
  MED  — abs_path freshness: auto-trigger _mnLibFetch() then retry once
         at 500ms before alerting
  MED  — Fix-Q intercept: verified FixQ URL list excludes /api/cr/full
  MED  — Safari capture-phase stopImmediatePropagation: belt-and-suspenders
         triple-stop (preventDefault + stopPropagation + stopImmediatePropagation)

Approach: Path B JS-only injection (per CLAUDE.md Rule 7). Same shape as
v51 Fix-P (LD-446) and v52 Fix-Q (LD-447 / preflight 181).

Input:  Production/Event_1/storyboard_v52_prod.html
Output: Production/Event_1/storyboard_v53_prod.html

Safety gates (HARD STOP on failure):
  - </html> exists exactly once in source
  - _fixR_installed not already present in source (idempotency)
  - SHA256 of all base64 blobs byte-identical before/after
  - Atomic write: .tmp file first, only renamed to final on all-checks-pass
  - readback verifies the _fixR_installed sentinel is in the final file

Phase 0 Directus row: prod_preflight_reviews id=182
LD: LIB_CROP_ROUTING_V1 (to register on Kim approval after live test)
"""
import hashlib
import os
import re
import sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v52_prod.html"
DEST = _EVENT_DIR / "storyboard_v53_prod.html"
TMP  = _EVENT_DIR / "storyboard_v53_prod.html.tmp"

if not SRC.exists():
    print(f"ERROR: source {SRC} not found", file=sys.stderr)
    sys.exit(2)

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")

# Gate 1 — </html> exactly once
end_count = html.count("</html>")
if end_count != 1:
    print(f"ERROR: </html> appears {end_count} times in source (expected 1)", file=sys.stderr)
    sys.exit(2)

# Gate 2 — idempotency
if "_fixR_installed" in html:
    print("ERROR: source already contains _fixR_installed — already patched", file=sys.stderr)
    sys.exit(2)

# Gate 2b — confirm Fix-Q (v52) is present so we know we're patching v52, not an older version
if "_fixQ_installed" not in html:
    print("ERROR: source missing _fixQ_installed sentinel — this is not a v52 file", file=sys.stderr)
    sys.exit(2)


def b64_signature(text: str):
    """Returns (sha256_hex, count) over all base64 blobs >100 chars."""
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs:
        h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_signature(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")


FIX_R = r"""
<script>
// =====================================================================
// Fix-R: Library-image Crop button routing (2026-05-01)
//
// Enables the per-slot Crop button on library-dropped beat slots
// (which v51 Fix-P deliberately disabled). On click of a lib-slot
// Crop button: fetch full-res via /api/cr/full?abs_path= (same path
// Fix-L uses), load into the cropper canvas, then switch to Cropper
// tab. CR_BEAT_ID is set to the slot's data-beat so existing
// _crSaveCrop V5 routes the cropped result back to the slot via
// _injectAcceptedPreview after Save.
//
// Wrap order (IMPORTANT): this IIFE injects before </html>, so when it
// runs, window._bgHandleLibSlotDrop is ALREADY Fix-P's wrapper (Fix-P
// inline at v52 L6361 runs first). Fix-R captures Fix-P's wrapper as
// "original" and runs AFTER it — so the sequence is:
//   base function disables cropBtn → Fix-P does post-work →
//   Fix-R re-enables cropBtn + sets title.
//
// LD: LIB_CROP_ROUTING_V1 (preflight 182)
// =====================================================================
(function FixR() {
  "use strict";
  if (window._fixR_installed) return;
  window._fixR_installed = true;
  console.log("[Fix-R] Library-image Crop routing active");

  // ── 1. Wrap _bgHandleLibSlotDrop to re-enable cropBtn ──────────────
  // _bgHandleLibSlotDrop has already been wrapped by Fix-P (inline at
  // v52 L6361). At install time, window._bgHandleLibSlotDrop refers to
  // Fix-P's wrapper. We wrap that wrapper so our re-enable runs LAST.
  var _origLibDrop = window._bgHandleLibSlotDrop;
  if (typeof _origLibDrop === "function") {
    window._bgHandleLibSlotDrop = function (slot, beatId, slotIdx, libItem) {
      // Run Fix-P's wrapper (which runs the base, disables cropBtn,
      // does its zombie-cleanup + thumbnail injection)
      _origLibDrop.call(this, slot, beatId, slotIdx, libItem);
      // Now re-enable + label the Crop button — Fix-R routing will
      // detect the data-lib-key on click and route via /api/cr/full
      var cropBtn = slot.querySelector(".bg-opt-crop");
      if (cropBtn) {
        cropBtn.disabled = false;
        cropBtn.title = "Crop this library image";
      }
    };
  }

  // ── 2. Helper: load image into cropper from a data URI ──────────────
  function _fixR_loadIntoCropper(dataUri, libKey, beatId) {
    var img = new Image();
    img.onload = function () {
      window.CR_IMG     = img;
      window.CR_BEAT_ID = beatId;     // routes cropped result back to slot
      window.CR_SRC_KEY = libKey;
      var cw = Math.min(img.width, img.height * 4 / 3);
      var ch = cw * 3 / 4;
      window.CR_CROP_BOX = {
        x: (img.width  - cw) / 2,
        y: (img.height - ch) / 2,
        w: cw, h: ch
      };
      if (typeof _crDraw === "function") _crDraw();
      var info = document.getElementById("cr-crop-info");
      if (info) info.textContent = "Image: " + img.width + "×" + img.height
        + "px  Crop: 4:3";
      var saveBtn = document.getElementById("cr-save-btn");
      if (saveBtn) saveBtn.disabled = false;
      // Switch to Cropper tab AFTER image is loaded so _crDraw has
      // a non-zero canvas size to draw into
      if (typeof _bgSwitchTab === "function") {
        _bgSwitchTab("cr", null);
      } else {
        // Defensive fallback if _bgSwitchTab signature drifts.
        // Phase 3 fix: deactivate ALL panels first so we don't end up with
        // two visible simultaneously (matches what the real _bgSwitchTab does).
        var allPanels = document.querySelectorAll(".tab-panel");
        for (var pi = 0; pi < allPanels.length; pi++) {
          allPanels[pi].classList.remove("active");
        }
        var crPanel = document.getElementById("panel-cr");
        if (crPanel) crPanel.classList.add("active");
      }
    };
    img.onerror = function () {
      alert("Failed to load library image into cropper.");
    };
    img.src = dataUri;
  }

  // ── 3. Helper: fetch full-res from server, then load ────────────────
  function _fixR_fetchAndLoad(libItem, beatId) {
    var absPath = libItem && libItem.abs_path;
    if (!absPath) {
      alert("Library image not ready (no abs_path). Try again in a moment.");
      return;
    }
    fetch(BG_SERVER + "/api/cr/full?abs_path=" + encodeURIComponent(absPath))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok || !d.data_uri) {
          alert("Failed to load library image: "
            + ((d && d.error) || "unknown server error"));
          return;
        }
        _fixR_loadIntoCropper(d.data_uri, libItem.key, beatId);
      })
      .catch(function (e) {
        alert("Library image fetch error: " + (e && e.message || "network"));
      });
  }

  // ── 4. Helper: lookup libItem in MN_LIB_DATA by key ─────────────────
  function _fixR_findLibItem(libKey) {
    var data = window.MN_LIB_DATA;
    if (!Array.isArray(data)) return null;
    for (var i = 0; i < data.length; i++) {
      if (data[i] && data[i].key === libKey) return data[i];
    }
    return null;
  }

  // ── 5. Capture-phase delegated click handler ────────────────────────
  document.addEventListener("click", function (e) {
    // Phase 3 fix: use closest(.bg-opt-crop) to handle clicks on hypothetical
    // child elements (icons / spans). Today the cropBtn has no children but
    // this is robust to future markup changes.
    var btn = e.target && e.target.closest
      ? e.target.closest(".bg-opt-crop")
      : null;
    if (!btn) return;
    var slot = btn.closest(".bg-opt");
    if (!slot) return;
    var img = slot.querySelector("img[data-lib-key]");
    if (!img) {
      // Not a lib-dropped slot — let inline onclick fire (flux path)
      return;
    }
    var libKey = img.getAttribute("data-lib-key");
    var beatId = slot.getAttribute("data-beat");
    if (!libKey || !beatId) return;

    // Belt-and-suspenders triple-stop for Safari capture-phase compliance
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    // Look up libItem; if abs_path empty, refresh library and retry once
    var libItem = _fixR_findLibItem(libKey);
    if (!libItem) {
      alert("Library entry not found for key: " + libKey
        + ". Try refreshing the library panel.");
      return;
    }
    if (!libItem.abs_path) {
      // Stale MN_LIB_DATA — trigger refresh and retry once.
      // Phase 3 fix: handle BOTH Promise-returning AND sync _mnLibFetch.
      if (typeof _mnLibFetch === "function") {
        var afterFetch = function () {
          var refreshed = _fixR_findLibItem(libKey);
          if (refreshed && refreshed.abs_path) {
            _fixR_fetchAndLoad(refreshed, beatId);
          } else {
            alert("Library image abs_path not yet available. "
              + "Wait a moment and click Crop again.");
          }
        };
        var p = _mnLibFetch();
        if (p && typeof p.then === "function") {
          p.then(afterFetch).catch(function () { afterFetch(); });
        } else {
          // Sync (or no Promise returned) — fall back to setTimeout
          setTimeout(afterFetch, 500);
        }
        return;
      }
      alert("Library image abs_path missing. Try reloading the page.");
      return;
    }

    _fixR_fetchAndLoad(libItem, beatId);
  }, true);  // capture phase — fires before inline onclick on the same element
})();
// === END Fix-R ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found", file=sys.stderr)
    sys.exit(2)

patched = html[:pos] + FIX_R + html[pos:]
print(f"Injected Fix-R ({len(FIX_R):,} chars) before </html>")

# Gate 3 — base64 byte-identical
hash_after, count_after = b64_signature(patched)
if hash_before != hash_after or count_before != count_after:
    print(
        f"INTEGRITY FAIL — base64 blob count {count_before} → {count_after}, "
        f"hash {hash_before[:16]}... → {hash_after[:16]}...",
        file=sys.stderr,
    )
    sys.exit(3)
print(f"Base64 integrity verified: {count_after} blobs, sha256 {hash_after[:16]}... unchanged")

# Atomic write — .tmp first, only rename on all-checks-pass
TMP.write_text(patched, encoding="utf-8")
print(f"Wrote tmp {TMP.name}: {len(patched):,} chars")

# Final verification — read back tmp, re-compute hash, check sentinel
verify_text = TMP.read_text(encoding="utf-8")
hash_verify, count_verify = b64_signature(verify_text)
if hash_verify != hash_after or count_verify != count_after:
    print(f"VERIFY FAIL — tmp file disagrees with computed patch", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
if "_fixR_installed" not in verify_text:
    print("VERIFY FAIL — tmp file missing _fixR_installed sentinel", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
if "_fixQ_installed" not in verify_text:
    print("VERIFY FAIL — tmp file lost _fixQ_installed sentinel", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
if "_fixPInited" not in verify_text:
    print("VERIFY FAIL — tmp file lost _fixPInited sentinel (Fix-P regression)", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
print(f"Tmp readback verified: {count_verify} blobs, sha256 {hash_verify[:16]}...")
print(f"  Sentinels present: _fixR_installed (NEW), _fixQ_installed, _fixPInited")

# All gates passed — atomic rename
os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:      {SRC.name}  ({len(html):,} chars)")
print(f"  Output:      {DEST.name}  ({len(patched):,} chars)")
print(f"  Delta:       +{len(patched) - len(html):,} chars (Fix-R IIFE)")
print(f"  Base64 sha:  {hash_after[:16]}... ({count_after} blobs, unchanged)")
print(f"  Sentinels:   Fix-P (LD-446), Fix-Q (LD-447), Fix-R (NEW LD)")

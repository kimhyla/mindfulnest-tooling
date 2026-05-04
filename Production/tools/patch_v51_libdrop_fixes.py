#!/usr/bin/env python3
"""
Path B patch: Beat Generator library-drop 3-bug fix v50 → v51.

Fix-P:
  1. (Bug 2) Wrap window._crLoadImage to strip double bg_bg_ prefix from crop
     key fallback. Happens when beat_id already starts with bg_ (e.g.
     bg_arc1_event2_pre_beat_07) and flux_options[i].key is absent, producing
     "bg_" + "bg_arc1_event2_pre_beat_07" + "_opt0" = "bg_bg_..._opt0".

  2. (Bug 1) Wrap window._bgHandleLibSlotDrop to clean up zombie sibling imgs.
     _bgHandleLibSlotDrop's clear loop removes data-lib-key but leaves img.src
     visible on sibling slots. These "zombie" imgs cause Crop to fire with the
     wrong fallback key (Bug 2) and confuse Kim about slot state.

  3. (Bug 3) After lib-drop, inject the accepted thumbnail into the top-right
     .bg-accepted-preview corner (same UX as "cropped ✓" from normal FLUX crops).
     Uses window.TH[key] which _bgHandleLibSlotDrop populates synchronously
     BEFORE the fetch fires — so it's always available in the wrapper.

Approach: wrap _bgHandleLibSlotDrop rather than window.fetch, which avoids
conflicting with the existing CRFIX-LIBFIX-V10 fetch interceptor.

Input:  Production/Event_1/storyboard_v50_prod.html
Output: Production/Event_1/storyboard_v51_prod.html

Safety: SHA256 of all base64 blobs verified byte-identical before/after.
"""
import hashlib
import re
import sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v50_prod.html"
DEST = _EVENT_DIR / "storyboard_v51_prod.html"

if not SRC.exists():
    print(f"ERROR: {SRC} not found")
    sys.exit(1)

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

FIX_P = r"""
<script>
// =====================================================================
// Fix-P: Library-drop 3-bug fix (2026-04-29)
//   Bug 1 — Zombie sibling imgs after lib-drop clear loop
//   Bug 2 — Double bg_bg_ prefix in crop-key fallback
//   Bug 3 — Missing top-right thumbnail on lib-drop acceptance
//
// Wraps _bgHandleLibSlotDrop (NOT window.fetch) to avoid conflicting with
// the existing CRFIX-LIBFIX-V10 fetch interceptor.
// =====================================================================
(function () {
  "use strict";
  if (window._fixPInited) return;
  window._fixPInited = true;

  // ── Bug 2: Strip double bg_bg_ prefix from crop-key fallback ────────
  // The crop button onclick constructs: "bg_" + b.beat_id + "_opt" + oi
  // When beat_id already starts with "bg_", this gives "bg_bg_..._optN".
  var _crLI_prev = window._crLoadImage;
  if (typeof _crLI_prev === "function") {
    window._crLoadImage = function (key, beatId) {
      if (typeof key === "string" && key.indexOf("bg_bg_") === 0) {
        key = key.substring(3);  // strip leading "bg_" → "bg_arc1_..."
      }
      return _crLI_prev.call(this, key, beatId);
    };
  }

  // ── Bug 1 + Bug 3: Wrap _bgHandleLibSlotDrop ────────────────────────
  // _bgHandleLibSlotDrop is a top-level function declaration = window property.
  // The drop event listener calls it by name from global scope, so overriding
  // window._bgHandleLibSlotDrop here intercepts every lib-drop.
  var _prevLibDrop = window._bgHandleLibSlotDrop;
  if (typeof _prevLibDrop === "function") {
    window._bgHandleLibSlotDrop = function (slot, beatId, slotIdx, libItem) {
      // Call original first (handles clear loop, TH population, fetch)
      _prevLibDrop.call(this, slot, beatId, slotIdx, libItem);

      // Bug 1: Remove zombie imgs from sibling slots that have no FLUX option.
      // The original clear loop removed data-lib-key but left img.src, making
      // sibling slots look like they have FLUX stills (they don't).
      var card = document.getElementById("bg-card-" + beatId);
      if (card) {
        var allSlots = card.querySelectorAll(".bg-opt");
        for (var si = 0; si < allSlots.length; si++) {
          var s = allSlots[si];
          var sIdx = parseInt(s.getAttribute("data-opt") || "0", 10);
          if (sIdx === slotIdx) { continue; }      // skip target slot
          var im = s.querySelector("img");
          if (!im) { continue; }                   // no img to clean
          if (im.getAttribute("data-lib-key")) { continue; }  // target lib img
          // Only remove if the slot has no real FLUX option in BG_BEATS
          var beat = null;
          var beats = window.BG_BEATS;
          if (Array.isArray(beats)) {
            for (var j = 0; j < beats.length; j++) {
              if (beats[j].beat_id === beatId) { beat = beats[j]; break; }
            }
          }
          var hasFlux = beat && beat.flux_options
                     && beat.flux_options[sIdx]
                     && beat.flux_options[sIdx].key;
          if (!hasFlux) {
            im.parentNode.removeChild(im);
          }
        }
      }

      // Bug 3: Inject top-right thumbnail — TH[key] is set synchronously
      // by the original _bgHandleLibSlotDrop before the fetch fires.
      // Small setTimeout to let DOM settle after the original's mutations.
      var libKey = libItem && libItem.key;
      if (libKey) {
        setTimeout(function () {
          var b64 = window.TH && window.TH[libKey];
          if (b64 && typeof window._injectAcceptedPreview === "function") {
            window._injectAcceptedPreview(beatId, b64);
          }
        }, 80);
      }
    };
  }

  console.log("[Fix-P] Library-drop 3-bug fix active — _crLoadImage + _bgHandleLibSlotDrop patched.");
})();
// === END Fix-P ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found")
    sys.exit(1)

patched = html[:pos] + FIX_P + html[pos:]
print(f"Injected Fix-P ({len(FIX_P):,} chars) before </html>")

hash_after, count_after = b64_hash(patched)
if hash_before != hash_after or count_before != count_after:
    print(f"INTEGRITY FAIL — base64 blob count {count_before} → {count_after}, hash changed!")
    sys.exit(1)
print(f"Base64 integrity verified: {count_after} blobs, hash {hash_after[:16]}... OK")

DEST.write_text(patched, encoding="utf-8")
print(f"Wrote {DEST.name}: {len(patched):,} chars")
print("Patch complete.")

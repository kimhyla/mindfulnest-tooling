#!/usr/bin/env python3
"""
Path B patch: storyboard v53 → v54 — keep cropBtn enabled on lib-dropped
slots after _bgRenderBeats re-hydration, plus libItem-null retry.

Fix-S (LD-449 to register, preflight 183):

Two concurrent bugs identified per Rule 28 Three-Bug Diagnosis after
v53 Fix-R failed to move the symptom:

  Bug 1 (PRIMARY) — re-hydration wrapper at v52/v53 line 6450 sets
  cropBtn.disabled=true after Fix-R's _bgHandleLibSlotDrop wrap re-enables
  it. Disabled buttons do NOT dispatch click events per HTML spec, so
  Fix-R's capture-phase document listener was structurally incapable of
  firing on lib-dropped slots after re-hydration (initial render or any
  state change that calls _bgRenderBeats).

  Bug 2 (CONCURRENT) — Fix-R click handler retries on !abs_path but NOT
  on !libItem. If MN_LIB_DATA is empty when click fires (race with
  _mnLibFetch on hard-refresh), libItem is null → alert + return, no
  recovery path.

3+3 Opus parallel debate (Rule 26 trigger #1 escalation) confirmed:
  - MutationObserver is the ONLY Path B mechanism reaching the disabled-
    mutation site, since doRestoreSlot is closure-private inside the IIFE
    at v52 L6417.
  - All T1-T6 alternatives infeasible (closure-private fetch hooks, broken
    semantic on .disabled property override, fight-the-platform CSS hacks,
    etc.).
  - Time-based wrap sweeps lose to the async fetch race at L6458.
  - Window-level capture listener fires BEFORE Fix-R's document-level
    capture listener, so it can pre-resolve MN_LIB_DATA state and
    redispatch a synthetic click after refresh.

Approach: Path B JS-only IIFE injection (per CLAUDE.md Rule 7), same
shape as Fix-P (LD-446) / Fix-Q (LD-447) / Fix-R (LD-448).

Input:  Production/Event_1/storyboard_v53_prod.html
Output: Production/Event_1/storyboard_v54_prod.html

Safety gates (HARD STOP on failure):
  - </html> exists exactly once in source
  - _fixS_installed not already present (idempotency)
  - Source is v53 (must contain _fixR_installed AND _fixQ_installed AND
    _fixPInited — sentinels for Fix-R, Fix-Q, Fix-P)
  - SHA256 of all base64 image blobs byte-identical before/after
  - Atomic write: .tmp file first, only renamed to final on all-checks-pass

Phase 0 Directus row: prod_preflight_reviews id=183
"""
import hashlib
import os
import re
import sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v53_prod.html"
DEST = _EVENT_DIR / "storyboard_v54_prod.html"
TMP  = _EVENT_DIR / "storyboard_v54_prod.html.tmp"

if not SRC.exists():
    print(f"ERROR: source {SRC} not found", file=sys.stderr)
    sys.exit(2)

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")

# Gate 1 — </html> appears at least once AND the LAST one is the real
# closing tag (within last 50 chars of file, ignoring trailing whitespace).
# Earlier patches' IIFE comments may contain the literal string "</html>"
# (e.g. Fix-R's "this IIFE injects before </html>"), which is fine — we
# always insert before the last </html>, which is the structural tag.
end_count = html.count("</html>")
if end_count < 1:
    print("ERROR: </html> not found in source", file=sys.stderr)
    sys.exit(2)
last_pos = html.rfind("</html>")
trailing = html[last_pos + len("</html>"):].strip()
if trailing:
    print(f"ERROR: content after last </html>: {trailing[:120]!r}", file=sys.stderr)
    sys.exit(2)
print(f"  </html> found {end_count}× — last at position {last_pos:,} (structural close), inserting before it")

# Gate 2 — idempotency
if "_fixS_installed" in html:
    print("ERROR: source already contains _fixS_installed — already patched", file=sys.stderr)
    sys.exit(2)

# Gate 2b — confirm we're patching v53 (must have all prior sentinels)
for sentinel, name in (("_fixPInited", "Fix-P"), ("_fixQ_installed", "Fix-Q"), ("_fixR_installed", "Fix-R")):
    if sentinel not in html:
        print(f"ERROR: source missing {sentinel} sentinel — this is not a v53 file (missing {name})", file=sys.stderr)
        sys.exit(2)


def b64_signature(text: str):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs:
        h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_signature(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")


FIX_S = r"""
<script>
// =====================================================================
// Fix-S: Keep cropBtn enabled on lib-dropped slots + MN_LIB_DATA pre-resolve
// (2026-05-02)
//
// Two bugs (Rule 28 Three-Bug Diagnosis after Fix-R failed to move
// symptom — Kim Mac, hard-refreshed v53, Crop button still non-functional):
//
//   1. Re-hydration wrapper at v52/v53 L6450 re-disables cropBtn after
//      Fix-R's _bgHandleLibSlotDrop wrap re-enables it. Disabled buttons
//      don't dispatch click events, so Fix-R's listener never fires.
//      → MutationObserver scoped to #panel-bg, watching [data-lib-key,
//        disabled, childList], re-enables any disabled cropBtn whose
//        slot has img[data-lib-key]. Guard `if (cropBtn.disabled)`
//        bounds the loop to 2 callback invocations per disable cycle.
//
//   2. Fix-R click handler retries on !abs_path but NOT on !libItem
//      (MN_LIB_DATA empty on hard-refresh race). Window-level capture
//      listener fires BEFORE Fix-R's document-level capture listener;
//      pre-resolves MN_LIB_DATA, blocks event if stale, refreshes,
//      redispatches synthetic click.
//
// LD: LIB_CROP_DISABLED_OBSERVER_V1 (preflight 183)
// =====================================================================
(function FixS() {
  "use strict";
  if (window._fixS_installed) return;
  window._fixS_installed = true;
  console.log("[Fix-S] Lib-crop disabled-observer + libItem-null retry active");

  // ── Part 1: MutationObserver to keep lib cropBtns enabled ───────────
  function _fixS_reenableLibCrops() {
    var imgs = document.querySelectorAll(".bg-opt img[data-lib-key]");
    for (var i = 0; i < imgs.length; i++) {
      var slot = imgs[i].closest(".bg-opt");
      if (!slot) continue;
      var cropBtn = slot.querySelector(".bg-opt-crop");
      if (cropBtn && cropBtn.disabled) {
        cropBtn.disabled = false;
        cropBtn.title = "Crop this library image";
      }
    }
  }

  var _fixS_mo = new MutationObserver(function () {
    _fixS_reenableLibCrops();
  });

  function _fixS_startObserver() {
    if (window._fixS_mo_started) return;
    window._fixS_mo_started = true;
    // Scope to #panel-bg if it exists, else fall back to body for safety
    var target = document.getElementById("panel-bg") || document.body;
    if (!target) return;  // DOM not ready yet
    _fixS_mo.observe(target, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["data-lib-key", "disabled"]
    });
    // Initial sweep for already-rendered slots
    _fixS_reenableLibCrops();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _fixS_startObserver);
  } else {
    _fixS_startObserver();
  }

  // ── Part 2: Window-level capture listener to pre-resolve MN_LIB_DATA ─
  // Fires BEFORE Fix-R's document-level capture listener (window capture
  // precedes document capture per DOM spec). If MN_LIB_DATA is empty or
  // doesn't have this libKey, block the event, refresh, then redispatch
  // a synthetic click that flows through to Fix-R cleanly.
  function _fixS_lookupLibItem(libKey) {
    var data = window.MN_LIB_DATA;
    if (!Array.isArray(data)) return null;
    for (var i = 0; i < data.length; i++) {
      if (data[i] && data[i].key === libKey) return data[i];
    }
    return null;
  }

  window.addEventListener("click", function (e) {
    // Marker to prevent infinite redispatch loop
    if (e._fixS_redispatched) return;

    var btn = e.target && e.target.closest
      ? e.target.closest(".bg-opt-crop")
      : null;
    if (!btn) return;
    var slot = btn.closest(".bg-opt");
    if (!slot) return;
    var img = slot.querySelector("img[data-lib-key]");
    if (!img) return;  // not lib-dropped — pass through to Fix-R / inline

    var libKey = img.getAttribute("data-lib-key");
    var item = _fixS_lookupLibItem(libKey);
    if (item && item.abs_path) {
      // MN_LIB_DATA is ready — pass through to Fix-R for normal handling
      return;
    }

    // MN_LIB_DATA missing or stale for this key — intercept, refresh, redispatch
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    var redispatch = function () {
      var found = _fixS_lookupLibItem(libKey);
      if (found && found.abs_path) {
        var ev = new MouseEvent("click", { bubbles: true, cancelable: true });
        ev._fixS_redispatched = true;
        btn.dispatchEvent(ev);
      } else {
        alert("Library data still not ready for " + libKey
          + ". Try clicking Crop again in a moment.");
      }
    };

    if (typeof _mnLibFetch === "function") {
      var p = _mnLibFetch();
      if (p && typeof p.then === "function") {
        p.then(redispatch).catch(redispatch);
      } else {
        setTimeout(redispatch, 500);
      }
    } else {
      alert("Library fetch unavailable. Reload the page.");
    }
  }, true);  // capture — fires before document-level capture in Fix-R
})();
// === END Fix-S ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found", file=sys.stderr)
    sys.exit(2)

patched = html[:pos] + FIX_S + html[pos:]
print(f"Injected Fix-S ({len(FIX_S):,} chars) before </html>")

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

# Atomic write
TMP.write_text(patched, encoding="utf-8")
print(f"Wrote tmp {TMP.name}: {len(patched):,} chars")

verify_text = TMP.read_text(encoding="utf-8")
hash_verify, count_verify = b64_signature(verify_text)
if hash_verify != hash_after or count_verify != count_after:
    print("VERIFY FAIL — tmp file disagrees with computed patch", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
for sentinel in ("_fixPInited", "_fixQ_installed", "_fixR_installed", "_fixS_installed"):
    if sentinel not in verify_text:
        print(f"VERIFY FAIL — tmp file missing {sentinel} sentinel", file=sys.stderr)
        TMP.unlink(missing_ok=True)
        sys.exit(4)
print(f"Tmp readback verified: {count_verify} blobs, sha256 {hash_verify[:16]}...")
print("  Sentinels present: Fix-P, Fix-Q, Fix-R, Fix-S (NEW)")

os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:      {SRC.name}  ({len(html):,} chars)")
print(f"  Output:      {DEST.name}  ({len(patched):,} chars)")
print(f"  Delta:       +{len(patched) - len(html):,} chars (Fix-S IIFE)")
print(f"  Base64 sha:  {hash_after[:16]}... ({count_after} blobs, unchanged)")
print(f"  Sentinels:   Fix-P (LD-446), Fix-Q (LD-447), Fix-R (LD-448), Fix-S (NEW)")

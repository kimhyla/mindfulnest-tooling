#!/usr/bin/env python3
"""
Path B patch: storyboard v55 -> v56 — Fix-U.

INVARIANTS:
  - Patches v55 only (must contain _fixPInited, _fixQ_installed,
    _fixR_installed, _fixS_installed, _fixT_installed)
  - </html> last-position is structural close (relaxed gate per v53+
    where Fix-R comment contains literal "</html>" string)
  - Idempotency via _fixU_installed sentinel
  - SHA256 of all base64 image blobs byte-identical pre/post
  - Atomic .tmp + readback + os.replace

Three concurrent fixes per Phase 0 preflight 185:

  Bug A scroll-reset target wrong (CRITICAL): _mnLibFetch resets scrollTop
    on .mn-lib-body but LIBFIX-V2 made that overflow:hidden. Real scrollable
    is #mn-lib-scroll-inner. Fix: DCL-deferred wrap that runs setTimeout(300)
    on _mnLibFetch to reset #mn-lib-scroll-inner.scrollTop = 0.

  Bug C FIX-H2 sticky redundant (MED, Rule 27): position:sticky on
    .mn-lib-upload-btn was for pinning; LIBFIX-V2 already pins via flex.
    FIX-H2's sticky now covers first thumbnail. Fix: CSS override
    .mn-lib-upload-btn { position: static !important; ... }
    (effect-removal per Rule 27 without violating Rule 7 Path B additive)

  Option 1 selector split (HIGH): V7's `body > label.mn-lib-upload-btn
    { height:32px }` only constrains body-direct-child. Fix-L's button
    inside #cr-lib-btn-wrap escapes constraint. Fix: broaden via bare
    `label.mn-lib-upload-btn { height:32px ... }` for dimensions only;
    V5/V6's narrow position:fixed rule untouched.

Phase 0 advocate+counter (Sonnet) findings addressed at root cause:
  HIGH-BLOCKING: Fix-U wrap deferred to DCL (registers after LIBFIX-V2)
  HIGH: Promise path documented as dead; setTimeout(300) is actual path
  MED: DCL load-order documented inline
  LOW: background:inherit !important added

Phase 0: prod_preflight_reviews id=185
"""
import hashlib
import os
import re
import sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v55_prod.html"
DEST = _EVENT_DIR / "storyboard_v56_prod.html"
TMP  = _EVENT_DIR / "storyboard_v56_prod.html.tmp"

if not SRC.exists():
    print(f"ERROR: source {SRC} not found", file=sys.stderr); sys.exit(2)

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")

# Gate 1 — </html> structural close at last position
end_count = html.count("</html>")
if end_count < 1:
    print("ERROR: </html> not found", file=sys.stderr); sys.exit(2)
last_pos = html.rfind("</html>")
trailing = html[last_pos + len("</html>"):].strip()
if trailing:
    print(f"ERROR: content after last </html>: {trailing[:120]!r}", file=sys.stderr); sys.exit(2)
print(f"  </html> {end_count}x — last at {last_pos:,}")

# Gate 2 — idempotency
if "_fixU_installed" in html:
    print("ERROR: _fixU_installed already present", file=sys.stderr); sys.exit(2)

# Gate 2b — sentinel matrix
for sentinel, name in (("_fixPInited","P"), ("_fixQ_installed","Q"),
                       ("_fixR_installed","R"), ("_fixS_installed","S"),
                       ("_fixT_installed","T")):
    if sentinel not in html:
        print(f"ERROR: source missing {sentinel} (Fix-{name}) — not v55", file=sys.stderr); sys.exit(2)
print("  Sentinel gate: P/Q/R/S/T all present")


def b64_sig(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs: h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_sig(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")

FIX_U = r"""
<script>
// =====================================================================
// Fix-U: Lib scroll-reset target + Option 1 selector split (2026-05-02)
//
// INVARIANTS:
//   - Must run AFTER LIBFIX-V2 installs its _mnLibFetch wrap (DCL-deferred)
//   - Original _mnLibFetch returns undefined through entire wrap chain
//     (FIX-H, FIX-H2, LIBFIX-V2 all preserve undefined). setTimeout(300)
//     is the ACTUAL scroll-reset path; .then() is dead.
//   - Fix-U's <script> position before final close tag ensures DCL
//     registration is LAST in source order, so wrap captures outermost.
//
// LD: LIB_SCROLL_AND_SELECTORS_FIX_V1 (preflight 185)
// =====================================================================
(function FixU() {
  "use strict";
  if (window._fixU_installed) return;
  window._fixU_installed = true;
  console.log("[Fix-U] Lib scroll-reset + Option-1 broaden + FIX-H2 neutralize active");

  // ── Part 1: CSS injection (synchronous, immediate) ───────────────────
  var css = ""
    // Bug C: neutralize FIX-H2 sticky positioning (Rule 27 effect-removal)
    + ".mn-lib-upload-btn {"
    + "  position: static !important;"
    + "  top: auto !important;"
    + "  z-index: auto !important;"
    + "  background: inherit !important;"  // belt-and-suspenders for FIX-H2 leftover
    + "}"
    // Option 1 broaden: V7 height constraint applies to ALL labels
    // (specificity 0,0,2 < Fix-T's 0,1,2 — Fix-T still wins where targeted)
    + "label.mn-lib-upload-btn {"
    + "  height: 32px !important;"
    + "  min-height: 32px !important;"
    + "  max-height: 32px !important;"
    + "  line-height: 24px !important;"
    + "  overflow: hidden !important;"
    + "  white-space: nowrap !important;"
    + "  padding: 4px 8px !important;"
    + "}"
    // Option 1 broaden: hidden file input
    + "label.mn-lib-upload-btn input[type='file'] {"
    + "  position: absolute !important;"
    + "  width: 0 !important;"
    + "  height: 0 !important;"
    + "  opacity: 0 !important;"
    + "  pointer-events: none !important;"
    + "}";
  var styleEl = document.createElement("style");
  styleEl.id = "fix-u-style";
  styleEl.textContent = css;
  (document.head || document.body || document.documentElement).appendChild(styleEl);

  // ── Part 2: scroll-reset wrap (DCL-deferred) ─────────────────────────
  function _fixU_scrollReset() {
    var el = document.getElementById("mn-lib-scroll-inner");
    if (el) el.scrollTop = 0;
  }

  function _fixU_installWrap() {
    if (window._fixU_wrapInstalled) return;
    window._fixU_wrapInstalled = true;
    var origFetch = window._mnLibFetch;
    if (typeof origFetch !== "function") {
      console.warn("[Fix-U] _mnLibFetch not a function at install time");
      return;
    }
    window._mnLibFetch = function () {
      var result = origFetch.apply(this, arguments);
      // Promise path — currently dead because origFetch returns undefined
      // through wrap chain. Preserved for future-proofing if base fn
      // ever starts returning Promise.
      if (result && typeof result.then === "function") {
        result.then(_fixU_scrollReset, _fixU_scrollReset);
      }
      // setTimeout fallback — ACTUAL path. 300ms exceeds FIX-H2's 100ms
      // _fixh2Pin and LIBFIX-V2's 150ms _libfixV2Enforce.
      setTimeout(_fixU_scrollReset, 300);
      return result;
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _fixU_installWrap);
  } else {
    // DCL already fired — defer one tick so other DCL handlers' wraps land
    setTimeout(_fixU_installWrap, 0);
  }
})();
// === END Fix-U ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
patched = html[:pos] + FIX_U + html[pos:]
print(f"Injected Fix-U ({len(FIX_U):,} chars) before structural </html>")

# Gate 3 — base64 byte-identical
hash_after, count_after = b64_sig(patched)
if hash_before != hash_after or count_before != count_after:
    print(f"INTEGRITY FAIL — sha {hash_before[:16]} -> {hash_after[:16]}", file=sys.stderr); sys.exit(3)
print(f"Base64 verified: {count_after} blobs, sha256 {hash_after[:16]}... unchanged")

TMP.write_text(patched, encoding="utf-8")
verify = TMP.read_text(encoding="utf-8")
hv, cv = b64_sig(verify)
if hv != hash_after or cv != count_after:
    print("VERIFY FAIL", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
for s in ("_fixPInited", "_fixQ_installed", "_fixR_installed",
          "_fixS_installed", "_fixT_installed", "_fixU_installed"):
    if s not in verify:
        print(f"VERIFY FAIL — missing {s}", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
print("Tmp readback verified, all 6 sentinels (P,Q,R,S,T,U) present")

os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:  {SRC.name} ({len(html):,} chars)")
print(f"  Output:  {DEST.name} ({len(patched):,} chars)")
print(f"  Delta:   +{len(patched) - len(html):,} chars")
print(f"  sha256:  {hash_after[:16]}... ({count_after} blobs unchanged)")

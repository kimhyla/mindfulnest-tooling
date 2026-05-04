#!/usr/bin/env python3
"""
Path B patch: storyboard v54 → v55 — fix 2 lib-panel CSS regressions.

Fix-T (LD-450 to register, preflight 184):

Bug 1 — Fix-L's "⬆ Add Image" label rendering 242×747 giant rectangle.
  V7's height:32px constraint uses selector `body > label.mn-lib-upload-btn`
  which requires direct body child. V5's safety-net moves only the FIRST
  matching label to body. Fix-L (later patch, 2026-04-27) creates a SECOND
  label.mn-lib-upload-btn inside #cr-lib-btn-wrap inside #cr-sidebar — it
  stays inside the cropper sidebar, doesn't get V7's height constraint,
  inherits base `width:100%` with no height limit, and grows to fill its
  flex parent.
  Confirmed live via user console:
    label count = 2
    [0] "⬆ Add Image" @ #cr-lib-btn-wrap = 242×747px (BAD)
    [1] "⬆ Upload Image" @ body = 242×32px (V7 working)

Bug 2 — Library new uploads hidden under storyboard nav.
  #mn-lib-sidebar { position:fixed; top:0; height:100vh } extends behind
  the ~150px-tall storyboard nav at viewport top. New uploads land at the
  top of the scrollable list inside the library; that scroll-top position
  is BEHIND the nav, so user can't see new images even when scrolled to top.
  Confirmed by Kim's screenshot: topmost thumbnail clipped at top edge.

Fix: pure CSS injected via <style> tag in IIFE. No JS behavior changes.

Approach: Path B JS-only injection (per CLAUDE.md Rule 7), same shape as
Fix-P/Q/R/S. Idempotent via window._fixT_installed.

Input:  Production/Event_1/storyboard_v54_prod.html
Output: Production/Event_1/storyboard_v55_prod.html

Safety gates (HARD STOP on failure):
  - </html> last-position is structural close (gate relaxed for v54+ comments)
  - _fixT_installed not already present (idempotency)
  - All prior sentinels present (Fix-P, Q, R, S)
  - SHA256 of all base64 image blobs byte-identical before/after
  - Atomic .tmp + readback + rename

Phase 0: prod_preflight_reviews id=184
"""
import hashlib
import os
import re
import sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v54_prod.html"
DEST = _EVENT_DIR / "storyboard_v55_prod.html"
TMP  = _EVENT_DIR / "storyboard_v55_prod.html.tmp"

if not SRC.exists():
    print(f"ERROR: source {SRC} not found", file=sys.stderr); sys.exit(2)

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")

# Gate 1 — </html> last-position is structural close
end_count = html.count("</html>")
if end_count < 1:
    print("ERROR: </html> not found in source", file=sys.stderr); sys.exit(2)
last_pos = html.rfind("</html>")
trailing = html[last_pos + len("</html>"):].strip()
if trailing:
    print(f"ERROR: content after last </html>: {trailing[:120]!r}", file=sys.stderr); sys.exit(2)
print(f"  </html> found {end_count}x — last at {last_pos:,}")

# Gate 2 — idempotency
if "_fixT_installed" in html:
    print("ERROR: _fixT_installed already present", file=sys.stderr); sys.exit(2)

# Gate 2b — confirm v54 (must have all prior sentinels)
for sentinel, name in (("_fixPInited","P"), ("_fixQ_installed","Q"), ("_fixR_installed","R"), ("_fixS_installed","S")):
    if sentinel not in html:
        print(f"ERROR: source missing {sentinel} (Fix-{name}) — not v54", file=sys.stderr); sys.exit(2)


def b64_sig(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs: h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_sig(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")

FIX_T = r"""
<script>
// =====================================================================
// Fix-T: Two lib-panel CSS regressions (2026-05-02)
//
// Bug 1: Fix-L's "Add Image" label rendering 242x747 because V7's
//   `body > label.mn-lib-upload-btn { height:32px }` selector requires
//   direct body child. Fix-L's label is inside #cr-lib-btn-wrap.
//   Fix: targeted #cr-lib-btn-wrap > label.mn-lib-upload-btn rule.
//
// Bug 2: #mn-lib-sidebar extends behind storyboard nav (top:0; 100vh),
//   hiding new uploads at scroll-top. Fix: top:150px + adjust height.
//
// Idempotent via _fixT_installed.
// LD: LIB_CSS_REGRESSIONS_FIX_V1 (preflight 184)
// =====================================================================
(function FixT() {
  "use strict";
  if (window._fixT_installed) return;
  window._fixT_installed = true;
  console.log("[Fix-T] Lib-panel CSS regressions fixed (Add Image button + sidebar top offset)");

  var css = ""
    // ── Bug 1: Constrain Fix-L's Add Image button ────────────────────
    + "#cr-lib-btn-wrap > label.mn-lib-upload-btn {"
    + "  height: 32px !important;"
    + "  min-height: 32px !important;"
    + "  max-height: 32px !important;"
    + "  line-height: 24px !important;"
    + "  overflow: hidden !important;"
    + "  white-space: nowrap !important;"
    + "  flex: 0 1 auto !important;"
    + "  align-self: flex-start !important;"
    + "  padding: 4px 8px !important;"
    + "}"
    // Hide the file input inside Fix-L's label (V7's rule misses it too)
    + "#cr-lib-btn-wrap > label.mn-lib-upload-btn input[type='file'] {"
    + "  position: absolute !important;"
    + "  width: 0 !important;"
    + "  height: 0 !important;"
    + "  opacity: 0 !important;"
    + "  overflow: hidden !important;"
    + "  pointer-events: none !important;"
    + "}"
    // ── Bug 2: Don't extend library behind storyboard nav ────────────
    + "#mn-lib-sidebar {"
    + "  top: 150px !important;"
    + "  height: calc(100vh - 150px) !important;"
    + "}";

  var styleEl = document.createElement("style");
  styleEl.id = "fix-t-style";
  styleEl.textContent = css;
  // Append to <head> if available, else <body>, else document
  var target = document.head || document.body || document.documentElement;
  if (target) target.appendChild(styleEl);
})();
// === END Fix-T ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
patched = html[:pos] + FIX_T + html[pos:]
print(f"Injected Fix-T ({len(FIX_T):,} chars) before </html>")

hash_after, count_after = b64_sig(patched)
if hash_before != hash_after or count_before != count_after:
    print(f"INTEGRITY FAIL — sha {hash_before[:16]} -> {hash_after[:16]}", file=sys.stderr); sys.exit(3)
print(f"Base64 integrity verified: {count_after} blobs, sha256 {hash_after[:16]}... unchanged")

TMP.write_text(patched, encoding="utf-8")
verify = TMP.read_text(encoding="utf-8")
hv, cv = b64_sig(verify)
if hv != hash_after or cv != count_after:
    print("VERIFY FAIL", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
for s in ("_fixPInited", "_fixQ_installed", "_fixR_installed", "_fixS_installed", "_fixT_installed"):
    if s not in verify:
        print(f"VERIFY FAIL — missing {s}", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
print(f"Tmp readback verified, all 5 sentinels present (P,Q,R,S,T)")

os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:  {SRC.name} ({len(html):,} chars)")
print(f"  Output:  {DEST.name} ({len(patched):,} chars)")
print(f"  Delta:   +{len(patched) - len(html):,} chars (Fix-T <style> injection)")
print(f"  sha256:  {hash_after[:16]}... ({count_after} blobs unchanged)")

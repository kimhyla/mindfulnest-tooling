#!/usr/bin/env python3
"""
Path B patch — Fix-D BG panel persistence (2026-04-25)
Appends a <script> block to storyboard_v43_prod.html that:
  1. Calls _bgLoadState() at DOMContentLoaded so BG state pre-loads
     in the background (same as Storyboard tab having L[] embedded).
  2. Wraps _mnLibRender so that whenever library data arrives,
     beats are re-rendered — fixing the race where ref images (Char Ref,
     BG Ref) showed blank because MN_LIB_DATA was empty at render time.

Root causes:
  - _bgLoadState() was only called on tab-click (line 3979), not page load.
  - _makeRefSlot() looks up images in MN_LIB_DATA (line 4178). If
    _bgRenderBeats runs before _mnLibFetch completes, ref images are blank.

Rule 7 compliance:
  - Only appends a new <script> block — no existing content changed
  - Authored base64 image data is byte-identical before/after
"""

import hashlib
import re
import sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixd_backup.html"

def sha256_b64(html: str) -> tuple[int, str]:
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    digest = hashlib.sha256(("".join(b64s)).encode()).hexdigest()
    return len(b64s), digest

PATCH_SCRIPT = """\

<script>
// =====================================================================
// FIX-D BG PANEL PERSISTENCE (2026-04-25)
// Problem 1: _bgLoadState() only fires on BG tab click (line 3979).
//   Storyboard tab has L[] embedded in HTML — always ready. BG tab
//   needs equivalent: pre-load state at DOMContentLoaded.
// Problem 2: Char Ref / BG Ref images rely on MN_LIB_DATA (populated
//   by _mnLibFetch, async). If beats render before lib data arrives,
//   ref image slots are blank. Fix: re-render beats after lib loads.
// =====================================================================
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Fix 1: Pre-load BG state at DOMContentLoaded (background hydration)
  // ------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    // Small delay so other DOMContentLoaded handlers (lib fetch, arc
    // selector, etc.) register first, avoiding dependency races.
    setTimeout(function () {
      if (typeof _bgLoadState === "function") {
        _bgLoadState();
      }
    }, 300);
  });

  // ------------------------------------------------------------------
  // Fix 2: After lib data arrives, re-render beats to pick up ref images.
  // _mnLibRender is called at end of every _mnLibFetch — wrapping it
  // ensures beats re-render whenever MN_LIB_DATA is freshly populated.
  // Guard: only re-render if BG_BEATS is already loaded (non-empty).
  // Guard: debounce 200ms so rapid lib refreshes don't spam re-renders.
  // ------------------------------------------------------------------
  var _fixd_rerender_timer = null;
  if (typeof _mnLibRender === "function") {
    var _mnLibRender_orig = _mnLibRender;
    window._mnLibRender = _mnLibRender = function () {
      _mnLibRender_orig.apply(this, arguments);
      // Re-render beats to pick up ref images now that MN_LIB_DATA is set
      clearTimeout(_fixd_rerender_timer);
      _fixd_rerender_timer = setTimeout(function () {
        if (typeof BG_BEATS !== "undefined" && BG_BEATS && BG_BEATS.length) {
          _bgRenderBeats(BG_BEATS);
        }
      }, 200);
    };
  }

})();
// === END FIX-D BG PANEL PERSISTENCE ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")

    b64_count_before, b64_hash_before = sha256_b64(html)
    print(f"  Base64 blocks before: {b64_count_before}, sha256: {b64_hash_before}")

    if "FIX-D BG PANEL PERSISTENCE" in html:
        print("ERROR: patch marker already present — refusing to double-patch.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup written: {BACKUP_PATH.name}")

    # Fix-C consumed </body>; anchor on </html>
    anchor = "</body>" if "</body>" in html else "</html>"
    if anchor not in html:
        print("ERROR: neither </body> nor </html> found.")
        sys.exit(1)

    patched = html.replace(anchor, PATCH_SCRIPT + anchor, 1)

    b64_count_after, b64_hash_after = sha256_b64(patched)
    print(f"  Base64 blocks after:  {b64_count_after}, sha256: {b64_hash_after}")

    if b64_hash_before != b64_hash_after or b64_count_before != b64_count_after:
        print("ABORT: base64 content changed — patch corrupted authored images.")
        sys.exit(1)
    print("  ✓ Base64 byte-identical — no authored images touched")

    HTML_PATH.write_text(patched, encoding="utf-8")
    size_kb = HTML_PATH.stat().st_size // 1024
    print(f"  ✓ Written: {HTML_PATH.name} ({size_kb} KB)")
    print("Done.")

if __name__ == "__main__":
    main()

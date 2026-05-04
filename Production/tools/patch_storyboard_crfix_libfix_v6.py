#!/usr/bin/env python3
"""
Targeted fix — CRFIX-LIBFIX-V6 (2026-04-25)

ROOT CAUSES:

1. _injectAcceptedPreview NOT IN GLOBAL SCOPE:
   V4 defined it inside an IIFE:
     (function() { "use strict";  ... function _injectAcceptedPreview(beatId, b64src) {...} })()
   Function declarations inside an IIFE are LOCAL to that function — not on window.
   V5's _crSaveCrop rewrite calls _injectAcceptedPreview(...) directly, which throws
   ReferenceError at runtime. V5's _bgRenderBeats wrapper checks
   typeof _injectAcceptedPreview === "function" which returns false — no injection.
   FIX: Define window._injectAcceptedPreview = function(...) at global scope in V6.

2. Upload button covers library panel:
   position:fixed; right:10px sits INSIDE the 260px-wide library panel area.
   z-index:10002 puts our button ON TOP of library contents.
   FIX: right:270px puts the button just to the LEFT of the library panel.
   Also: the storyboard's own built-in "Upload Image" button at the top-right
   header is a DIFFERENT button (it's the storyboard builder's own upload feature,
   always present) — Kim should ignore that one for library use.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv6_backup.html"

SENTINEL = "CRFIX-LIBFIX-V6"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<style>
/* =========================================================
   CRFIX-LIBFIX-V6 (2026-04-25)
   Upload button: right:270px so it clears the 260px library panel
   ========================================================= */

/* Override V5's right:10px — at right:10px the button sits INSIDE
   the library panel (260px wide from the right).
   right:270px puts it 10px to the LEFT of the library panel edge. */
body > label.mn-lib-upload-btn {
  right: 270px !important;
  bottom: 80px !important;
}
body.mn-lib-open > label.mn-lib-upload-btn {
  display: block !important;
}
</style>
<script>
// =====================================================================
// CRFIX-LIBFIX-V6: Global _injectAcceptedPreview + button placement (2026-04-25)
//
// V4 defined _injectAcceptedPreview() inside an IIFE — LOCAL scope only.
// V5's _crSaveCrop and _bgRenderBeats wrapper can't call it (ReferenceError).
// This patch exposes it globally so both can find it.
// =====================================================================

// Define globally BEFORE DOMContentLoaded so _crSaveCrop can call it
// synchronously (the call site is inside a .then() callback but the function
// reference is looked up at call time, not at parse time, so global is fine).
window._injectAcceptedPreview = function (beatId, b64src) {
  var card = document.getElementById("bg-card-" + beatId);
  if (!card) {
    console.warn("[V6] bg-card-" + beatId + " not found for thumbnail inject");
    return;
  }
  var hdr = card.querySelector(".bg-beat-hdr");
  if (!hdr) return;

  // Remove any previous preview
  var old = hdr.querySelector(".bg-accepted-preview");
  if (old) old.parentNode.removeChild(old);

  if (b64src) {
    var thumb = document.createElement("img");
    thumb.className = "bg-accepted-preview";
    thumb.src = b64src;
    thumb.title = "Accepted crop";
    hdr.appendChild(thumb);
  }

  // Update status chip
  var sp = document.getElementById("bg-status-" + beatId);
  if (sp) sp.textContent = "cropped \u2713";

  // Enable Accept All button
  var globalBtn = document.getElementById("bg-accept-btn");
  if (globalBtn) globalBtn.disabled = false;

  console.log("[V6] _injectAcceptedPreview: beat", beatId, "thumbnail injected");
};
// === END CRFIX-LIBFIX-V6 ===
</script>
"""


def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if SENTINEL in html:
        print(f"ERROR: already patched ('{SENTINEL}' found).")
        sys.exit(1)

    if "CRFIX-LIBFIX-V5" not in html:
        print("ERROR: CRFIX-LIBFIX-V5 not found — apply V5 patch first.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel {patched.count(SENTINEL)} ≠ {expected}")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    # Atomic write (temp → rename prevents truncation on failure)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".html", dir=HTML_PATH.parent)
    try:
        with open(tmp_fd, 'w', encoding="utf-8") as f:
            f.write(patched)
        shutil.move(tmp_path, str(HTML_PATH))
    except Exception as e:
        import os; os.unlink(tmp_path)
        print(f"ABORT: write failed — {e}"); sys.exit(1)

    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")
    print()
    print("Fixes applied:")
    print("  1. window._injectAcceptedPreview defined globally")
    print("     → V5's _crSaveCrop and _bgRenderBeats wrapper can now call it")
    print("     → Crop thumbnail will appear in beat card header after save")
    print("  2. Upload button: right:270px (was right:10px, was inside library panel)")
    print("     → Button now sits just LEFT of the 260px library panel")
    print()
    print("Remind Kim: hard-refresh (Cmd+Shift+R) to get V5+V6 code running.")
    print("The 'Upload Image' button at the TOP of the storyboard header is the")
    print("storyboard's OWN built-in upload feature — it's separate from the library button.")


if __name__ == "__main__":
    main()

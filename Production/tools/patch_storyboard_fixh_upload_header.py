#!/usr/bin/env python3
"""
Path B patch — Fix-H: Upload button as persistent sidebar header (2026-04-25)
Fix-F moved the button to the TOP of .mn-lib-body (scrollable), so it scrolls
away when the library has many images. True fix: move the button OUT of the
scrollable body entirely, as a fixed header div between the toggle and the body.
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixh_backup.html"

def sha256_b64(html):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()

PATCH = """\

<style>
/* FIX-H: sticky upload button — always visible at top of library scroll area (2026-04-25)
   #mn-lib-sidebar is flex-direction:row, so .mn-lib-body is the scrollable column.
   position:sticky;top:0 keeps the button pinned to the top of the scroll viewport
   even when the user scrolls through many images. */
.mn-lib-upload-btn {
  position: sticky !important;
  top: 0 !important;
  z-index: 5 !important;
  background: #141e14 !important;
  margin-bottom: 6px !important;
  padding-bottom: 6px !important;
  border-bottom: 1px solid #2a4a2a !important;
}
/* Remove prior padding hacks */
.mn-lib-body { padding-bottom: 8px !important; }
</style>
<script>
// FIX-H: Ensure .mn-lib-upload-btn stays at TOP of .mn-lib-body DOM order (2026-04-25)
// The sidebar is flex-direction:row so the button must stay INSIDE .mn-lib-body.
// position:sticky;top:0 (CSS above) pins it visually. This JS ensures DOM order
// is correct (first child) so sticky works from the top.
(function () {
  "use strict";

  function _fixhPinUploadBtn() {
    var body = document.querySelector(".mn-lib-body");
    var btn  = document.querySelector(".mn-lib-upload-btn");
    if (!body || !btn) return;
    // Move to first child if not already
    if (body.firstElementChild !== btn) {
      body.insertBefore(btn, body.firstChild);
    }
  }

  document.addEventListener("DOMContentLoaded", _fixhPinUploadBtn);

})();
// === END FIX-H UPLOAD HEADER ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if "FIX-H: Move upload button OUTSIDE" in html:
        print("ERROR: already patched.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")

if __name__ == "__main__":
    main()

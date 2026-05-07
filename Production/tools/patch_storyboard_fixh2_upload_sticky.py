#!/usr/bin/env python3
"""
Path B patch — Fix-H2: Correct upload button with sticky CSS (2026-04-25)
Fix-H moved the button into a row-flex sibling (wrong — becomes a narrow column).
Fix-H2: move button back INTO .mn-lib-body as firstElementChild, then use
position:sticky;top:0 so it is always visible at the top regardless of scroll.
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixh2_backup.html"

def sha256_b64(html):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()

PATCH = """\

<style>
/* FIX-H2: sticky upload btn always visible at top of library scroll area (2026-04-25) */
.mn-lib-upload-btn {
  position: sticky !important;
  top: 0 !important;
  z-index: 5 !important;
  background: #141e14 !important;
  margin-bottom: 6px !important;
  border-bottom: 1px solid #2a4a2a !important;
  display: block !important;
}
.mn-lib-body { padding-bottom: 8px !important; }
</style>
<script>
// FIX-H2: Fix-H put the button in a row-flex sidebar column (wrong). (2026-04-25)
// This corrects it: move btn back into .mn-lib-body as the first element child.
// position:sticky;top:0 (CSS above) pins it to the top of the scroll viewport.
(function () {
  "use strict";

  function _fixh2Pin() {
    var body = document.querySelector(".mn-lib-body");
    if (!body) return;
    // If Fix-H moved btn outside .mn-lib-body (into #mn-lib-upload-header), move it back
    var misplacedHeader = document.getElementById("mn-lib-upload-header");
    if (misplacedHeader) {
      var btn = misplacedHeader.querySelector(".mn-lib-upload-btn");
      if (btn) {
        body.insertBefore(btn, body.firstChild);
      }
      if (misplacedHeader.parentNode) misplacedHeader.parentNode.removeChild(misplacedHeader);
    } else {
      // No misplaced header — ensure btn is first child of body
      var btn2 = document.querySelector(".mn-lib-upload-btn");
      if (btn2 && body.firstElementChild !== btn2) {
        body.insertBefore(btn2, body.firstChild);
      }
    }
  }

  // Run at DOMContentLoaded AND after any dynamic render
  document.addEventListener("DOMContentLoaded", _fixh2Pin);

  // Also hook _mnLibFetch so the pin survives library refresh
  document.addEventListener("DOMContentLoaded", function () {
    var _origFetch = window._mnLibFetch;
    if (typeof _origFetch === "function") {
      window._mnLibFetch = _mnLibFetch = function () {
        var result = _origFetch.apply(this, arguments);
        setTimeout(_fixh2Pin, 100);
        return result;
      };
    }
  });

})();
// === END FIX-H2 UPLOAD STICKY ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if "FIX-H2: sticky upload btn" in html:
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

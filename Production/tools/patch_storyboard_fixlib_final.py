#!/usr/bin/env python3
"""
Path B patch — FIXLIB-FINAL: Definitive library upload button fix (2026-04-25)
Prior patches Fix-E through Fix-H2 conflicted with each other (CSS !important fights,
DOMContentLoaded race conditions, wrong flex-axis placement).

Root solution: restructure .mn-lib-body into a flex-column container where the
upload button is a pinned top child and the 3 sections live in a separate
#mn-lib-scroll-inner div that scrolls. Upload button never enters the scroll area.

Also cleans up Fix-H's misplaced #mn-lib-upload-header (wrong row-flex column).
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixlib_final_backup.html"

def sha256_b64(html):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()

PATCH = """\

<style>
/* FIXLIB-FINAL: flex-column .mn-lib-body so upload btn is always above scroll area */
.mn-lib-body {
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
  padding: 0 !important;
}
.mn-lib-upload-btn {
  flex-shrink: 0 !important;
  position: static !important;
  margin: 5px 6px 4px 6px !important;
  width: calc(100% - 12px) !important;
  box-sizing: border-box !important;
  border-bottom: 1px solid #2a4a2a !important;
  padding-bottom: 6px !important;
  z-index: auto !important;
}
#mn-lib-scroll-inner {
  flex: 1;
  overflow-y: auto;
  padding: 4px 6px 12px 6px;
  min-height: 0;
}
</style>
<script>
// FIXLIB-FINAL: Restructure .mn-lib-body into flex-column with pinned upload btn (2026-04-25)
// Cleans up all prior Fix-E/F/G/H/H2 attempts and does it correctly once.
(function () {
  "use strict";

  function _fixlibSetup() {
    if (document.getElementById("mn-lib-scroll-inner")) return; // already done

    var body = document.querySelector(".mn-lib-body");
    if (!body) return;

    // Recover upload btn from Fix-H's misplaced #mn-lib-upload-header if present
    var badHeader = document.getElementById("mn-lib-upload-header");
    if (badHeader && badHeader.parentNode) {
      badHeader.parentNode.removeChild(badHeader);
    }

    var btn = document.querySelector(".mn-lib-upload-btn");

    // Wrap the 3 .mn-lib-section divs in a scrollable inner container
    var inner = document.createElement("div");
    inner.id = "mn-lib-scroll-inner";

    var sections = Array.prototype.slice.call(body.querySelectorAll(".mn-lib-section"));
    sections.forEach(function (s) { inner.appendChild(s); });

    // Rebuild body: upload btn (pinned) then scrollable inner
    // Clear everything (sections moved, btn may still be in body)
    while (body.firstChild) body.removeChild(body.firstChild);

    if (btn) body.appendChild(btn);
    body.appendChild(inner);
  }

  // Run at DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _fixlibSetup);
  } else {
    _fixlibSetup();
  }

  // Re-run after _mnLibFetch renders content (defensive — _mnLibRender only updates
  // grid children, not .mn-lib-section elements, so this should be a no-op normally)
  var _checkInterval = setInterval(function () {
    if (document.getElementById("mn-lib-scroll-inner")) {
      clearInterval(_checkInterval);
      return;
    }
    _fixlibSetup();
  }, 500);
  // Stop checking after 10s
  setTimeout(function () { clearInterval(_checkInterval); }, 10000);

})();
// === END FIXLIB-FINAL ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if "FIXLIB-FINAL" in html:
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

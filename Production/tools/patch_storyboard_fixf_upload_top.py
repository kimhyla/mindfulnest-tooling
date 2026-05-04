#!/usr/bin/env python3
"""
Path B patch — Fix-F: Move library upload button to top of .mn-lib-body (2026-04-25)
The upload button was the LAST element in .mn-lib-body and got buried behind
the fixed debug/Restart Server overlay. This JS patch moves it to the TOP
so it is always visible without scrolling.
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixf_backup.html"

def sha256_b64(html):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()

PATCH = """\

<style>
/* FIX-F: upload button at top, remove bottom padding hack (2026-04-25) */
.mn-lib-body { padding-bottom: 8px !important; }
.mn-lib-upload-btn { margin-bottom: 8px; }
</style>
<script>
// FIX-F: Move .mn-lib-upload-btn to TOP of .mn-lib-body (2026-04-25)
// The button was last — buried behind the fixed debug/Restart Server overlay.
// Moving to top makes it always accessible without scrolling.
document.addEventListener("DOMContentLoaded", function () {
  var body = document.querySelector(".mn-lib-body");
  var btn  = document.querySelector(".mn-lib-upload-btn");
  if (body && btn && body.firstChild !== btn) {
    body.insertBefore(btn, body.firstChild);
  }
});
// === END FIX-F UPLOAD TOP ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if "FIX-F: Move .mn-lib-upload-btn" in html:
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

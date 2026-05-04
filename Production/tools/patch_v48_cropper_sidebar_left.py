#!/usr/bin/env python3
"""
Path B patch: Move #cr-sidebar to the LEFT of the canvas.

Problem: #mn-lib-sidebar is position:fixed; right:0; width:260px.
         When it opens it covers the #cr-sidebar (which is at the right
         of the flex layout), making the Save/Back buttons unreachable.

Fix:  CSS `order` swap — cr-sidebar gets order:1, canvas-wrap gets order:2.
      Sidebar is now left-side, library panel opens on right over canvas
      (acceptable — canvas is still partially usable and library auto-closes
      when Kim clicks an image).

Input:  storyboard_v47_prod.html
Output: storyboard_v48_prod.html

Safety: SHA256 of all base64 blobs verified identical before/after.
"""
import hashlib, re, sys
from pathlib import Path

SRC  = Path(__file__).parent.parent / "Event_1" / "storyboard_v47_prod.html"
DEST = Path(__file__).parent.parent / "Event_1" / "storyboard_v48_prod.html"

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

FIX_M = r"""
<script>
// ══════════════════════════════════════════════════════════════════════════
// Fix-M: Move #cr-sidebar to LEFT of canvas (2026-04-27)
// Prevents #mn-lib-sidebar (fixed right 260px) from covering the sidebar
// when the library panel opens from the Cropper tab.
// Order: sidebar(1, left) | canvas-wrap(2, right)
// ══════════════════════════════════════════════════════════════════════════
(function () {
  var style = document.createElement("style");
  style.textContent = [
    "#cr-canvas-wrap { order: 2; }",
    "#cr-sidebar      { order: 1; }"
  ].join(" ");
  document.head.appendChild(style);
})();
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found"); sys.exit(1)

patched = html[:pos] + FIX_M + html[pos:]
print(f"Injected Fix-M ({len(FIX_M):,} chars) before </html>")

hash_after, count_after = b64_hash(patched)
if hash_before != hash_after or count_before != count_after:
    print(f"INTEGRITY FAIL"); sys.exit(1)
print(f"Base64 integrity verified: {count_after} blobs ✓")

DEST.write_text(patched, encoding="utf-8")
print(f"Wrote {DEST.name}")

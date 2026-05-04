#!/usr/bin/env python3
"""
Path B patch — Fix-C3b full-res crop (2026-04-25)
Appends a <script> block to storyboard_v43_prod.html that overrides
_crLoadImage to always XHR the full-res PNG from /bg-stills/ instead
of using thumb_b64 from TH (which is only 256x190).

Root cause: _injectImage() stores thumb_b64 in TH[key]. Fix-C's C3
patch checked `if (TH[key])` and short-circuited to the original
_crLoadImage_orig — loading the thumbnail into the crop canvas.

Fix: replace _crLoadImage entirely; always fetch /bg-stills/<key>.png
(full-res); fall back to TH on 404; upgrade TH to full-res on success.

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
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixc3b_backup.html"

def sha256_b64(html: str) -> tuple[int, str]:
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    digest = hashlib.sha256(("".join(b64s)).encode()).hexdigest()
    return len(b64s), digest

PATCH_SCRIPT = """\

<script>
// =====================================================================
// FIX-C3b FULL-RES CROP (2026-04-25)
// Root cause: _injectImage() puts thumb_b64 (256x190) in TH[key].
// Fix-C's C3 patch had `if (TH[key]) return early` — so it used the
// thumbnail instead of XHRing the full-res PNG from /bg-stills/.
// Fix: always XHR /bg-stills/<key>.png (full resolution) for crop.
//      Fall back to TH on 404. Upgrade TH to full-res on success.
// =====================================================================
(function () {
  "use strict";

  function _crOpenFullRes(key, src) {
    var img = new Image();
    img.onload = function () {
      CR_IMG = img;
      var cropW = Math.min(img.width, img.height * 4 / 3);
      var cropH = cropW * 3 / 4;
      CR_CROP_BOX = {
        x: (img.width - cropW) / 2,
        y: (img.height - cropH) / 2,
        w: cropW,
        h: cropH
      };
      _bgSwitchTab("cr", null);
      _crDraw();
      var info = document.getElementById("cr-crop-info");
      if (info) info.textContent = "Image: " + img.width + "\\u00d7" + img.height + "px\\nCrop: 4:3";
      var saveBtn = document.getElementById("cr-save-btn");
      if (saveBtn) saveBtn.disabled = false;
    };
    img.onerror = function () { alert("Failed to load image."); };
    img.src = src;
  }

  // Full replacement of _crLoadImage — always uses /bg-stills/ full-res
  window._crLoadImage = function (key, beatId) {
    CR_BEAT_ID = beatId;
    CR_SRC_KEY = key;

    var url = BG_SERVER + "/bg-stills/" + encodeURIComponent(key + ".png")
            + "?v=" + Date.now();
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.responseType = "blob";
    xhr.onload = function () {
      if (xhr.status === 200) {
        var reader = new FileReader();
        reader.onload = function () {
          TH[key] = reader.result;         // upgrade TH from thumb to full-res
          _crOpenFullRes(key, TH[key]);
        };
        reader.readAsDataURL(xhr.response);
      } else if (TH[key]) {
        // /bg-stills/ returned 404/error — fall back to whatever TH has
        _crOpenFullRes(key, TH[key]);
      } else {
        alert("Image not found on disk: " + key);
      }
    };
    xhr.onerror = function () {
      if (TH[key]) { _crOpenFullRes(key, TH[key]); }
      else { alert("Failed to load image: " + key); }
    };
    xhr.send();
  };

})();
// === END FIX-C3b FULL-RES CROP ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")

    b64_count_before, b64_hash_before = sha256_b64(html)
    print(f"  Base64 blocks before: {b64_count_before}, sha256: {b64_hash_before}")

    if "FIX-C3b FULL-RES CROP" in html:
        print("ERROR: patch marker already present — refusing to double-patch.")
        sys.exit(1)

    if "FIX-C STATIC STILLS PATCH" not in html:
        print("ERROR: Fix-C patch not found — must apply Fix-C first.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup written: {BACKUP_PATH.name}")

    # Fix-C consumed </body>; anchor on </html> instead
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

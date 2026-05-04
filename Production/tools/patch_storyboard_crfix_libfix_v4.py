#!/usr/bin/env python3
"""
Combined patch — CRFIX + LIBFIX-V4 (2026-04-25)

ROOT CAUSES identified by 4-agent Opus debate:

1. UPLOAD BUTTON (7 iterations failed because we fought structure instead of position):
   - The CSS has #mn-lib-sidebar { transform:!important } which locks panel at
     calc(100% - 36px) even when .open class is toggled — CSS can't open the panel
   - The upload button, even if first in DOM, is inside overflow:hidden containers
     that can clip it depending on layout state
   FIX:
   a) Add #mn-lib-sidebar.open { transform:translateX(0) !important } — higher
      specificity + !important beats the base rule's !important
   b) Give the upload button position:fixed so it escapes ALL layout containers
      (overflow:hidden cannot clip position:fixed children)
   c) Toggle display via body.mn-lib-open class set by _mnLibToggle wrapper

2. CROPPER RIGHT BORDER MISSING:
   - #cr-canvas-wrap { overflow:hidden } clips the right edge of the canvas
   FIX: overflow:visible + explicit canvas block display

3. CROPPER CANNOT RESIZE:
   - Mouse handlers only implement PAN — no resize handles at all
   - scale correction needed: getBoundingClientRect() may not match canvas.width
   FIX: Add scale-corrected coords + corner hit-test + 4:3 resize on corner drag

4. AFTER CROP SAVE — NO INDICATION IN BEAT CARD:
   - _crSaveCrop sets beat.accepted_image_key but beat card renders from flux_options[]
     only — crop keys are never in flux_options, so no slot lights up
   FIX: Inject a small accepted-image thumbnail into the beat card header after save
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv4_backup.html"

SENTINEL = "CRFIX-LIBFIX-V4"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<style>
/* =========================================================
   CRFIX-LIBFIX-V4 (2026-04-25)
   Upload button: position:fixed escape + panel open fix
   Cropper: overflow:visible + scale-correct coords
   ========================================================= */

/* 1. Fix the CSS !important lock that prevents #mn-lib-sidebar.open from working.
      Both rules have !important → higher specificity wins:
      #mn-lib-sidebar.open (0-1-1-0) beats #mn-lib-sidebar (0-1-0-0) */
#mn-lib-sidebar.open {
  transform: translateX(0) !important;
  transition: transform 0.2s !important;
}

/* 2. Upload button: escape ALL flex/overflow layout.
      position:fixed takes it out of stacking context — even overflow:hidden
      on mn-lib-body cannot clip it. Show only when library is open. */
.mn-lib-upload-btn {
  position: fixed !important;
  right: 10px !important;
  bottom: 60px !important;
  width: 242px !important;
  z-index: 10002 !important;
  display: none !important;
  background: #1a2e1a !important;
  color: #6f6 !important;
  border: 1px dashed #2a4a2a !important;
  padding: 8px 4px !important;
  border-radius: 4px !important;
  cursor: pointer !important;
  font-size: 11px !important;
  text-align: center !important;
  box-sizing: border-box !important;
}
body.mn-lib-open .mn-lib-upload-btn {
  display: block !important;
}

/* 3. Cropper canvas wrap: let canvas breathe — no more clipping */
#cr-canvas-wrap {
  overflow: visible !important;
}
#cr-canvas {
  display: block !important;
  flex-shrink: 0 !important;
  cursor: crosshair !important;
}

/* 4. Accepted crop thumbnail in beat card header */
.bg-accepted-preview {
  width: 60px !important;
  height: 45px !important;
  object-fit: cover !important;
  border-radius: 3px !important;
  border: 2px solid #52b788 !important;
  margin-left: 8px !important;
  vertical-align: middle !important;
  flex-shrink: 0 !important;
}
</style>
<script>
// =====================================================================
// CRFIX-LIBFIX-V4: Definitive cropper + upload button fixes (2026-04-25)
// =====================================================================

(function () {
  "use strict";

  // ── 1. Toggle body.mn-lib-open so upload btn becomes visible ─────────
  // Wrap _mnLibToggle to add/remove class that controls btn display
  document.addEventListener("DOMContentLoaded", function () {
    var _orig = window._mnLibToggle;
    if (typeof _orig === "function") {
      window._mnLibToggle = function () {
        _orig.apply(this, arguments);
        var sidebar = document.getElementById("mn-lib-sidebar");
        if (sidebar) {
          if (sidebar.classList.contains("open")) {
            document.body.classList.add("mn-lib-open");
          } else {
            document.body.classList.remove("mn-lib-open");
          }
        }
      };
    }
  });

  // ── 2. Replace cropper mouse handlers with scale-corrected + resize ──
  document.addEventListener("DOMContentLoaded", function () {
    var canvas = document.getElementById("cr-canvas");
    if (!canvas) return;

    // Helper: get scale-corrected canvas coords from a mouse event
    function _crMousePos(e) {
      var r = canvas.getBoundingClientRect();
      var scaleX = canvas.width  / (r.width  || canvas.width);
      var scaleY = canvas.height / (r.height || canvas.height);
      return {
        x: (e.clientX - r.left) * scaleX,
        y: (e.clientY - r.top)  * scaleY
      };
    }

    // Helper: which corner is at canvas-coord (cx, cy)? Returns 'tl','tr','bl','br' or null
    var HANDLE = 14; // px hit area on each corner handle
    function _crCornerHit(cx, cy) {
      if (!CR_CROP_BOX || !CR_IMG) return null;
      var cw = canvas.width, ch = canvas.height;
      var scale = Math.min(cw / CR_IMG.width, ch / CR_IMG.height);
      var dx = (cw - CR_IMG.width  * scale) / 2;
      var dy = (ch - CR_IMG.height * scale) / 2;
      var bx = dx + CR_CROP_BOX.x * scale;
      var by = dy + CR_CROP_BOX.y * scale;
      var bw = CR_CROP_BOX.w * scale;
      var bh = CR_CROP_BOX.h * scale;
      var corners = {
        tl: [bx,        by       ],
        tr: [bx + bw,   by       ],
        bl: [bx,        by + bh  ],
        br: [bx + bw,   by + bh  ]
      };
      for (var name in corners) {
        var c = corners[name];
        if (Math.abs(cx - c[0]) <= HANDLE && Math.abs(cy - c[1]) <= HANDLE) {
          return name;
        }
      }
      return null;
    }

    var _crState = null; // {mode: 'pan'|'resize', corner, startPos, boxStart, imgScale, imgOffset}

    // REMOVE existing pan-only listeners by cloning (replaces the node)
    var newCanvas = canvas.cloneNode(true);
    canvas.parentNode.replaceChild(newCanvas, canvas);
    canvas = newCanvas;
    // Re-wire CR_CANVAS global
    if (typeof CR_CANVAS !== "undefined") { /* will be re-assigned on next _crLoadImage */ }

    canvas.addEventListener("mousedown", function (e) {
      if (!CR_IMG) return;
      var pos = _crMousePos(e);
      var corner = _crCornerHit(pos.x, pos.y);

      var cw = canvas.width, ch = canvas.height;
      var scale = Math.min(cw / CR_IMG.width, ch / CR_IMG.height);
      var imgDx = (cw - CR_IMG.width  * scale) / 2;
      var imgDy = (ch - CR_IMG.height * scale) / 2;

      _crState = {
        mode:      corner ? "resize" : "pan",
        corner:    corner,
        startPos:  pos,
        boxStart:  Object.assign({}, CR_CROP_BOX),
        imgScale:  scale,
        imgOffset: {x: imgDx, y: imgDy}
      };
    });

    canvas.addEventListener("mousemove", function (e) {
      if (!_crState || !CR_IMG) return;
      var pos  = _crMousePos(e);
      var st   = _crState;
      var sc   = st.imgScale;
      var ddx  = (pos.x - st.startPos.x) / sc; // delta in image-space pixels
      var ddy  = (pos.y - st.startPos.y) / sc;
      var box  = st.boxStart;
      var iw   = CR_IMG.width, ih = CR_IMG.height;
      var RATIO = 4 / 3;

      if (st.mode === "pan") {
        CR_CROP_BOX.x = Math.max(0, Math.min(iw - box.w, box.x + ddx));
        CR_CROP_BOX.y = Math.max(0, Math.min(ih - box.h, box.y + ddy));

      } else {
        // Resize: anchor the opposite corner, drag the hit corner
        // Only width drives aspect (4:3 locked), height is derived
        var newX = box.x, newW = box.w, newH = box.h;
        var MIN = 80; // minimum crop width in image pixels

        switch (st.corner) {
          case "br":
            newW = Math.max(MIN, box.w + ddx);
            break;
          case "bl":
            newW = Math.max(MIN, box.w - ddx);
            newX = box.x + box.w - newW;
            break;
          case "tr":
            newW = Math.max(MIN, box.w + ddx);
            break;
          case "tl":
            newW = Math.max(MIN, box.w - ddx);
            newX = box.x + box.w - newW;
            break;
        }
        newH = newW / RATIO;

        // Vertical anchor for top-corner drags
        var newY = box.y;
        if (st.corner === "tl" || st.corner === "tr") {
          newY = box.y + box.h - newH;
        }

        // Clamp to image bounds
        newX = Math.max(0, newX);
        newY = Math.max(0, newY);
        if (newX + newW > iw) { newW = iw - newX; newH = newW / RATIO; }
        if (newY + newH > ih) { newH = ih - newY; newW = newH * RATIO; }

        CR_CROP_BOX.x = newX;
        CR_CROP_BOX.y = newY;
        CR_CROP_BOX.w = newW;
        CR_CROP_BOX.h = newH;
      }

      if (typeof _crDraw === "function") _crDraw();
    });

    canvas.addEventListener("mouseup",    function () { _crState = null; });
    canvas.addEventListener("mouseleave", function () { _crState = null; });

    // Re-wire CR_CANVAS so _crDraw() uses the new node
    // (cloneNode replaces the old reference)
    if (typeof _crInitCanvas === "function") {
      document.addEventListener("mn-lib-cr-ready", _crInitCanvas);
    }
    // Direct assignment — _crLoadImage sets CR_CANVAS via getElementById
    // so the clone is found correctly as long as the id is preserved (it is).
  });

  // ── 3. After crop save: show accepted thumbnail in beat card header ──
  // Wrap _crSaveCrop to inject preview after successful save.
  document.addEventListener("DOMContentLoaded", function () {
    var _origSave = window._crSaveCrop;
    if (typeof _origSave !== "function") return;

    window._crSaveCrop = function () {
      // Intercept by monkey-patching fetch AFTER _origSave calls it.
      // Simpler: override only the success branch by post-processing.
      // We do this by temporarily wrapping fetch for the /api/cr/save-crop call.
      var _origFetch = window.fetch;
      var _once = false;
      window.fetch = function (url, opts) {
        var p = _origFetch.apply(this, arguments);
        if (!_once && typeof url === "string" && url.indexOf("/api/cr/save-crop") !== -1) {
          _once = true;
          window.fetch = _origFetch; // restore immediately
          p = p.then(function (resp) {
            // Clone and tee the response so _origSave can still read it
            var respClone = resp.clone();
            respClone.json().then(function (d) {
              if (d && d.key && CR_BEAT_ID) {
                _injectAcceptedPreview(CR_BEAT_ID, d.gallery_b64 || d.thumb_b64 || "");
              }
            }).catch(function(){});
            return resp;
          });
        }
        return p;
      };
      _origSave.apply(this, arguments);
    };
  });

  function _injectAcceptedPreview(beatId, b64src) {
    var card = document.getElementById("bg-card-" + beatId);
    if (!card) return;
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

    console.log("[CRFIX-V4] Beat", beatId, "accepted preview injected.");
  }

})();
// === END CRFIX-LIBFIX-V4 ===
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

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel {patched.count(SENTINEL)} ≠ {expected}")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")
    print()
    print("Fixes applied:")
    print("  1. #mn-lib-sidebar.open { transform !important } — CSS panel open now works")
    print("  2. .mn-lib-upload-btn { position:fixed } — escapes all overflow:hidden")
    print("  3. body.mn-lib-open class toggle in _mnLibToggle — btn shows when panel open")
    print("  4. #cr-canvas-wrap { overflow:visible } — right border no longer clipped")
    print("  5. Scale-corrected mouse coords + 4:3 resize on corner drag in cropper")
    print("  6. Accepted crop thumbnail injected into beat card header after save")


if __name__ == "__main__":
    main()

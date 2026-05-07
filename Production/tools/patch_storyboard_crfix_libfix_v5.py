#!/usr/bin/env python3
"""
Terminal fix — CRFIX-LIBFIX-V5 (2026-04-25)

ROOT CAUSES (confirmed by 2 Opus agents after 4 failed iterations):

1. UPLOAD BUTTON trapped by CSS Transforms (CSS Transforms Module Level 1 §3):
   transform on a parent creates a containing block for position:fixed descendants.
   #mn-lib-sidebar has transform:translateX(...) so position:fixed on .mn-lib-upload-btn
   positions the button relative to the 260px sidebar — not the viewport.
   FIX: Move the label element to be a DIRECT CHILD OF <body> (static HTML move).
   position:fixed then positions relative to the viewport as intended.
   Safety net: DOMContentLoaded JS ensures the move even if static regex mis-fires.

2. CROP SAVE THUMBNAIL wiped by re-render:
   a) V4's _crSaveCrop wrapped window.fetch with a _once flag — broken because the
      async blob→FileReader chain takes 100-500ms, during which other fetches can fire.
   b) _bgSwitchTab("bg", null) triggers _bgRenderBeats which rebuilds ALL beat cards
      from scratch, wiping any .bg-accepted-preview injected before the async completes.
   FIX:
   a) Complete _crSaveCrop rewrite: no fetch interception, draws from CR_IMG directly
      using document.getElementById("cr-canvas"), captures beatIdAtSave before async.
   b) _bgSwitchTab called FIRST, then _injectAcceptedPreview with setTimeout(150)
      so the thumbnail is injected AFTER the re-render settles.
   c) TH[] populated immediately so _bgRenderBeats wrapper can re-inject on future renders.
   d) _bgRenderBeats wrapper: after every render, re-injects thumbnails for beats
      with accepted_image_key present in TH[].
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv5_backup.html"

SENTINEL = "CRFIX-LIBFIX-V5"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


def move_upload_btn_to_body(html: str):
    """
    Extract <label class="mn-lib-upload-btn">...</label> from wherever it sits
    (currently first child of .mn-lib-body after LIBFIX-V3) and inject it as
    a direct child of <body> just before </body>.
    Returns new_html.
    """
    btn_pattern = re.compile(
        r'[ \t]*<label[^>]*class="mn-lib-upload-btn"[^>]*>.*?</label>[ \t]*\n?',
        re.DOTALL
    )
    m = btn_pattern.search(html)
    if not m:
        raise ValueError("Could not find .mn-lib-upload-btn label in HTML")

    label_html = m.group(0).strip()
    html_without_btn = html[:m.start()] + html[m.end():]

    anchor = "</body>" if "</body>" in html_without_btn else "</html>"
    return html_without_btn.replace(anchor, "\n" + label_html + "\n" + anchor, 1), label_html


PATCH = """\

<style>
/* =========================================================
   CRFIX-LIBFIX-V5 (2026-04-25)
   Upload button: moved to <body> direct child — viewport-relative fixed
   Crop save: complete rewrite — thumbnail survives re-render
   ========================================================= */

/* Button is now a DIRECT child of <body>, no transformed ancestor.
   position:fixed is viewport-relative. Show when body.mn-lib-open
   (set by _mnLibToggle wrapper already installed in CRFIX-LIBFIX-V4). */
body > label.mn-lib-upload-btn {
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
body.mn-lib-open > label.mn-lib-upload-btn {
  display: block !important;
}
</style>
<script>
// =====================================================================
// CRFIX-LIBFIX-V5: Terminal upload button + crop thumbnail fix (2026-04-25)
// =====================================================================

(function () {
  "use strict";

  // ── 1. Safety-net: ensure .mn-lib-upload-btn is direct child of <body> ──
  // Static HTML was already restructured above. This guard runs on
  // DOMContentLoaded as a belt-and-suspenders check.
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.querySelector("label.mn-lib-upload-btn");
    if (!btn) { console.warn("[V5] .mn-lib-upload-btn not found in DOM"); return; }
    if (btn.parentNode !== document.body) {
      document.body.appendChild(btn);
      console.log("[V5] upload btn moved to body from:", btn.parentNode && btn.parentNode.id);
    } else {
      console.log("[V5] upload btn already at body level — OK");
    }
  });

  // ── 2. Complete _crSaveCrop rewrite ─────────────────────────────────────
  // Replaces the broken V4 fetch-interception approach entirely.
  // Key invariants:
  //   - beatIdAtSave captured synchronously before any async work
  //   - Draws from document.getElementById("cr-canvas") so canvas clone (from V4)
  //     doesn't cause CR_CANVAS global to point to a detached node
  //   - _bgSwitchTab called first, then _injectAcceptedPreview with setTimeout(150)
  //     so thumbnail is injected AFTER _bgRenderBeats re-render settles
  //   - TH[] populated immediately so future renders can re-inject the thumbnail
  document.addEventListener("DOMContentLoaded", function () {

    window._crSaveCrop = function () {
      // Prefer getElementById over CR_CANVAS global (clone may have detached old ref)
      var srcCanvas = document.getElementById("cr-canvas");
      if (!srcCanvas && typeof CR_CANVAS !== "undefined") srcCanvas = CR_CANVAS;
      if (!CR_IMG || !srcCanvas) {
        alert("No image loaded into cropper.");
        return;
      }

      // Capture mutable globals NOW before any async
      var beatIdAtSave = (typeof CR_BEAT_ID !== "undefined") ? CR_BEAT_ID : null;
      var srcKeyAtSave = (typeof CR_SRC_KEY !== "undefined") ? CR_SRC_KEY : null;

      // Build crop canvas
      var w = Math.max(1, Math.round(CR_CROP_BOX.w));
      var h = Math.max(1, Math.round(CR_CROP_BOX.h));
      var tmp = document.createElement("canvas");
      tmp.width  = w;
      tmp.height = h;
      tmp.getContext("2d").drawImage(
        CR_IMG,
        CR_CROP_BOX.x, CR_CROP_BOX.y, w, h,
        0, 0, w, h
      );

      // Disable save button while in flight
      var saveBtn = document.getElementById("cr-save-btn");
      if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Saving\u2026"; }

      var _restoreBtn = function () {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "\\uD83D\\uDCBE Save Crop"; }
      };

      tmp.toBlob(function (blob) {
        if (!blob) { _restoreBtn(); alert("Failed to generate crop PNG."); return; }

        var reader = new FileReader();
        reader.onload = function () {
          var b64 = reader.result.split(",")[1];

          fetch(BG_SERVER + "/api/cr/save-crop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              crop_png_b64: b64,
              beat_id:      beatIdAtSave,
              source_key:   srcKeyAtSave
            })
          })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d || d.error) {
              alert("Save failed: " + (d && d.error ? d.error : "unknown"));
              return;
            }

            // Add to library gallery
            if (d.key && d.filename && d.thumb_b64 && d.gallery_b64) {
              if (typeof _injectImage === "function") {
                _injectImage(d.key, d.filename, d.thumb_b64, d.gallery_b64);
              }
            }

            // Populate TH[] so future renders can re-inject the thumbnail
            var thumbSrc = d.gallery_b64 || d.thumb_b64;
            if (thumbSrc && d.key && typeof TH !== "undefined") {
              TH[d.key] = thumbSrc;
            }

            // Update in-memory beat record
            if (beatIdAtSave && d.key) {
              var blist = Array.isArray(BG_BEATS) ? BG_BEATS : [];
              for (var j = 0; j < blist.length; j++) {
                if (blist[j].beat_id === beatIdAtSave) {
                  blist[j].accepted_image_key = d.key;
                  blist[j].status = "cropped";
                  break;
                }
              }
              // Persist to server
              fetch(BG_SERVER + "/api/bg/accept-option", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ beat_id: beatIdAtSave, option_key: d.key })
              }).catch(function () {});
            }

            // Switch tab FIRST (triggers _bgRenderBeats which rebuilds cards)
            if (typeof _bgSwitchTab === "function") {
              _bgSwitchTab("bg", null);
            }

            // Inject thumbnail AFTER re-render settles (150ms > one React tick)
            if (beatIdAtSave && thumbSrc) {
              setTimeout(function () {
                _injectAcceptedPreview(beatIdAtSave, thumbSrc);
              }, 150);
            }

            console.log("[V5-CROP] Beat", beatIdAtSave, "saved key:", d.key);
          })
          .catch(function (e) { alert("Crop upload error: " + e); })
          .finally(_restoreBtn);
        };
        reader.readAsDataURL(blob);
      }, "image/png");
    };

  });

  // ── 3. _bgRenderBeats wrapper: re-inject thumbnails after every render ──
  // Every _bgRenderBeats call rebuilds beat cards from scratch, wiping any
  // .bg-accepted-preview elements. This wrapper re-injects them for all beats
  // that have accepted_image_key present in TH[].
  document.addEventListener("DOMContentLoaded", function () {
    var _prev = window._bgRenderBeats;
    if (typeof _prev !== "function") return;

    window._bgRenderBeats = function (beats) {
      _prev.call(this, beats || BG_BEATS);
      setTimeout(function () {
        var blist = Array.isArray(BG_BEATS) ? BG_BEATS : [];
        for (var i = 0; i < blist.length; i++) {
          var beat = blist[i];
          if (!beat || !beat.accepted_image_key) continue;
          var src = (typeof TH !== "undefined") ? TH[beat.accepted_image_key] : null;
          if (src && typeof _injectAcceptedPreview === "function") {
            _injectAcceptedPreview(beat.beat_id, src);
          }
        }
      }, 80);
    };
  });

})();
// === END CRFIX-LIBFIX-V5 ===
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

    # Step 1: Move upload button out of sidebar to direct <body> child
    print("  Moving .mn-lib-upload-btn to direct child of <body>...")
    try:
        html, label_html = move_upload_btn_to_body(html)
        preview = label_html[:80].replace("\n", " ")
        print(f"  ✓ Button extracted ({len(label_html)} chars): {preview!r}...")
    except ValueError as e:
        print(f"ABORT: {e}")
        sys.exit(1)

    # Verify button is NOT still inside #mn-lib-sidebar
    sidebar_idx = html.find('id="mn-lib-sidebar"')
    if sidebar_idx >= 0:
        # Sidebar closes within ~8KB; scan that window for the btn
        sidebar_window = html[sidebar_idx:sidebar_idx + 10000]
        if 'mn-lib-upload-btn' in sidebar_window:
            # Could be a false positive from CSS text; check HTML element form
            if '<label' in sidebar_window and 'mn-lib-upload-btn' in sidebar_window:
                print("ABORT: .mn-lib-upload-btn still found inside #mn-lib-sidebar")
                sys.exit(1)
    print("  ✓ Button no longer inside #mn-lib-sidebar")

    # Verify button appears near </body>
    body_close_idx = html.rfind("</body>")
    if body_close_idx > 0:
        tail = html[max(0, body_close_idx - 2000):body_close_idx]
        if 'mn-lib-upload-btn' not in tail:
            print("ABORT: button not found near </body> after move")
            sys.exit(1)
    print("  ✓ Button confirmed near </body>")

    # Step 2: Inject CSS + JS patch
    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    # Safety: base64 byte-identical
    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel {patched.count(SENTINEL)} ≠ {expected}")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    # Write to temp file first, rename on success — prevents truncating HTML on encoding failure
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
    print("  1. Static HTML: .mn-lib-upload-btn moved to direct child of <body>")
    print("     → position:fixed is now viewport-relative, not sidebar-relative")
    print("  2. JS safety-net on DOMContentLoaded: moves btn to body if not already there")
    print("  3. CSS: body > label.mn-lib-upload-btn { fixed, right:10px, bottom:60px }")
    print("     body.mn-lib-open > label.mn-lib-upload-btn { display:block }")
    print("  4. JS: Complete _crSaveCrop rewrite — getElementById for canvas, no fetch wrap")
    print("     → _bgSwitchTab first, then _injectAcceptedPreview with setTimeout(150)")
    print("     → TH[] populated immediately so future re-renders can re-inject")
    print("  5. JS: _bgRenderBeats wrapper re-injects .bg-accepted-preview after every render")


if __name__ == "__main__":
    main()

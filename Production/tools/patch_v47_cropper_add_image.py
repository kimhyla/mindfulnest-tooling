#!/usr/bin/env python3
"""
Path B patch: Add "Add Image" + "Library" buttons to Cropper tab (#cr-sidebar)
and wire library-item clicks to load into the Cropper canvas when Cropper is active.

Input:  storyboard_v46_prod.html
Output: storyboard_v47_prod.html

Safety: SHA256 of all base64 blobs verified identical before/after.
"""
import hashlib, re, sys
from pathlib import Path

SRC  = Path(__file__).parent.parent / "Event_1" / "storyboard_v46_prod.html"
DEST = Path(__file__).parent.parent / "Event_1" / "storyboard_v47_prod.html"

# ── 1. Read source ──────────────────────────────────────────────────────────
html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars, {html.count(chr(10))+1} lines")

# ── 2. Hash all base64 blobs (images must survive byte-identical) ───────────
def b64_hash(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs:
        h.update(b.encode())
    return h.hexdigest(), len(blobs)

hash_before, count_before = b64_hash(html)
print(f"Base64 blobs before: {count_before}, hash: {hash_before[:16]}…")

# ── 3. Build the Fix-L script block ────────────────────────────────────────
FIX_L = r"""
<script>
// ══════════════════════════════════════════════════════════════════════════
// Fix-L: Cropper "Add Image" + Library click-to-load (2026-04-27)
//   1. Adds "⬆ Add Image" + "📚 Library" buttons to #cr-sidebar.
//   2. "Add Image" uploads immediately AND auto-loads into the canvas.
//   3. Clicking a library item while Cropper tab is active loads it into
//      the canvas (full-res fetch, same path as the existing drag-drop).
// ══════════════════════════════════════════════════════════════════════════
(function () {
  "use strict";
  if (window._crLibraryInited) return;
  window._crLibraryInited = true;

  // ── 1. Inject buttons into #cr-sidebar ─────────────────────────────────
  function _crAddSidebarButtons() {
    var sidebar = document.getElementById("cr-sidebar");
    if (!sidebar) return;
    if (document.getElementById("cr-lib-btn-wrap")) return; // idempotency

    var wrap = document.createElement("div");
    wrap.id = "cr-lib-btn-wrap";
    wrap.style.cssText = "margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;";

    // ── "⬆ Add Image" label/input ─────────────────────────────────────────
    // Uploads file → saves to library → auto-loads into Cropper canvas.
    var lbl = document.createElement("label");
    lbl.className = "mn-lib-upload-btn";
    lbl.style.cssText = "flex:1;min-width:80px;text-align:center;cursor:pointer;";
    lbl.textContent = "⬆ Add Image";
    var inp = document.createElement("input");
    inp.type = "file";
    inp.accept = "image/*";
    inp.style.display = "none";
    inp.addEventListener("change", function () {
      if (!inp.files || !inp.files[0]) return;
      var file = inp.files[0];
      var reader = new FileReader();
      reader.onload = function () {
        var b64 = reader.result.split(",")[1];
        fetch(BG_SERVER + "/api/cr/upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, image_b64: b64, tier: "source" })
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { alert("Upload failed: " + (d.error || "unknown")); return; }
          if (typeof _mnLibFetch === "function") _mnLibFetch(); // refresh library panel
          // Auto-load into Cropper canvas from the b64 already in memory
          window.CR_BEAT_ID = null;
          window.CR_SRC_KEY = d.key || file.name;
          var img2 = new Image();
          img2.onload = function () {
            window.CR_IMG = img2;
            var cw = Math.min(img2.width, img2.height * 4 / 3);
            var ch = cw * 3 / 4;
            window.CR_CROP_BOX = {
              x: (img2.width - cw) / 2,
              y: (img2.height - ch) / 2,
              w: cw, h: ch
            };
            if (typeof _crDraw === "function") _crDraw();
            var info = document.getElementById("cr-crop-info");
            if (info) info.textContent = "Image: " + img2.width + "×" + img2.height + "px  Crop: 4:3";
            var saveBtn = document.getElementById("cr-save-btn");
            if (saveBtn) saveBtn.disabled = false;
          };
          img2.src = "data:" + file.type + ";base64," + b64;
        })
        .catch(function (ex) { alert("Upload error: " + ex); });
      };
      reader.readAsDataURL(file);
      inp.value = "";
    });
    lbl.appendChild(inp);
    wrap.appendChild(lbl);

    // ── "📚 Library" button ────────────────────────────────────────────────
    // Opens the shared #mn-lib-sidebar so Kim can pick an existing image.
    var libBtn = document.createElement("button");
    libBtn.className = "b";
    libBtn.textContent = "📚 Library";
    libBtn.style.cssText = "flex:1;min-width:80px;";
    libBtn.addEventListener("click", function () {
      if (typeof _mnLibToggle === "function") _mnLibToggle();
    });
    wrap.appendChild(libBtn);

    // Insert before the Save/Back button row (first div[style] child)
    var btnRow = sidebar.querySelector("div[style]");
    if (btnRow) {
      sidebar.insertBefore(wrap, btnRow);
    } else {
      sidebar.appendChild(wrap);
    }
  }

  // ── 2. Library item click → Cropper when Cropper tab is active ──────────
  // Event delegation on #mn-lib-sidebar — survives _mnLibRender re-renders.
  function _crLibClickRoute(e) {
    // Only intercept .mn-lib-item clicks
    var item = e.target && e.target.closest && e.target.closest(".mn-lib-item");
    if (!item) return;
    // Only when Cropper tab is the active panel
    var crPanel = document.getElementById("panel-cr");
    if (!crPanel || !crPanel.classList.contains("active")) return;

    e.preventDefault();
    e.stopPropagation();

    var key = item.getAttribute("data-key");
    if (!key) return;

    // Look up abs_path from in-memory MN_LIB_DATA (same pattern as drop handler)
    var libItem = null;
    for (var i = 0; i < MN_LIB_DATA.length; i++) {
      if (MN_LIB_DATA[i].key === key) { libItem = MN_LIB_DATA[i]; break; }
    }
    if (!libItem) { console.warn("[Fix-L] key not found in MN_LIB_DATA:", key); return; }

    var apath = libItem.abs_path || "";
    if (!apath) { console.warn("[Fix-L] no abs_path for key:", key); return; }

    // Fetch full-res (same path as the drop handler on #cr-canvas-wrap at line ~5395)
    fetch(BG_SERVER + "/api/cr/full?abs_path=" + encodeURIComponent(apath))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok || !d.data_uri) { console.warn("[Fix-L] full-res failed:", d); return; }
        window.CR_BEAT_ID = null;
        window.CR_SRC_KEY = key;
        var img2 = new Image();
        img2.onload = function () {
          window.CR_IMG = img2;
          var cw = Math.min(img2.width, img2.height * 4 / 3);
          var ch = cw * 3 / 4;
          window.CR_CROP_BOX = {
            x: (img2.width - cw) / 2,
            y: (img2.height - ch) / 2,
            w: cw, h: ch
          };
          if (typeof _crDraw === "function") _crDraw();
          var info = document.getElementById("cr-crop-info");
          if (info) info.textContent = "Image: " + img2.width + "×" + img2.height + "px  Crop: 4:3";
          var saveBtn = document.getElementById("cr-save-btn");
          if (saveBtn) saveBtn.disabled = false;
          // Auto-close the library panel after selection
          var s = document.getElementById("mn-lib-sidebar");
          if (s && s.classList.contains("open")) s.classList.remove("open");
        };
        img2.src = d.data_uri;
      })
      .catch(function (ex) { console.warn("[Fix-L] fetch error:", ex); });
  }

  // ── 3. Wire up on DOM ready ─────────────────────────────────────────────
  function _crLibInit() {
    var libSidebar = document.getElementById("mn-lib-sidebar");
    if (libSidebar && !libSidebar._crClickWired) {
      libSidebar.addEventListener("click", _crLibClickRoute);
      libSidebar._crClickWired = true;
    }
    _crAddSidebarButtons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _crLibInit);
  } else {
    _crLibInit();
  }
})();
</script>
"""

# ── 4. Inject before </html> using rfind (not endswith) ────────────────────
MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found — aborting.")
    sys.exit(1)

patched = html[:pos] + FIX_L + html[pos:]
print(f"Injected Fix-L ({len(FIX_L):,} chars) before </html> at position {pos:,}")

# ── 5. Verify base64 integrity ──────────────────────────────────────────────
hash_after, count_after = b64_hash(patched)
if hash_before != hash_after:
    print(f"INTEGRITY FAIL: base64 hash changed!")
    print(f"  Before: {hash_before}")
    print(f"  After:  {hash_after}")
    sys.exit(1)
if count_before != count_after:
    print(f"INTEGRITY FAIL: blob count changed {count_before} → {count_after}")
    sys.exit(1)
print(f"Base64 integrity verified: {count_after} blobs, hash {hash_after[:16]}…  ✓")

# ── 6. Write output ─────────────────────────────────────────────────────────
DEST.write_text(patched, encoding="utf-8")
print(f"\nWrote {DEST.name}: {len(patched):,} chars")
print("Done — open storyboard_v47_prod.html in browser to test.")

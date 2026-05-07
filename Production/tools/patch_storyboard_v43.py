#!/usr/bin/env python3
"""
patch_storyboard_v43.py — Definitive library drag-drop fix.
Reads storyboard_v42_prod.html, applies 4 HTML patches, writes storyboard_v43_prod.html.
Also patches production_server.py to strip the nav-injection JS override block.

ROOT CAUSES FIXED
─────────────────
1. Nav-injection _mnLibRender override fired 400 ms after page load, raced with
   MN_LIB_DATA, and registered a dragstart handler that removed '.open' from the
   sidebar mid-drag → CSS transition slid the source element offscreen → Chromium
   aborted the drag session before any drop could land.

2. The correct fix: use a CSS attribute selector on <body data-mn-dragging="1">
   plus transition:none so the sidebar snaps offscreen INSTANTLY on dragstart
   (browser has already captured the drag image at that point).

3. img elements inside library items lacked draggable="false", allowing Chrome's
   native image-drag to steal the dataTransfer in some situations.

4. Cropper drop loaded a 200×150 thumbnail into CR_IMG → crop quality was terrible.
   Fix: async fetch from /api/cr/full for full-resolution image.

WHAT IS NOT CHANGED
───────────────────
• _mnLibFetch already uses ?_t=Date.now() cache-buster in v42 — no change needed.
• _mnLibUpload already calls _mnLibFetch() correctly — no change needed.
• gallery_b64 in library API already equals thumb_b64 and _injectImage ignores
  arg 4 entirely — .lr storyboard row drops are correct as-is.
• The storyboard nav bar UI (switcher, Load/Refresh buttons) is preserved.
"""
import sys
import shutil
import time
from pathlib import Path

_HERE    = Path(__file__).parent
_EVENT   = _HERE.parent / "Event_1"
SRC      = _EVENT / "storyboard_v42_prod.html"
DST      = _EVENT / "storyboard_v43_prod.html"
SERVER   = _HERE  / "production_server.py"

# ── Pre-flight ────────────────────────────────────────────────────────────────
if not SRC.exists():
    print(f"ERROR: source not found: {SRC}"); sys.exit(1)
if DST.exists():
    print(f"ERROR: {DST.name} already exists — delete it first to avoid "
          f"overwriting Kim's edits."); sys.exit(1)

html = SRC.read_text(encoding="utf-8", errors="replace")
b64_before = html.count("data:image/")
print(f"Source : {SRC.name}  ({len(html)//1024} KB, {b64_before} base64 blobs)")

ts = int(time.time())
bak_html = SRC.with_suffix(f".html.bak.{ts}")
shutil.copy2(SRC, bak_html)
print(f"Backup : {bak_html.name}")

# ── Patch helper ──────────────────────────────────────────────────────────────
def patch(text, name, old, new):
    count = text.count(old)
    assert count == 1, (
        f"\nFAIL {name}: anchor found {count} time(s) — expected exactly 1.\n"
        f"Anchor preview: {repr(old[:140])}"
    )
    result = text.replace(old, new, 1)
    print(f"OK   {name}")
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# H1 — CSS: instant sidebar hide via body attribute (no transition during drag)
# ═══════════════════════════════════════════════════════════════════════════════
# Why: the only existing rule that hides the sidebar is removing ".open" which
# triggers the 0.2s CSS transition. That transition moves the source element
# off-screen while Chromium still tracks it → drag session aborted.
# body[data-mn-dragging] overrides transform + disables transition atomically.

H1_OLD = "#mn-lib-sidebar.open{transform:translateX(0)}"

H1_NEW = (
    "#mn-lib-sidebar.open{transform:translateX(0)}"
    "body[data-mn-dragging=\"1\"] #mn-lib-sidebar{"
    "transform:translateX(calc(100% - 36px))!important;"
    "transition:none!important}"
)

html = patch(html, "H1 (drag-state CSS)", H1_OLD, H1_NEW)

# ═══════════════════════════════════════════════════════════════════════════════
# H2 — _mnLibRender: add draggable=false on img + filename label
# ═══════════════════════════════════════════════════════════════════════════════
# draggable=false: prevents Chrome's native image-drag from stealing dataTransfer.
# label: Kim needs to tell apart guide_bird_shocked_halfsmile vs _openmouth etc.

H2_OLD = (
    "      var img = document.createElement('img');\n"
    "      img.src = item.thumb_b64;\n"
    "      img.alt = item.filename;\n"
    "      el.appendChild(img);\n"
    "      var badge = document.createElement('span');"
)

H2_NEW = (
    "      var img = document.createElement('img');\n"
    "      img.src = item.thumb_b64;\n"
    "      img.alt = item.filename;\n"
    "      img.setAttribute('draggable', 'false');\n"
    "      el.appendChild(img);\n"
    "      var lbl = document.createElement('span');\n"
    "      lbl.style.cssText = 'position:absolute;bottom:0;left:0;right:0;font-size:8px;'\n"
    "        + 'padding:2px 3px;background:rgba(0,0,0,.75);color:#ddd;'\n"
    "        + 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none;';\n"
    "      lbl.textContent = item.key;\n"
    "      el.appendChild(lbl);\n"
    "      var badge = document.createElement('span');"
)

html = patch(html, "H2 (draggable=false + filename label)", H2_OLD, H2_NEW)

# ═══════════════════════════════════════════════════════════════════════════════
# H3 — _mnLibRender dragstart/dragend: set/clear body[data-mn-dragging]
# ═══════════════════════════════════════════════════════════════════════════════
# dragstart: set attribute → H1 CSS instantly hides sidebar (transition:none).
# dragend: always fires (even on cancelled drops) → clears attribute → sidebar
# smoothly slides back open via the original 0.2s transition.

H3_OLD = (
    "      el.addEventListener('dragstart', function(e) {\n"
    "        el.classList.add('dragging');\n"
    "        e.dataTransfer.setData('mn-lib-key', item.key);"
    " // key only \u2014 full data looked up in MN_LIB_DATA on drop\n"
    "        e.dataTransfer.effectAllowed = 'copy';\n"
    "      });\n"
    "      el.addEventListener('dragend', function(){ el.classList.remove('dragging'); });"
)

H3_NEW = (
    "      el.addEventListener('dragstart', function(e) {\n"
    "        el.classList.add('dragging');\n"
    "        e.dataTransfer.setData('mn-lib-key', item.key);"
    " // key only \u2014 full data looked up in MN_LIB_DATA on drop\n"
    "        e.dataTransfer.effectAllowed = 'copy';\n"
    "        document.body.setAttribute('data-mn-dragging', '1');\n"
    "      });\n"
    "      el.addEventListener('dragend', function() {\n"
    "        el.classList.remove('dragging');\n"
    "        document.body.removeAttribute('data-mn-dragging');\n"
    "      });"
)

html = patch(html, "H3 (data-mn-dragging on dragstart/dragend)", H3_OLD, H3_NEW)

# ═══════════════════════════════════════════════════════════════════════════════
# H4 — Global drop handler: Cropper branch → async full-res fetch
# ═══════════════════════════════════════════════════════════════════════════════
# Old code: img2.src = b64  where b64 == gallery_b64 == thumbnail (200x150).
# Cropper needs the original full-resolution image for Rule 6 (≥600px shortest
# side). /api/cr/full?abs_path=... returns the raw file as a data URI.
#
# KNOWN UX LIMIT: #panel-cr is display:none when Cropper tab is not active,
# so drops only land when the user has already switched to the Cropper tab.
# This is documented — not fixed in v43.
#
# Also: clear data-mn-dragging attribute here as belt-and-suspenders in case
# dragend fired before the fetch completed (rare but possible).

H4_OLD = (
    "  // Drop on #cr-canvas-wrap \u2192 load into Cropper\n"
    "  var crw = e.target.closest && e.target.closest('#cr-canvas-wrap');\n"
    "  if (crw) {\n"
    "    e.preventDefault();\n"
    "    if (!b64) return;\n"
    "    CR_BEAT_ID = null;\n"
    "    CR_SRC_KEY = key;\n"
    "    var img2 = new Image();\n"
    "    img2.onload = function() {\n"
    "      CR_IMG = img2;\n"
    "      var cw = Math.min(img2.width, img2.height * 4/3);\n"
    "      var ch = cw * 3/4;\n"
    "      CR_CROP_BOX = {x:(img2.width-cw)/2, y:(img2.height-ch)/2, w:cw, h:ch};\n"
    "      _bgSwitchTab('cr', null);\n"
    "      _crDraw();\n"
    "      var info = document.getElementById('cr-crop-info');\n"
    "      if (info) info.textContent = 'Image: ' + img2.width + '\\u00d7' + img2.height + 'px  Crop: 4:3';\n"
    "      var saveBtn = document.getElementById('cr-save-btn');\n"
    "      if (saveBtn) saveBtn.disabled = false;\n"
    "    };\n"
    "    img2.src = b64;\n"
    "    return;\n"
    "  }"
)

H4_NEW = (
    "  // Drop on #cr-canvas-wrap \u2192 fetch full-res image, then load into Cropper\n"
    "  // NOTE: requires Cropper tab to be active first (#panel-cr is display:none\n"
    "  // when inactive \u2014 pointer events never reach the canvas in that state).\n"
    "  var crw = e.target.closest && e.target.closest('#cr-canvas-wrap');\n"
    "  if (crw) {\n"
    "    e.preventDefault();\n"
    "    document.body.removeAttribute('data-mn-dragging'); // belt-and-suspenders clear\n"
    "    if (!apath) return;\n"
    "    fetch(BG_SERVER + '/api/cr/full?abs_path=' + encodeURIComponent(apath))\n"
    "      .then(function(r){ return r.json(); })\n"
    "      .then(function(d){\n"
    "        if (!d.ok || !d.data_uri) {\n"
    "          console.warn('[lib-drop] /api/cr/full failed', d); return;\n"
    "        }\n"
    "        CR_BEAT_ID = null;\n"
    "        CR_SRC_KEY = key;\n"
    "        var img2 = new Image();\n"
    "        img2.onload = function() {\n"
    "          CR_IMG = img2;\n"
    "          var cw = Math.min(img2.width, img2.height * 4/3);\n"
    "          var ch = cw * 3/4;\n"
    "          CR_CROP_BOX = {x:(img2.width-cw)/2, y:(img2.height-ch)/2, w:cw, h:ch};\n"
    "          _bgSwitchTab('cr', null);\n"
    "          _crDraw();\n"
    "          var info = document.getElementById('cr-crop-info');\n"
    "          if (info) info.textContent = 'Image: ' + img2.width + '\\u00d7' + img2.height + 'px  Crop: 4:3';\n"
    "          var saveBtn = document.getElementById('cr-save-btn');\n"
    "          if (saveBtn) saveBtn.disabled = false;\n"
    "        };\n"
    "        img2.src = d.data_uri;\n"
    "      })\n"
    "      .catch(function(ex){ console.warn('[lib-drop] cropper full-res error:', ex); });\n"
    "    return;\n"
    "  }"
)

html = patch(html, "H4 (Cropper async full-res)", H4_OLD, H4_NEW)

# ═══════════════════════════════════════════════════════════════════════════════
# Integrity checks — BLOCKING
# ═══════════════════════════════════════════════════════════════════════════════
b64_after = html.count("data:image/")
assert b64_after == b64_before, \
    f"FAIL: base64 blob count changed {b64_before} \u2192 {b64_after}"
assert html.count('body[data-mn-dragging="1"]') == 1, \
    "FAIL: H1 drag-state CSS rule not found in output"
assert html.count("img.setAttribute('draggable', 'false')") == 1, \
    "FAIL: H2 draggable=false not found"
assert html.count("document.body.setAttribute('data-mn-dragging', '1')") == 1, \
    "FAIL: H3 dragstart attribute set not found"
assert html.count("document.body.removeAttribute('data-mn-dragging')") >= 1, \
    "FAIL: H3/H4 attribute clear not found"
assert html.count('/api/cr/full?abs_path=') == 1, \
    "FAIL: H4 async cropper fetch not found"
assert html.count('data-lib-was-open') == 0, \
    "FAIL: broken auto-hide (data-lib-was-open) still present — nav override not cleaned up"
assert html.count('_navLibRefresh') == 0, \
    "FAIL: _navLibRefresh still in HTML — nav override not cleaned up"

print(f"OK   base64 blobs: {b64_after} (unchanged)")

# ── Write v43 HTML ────────────────────────────────────────────────────────────
DST.write_text(html, encoding="utf-8")
print(f"OK   Written: {DST.name}  ({DST.stat().st_size // 1024} KB)")

# ═══════════════════════════════════════════════════════════════════════════════
# S1 — Strip nav-injection override block from production_server.py
# ═══════════════════════════════════════════════════════════════════════════════
# The _build_storyboard_nav_html function currently injects a second <script>
# block that overrides _mnLibRender, _mnLibUpload, and adds a capture-phase
# drop handler. These overrides were the root cause of the racing/corruption
# problem. With H1-H4 baked directly into the HTML, the overrides are not only
# unnecessary but harmful (they would overwrite H2/H3 on every page serve).
#
# What is KEPT in the nav injection:
#   • <style> for #sb-nav-bar
#   • <script> for window.__ACTIVE_STORYBOARD_STEM__
#   • <div id="sb-nav-bar"> HTML (switcher, Load, Refresh buttons, active pill)
#   • <script> IIFE for storyboard list fetch + load/refresh button handlers
#
# What is STRIPPED (the entire second <script> block):
#   • window._mnLibRender override (with broken auto-hide dragstart)
#   • _navLibRefresh function + setTimeout 400ms re-fetch
#   • window._mnLibUpload override
#   • capture-phase document drop handler

print("\n--- Patching production_server.py ---")

if not SERVER.exists():
    print(f"SKIP: {SERVER.name} not found at {SERVER} — patch manually.")
else:
    bak_srv = SERVER.with_suffix(f".py.bak.{ts}")
    shutil.copy2(SERVER, bak_srv)
    print(f"Backup : {bak_srv.name}")

    srv = SERVER.read_text(encoding="utf-8", errors="replace")

    # The second <script> block begins immediately after the switcher IIFE's </script>
    # and ends with </script>""" (the closing of the Python f-string).
    S1_START = '\n<script>\n/* Nav-injected library fix'
    S1_END   = '</script>"""'

    s1_idx = srv.find(S1_START)
    assert s1_idx != -1, \
        "FAIL S1: override block start marker not found in production_server.py\n" \
        f"  Looking for: {repr(S1_START)}"

    s1_end_idx = srv.find(S1_END, s1_idx)
    assert s1_end_idx != -1, \
        "FAIL S1: override block end marker not found after start marker\n" \
        f"  Looking for: {repr(S1_END)}"

    # Cut from start of second <script> through (and including) </script>"""
    # Replace with just """ so the f-string closes cleanly after the first block.
    srv_patched = srv[:s1_idx] + '\n"""' + srv[s1_end_idx + len(S1_END):]

    # Verify override content is gone
    assert 'Nav-injected library fix' not in srv_patched, \
        "FAIL S1: override comment still present after patch"
    assert '_navLibRefresh'           not in srv_patched, \
        "FAIL S1: _navLibRefresh still present after patch"
    assert 'data-lib-was-open'        not in srv_patched, \
        "FAIL S1: data-lib-was-open still present after patch"

    # Syntax check — catches malformed f-string or missing closing quote
    try:
        import ast as _ast
        _ast.parse(srv_patched)
        print("OK   S1 syntax check passed")
    except SyntaxError as se:
        print(f"\nFAIL S1 syntax error after strip: {se}")
        print("Restoring backup and aborting.")
        shutil.copy2(bak_srv, SERVER)
        sys.exit(1)

    SERVER.write_text(srv_patched, encoding="utf-8")
    print(f"OK   S1 nav-injection override block stripped")
    print(f"     Server: {SERVER.stat().st_size // 1024} KB")

# ═══════════════════════════════════════════════════════════════════════════════
print("""
\033[92mDONE\033[0m — storyboard_v43_prod.html + production_server.py patched.

Next steps:
  1. Stop the current server (Ctrl-C or kill the process on port 5111)
  2. Restart with:
       python3 production_server.py \\
         --event-dir ../Event_1 \\
         --storyboard storyboard_v43_prod.html \\
         --event-id Event_1
  3. Hard-refresh browser: \033[1mCmd+Shift+R\033[0m

What changed:
  H1  CSS: body[data-mn-dragging] hides sidebar INSTANTLY (no transition)
  H2  img draggable=false + filename label on every library item
  H3  dragstart sets body attr (sidebar snaps closed); dragend clears it
  H4  Cropper drop fetches full-res via /api/cr/full (was thumbnail before)
  S1  Nav-injection override block stripped (no more racing re-render at +400ms)

Keep storyboard_v42_prod.html until Kim confirms v43 is working.
""")

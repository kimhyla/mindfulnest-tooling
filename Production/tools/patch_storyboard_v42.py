#!/usr/bin/env python3
"""
patch_storyboard_v42.py — Path B JS+CSS patch. No base64 touched.
Reads storyboard_v41_prod.html, applies 3 changes, writes storyboard_v42_prod.html.
Run from: Production/tools/  OR project root.
"""
import sys
from pathlib import Path

# Resolve paths
_HERE = Path(__file__).parent
_EVENT_DIR = _HERE.parent / "Event_1"
SRC = _EVENT_DIR / "storyboard_v41_prod.html"
DST = _EVENT_DIR / "storyboard_v42_prod.html"

if not SRC.exists():
    print(f"ERROR: source not found: {SRC}")
    sys.exit(1)

html = SRC.read_text(encoding="utf-8", errors="replace")
b64_before = html.count("data:image/")
print(f"Source: {SRC} ({len(html)//1024} KB, {b64_before} base64 blobs)")

# ---------------------------------------------------------------------------
# Change 1: CSS — insert after .bg-beat-card.drag-over rule
# ---------------------------------------------------------------------------
CSS_ANCHOR = ".bg-beat-card.drag-over{border-color:#52b788;box-shadow:0 0 10px rgba(82,183,136,.3)}"
NEW_CSS = (
    CSS_ANCHOR
    + ".bg-ref-row{display:flex;gap:6px;margin-bottom:8px}"
    ".bg-ref-slot{flex:1;min-height:72px;border:1px dashed #555;border-radius:6px;"
    "background:#0f1a2e;position:relative;display:flex;align-items:center;"
    "justify-content:center;font-size:11px;color:#8aa;overflow:hidden;cursor:pointer}"
    ".bg-ref-slot.drag-over{border-color:#52b788;border-style:solid;"
    "box-shadow:0 0 8px rgba(82,183,136,.4)}"
    ".bg-ref-slot.has-ref{border-color:#52b788;border-style:solid}"
    ".bg-ref-slot img{width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0}"
    ".bg-ref-slot .bg-ref-lbl{position:relative;z-index:1;background:rgba(0,0,0,.55);"
    "padding:2px 5px;border-radius:3px;pointer-events:none}"
    ".bg-ref-slot .bg-ref-clr{position:absolute;top:2px;right:4px;z-index:2;"
    "background:rgba(0,0,0,.6);border:none;color:#f88;cursor:pointer;font-size:13px;"
    "line-height:1;padding:1px 4px;border-radius:3px}"
)
assert CSS_ANCHOR in html, "FAIL: CSS anchor not found in source HTML"
html = html.replace(CSS_ANCHOR, NEW_CSS, 1)
print("OK  Change 1: CSS added")

# ---------------------------------------------------------------------------
# Change 2: _bgUpdateBeat — add return + .then()
# ---------------------------------------------------------------------------
OLD_UPDATE = (
    "function _bgUpdateBeat(beatId, fields) {\n"
    "  var payload = Object.assign({beat_id: beatId}, fields);\n"
    "  fetch(BG_SERVER + \"/api/bg/update-beat\", {\n"
    "    method: \"POST\",\n"
    "    headers: {\"Content-Type\":\"application/json\"},\n"
    "    body: JSON.stringify(payload)\n"
    "  }).catch(function(e){ console.warn(\"[BG] update-beat error:\", e); });\n"
    "}"
)
NEW_UPDATE = (
    "function _bgUpdateBeat(beatId, fields) {\n"
    "  var payload = Object.assign({beat_id: beatId}, fields);\n"
    "  return fetch(BG_SERVER + \"/api/bg/update-beat\", {\n"
    "    method: \"POST\",\n"
    "    headers: {\"Content-Type\":\"application/json\"},\n"
    "    body: JSON.stringify(payload)\n"
    "  }).then(function(r){ return r.json(); })\n"
    "    .catch(function(e){ console.warn(\"[BG] update-beat error:\", e); return {ok:false}; });\n"
    "}"
)
assert OLD_UPDATE in html, "FAIL: _bgUpdateBeat anchor not found — check whitespace"
html = html.replace(OLD_UPDATE, NEW_UPDATE, 1)
print("OK  Change 2: _bgUpdateBeat returns promise")

# ---------------------------------------------------------------------------
# Change 3: ref slots — insert after card.appendChild(hdr); before Dialogue
# ---------------------------------------------------------------------------
SLOT_ANCHOR = "    card.appendChild(hdr);\n\n    // Dialogue \u2014 editable textarea"
REF_SLOTS_JS = (
    "    card.appendChild(hdr);\n\n"
    "    // --- Reference image slots (Char Ref + BG Ref) ---\n"
    "    var refRow = document.createElement(\"div\");\n"
    "    refRow.className = \"bg-ref-row\";\n\n"
    "    function _makeRefSlot(bid, field, label, currentPath) {\n"
    "      var sl = document.createElement(\"div\");\n"
    "      sl.className = \"bg-ref-slot\" + (currentPath ? \" has-ref\" : \"\");\n"
    "      sl.dataset.beatId = bid;\n"
    "      sl.dataset.field = field;\n"
    "      var lbl = document.createElement(\"span\");\n"
    "      lbl.className = \"bg-ref-lbl\";\n"
    "      lbl.textContent = currentPath ? label + \" \\u2713\" : label;\n"
    "      sl.appendChild(lbl);\n"
    "      if (currentPath) {\n"
    "        sl.title = currentPath.split(/[\\/\\\\]/).pop();\n"
    "        var found = null;\n"
    "        for (var _i = 0; _i < MN_LIB_DATA.length; _i++) {\n"
    "          if (MN_LIB_DATA[_i].abs_path === currentPath) { found = MN_LIB_DATA[_i]; break; }\n"
    "        }\n"
    "        if (found && found.thumb_b64) {\n"
    "          var timg = document.createElement(\"img\");\n"
    "          timg.src = found.thumb_b64;\n"
    "          sl.insertBefore(timg, lbl);\n"
    "        }\n"
    "        var clr = document.createElement(\"button\");\n"
    "        clr.className = \"bg-ref-clr\";\n"
    "        clr.textContent = \"\\u00d7\";\n"
    "        clr.title = \"Clear \" + label;\n"
    "        clr.onclick = (function(b, f) {\n"
    "          return function(e) {\n"
    "            e.stopPropagation(); e.preventDefault();\n"
    "            var pld = {}; pld[f] = null;\n"
    "            _bgUpdateBeat(b, pld);\n"
    "            var bt = (BG_BEATS || []).find(function(x){ return x.beat_id === b; });\n"
    "            if (bt) bt[f] = null;\n"
    "            _bgRenderBeats(BG_BEATS);\n"
    "          };\n"
    "        })(bid, field);\n"
    "        sl.appendChild(clr);\n"
    "      }\n"
    "      sl.addEventListener(\"dragover\", function(e) {\n"
    "        if (!_mnLibHasKey(e)) return;\n"
    "        e.preventDefault(); e.stopPropagation();\n"
    "        sl.classList.add(\"drag-over\");\n"
    "      });\n"
    "      sl.addEventListener(\"dragleave\", function(e) {\n"
    "        if (!sl.contains(e.relatedTarget)) sl.classList.remove(\"drag-over\");\n"
    "      });\n"
    "      sl.addEventListener(\"drop\", function(e) {\n"
    "        e.preventDefault(); e.stopPropagation();\n"
    "        sl.classList.remove(\"drag-over\");\n"
    "        var key = e.dataTransfer.getData(\"mn-lib-key\");\n"
    "        if (!key) return;\n"
    "        var item = null;\n"
    "        for (var _j = 0; _j < MN_LIB_DATA.length; _j++) {\n"
    "          if (MN_LIB_DATA[_j].key === key) { item = MN_LIB_DATA[_j]; break; }\n"
    "        }\n"
    "        if (!item || !item.abs_path) return;\n"
    "        var apath = item.abs_path;\n"
    "        var fld = sl.dataset.field;\n"
    "        var beatId = sl.dataset.beatId;\n"
    "        var pld = {}; pld[fld] = apath;\n"
    "        _bgUpdateBeat(beatId, pld).then(function(r) {\n"
    "          if (!r || r.ok === false) {\n"
    "            console.error(\"[BG] ref write failed:\", r);\n"
    "            sl.style.borderColor = \"#f44\";\n"
    "            return;\n"
    "          }\n"
    "          var bt = (BG_BEATS || []).find(function(x){ return x.beat_id === beatId; });\n"
    "          if (bt) bt[fld] = apath;\n"
    "          _bgRenderBeats(BG_BEATS);\n"
    "        });\n"
    "      });\n"
    "      return sl;\n"
    "    }\n\n"
    "    refRow.appendChild(_makeRefSlot(beat.beat_id, \"reference_image\", \"Char Ref\", beat.reference_image || null));\n"
    "    refRow.appendChild(_makeRefSlot(beat.beat_id, \"bg_ref_image\",    \"BG Ref\",   beat.bg_ref_image   || null));\n"
    "    card.appendChild(refRow);\n"
    "    // --- end reference image slots ---\n\n"
    "    // Dialogue \u2014 editable textarea"
)
assert SLOT_ANCHOR in html, "FAIL: slot anchor not found — check em-dash encoding"
html = html.replace(SLOT_ANCHOR, REF_SLOTS_JS, 1)
print("OK  Change 3: ref slots injected")

# ---------------------------------------------------------------------------
# Safety: verify base64 count unchanged
# ---------------------------------------------------------------------------
b64_after = html.count("data:image/")
assert b64_after == b64_before, f"FAIL: base64 count changed {b64_before} -> {b64_after}"
print(f"OK  base64 blobs: {b64_after} (unchanged)")

# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
DST.write_text(html, encoding="utf-8")
print(f"OK  Written: {DST.name} ({DST.stat().st_size // 1024} KB)")
print("DONE — open storyboard_v42_prod.html in browser to verify slots render.")
print("Keep storyboard_v41_prod.html until Kim confirms v42 is good.")

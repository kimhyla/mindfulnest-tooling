#!/usr/bin/env python3
"""
patch_storyboard_library_v41.py  — Path B patch: v40 → v41
Injects the persistent library sidebar (CSS + HTML + JS) into an existing
storyboard without touching any base64 image data.

Usage:
    python3 patch_storyboard_library_v41.py [--input storyboard_v40.html] [--output storyboard_v41.html]

Defaults:
    --input   Production/Event_1/storyboard_v40_prod.html
    --output  Production/Event_1/storyboard_v41_prod.html

Path B compliance:
  - Only patches </style>, HTML before <script>, and </script></body></html>
  - SHA256-verifies every data:image/ URI before and after; aborts if any change
  - Idempotent: if mn-lib-sidebar is already present, exits 0 with "already patched" msg
"""
from __future__ import annotations
import argparse
import hashlib
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_IN  = _HERE.parent / "Event_1" / "storyboard_v40_prod.html"
_DEFAULT_OUT = _HERE.parent / "Event_1" / "storyboard_v41_prod.html"


# ---------------------------------------------------------------------------
# CSS payload (same as build_storyboard.py append_extras_tabs tab_css addition)
# ---------------------------------------------------------------------------
_LIB_CSS = """
/* ── Persistent Library Sidebar (mn-context library-panel) ── */
#mn-lib-sidebar{position:fixed;top:0;right:0;width:260px;height:100vh;background:#0f1722;border-left:1px solid #333;display:flex;flex-direction:row;z-index:1000;transform:translateX(calc(100% - 36px));transition:transform .2s}
#mn-lib-sidebar.open{transform:translateX(0)}
#mn-lib-toggle{writing-mode:vertical-rl;cursor:pointer;background:#4a3f6b;color:#e0c3fc;border:none;padding:10px 4px;font-size:11px;font-weight:bold;flex-shrink:0;width:36px;align-self:stretch;letter-spacing:1px}
.mn-lib-body{flex:1;overflow-y:auto;padding:8px 6px;min-width:0}
.mn-lib-section{margin-bottom:12px}
.mn-lib-section-hdr{color:#888;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:8px 0 4px;padding-bottom:3px;border-bottom:1px solid #222}
.mn-lib-grid{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.mn-lib-item{width:100px;height:75px;border:2px solid #333;border-radius:4px;cursor:grab;overflow:hidden;position:relative;flex-shrink:0}
.mn-lib-item img{width:100%;height:100%;object-fit:cover;display:block}
.mn-lib-item:hover{border-color:#52b788}
.mn-lib-item[data-tier="source"]{border-color:#4a6faa}
.mn-lib-item[data-tier="character_master"]{border-color:#7a5a3a}
.mn-lib-item.dragging{opacity:.45}
.mn-lib-tier-badge{position:absolute;bottom:2px;left:2px;font-size:8px;padding:1px 3px;border-radius:2px;background:rgba(0,0,0,.75);color:#aaa;pointer-events:none}
.mn-lib-upload-btn{display:block;width:100%;background:#141e14;color:#6f6;border:1px dashed #2a4a2a;padding:4px;border-radius:4px;cursor:pointer;font-size:10px;text-align:center;box-sizing:border-box}
.mn-lib-upload-input{display:none}
.mn-lib-empty{color:#555;font-size:11px;font-style:italic;padding:4px 0}
.mn-lib-refresh{background:none;border:none;color:#666;cursor:pointer;font-size:11px;padding:0;margin-left:auto}
#mn-lib-sidebar .bg-beat-card.drag-over,.lr.drag-over-lib{outline:2px dashed #52b788}
"""

# ---------------------------------------------------------------------------
# HTML payload — the sidebar div (no images, no base64)
# ---------------------------------------------------------------------------
_LIB_HTML = """
<div id="mn-lib-sidebar">
<button id="mn-lib-toggle" onclick="_mnLibToggle()">&#x2261; Library</button>
<div class="mn-lib-body">
  <div class="mn-lib-section">
    <div class="mn-lib-section-hdr">Source Images</div>
    <div class="mn-lib-grid" id="mn-lib-grid-source"></div>
    <div class="mn-lib-empty" id="mn-lib-empty-source">No source images yet.</div>
  </div>
  <div class="mn-lib-section">
    <div class="mn-lib-section-hdr" style="display:flex;align-items:center">Ready Images <button class="mn-lib-refresh" onclick="_mnLibFetch()" title="Refresh">&#x21bb;</button></div>
    <div class="mn-lib-grid" id="mn-lib-grid-cropped"></div>
    <div class="mn-lib-empty" id="mn-lib-empty-cropped">No crops yet.</div>
  </div>
  <div class="mn-lib-section">
    <div class="mn-lib-section-hdr">Character Masters</div>
    <div class="mn-lib-grid" id="mn-lib-grid-character_master"></div>
    <div class="mn-lib-empty" id="mn-lib-empty-character_master">No masters yet.</div>
  </div>
  <label class="mn-lib-upload-btn">&#x2B06; Upload Image<input class="mn-lib-upload-input" type="file" accept="image/*" onchange="_mnLibUpload(this)"></label>
</div>
</div>
"""

# ---------------------------------------------------------------------------
# JS payload — wrapped in idempotency guard (identical to builder injection)
# ---------------------------------------------------------------------------
_LIB_JS = r"""
// ====================================================================
// PERSISTENT LIBRARY SIDEBAR  (idempotency guard — no-op on rebuild)
// ====================================================================
if (typeof _bgLibraryInited === "undefined") {
var _bgLibraryInited = true;
var MN_LIB_DATA = [];

function _mnLibToggle() {
  var s = document.getElementById('mn-lib-sidebar');
  if (s) {
    s.classList.toggle('open');
    if (s.classList.contains('open')) _mnLibFetch();
  }
}

function _mnLibFetch() {
  fetch(BG_SERVER + '/api/cr/library')
    .then(function(r){ return r.json(); })
    .then(function(d) { MN_LIB_DATA = d.images || []; _mnLibRender(); })
    .catch(function(e){ console.warn('[MNLib] fetch error:', e); });
}

function _mnLibRender() {
  ['source','cropped','character_master'].forEach(function(tier) {
    var gid = 'mn-lib-grid-' + tier;
    var eid = 'mn-lib-empty-' + tier;
    var grid = document.getElementById(gid);
    var empty = document.getElementById(eid);
    if (!grid) return;
    grid.innerHTML = '';
    var items = MN_LIB_DATA.filter(function(x){ return x.tier === tier; });
    if (!items.length) { if (empty) empty.style.display = 'block'; return; }
    if (empty) empty.style.display = 'none';
    items.forEach(function(item) {
      var el = document.createElement('div');
      el.className = 'mn-lib-item';
      el.setAttribute('data-tier', item.tier);
      el.setAttribute('data-key', item.key);
      el.setAttribute('draggable', 'true');
      el.title = item.filename;
      var img = document.createElement('img');
      img.src = item.thumb_b64;
      img.alt = item.filename;
      el.appendChild(img);
      var badge = document.createElement('span');
      badge.className = 'mn-lib-tier-badge';
      badge.textContent = tier === 'character_master' ? 'master' : tier;
      el.appendChild(badge);
      el.addEventListener('dragstart', function(e) {
        el.classList.add('dragging');
        e.dataTransfer.setData('mn-lib-key', item.key); // key only — full data looked up in MN_LIB_DATA on drop
        e.dataTransfer.effectAllowed = 'copy';
      });
      el.addEventListener('dragend', function(){ el.classList.remove('dragging'); });
      grid.appendChild(el);
    });
  });
}

function _mnLibHasKey(e) {
  try {
    var t = e.dataTransfer.types;
    return t.indexOf ? t.indexOf('mn-lib-key') !== -1 : t.includes('mn-lib-key');
  } catch(ex){ return false; }
}

document.addEventListener('dragover', function(e) {
  if (_mnLibHasKey(e)) e.preventDefault();
});

document.addEventListener('dragenter', function(e) {
  if (!_mnLibHasKey(e)) return;
  var card = e.target && e.target.closest && e.target.closest('.bg-beat-card');
  if (card) card.classList.add('drag-over');
  var lr = e.target && e.target.closest && e.target.closest('.lr');
  if (lr) lr.classList.add('drag-over-lib');
});

document.addEventListener('dragleave', function(e) {
  var card = e.target && e.target.closest && e.target.closest('.bg-beat-card');
  if (card && !card.contains(e.relatedTarget)) card.classList.remove('drag-over');
  var lr = e.target && e.target.closest && e.target.closest('.lr');
  if (lr && !lr.contains(e.relatedTarget)) lr.classList.remove('drag-over-lib');
});

// Capture-phase: prevent textareas/inputs from accepting library drops as text
document.addEventListener('drop', function(e) {
  if (!_mnLibHasKey(e)) return;
  var tag = e.target && e.target.tagName;
  if (tag === 'TEXTAREA' || tag === 'INPUT' || (e.target && e.target.contentEditable === 'true')) {
    e.preventDefault();
  }
}, true);

document.addEventListener('drop', function(e) {
  var key = e.dataTransfer && e.dataTransfer.getData('mn-lib-key');
  if (!key) return;
  // Look up data from in-memory cache — NOT from dataTransfer (avoids textarea text-drop bug)
  var libItem = null;
  for (var i = 0; i < MN_LIB_DATA.length; i++) { if (MN_LIB_DATA[i].key === key) { libItem = MN_LIB_DATA[i]; break; } }
  if (!libItem) return;
  var b64   = libItem.gallery_b64;
  var fname = libItem.filename;
  var apath = libItem.abs_path || '';

  // Drop on .bg-beat-card → set reference_image for beat
  var card = e.target.closest && e.target.closest('.bg-beat-card');
  if (card) {
    e.preventDefault();
    card.classList.remove('drag-over');
    var bid = card.id ? card.id.replace(/^bg-card-/, '') : null;
    if (!bid) return;
    _bgUpdateBeat(bid, {reference_image: apath});
    var slot0 = document.getElementById('bg-opt-' + bid + '-0');
    if (slot0 && b64) {
      var eimg = slot0.querySelector('img');
      if (!eimg) { eimg = document.createElement('img'); slot0.insertBefore(eimg, slot0.firstChild); }
      eimg.src = b64;
      slot0.title = 'Ref: ' + fname;
    }
    return;
  }

  // Drop on .lr (Storyboard row) → inject into gallery + assign
  var lr = e.target.closest && e.target.closest('.lr');
  if (lr) {
    e.preventDefault();
    lr.classList.remove('drag-over-lib');
    if (b64 && key) {
      _injectImage(key, fname, b64, b64);
      var sel = lr.querySelector('select');
      if (sel) {
        var found = false;
        for (var i = 0; i < sel.options.length; i++) { if (sel.options[i].value === key) { found = true; break; } }
        if (!found) { var o = document.createElement('option'); o.value = key; o.textContent = fname; sel.appendChild(o); }
        sel.value = key;
        sel.dispatchEvent(new Event('change'));
      }
    }
    return;
  }

  // Drop on #cr-canvas-wrap → load into Cropper
  var crw = e.target.closest && e.target.closest('#cr-canvas-wrap');
  if (crw) {
    e.preventDefault();
    if (!b64) return;
    CR_BEAT_ID = null;
    CR_SRC_KEY = key;
    var img2 = new Image();
    img2.onload = function() {
      CR_IMG = img2;
      var cw = Math.min(img2.width, img2.height * 4/3);
      var ch = cw * 3/4;
      CR_CROP_BOX = {x:(img2.width-cw)/2, y:(img2.height-ch)/2, w:cw, h:ch};
      _bgSwitchTab('cr', null);
      _crDraw();
      var info = document.getElementById('cr-crop-info');
      if (info) info.textContent = 'Image: ' + img2.width + '\u00d7' + img2.height + 'px  Crop: 4:3';
      var saveBtn = document.getElementById('cr-save-btn');
      if (saveBtn) saveBtn.disabled = false;
    };
    img2.src = b64;
    return;
  }
});

function _mnLibUpload(input) {
  if (!input.files || !input.files[0]) return;
  var file = input.files[0];
  var reader = new FileReader();
  reader.onload = function() {
    var b64 = reader.result.split(',')[1];
    fetch(BG_SERVER + '/api/cr/upload', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({filename: file.name, image_b64: b64, tier: 'source'})
    }).then(function(r){ return r.json(); })
    .then(function(d){ if (d.ok) _mnLibFetch(); else alert('Upload failed: ' + (d.error || 'unknown')); })
    .catch(function(ex){ alert('Upload error: ' + ex); });
  };
  reader.readAsDataURL(file);
  input.value = '';
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _mnLibFetch);
} else {
  _mnLibFetch();
}
} // end _bgLibraryInited guard
"""


def _extract_b64_shas(html: str) -> dict[str, str]:
    """Return {sha256_hex: data_uri_prefix} for every data:image/ URI."""
    shas = {}
    for m in re.finditer(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', html):
        raw = m.group(1)
        sha = hashlib.sha256(raw.encode()).hexdigest()
        shas[sha] = raw[:20]  # prefix for diagnostics
    return shas


def patch(input_path: Path, output_path: Path) -> None:
    html = input_path.read_text(encoding="utf-8")

    # --- idempotency check ---
    if 'id="mn-lib-sidebar"' in html:
        print(f"[patch] Already patched — mn-lib-sidebar found in {input_path.name}. Skipping.")
        if input_path != output_path:
            output_path.write_text(html, encoding="utf-8")
            print(f"[patch] Copied as {output_path.name} unchanged.")
        return

    # --- SHA snapshot before ---
    before_shas = _extract_b64_shas(html)
    print(f"[patch] Input: {input_path.name}  ({len(html)//1024} KB, {len(before_shas)} base64 blobs)")

    # 1. CSS — inject before </style>
    if "</style>" not in html:
        print("[patch] ERROR: </style> anchor not found — cannot inject CSS", file=sys.stderr)
        sys.exit(1)
    html = html.replace("</style>", _LIB_CSS + "\n</style>", 1)

    # 2. HTML sidebar — inject before first <script> tag
    script_idx = html.find("<script>")
    if script_idx == -1:
        print("[patch] ERROR: <script> anchor not found — cannot inject sidebar HTML", file=sys.stderr)
        sys.exit(1)
    html = html[:script_idx] + _LIB_HTML + "\n" + html[script_idx:]

    # 3. JS — inject before the final </script> (robust to any whitespace/newline layout)
    idx = html.rfind("</script>")
    if idx != -1:
        html = html[:idx] + _LIB_JS + "\n" + html[idx:]
    elif "</body>" in html:
        # No existing <script> block — must wrap our own
        html = html.replace("</body>", "<script>\n" + _LIB_JS + "\n</script>\n</body>", 1)
    else:
        print("[patch] ERROR: neither </script> nor </body> found — cannot inject JS", file=sys.stderr)
        sys.exit(1)

    # --- SHA verification after ---
    after_shas = _extract_b64_shas(html)
    missing = set(before_shas) - set(after_shas)
    added   = set(after_shas) - set(before_shas)
    if missing:
        print(f"[patch] ABORT: {len(missing)} base64 blobs lost after patch — data corruption detected!", file=sys.stderr)
        for sha in list(missing)[:3]:
            print(f"  missing sha={sha}  prefix={before_shas[sha]}", file=sys.stderr)
        sys.exit(1)
    if added:
        # We injected base64 thumbnails from the library? Shouldn't happen — _LIB_HTML has none.
        print(f"[patch] WARNING: {len(added)} unexpected base64 blobs added (should be 0 for Path B).")

    output_path.write_text(html, encoding="utf-8")
    print(f"[patch] Output: {output_path.name}  ({len(html)//1024} KB)")
    print(f"[patch] SHA check: {len(before_shas)} blobs before = {len(after_shas) - len(added)} blobs after OK")
    print(f"[patch] Done. Open {output_path.name} in browser to verify library sidebar.")


def main():
    p = argparse.ArgumentParser(description="Path B: inject library sidebar into storyboard")
    p.add_argument("--input",  default=str(_DEFAULT_IN),  help="Source storyboard HTML")
    p.add_argument("--output", default=str(_DEFAULT_OUT), help="Output storyboard HTML")
    args = p.parse_args()
    patch(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()

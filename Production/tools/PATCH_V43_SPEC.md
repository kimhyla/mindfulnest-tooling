# `patch_storyboard_v43.py` — Technical Specification

**Status:** Spec only. Engineer writes the patch script from this document.
**Source:** `Production/Event_1/storyboard_v42_prod.html` (5,369 lines)
**Output:** `Production/Event_1/storyboard_v43_prod.html`
**Companion change:** `Production/tools/production_server.py::_build_storyboard_nav_html` (Section B)

---

## 0. Strategy Summary

The v42 architecture has TWO layers of library JS:

1. **Page JS** (lines 5172–5366 in `storyboard_v42_prod.html`, inside the `_bgLibraryInited` IIFE) — defines `_mnLibFetch`, `_mnLibRender`, `_mnLibUpload`, `MN_LIB_DATA`, and the document-level dragover/dragenter/dragleave/drop handlers.
2. **Nav-injection JS** (lines 6381–6550 in `production_server.py::_build_storyboard_nav_html`) — runs AFTER page JS and overrides `window._mnLibRender`, `window._mnLibUpload`, attaches a capture-phase drop handler, and runs a third library refetch via `setTimeout(_navLibRefresh, 400)`.

v43 collapses these into ONE layer in the HTML by:
- Baking the fixes the nav override added (filename label, `draggable=false`, full-res fetch) directly into page JS.
- Replacing the corrupting drag-time sidebar hide (CSS `transition` while element is the drag source) with an instant, transition-free hide on `dragstart` plus an instant restore on `dragend`.
- Stripping ALL library JS from the nav injection (Section B), leaving ONLY the storyboard switcher UI (select / Load / Refresh).

After v43 ships, the page is the single source of truth for library behavior. The nav contributes only the switcher dropdown.

---

## A. Changes to `storyboard_v42_prod.html`

### A0. Read-time setup

```python
SRC = _EVENT_DIR / "storyboard_v42_prod.html"
DST = _EVENT_DIR / "storyboard_v43_prod.html"
html = SRC.read_text(encoding="utf-8", errors="replace")
b64_before = html.count("data:image/")
```

Apply changes A1 → A7 in order. Each change does ONE `assert anchor in html` then one `html = html.replace(old, new, 1)`. After all changes, verify `html.count("data:image/") == b64_before` and write DST.

---

### A1. CSS — instant sidebar hide during drag (no transition)

**Why:** Root cause #1 + #5. The nav override removes `.open` from `#mn-lib-sidebar` on `dragstart`. CSS at line 142 has `transition:transform .2s` on the sidebar — so the element animates offscreen WHILE it is the drag source. Chromium reads the post-transition position and the drag visual collapses onto an empty area. The fix: add a `data-dragging="1"` attribute on `dragstart` that BOTH (a) hides the sidebar via `visibility:hidden` (no animation) AND (b) suppresses the transition. On `dragend` we remove the attribute; the sidebar reappears instantly.

We also add `.dragging` opacity stays from line 154 — leave alone.

**Anchor (find — exact, line 142):**

```
#mn-lib-sidebar{position:fixed;top:0;right:0;width:260px;height:100vh;background:#0f1722;border-left:1px solid #333;display:flex;flex-direction:row;z-index:1000;transform:translateX(calc(100% - 36px));transition:transform .2s}
#mn-lib-sidebar.open{transform:translateX(0)}
```

**Replace with:**

```
#mn-lib-sidebar{position:fixed;top:0;right:0;width:260px;height:100vh;background:#0f1722;border-left:1px solid #333;display:flex;flex-direction:row;z-index:1000;transform:translateX(calc(100% - 36px));transition:transform .2s}
#mn-lib-sidebar.open{transform:translateX(0)}
#mn-lib-sidebar[data-dragging="1"]{transition:none!important;visibility:hidden!important}
```

**Risk:** Anchor is a single 2-line block; very stable (CSS hand-authored, not generated). If ever changed (e.g., width tweak), the assert fires loudly. Replacement adds ONE rule with `!important` to override `.open` — safe.

---

### A2. Page `_mnLibRender` — bake in `draggable=false`, filename label, transition-free sidebar hide

**Why:** Root causes #1, #5, #6. Today the page renders without `draggable=false` on `<img>` (so Chrome fires its OWN image-drag, stealing `mn-lib-key`) and without filename labels (Kim can't tell guide-bird thumbs apart). The nav override fixed both, plus auto-hid the sidebar with a CSS-transition path that broke the drag. v43 bakes the filename label + `draggable=false` into the page render and uses the new `data-dragging` attribute for an instant, transition-free hide.

**Anchor (find — exact, lines 5199–5234, the entire page `_mnLibRender` body):**

```
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
```

**Replace with (exact):**

```
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
      img.setAttribute('draggable', 'false'); // prevent native image drag from stealing dataTransfer
      el.appendChild(img);
      var badge = document.createElement('span');
      badge.className = 'mn-lib-tier-badge';
      badge.textContent = tier === 'character_master' ? 'master' : tier;
      el.appendChild(badge);
      // Filename label so Kim can distinguish near-identical guide-bird thumbs
      var fnLbl = document.createElement('span');
      fnLbl.style.cssText = 'position:absolute;bottom:0;left:0;right:0;font-size:8px;'+
        'padding:2px 3px;background:rgba(0,0,0,.75);color:#ddd;'+
        'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none;';
      fnLbl.textContent = item.key;
      el.appendChild(fnLbl);
      el.addEventListener('dragstart', function(e) {
        el.classList.add('dragging');
        e.dataTransfer.setData('mn-lib-key', item.key);
        e.dataTransfer.effectAllowed = 'copy';
        // Hide sidebar instantly (no transition) so it can't overlap drop targets
        // and can't corrupt the drag session by animating offscreen.
        var sb = document.getElementById('mn-lib-sidebar');
        if (sb) {
          sb.setAttribute('data-lib-was-open', sb.classList.contains('open') ? '1' : '0');
          sb.setAttribute('data-dragging', '1');
        }
      });
      el.addEventListener('dragend', function(){
        el.classList.remove('dragging');
        var sb = document.getElementById('mn-lib-sidebar');
        if (sb) {
          sb.removeAttribute('data-dragging');
          // 'data-lib-was-open' is purely advisory now — sidebar visibility is
          // governed by .open class, which we never toggled. No restore needed.
          sb.removeAttribute('data-lib-was-open');
        }
      });
      grid.appendChild(el);
    });
  });
}
```

**Risk:** Anchor is a 36-line literal — must match whitespace/indentation exactly. Mitigation: assert + `replace(..., 1)`. If indentation in the source ever shifts (e.g., a future patch reformats), assert fires; engineer must re-anchor on a smaller unique substring inside the function body. Recommend the assert message read: `"FAIL: page _mnLibRender anchor not found — check indentation drift"`.

---

### A3. Page `_mnLibFetch` — already cache-busted; leave alone

**Decision:** No change required. Inspection of line 5188 shows the page already does `fetch(BG_SERVER + '/api/cr/library?_t=' + Date.now())`. The cache-buster is in place; `Cache-Control: no-store` on the server makes this redundant but harmless. **Skip this change.**

(This was listed in the prompt as Change 2 but the assumption that the page was non-cache-busted is wrong as of v42. Documenting the no-op here for traceability.)

---

### A4. Page `_mnLibUpload` — already cache-busted via `_mnLibFetch`; leave alone

**Decision:** No change required. Page `_mnLibUpload` (lines 5344–5360) calls `_mnLibFetch()` after upload, which is cache-busted (A3). The nav override only existed because the OLD page version was non-cache-busted; v42 already fixed this. **Skip this change.**

---

### A5. Global drop handler — `.lr` keeps thumbnail; `#cr-canvas-wrap` switches to async full-res fetch

**Why:** Root causes #3 + #4.
- `.lr` storyboard rows: the gallery is a thumbnail strip. `gallery_b64` (thumbnail, ~200×150) is sufficient and matches the existing storyboard gallery image scale. Keep current behavior — synchronous, no fetch needed.
- `#cr-canvas-wrap`: the Cropper REQUIRES full-resolution pixels (Rule 6 mandates ≥600 px shortest side; thumbnails are 200×150). Must switch to async `/api/cr/full?abs_path=...` fetch.

**Anchor (find — exact, lines 5319–5341, the Cropper drop branch):**

```
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
```

**Replace with (exact):**

```
  // Drop on #cr-canvas-wrap → fetch full-res then load into Cropper
  var crw = e.target.closest && e.target.closest('#cr-canvas-wrap');
  if (crw) {
    e.preventDefault();
    if (!apath) return;
    CR_BEAT_ID = null;
    CR_SRC_KEY = key;
    fetch(BG_SERVER + '/api/cr/full?abs_path=' + encodeURIComponent(apath))
      .then(function(r){ return r.json(); })
      .then(function(d) {
        if (!d.ok || !d.data_uri) {
          console.error('[Cropper drop] full-res fetch failed:', d);
          return;
        }
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
        img2.src = d.data_uri;
      })
      .catch(function(ex){ console.warn('[Cropper drop] fetch error:', ex); });
    return;
  }
```

**`.lr` branch (lines 5300–5317):** No change. `gallery_b64` is the thumbnail and is appropriate for the storyboard gallery preview. Keep as-is.

**Risk:** The Cropper anchor is unique (only one `Drop on #cr-canvas-wrap` comment in the file). The replacement adds an async layer — if `/api/cr/full` 404s or the abs_path safety check fails, the Cropper silently does nothing instead of loading a broken thumbnail. Acceptable failure mode; logs a `console.error`.

---

### A6. `BG_SERVER` reference — confirmed correct, no change

**Decision:** Page JS at line 3957 has `var BG_SERVER = "http://localhost:5111"` hardcoded. Server runs at `localhost:5111` per the brief. The new Cropper async fetch (A5) uses `BG_SERVER`, which resolves to the same origin. The nav override's `window.location.origin` was equivalent. **No change required.** (If Kim ever proxies behind a different host, change this constant in one place — page line 3957.)

---

### A7. `_makeRefSlot` thumbnail lookup — already correct, no change

**Why:** v42's `_makeRefSlot` (injected by `patch_storyboard_v42.py`) does `MN_LIB_DATA[_i].abs_path === currentPath` to locate the thumb. Since:
1. `currentPath` comes from `beat.reference_image` (an `abs_path` written by `_bgUpdateBeat`), and
2. The library API at `production_server.py:4793` populates `abs_path: fp` for every item,

the lookup matches by exact-string equality. After a successful drop the page calls `_bgRenderBeats(BG_BEATS)` which re-runs `_makeRefSlot` — at that point `MN_LIB_DATA` is already populated (the library loaded at page-init), so the thumbnail renders. **No change required.**

**Edge case to flag (NOT fixed in v43):** If a user drops a freshly-uploaded image, `MN_LIB_DATA` may not yet contain it because library refresh and beat-update race. The slot would render label-only until the next page refresh. Out of scope for v43 — fix later by calling `_mnLibFetch()` inside the ref-slot drop handler before `_bgRenderBeats`.

---

## B. Server changes — `production_server.py::_build_storyboard_nav_html`

Strip everything except the storyboard switcher UI. The library JS layer is now fully owned by the HTML.

### B1. Remove the entire second `<script>` block

In `production_server.py` lines 6381–6551 (the block beginning with `<script>\n/* Nav-injected library fix —` and ending with `</script>"""`), delete the WHOLE block.

### B2. Final shape of `_build_storyboard_nav_html` return value

After the change, the method's f-string returns ONLY:

1. The `<style>` block (lines 6313–6326) — KEEP.
2. The active-stem `<script>` (line 6327) — KEEP.
3. The `<div id="sb-nav-bar">` (lines 6328–6334) — KEEP.
4. The first `<script>` block that defines `loadList`, the Load button handler, and the Refresh button handler (lines 6335–6380) — KEEP.

The trailing `</script>` of step 4 becomes the final character of the returned string.

### B3. Reference replacement (drop-in for the engineer)

Replace `_build_storyboard_nav_html`'s body with exactly the f-string from line 6312 up to and including line 6380's `</script>`, plus the closing `"""`. Everything from line 6381 (`<script>` for nav-injected library fix) through line 6551 is deleted.

---

## C. Patch script structure — `patch_storyboard_v43.py`

```python
#!/usr/bin/env python3
"""
patch_storyboard_v43.py — collapse nav-injection layer into HTML.
Reads storyboard_v42_prod.html, applies A1/A2/A5, writes storyboard_v43_prod.html.
A3, A4, A6, A7 are no-ops (verified safe in v42 — see PATCH_V43_SPEC.md).
Server-side strip of nav-injection JS (Section B) is a SEPARATE manual edit
to production_server.py — not done by this script.

Run from: Production/tools/  OR project root.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_EVENT_DIR = _HERE.parent / "Event_1"
SRC = _EVENT_DIR / "storyboard_v42_prod.html"
DST = _EVENT_DIR / "storyboard_v43_prod.html"

if not SRC.exists():
    print(f"ERROR: source not found: {SRC}")
    sys.exit(1)

html = SRC.read_text(encoding="utf-8", errors="replace")
b64_before = html.count("data:image/")
print(f"Source: {SRC.name} ({len(html)//1024} KB, {b64_before} base64 blobs)")

# A1 — CSS: instant transition-free hide during drag
A1_OLD = "<exact 2-line block from spec A1>"
A1_NEW = "<exact 3-line block from spec A1>"
assert A1_OLD in html, "FAIL A1: sidebar CSS anchor not found"
html = html.replace(A1_OLD, A1_NEW, 1)
print("OK  A1: sidebar CSS — instant-hide rule added")

# A2 — page _mnLibRender: bake in label + draggable=false + transition-free hide hooks
A2_OLD = "<exact 36-line _mnLibRender body from spec A2>"
A2_NEW = "<exact replacement from spec A2>"
assert A2_OLD in html, "FAIL A2: page _mnLibRender anchor not found — check indentation drift"
html = html.replace(A2_OLD, A2_NEW, 1)
print("OK  A2: _mnLibRender — label + draggable=false + sidebar hooks")

# A5 — Cropper drop branch: switch to async /api/cr/full
A5_OLD = "<exact Cropper drop branch from spec A5>"
A5_NEW = "<exact replacement from spec A5>"
assert A5_OLD in html, "FAIL A5: Cropper drop branch anchor not found"
html = html.replace(A5_OLD, A5_NEW, 1)
print("OK  A5: Cropper drop now fetches full-res via /api/cr/full")

# Safety: base64 count unchanged (no images touched)
b64_after = html.count("data:image/")
assert b64_after == b64_before, f"FAIL: base64 count changed {b64_before} -> {b64_after}"
print(f"OK  base64 blobs: {b64_after} (unchanged)")

DST.write_text(html, encoding="utf-8")
print(f"OK  Written: {DST.name} ({DST.stat().st_size // 1024} KB)")
print("")
print("NEXT STEPS:")
print("  1. Manually strip nav-injection library JS in production_server.py")
print("     (see PATCH_V43_SPEC.md Section B — delete lines 6381–6550).")
print("  2. Restart server.")
print("  3. Verify: Beat Generator ref slots accept drops; Cropper accepts drops")
print("     and shows full resolution; Storyboard rows still accept drops.")
print("  4. Keep storyboard_v42_prod.html until Kim confirms v43.")
```

### Order rationale

A1 → A2 → A5. A1 must run before A2 because A2's `dragstart` handler references the `data-dragging` attribute that A1's CSS makes meaningful. (Functionally either order works since neither rewrites the other's anchor; A1-first is simply easier to debug.)

### Assertions

Each anchor uses a strict `assert literal in html`. No regex; no fuzzy matching. If an assert fails, the engineer reads `PATCH_V43_SPEC.md`, finds which whitespace shifted, and re-anchors on a smaller unique substring — never bypasses the assert.

### Base64 count check

`html.count("data:image/")` before and after must be EQUAL. v43 touches zero base64 blobs. If the count changes, the patch corrupted an image — refuse to write DST.

### Success output

Five OK lines + a `NEXT STEPS` block reminding the engineer to strip Section B from `production_server.py`.

---

## D. Risk Analysis

| Change | Failure mode | Detection | Mitigation |
|---|---|---|---|
| **A1** | CSS file reformatted (selector list collapsed, whitespace different) → anchor miss | `assert` fires | Engineer re-anchors on `#mn-lib-sidebar.open{transform:translateX(0)}` (highly unique) and inserts the new rule on the next line. |
| **A1** | New `[data-dragging="1"]` rule ranks below `.open` due to specificity → sidebar reappears mid-drag | Visual: drag visual still slides offscreen | `!important` on both `transition` and `visibility` in the new rule guarantees override. Confirmed in spec. |
| **A2** | 36-line anchor whitespace drift (e.g., editor changed 2-space to 4-space, or stripped trailing whitespace) → anchor miss | `assert` fires | Re-anchor on `function _mnLibRender() {\n  ['source','cropped','character_master'].forEach(function(tier) {` (the function header, 2 lines, far less likely to drift) AND the closing `\n      grid.appendChild(el);\n    });\n  });\n}` — replace the slice between them. (Engineer judgment call; only if first attempt fails.) |
| **A2** | `data-lib-was-open` used but not restored → no functional bug today, but dead state on the DOM | Visual inspection | Spec already removes the attribute on `dragend`. Comment notes it's advisory only. |
| **A2** | `dragend` doesn't fire (e.g., drop into iframe, browser bug) → sidebar stays hidden | Sidebar invisible after a failed drop | Add a `document.addEventListener('dragend', cleanup, true)` global belt-and-suspenders cleanup that removes `data-dragging` from the sidebar regardless of source. **Recommended addition to A2** but not strictly required for v43. |
| **A5** | `/api/cr/full` returns 403 (path outside project) → Cropper drop silently does nothing | `console.error` in DevTools | Acceptable — better than loading a thumbnail and giving Kim a low-res crop she can't tell is degraded. The error log is sufficient. |
| **A5** | `apath` is empty (item missing `abs_path`) → early return | `if (!apath) return` | Spec already handles. Old code's `if (!b64) return` is replaced by the new guard. |
| **A5** | Anchor includes ASCII `→` arrow in comment — encoding hazard | `assert` fires if file re-encoded | The arrow character in line 5319 is ASCII `→` (U+2192). Engineer must paste the literal U+2192 in the Python source, NOT type `->`. Mark this in a comment near A5_OLD: `# NOTE: the arrow below is U+2192, not "->"`. |
| **B (server)** | Engineer forgets to restart the server after stripping nav JS → page still gets old nav-injected library overrides → A1/A2 changes appear to do nothing | "Browser shows v43 file but library still misbehaves" | Spec output prints `NEXT STEPS` reminder. Optional belt-and-suspenders: add a console.log at the top of page `_mnLibRender` saying `"[v43 page render]"` so DevTools confirms which layer is rendering. |
| **B (server)** | Engineer accidentally deletes the FIRST `<script>` block (storyboard switcher) instead of the second (library) | Switcher dropdown disappears from the nav bar | Spec is explicit: KEEP lines 6335–6380, DELETE lines 6381–6550. The two blocks are separated by `</script>\n<script>` on lines 6380–6381 — a single visible boundary. |
| **All** | base64 count drift (extremely unlikely — no change touches `data:image/`) | Final assert fires | Engineer rolls back DST and reads the diff. |

---

## E. Verification checklist (post-patch, before declaring v43 done)

1. `python3 patch_storyboard_v43.py` exits 0 with all OK lines.
2. `storyboard_v43_prod.html` exists; size within 5% of v42.
3. Manually edit `production_server.py` per Section B; restart server.
4. Open `http://localhost:5111` in Chrome with DevTools open.
5. Network panel: `/api/cr/library` fires ONCE on load (not three times).
6. Console: no `_mnLibRender` redefinition warnings.
7. Drag a thumbnail from the library:
   - Sidebar disappears INSTANTLY (no slide).
   - Drop on a Beat Generator ref slot → slot turns green, thumbnail renders, persists across refresh.
   - Drop on a Storyboard `.lr` row → gallery shows thumbnail, select updates.
   - Drop on the Cropper canvas → tab switches to Cropper, full-resolution image loads (verify W×H readout shows full dimensions, not 200×150).
8. Sidebar reappears instantly on `dragend` (mouse release).
9. Library thumbnails show filename label at the bottom.
10. Upload a new image via the Upload button → library refreshes once (no double-fetch).

If any step fails, roll back to v42 and diagnose before iterating.

---

## F. Out of scope for v43 (flagged for future work)

- Race between `_bgUpdateBeat` and library refresh after drop of a freshly-uploaded image (A7 edge case).
- The `.lr` thumbnail vs full-res question: confirmed thumbnail is acceptable for storyboard gallery, but if Kim later wants full-res in the gallery, the same async-fetch pattern from A5 ports over.
- Replacing `var BG_SERVER = "http://localhost:5111"` with `window.location.origin` for portability (A6).
- Failure-mode for `dragend` not firing on cross-window drops (A2 mitigation note).

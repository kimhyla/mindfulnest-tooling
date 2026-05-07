# Lessons Learned — Beat Generator Library Sidebar
## Session: April 24, 2026 (work PC)

Covers: Beat Generator library panel build, Path B storyboard patch (v40→v41), upload pipeline fixes, drag-drop bug fixes.

---

## 1. JS Injection — Use `rfind("</script>")`, Not `endswith`

**What broke:** `patch_storyboard_library_v41.py` injected JS as visible body text. The check `html.endswith("</script></body></html>")` returned False because the actual file ends with `</script>\n</body></html>` (trailing newline). The fallback inserted raw JS before `</body>` without a `<script>` wrapper.

**Fix:** Replace `endswith` with `rfind`:
```python
_idx = html.rfind("</script>")
if _idx != -1:
    html = html[:_idx] + new_js + "\n" + html[_idx:]
elif "</body>" in html:
    html = html.replace("</body>", "<script>\n" + new_js + "\n</script>\n</body>", 1)
else:
    raise RuntimeError("neither </script> nor </body> found")
```

**Applied in:** `patch_storyboard_library_v41.py` AND `build_storyboard.py` `append_extras_tabs()`.

**Rule:** Never assume exact trailing whitespace in generated HTML. Always use `rfind` for injection point location.

---

## 2. CSS Sidebar Layout — `flex-direction:row` Not `column`

**What broke:** Sidebar showed section header text ("Source Images", "Ready Images") as a visible sliver at the right edge, not a toggle button strip. Root cause: `flex-direction:column` made the toggle button span the full width on top, with 36px of the body's right side showing as the "sliver."

**Fix:** `flex-direction:row` — toggle is the leftmost 36px strip, body extends to the right. Sidebar slides out by translating right.

**Supporting CSS fixes:**
- `width:36px; align-self:stretch` on the toggle button
- `min-width:0` on the body (prevents flex overflow)
- `width:260px` total sidebar width

**Rule:** For a right-edge slide-out panel with a vertical tab strip: use `flex-direction:row`, toggle LEFT, body RIGHT, `transform:translateX(calc(100% - 36px))` to hide.

---

## 3. Upload Response — Always Include `"ok": True`

**What broke:** After fixing the missing `/api/cr/upload` route and restarting the server, uploads returned "Upload failed: unknown." JS checks `if (d.ok)` — without that field, it evaluated falsy.

**Fix in `production_server.py` `_handle_cr_upload()`:**
```python
return self._send_json(200, {
    "ok": True,   # ← this was missing
    "key": key, "filename": filename,
    "thumb_b64": gallery_b64, "gallery_b64": gallery_b64,
    "tier": tier, "abs_path": dest_path,
})
```

**Rule:** Every JSON success response that JS checks with `if (d.ok)` must explicitly include `"ok": True`. Don't assume truthiness from other fields.

---

## 4. Drag-Drop Base64 Corruption of Textarea

**What broke:** Dragging a library image onto a beat card inserted a base64 string into the dialogue textarea. Chrome's native textarea drop handler extracted `dataTransfer` data as text and inserted it.

**Root cause:** `e.dataTransfer.setData('mn-lib-b64', item.gallery_b64)` stored full base64 in the drag payload. Chrome saw it as droppable text.

**Fix — two-layer protection:**

**Layer 1 — Key-only in dataTransfer:**
```javascript
// dragstart: store only the key, never the data
e.dataTransfer.setData('mn-lib-key', item.key);
// on drop: look up data from in-memory MN_LIB_DATA
var key = e.dataTransfer.getData('mn-lib-key');
var item = MN_LIB_DATA[key];
```

**Layer 2 — Capture-phase listener blocks textarea drops:**
```javascript
document.addEventListener('drop', function(e) {
  if (!_mnLibHasKey(e)) return;
  var tag = e.target && e.target.tagName;
  if (tag === 'TEXTAREA' || tag === 'INPUT' || 
      (e.target && e.target.contentEditable === 'true')) {
    e.preventDefault();
  }
}, true);  // ← capture phase, fires before textarea's native handler
```

**Rule:** Never store large binary data in `dataTransfer`. Store a key only; look up data from in-memory store on drop. Always add a capture-phase listener when drag-drop targets coexist with textareas.

---

## 5. Idempotency Guard for Library JS

**Pattern:** `_bgLibraryInited` flag prevents double-registration of event listeners when the library JS runs on a rebuilt storyboard that already has the library natively embedded.

```javascript
if (window._bgLibraryInited) return;
window._bgLibraryInited = true;
// ... register listeners
```

**Rule:** Any JS injected via Path B that registers DOM event listeners must have an idempotency guard. Rebuilt storyboards include the same JS natively — without the guard, listeners register twice.

---

## 6. Windows cp1252 Encoding in `extract_features()`

**What broke:** `open(html_path, "r")` on Windows raises `UnicodeDecodeError` on storyboards containing non-ASCII characters (em dashes, smart quotes, etc.) because Windows defaults to cp1252.

**Fix:**
```python
open(html_path, "r", encoding="utf-8", errors="replace")
```

**Rule:** Always specify `encoding="utf-8", errors="replace"` when reading HTML files on Windows. Never rely on the platform default encoding.

---

## 7. `✓` / Unicode in Print Statements on Windows

**What broke:** `print("✓ SHA verified")` raised `UnicodeEncodeError` on Windows cp1252 console.

**Fix:** Replace Unicode symbols with ASCII equivalents in all print statements: `✓` → `OK`, `✗` → `FAIL`, `→` → `->`.

**Rule:** Production scripts running on Windows must use ASCII-only print output, or explicitly encode: `sys.stdout.buffer.write(msg.encode('utf-8'))`.

---

## 8. Server Must Be Restarted After Route Changes

**What happened:** Added `/api/cr/upload` route to `production_server.py`. First upload attempt returned 404 — old server process was still running without the new route.

**Rule:** Any time `production_server.py` is edited, kill the old process and restart before testing. Kim's workflow: stop server in terminal (Ctrl+C), restart with `python production_server.py`.

---

## 9. Dual-Landing Pattern for Path B Patches

**Pattern:** When adding a new feature via Path B patch:
1. Apply the patch to the existing HTML file (immediate use)
2. Simultaneously update `build_storyboard.py`'s `append_extras_tabs()` (so future rebuilds include it natively)
3. Idempotency guard makes Path B a no-op on rebuilt storyboards

**Why:** Without step 2, every future rebuild loses the feature and requires re-patching. With the dual-landing, the patch script becomes a one-time migration tool.

---

## 10. Beat Generator — One Reference Image Slot (Pending Fix)

**Current limitation:** Each beat card accepts only one drag-and-drop reference image. FLUX Kontext needs both a character master AND a background reference to place a character correctly in a scene.

**Workaround Kim used:** Describe the background in the FLUX prompt text field.

**Planned fix (home session):** Add a second reference slot ("BG Ref") to each beat card. Server-side: if both slots are populated, composite the two images side-by-side before sending to FLUX Kontext. FLUX handles multi-reference composites correctly.

**Affected files:** Beat Generator UI (beat card HTML in `production_server.py`), FLUX submission handler in `beat_generator.py`.

---

## 11. FLUX Prompt Field = The Generation Prompt

**Clarification for Kim:** The italic text field below the dialogue textarea in each Beat Generator card is the FLUX Kontext prompt — it goes directly to the image generation API. It should be specific: character name, pose, emotion, setting, lighting, art style. Example:

> *Chipper the blue cartoon bird, shocked expression, wide eyes, standing amid crumbling stone ruins with a glowing runestone altar, warm magical lighting, 3D animated style*

The animation dropdown (Kling / Magic Trail / Ken Burns / Static Hold) is separate — controls video animation type applied later, does not affect still generation.

---

## 12. Library Directory Structure

```
Production/beat_generator_stills/
  sources/          ← pre-crop FLUX stills + manual uploads (tier="source")
  crops/            ← Cropper output (tier="cropped")
  ../Character_Assets/  ← character masters (tier="character_master")
```

Library refresh button (↻) re-scans these directories. Upload button writes to `sources/`.

**Heartwood reference images:** `Production/Backgrounds/heartwood/`
- `heartwood_07_three_quarter_left.png` — 45-degree left angle (copied to sources/ this session)
- `heartwood_08_three_quarter_right.png` — 45-degree right angle
- `heartwood_05_high_angle.png` — overhead view
- `HERO_runestones_dormant_v1.png` — hero runestone shot

---

## Files Changed This Session

| File | Change |
|---|---|
| `Production/tools/patch_storyboard_library_v41.py` | Created — Path B patch script, v40→v41 |
| `Production/tools/build_storyboard.py` | `append_extras_tabs()`: library sidebar CSS/HTML/JS; `rfind` injection fix; key-only drag; capture-phase listener; `extract_features()` encoding fix |
| `Production/tools/production_server.py` | `_handle_cr_upload()`: added `"ok": True` to response |
| `Production/Event_1/storyboard_v41_prod.html` | Generated — 3965 KB, 22 base64 blobs preserved, library sidebar added |
| `Production/beat_generator_stills/sources/heartwood_07_three_quarter_left.png` | Copied from Backgrounds/heartwood/ for Kim to crop |

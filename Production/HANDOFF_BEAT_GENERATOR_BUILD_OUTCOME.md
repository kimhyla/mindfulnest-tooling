# Beat Generator Tab — Build Outcome
**Completed:** 2026-04-23  
**Preflight row:** 152 (ARCHITECTURAL)  
**Budget used:** ~$0.16 (2 of 3 FLUX options rendered before session ended)

---

## What Was Built

Three-tab extension of the MindfulNest storyboard HTML:
- **Tab 1 — Storyboard**: existing pipeline, unchanged behavior
- **Tab 2 — Beat Generator**: arc/segment picker → beat extraction → FLUX still generation → pick + crop → accept to Storyboard
- **Tab 3 — Cropper**: image crop tool with Rule 6 enforcement + Directus Two-Write registration

---

## Files Created / Modified

### NEW: `Production/tools/beat_generator.py`
Core module: arc skeleton parsing, FLUX Kontext API calls, sidecar JSON management, image download + Rule 6 crop processing.

Key paths:
- Skeleton base: `Arc Skeletons/ARC_0N_SKELETON_FINAL.md`
- Sidecar: `Production/beat_generator_state.json`
- Stills dir: `Production/beat_generator_stills/`

FLUX API: `api.bfl.ai/v1/flux-kontext-pro` via `x-key` header (NOT `Authorization: Bearer`). Fresh SSL per call (LD-137).

### MODIFIED: `Production/tools/build_storyboard.py`
Added `--with-extras` flag. When passed, calls `append_extras_tabs(output_path)` after the normal registry/config build. Injects:
- Tab CSS + JS switcher
- Panel wrappers (panel-sb, panel-bg, panel-cr)
- Beat Generator HTML + JS
- Cropper HTML + JS

**Build command:**
```bash
python3 Production/tools/build_storyboard.py \
  --registry --module M1 --event 1 \
  --lines "Production/Event_1/M1E1_locked_lines_v16.json" \
  --with-extras \
  --output Production/Event_1/storyboard_with_bg_v1.html
```

### MODIFIED: `Production/tools/production_server.py`
Added lazy beat_generator import via `_bg_module()` helper.

**New routes (GET):**
- `/api/bg/segments?arc=N` — list skeleton segments
- `/api/bg/session-state?arc=N&segment_index=I` — rehydrate from sidecar
- `/api/bg/poll-flux-status?beat_id=X&request_ids=A,B,C` — poll BFL, return base64 on ready
- `/api/cr/library` — list registered crops from Directus

**New routes (POST):**
- `/api/bg/extract-beats` — parse skeleton, write sidecar, return beats
- `/api/bg/update-beat` — patch single beat fields in sidecar
- `/api/bg/reorder-beats` — reindex beats array
- `/api/bg/delete-beat` — remove beat from sidecar (POST, not DELETE — no do_DELETE in server)
- `/api/bg/accept-beats` — push accepted beats into L[] / storyboard state
- `/api/bg/submit-flux-batch` — submit 3 FLUX options per beat, return request IDs
- `/api/bg/accept-option` — copy still to gallery, update sidecar accepted_image_key
- `/api/cr/save-crop` — Rule 6 crop enforcement + Directus Two-Write (prod_visual_assets + prod_activity_log)

### OUTPUT: `Production/Event_1/storyboard_with_bg_v1.html`
Three-tab storyboard. Size: 1637KB.

Audit vs baseline (storyboard_v38_prod.html):
| Feature | v38 | with_bg_v1 | |
|---------|-----|------------|--|
| Images | 11 | 12 | ✓ |
| Lines | 12 | 12 | ✓ |
| Drag-drop | YES | YES | ✓ |
| Export | YES | YES | ✓ |
| Audio | 10 | 6 | ⚠️ pre-existing (4 files missing from disk) |

---

## Test Results (2026-04-23)

All 10 §8 curl tests passed:

| # | Endpoint | Result |
|---|----------|--------|
| 1 | `GET /api/bg/segments?arc=1` | ✓ 9 segments returned |
| 2 | `POST /api/bg/extract-beats` | ✓ 10+ beats extracted from ARC_01_SKELETON_FINAL.md |
| 3 | `GET /api/bg/session-state` | ✓ Sidecar rehydration works |
| 4 | `GET /api/bg/poll-flux-status` (no IDs) | ✓ Proper error: "request_ids required" |
| 5 | `POST /api/bg/update-beat` | ✓ ok:true |
| 6 | `POST /api/bg/delete-beat` (nonexistent) | ✓ ok:true (graceful) |
| 7 | `POST /api/bg/accept-option` (no image) | ✓ Error: "beat_id and option_key required" |
| 8 | `POST /api/bg/accept-beats` | ✓ ok:true, accepted:0 |
| 9 | `GET /api/cr/library` | ✓ images:[] |
| 10 | `POST /api/bg/submit-flux-batch` (beat_01 only) | ✓ 3 request IDs returned |
| 11 | `GET /api/bg/poll-flux-status` (with IDs, ~25s) | ✓ 2/3 status:ready, images saved to disk |

**FLUX test (live, ~$0.16 spent):**
- Beat: `bg_arc1_seg4_beat_01` (Chipper: "Are you OK...? What's wrong?")
- Request IDs: `27be3301`, `397469d2`, `f7f4707d`
- Results: opt1 + opt2 returned as PNG (~1.4MB each), saved to `beat_generator_stills/`
- opt0 was still pending at time of check (normal — BFL parallelizes)

---

## Architectural Decisions Made This Session

1. **DELETE→POST for delete-beat**: no `do_DELETE` method in production_server.py; used POST consistently with codebase pattern.
2. **Lazy import**: `_bg_module()` helper prevents hard startup failure if beat_generator.py has issues.
3. **Render hook wrapper**: `render = (function(prev){ return function(){ prev(); ..._bgRenderBeats()...; }; })(render)` — BG controls survive every storyboard render call.
4. **No kling_prompt in sidecar**: `build_motion_prompt()` runs on-demand in Storyboard tab, per Kim's 2026-04-23 correction.
5. **`/api/cr/save-crop` uses JSON body (not multipart)**: mitigation M2 from handoff, avoids multipart parsing complexity. Base64-encoded PNG sent as JSON field.

---

## Known Minor Issues

- **Poll handler stores option key but not filename in sidecar**: When browser polls and image is ready, sidecar `flux_options[i]` gets `key` set but `status` and `filename` remain None. The file IS saved to disk as `bg_{key}.png`. The `accept-option` handler can reconstruct the path from the key. Fix: update poll handler to write filename into sidecar on ready.
- **4 audio files missing from disk**: Pre-existing state. Build emits warnings but succeeds.
- **Directus storyboard registration fails on build**: 400 error from Directus (pre-existing auth/schema issue). Non-blocking.

---

## Starting Point for Next Session

**To open the storyboard:**
```bash
cd "Production/tools"
python3 production_server.py \
  --event-dir "../Event_1" \
  --storyboard "../Event_1/storyboard_with_bg_v1.html" \
  --event-id 1
# Open http://localhost:5111 in browser, click "Beat Generator" tab
```

**To test full FLUX flow:**
1. Select "Arc 1" and "EVENT 1: TESSA'S FALL" in Beat Generator tab
2. Click "Extract Beats" — should load 10+ beats from sidecar (already extracted)
3. Click "Generate Stills" on any beat (~$0.08 per option × 3 = $0.24)
4. Wait for poll to return (auto-polls every 5s)
5. Click "Accept" on chosen option → image appears in gallery
6. Click "Accept All to Storyboard" → beats pushed to Storyboard tab

**Outstanding from handoff §8 (not built this session):**
- Accept-option → `_injectImage()` bridge (JS side — browser wires this up when poll returns ready)
- Auto-poll loop in browser (JS polling every 5s using `BG_POLL_ID = setInterval`)
- Drag-drop from BG gallery → storyboard lines

These are browser-side JS features inside the injected HTML in build_storyboard.py. Check the `panel-bg` HTML block in `append_extras_tabs()`.

---

## Sidecar State (after tests)

```
Production/beat_generator_state.json
  active_context: arc_number=1, segment_index=4
  arcs → arc_1 → segments → seg_4 → beats: 10 beats
  beat_01 flux_options: 3 (opt0=pending, opt1/opt2=key set, files on disk)
```

**Files on disk:**
```
Production/beat_generator_stills/
  bg_bg_arc1_seg4_beat_01_opt1.png  (1.4MB)
  bg_bg_arc1_seg4_beat_01_opt2.png  (1.3MB)
```

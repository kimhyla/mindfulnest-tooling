# Storyboard Production Pipeline — Lessons Learned
**Session Date:** April 16, 2026  
**Scope:** Cropper→Storyboard pipeline, production server, drag-drop, animation/lip sync, image handling  
**Status:** Active reference — consult before any storyboard production work

---

## 1. Server Infrastructure

### 1.1 Port Binding & Restart Failures
**Symptom:** Server fails to start on port 5111; "port still in use" errors after restart.  
**Root Cause:** `os.execv()` re-exec doesn't release the socket before rebinding. Stale processes linger.  
**Fix:** Triple-kill sequence in `.command` launcher: (1) kill by PID file, (2) kill by `lsof -ti :5111`, (3) `pkill -f production_server.py`. Added `SO_REUSEADDR` to port check socket. Server calls `server.shutdown()` + `server_close()` before `os.execv()`.  
**Prevention Rule:** Always implement PID-based cleanup + port-based cleanup + name-pattern cleanup. Never rely on a single kill method.

### 1.2 Restart Button — Fixed Wait vs Poll-Until-Ready
**Symptom:** In-browser restart button showed "Restarting..." then either timed out or showed stale page.  
**Root Cause:** Fixed 3–4 second `setTimeout` before checking server health — too short under load, and didn't reload the page.  
**Fix:** Replaced with poll loop: every 1.5s, `fetch("/api/health")`. On success → `location.reload()`. Timeout after 15 attempts → show "use .command file" message. Both success and catch paths use the same polling logic.  
**Prevention Rule:** Never use fixed delays for async operations. Always poll with a timeout. Auto-reload the page after server restart so the latest storyboard version is loaded.

### 1.3 Server Restart Auto-Finds Latest Storyboard
**Symptom:** After patching storyboard to v35/v36/v37, restart button re-launched with the old `--storyboard v34` argument.  
**Root Cause:** `os.execv(sys.executable, sys.argv)` replays the original CLI arguments, which hardcode the storyboard filename.  
**Fix:** Before re-exec, scan `event_dir.glob("storyboard_v*_prod.html")` sorted by mtime, replace the `--storyboard` argument with the latest filename.  
**Prevention Rule:** Server restart must always auto-detect the latest `_prod.html`. Never hardcode storyboard version in restart logic.

### 1.4 CORS — file:// to localhost Blocked
**Symptom:** Cropper loaded from `file://` URL couldn't POST to `localhost:5111`. "Failed to fetch" error.  
**Root Cause:** Browsers enforce CORS for `file://` protocol — it's treated as a different origin from `localhost`.  
**Fix:** Added `/cropper` route to production server so the cropper is served at the same origin (`localhost:5111/cropper`).  
**Prevention Rule:** Never serve interactive HTML tools from `file://` if they make API calls. Always serve via the production server for same-origin access.

---

## 2. Storyboard UI & Button Persistence

### 2.1 render() Destroys All Dynamic DOM
**Symptom:** Lip sync buttons, animation controls, and other dynamically injected UI disappeared after drag-drop or any action that triggered `render()`.  
**Root Cause:** The storyboard's `render()` function rebuilds ALL row DOM from scratch. Any `appendChild()`-injected elements are destroyed. Only functions explicitly called after `_baseRender()` survive.  
**Fix:** Render wrapper pattern:
```javascript
var _baseRender = render;
render = function() {
  _baseRender();
  initDrag();
  setupDropZones();
  if (window._injectAnimations) window._injectAnimations();
  if (window._injectLipSyncButtons) window._injectLipSyncButtons();
};
```
**Prevention Rule:** ANY dynamically injected UI MUST have a corresponding `window._injectXXX` function hooked into the render wrapper. Never add buttons to storyboard rows without also adding a render hook. This is the #1 recurring failure pattern in this session.

### 2.2 Lip Sync Buttons — IIFE Scope Not Exposed
**Symptom:** Lip sync buttons appeared on first load but vanished on first render cycle.  
**Root Cause:** `injectLipSyncButtons()` was defined inside an IIFE `(function(){...})()` — not accessible to the render wrapper's `window._injectLipSyncButtons` check.  
**Fix:** Added `window._injectLipSyncButtons = injectLipSyncButtons;` inside the IIFE before the `setTimeout` call.  
**Prevention Rule:** Any injection function that must survive render cycles needs to be exposed to `window` scope, even if defined inside an IIFE.

### 2.3 Animation Controls Hidden for "Polling" State Beats
**Symptom:** After clicking "Generate B+C", beat 2's animation section (Preview, Trim, Generate B+C button) vanished entirely.  
**Root Cause:** `injectAnimationsFromStatus()` had: `if (b.status !== "completed") return;` — beats in "polling" state (waiting for WaveSpeed) were skipped entirely, hiding ALL controls including the button needed to retry.  
**Fix:** Relaxed check to: `if (!b.options || b.options.length === 0) return;` — show controls for any beat that has at least one option, regardless of overall status.  
**Prevention Rule:** Don't hide entire UI sections because a sub-operation is pending. Only disable the specific control that triggers the pending operation. Show existing completed options while new ones generate.

### 2.4 Drop Zone Hint Duplication
**Symptom:** "↓ Drop image here" text stacked up (2–3 copies) after multiple render cycles.  
**Root Cause:** `setupDropZones()` appended new `.drop-hint` divs on every call without checking if one already existed.  
**Fix:** Added guard: `if(rows[i].querySelector(".drop-hint")) continue;` before creating new hint.  
**Prevention Rule:** Any function called by the render wrapper that creates DOM elements must check for existing instances first.

---

## 3. Image Data Structures — The Three-Layer Model

### 3.1 Three Structures Must Stay in Sync
The storyboard maintains three separate image data structures:

| Structure | Purpose | Format | Size |
|-----------|---------|--------|------|
| `IN` (var IN={}) | Key→name map for dropdowns and drag-drop | `"key": "filename.png"` | N/A |
| `TH` (TH["key"]) | Thumbnail data URIs for preview | base64 PNG | ~80px |
| Gallery `.ic` divs | Full-res images for visual library | base64 PNG | 200px (builder) or full-res (injected) |

**Critical Lesson:** All three MUST be populated for any image to work in drag-drop. If `IN` is missing the key, the dropdown won't list it. If `TH` is missing, the thumbnail won't render. If the gallery div is missing, drag-drop has nothing to drag.

### 3.2 Gallery Images Are NOT Full-Res
**Symptom:** Animation generation failed dimension validation despite images appearing fine in the UI.  
**Root Cause:** The 9 original gallery images from the builder are only **200×150px** — small previews, not production images. Only images injected via the cropper pipeline are full-res. The `TH` thumbnails are **80px**.  
**Fix:** `extract_beats_from_html()` now prefers gallery (full-res) over TH (thumbnail) when resolving beat images. Added auto-upscale fallback.  
**Prevention Rule:** Never assume gallery images are production-quality. Always validate dimensions before sending to animation APIs.

### 3.3 Drag-Drop Index-Mapping Bug
**Symptom:** Drag-drop placed wrong images on beats. Gallery image #5 mapped to wrong IN key.  
**Root Cause:** `initDrag()` mapped gallery images to IN keys by **position index**. When images were injected (changing positions), the indices no longer matched.  
**Fix:** Label-based key derivation: `key = p.textContent.replace(/\.png$/i,"").replace(/\s+/g,"_")`. Each image's drag key comes from its `<p>` label, not its position.  
**Prevention Rule:** Never use positional indices for identity in UI components that can grow dynamically. Use label-derived or ID-based keys.

---

## 4. Image Pipeline — Cropper to Animation

### 4.1 Cropper → Storyboard Library Pipeline
**Symptom:** Kim cropped images but they didn't appear in the storyboard library.  
**Root Cause:** No direct pipeline existed. The cropper and storyboard were separate tools with no integration.  
**Fix:** Added "Send to Storyboard" buttons to cropper (per-crop and "Send All"). These POST to `/api/inject-image` which adds the image to all three data structures (IN, TH, gallery) and writes a new storyboard version.  
**Kim's Quote:** "They always need to go directly from the cropper into the storyboard. That's the whole point. The storyboard LIBRARY."  
**Prevention Rule:** Crops must flow directly from cropper to storyboard library via API — never manual file copy.

### 4.2 "Send All" Timing Bug
**Symptom:** "All 4 crops sent to storyboard!" message appeared but library was empty.  
**Root Cause:** `sendAllToStoryboard()` reported success after queuing requests, not after they completed. The success message fired in the main thread before async fetches resolved.  
**Prevention Rule:** Never display success messages for async operations before the final `.then()` fires. Tie UI feedback to completion, not initiation.

### 4.3 Drag-Drop Doesn't Notify Server
**Symptom:** Kim drag-dropped a new image onto beat 2, hit "Generate B+C", but the animation used the OLD image.  
**Root Cause:** Drag-drop updated `L[idx].i` in browser memory only. The server's `_beats_cache` still had the old image from the HTML file on disk. `add_options` extracted the stale image.  
**Fix:** Three-part solution: (1) Drag-drop now POSTs to `/api/assign-image` with beat ID and image key. (2) Server looks up full-res gallery image and stores in `_image_overrides` dict. (3) `_handle_animate` and `_handle_add_options` check `_image_overrides` first.  
**Prevention Rule:** Any interactive state change in the storyboard (drag-drop, reorder, pause edit) must call a server endpoint to persist. Browser-only state is invisible to the server.

### 4.4 The 600px Dimension Gate + Auto-Upscale
**Symptom:** "Generate B+C" silently failed for beat 2. No error shown.  
**Root Cause:** `shot6_v2_establishing_frame_1.png` was 693×520px. Shortest side (520) < 600px minimum (CLAUDE.md Rule 6). The `validate_image_dimensions()` function rejected it, and the JS error handler reverted the button without showing the error clearly.  
**Fix:** Added `auto_upscale_image()` function: if shortest side < 600px, scale up using PIL Lanczos to meet the minimum. Applied in both `_handle_animate` and `_handle_add_options` before validation.  
**Prevention Rule:** Enforce the 600px gate at multiple layers (cropper warning, server validation, auto-upscale fallback). The auto-upscale is a safety net, not a substitute for proper cropping.

### 4.5 extract_beats_from_html Used Thumbnails for Animation
**Symptom:** Animation API received 80px thumbnail images instead of full-res.  
**Root Cause:** `extract_beats_from_html()` resolved image keys via `TH["key"]` (80px thumbnails) rather than gallery `.ic` divs (full-res).  
**Fix:** Updated extraction to prefer gallery images: first search for `<div class="ic"><img src="..."><p>key...</p></div>`, fall back to `TH` only if gallery match not found.  
**Prevention Rule:** When extracting beat data for production use (animation, lip sync), always resolve to the highest-resolution image available. Thumbnails are for UI display only.

---

## 5. Animation vs Lip Sync — Two Separate Processes

### 5.1 Pipeline Sequence
Kim's correction: "Animation and lipsync are two separate processes. Please review the documentation carefully."

| Step | Input | API | Output | Cost |
|------|-------|-----|--------|------|
| **Animation** | Still image + motion prompt | Kling v3.0 Pro via WaveSpeed `/api/v3/kwaivgi/kling-v3.0-pro/image-to-video` | Silent 5s video clip | ~$0.375 |
| **Lip Sync** | Animated clip + TTS audio | ByteDance via WaveSpeed `/api/v3/bytedance/lipsync/audio-to-video` | Video with mouth movement | ~$0.15 |

**These are sequential, not alternative.** Animation produces motion from a still. Lip sync adds mouth movement to the animated clip. You cannot lip-sync a still image directly.

### 5.2 Storyboard Server Endpoints
- `POST /api/animate` — Submit beats for Kling animation (uses assigned image)
- `POST /api/beat/add_options` — Generate B+C options (keeps Option A)
- `GET /api/animate/status` — Poll animation progress
- `POST /api/lipsync` — Submit beat for ByteDance lip sync (uses selected animation clip)
- `GET /api/lipsync/status` — Poll lip sync progress

---

## 6. Path B Patching Protocol

### 6.1 Base64 Safety Verification
Every Path B patch MUST verify all base64 images are preserved byte-identical:
```python
old_b64 = re.findall(r'data:image/[^"]{100,}', html)
# ... apply patches ...
new_b64 = re.findall(r'data:image/[^"]{100,}', html)
for i, (a, b) in enumerate(zip(old_b64, new_b64)):
    if a != b:
        print(f"CRITICAL: base64 image {i} corrupted. Aborting.")
        sys.exit(1)
```
**Why:** Base64 strings can be 1–5MB. Text editors silently truncate them. Direct HTML editing is FORBIDDEN (CLAUDE.md Rule 7).

### 6.2 Tools Created This Session
| Tool | Purpose |
|------|---------|
| `patch_drag_drop_fix.py` | Label-based initDrag() + IN sync |
| `patch_cropper_send_to_storyboard.py` | "Send to Storyboard" buttons in cropper |
| `inject_image_into_storyboard.py` | CLI tool for surgical image injection |
| `patch_lipsync_render_hook.py` | Hook lip sync buttons into render cycle |
| `patch_animation_polling_state.py` | Show animation controls for polling beats |
| `patch_dragdrop_notify_server.py` | Drag-drop → /api/assign-image notification |

---

## 7. Open Issues (For Claude Code Handoff)

### 7.1 Generate B+C Still Failing on Beat 2 — RESOLVED (April 16 2026 afternoon session)
**Status:** RESOLVED. The original "Submitting... then reverts" behavior was caused by **a different root cause than initially suspected**.

**Actual root cause (not the original suspicion list):**
1. `urllib.request.urlopen` in the long-running Python server process entered a **stuck network state** after hours of uptime. Polls to `api.wavespeed.ai/api/v3/predictions/{id}/result` timed out at 30s every single time — despite the exact same endpoint responding in ~0.3s from any fresh Python subprocess. Hypothesis: SSL session-ticket accumulation + connection-pool state drift in `urllib`'s module-level opener.
2. `_handle_add_options` returned 200 with `new_submitted: 0` when the submit path threw (silent failure).
3. `/api/animate/status` filtered out polling/failed options, so the UI could not render "in progress" or error state — button reverted to default label via `pollStatus()` re-render.
4. `_handle_restart`'s `os.execv` ran in a `daemon=True` thread which died before the exec completed (Restart Server button was a no-op).
5. `_image_overrides` was in-memory only — every server restart wiped drag-drop assignments.
6. The server was launched without `python3 -u`, so stdout was buffered → zero log visibility during debugging.

**Fixes landed (see `prod_locked_decisions` 129–135, 137–138):**
- `POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT` (id=137) — swapped `urllib` for stdlib `http.client.HTTPSConnection` with fresh SSL context per call + `OP_NO_TICKET` + explicit close.
- `EXP_BACKOFF_POLL_RETRY` (id=129) — `MAX_RETRIES=4`, non-blocking `next_attempt_at_epoch` backoff.
- `PRE_FAIL_CDN_RECHECK` (id=130) — async CDN probe at retries `{2, 4}`.
- Non-blocking stdout via `-u` flag in launcher.
- `_handle_restart` → `daemon=False` + extracted `perform_server_restart()` helper.
- Client HTML + `patch_delay_trim.py` now check `data.new_submitted === 0` as failure.
- `/api/animate/status` now includes polling/failed options with per-option status + retries.
- `IMAGE_OVERRIDE_DURABILITY_HYBRID` (id=138) — `_image_overrides` persist to `production_state.json` disk, survive restart, with fire-and-forget Directus audit-log mirror.

**Verified live:** Lip sync job `fea4b30cb0b6...` completed in 52s after the http.client swap. Poll timings went from 30s-timeout-every-time to 0.33s-response. Beat_03 Generate B+C session tripped a brief real WaveSpeed outage (~2-3 min) during testing and auto-recovered via CDN pull per `CDN_RECOVERY_TOOL_PRIMARY` (id=131).

### 7.2 sendAllToStoryboard() Timing Bug
**Status:** Known but unfixed. Success message fires before all fetches complete.

---

## 8. Additional Resilience Fixes (April 16 2026 evening session)

Landed AFTER section 7.1 was resolved, covering Tier 3 blind spots identified via Phase 6 adversarial review:

- **`CROSS_MACHINE_DIRECTUS_LOCK`** (id=132, BS1): Directus `prod_locks` semaphore wraps every state mutation. Same Dropbox-synced event_dir is now safely writable from Kim's Mac AND Windows machine (serial, not concurrent). Fails closed if Directus is unreachable (env `PRODUCTION_SERVER_SINGLE_MACHINE=1` escapes for offline work).
- **`WAVESPEED_STARTUP_SMOKE_TEST`** (id=133, BS3): 5s WaveSpeed connectivity probe at server startup. WARN-only logs. Differentiates auth / upstream 5xx / connectivity failures. Would have shown "connectivity failure" at boot during today's brief WaveSpeed outage instead of at first `/api/animate`.
- **`ATOMIC_DOWNLOAD_TMP_RENAME`** (id=134, BS4): `WaveSpeedClient.download` writes to `dest.tmp` then `os.replace`. Startup orphan-sweep in `run_server` cleans up `*.tmp` files from crashed downloads.
- **`BS6_ACCEPT_DIRECTUS_AUDIT_GAPS`** (id=135, BS6): Fire-and-forget `_async_log_image_override` kept as-is — NO retry queue built. REVISIT TRIGGER when a second reader of `prod_session_decisions` IMAGE_OVERRIDE_ rows exists.

## 9. Stitch Pipeline Design (April 16 2026 — decided, NOT YET IMPLEMENTED)

Decisions locked via this session; implementation deferred to next Tier 4 build:

- **`STITCH_ARCHITECTURE_MULTI_STAGE`** (id=139): Two-stage scene assembly — `/api/beat/finalize` per beat + `/api/scene/assemble` concat. Resumable. Matches existing `phase_1` / `lipsync` state pattern.
- **`STITCH_WORKFLOW_PREVIEW_THEN_COMMIT`** (id=140): Preview Scene button → inline preview at top of storyboard → reject? edit beats in existing controls → re-Preview → Commit Final.
- **`STITCH_BUTTON_LOCATION_STORYBOARD_OVERLAY`** (id=141): Buttons live in `inject_production_overlay.py` emission next to Export Selections.

---

## Summary: Top 5 Prevention Rules

1. **Hook ALL dynamic UI into the render wrapper** — if render() can destroy it, `window._injectXXX` must recreate it
2. **Keep IN + TH + gallery in sync** — any image operation must update all three atomically
3. **Drag-drop must notify the server** — browser state is invisible to production APIs without explicit `/api/assign-image` calls
4. **Never use thumbnails for production** — always resolve to full-res gallery images; auto-upscale as safety net
5. **Never use fixed delays for async ops** — poll with timeout, report completion not initiation

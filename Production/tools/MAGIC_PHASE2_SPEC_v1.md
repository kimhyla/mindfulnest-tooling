# Visible Magic — Phase 2 Server Integration Spec v1
# Production/tools/MAGIC_PHASE2_SPEC_v1.md
# Written 2026-04-24 after full production_server.py architecture review
# ─────────────────────────────────────────────────────────────────────────

## What Phase 2 Builds

A zero-Claude-turns visible magic workflow fully integrated into the existing
production server at localhost:5111. Kim's complete interaction:

1. Open `/magic?scene_key=m1_e1_res_beat_01_heartwood_wide` in browser
2. Background auto-loads (no drag needed)
3. Click 3-9 points on the path
4. Click **Submit Path**
5. Watch progress bar: validating → writing → rendering preview → rendering video → registering
6. See preview image + video player inline on the same page
7. Done. No Claude involvement. No copy-paste. No approvals required.

---

## New Files

| File | Purpose |
|---|---|
| `MAGIC_PHASE2_SPEC_v1.md` | This document |
| `patch_magic_server.py` | Applies magic routes to production_server.py |
| `path_picker.html` | Enhanced: server-submit mode + progress UI |

---

## New API Routes

### GET /magic
Serves `path_picker.html` with URL params injected.

Query params:
- `scene_key` (optional) — pre-selects scene; background auto-loads
- `bg` (optional) — direct URL to background still (fallback if scene_key resolution fails)

### POST /api/magic/submit_path
Receives clicked path, validates, writes registry, kicks off full render pipeline.

Request body:
```json
{
  "scene_key": "m1_e1_res_beat_01_heartwood_wide",
  "manual_path": [[0.111, 0.731], [0.316, 0.792], ..., [0.497, 0.642]],
  "module_id": "m1",
  "event_id": "e1",
  "beat": "res_beat_01",
  "style": "tessa_ori"
}
```

Response:
```json
{"ok": true, "job_id": "magic_1714000000_heartwood_wide", "poll": "/api/magic/status?job_id=..."}
```

Validation rules (400 if violated):
- `scene_key` required, non-empty
- `manual_path` required, list of [x,y] pairs
- All values in [0.0, 1.0]
- Length 2–20 points
- No duplicate adjacent points

### GET /api/magic/status?job_id=X
Polls job state. Called every 2s by path_picker.html.

Response shape:
```json
{
  "ok": true,
  "status": "pending|writing_registry|rendering_preview|rendering_video|registering|done|error",
  "message": "Human-readable status message",
  "preview_url": "/files?path=<abs_path>",  // set when preview done
  "video_url": "/files?path=<abs_path>",    // set when video done
  "error": null
}
```

---

## Server-Side Job Flow (_MAGIC_JOBS dict)

Mirrors `_ASSEMBLE_JOBS` pattern exactly.

```python
_MAGIC_JOBS: dict = {}
# job_id → {
#   "status": str,
#   "message": str,
#   "scene_key": str,
#   "preview_path": str | None,
#   "video_path": str | None,
#   "error": str | None,
# }
```

Background thread sequence (all in one daemon thread):

```
Step 1 — Validate input        → status: "writing_registry"
Step 2 — Write scene_registry  → status: "rendering_preview"
Step 3 — Render preview still  → status: "rendering_video"
           (final frame, t=total_frames-2)
Step 4 — Render full video     → status: "registering"
Step 5 — Directus two-write    → status: "done"
```

On any exception: `status: "error"`, `error: str(e)`, thread exits.

### Step 2 detail — Write scene_registry.yaml
Uses `ruamel.yaml` round-trip (preserves all comments + structure).
Falls back to `pyyaml` + full rewrite if ruamel unavailable.
Writes `.bak` before any modification.
Writes `manual_path` under scene_key, creating entry from template if absent.

### Step 3 detail — Render preview still
```python
from magic_compositor import MagicCompositor
mc = MagicCompositor(bg_path, path_pts, style="tessa_ori", ...)
preview_path = mc.render_preview(frame_idx=total_frames - 2)
```

Background still resolved in priority order:
1. scene_registry `source_asset_query` → look up approved still from prod_visual_assets
2. Well-known path pattern: `Production/Event_{N}/resolution_stills/{shot_role}.png`
3. `heartwood_wide_1456.png` as explicit fallback for known scene keys

### Step 4 detail — Render full video
```python
video_path = mc.render_video()
```

### Step 5 detail — Directus two-write
Write 1: `prod_magic_clips` (scene_key, path, style, preview_path, video_path, confirmed_at)
Write 2: `prod_activity_log` (magic_render_approved)
On failure: append to `PENDING_REGISTRATIONS.json`, continue (non-blocking).

---

## path_picker.html Enhancements

### Mode Detection
On load, read `?scene_key=` and `?bg=` from URL.

If `scene_key` present:
- Show scene_key in header
- Auto-fetch background: `GET /files?path=<resolved_still_path>`
- Resolution: ask server via `GET /api/magic/resolve_bg?scene_key=X` → returns `{bg_url}`
- On success: load into canvas automatically (no drag needed)

If `bg` param present: fetch that URL directly and load into canvas.

If neither: show drag zone as before (backward compat).

### New Submit Button
Alongside existing "Copy YAML" button:
- **"Submit Path"** (blue) — posts to `/api/magic/submit_path`, shows progress UI
- "Copy YAML" stays as backup for offline/Claude-mode use

### Progress UI (appears after Submit)
Replaces YAML output div with progress panel:
```
[███████░░░░] Rendering preview...
```
States shown with spinner:
- writing_registry → "Saving path..."
- rendering_preview → "Rendering preview (frame 82/84)..."
- rendering_video → "Rendering full video (84 frames)..."
- registering → "Registering in Directus..."
- done → progress bar hidden; show result panel

### Result Panel (shown when done)
```
✓ Magic render complete

[Preview image: inline <img>]
[Video player: <video controls autoplay loop>]

[▶ Open in QuickTime]  [↩ Pick new path]
```

---

## Additional GET Route: /api/magic/resolve_bg

Resolves the background still path for a scene_key.

```
GET /api/magic/resolve_bg?scene_key=m1_e1_res_beat_01_heartwood_wide
→ {"ok": true, "bg_url": "/files?path=/Users/.../heartwood_wide_1456.png"}
```

Resolution logic (in priority order):
1. `scene_registry.yaml` → `source_asset_query.filter.shot_role` → glob in resolution_stills/
2. Known fallback map keyed on scene_key (heartwood, runestone, etc.)
3. 404 if unresolvable → path_picker falls back to drag-drop

---

## Implementation: patch_magic_server.py

Patch script (not direct edit — safe on 4000-line file):
1. Back up production_server.py → production_server.py.bak_magic_TIMESTAMP
2. String-replace to add `_MAGIC_JOBS` after `_ASSEMBLE_JOBS` (line 103)
3. String-replace to add GET routes in `do_GET` before the 404 fallback
4. String-replace to add POST route in `do_POST` before the 404 fallback
5. String-replace to add handler methods before `_handle_bg_segments`
6. Verify patch via `python3 -c "import production_server"` — must import cleanly

---

## Failure Modes & Mitigations

| Risk | Mitigation |
|---|---|
| ruamel.yaml not installed | Fall back to pyyaml + full file rewrite + bak |
| Background still not found | /api/magic/resolve_bg returns 404; picker shows drag zone |
| Render takes >60s | Job stays in rendering_* state; client polls every 2s; no timeout |
| Directus write fails | Append to PENDING_REGISTRATIONS.json; job still reaches "done" |
| Server patch breaks import | Bak restore on ImportError; verify step catches this |
| Concurrent submits for same scene_key | Last-write-wins on registry (ruamel round-trip is atomic per write) |
| Video file too large | magic_compositor uses additive blend, no ffmpeg re-encode; output ~300KB |

---

## Multipass Verification Plan

After implementation, run these checks in order:

**Pass 1 — Import check:**
```bash
cd Production/tools && python3 -c "import production_server; print('OK')"
```

**Pass 2 — Route check:**
```bash
curl -s http://localhost:5111/api/magic/resolve_bg?scene_key=m1_e1_res_beat_01_heartwood_wide
# Expected: {"ok": true, "bg_url": "..."}
```

**Pass 3 — Submit check:**
```bash
curl -s -X POST http://localhost:5111/api/magic/submit_path \
  -H "Content-Type: application/json" \
  -d '{"scene_key":"m1_e1_res_beat_01_heartwood_wide","manual_path":[[0.111,0.731],[0.497,0.642]]}'
# Expected: {"ok": true, "job_id": "...", "poll": "..."}
```

**Pass 4 — Poll check:**
```bash
# Poll until done
curl -s "http://localhost:5111/api/magic/status?job_id=<id>"
```

**Pass 5 — Browser check:**
Open http://localhost:5111/magic?scene_key=m1_e1_res_beat_01_heartwood_wide
Verify: background auto-loads, click 3 dots, submit, see progress, see video.

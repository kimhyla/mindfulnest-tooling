# Visible Magic — Complete Lessons Learned v5
**Date:** 2026-04-25
**Produced by:** Full transcript scrape (919cdad0) + 3 compaction summaries + three-agent debate synthesis
**Supersedes:** v1 (tools/), v2 (tools/), v3 (Production/), v4 (Production/)
**Status:** DEFINITIVE — covers the complete arc from broken skill → working server-integrated pipeline

---

## 0. One-Paragraph Verdict

The visible magic skill failed for ~40 total iterations across multiple sessions because it had three separate problems at three separate layers, each of which had to be solved independently before the next layer's problem became visible. **Layer 1 (physics):** additive blend on daytime backgrounds was non-negotiable — screen blend is invisibly weak on bright backgrounds. **Layer 2 (geometry):** every approach to auto-detecting where the path goes (color thresholding, numpy luminosity peaks, Preview drawing extraction) was either wrong or too lossy. The only thing that works is Kim clicking the points herself on the image. **Layer 3 (integration):** once the compositor worked and the path picker worked, wiring them into the beat generator storyboard required 8 separate bug fixes across server routing, sidecar data model, image path resolution, URL encoding, and fallback logic. Every layer looked like "just one more bug" but was actually an independent architectural gap. The final working system is: beat generator → Open Path Picker → background auto-loads → click dots → Submit Path → server pipeline renders and delivers video. Zero Claude involvement after the click.

---

## 1. Full Chronological History (All Sessions)

### Phase 1 — Session 2026-04-22 morning: First compositor attempts (~12 iterations)
**Target:** 3–3.5s animated magic trail, left forest edge → Heartwood altar, daytime background `heartwood_3q_left_1456.png`

- **v1–v4:** Per-orb PIL approach, GaussianBlur. Render: 15–40 min. **INVISIBLE on daytime background.** Root cause: screen blend. bg=180, magic=100 → +30 delta only. Below perceptual threshold.
- **v5–v8:** Switched approach, but path endpoint wrong: altar TOP `(0.51, 0.60)` instead of step edge `(0.47, 0.670)`. Magic visibly floated in air 90px above floor.
- **Full-image darkening attempt:** Made entire scene twilight. Magic visible. Kim: **"NO — you made it nighttime!"** REJECTED.
- **Corridor dimming (v10):** 60% darkness along path only. Shadow band visible. Session stopped.
- **Solid filled ellipse (v11):** Visible but "worm"-like trail. Rejected.
- **`composite_magic_path_tessa.py` v5:** `make_glow()` accumulation, corrected endpoint. Used screen blend. Session ended before Kim verdict. Labeled "best script" in memory — BUT still used the banned screen blend.

### Phase 2 — Session 2026-04-22 late: First approval
- **v6 (`magic_compositor.py` class):** Pre-placed seeded particles (1800), 1–3px crisp dots, **additive blend**, anisotropic blur `[2.5, 18.0]`, auto-gain calibration `gain = 0.7 + (avg_lum/128)×0.6`. **Kim APPROVED → `beat_magic_path_v6.mp4`.** Locked as LD-398 `MAGIC_STYLE_TESSA_ORI_V1`. The ONLY unconditional win in the entire physics-layer history.

### Phase 3 — Session 2026-04-23: Geometry calibration for new scenes
- **Tessa exit-right:** v1–v2 had `t_head = t_frac` bug, odd-dimensions crash, `frame_idx` NameError. v3 approved. Foot coords found via numpy luminosity — initially found shell highlight at `y=0.898` instead of ground contact `y=0.96`.
- **Runestone activation:** First coordinate guess off by 0.08 in both axes (~130px on 1676px frame). Fixed via orange-channel color thresholding.
- **Full sequence v1 stitched** → APPROVED.
- **Full sequence v2 — CATASTROPHIC FAILURE.** Assembled by filename pattern, not registry. Zero of three clips correct.

### Phase 4 — Session 2026-04-24 early: Three-agent diagnostic debate → spec

Three Opus agents debated the full history:
- **Agent 1 (Forensic Historian):** ~20 iterations pre-first-approval; only one genuine end-to-end win; stitching forced by compositor-can't-eat-video.
- **Agent 2 (Technical Root Cause Analyst):** Physics of bioluminescence on bright backgrounds; 25-parameter search space; screen vs additive; why numpy heuristics fail.
- **Agent 3 (Systems Architect):** What "first time works" requires; the right interface is `render_magic(scene_key=...)`, not coordinate reconstruction each time.

**Unanimous verdict:** The path-drawing loop with Preview is structurally lossy. Preview auto-smooths lines, black pixels blend into scene shadows, and coordinates are re-extracted incorrectly every time. Fix: browser click tool.

**Output:** `VISIBLE_MAGIC_LESSONS_LEARNED_v4.md`, `VISIBLE_MAGIC_TECH_SPEC_v1.md`, `VISIBLE_MAGIC_IMPLEMENTATION_HANDOFF_v1.md`

### Phase 5 — Session 2026-04-24: Geometry detector + path picker build

**Task 1 — `geometry_detector.py`:**
- Built color-channel thresholding (6 lambdas per stone color)
- Orange altar found at `(0.616, 0.543)` — WRONG: altar body glow, not step edge
- Floor clamp added → `y≈0.86` (47% confidence) — WRONG: floor tiles below altar, nothing orange there
- `manual_target` added as explicit override in registry for scenes where landing point has no distinctive colour
- Path still hovering: `y≈0.62–0.67` (altar bowl level), correct is `y≈0.75–0.80`
- Kim drew path 4–5 times in Preview — all attempts lossy (Preview smooths strokes, black pixels blend with tree shadows in source image)
- Multiple debug grid images generated at 0.01 increments with y-coordinate labels
- Final corrected coords after iteration: `manual_origin: [0.0, 0.790]`, `manual_target: [0.40, 0.730]`

**Three-agent debate on path drawing extraction:**
- All three agents independently concluded: "The drawing approach is structurally lossy — Preview smooths lines, black pixels blend with scene darks, data is thrown away every time."
- **Unanimous recommendation: `path_picker.html`** — browser click tool where Kim clicks 3–8 points and gets pixel-exact YAML.

**`path_picker.html` build:**
- Drag PNG onto canvas → click points → live red line with coordinate display → "Copy YAML" button
- Kim tested with heartwood_wide image: 9 points clicked, YAML output correct
- Render immediately confirmed: magic trail on correct floor path
- Kim: **"BEAUTIFUL!!!"** — full approval

### Phase 6 — Session 2026-04-24: Phase 2 server integration

**Spec:** `MAGIC_PHASE2_SPEC_v1.md` — full zero-Claude-turns workflow via `production_server.py`

**New server routes added (via `patch_magic_server.py`):**
- `GET /magic` → serves `path_picker.html` with URL params
- `POST /api/magic/submit_path` → validates, writes registry, starts background render thread
- `GET /api/magic/status?job_id=X` → polls render progress
- `GET /api/magic/resolve_bg?scene_key=X` → resolves background still from registry
- `GET /api/beat/accepted-bg?beat_id=X` → resolves background from beat sidecar

**Server job pipeline (background thread):**
```
POST submit_path → validate → write scene_registry.yaml → resolve bg still
→ render preview (final frame) → render full video → Directus two-write → done
```

**5-pass verification passed:** import OK → resolve_bg 200 → submit_path 200 → poll loop → video rendered in 14s

**Bug encountered:** `\n` inside triple-quoted Python patch string was a literal newline, breaking regex patterns `r"directus.*?email[:\s]+([^\s\n]+)"`. Fixed by removing `\n` from regex: `r"directus.*?email[\s:]+(\S+)"`.

### Phase 7 — Session 2026-04-24/25: Storyboard beat generator integration

**Goal:** Kim selects "✨ Magic Trail" dropdown → places image in Option 1 → clicks "Open Path Picker" → background auto-loads → clicks dots → Submit → video delivered.

**Bug 1 — confusing scene_key field shown to Kim:**
- First implementation showed a raw scene_key text field Kim had to fill in manually
- Fix: auto-generate scene_key from beat ID, hide the field entirely, show only the blue button

**Bug 2 — "Preview Frames / Render Video" buttons showing:**
- Kim clicked them expecting them to work; they errored
- Fix: hidden under "Manual override (advanced)" disclosure triangle

**Bug 3 — DOM scraping failed to find Option 1 image:**
- First approach: grab `img` elements from Option 1's DOM card
- Problem: beat generator uses a different HTML structure than storyboard
- CSS selectors tried: `.bg-beat-option-card img`, `.bg-flux-slot img`, `.bg-option-card:first-child img`, etc. — all returned null
- Fix: architecturally wrong approach; server already owns the data

**Bug 4 — Root cause of DOM scraping failures (Opus agent debate):**
Two Opus agents independently identified the same root cause: **the beat generator has two separate image concepts**:
1. "Image placed in option slot" — visual only, never written to server
2. "Image accepted/chosen" — server state written, `accepted_image_key` set

The DOM scraping was chasing visual state. The server had no record of it. The agents recommended adding `GET /api/beat/accepted-bg?beat_id=X` to read from the sidecar.

**Bug 5 — ✨ button on every option slot:**
- First implementation added a ✨ button to every flux option slot
- Kim: **"no no no"** — not all images are Magic Trail, adding an option shouldn't auto-fire visible magic
- Fix: reverted immediately; ✨ button only on the Magic Trail panel, not per-slot

**Bug 6 — `accepted_image_key` was null in sidecar:**
Sidecar dump for beat_02:
```json
{
  "accepted_image_key": null,
  "flux_options": [],
  "reference_image": "/Users/.../heartwood_07_three_quarter_left.png"
}
```
The image WAS there — stored as `reference_image` (drag-from-sources path), not `accepted_image_key`. The `_handle_beat_accepted_bg` endpoint was checking accepted_image_key first, then flux_options, but never checked reference_image.
Fix: added reference_image/bg_ref_image as FIRST fallback check.

**Bug 7 — `crossOrigin='anonymous'` blocked image load:**
`loadImageFromURL()` in path_picker.html had `image.crossOrigin = 'anonymous'`. Same-origin `/files?path=` requests don't send CORS headers in the response (they don't need to). The `crossOrigin='anonymous'` attribute caused the browser to reject the load. Fix: removed it.

**Bug 8 — path_picker `resolve_bg` falls through on unknown scene_key:**
When `scene_key=m1_e1_res_bg_arc1_event1_post_beat_02` (a beat generator ID, not in scene_registry.yaml), `GET /api/magic/resolve_bg` returned 404. The path_picker code branched:
- If `sceneKey` present → fetch resolve_bg → on failure: show "Could not auto-load" message
- `else if bgParam` → load directly from bg URL
The `bgParam` fallback was never reached because `sceneKey` was always present.
Fix: when resolve_bg fails, fall back to bgParam rather than showing error:
```javascript
} else if (bgParam) {
  loadImageFromURL(bgParam);
} else {
  // show error
}
```

**Bug 9 — Submit Path couldn't find background still:**
`POST /api/magic/submit_path` received `scene_key` and `manual_path` but not the background image path. Server tried to resolve bg from scene_registry `source_asset_query` and `_KNOWN_STILLS` — both failed for beat generator keys.
Error: `"Cannot find background still for m1_e1_res_bg_arc1_event1_post_beat_02"`
Fix (two-part):
1. path_picker.html extracts absolute file path from `bgParam` URL (`new URL(bgParam).searchParams.get('path')`) and sends it as `bg_path` in POST body
2. Server checks `body.get("bg_path")` as first source before registry/known_stills:
```python
explicit_bg = body.get("bg_path", "")
if explicit_bg and Path(explicit_bg).is_file():
    bg_path = explicit_bg
```

**Final result:** End-to-end pipeline working. Kim clicks "Open Path Picker", background auto-loads, places 9 dots, clicks Submit Path, server renders magic trail video.

---

## 2. What ACTUALLY Solved Each Problem (Layer by Layer)

### Layer 1 — Physics (why magic was invisible)
**The answer:** Additive blend, not screen blend.
- Screen blend on daytime bg=180: only +30 brightness delta. Imperceptible on warm stone.
- Additive blend + 1800 pre-seeded particles + auto-gain calibration: visible without nighttime darkening.
- This was a one-time discovery. Once locked in LD-398, it has never been revisited.

### Layer 2 — Geometry (where does the path go)
**The answer:** Kim clicks the points herself in a browser tool. No inference needed.
- Color thresholding: found wrong pixels (bowl contents, not altar step).
- Numpy luminosity: found shell highlights, not ground contact.
- Preview drawing: auto-smoothed, black pixels blended with shadow, data thrown away.
- **`path_picker.html`:** Kim clicks 3–9 points on the actual image. Pixel-exact fractional coordinates. Zero extraction error. Zero iteration.

### Layer 3 — Integration (how does it reach production)
**The answer:** A dedicated server endpoint (`/api/beat/accepted-bg`) that reads from the sidecar's `reference_image` field, plus `bg_path` forwarded through the submit chain.
- DOM scraping: the beat generator never writes image state to the DOM in a way Claude can reliably read.
- `accepted_image_key`: only set when an image is accepted via the FLUX accept flow; drag-from-sources uses `reference_image` instead.
- URL param fallback: when scene_key is a beat-generator ID (not in registry), the `bg=` param carries the image URL, but must be explicitly forwarded to the render job's POST body.

---

## 3. The 5 Failure Mode Patterns (Summary — Full Detail in v4)

| # | Pattern | What Caused It | What Fixed It |
|---|---|---|---|
| 3.1 | Magic invisible on daytime bg | Screen blend; only +30 brightness delta | Additive blend + 1800 particles + auto-gain |
| 3.2 | "Floating above the floor" trail | Wrong endpoint (altar top not step edge); `SIGMA_Y` too high; abs(gauss) scatter | All 4 params changed together; `manual_path` via picker |
| 3.3 | Wrong coordinates | numpy heuristics find wrong features; drawing lossy | path_picker.html; Kim clicks directly |
| 3.4 | Jerky/popping particles | Per-frame new particle positions | Pre-place all N particles at init with fixed seed |
| 3.5 | Wrong clips in stitch | Filename pattern resolution; not registry | Directus two-write; `reference_image` fallback in sidecar |

---

## 4. Locked Parameters — Never Tune These

| Parameter | Locked Value | Authority |
|---|---|---|
| Blend mode | Additive | LD-398 (screen failed v1–v5) |
| Palette | Warm golden-white `(255,255,238)/(255,252,200)/(255,240,155)` | All cool palettes rejected |
| Dot sizes | `[1,1,1,2,2,3]` | Larger = blobs (rejected) |
| Scatter | Symmetric gaussian, NOT `abs(gauss)` | Half-normal creates floating band |
| `scatter_y_frac` | 0.032 | Larger = floating (rejected) |
| `AMBIENT_BLUR_YX` | `[6.0, 28.0]` | Narrow Y prevents sky leak |
| `AMBIENT_MIX` | 2.4 | Empirically tuned in v6 |
| `T_TRAIL_COMPLETE` | 0.70 | Timing approved v6 |
| `T_FADEOUT_START` | 0.75 | Same |
| `seed` | 42 | Determinism |
| Particle pre-placement | Pre-placed at init, sorted by `ts` | Per-frame placement = popping |
| Path interpolation | Bezier (spline) | Produces smooth curve; accepted by Kim ("close enough") |

---

## 5. The Complete Working System (As of 2026-04-25)

### Files
| File | Role | Status |
|---|---|---|
| `Production/tools/magic_compositor.py` | Core renderer class `MagicCompositor` | ✅ Production-ready |
| `Production/tools/path_picker.html` | Browser click-to-path tool | ✅ Production-ready |
| `Production/tools/production_server.py` | Server with magic routes | ✅ Live at localhost:5111 |
| `Production/tools/scene_registry.yaml` | Path + style registry per scene_key | ✅ Has heartwood_wide entry |
| `Production/tools/geometry_detector.py` | Color-detection with manual_path override | ✅ manual_path bypasses all detection |
| `Production/tools/patch_magic_server.py` | One-time patch script (already applied) | ✅ Applied |

### Server Routes
| Route | Purpose |
|---|---|
| `GET /magic?scene_key=X&bg=URL` | Serves path_picker.html with params |
| `POST /api/magic/submit_path` | Validates path, starts background render job |
| `GET /api/magic/status?job_id=X` | Polls render progress (2s interval) |
| `GET /api/magic/resolve_bg?scene_key=X` | Resolves bg still from registry/known_stills |
| `GET /api/beat/accepted-bg?beat_id=X` | Resolves bg from beat sidecar (reference_image → flux_options → key lookup) |

### The Workflow (Kim's complete interaction)
1. In beat generator: select **✨ Magic Trail** from animation dropdown
2. Drag background image from sources panel into beat card (saves to `reference_image` in sidecar)
3. Click **✨ Open Path Picker ↗**
4. Background auto-loads into canvas (via `/api/beat/accepted-bg` → `bg=` URL param → fallback when resolve_bg fails)
5. Click 3–9 points along the intended magic trail path
6. Click **Submit Path**
7. Progress bar: `validating → writing_registry → rendering_preview → rendering_video → registering → done`
8. Preview image + video player appear inline
9. Done — no Claude involvement after step 3

### Key Data Flows
```
Kim drags image to beat card
  → _bgUpdateBeat(bid, {reference_image: apath})
  → POST /api/bg/update-beat
  → sidecar.reference_image = "/abs/path.png"

Kim clicks "Open Path Picker"
  → GET /api/beat/accepted-bg?beat_id=X
  → reads sidecar: reference_image || bg_ref_image || flux_options[0].key
  → returns {bg_url: "/files?path=/abs/path.png"}
  → window.open("/magic?scene_key=X&bg=http://localhost:5111/files?path=...")

path_picker.html onload:
  → params.get('scene_key') → fetch /api/magic/resolve_bg
  → if 404: fall back to params.get('bg')  ← THIS WAS THE KEY FIX (Bug 8)
  → loadImageFromURL(bgParam) → image loads

Kim clicks Submit Path:
  → extract abs path from bgParam URL (new URL(bgParam).searchParams.get('path'))
  → POST /api/magic/submit_path { scene_key, manual_path, style, bg_path }  ← Bug 9 fix
  → server: body.get("bg_path") checked FIRST  ← Bug 9 fix
  → background render thread: validate → registry → preview → video → Directus
  → polls /api/magic/status every 2s
  → shows progress bar → result panel with video
```

---

## 6. What To Watch Out For (Future Scenes)

### 6.1 Background class matters
The `tessa_ori` params were tuned for daytime warm stone (Heartwood). They will produce different results on:
- **Nighttime backgrounds (Luna, Bork):** Magic will be over-bright; reduce gain
- **Indoor/cave (Ember):** May need narrower `AMBIENT_BLUR_YX`
- **Bright sky backgrounds:** Any `SIGMA_Y > 8px` leaks into sky; keep current narrow Y

### 6.2 The path is a Bezier curve, not zigzag
The compositor uses Bezier interpolation through clicked points. Kim accepted this ("close enough") for the heartwood scene. For scenes where straight-line segments matter, `magic_compositor.py` would need a `path_mode='linear'` option added.

### 6.3 New beats with unknown scene_keys need `bg_path` to flow through
Any beat generator beat with a non-registry scene_key will fail if the `bg_path` isn't forwarded through. The current fix (path_picker sends `bg_path` in POST body, server checks it first) handles this correctly. Don't add hacks to `_KNOWN_STILLS` — the bg_path forwarding path is the right solution.

### 6.4 The registry two-write on job completion
`POST /api/magic/submit_path` writes to both `prod_magic_clips` (Directus) and `prod_activity_log`. If Directus is down, results are appended to `PENDING_REGISTRATIONS.json`. This file should be replayed at session start if non-empty.

### 6.5 The `source_frame_sha` issue (from v4) remains unfixed
`scene_registry.yaml` entries don't store a SHA of the source image. If a background image is regenerated with different framing, stored path coordinates become wrong. For now: always use the same source image per scene_key. Structural fix (compute geometry fresh from source clip) is Future Work.

---

## 7. Why It Took So Long (Root Cause Summary)

The problem had three independent layers, each invisible until the previous was solved:

**Layer 1 was invisible first:** Magic was invisible on screen (literally — screen blend produces nothing you can see). All geometry work in this phase was wasted because the compositor itself was broken.

**Layer 2 was invisible second:** Once additive blend worked, every path was wrong. Auto-detection tools (numpy luminosity, color thresholding, Preview drawing extraction) all found the wrong pixels. The geometry calibration loop dominated 20+ iterations because each fix exposed a different wrong pixel, and the only ground truth was Kim's eye.

**Layer 3 was invisible third:** Once the compositor + path picker worked end-to-end manually, wiring it into the beat generator exposed 9 separate integration bugs. Each one was technically small (one fallback check, one URL param extraction, one field name). But there was no way to know which bugs existed until the previous ones were fixed — each fix revealed the next failure.

**The meta-lesson:** When a skill fails "for unknown reasons," it's almost always multiple independent layers. Fix layer 1 completely before diagnosing layer 2. Don't spend 20 iterations tuning geometry when the blend mode is wrong. Don't spend 9 patches fixing integration when the compositor itself isn't validated.

**The structural lesson:** The path picker tool was the right solution to layer 2. It was identified by 3-agent debate (twice — once at the end of Phase 4, once at the end of Phase 5). The tool was built immediately and worked first try. **Send agents to debate the architecture before writing code.** The agents identified `path_picker.html` in one turn; every previous approach to geometry took 5+ turns and failed.

---

*Supersedes all prior versions (v1 tools/, v2 tools/, v3 Production/, v4 Production/). Retained for historical record only.*

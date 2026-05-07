# Lessons Learned — Animation & Visible Magic Pipeline (2026-04-26)

**Session window:** 2026-04-25 → 2026-04-26 (Event 1 final assembly + magic trail + Phase B watercolor hands tile animation)
**Author:** Claude (Opus, post-session forensic pass)
**Audience:** the next Claude session that touches the magic compositor, watercolor tile animation, or the storyboard beat generator
**Status:** locked reference — read before any new visible-magic OR Phase B tile animation work

---

## TL;DR — The Two Approved Workflows

1. **Visible magic on a still or scene** → `path_picker.html` → POST `/api/magic/submit_path` → `magic_compositor.py` (style `tessa_ori`) → preview still + full video → registered in `prod_magic_clips` + `prod_activity_log`. **Wired into the beat generator storyboard (`storyboard_v43_prod.html`)** under the animation method dropdown ("✨ Magic Trail").
2. **Animating a watercolor cue tile inside a Phase B video** (e.g. the "press hands together" tile) → `animate_hands_v5`-style **Python warp with Kim's seam path**, NOT Kling. Static mask from the original source isolates art pixels from frame/border. ffmpeg `rawvideo` pipe (NOT imageio) for output. Forced even dimensions for libx264. Time window detected by scanning video for the tile's actual color signature.

Everything else in this document explains *why* those two paths are the locked answers.

---

## Section 1 — Visible Magic (Heartwood Trail) — Magic Compositor

### 1.1 What the system does

`Production/tools/magic_compositor.py` (and earlier specialized scripts like `composite_magic_path_tessa.py v5`) renders a visible bioluminescent magic trail along a Kim-defined path, composited over a still or live video clip.

**Style locked: `tessa_ori`** — gold/cream/amber Ori-of-the-Blind-Forest palette:
- `ORI_CORE = (255, 255, 238)`
- `ORI_BRIGHT = (255, 252, 200)`
- `ORI_MID = (255, 240, 155)`
- `ORI_DIM = (190, 140, 35)`

This was reached after 12 iterations of trying to render visible bioluminescence on bright daytime backgrounds. The earlier "pink/magenta" failures were a colorspace bug, not an art-direction bug (see §1.4).

### 1.2 End-to-end pipeline

```
Beat Generator storyboard (storyboard_v43_prod.html)
   │  user picks "✨ Magic Trail" in animation method dropdown
   │  user clicks "Open Path Picker ↗"
   ▼
GET /magic?scene_key=m1_e1_res_<beat_id>&bg=<bg_url>
   │  served by production_server.py → returns path_picker.html
   ▼
path_picker.html
   │  auto-loads background via GET /api/magic/resolve_bg
   │  user clicks points along desired trail path
   │  user hits "Submit Path"
   ▼
POST /api/magic/submit_path
   │  body: { scene_key, path_pts:[[x,y],...], style:"tessa_ori", bg_url }
   ▼
production_server.py route handler
   │  shells out to magic_compositor.py with the path and background
   ▼
magic_compositor.py
   │  - loads background (still or first video frame)
   │  - rasterizes path with feathered glow at each point
   │  - applies Ori palette tonemap
   │  - PIL ImageChops.screen() blend onto background (NOT ffmpeg blend)
   │  - writes preview still + full MP4 with trail head animating along path
   ▼
Registration
   │  - INSERT into prod_magic_clips
   │  - INSERT into prod_activity_log (kim_verdict NULL until approval)
   │  - SHA256 + file_size_bytes recorded
   ▼
Result returned to storyboard UI
```

### 1.3 What was proven to work (locked recipe)

- **Style:** `tessa_ori` (gold/cream/amber, Ori palette above).
- **Blend method:** PIL `ImageChops.screen()`. **ffmpeg `blend=all_mode=screen` is BANNED** for magic compositing — see §1.4.
- **Audio:** imageio always drops audio. After every Python composite, `ffmpeg -map 0:v -map 1:a -c copy` to mux the original audio back in.
- **Trail vs shell glow are TWO DIFFERENT EFFECTS:**
  - Shell glow = stationary Ori orb anchored to a fixed pixel (e.g. Tessa's shell at `SHELL_CX_FRAC=0.55, SHELL_CY_FRAC=…`).
  - Trail = traveling head + fading tail along Kim's clicked path.
  Do not conflate them. The session burned ~30 minutes mid-debug because "magic" got read as "shell glow" when Kim meant "trail."
- **Path collection:** Kim draws via `path_picker.html` (drag-drop background, click points, hit Copy YAML). Coordinates are normalized `[0..1]` fractions. Manual override panel exists in path_picker.html for testing — paste `path_pts` JSON directly.

### 1.4 Errors encountered and their fixes

| # | Error | Root cause | Fix |
|---|---|---|---|
| 1 | Pink/magenta output despite gold palette | imageio writes MP4 with `color_range=unknown, color_space=unknown, color_transfer=unknown` → ffmpeg blend operations do incorrect channel math | Switch from ffmpeg `blend=all_mode=screen` to single-pass Python PIL `ImageChops.screen()`. Locked. |
| 2 | Tessa_ori flooding the full frame pink at full intensity | Trail file fully saturated bright pink across full frame, screen blend at full intensity floods everything | Reduce trail brightness pre-blend; verified gold once colorspace bug fixed |
| 3 | Magic compositor `--bg` flag not recognized | Script uses `--background` not `--bg` | Use `--background` everywhere; updated rebuild scripts |
| 4 | ffmpeg concat "Impossible to open" | Relative paths in concat list file | Always use absolute paths in concat files |
| 5 | `anullsrc` flag order: `Error parsing options for input file anullsrc=...` | `-f lavfi` must come before the anullsrc input declaration | `-f lavfi -i "anullsrc=r=44100:cl=mono"` as a proper input before any `-map` |
| 6 | Audio dropped by imageio composite | imageio writes video-only MP4 | Explicit ffmpeg audio mux step after every imageio render |
| 7 | Module-level side effect in `composite_magic_overlay.py` | No `if __name__ == "__main__":` guard → render fired on import | Wrap render call in main guard |
| 8 | WaveSpeed timeout on large base64 payloads | Default urllib timeout, big base64 image+video bodies | Use `subprocess` curl with `--max-time 120` for large payloads |
| 9 | Directus 403 on filtered queries | Login + simple 5-item queries work, but `filter[field][_contains]` and `sort=-id&limit=50` return 403 | Use simpler queries; paginate manually; do not rely on `_contains` for asset hunting (this also drove Rule 31 — Directus before disk via `notes` text search) |

### 1.5 Beat Generator wiring status (verified end-to-end this session)

- ✅ "✨ Magic Trail" option present in animation-method dropdown (`storyboard_v43_prod.html`, confirmed at line 4284)
- ✅ "Open Path Picker ↗" button opens `/magic?scene_key=m1_e1_res_<beat_id>&bg=<bg_url>`
- ✅ `/magic` route in `production_server.py` serves `path_picker.html`
- ✅ `path_picker.html` auto-loads background via `GET /api/magic/resolve_bg`
- ✅ Submit fires `POST /api/magic/submit_path` → runs `magic_compositor.py` → writes to `prod_magic_clips` + `prod_activity_log`
- ✅ Manual override panel with `path_pts` textarea for coordinate testing

**No gaps found.** The pipeline is intact and will fire for all visible-magic productions invoked from the beat generator. Per Rule 32, all `fetch()` calls inside the storyboard use `http://localhost:<PORT>/api/...` absolute URLs — verified.

---

## Section 2 — Phase B Watercolor Tile Animation (Animated Hands)

This was the longest debugging arc of the session. The goal: replace the static "hands pressed together" watercolor cue tile inside `arc1_event1_phase_b_v1_20260420.mp4` with an animated version where the hands rub up/down. Eleven distinct errors had to be solved before the animation rendered correctly.

### 2.1 The eleven errors, in order

1. **Wrong Phase B source file.**
   - Used `phase_b_snipped_v2.mp4` initially.
   - Correct source: `Production/Event_1/exports/arc1_event1_phase_b_v1_20260420.mp4` (1280×720, 148s, the LD-348 locked deliverable).
   - **Lesson:** always query Directus `prod_assets` for the LD-locked file before grabbing whatever has the most recent mtime on disk. (Rule 31, "Directus before disk.")

2. **Wrong source image for the hands.**
   - Started with photorealistic `m1_phase_b_still_rub_v5*.png` variants.
   - Correct: extract directly from the Phase B video itself at `t=35s`, then crop to the exact tile interior. The Phase B video already contains the canonical watercolor hand art — no AI generation needed.
   - **Lesson:** if the asset already exists in the rendered video, extract it. Don't re-generate.

3. **Kling kept generating fire/flame hands.**
   - Prompt: *"hands rubbing up and down like trying to get warm on a cold day"* → Kling output: realistic hands with a glowing flame between them.
   - Root cause: Kling/Seedance models have a strong **friction/warmth/cold-day → fire** prior. "Get warm" triggers fire generation regardless of the watercolor style instruction.
   - **Fix:** abandon Kling for this task. Use Python pixel-warp animation against the existing watercolor still.
   - **Lesson:** Kling has model-bias false positives on conceptual prompts. If the source art is already correct and you only need motion, a deterministic Python warp beats a generative model. (See Rule 8 / §8 in CLAUDE.md for the broader anti-lipsync class of model biases.)

4. **WaveSpeed timeout on large base64 payloads.**
   - Default urllib `urlopen` timed out submitting full-resolution PNG + video as base64.
   - **Fix:** `subprocess.run(["curl", "--max-time", "120", ...])` instead of urllib for large submissions.

5. **v1 Python animation moved the whole screen instead of just the hands.**
   - Naïve forward warp shifted every pixel → background, frame border, and white interior all moved together.
   - **Fix:** Kim drew a palm seam via `path_picker.html`. Inverse mapping: each output pixel asks "where did I come from in the source?" — left hand pulled from above-seam, right hand from below-seam, with offsets oscillating per frame.

6. **imageio macro-block resize bug (the worst one).**
   - Source tile interior: 364×539 pixels.
   - imageio auto-pads video dimensions to the nearest multiple of 16 → wrote output as 368×544.
   - When composited over the original 1280×720 frame, the 4px-right + 5px-down padding made the animated tile **bleed into the brown frame border** at the bottom-right corner.
   - **Fix:** stop using imageio for output. Pipe raw frames directly to ffmpeg via `-f rawvideo -pix_fmt rgb24 -s 364x540` → ffmpeg respects exact dimensions. Setting `macro_block_size=1` in imageio is a partial fix but the rawvideo pipe is more reliable.

7. **Edge-clamp smear (`np.clip` repeating edge pixels).**
   - When the inverse-mapped source coordinate fell outside the source image, `np.clip(x, 0, W-1)` returned the edge pixel → the rightmost column of skin tone smeared into the brown border zone.
   - **Fix:** out-of-bounds (OOB) source coordinates → output white pixel `(255, 255, 255)`, NOT clamped to the edge. White matches the tile interior background; smearing is invisible.

8. **H.264 odd-height encoding error.**
   - Tile interior was 364×**539**. libx264 requires both width AND height to be even.
   - Error from ffmpeg: `width or height not divisible by 2`.
   - **Fix:** pad height to **540** (one row of white at the bottom — invisible because the tile interior is white-bordered). Always: `height = source_h + (source_h % 2)`.

9. **Wrong tile time range.**
   - First attempt animated `t=14s → t=142s` — the entire 128-second window where *some* watercolor cue tile was visible.
   - But the cue position holds **four different tiles** in sequence (title card, hands, orb v1, orb v2). Animating the whole window made the title card and orbs warp into hands.
   - **Fix:** scan the Phase B video frame-by-frame, sample the tile's center pixel color, and detect segment boundaries by color change.
   - **Result:** the hands tile is **t=30s → t=42s** (12 seconds). All other times leave the original frames untouched.

10. **Wrong source crop (280×473 stretched to 364×540).**
    - First source was a too-tight hand crop, stretched up to fill the tile interior → distorted proportions.
    - **Fix:** extract the tile interior **exactly** from the Phase B frame at `t=35s`, pixel coordinates `x=79..443, y=55..594` — that's the native 364×539 tile interior, no resize.

11. **Frame border moving (the final boss).**
    - Even with the correct source and correct dimensions, the brown frame border was being warped because the threshold "is this a hand pixel?" used `pixel_value < HAND_THR` (dark = hand). The brown border is also dark → it qualified as "hand" and got animated.
    - **Fix: static mask from the original source.** Compute once, before any frame loop:
      ```
      is_art = (NOT pure_white) AND (NOT dark_border)
             ≈ (R<250 OR G<250 OR B<250) AND (R>HAND_THR OR G>HAND_THR OR B>HAND_THR)
      ```
      Skin-tone watercolor pixels = ~20% of tile area. Mask is binary, computed once. During animation: only `is_art` pixels get inverse-mapped from the warped source; everything else (pure white interior, brown border) copies straight from the original frame and stays pixel-identical.

### 2.2 The FINAL working process (`animate_hands_v5` approach)

**Inputs:**
- Phase B video: `Production/Event_1/exports/arc1_event1_phase_b_v1_20260420.mp4`
- Source tile (extracted from the video at `t=35s`, cropped `x=79:443, y=55:594`): `Production/Event_1/phase_b_hands_source.png`, exactly 364×539
- Kim's palm seam path (from `path_picker.html` against the source still): `PATH_PTS` list of normalized points, e.g.:
  ```
  [[0.231, 0.779], [0.299, 0.778], [0.299, 0.735], [0.392, 0.743],
   [0.453, 0.731], [0.449, 0.696], [0.541, 0.685], [0.544, 0.656], …]
  ```

**Locked parameters:**

| Param | Value | Purpose |
|---|---|---|
| `AMPLITUDE` | 14 px | Max vertical offset for hand rub motion |
| `CYCLES` | 3.0 | Number of full up-down rubs in the segment |
| `FPS` | 24 | Output framerate (matches Phase B source) |
| `BLEND_R` | 6 px | Feather radius across the seam line (left↔right hand transition) |
| `TILE_X0:TILE_X1` | 79 : 443 | Tile interior horizontal bounds in 1280×720 frame |
| `TILE_Y0:TILE_Y1` | 55 : 594 | Tile interior vertical bounds (539 px tall) |
| `OUT_H` | 540 | Padded output height (539 → 540 for libx264 even-height) |
| `SEGMENT_START` | 30.0 s | First frame of hands tile in Phase B |
| `SEGMENT_END` | 42.0 s | Last frame of hands tile (12 s total) |
| `HAND_THR` | 220 (per-channel) | Threshold below which a pixel counts as "potentially border" |
| OOB policy | white `(255,255,255)` | Out-of-bounds inverse-mapped pixels render as white, NOT edge-clamped |
| Output encoding | `ffmpeg -f rawvideo -pix_fmt rgb24 -s 364x540 -r 24 -i - -c:v libx264 -pix_fmt yuv420p` | Raw pipe, NOT imageio |

**Algorithm:**

1. Load source tile (364×539) → pad to 364×540 with one row of white at bottom.
2. Compute static mask `is_art` from original source: `(NOT pure_white) AND (NOT dark_border)`. Cache as a 2D boolean array.
3. Build per-row seam x-position by interpolating Kim's `PATH_PTS` against tile y-coordinates. This gives `seam_x[y]` for every row.
4. For each frame `t` in `[30.0, 42.0]` at 24 fps (288 frames):
   - Compute oscillation phase `θ = 2π * CYCLES * (t - 30.0) / 12.0`.
   - Left-hand offset: `dy_L = +AMPLITUDE * sin(θ)`.
   - Right-hand offset: `dy_R = -AMPLITUDE * sin(θ)` (counter-phase rub).
   - For every output pixel `(x, y)`:
     - If NOT `is_art[y, x]` → copy original source pixel (border/white stays static).
     - Else if `x < seam_x[y] - BLEND_R/2` → inverse-map from `(x, y - dy_L)` (left hand region).
     - Else if `x > seam_x[y] + BLEND_R/2` → inverse-map from `(x, y - dy_R)` (right hand region).
     - Else → linear blend across the `BLEND_R`-wide seam.
     - If inverse-mapped source coord is OOB → write white.
   - Write frame to ffmpeg rawvideo stdin pipe.
5. ffmpeg encodes 364×540 H.264 yuv420p clip.
6. ffmpeg overlay step composites the animated tile onto the original Phase B at exact pixel position `(x=79, y=55)` only during `[30.0s, 42.0s]`. Outside that window, original frames pass through untouched.
7. Audio re-muxed from original Phase B (`-c:a copy`).

**Result:** brown frame border perfectly static, white tile interior perfectly static, only the watercolor hands rub. Title card (t=14-29), orb v1 (t=42-81), and orb v2 (t=82-141) all untouched.

---

## Section 3 — Phase B Cue Tile Layout for Event 1 M1

**Frame size:** 1280×720, 24 fps.
**Cue tile pixel bounds (interior, excluding brown frame + cream mat):** `x = 79..443`, `y = 55..594` → 364×539 interior.

**Time segments (verified by color sampling the tile center across all frames):**

| Segment | Time range | Content | Animate? |
|---|---|---|---|
| Pre-tile | `t = 0..14s` | Cedric narration over Phase B background, no cue tile | — |
| Title card | `t = 14..29s` | "The Magic Hands Spell" framed text card | NO |
| **Hands** | **`t = 30..41s`** (effectively 30..42 — 12s window) | **Pressed watercolor hands. THE TILE TO ANIMATE.** | **YES (rub motion)** |
| Orb v1 | `t = 42..81s` | Hands cupping a glowing orb (variant 1) | NO |
| Orb v2 | `t = 82..141s` | Hands cupping a glowing orb (variant 2) | NO |
| Post-tile | `t = 142..148s` | Outro narration | — |

**Tile boundary detection method (use this any time tile timings need to be re-verified):**

```python
# Pseudocode — sample one pixel at the tile's center across all frames
import cv2, numpy as np
cap = cv2.VideoCapture(phase_b_path)
fps = cap.get(cv2.CAP_PROP_FPS)
n   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
center_x, center_y = (79+443)//2, (55+594)//2
colors = []
for i in range(n):
    ok, fr = cap.read()
    if not ok: break
    colors.append(fr[center_y, center_x].copy())
# Now find runs where the color jumps significantly → segment boundaries
for i in range(1, len(colors)):
    if np.linalg.norm(colors[i].astype(int) - colors[i-1].astype(int)) > 60:
        print(f"boundary at t={i/fps:.2f}s")
```

This caught the four-tile-sequence reality. Without this scan, the first attempt animated the whole 14-142 window and warped the title card.

---

## Section 4 — General Animation Lessons

1. **Never use imageio for H.264 output when exact dimensions matter.** imageio silently macro-block-pads to multiples of 16, breaking pixel alignment in any composite. Use `ffmpeg -f rawvideo -pix_fmt rgb24 -s WxH` piped from your Python frame loop.
2. **H.264 (libx264) requires BOTH width and height to be even.** If either is odd, pad by one pixel. Always: `out_h = src_h + (src_h % 2)`.
3. **Inverse mapping > forward mapping.** Forward mapping (push source pixel → output) leaves holes. Inverse mapping (each output pixel pulls from a source coordinate) is hole-free and lets you cleanly handle OOB cases.
4. **Static mask approach for animating art inside a framed illustration.** Compute a binary mask from the **original** source (which pixels are art vs. which are frame/border/background). During animation, only mask pixels get warped; non-mask pixels copy straight through. This is the only way to keep frames perfectly static while content animates.
5. **OOB → fill color, not edge-clamp.** When inverse-mapped source coordinates fall outside the source image, return the background color (white in this case), not the nearest edge pixel. Edge-clamping smears the rightmost (or top/bottom) column across the OOB region — visibly wrong.
6. **PIL `ImageChops.screen()` for screen-blending magic overlays.** ffmpeg `blend=all_mode=screen` is unreliable when imageio wrote any intermediate file (colorspace metadata = `unknown` poisons the blend). Banned for magic compositing.
7. **Always re-mux audio after a Python composite.** imageio video writers drop audio without warning. Locked step: `ffmpeg -i video_only.mp4 -i original.mp4 -map 0:v -map 1:a -c copy output.mp4`.
8. **Distinguish "which pixels animate" from "which pixels freeze" up front.** The single biggest time-sink in this session was border pixels secretly getting animated because the threshold was based on darkness. Compute the mask first, verify it visually (dump the mask as a PNG), THEN run the animation loop. Saves hours.

---

## Section 5 — Kling / WaveSpeed Lessons

1. **Kling false positives on conceptual prompts.**
   - Friction / warmth / cold day → fire generation, regardless of art-style instructions.
   - "Get warm" → flame between hands (multiple confirmed false positives this session).
   - This is the same model-bias class as Seedance's Chinese-phoneme talking-head bias (CLAUDE.md §8). Kling is NOT immune; it just has a different bias surface.
2. **When to abandon Kling for Python warp.**
   - If the source art already exists and is correct, and the only thing missing is motion → use deterministic Python warp.
   - If the motion is constrained (linear oscillation, simple translation, looping rub) → Python wins on cost, speed, determinism, and zero false-positive risk.
   - Kling earns its keep when the motion is organic, multi-DOF, or character-based (Tessa head turn, Chipper wing flap) AND lipsync isn't downstream.
3. **WaveSpeed timeout fix on large base64 payloads.**
   - urllib's default timeout silently aborts on big PNG+video bodies.
   - Use `subprocess.run(["curl", "--max-time", "120", "--data-binary", "@payload.json", url])`.
   - Saves debug time when the API is fine but the client is timing out.
4. **Switching models is one endpoint string change.** Both Kling v3.0 Pro and Seedance v1.5 Pro use the same WaveSpeed API key; only the path changes. No reconfiguration, no rebuilds. Log every model switch in `prod_activity_log`.

---

## Section 6 — Beat Generator Magic Trail Wiring (Verified)

Audited end-to-end against `storyboard_v43_prod.html` and `production_server.py` this session. **No gaps found.**

| Item | Status | Where |
|---|---|---|
| "✨ Magic Trail" option in animation method dropdown | ✅ | `storyboard_v43_prod.html` line ~4284 |
| "Open Path Picker ↗" button opens `/magic?scene_key=m1_e1_res_<beat_id>&bg=<bg_url>` | ✅ | storyboard JS `openPathPicker()` |
| `/magic` route serves `path_picker.html` | ✅ | `production_server.py` |
| `path_picker.html` auto-loads background via `GET /api/magic/resolve_bg` | ✅ | `path_picker.html` onload handler |
| `POST /api/magic/submit_path` runs `magic_compositor.py` | ✅ | `production_server.py` route handler |
| Result registered in `prod_magic_clips` | ✅ | inside submit_path handler |
| Result registered in `prod_activity_log` | ✅ | inside submit_path handler (kim_verdict NULL until approval) |
| Manual override panel with `path_pts` textarea | ✅ | `path_picker.html` |
| All `fetch()` calls use absolute `http://localhost:<PORT>/api/...` | ✅ | per Rule 32; verified |

**Tested call shape:**
```
GET  /magic?scene_key=m1_e1_res_<beat_id>&bg=<background_url>
GET  /api/magic/resolve_bg?scene_key=...
POST /api/magic/submit_path
       body: { scene_key, path_pts, style:"tessa_ori", bg_url }
       returns: { magic_clip_id, preview_still_url, full_video_url, sha256, file_size_bytes }
```

**For the next session:** if a new visible-magic beat is needed, do NOT write a one-off script. Open the storyboard, pick "✨ Magic Trail" on the resolution beat, click through path_picker, submit. The pipeline is fully wired.

---

## Appendix A — File / Asset Reference

| Purpose | Path |
|---|---|
| Phase B canonical (LD-348) | `Production/Event_1/exports/arc1_event1_phase_b_v1_20260420.mp4` |
| Hands tile source (extracted t=35) | `Production/Event_1/phase_b_hands_source.png` (364×539) |
| Magic compositor | `Production/tools/magic_compositor.py` |
| Magic compositor v5 (Tessa-specific) | `composite_magic_path_tessa.py v5` (referenced in memory file `project_magic_compositor_system.md`) |
| Path picker UI | `Production/tools/path_picker.html` |
| Magic tech spec | `Production/tools/VISIBLE_MAGIC_TECH_SPEC_v1.md` |
| Magic prior lessons | `Production/tools/VISIBLE_MAGIC_LESSONS_LEARNED_v2.md` |
| Storyboard (with Magic Trail wiring) | `Production/tools/build_storyboard.py` outputs → `storyboard_v43_prod.html` |
| Production server (routes) | `Production/tools/production_server.py` |
| Watercolor library | `Production/assets/watercolor_library/` |

## Appendix B — Locked Decisions Referenced

- **LD-348** `PHASE_B_M1_DELIVERABLE_SHIPPED_20260420` — `arc1_event1_phase_b_v1_20260420.mp4` is the canonical Phase B
- **LD-203** Phase B watercolor cues are framed (brown border + cream mat + white interior); never bare cutouts
- **LD-280** Single-MP4 atomic playback architecture (governs why we bake animations into the video, not runtime composite)
- **CLAUDE.md Rule 8** — model-bias class (Kling/Seedance false positives)
- **CLAUDE.md Rule 19** — no error paths in shipping production
- **CLAUDE.md Rule 31** — Directus before disk for "the approved X"
- **CLAUDE.md Rule 32** — absolute `http://localhost:<PORT>` URLs in production tool fetch() calls

## Appendix C — One-Line Summary Per Failure Mode (for quick scanning next session)

1. Wrong Phase B source → query Directus first
2. Wrong source image → extract from existing rendered video, don't regenerate
3. Kling fire/flame on warmth prompts → abandon Kling, Python warp
4. WaveSpeed timeout on big base64 → subprocess curl --max-time 120
5. v1 warp moved everything → inverse map + Kim's seam path
6. imageio macro-block 364→368, 539→544 → ffmpeg rawvideo pipe
7. Edge-clamp smear → OOB → white, not clamp
8. H.264 odd height 539 → pad to 540
9. Wrong tile time window 14-142 → scan for color-change boundaries → 30-42
10. Wrong source crop 280×473 stretched → exact tile interior x=79:443 y=55:594
11. Frame border moving → static mask from original source: art = not-white AND not-dark-border

— end of document —

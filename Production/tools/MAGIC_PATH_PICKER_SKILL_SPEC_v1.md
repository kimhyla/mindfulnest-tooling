# Magic Path Picker — Skill Spec v1
# Production/tools/MAGIC_PATH_PICKER_SKILL_SPEC_v1.md
#
# Spec for the `magic-path-picker` skill + `visible-magic` render skill.
# Written 2026-04-24 after 3-Opus-agent debate.
# Governs: path_picker.html, scene_registry.yaml manual_path field,
#          geometry_detector.py override, magic_compositor.py render flow.
# ──────────────────────────────────────────────────────────────────────────

---
name: magic-path-picker
description: |
  Sets the path for a visible-magic trail or burst on any scene still, then
  renders the approved magic overlay as a preview still and full video.
  Trigger on: 'produce visible magic', 'magic trail', 'magic path',
  'where should the magic go', 'set magic path', 'magic burst',
  'render magic', 'usual process for making visible magic',
  'magic overlay', 'compositor', 'add magic to', or any request to
  position or render a magic effect on a scene background.
---

---

## What This Skill Does

Gives Kim a one-and-done workflow to define EXACTLY where a magic trail or
burst should appear on any scene background still, then renders it.

**The core problem it solves:** Previous approaches (color detection, optical
flow, manual coordinate guessing, black-pixel extraction from Preview drawings)
all lose information before coordinates reach the compositor. This skill
eliminates ALL inference — Kim clicks points on the scene image, those exact
pixels become the path.

**What this skill does NOT do:**
- Generate creative decisions about where magic should go (Kim decides)
- Re-detect geometry automatically (that's the fallback path for future batch)
- Re-use old coordinates from memory (always reads scene_registry.yaml fresh)
- Skip any step to save time (every gate is mandatory)

---

## The Two Sub-Skills

This spec defines two tightly coupled sub-skills invoked in sequence:

| Sub-skill | Trigger | What it does |
|---|---|---|
| **path-picker** | "where should the magic go" / first-time scene | Opens path_picker.html; Kim clicks path; writes manual_path to registry |
| **magic-render** | "render magic" / "produce visible magic" | Reads manual_path from registry; renders preview + video |

If `manual_path` already exists in scene_registry.yaml for the scene → skip
path-picker, go straight to magic-render. Kim can always re-run path-picker
to override a stored path.

---

## Cardinal Rules

These override everything else.

### Rule 1 — Never Guess Coordinates
If `manual_path` is absent from scene_registry.yaml and the scene has no
confirmed geometry, STOP and run path-picker. Do not infer from color
detection, optical flow, or old debug images. The ONLY valid source of path
coordinates is `manual_path` (Kim-clicked) or a geometry_detector result
with confidence ≥ 0.80 AND a prior Kim approval on record in Directus
`prod_magic_clips`. Anything else is a guess.

### Rule 2 — Preview Before Video
NEVER render the full video without first showing Kim a complete-trail
preview still (final frame). One approval gate, no exceptions.

### Rule 3 — scene_registry.yaml Is the Single Source of Truth
All path data lives in scene_registry.yaml. Never read paths from old debug
images, memory, or hard-coded constants in magic_compositor.py. If the
registry entry doesn't exist for the scene, create it from the template
before proceeding.

### Rule 4 — path_picker.html Is the ONLY Way to Input Path Coordinates
Kim must not be asked to draw in Preview, type coordinates manually, or
describe the path in words. The ONLY valid input method is clicking in
path_picker.html. If path_picker.html is not available (missing, can't open
in browser), STOP and fix it before continuing — do not fall back to drawing.

### Rule 5 — Register to Directus prod_magic_clips
Every approved magic render (preview approved + video rendered) gets
registered in Directus `prod_magic_clips`. If registration fails, warn Kim
and write to PENDING_REGISTRATIONS.json. Do not skip.

---

## Step-by-Step Workflow (Mandatory — No Steps May Be Skipped)

### PHASE 0 — Identify the Scene

**Claude does:**
1. Determine the `scene_key` (e.g., `m1_e1_res_beat_01_heartwood`).
   - If Kim said "produce visible magic" with no scene specified → ask:
     "Which scene? Give me the module, event, and beat, or say 'heartwood'."
   - If Kim gave a scene context → derive the key from it.

2. Read `Production/tools/scene_registry.yaml`. Find the entry for `scene_key`.
   - If entry missing → create it from the TEMPLATE block at the bottom of
     scene_registry.yaml. Fill in archetype, module_id, event_id, beat, style.
     Ask Kim to confirm before proceeding.

3. Check for `manual_path` field in the entry.
   - **Present** → skip to PHASE 2 (magic-render). Tell Kim:
     "Found existing path for [scene_key]: [N] points. Rendering now.
      Say 'repick path' to replace it."
   - **Absent** → continue to PHASE 1 (path-picker).

4. Identify the background still path from `source_asset_query` or ask Kim
   for it. Verify the file exists on disk. If missing → STOP and ask Kim.

---

### PHASE 1 — Path Picker (runs only when manual_path is absent)

**Claude does:**
1. Confirm `Production/tools/path_picker.html` exists. If missing → build it
   from the spec in §Appendix A of this document before continuing.

2. Open path_picker.html in the default browser:
   ```bash
   open "Production/tools/path_picker.html"
   ```

3. Tell Kim exactly this (verbatim):
   > "path_picker.html is open in your browser. Drag **[background_filename]**
   > onto the grey drop zone. Then click 3–8 points along your intended path
   > — dots will appear connected by a line. Right-click to undo the last
   > point. When satisfied, click **Copy YAML** and paste it here."

4. Wait for Kim to paste the YAML block. It will look like:
   ```yaml
   manual_path:
     - [0.000, 0.790]
     - [0.213, 0.762]
     - [0.401, 0.730]
   ```

5. Validate the pasted YAML:
   - All values must be floats between 0.0 and 1.0
   - Minimum 2 points, maximum 20 points
   - X values must be monotonically increasing (left-to-right trail) OR
     decreasing (right-to-left) — not random. If out of order, flag to Kim.
   - If validation fails → tell Kim what's wrong and ask her to re-click.

6. Write `manual_path` into scene_registry.yaml under the correct scene key.
   Add a comment: `# Kim-clicked via path_picker.html, [date]`.

7. Tell Kim: "Path saved — [N] points from ([x0],[y0]) to ([xN],[yN]).
   Proceeding to preview render."

---

### PHASE 2 — Magic Render

**Claude does (Steps A–D must run in order):**

#### Step A — Generate debug overlay (path-on-background confirmation)

Run:
```bash
python3 Production/tools/geometry_detector.py \
  --scene [scene_key] \
  --bg [background_still_path] \
  --confirm
```

This produces a debug PNG showing the stored `manual_path` points as red dots
on the actual scene background (no grid — the grid was only for calibration).

Open the debug PNG for Kim:
```bash
open [debug_output_path]
```

Ask Kim: "Here are your [N] path points overlaid on the scene. Do these look
right, or do you want to repick?"

- **Kim says yes / looks good** → continue to Step B
- **Kim says repick** → delete `manual_path` from scene_registry.yaml,
  return to PHASE 1 Step 2

**This is the ONLY correction gate. After Kim approves here, no more
coordinate iteration.**

#### Step B — Render complete-trail preview still (final frame)

```python
from magic_compositor import MagicCompositor
import yaml

reg = yaml.safe_load(open("Production/tools/scene_registry.yaml"))
scene = reg[scene_key]
path_pts = [tuple(pt) for pt in scene["manual_path"]]
style = scene.get("style", "tessa_ori")

mc = MagicCompositor(
    background_path=background_still_path,
    path_pts=path_pts,
    style=style,
    duration=3.5,
    fps=24,
    seed=99,
    output_dir="Production/Event_[N]/kling_clips",
    label=f"{scene_key}_approved",
)
total_frames = int(mc.duration * mc.fps)
preview_path = mc.render_preview(frame_idx=total_frames - 2)
```

Open the preview:
```bash
open [preview_path]
```

Tell Kim: "Complete trail preview — this is what the final frame looks like.
Approve to render the full video, or say 'too bright', 'too faint',
'reposition' for adjustments."

- **Kim approves** → continue to Step C
- **Kim says 'too bright' / 'too faint'** → adjust `sparkle_gain` / `ambient_gain`
  in STYLES["tessa_ori"] and re-render preview. One adjustment only — if
  still wrong, log as a style issue and escalate.
- **Kim says 'reposition'** → return to PHASE 1 Step 2 (full repick)

#### Step C — Render full video

```python
video_path = mc.render_video()
```

This renders the full animation (3.5s at 24fps = 84 frames).

Open the result:
```bash
open [video_path]
```

Tell Kim: "Full video rendered: [filename] ([duration]s). Approve to register
and lock, or flag any issue."

- **Kim approves** → continue to Step D
- **Kim flags an issue** → determine if it's a path issue (→ repick),
  style issue (→ adjust style params), or compositor bug (→ log to lessons
  learned and escalate)

#### Step D — Register in Directus + lock scene_registry

**Two-Write Rule — both writes are mandatory:**

**Write 1: prod_magic_clips**
```python
import urllib.request, json, datetime
# Read credentials from Production/API_KEYS_MASTER.md
payload = {
    "scene_key": scene_key,
    "module_id": scene["module_id"],
    "event_id": scene["event_id"],
    "beat": scene["beat"],
    "style": style,
    "archetype": scene["archetype"],
    "manual_path": scene["manual_path"],
    "preview_path": preview_path,
    "video_path": video_path,
    "geometry_confirmed_at": datetime.datetime.utcnow().isoformat(),
    "status": "approved",
}
# POST to /items/prod_magic_clips
```

**Write 2: prod_activity_log**
```python
activity = {
    "session_date": datetime.date.today().isoformat(),
    "module_id": scene["module_id"],
    "activity_type": "magic_render_approved",
    "description": f"Magic trail approved for {scene_key}. "
                   f"Path: {len(scene['manual_path'])} points. "
                   f"Style: {style}. Video: {video_path}",
    "output_file": video_path,
    "kim_verdict": "approved",
}
# POST to /items/prod_activity_log
```

If either write fails → write to `Production/Event_[N]/PENDING_REGISTRATIONS.json`
and warn Kim. Do NOT skip registration silently.

Tell Kim: "Registered. Scene [scene_key] is locked. Magic render complete."

---

## scene_registry.yaml — manual_path Field Spec

Add this field to any scene entry where Kim has clicked a path:

```yaml
m1_e1_res_beat_01_heartwood:
  archetype: "ground_left_to_target"
  # ... existing fields ...

  # manual_path: Kim-clicked via path_picker.html, 2026-04-24.
  # AUTHORITATIVE — geometry_detector uses this with confidence=1.0,
  # skipping all color/optical-flow detection. To repick: delete this
  # field and run the magic-path-picker skill.
  manual_path:
    - [0.000, 0.790]    # origin: left edge stone floor
    - [0.213, 0.762]    # waypoint 1
    - [0.401, 0.730]    # target: altar step edge
```

**Schema rules:**
- Values are `[x_fraction, y_fraction]` pairs. x=0 is left edge, y=0 is top.
- Minimum 2 points (origin + target). Maximum 20.
- `manual_path` takes absolute priority over `manual_origin`, `manual_target`,
  and all archetype-based detection. If both exist, `manual_path` wins.
- Comment each point with a human-readable label (floor, step, altar, etc.)
  so future sessions can sanity-check without re-examining the image.

---

## geometry_detector.py — Required Change (4 Lines)

At the top of `GeometryDetector.infer()`, add the manual_path override:

```python
def infer(self, scene_key, source_clip=None, bg_still=None):
    scene = self.registry.get(scene_key, {})

    # HIGHEST PRIORITY: Kim-clicked path from path_picker.html
    if "manual_path" in scene and scene["manual_path"]:
        path_pts = [tuple(float(v) for v in pt) for pt in scene["manual_path"]]
        return path_pts, 1.0   # confidence=1.0, no detection needed

    # ... existing archetype dispatch below ...
```

This ensures `manual_path` is always used if present, regardless of what
other fields exist (archetype, color_target, floor_perspective, etc.).

---

## Appendix A — path_picker.html Full Spec

Build this file at `Production/tools/path_picker.html`.

### What it must do

1. **Drop zone:** User drags a PNG/JPEG onto the page. The image renders
   inside a `<canvas>` at its native pixel dimensions (no scaling).

2. **Click to place points:** Each left-click on the canvas:
   - Records `(x / canvas.width, y / canvas.height)` as a normalized point
   - Draws a filled red circle (radius 8px) with a white border at that pixel
   - Draws a red line from the previous point to this one
   - Displays the point number next to the dot

3. **Right-click to undo:** Removes the last point and redraws.

4. **Live coordinate display:** A small overlay in the top-right corner shows
   the last clicked point as `x=0.213, y=0.762` updating in real-time on
   mousemove.

5. **Copy YAML button:** Outputs the following to clipboard:
   ```yaml
   manual_path:
     - [0.000, 0.790]
     - [0.213, 0.762]
     - [0.401, 0.730]
   ```
   Values are rounded to 3 decimal places. Shows a "Copied!" flash on the button.

6. **Clear button:** Removes all points and redraws the clean image.

7. **No external dependencies:** Vanilla HTML + JS only. No npm, no CDN.
   Must work offline with `open path_picker.html` in any browser.

### What it must NOT do
- Scale or resize the image (would corrupt coordinates)
- Smooth, interpolate, or reorder clicks
- Auto-detect anything about the path
- Send data anywhere (no network calls)

### Coordinate precision
Normalize to 3 decimal places: `(clickX / img.naturalWidth).toFixed(3)`.
Use `img.naturalWidth` / `img.naturalHeight`, NOT `canvas.offsetWidth`,
to ensure coordinates are always relative to the original image resolution
regardless of browser zoom or canvas CSS sizing.

---

## Appendix B — Governance Checklist

File: `Production/governance/magic-path-picker_governance.md`

Before any render step, verify:

- [ ] `scene_registry.yaml` entry exists for the scene
- [ ] `manual_path` field present with ≥ 2 valid points (or path-picker ran)
- [ ] Background still file exists on disk at the path in source_asset_query
- [ ] Style is `tessa_ori` (only approved style in V1 per LD-398)
- [ ] Debug overlay shown to Kim and approved (PHASE 2 Step A gate)
- [ ] Complete-trail preview shown to Kim and approved (PHASE 2 Step B gate)
- [ ] Full video opened for Kim review before registration (PHASE 2 Step C gate)
- [ ] Both Directus writes completed: prod_magic_clips + prod_activity_log
- [ ] No coordinate guessing at any step (Rule 1)

---

## Why Each Step Exists (Failure History)

| Step | Why it's mandatory |
|---|---|
| Phase 0: registry check | Prevents running path-picker when path already confirmed |
| Phase 0: bg file check | Prevents silent fallback to wrong background |
| Phase 1: path_picker.html only | Drawing → black-pixel extraction lost Kim's path 4–5× |
| Phase 1: YAML validation | Prevents random-order or out-of-bounds coordinates reaching compositor |
| Phase 2A: debug overlay gate | Shows Kim her clicked points on the REAL scene (not grid) before any render cost |
| Phase 2B: complete-trail preview | Shows Kim the FINAL frame — mid-animation previews confused "is the trail done?" question |
| Phase 2B: no coordinate iteration after approval | All prior sessions burned time adjusting coordinates AFTER seeing wrong renders |
| Phase 2C: full video before registration | Prevents locking wrong results in Directus |
| Phase 2D: two-write rule | Invisible assets get regenerated or lost |
| Rule 4: path_picker.html only | Every alternative (drawing, text description, guessing) has failed |

# Magic Path Picker — Governance Gate

**Skill:** magic-path-picker  
**Created:** 2026-04-24  
**Severity:** HIGH — wrong path coordinates produce wrong magic renders; all prior failures traced to coordinate input loss

## Governing Documents

1. `Production/tools/MAGIC_PATH_PICKER_SKILL_SPEC_v1.md` — full skill spec (authoritative)
2. `Production/tools/scene_registry.yaml` — single source of truth for all path data
3. `Production/tools/geometry_detector.py` — `manual_path` override (confidence=1.0)
4. `Production/tools/magic_compositor.py` — render engine, tessa_ori style
5. `Production/VISIBLE_MAGIC_LESSONS_LEARNED_v4.md` — failure history
6. `CLAUDE.md` Rule 19 — no shortcuts, no error paths

## Why This Skill Exists (Failure History)

Kim drew the correct path 4–5 times across multiple sessions. Every time the
information was lost because:

| Failure mode | Root cause |
|---|---|
| Preview auto-smoothed freehand lines | OS drawing tool behavior, not fixable |
| Black-pixel extraction picked up scene darks | Ill-posed: cannot color-key black from scene |
| Manual origin/target coordinate guessing | ~130px error per round; multiple correction rounds needed |
| Mid-animation preview shown as "final" | Looked incomplete; caused confusion about endpoint |
| Color detection found wrong object | Bowl contents (y≈0.54) not step edge (y≈0.73) |

The ONLY reliable input method is `path_picker.html` click-to-place. This
governance file enforces that nothing substitutes for it.

## Startup Checklist (Run Before Any Path-Related Work)

### 1. Scene Registry Check
- [ ] `scene_registry.yaml` entry exists for the scene_key
- [ ] If entry missing → create from TEMPLATE block, confirm with Kim before proceeding
- [ ] `manual_path` field present? → YES: skip to render checklist below
- [ ] `manual_path` absent? → MUST run path_picker.html before ANY render

### 2. Input Method Gate (BLOCKING)
- [ ] Is `manual_path` absent from registry? → open path_picker.html. STOP if:
  - Kim offers to draw in Preview → decline; redirect to path_picker.html
  - Kim offers to type coordinates manually → decline; redirect to path_picker.html
  - Kim describes path in words ("it goes from left to the altar") → decline;
    redirect to path_picker.html
  - path_picker.html file is missing → build it from spec before proceeding
- [ ] YAML from path_picker.html validated: all values in [0,1]; ≥2 points;
  x-values left-to-right or right-to-left (not random); no duplicates

### 3. Background Still Check
- [ ] Background still file exists on disk at path from source_asset_query
- [ ] File is PNG or JPEG (not a video clip)
- [ ] File is the CORRECT still for this scene_key (verify filename matches scene)

### 4. Style Check
- [ ] Style is `tessa_ori` (only approved style in V1 per LD-398 MAGIC_STYLE_TESSA_ORI_V1)
- [ ] If a different style is requested → STOP, require new LD from Kim

### 5. Render Gate Sequence (ALL three gates mandatory, in order)

**Gate A — Debug overlay (path on real background):**
- [ ] geometry_detector `--confirm` debug PNG generated and opened for Kim
- [ ] Kim said "yes" / "looks good" → proceed
- [ ] Kim said "repick" → delete manual_path, return to path_picker.html
- [ ] NO render proceeds without Gate A approval

**Gate B — Complete-trail preview still (final frame):**
- [ ] Preview rendered at `frame_idx = total_frames - 2` (NOT default frame 55)
- [ ] Preview opened in Preview.app for Kim
- [ ] Kim approved → proceed to full video render
- [ ] Kim flagged brightness/position → one adjustment, re-render preview; if still
  wrong, log issue to lessons-learned and escalate
- [ ] NO full video render proceeds without Gate B approval

**Gate C — Full video opened for Kim:**
- [ ] Full video rendered and opened via `open` command
- [ ] Kim approved → proceed to registration
- [ ] Kim flagged issue → determine: path issue (repick) / style issue (adjust params)
  / compositor bug (log to VISIBLE_MAGIC_LESSONS_LEARNED_v4.md)

### 6. Directus Registration (Two-Write Rule — BOTH mandatory)
- [ ] Write 1: `prod_magic_clips` — scene_key, module_id, event_id, beat, style,
  manual_path, preview_path, video_path, geometry_confirmed_at, status=approved
- [ ] Write 2: `prod_activity_log` — date, module_id, activity_type=magic_render_approved,
  description, output_file, kim_verdict=approved
- [ ] If either write fails → write to PENDING_REGISTRATIONS.json, warn Kim,
  resolve before session ends

## What Is NEVER Allowed

- Rendering from coordinates not in `manual_path` (no guessing, no old debug
  images, no hardcoded values that differ from the registry)
- Skipping Gate A (debug overlay) to save time
- Showing a mid-animation frame as the "final" preview
- Using any drawing/extraction input method other than path_picker.html
- Running path-picker for a scene that already has an approved `manual_path`
  without Kim explicitly saying "repick" or "redo the path"
- Registering to Directus before Kim approves the full video

## Confidence Reference

| Source | Confidence | Behavior |
|---|---|---|
| `manual_path` (Kim-clicked) | 1.0 | Render immediately, no debug gate |
| auto-detected, confidence ≥ 0.80 | high | Render debug image, Kim approval required |
| auto-detected, 0.50–0.79 | medium | STOP, ask Kim to run path_picker.html |
| auto-detected, < 0.50 | low | STOP, mandatory path_picker.html |

# Visible Magic Lessons Learned v4
**Date:** 2026-04-24
**Produced by:** Three-agent diagnostic debate (Opus × 3: Forensic Historian + Technical Root Cause Analyst + Systems Architect)
**Supersedes:** `Production/tools/VISIBLE_MAGIC_LESSONS_LEARNED_v1.md`, `v2.md`, `Production/VISIBLE_MAGIC_LESSONS_LEARNED_v3.md`

---

## 0. One-Sentence Verdict

**The skill is a parameter snapshot of one approved scene, deployed as a general system, with no geometry auto-detection and no validated end-to-end stitch path — so every new shot requires a 20-iteration manual search that converges by luck, not design.**

---

## 1. What "First Time Works" Means (Kim-Approval Criteria)

Based on approved outputs (`beat_magic_path_v6.mp4`, `beat01_tessa_magic_composite_v4.mp4`, `beat02_event1_full_sequence_v1.mp4`) vs all rejected attempts:

| Attribute | Approved | Rejected |
|---|---|---|
| Color | Warm golden-white: `(255,255,238)` / `(255,252,200)` / `(255,240,155)` | Teal, blue, any cool hue |
| Shape | Flat "sparkle river" — wide in X, thin in Y | Worm, laser, floating orb, blob |
| Particle form | 1–3px crisp dots | Anything larger, gradient ellipses |
| Vertical anchor | Trail hugs floor pixels; `scatter_y_frac ≤ 0.032`, `SIGMA_Y ≤ 8px` | Anything floating above ground |
| Brightness | Visible but not blown out; 25% floor at origin | Invisible (v1–v5 day) OR nighttime-darkened scene |
| Motion | Smooth, no pop or jerk | Particles appearing mid-trail |
| Position | Pixel-verified foot/origin to pixel-verified target | Off by 17px+ = rejected |
| Timing | 4-phase: grow → hold → fade → optional burst | Trail and burst overlapping |

**"First time works"** = Kim sees preview PNG #1 and says "approve" or at most "brighter/dimmer" once. Zero position iteration. Zero aesthetic re-tuning.

---

## 2. Chronological Iteration History

### Phase 1 — Session 2026-04-22 morning: Heartwood (~12 iterations)
Target: 3–3.5s animated magic trail, left forest edge → Heartwood altar, daytime background `heartwood_3q_left_1456.png`.

- **v1–v4:** Per-orb PIL approach, full W×H image per orb, GaussianBlur. Render: 15–40 min. **Failure: magic invisible on daytime background.** Blend mode: screen (`out = 255 − (255−bg)(255−magic)/255`); bg=180, magic=100 → only +30 delta. Below perceptual threshold.
- **v5–v8:** Path geometry wrong. Endpoint at `(0.51, 0.60)` = altar TOP. **Magic visibly floated in air.**
- **Full-image darkening:** Made entire scene twilight. Magic visible. Kim: **"NO — you made it nighttime!"** REJECTED.
- **Corridor dimming (v10):** 60% darkness along path only. Shadow band visible. Session stopped.
- **Solid filled ellipse (v11):** Visible but "worm"-like trail. Rejected.
- **v5 (composite_magic_path_tessa.py):** `make_glow()` accumulation, endpoint corrected to `(0.47, 0.670)`. Used screen blend (`ImageChops.screen`). Preview generated. Session ended before Kim verdict. **This script is the "best current script" in memory but uses the banned blend mode.**

### Phase 2 — Session 2026-04-22 late: First approval
- **v6 (`composite_magic_path_v6.py` → `magic_compositor.py` class):** Pre-placed seeded particles (1800), 1–3px crisp dots, **additive blend**, anisotropic blur `[2.5, 18.0]`, auto-gain calibration `gain = 0.7 + (avg_lum/128)×0.6`. **Kim APPROVED → `beat_magic_path_v6.mp4`.** Locked as LD-398 `MAGIC_STYLE_TESSA_ORI_V1`. This is the ONLY unconditional win in the entire history.

### Phase 3 — Session 2026-04-23: Beat 2 production
- **Tessa exit-right:** v1–v2 had `t_head = t_frac` bug, odd-dimensions crash, `frame_idx` NameError. **v3 approved** (`tessa_exit_right_v3.py`). Foot coords found via vertical reference-line debug images — numpy luminosity peak initially found shell highlight at `y=0.898` instead of ground contact at `y=0.96`.
- **Runestone activation:** First coordinate guess off by **0.08 in both x and y (~130px error on 1676px frame)**. Fixed via numpy orange-channel color thresholding → `(0.362, 0.440)`. v3 rendered; Kim said "ok that's good enough" in preview context only — **status: pending, never fully approved.**
- **Full sequence v1 stitched** `beat02_event1_full_sequence_v1.mp4` — APPROVED.
- **Full sequence v2 — CATASTROPHIC FAILURE.** Assembled by filename pattern instead of registry. Pulled base Tessa clip (no magic) + wrong heartwood clip + pending runestone clip. Zero of three source clips were correct. Triggered creation of `resolve_stitch_clips()` registry gate — **written AFTER the failure, never independently re-validated.**

### Phase 4 — 2026-04-24: Skill codification
- `visible-magic` SKILL.md built, governance file, `magic_clip_registry.json`, `magic_position_finder.py`, VISIBLE_MAGIC_LESSONS_LEARNED_v3.md.
- **`wide_ori` style: still draft.** `burst` style: still pending/nonexistent.
- **`source_frame_sha` fields: NULL for all 4 KNOWN_SCENES entries.** The integrity gate never fires.
- Skill has survived **exactly one** end-to-end stitch validation (v1 full sequence). The mechanism that would catch v2-class failures was built after the failure.

---

## 3. The 5 Failure Mode Patterns (by frequency)

### 3.1 — Magic invisible on daytime backgrounds (v1–v11, most frequent)
**Physics:** Screen blend on bg=180 yields only +30 brightness delta — below JND for small particles. Daytime backgrounds have only 55–105 luminance headroom to white. The magic's warm-gold palette `(255,255,238)` is *chromatically identical* to scene highlights on warm stone, so it can't pop by hue. High-frequency floor texture (mossy stones, tile seams) camouflages 1–3px dots.

**Fixes tried:** Full image darkening (rejected), corridor dimming (rejected), higher density (insufficient).
**Fix that worked:** Additive blend + 1800 pre-placed particles + auto-gain calibration.
**Residual risk:** Gain calibration uses a single average scalar over the path. On scenes with non-uniform luminance or different background classes (nighttime, indoor), it will fail the same way.

### 3.2 — "Floating above the floor" trail (v5–v8, recurring)
**Root causes (all four must be fixed simultaneously):**
1. `SIGMA_Y=22` — ambient blur spreads glow 44–66px upward into sky zones
2. `abs(gauss(0, sigma))` scatter — hard horizontal slice (half-normal), creates midair band
3. Endpoint at altar TOP `(0.51, 0.60)` not step edge `(0.47, 0.670)` — trail anchors 90px above floor
4. `scatter_y_frac=40%` — vertical scatter extends trail into air

**Fix:** All four must change together: symmetric gauss scatter, `scatter_y_frac=0.032`, `AMBIENT_BLUR_YX=[6.0, 28.0]` (narrow Y, wide X), endpoint at step edge. Fixing any three of four leaves the problem visible.

### 3.3 — Wrong coordinates from eyeballing / numpy heuristics (all sessions)
**Magnitude:** 130px error on runestone (0.08 fractional × 1676px frame). 8 versions with wrong Heartwood endpoint.

**Specific failures:**
- Numpy luminosity peak: found Tessa shell highlight at `y=0.898` instead of ground contact at `y=0.96`
- Initial runestone guess: off by `(0.08, 0.08)` in both axes
- Altar top vs step edge: `(0.51, 0.60)` vs `(0.47, 0.670)` — 90px vertical error

**Fix:** Color-channel thresholding per stone color (6 lambdas), dense debug grid images at 0.01 increments, Kim red-circle confirmation on the debug PNG before committing to video render.
**Residual risk:** This is still a manual process. Any re-render with different source clip framing invalidates stored coordinates. The `source_frame_sha=null` fields mean the integrity gate never catches drift.

### 3.4 — Jerky / popping particles (v1–v5)
**Cause:** `n_samples = int(t_head × 50)` computed per frame → new particle pops into existence at a fresh random position every ~1.7 frames.

**Fix:** All N particles placed at initialization with fixed seed (`seed=42`), sorted by `ts`, per-frame filter `if ts > t_head: break`. Fully deterministic. This fix is in v6 and has not regressed.

### 3.5 — Stitched sequence pulls wrong clips (v2 full sequence)
**Cause:** ffmpeg concat driven by filename patterns, not registry. Base clip (no magic) substituted for approved magic version; pending runestone clip stitched as approved.

**Fix:** `resolve_stitch_clips()` reads `magic_clip_registry.json`, substitutes only `status=="approved"`, guards `Path(None)` for `source_clip=null` composite entries.
**Residual risk:** Registry lives in a loose JSON file separate from Directus. Never independently re-validated after the v2 failure that motivated it.

---

## 4. Why Stitching Became Necessary (Structural)

The compositor takes a **PNG still** as its background input. The Kling-generated character clip is a **video**. This creates a fundamental incompatibility:

- Compositing magic on every frame of a video requires re-running the compositor per frame, producing position jitter unless geometry is pixel-perfect
- Kling-generated character clips sometimes contain AI-rendered "shell magic" baked in for all 5 seconds — overlaying our ground trail creates 5 seconds of competing magic from two sources

**The canonical workaround** (correct and should be locked as the official pattern):
```
[Kling animated clip — character in motion] 
+ 
[ffmpeg-extracted last frame as held still + compositor magic trail on that still]
= ffmpeg concat → final clip
```

The workaround failed in v2 not because the concept is wrong but because clip resolution used filename patterns instead of a registry. The registry fix is correct; it is just located in a fragile JSON file instead of Directus.

---

## 5. The Parameter Space Problem

The `tessa_ori` style has approximately **25–30 tunable parameters**:

Particle system: `n_particles`, `dot_sizes` (6-entry list), `bright_range` (lo/hi), `twinkle_range` (lo/hi), `PALETTE` (3×RGB = 9 values), `palette_weights` (3), `seed`

Geometry: `scatter_x_frac`, `scatter_y_frac`, `SIGMA_Y`, path control points (N × 2 coords)

Blend: `sparkle_gain`, `ambient_gain`, `AMBIENT_BLUR_YX` (2), `sparkle_blur`, `ambient_mix`, blend mode, additive vs screen

Timing: `T_TRAIL_COMPLETE`, `T_FADEOUT_START`, `T_FADEOUT_END`, `T_DISSOLVE_START`, `T_DISSOLVE_END`

Auto-calibration covers **1 of 25**: the gain scalar. Everything else requires manual tuning. With qualitative Kim feedback ("floating," "blobs," "too bright") and 2–5 min per render, this is effectively a blind search in 25-D space. Expected convergence: hundreds of iterations. Empirical: ~20 before v6, then additional iterations per new scene.

Kim's discrete breakthroughs (reject screen blend, reject dots >3px, reject abs(gauss)) each eliminated one dimension from the search. The v3 "delta table" hand-authors a gradient for 7 of 25 dimensions. The remaining 18 are unguided.

---

## 6. Why the Skill Is Structurally Wrong

### 6.1 Wrong abstraction level
The skill exposes `MagicCompositor(bg, path_pts, style, ...)` requiring Claude to re-derive `path_pts` for every shot via an interactive pixel-verification dance. But 95% of MindfulNest magic shots are repeats of ~4 scene archetypes. The right interface is `render_magic(scene_key="m1_e1_res_beat_03")` — not coordinate reconstruction from scratch.

### 6.2 Wrong inputs
Fractional coordinates are a computed result, not a creative decision. Kim's actual creative inputs are semantic: "Tessa walks out the right side," "the magic lands on the orange stone." Coordinates should auto-detect from those semantics, not be derived manually.

### 6.3 Wrong assumption about Kim's decision surface
Kim's decision surface is scene-level ("yes that looks like my approved Tessa magic" / "wrong position"). Every time we surface a gain number, a sigma, or a scatter_y_frac, we're asking Kim the wrong question. The locked invariants are locked because Kim doesn't want to tune them — but the skill keeps allowing Claude to tune them anyway.

### 6.4 Geometry stored as data, not computed as function
`KNOWN_SCENES` stores `{path: [(x,y),...], source_frame_sha: null}`. Frozen pixel fractions become wrong the moment a source clip re-renders with different framing. The SHA gate that would catch this drift has never fired because all four entries have `source_frame_sha=null`. The correct model: store the RECIPE (archetype + semantic anchor) and compute coordinates fresh at render time from the actual source clip.

### 6.5 Registry lives outside Directus
`magic_clip_registry.json` is a parallel source of truth for clip approval state. It must be manually kept in sync with `prod_visual_assets`. The v2 stitch failure happened because someone bypassed this sync step. The fix is to put approval state in Directus, where it belongs, not in a loose JSON file.

---

## 7. The Background Physics Constraint (Non-Obvious)

The Heartwood daytime stone floor is specifically the **worst possible background** for warm-gold bioluminescent magic:

1. **Mean luminosity 150–200/255** → only 55–105 headroom to white for small-particle effects
2. **Warm-gold palette of magic = chromatically identical to scene highlights** → cannot pop by hue, only by brightness. But brightness headroom is already gone.
3. **High-frequency floor texture** (mossy stones, tile seams) → 1–3px dots match background noise frequency, camouflaging them
4. **Bright sky in upper frame** → any `SIGMA_Y > 8px` leaks ambient glow into sky, creating "floating" appearance
5. **No dark contrast rail near the path** → unlike Tessa's shell framing (dark tree trunks), the Heartwood path has no adjacent darkness for visual contrast

Kim's reference "river of sparkles" image works because it inverts all five conditions (nighttime bg, cool-blue contrast, clean ground, dark sky, dark surround).

**Critical implication for future arcs:** Luna (nighttime garden), Bork (cave interior), and Ember (campfire scene) will have backgrounds that are EASIER — more luminance headroom, more chromatic contrast. The daytime Heartwood parameters MUST NOT be used as defaults for those scenes or the magic will be over-bright and incorrect. A background-class routing system is needed before those arcs enter production.

---

## 8. Locked Parameters — Never Tune These

These were established through Kim approval or explicit rejection. They are NOT variables:

| Parameter | Locked Value | Why |
|---|---|---|
| Blend mode | Additive | Screen fails on daytime bg (proven v1–v5) |
| Palette | Warm golden-white `(255,255,238)/(255,252,200)/(255,240,155)` | All cool palettes rejected |
| Dot sizes | `[1,1,1,2,2,3]` | Larger = blobs (rejected) |
| Scatter | Symmetric gaussian, NOT `abs(gauss)` | Half-normal creates floating band |
| `scatter_y_frac` | 0.032 (floor trail) | Larger = floating (rejected) |
| `AMBIENT_BLUR_YX` | `[6.0, 28.0]` | Narrow Y prevents sky leak |
| `AMBIENT_MIX` | 2.4 | Empirically tuned in v6 |
| `T_TRAIL_COMPLETE` | 0.70 | Timing pattern approved v6 |
| `T_FADEOUT_START` | 0.75 | Same |
| `seed` | 42 | Determinism |
| Particle pre-placement | Pre-placed at init, sorted by `ts` | Per-frame placement = popping (rejected) |

---

## 9. The Fix Plan (Priority Order)

### Fix 1 — `geometry_detector.py` (biggest unlock)
Build four auto-detection methods:
- `detect_foot_contact(clip) → (x, y)` — character alpha-mask bottom edge on mid-frame
- `detect_exit_vector(clip) → [pts]` — optical flow last 10 frames → normalized direction
- `detect_stone_center(bg, color) → (x, y)` — color-channel thresholding (reuses 6 existing lambdas from `magic_position_finder.py`)
- `detect_horizon_line(bg) → y` — bright/dark band transition for wide clearings

CLI: `python3 geometry_detector.py --clip X --archetype ground_exit`

This eliminates the 4-step interactive pixel-verification dance. On novel archetypes, Kim confirms one red-circle. On known archetypes (same scene type appeared before), zero confirmation needed.

### Fix 2 — Archetype-addressed KNOWN_SCENES
Replace coordinate storage with recipe storage:
```json
{
  "m1_e1_res_beat_01_heartwood": {
    "archetype": "ground_left_to_target",
    "color_target": "orange",
    "direction": "left_to_right"
  }
}
```
Delete `source_frame_sha` entirely. Geometry computed fresh at render time from actual source clip. SHA drift becomes structurally impossible.

### Fix 3 — Background-class routing
At calibration time: measure path-centerline luminance + saturation → classify as `daytime-warm / daytime-cool / nighttime / indoor`. Route to class-appropriate parameter block:

| Class | `SIGMA_Y` | `ambient_blur_yx` | Palette shift |
|---|---|---|---|
| daytime-warm (current) | 6.0 | [6.0, 28.0] | None (locked Ori) |
| nighttime | 12.0 | [10.0, 40.0] | Cool blue allowed |
| indoor-low-key | 8.0 | [8.0, 30.0] | Neutral |
| daytime-cool | 6.0 | [6.0, 28.0] | Warmer shift |

This prevents current Heartwood params from being applied blindly to Luna, Bork, Ember scenes.

### Fix 4 — Move clip registry to Directus
Add `prod_magic_clips` collection (or FK on `prod_visual_assets`) with fields: `source_asset_id`, `magic_asset_id`, `status`, `scene_archetype`, `approved_at`. Rewrite `resolve_stitch_clips()` to query Directus. Delete `magic_clip_registry.json` after migration.

### Fix 5 — Link LD-398 in code; block non-approved styles at runtime
- Set `STYLES["tessa_ori"]["directus_ld"] = 398` (currently `None` with TODO comment)
- Add: `if style["status"] != "approved" and not args.draft: raise RuntimeError(f"Style {name} is not approved for production")`
- This prevents `wide_ori` (draft) and `burst` (nonexistent) from silently entering production

### Fix 6 — Canonize the stitch pattern as a first-class function
```python
assemble_magic_sequence(kling_clip, magic_still, magic_duration) 
  → resolve_stitch_clips() [Directus]
  → ffmpeg concat
  → output to prod_visual_assets
```
Not an improvised workaround. A locked, documented production function.

---

## 10. The Target State ("Produce visible magic" → first time works)

```python
render_magic(scene_key="m1_e1_res_beat_03")
```

1. Auto-resolve `source_clip` from Directus `prod_visual_assets` (approved, shot_number matching)
2. Run `geometry_detector.infer(scene_key, source_clip)` → path_pts
3. Measure background class → select parameter block
4. Apply locked tessa_ori params (never exposed to Claude as tunable)
5. Render preview PNG at `T_TRAIL_COMPLETE` frame
6. Open in Preview.app
7. Kim: "approve" OR one of: `[brighter] [dimmer] [lower] [reposition] [reject]`
8. If approved → render full video → register in Directus → stitch → done

**Zero coordinate grids. Zero sigma tuning. Zero registry JSON. Two renders maximum.**

---

*Supersedes v1 (Production/tools/), v2 (Production/tools/), v3 (Production/). All prior versions retained for historical traceability only.*

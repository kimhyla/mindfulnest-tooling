# Watercolor Animate — Procedural Tech Spec v2

**Date:** 2026-05-28  
**Status:** CURRENT — supersedes Claude+ffmpeg LD-470 implementation details  
**Supersedes:** Claude-era `WATERCOLOR_ANIMATE_PROCEDURAL_V1` behavior (LD-470 decision text amended via `WATERCOLOR_ANIMATE_PIL_RENDERER_V1`)  
**Lessons learned:** `LESSONS_LEARNED_20260528_PHASE_B_WATERCOLOR_ANIMATE_V1.md`  
**Locked decision:** `WATERCOLOR_ANIMATE_PIL_RENDERER_V1`

---

## §1 Purpose

Define the **canonical, durable** server behavior for Phase B **Animate this** (`POST /api/watercolor/animate`) and its consumption by:

- Phase B **Preview with Overlay** (`POST /api/phase_b/preview`)
- Stitcher watercolor overlay compositor (`render_watercolor_overlay`)

This spec is the contract for **all future Phase B watercolor animations**, not only `hands_rubbing`.

---

## §2 Architecture (end-to-end)

```text
path_picker.html (mode=watercolor_animate)
  → POST /api/watercolor/animate
      { watercolor_key, manual_path, motion_description, scope_event_id }
  → handle_watercolor_animate (background.py)
      → PIL deterministic frame renderer (NO Claude, NO filter_complex)
      → {key}_animated_{timestamp}.mp4 in watercolor_library/
  → state writeback: watercolor_animated_overrides[key]
  → postMessage → PhaseProducer updates cue to animated key + cue_type=video

Phase B preview / Stitcher:
  → render_watercolor_overlay (ffmpeg_stitch.py)
      → chromakey magenta, scale to bbox, overlay at frame_x/frame_y
      → recipe pin: WATERCOLOR_OVERLAY_RECIPE_VERSION = wc_v13_hand_only_split
```

---

## §3 Encode contract (PIL renderer) — MANDATORY

### §3.1 Canvas

- Tight crop around source PNG + rub padding (`_rub_px`) + edge pad.
- Background fill: **magenta `(255,0,255)`** for chromakey (not green — see wc_v4).
- Output: H.264 yuv420p via ffmpeg concat of PNG frames.

### §3.2 Three-layer composite (every frame)

| Layer | Content | Moves? |
|-------|---------|--------|
| 1 | Solid white RGB rectangle — full opaque matte bbox | **NO** |
| 2 | Fixed frame pixels from source — cream + border + pure white | **NO** |
| 3a | Hand pigment half A | **YES** — oscillate along path axis |
| 3b | Hand pigment half B | **YES** — opposite phase to 3a |

**NEVER** split or translate cream paper, black border, or full PNG as a unit.

### §3.3 Pixel classification (canonical)

For each pixel with alpha ≥ 20:

```python
# border — fixed
r < 80 and g < 80 and b < 80

# pure paper — fixed (also covered by white underlay)
r > 245 and g > 245 and b > 245

# cream/off-white matte — fixed
(r + g + b) > 700 and (max(r,g,b) - min(r,g,b)) < 35

# hand pigment — ONLY class that may be split + animated
else
```

### §3.4 Center-split rub geometry

- **Path direction** from first→last normalized path point (unit vector).
- If `|dir_y| >= |dir_x|`: **vertical rub** → split hand pixels at hand-bbox center **X**; halves move on **Y** in opposite directions.
- Else: **horizontal rub** → split at hand-bbox center **Y**; halves move on **X** in opposite directions.
- Oscillation: `t = 0.5 - 0.5*cos(2π × freq × time)`; offset = `(t-0.5) × 2 × rub_px`.
- Half A offset: `(+dir × offset)`; Half B: `(-dir × offset)`.

### §3.5 Motion description parsing (NOT Claude)

`motion_description` is **required** (non-empty, ≤500 chars). Server reads it in `handle_watercolor_animate` only:

| Pattern (case-insensitive substring) | Oscillation freq |
|----------------------------------------|------------------|
| rub, friction, heat, warm, brisk, quick, fast, opposite, back and forth, up and down, … | 2.5 Hz |
| gentle, slow, soft, drift, float, sway, pulse, breathe, subtle, calm, … | 0.75 Hz |
| default | 1.5 Hz |

Duration: `max(2s, min(5s, path_len×0.4))`, extended to ensure ≥3 full cycles at chosen freq.

**Future animations:** extend keyword tables in one place (`background.py`); do not reintroduce LLM/ffmpeg for standard rub/drift.

---

## §4 UI contract (path_picker.html)

- Mode: `?mode=watercolor_animate&watercolor_key=…&return_endpoint=/api/watercolor/animate`
- **WHERE:** 2+ path points (normalized 0–1).
- **WHAT:** `motion_description` textarea — drives server freq/style (§3.5).
- Help text MUST state: **“Interpreted by the server PIL renderer (deterministic). Not sent to Claude.”**

---

## §5 Compositor contract (ffmpeg_stitch.py)

- `cue_type=video` animated cues: chromakey `0xFF00FF:0.25:0.0`, **static overlay x** (no `gentle_pan` on video).
- Loop/tpad: rub clip loops for cue enable window (wc_v8+).
- `WATERCOLOR_OVERLAY_RECIPE_VERSION` must bump when compositor semantics change → invalidates preview cache.

Current pin: **`wc_v13_hand_only_split`**

---

## §6 Durability requirements (enforcement)

| Mechanism | Artifact |
|-----------|----------|
| Locked decision | Directus `prod_locked_decisions`: `WATERCOLOR_ANIMATE_PIL_RENDERER_V1` |
| Reference docs | This file + lessons learned in `prod_reference_docs` |
| Code pin | `WATERCOLOR_OVERLAY_RECIPE_VERSION`, renderer tag `pil_center_split_rub` |
| Handler docstring | `handle_watercolor_animate` — must reference this spec |
| Deploy | `deploy_storyboard_v59.sh` — no partial hot-copy for animate path |
| Kim gate | Re-animate + Preview with Overlay after any change |

---

## §7 Verification commands (positive proof)

```bash
# 1. Animate
curl -s -X POST http://localhost:5111/api/watercolor/animate \
  -H 'Content-Type: application/json' \
  -d '{"scope_event_id":"Event_1","watercolor_key":"hands_rubbing",
       "motion_description":"hands rubbing together vertically for warmth",
       "manual_path":[[0.5,0.35],[0.5,0.65]]}'

# 2. Confirm explanation contains wc_v13 / fixed frame + hand-pigment
# 3. Preview with Overlay in Phase B UI at cue timestamp
# 4. grep recipe version
grep WATERCOLOR_OVERLAY_RECIPE_VERSION Production/tools/credentials_lib/ffmpeg_stitch.py
```

**Encode acceptance (automated):**

- Frame shear (top vs bottom white edge x): **0 px** at all frames.
- Vacated hand pixels at rub peak: **magenta ≈ 0**, white ≫ 0.

---

## §8 Explicit non-goals

- Do **not** restore Claude+ffmpeg `filter_complex` for standard animate (failed at runtime; superseded).
- Do **not** translate whole PNG for rub motion.
- Do **not** classify “not pure white” as hand.
- Do **not** apply compositor pan/fade to video cues beyond chromakey+scale (motion is baked).

---

## §9 Change log

| Version | Date | Change |
|---------|------|--------|
| v1 (LD-470) | 2026-05 | Claude+ffmpeg filter_complex from path + motion_description |
| v2 | 2026-05-28 | Deterministic PIL: fixed frame + hand-only center-split rub; wc_v13; supersedes v1 implementation |

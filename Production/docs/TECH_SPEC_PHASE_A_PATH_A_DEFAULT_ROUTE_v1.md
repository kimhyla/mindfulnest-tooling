# TECH SPEC — Phase A Path A default lipsync route (v1)

Marker: `PHASE_A_PATH_A_ROUTE_V1`  
Registry concept: `phase_a_lipsync_route`  
Runbook: `Production/tools/PHASE_A_PATH_A_LIPSYNC_RUNBOOK_v1.md`  
Mirrors Cedric Phase B Path A (`PHASE_B_PATH_A_ROUTE_V1`) for Arlo.

## 1. Problem / category

Whole-frame Phase A lipsync (still bookend idle → Kling LipSync) re-renders
the entire frame: room warp, detail loss at 832×464, and no durable gesture
idle track. Same defect class as Phase B before Path A.

## 2. Fix (category)

Make the **Path A layered pipeline** (`phase_a_path_a_pipeline.py`) the single
default route for Phase A module lipsync:

1. Static room plate + **green**-screen Arlo cutout.
2. Gesture idle from approved 10s crop unit (self-looped with 0.5s xfade).
3. Silence-aligned ≤50s chunks → Kling lipsync in parallel.
4. QC: pupil scan + body still-span (≥0.5s).
5. Chroma-key green, composite onto plate + stem audio.

Idle mouth flap on the base unit is accepted (Kling lip-lock is unreliable on
Arlo); lipsync overwrites the mouth on speech chunks — same pragmatic stance
as Cedric Path A units A/B.

## 3. Server integration

`handle_phase_a_lipsync` → `validate_path_a_assets` → chunk budget gate →
background `run_phase_a_path_a_lipsync` → A/V gap + QA frames → delivery encode
→ status `needs_manual_visual_review` (Phase A visual gate unchanged).

`base_clip_id` is continuity-only; Path A does not read a whole-frame base clip.

## 4. Assets (Dropbox)

| Asset | Path |
|---|---|
| Green cutout 1280×720 | `NEW STYLE CHARACTERS/ARLO/path_a_prep/arlo_cutout_green_1280x720_v1.png` |
| Room plate 1280×720 | `NEW STYLE CHARACTERS/ARLO/path_a_prep/arlo_room_plate_1280x720_v1.png` |
| Idle A (crop, lipsync) | `assets/lipsync_bases/<chosen>_crop_green_1920x1080.mp4` (provisional: `arlo_path_a_gesture_idle_o3_v12_10s_crop_green_1920x1080.mp4`) |
| Idle A source (fullframe) | matching `*_fullframe_green_1920x1080.mp4` under lipsync_bases |

Geometry: crop **832×468 @ (325, 157)** on the 1280×720 plate (full body —
shrinking this box leaves still cutout legs and looks cut in half).

Idle selection is **not** locked in v1 — operator swaps `IDLE_UNIT_A.path`
(see runbook). Path A route + plate/cutout/geometry are the durable rewiring.

## 5. Out of scope

- Locking the production idle unit (operator swaps `IDLE_UNIT_A.path` later).
- Second idle unit B (optional later).
- Changing Phase A visual-review / auto-stitch gates.
- Whole-frame startend still idle route (retired as default).
- Face-only Kling submit + paste-back (optional later; do not shrink CROP_*).

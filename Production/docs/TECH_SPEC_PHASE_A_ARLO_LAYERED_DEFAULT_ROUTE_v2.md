# Tech Spec — Phase A Arlo layered default route v2

**Status:** LOCKED 2026-08-11 (Kim Gate0 headshot Speak)  
**Marker:** `PHASE_A_ARLO_LAYERED_ROUTE_V2`  
**Authority:** `phase_a_lipsync_route`  
**Supersedes:** `TECH_SPEC_PHASE_A_ARLO_LAYERED_DEFAULT_ROUTE_v1.md` (full_loop_30s + chair plate)

## Category-unlocker

- **Bug category:** Phase A Speak used the wrong layered assets (full-body loop + chair plate).
- **Category fix:** One Send route — Gate0 pinned headshot idle + headshot plate + Kling LipSync → 1280×720 module delivery.
- **Fix type:** CATEGORY

## Process (Send)

1. Operator: script → stem (unchanged).
2. Send for Lipsync → `_handle_phase_a_lipsync_layered` only.
3. Engine loops **locked** idle → WaveSpeed Kling LipSync chunks → green chromakey + despill → headshot plate → `phase_a_lipsync_*.mp4` at **1280×720**.
4. Status `needs_manual_visual_review`.
5. Normalize / Export to Stitcher → slot `phase_a` (unchanged handoff).

**Not on Send:** Avatar Pro, ByteDance, Kling motion-idle regen, Gate0 trim (Cat-2 prep only).

## Locked assets (Dropbox `Production/`)

| Role | Path |
|------|------|
| Idle | `NEW STYLE CHARACTERS/ARLO/arlo_gesture_idle_kim_gate0_pinned_15s_v1.mp4` |
| Plate | `NEW STYLE CHARACTERS/ARLO/arlo_room_plate_headshot_close_1280x720_v1.png` |
| Key canvas | `NEW STYLE CHARACTERS/ARLO/arlo_key_canvas_headshot_1280x720_v1.png` |
| Key RGB | `(11, 243, 7)` → `chromakey=0x0BF307:0.20:0.06` + `despill=type=green` |

Prep recipe (once): `Production/docs/ARLO_GREEN_PATH_A_GATE0_CUTOUT_RECIPE_v1.md` + pin constant key.

## UI

- Speak idle dropdown: **locked** to metadata ID `arlo_idle_kim_gate0_headshot_v1` (does not change render asset).
- Regen base clip: **hidden** (does not drive Send).
- Export / Reject / Normalize / stem / watercolors: preserved.

## Code SSoT

- `Production/tools/layered_character_lipsync.py` → `ARLO_PROFILE`
- `Production/tools/server_handlers/phases.py` → `handle_phase_a_lipsync` → layered only
- `Production/tools/phase_a_arlo_contract.py` / `phaseAArloContract.ts`

## Proof oracle

Offline: `Event_6/_proof_arlo_green_path_a/headshot_path_a/kim_gate0_idle_lipsync_12s_on_plate.mp4`  
Live: Option B Event_6 (`:5116`) Send + build-sha match HEAD.

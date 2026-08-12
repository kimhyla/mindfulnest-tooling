# CANON — Phase A Gate0 Speak lock (forever)

**Status:** CANON 2026-08-12 (Kim: “perfect” on full stem; Export→Stitcher green)  
**Markers:** `PHASE_A_ARLO_LAYERED_ROUTE_V2`, `arlo_idle_kim_gate0_headshot_v1`, `STITCH_MIX_LOCAL_INPUTS_V1`

## What we locked

Phase A **Speak** is Gate0 headshot green idle → Kling LipSync → chromakey over headshot plate → **1280×720** module delivery. Not Avatar Pro. Not ByteDance on Send. Not Kling motion-idle regen.

| Piece | Canon |
|-------|--------|
| Route | `PHASE_A_ARLO_LAYERED_ROUTE_V2` / `layered_headshot_gate0_kling_lipsync_v1` |
| Idle file | `arlo_gesture_idle_kim_gate0_pinned_15s_v1.mp4` |
| Plate | `arlo_room_plate_headshot_close_1280x720_v1.png` |
| Key RGB | `(11, 243, 7)` + Gate0 spill/choke recipe |
| UI Speak idle | locked `arlo_idle_kim_gate0_headshot_v1` |
| Regen base clip | hidden |
| Authority | `phase_a_lipsync_route` → tech spec v2 |

## Worship / do not regress

1. Do **not** put Avatar Pro, ByteDance, or motion-idle regen back on Phase A Send.
2. Do **not** swap Gate0 idle/plate for full-body chair assets without a new Kim visual lock + v3 tech spec.
3. Halo = Gate0 recipe (`spillkill_warm_edge_vj` + choke + hard matte) — not ffmpeg chromakey-only shortcuts.
4. Export→Stitcher must land `phase_a` with full stem duration (not empty/2.5s stub). Mix uses local hot-serve inputs + speech mono (`STITCH_MIX_*`).
5. Proof: Event_6 Stitcher shows **Phase A ~55.5 s** after Export; audit JSONL ends `OK`.

## Specs

- `TECH_SPEC_PHASE_A_ARLO_LAYERED_DEFAULT_ROUTE_v2.md`
- `ARLO_GREEN_PATH_A_GATE0_CUTOUT_RECIPE_v1.md`
- `STORYBOARD_AUTHORITY_REGISTRY_v1.md` → `phase_a_lipsync_route`

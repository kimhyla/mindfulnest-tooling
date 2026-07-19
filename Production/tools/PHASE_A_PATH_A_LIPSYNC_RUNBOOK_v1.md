# Phase A "Path A" layered lipsync — runbook v1 (Arlo)

Code: `Production/tools/phase_a_path_a_pipeline.py`.  
Default Storyboard route: `PHASE_A_PATH_A_ROUTE_V1` via `handle_phase_a_lipsync`.  
Spec: `Production/docs/TECH_SPEC_PHASE_A_PATH_A_DEFAULT_ROUTE_v1.md`.

## One-time assets

| Asset | Path |
|---|---|
| Green cutout | `NEW STYLE CHARACTERS/ARLO/path_a_prep/arlo_cutout_green_1280x720_v1.png` |
| Room plate | `NEW STYLE CHARACTERS/ARLO/path_a_prep/arlo_room_plate_1280x720_v1.png` |
| Idle A (crop for Kling) | `assets/lipsync_bases/arlo_path_a_gesture_idle_A_10s_crop_green_1920x1080.mp4` |

Approved source idle: `ARLO_IDLE_A_v6` fullframe → crop `1248x702@488,236` on
1920×1080 → scale to 1920×1080 for lipsync submit.

## Hard rules (same class as Cedric)

1. Kling lipsync always returns **832×464** — never submit a wide frame with a
   small character; use the crop idle.
2. Build **local-first** (`/tmp`), verify, then copy to Dropbox/event dir.
3. Green chromakey (`0x00FF00`), not blue (Arlo vest/scarf colors).
4. Mouth lock on idle gen is unreliable — ship gesture-good units; lipsync owns
   the mouth during speech.

## CLI

```bash
cd ~/Projects/mindfulnest-tooling/Production/tools
python3 phase_a_path_a_pipeline.py "<stem.mp3>" "<out.mp4>"
```

# Phase B "Path A" layered lipsync — runbook v1 (Cedric)

Validated end-to-end on Event 5 Phase B (Jul 17 2026). Code:
`Production/tools/phase_b_path_a_pipeline.py`.

## What this replaces and why

- **Whole-frame lipsync** warped the entire room (shelves ripple, props morph) because Kling re-renders every pixel. Path A splits the scene into a **static room plate** + **blue-screen character cutout**, so only Cedric is ever re-rendered.
- **Avatar Pro** was rejected earlier: Chinese-text hallucinations and ~4x the cost.

## One-time assets (already built, reusable for every Event)

All in Dropbox `Production/`:

| Asset | Path |
|---|---|
| Blue cutout frame (1280x720) | `NEW STYLE CHARACTERS/CEDRIC/path_a_prep/cedric_cutout_blue_1280x720_v1.png` |
| Room plate (1280x720) | `NEW STYLE CHARACTERS/CEDRIC/path_a_prep/cedric_room_plate_1280x720_v1.png` |
| Crop still used to generate idles | `assets/lipsync_bases/cedric_path_a_crop_still_1920x1080_v1.png` |
| Gesture idle unit A (10s, blue, 1920x1080) | `assets/lipsync_bases/cedric_path_a_gesture_idle_10s_loop_v1_blue_1920x1080.mp4` |
| Gesture idle unit B | `assets/lipsync_bases/cedric_path_a_gesture_idle_B_10s_loop_v1_blue_1920x1080.mp4` |
| Gesture idle unit C2 (spare, not in rotation) | `assets/lipsync_bases/cedric_path_a_gesture_idle_C2_10s_loop_v1_blue_1920x1080.mp4` |

Idle units are Kling start/end I2V jobs with the **same still as both frames** (bookend), so there is zero scale drift. Prompts must include MOUTH LOCK (lips sealed) and HEAD LOCK (level head) — see "White eyes" below.

## Per-line recurring cost

Only the lipsync jobs recur. 180s stem = 4 chunks x $0.35 ≈ **$1.40** per Phase B line. Idle regens (~$0.50 each) only when adding variants.

## Pipeline (what the script does)

1. **Idle track**: units are head/tail-trimmed (A: 0.6/1.2s, B: 1.3/0.5s) to remove the near-still bookend ramps, then chained with 0.5s `xfade` crossfades and cut to stem length.
2. **Chunking**: `silencedetect=noise=-35dB:d=0.45`, cut at silence midpoints, max 50s/chunk (Kling limit headroom).
3. **Lipsync**: WaveSpeed Kling lipsync, `transport="url"`, all chunks in parallel. DNS pins via 1.1.1.1 (LD-379-class ISP poisoning breaks filebin/catbox/uguu and api.wavespeed.ai).
4. **QC gates** (all must pass before compositing):
   - pupil scan on every chunk (white-eyes detector);
   - body-motion still scan: no still span >= 0.5s in the chest/shoulders region.
5. **Composite**: pad each chunk to exact audio duration → concat → `cas=0.45,eq=contrast=1.03:saturation=1.03` → overlay at 292,150 on the blue frame → `chromakey=0x0000FF:0.28:0.06,despill=type=blue` → overlay on plate → stem audio.

## Run

```bash
cd ~/Projects/mindfulnest-tooling/Production/tools
python3 phase_b_path_a_pipeline.py "<stem.mp3>" "<out.mp4>"
```

Work dir defaults to local `/tmp` (mkdtemp). Keep it there — see below.

## Hard-won rules (do not regress)

1. **Kling lipsync always outputs 832x464**, both transports, any input size. Never submit a wide frame where the character is small: crop tight (832x468 box @ 292,150 on the 720p frame), upscale the crop to 1920x1080 for submission, then **downscale** the output back to on-plate size. Detail survives downscaling, not upscaling.
2. **White eyes are input-driven, not random.** If an idle unit shows head tilted back with parted lips, Kling's face re-render hallucinates white eyes at that spot in *every* seed. Re-rolling the lipsync job does nothing — fix the idle unit (MOUTH LOCK + HEAD LOCK prompts) and re-run. The pupil scan gate catches this.
3. **Frozen seams are structural.** Bookend units decay to stillness at both ends. Concatenating them back-to-back produces a 2-3s freeze at every join. Fix = trim the still ramps + 0.5s crossfade. Never ship without the 0.5s still-span scan passing (the older 1.0s threshold let perceptible freezes through).
4. **Unit C2 is eyes-safe but too calm** — next to A/B it reads as a freeze. Excluded from the default rotation; keep for remixes only if re-measured trims pass the still scan.
5. **Build local-first.** Encoding straight into Dropbox CloudStorage corrupted a 2-min encode mid-write (truncated file, no moov atom). Build + verify (full decode, both QC scans) on local disk, then copy to Dropbox/Desktop.
6. **Verify concat output.** `concat -c copy` has produced NAL-unit corruption; the script decodes the concat result as a gate.

## Extending to other characters

Everything is parametrized by: cutout PNG + plate PNG + crop geometry + idle units. To add a character, produce those four (Path A prep: cutout via chroma paint-out, plate via inpaint, crop box around the character, 2-3 bookend idle units with mouth/head locks) and clone the constants block.

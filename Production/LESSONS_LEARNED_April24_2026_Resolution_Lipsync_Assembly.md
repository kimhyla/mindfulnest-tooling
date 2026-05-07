# Lessons Learned — April 23-24, 2026 — M1 Event 1 Resolution Scene: Lipsync + Magic Assembly

**Session window:** April 23 night → April 24  
**Primary outcome:** `tessa_resolution_final_v20.mp4` — 18s resolution scene with lipsync, magic departure, and true fade-to-black transition (pending final approval)  
**Related docs:** `Production/LESSONS_LEARNED_April23_2026_Resolution_Production.md`, `Production/Event_1/LESSONS_LEARNED_magic_path_compositor_20260422.md`, `Production/tools/tessa_res_v2_pipeline.py`, `Production/tools/tessa_res_v3_pipeline.py`, `Production/tools/tessa_res_v3_resume_nomagic.py`  
**Related LD:** `LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1` (id=400), `LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION` (decision 162)

---

## Why this document exists

Producing the resolution scene required 20 iterations across two sessions, driven by four distinct mistake classes: wrong source materials, wrong magic composite application, wrong operation order, and wrong ffmpeg transition technique. Each class caused multiple wasted iterations. These lessons prevent repeating any of them on future resolution beats or on other modules.

---

## PART 1 — Visible Magic Production Mistakes

### 1. §8.5 operation order: lipsync FIRST on a clean source, magic composite AFTER

**What happened:** Versions v1–v8 used the pre-approved stitch (`beat02_event1_full_sequence_v1.mp4`) — which already had magic sparkles baked into the Tessa section — as the ByteDance LipSync source. ByteDance LatentSync received a video with visible sparkle overlays in the mouth region, corrupting landmark detection.

**The correct §8.5 order:**
1. Generate clean Kling source clip (no magic)
2. Apply ByteDance LipSync to that clean clip → get lipsynced Tessa
3. THEN apply MagicCompositor over the lipsynced frames
4. THEN stitch with the approved tail (scenes 2+3 from the approved stitch)

**Rule:** Never submit a source clip to ByteDance LipSync if it already has visible magic overlays, sparkles, or composited effects. The lipsync stage requires pixel-clean source footage.

---

### 2. The approved stitch already has magic pre-baked for scenes 2+3 — do not re-composite

**What happened:** The pipeline attempted to apply MagicCompositor to Scene 1 (Tessa lipsync). Kim's feedback: "you're applying the visible magic that's supposed to go on the second stitch to the first stitch." Magic was already pre-baked in `beat02_event1_full_sequence_v1.mp4` for the scene where magic departs from Tessa's feet (t=7-9s), the Heartwood wide shot, and the runestone activation.

**Rule:** Before running MagicCompositor, check what is already in the approved stitch. Map each scene to whether it needs new composite or should be extracted from the stitch unchanged:

| Scene | Source | Magic |
|-------|--------|-------|
| Scene 1 (Tessa lipsync, ~6s) | Fresh Kling → lipsync → optional compositor | Only if magic trail departing is required |
| Scene 2+ (magic trail departure, heartwood, runestone) | `beat02_event1_full_sequence_v1.mp4` | PRE-BAKED — extract directly, no compositor |

---

### 3. Magic path y-coordinates are scene-specific — never import from a different scene

**What happened:** The `tessa_exit_right` scene (Beat 01 approved) uses path coordinates with y≈0.84–0.968 because Tessa stands at the very bottom of that frame. For the resolution 3/4 rear scene (`still_1_tessa_3q_rear_noglow.png`), Tessa's feet are at y≈0.73. Using the exit_right y-values placed the magic trail well above Tessa's feet — visually floating in mid-air.

**The locked lesson from VISIBLE_MAGIC_LESSONS_LEARNED_v2.md** said y=0.968. That number applies ONLY to `tessa_exit_right`. It does NOT generalize.

**Rule:** Magic path coordinates must be visually measured for EACH source image. The y-values from one approved clip are invalid for any other clip. Always:
1. Export a test frame at 1280×720 from the target still
2. Identify the character's feet pixel position
3. Divide by 720 to get normalized y
4. Start the path there, not from any prior clip's values

**Resolution 3/4 rear scene coordinates (locked):**
```python
RES_PATH_PTS = [
    (0.30, 0.730), (0.44, 0.734), (0.58, 0.738),
    (0.72, 0.743), (0.86, 0.748), (1.00, 0.754),
]
```

---

### 4. Use the noglow still for lipsync source — the glow still bakes the green shell glow into ALL frames

**What happened:** v9/v10 used `still_1_tessa_3q_rear_glow_v2.png` as the Kling source still. This still has an intense green bioluminescent shell glow already rendered into it. That glow appeared in every single lipsync frame because it was baked into the source image.

**Rule:** For the resolution lipsync scene (Scene 1), always use:
- `still_1_tessa_3q_rear_noglow.png` — clean shell, no glow, correct source for lipsync

The glow-v2 still is for reference/magic composite purposes only. It should not be used as a Kling source for any clip going into ByteDance LipSync.

**Files:**
- Correct: `Production/Event_1/resolution_stills/still_1_tessa_3q_rear_noglow.png`
- Wrong for lipsync: `Production/Event_1/resolution_stills/still_1_tessa_3q_rear_glow_v2.png`

---

### 5. End frame prompt gaze control: "turns her head slightly to look at camera" causes significant head movement

**What happened:** v10 used a FLUX Kontext end frame with the prompt phrase "turns her head very slightly to look toward camera." Kling interpreted this as a major head turn across the 10s clip — not a subtle shift. The character appeared to spin around in the second half of the clip.

**Rule (consistent with §8.2 and §8.3):** Gaze control in FLUX Kontext end frames must use **negative prompt only**, not positive prompt direction. Positive-prompt gaze lock stacks with §8.1 mouth constraints and triggers the §8.2 do-not-stack violation.

```python
# WRONG — causes head movement
prompt = "Same character. Turns her head very slightly to look toward camera."

# CORRECT — negative-prompt-only gaze control
negative_prompt = "looking up, looking away, profile view, head turned, off-axis gaze, spinning, rotation"
```

---

## PART 2 — ffmpeg Assembly Mistakes

### 6. xfade crossdissolve ≠ fade to black — Kim wants a true fade through black

**What happened:** v13 used `xfade=transition=fade` which is a crossdissolve (both clips visible simultaneously during the transition). Kim described this as a "weird transition." After iterating through v14–v16 trying to tune the crossdissolve, Kim explicitly asked for "a normal black fade."

**The correct technique for a clean scene transition:**
```python
# Step 1: Encode PartA with video fade-to-black at the end
ffmpeg -i partA_source.mp4 -t {PARTA_END} \
  -vf "scale=1280:720:flags=lanczos,fps=24,fade=t=out:st={VID_FADE_START}:d={VID_FADE_DUR}" \
  -an partA_vid.mp4

# Step 2: Encode PartB with video fade-from-black at the start
ffmpeg -i partB_source.mp4 -ss {PARTB_SS} \
  -vf "scale=1280:720:flags=lanczos,fps=24,fade=t=in:st=0:d=0.5" \
  -an partB_vid.mp4

# Step 3: Concatenate (no overlap — full duration preserved)
ffmpeg -f concat -safe 0 -i list.txt -c:v copy -an combined_vid.mp4

# Step 4: Mux audio (with separate afade for bop protection)
ffmpeg -i combined_vid.mp4 -i audio_source.mp4 \
  -filter_complex "[1:a]atrim=end={PARTA_END},afade=t=out:st={AUD_FADE_START}:d=0.4,asetpts=PTS-STARTPTS,apad=whole_dur={total}[aout]" \
  -map 0:v -map [aout] -c:v copy -c:a aac ... output.mp4
```

**Key point:** With this method, total_duration = PartA_dur + PartB_dur (no overlap removed). The crossdissolve (xfade) subtracts `xfade_dur` from total — use that only when you need an overlap.

---

### 7. ffmpeg xfade hard constraint: offset + duration must be ≤ PartA_duration

**What happened:** v15 used `xfade=offset=5.5:duration=1.5` with PartA=6.0s. Since 5.5 + 1.5 = 7.0 > 6.0, ffmpeg silently fell back to a hard cut. The clip looked like it had no transition at all, even though no error was raised.

**Rule:** For xfade, always verify: `offset + duration ≤ PartA_duration`. There is no ffmpeg warning when this is violated — it just removes the fade silently.

**Constraint table for PartA=6.0s:**

| duration | max safe offset |
|----------|----------------|
| 0.5s | ≤ 5.5s |
| 1.0s | ≤ 5.0s |
| 1.5s | ≤ 4.5s |
| 2.0s | ≤ 4.0s |

---

### 8. The heartwood scene boundary in v7: hard cap PartA at ≤6.0s

**What happened:** v14 extended PartA to 7.0s from `tessa_resolution_final_v7.mp4` to push the xfade start later. But v7 contains all 3 scenes — the heartwood wide shot begins at t≈6.5s. With PartA=7.0s, the last 0.5s of PartA showed the heartwood scene, which leaked into the xfade. Kim described this as: "the video forwards to the zoomed-out heartwood for a half second (with that old bop bop bop audio) and THEN BACK TO the Tessa clip."

**Rule:** When using `tessa_resolution_final_v7.mp4` as PartA, the hard cap is **≤6.0s**. Heartwood visuals appear at t≈6.5s and the associated scene-2 audio appears at t≈4.7s. Do not use any portion of v7 past 6.0s as PartA for assembly.

---

### 9. ffmpeg silencedetect reports PAUSES as silence — speech can continue after a silence_end

**What happened:** Running `silencedetect=noise=-35dB:duration=0.3` on v7 showed:
```
silence_start: 4.089  silence_end: 4.727
```
This was interpreted as "speech ends at 4.089s." But the last line of dialogue is "Whoah, where's it going?" The word "going" appears AFTER the silence_end at 4.727s — the silence was a breath between "where's it" and "going," not the end of speech.

Three versions (v17, v18, v19) set audio fade start before speech ended because of this misread:
- v17: afade at 4.1s → cut off "where's it going"
- v18: afade at 4.5s → cut off "where is it going now"  
- v19: afade at 5.2s → cut off "going"
- v20: afade at 5.6s → pending

**Rule:** When using silencedetect to find the end of dialogue, the last `silence_start` is NOT the end of speech — it may be a pause between words. Actual speech end is found by:
1. Running `silencedetect` at `-45dB` to catch quiet trailing phonemes
2. Checking whether any silence_end is followed by more audio (no subsequent silence_start = more speech or music follows)
3. Adding a conservative 0.5s buffer AFTER the last detected speech activity before setting afade

**For v7 specifically:** Speech ends somewhere between 5.5–5.8s (not 4.089s). The silencedetect pause at 4.089–4.727s is the breath between "where's it" and "going."

---

### 10. Separate the audio trim point from the video trim point when source has scene-transition audio

**What happened:** `tessa_resolution_final_v7.mp4` contains 3 scenes. The video from Scene 1 (Tessa) runs 0–6.5s. But the audio from Scene 2 (heartwood/bops) bleeds in starting at t≈4.7s while the video still shows Tessa. Setting a single `-t 6.0` trim captured unwanted scene-2 audio during the fade period.

**Rule:** For any source clip that spans multiple scenes, decouple audio and video trim:
- **Video trim point:** where the scene visually transitions (for v7: 6.0s, safely before heartwood at 6.5s)
- **Audio trim point (afade start):** just after dialogue completes (for v7: ≈5.6s+)
- Apply `afade=t=out:st={AUD_FADE_START}:d=0.4` to fade out the audio before scene-2 sounds become audible

---

## PART 3 — Process Lessons

### 11. Check the approved stitch structure before starting any assembly

**What happened:** The approved stitch `beat02_event1_full_sequence_v1.mp4` contains:
- t=0–9s: Tessa with magic trail departing feet (video only, no audio)
- t=9–12.5s: Heartwood wide shot with magic trail
- t=12.5–17s: Runestone activation

This structure was not mapped before building the pipeline. As a result, the pipeline tried to re-create what was already in the stitch (scenes 2+3), and tried to add magic to Scene 1 even though the stitch already showed it.

**Rule:** Before any assembly session, run this check on the approved stitch:
```bash
ffprobe -v quiet -show_streams -select_streams a beat02_event1_full_sequence_v1.mp4
# → confirms no audio track (video only)
ffprobe -v quiet -show_entries format=duration beat02_event1_full_sequence_v1.mp4
# → 17.04s
```
Then extract and inspect frame at key timestamps (7s, 9s, 12.5s) to confirm what each scene contains before writing any assembly script.

---

### 12. "Too little magic" is as wrong as "wrong magic" — the transition scene must show magic departing

**What happened:** v11 built a clean lipsync (no magic on Scene 1) then stitched directly to the approved tail (scenes 2+3). Kim: "there's no magic in the first clip, which means it is NOT showing the magic coming off Tessa." The magic departure from Tessa's feet needed to be visible somewhere. The approved stitch shows this at t=5–9s (still showing Tessa but with sparkle trail at feet), which is why PARTB_START=5.0s was the correct join point — it overlaps visually between "Tessa speaking" and "magic visibly departing."

**Rule:** The transition join point must be chosen so that the scene of magic leaving Tessa's feet is present in the assembled output. `beat02_event1_full_sequence_v1.mp4` t=5.0–9.0s is the magic-departure section. Starting PartB at t=5.0s ensures this transition is visible in the final clip.

---

### 13. The final working assembly parameters (locked for future reference)

As of v20, the working parameters for `tessa_resolution_final.mp4` assembly:

```python
V7               = "tessa_resolution_final_v7.mp4"       # lipsynced Tessa, 14s
STITCH           = "beat02_event1_full_sequence_v1.mp4"   # approved 3-scene stitch, 17s, no audio

PARTA_END        = 6.0    # PartA from v7: 0–6.0s (heartwood at 6.5s, safe cap)
PARTB_SS         = 5.0    # PartB from stitch: t=5.0s to end (includes magic departure)
VID_FADE_START   = 5.0    # video fade-to-black starts here (1.0s before PartA ends)
VID_FADE_DUR     = 1.0    # 1.0s fade to black
AUD_FADE_START   = 5.6    # audio fade starts here (AFTER "going" completes ~5.5s)
AUD_FADE_DUR     = 0.4    # fade audio to silence by 6.0s
FADEIN_DUR       = 0.5    # PartB fades in from black over 0.5s
TOTAL            = 18.0s  # PartA (6.0s) + PartB (12.042s) = 18.042s
```

---

## PART 4 — Iteration History (for traceability)

| Version | Key change | Failure reason |
|---------|-----------|----------------|
| v1–v8 | Various pipelines using approved stitch as lipsync source | §8.5 violation: magic pre-baked in source → ByteDance corruption |
| v9 | Switched to clean Kling; used glow still | Shell glow baked into all lipsync frames |
| v10 | Switched to noglow still; corrected path to y=0.73 | End frame head-turn caused head spin; magic path still imprecise |
| v11 | No magic composite on Scene 1 | No magic departure visible — Kim: "there's no magic in the first clip" |
| v12 | Used v7 lipsync + beat02 tail from t=5.0s | Hard cut between two Tessa clips |
| v13 | Added 1.0s xfade crossdissolve | Crossdissolve looked "weird" — Kim asked for longer fade |
| v14 | Extended PartA to 7.0s, xfade offset=6.0 | Heartwood at t=6.5s leaked into fade + bop audio |
| v15 | xfade offset=5.5, duration=1.5 | **Violated xfade constraint** (5.5+1.5>6.0) → hard cut |
| v16 | xfade offset=4.3, duration=1.7 | Cut time out of first clip — Kim: "not a normal black fade" |
| v17 | True fade-to-black, VID_FADE_START=4.1s, AUD_FADE_START=4.1s | Cut off "where's it going" — silencedetect pause misread as speech end |
| v18 | AUD_FADE_START=4.5s | Cut off "where is it going now" — speech continues past 4.727s |
| v19 | AUD_FADE_START=5.2s | "Going" still cut off |
| v20 | AUD_FADE_START=5.6s | Pending Kim review |

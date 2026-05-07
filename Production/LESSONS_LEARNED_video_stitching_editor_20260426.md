# LESSONS LEARNED — Video Stitching Session
**Date:** 2026-04-26
**Session:** cb6fe1f0 (2:15 AM – ~7:55 AM)
**What we were trying to do:** Concatenate Event 1 segments (intro + Phase A + Phase B + win/resolution) into one small deliverable MP4, then apply visual magic effects to the resolution beat.

---

## SECTION 1: Technical Lessons Learned

### 1.1 — Pink/Magenta Colorspace Issue with Python PIL + ffmpeg Blend

**What happened:** Early composite attempts using `imageio` to write frames and ffmpeg to encode produced pink/magenta color casts in the output video instead of the expected warm gold/cream magic glow.

**Root cause:** `imageio.v3` writes frames in BGR channel order by default. PIL's `ImageChops.screen()` blend mode operates in RGB. When frames come out of PIL (RGB) and get passed to imageio without explicit channel conversion, the R and B channels are swapped, turning warm yellows into pinks.

**Fix:** Use PIL `ImageChops.screen()` for the blend (this is the correct approach — it matches how "screen" blend mode works in compositing apps), then convert the resulting PIL image to a numpy array in RGB order before passing to imageio. Alternatively, write frames via PIL `.save()` and let ffmpeg read them from disk.

**Confirmed working approach:** `composite_magic_path_tessa.py` v5 and `tessa_magic_live_composite_v5.mp4` used PIL `ImageChops.screen()` throughout. That is the canonical, approved method. Do not switch to ffmpeg's `blend=screen` filter — the color math differs and produces a different look.

**Key rule going forward:** PIL screen blend = correct. ffmpeg blend filter = different result. Pick one and stay consistent.

---

### 1.2 — Audio Dropping with imageio + the ffmpeg Mux Fix

**What happened:** Scripts that rendered frames via `imageio.v3` and wrote an MP4 lost the audio track entirely. The resulting file was video-only, which caused the subsequent lipsync step to fail (ByteDance LatentSync needs audio to drive the mouth).

**Root cause:** `imageio.v3` writes video-only containers by default. It has no built-in audio muxing for MP4 output.

**Fix:** Always separate video and audio:
1. Render frames to a silent video via imageio or ffmpeg.
2. Then mux audio back in with ffmpeg: `ffmpeg -i silent_video.mp4 -i audio_source.mp4 -c:v copy -c:a aac -map 0:v -map 1:a output.mp4`

**Lesson:** Any script that renders a video with imageio MUST have an explicit ffmpeg mux step at the end. Never assume imageio carried the audio along.

---

### 1.3 — Module-Level Side-Effect Problem in composite_magic_overlay.py (No `__name__` Guard)

**What happened:** `composite_magic_overlay.py` was running its full render pipeline at import time. When another script did `from composite_magic_overlay import make_glow` to reuse the glow function, the entire 84-frame render kicked off unexpectedly, taking minutes and producing an unwanted output file.

**Root cause:** No `if __name__ == "__main__":` guard around the render code. Python executes all top-level code in a module when it's imported, not just the function definitions.

**Fix:** All render code (frame loops, ffmpeg calls, file writes) must live inside `if __name__ == "__main__":`. Only function definitions live at module level. This is standard Python practice that was missed under session time pressure.

**Lesson:** Every production script that is also meant to be imported as a library (e.g., to reuse `make_glow()`, `bezier()`) MUST have this guard. If you notice a script running code on import, add the guard before reusing it.

---

### 1.4 — The `anullsrc` Flag Order Error

**What happened:** An ffmpeg command using `anullsrc` to generate silent audio failed with a cryptic filter error. The command had `-f lavfi -i anullsrc=r=44100:cl=mono` but the flags were in the wrong order relative to the other inputs.

**Root cause:** ffmpeg is sensitive to input flag order. When `-f lavfi` appears after other `-i` flags, ffmpeg gets confused about which input the format flag applies to.

**Fix:** Always specify `-f lavfi -i anullsrc=...` as the FIRST input if generating silence as padding, or use a concat demuxer text file to sequence segments rather than relying on filter chain silence generation.

**Correct pattern for silence padding:**
```bash
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -i video.mp4 \
  -c:v copy -c:a aac -shortest output.mp4
```
Put the `lavfi` input before the main video input.

---

### 1.5 — The "Whoah" Lipsync Confusion: That File Never Existed

**What happened:** Hours were spent looking for a file Kim believed existed — a lipsynced version of Tessa saying "whoah, where is it going?" — searching Directus, scanning disk, querying prod_activity_log. The file did not exist.

**Root cause:** Kim's memory of seeing this lipsync was from a PREVIEW or a mental model of what the sequence should feel like, not from an actual produced file. The ByteDance lipsync had never been run on the "whoah" audio.

**Fix:** Had to generate fresh TTS for "whoah, where is it going?" via ElevenLabs, then run a new Kling generation + ByteDance lipsync pipeline.

**Lesson:** When Kim says "I thought we had a file that..." — query Directus FIRST (`prod_activity_log`, `prod_assets`) before spending time searching disk. If Directus has no record of it with a kim_verdict of "approved," it either doesn't exist or was never registered. Ask Kim to confirm before doing a disk scan. Disk has hundreds of intermediates; only Directus identifies canonical files.

This also reinforces Rule 31 (Directus Before Disk for Any Approved Asset).

---

### 1.6 — QuickTime Black Screen / Stale Cache Issue

**What happened:** After Claude wrote a new composite MP4 to disk and opened it in QuickTime, Kim reported seeing a black screen. The file was correct (ffprobe confirmed video + audio streams, correct duration), but QuickTime showed nothing.

**Root cause:** QuickTime Player on macOS caches the last-opened version of a file by filename. If a file is overwritten in place (same filename, new content), QuickTime sometimes serves the cached/stale version — or fails to decode the new file if the previous version was left in an inconsistent state by a mid-write crash or partial ffmpeg encode.

**Fix options (in order of preference):**
1. Always write a new filename with a version suffix (v2, v3, etc.) instead of overwriting. Never overwrite an MP4 in place.
2. If you must reuse a filename, force-quit QuickTime and reopen.
3. If a file shows black screen in QuickTime but ffprobe reports it as valid, do a one-pass ffmpeg re-encode to a new filename: `ffmpeg -i suspect.mp4 -c:v libx264 -c:a aac reencoded.mp4`

**Lesson:** Version every output file. `output_v1.mp4`, `output_v2.mp4`, etc. Never write to the same filename. This also preserves rollback options.

---

### 1.7 — ByteDance LipSync: What Works vs What Breaks

**What works (validated across this and prior sessions):**
- Clips ≤10 seconds, single spoken phrase, no internal silence gaps
- Audio submitted with silcomp preprocessing (silence gaps > 1s compressed to 0.8s per §8.4)
- Kling source video with natural 3D mouth geometry (not flat-line compressed)
- cfg_scale ≤ 0.5 on the Kling source clip

**What breaks:**
- Clips longer than 10 seconds: ByteDance embeds a visible Chinese watermark (China AI labeling law) and sometimes replaces scene content with hallucinated MindfulNest environments
- Clips with internal silence gaps > 1s: ByteDance loses audio conditioning across the gap and hallucinates scene content
- Over-constrained Kling source (cfg_scale > 0.5 + positive gaze lock + mouth lock stacked): flattens the mouth pixel region, LatentSync has nothing to stamp onto, produces missing phrases or "dropped" mouth sync
- Submitting a video that imageio wrote without audio: ByteDance needs the actual TTS audio file, not the silent video

**The silence-split protocol (§8.5) is mandatory for any source > 10s:** split at silence boundaries, submit speaking segments only (each ≤10s), passthrough original frames for silent portions, reassemble.

---

### 1.8 — Shell Glow vs Traveling Trail: Two Separate Effects

**What happened:** At one point, Claude started applying the shell glow effect (Tessa's ambient bioluminescent glow around her body, which is what the Ori-style overlay produces) to a beat that Kim wanted the traveling trail effect (magic light moving along the ground from Tessa toward the altar).

**Kim caught this and stopped it.**

**The distinction:**
- **Shell glow** (`composite_magic_overlay.py`): A static elliptical bioluminescent glow centered on Tessa's body. Warm gold. Pulses slightly. Used in Beat 01 (Tessa appears, shell glows). This is an **Ori-style effect** — named after the "Ori and the Blind Forest" visual aesthetic of a creature surrounded by ambient light.
- **Traveling trail** (`composite_magic_path_tessa.py`, `composite_magic_path_v6.py`): The magic MOVES along a path across the floor — growing trail from left to right, floor perspective, toward the altar/heartwood. Used in the resolution beats when the spell takes effect. This is a **"light pushing through"** effect, distinct from shell glow.

**Rule:** Before applying any magic compositor, confirm with Kim which effect: glow-on-creature (shell) or trail-across-floor (traveling). They are not interchangeable. The scripts have different logic, different path coordinates, and different visual output.

---

### 1.9 — The `path_picker.html` Tool and Kim's Drawn Paths

**What it does:** `path_picker.html` is a browser-based tool that lets Kim load a background image and draw a freehand path on it. The tool exports the path as normalized (x,y) coordinates (0.0–1.0 range). These coordinates feed directly into `composite_magic_path_tessa.py`'s `PATH_PTS` array.

**Why this matters:** Claude cannot reliably guess what path Kim wants the magic to travel. A guessed path based on visual analysis of the background image (e.g., "the altar is at 47% width, 67% height") may be technically correct but feel wrong in motion. Kim's drawn path captures artistic intent: the exact arc, the speed impression, which ground-level features to pass near.

**Workflow:**
1. Kim opens `path_picker.html` in browser
2. Drags the background still onto the canvas
3. Draws the desired magic path by clicking waypoints
4. Tool outputs JSON with normalized coordinates
5. Claude pastes those coordinates into `PATH_PTS` in the compositor script

**Lesson:** For any new resolution beat with a traveling trail, ALWAYS open `path_picker.html` first and get Kim's drawn path before rendering a single frame. Do not estimate the path.

---

### 1.10 — New "Light Pushing Through" Trail Style vs Old Ori Shell Glow Style

**Context:** The current approved magic trail look is described as "light pushing through" — a subtle, floor-hugging warm gold trail that grows along the ground. It uses perspective scaling (glow radius gets smaller toward the horizon) and a persistent trail that persists and dims as the head moves forward.

**Kim prefers this over the original Ori shell glow** because:
- It shows the MAGIC TRAVELING to the altar, telling a visual story
- It reads as naturalistic — as if the ground is channeling energy
- The shell glow looked great for Tessa's appearance beat but is not the right effect for the resolution story beat

**Approved color palette (DO NOT CHANGE without Kim's approval):**
```python
ORI_CORE   = (255, 255, 238)  # near-white warm
ORI_BRIGHT = (255, 252, 200)  # warm yellow
ORI_MID    = (255, 240, 155)  # gold
ORI_DIM    = (190, 140,  35)  # amber
ORI_WISP   = (255, 253, 225)  # pale warm
```

**Blend mode:** PIL `ImageChops.screen()` — this is the locked method. Do not substitute ffmpeg blend filter.

---

## SECTION 2: What a Proper Video Stitching Editor Should Look Like

This session took ~5.5 hours to produce what should have been a 30-minute task: take four approved clips, stitch them together, apply one magic effect to one beat, export a preview MP4. That gap exists because there is no assembly tool Kim can use herself.

---

### What Kim Actually Needed Today (the real workflow)

In plain terms, here is what happened repeatedly:

1. **Locate the approved clip** for each segment (intro, Phase A, Phase B, resolution/win)
2. **Confirm which exact file** is the approved version (not a draft, not a wrong bitrate, not missing the gong sounds) — this required Directus queries, disk searches, ffprobe, and back-and-forth
3. **Apply a visual effect** to one clip (the resolution beat: shell glow or traveling trail)
4. **Preview it** — open in QuickTime, assess, request adjustments
5. **Stitch the four segments** into one sequential MP4 with correct timing
6. **Export the final assembled video** as a small, normalized file ready for app testing

None of steps 1–6 have a UI. Everything happened through Claude running Bash commands, Python scripts, and ffprobe — with Kim watching and reacting.

---

### What Existing Tools Offer

#### DaVinci Resolve (free, Mac native)
**What it does well:**
- Full non-linear timeline: import clips, arrange, trim, preview in real time
- Compositing layer for overlaying effects (magic trail could be imported as a video overlay)
- Color grading, audio mixing, export presets
- Free tier is genuinely capable — not crippled

**Where it falls short for this pipeline:**
- Learning curve is real (2–4 hours to be comfortable)
- Does not integrate with Directus — Kim would still need Claude to tell her "use file X not file Y"
- Cannot run our Python magic compositor scripts natively; magic effects still need to be pre-rendered by Claude and handed to Kim as a video file
- Resolve's "Color Science" is overkill for our use case

**Verdict: This solves the ASSEMBLY problem today.** Kim could import 4 clips, arrange them on a timeline, preview, and export — without Claude. The only thing Claude needs to do first is confirm which clips to use and pre-render any magic effect clips.

---

#### CapCut (free, desktop)
**What it does well:**
- Dead simple timeline — designed for non-technical users
- Drag and drop clips, add overlays, trim
- Exports quickly in standard formats
- Zero learning curve if you've ever used any video app

**Where it falls short:**
- Limited codec control (can't guarantee H.264/yuv420p/faststart to our spec)
- No ffprobe-level inspection
- Proprietary file handling may add watermarks on free tier (check)
- Not ideal for professional quality control

**Verdict: Good for quick previews. Not for final production exports.**

---

#### iMovie (free, already on Kim's Mac)
**What it does well:**
- Kim already has it — zero install, zero learning curve
- Basic timeline with clips, can add video overlays
- Exports to standard MP4

**Where it falls short:**
- Limited codec and bitrate control
- No color grading
- Can't import arbitrary video overlays in arbitrary formats (limited codec support)
- Some of our clips (from Kling, ByteDance) may not import cleanly without re-encoding first

**Verdict: Works for basic stitch previews. Not production-grade.**

---

#### Adobe Premiere Pro
**Cost:** ~$60/month. Not worth it for this use case.

#### Final Cut Pro
**Cost:** $300 one-time. Better value than Premiere for Mac, but still overkill.

---

#### ScreenFlow (Mac screen recorder + basic editor)
**Cost:** ~$150. Has a basic timeline. Not designed for this use case. Skip.

---

#### Vimeo / YouTube editor (cloud-based)
**Verdict:** Not useful. No custom magic effect overlay, no codec control, not private during production.

---

### What Our Custom Storyboard Should Eventually Replace

The ideal MindfulNest-specific assembly component inside the existing beat generator / storyboard tool would look like this:

**Beat-level timeline:**
- Each beat is a numbered slot (Beat 01: Tessa appears, Beat 02: heartwood, etc.)
- Each slot shows: clip thumbnail, duration, lipsync status badge (lipsynced / pending / not needed), magic effect badge (shell glow / trail / none / needs generation)

**Clip library panel (right side):**
- Lists all approved clips from Directus (`prod_assets` where `status = 'approved'` and `kim_verdict = 'approved'`)
- Shows filename, duration, file size
- Kim drags a clip from library into a beat slot

**One-click effect toggle per clip:**
- Each beat slot has an "effects" dropdown: None / Shell Glow / Traveling Trail
- Selecting an effect triggers a server-side render of the effect and updates the clip in the slot
- Kim does not need to know which Python script to run

**In-browser preview:**
- Play button assembles the current slot sequence in memory and streams a preview
- No export needed for casual review — just press play

**Audio waveform strip:**
- Below the timeline, show the audio waveform of the assembled sequence
- Kim can see where speech starts and ends in each beat, catch silence gaps, verify audio continuity

**Export button:**
- Triggers the server-side ffmpeg concat + normalize pipeline (LD-284 `NORMALIZATION_BEFORE_CONCAT_V1`)
- Outputs a normalized MP4 with the canonical codec spec (H.264 High / yuv420p / 1280×720 / 24fps / AAC 128kbps / faststart)
- Posts the result to `prod_assets` in Directus automatically
- Shows Kim a download link and the ffprobe size readout

**Kim drives it entirely.** Claude's job shifts to: confirm which clips are approved (query Directus), pre-render any effect clips Kim requests, answer questions. Claude is NOT in the assembly loop.

---

### The Honest Recommendation

**Right now, today, given that Kim is non-technical and time is the constraint:**

**Option A — Use DaVinci Resolve for final assembly NOW**

Pros:
- Resolves the 5-hour back-and-forth problem immediately
- Free. Already available on Mac.
- Kim imports 4 approved clips, arranges timeline, exports. Done in 20 minutes once comfortable.
- Claude pre-renders any magic effect clips and hands Kim an MP4 file to drop into Resolve

Cons:
- 2-4 hour learning investment upfront (watch one 30-min YouTube tutorial, then practice with the Event 1 clips)
- Kim still needs Claude to tell her which files to import (Directus lookup) and to generate magic effects
- No integration with Directus — assembly state not recorded anywhere

**Option B — Build the beat-slot editor into the existing storyboard tool**

Pros:
- Fully integrated with Directus — assembly state is tracked
- Kim would never need to know filenames
- Lipsync status, effect status, everything visible in one place
- This is the RIGHT long-term solution

Cons:
- 6–10 hours of Claude development time to build (extending the beat generator HTML tool + server-side concat endpoint)
- Not available today
- Requires careful alignment with production server endpoints and normalization pipeline (LD-284)

**Option C — Hybrid (RECOMMENDED)**

Claude produces individual normalized clips to spec (this already works). Kim assembles in DaVinci Resolve for now. In parallel, Claude builds the beat-slot editor as a background project.

**Sequence:**
1. This week: Kim installs DaVinci Resolve, watches a 30-minute "import, arrange, export" tutorial. Claude gives her the 4 approved clip filenames and file paths via a Directus query at the start of each assembly session.
2. This week: Claude adds a `GET /api/scene/clips_ready` endpoint to `production_server.py` that returns a JSON list of approved clips with file:// paths formatted for easy copy-paste into Resolve's import dialog.
3. Next 2 weeks: Claude builds the beat-slot editor into the beat generator HTML tool as a new tab — "Assembly" — wired to the server's concat endpoint.
4. Once the beat-slot editor is working: Kim stops using Resolve for this pipeline. Assembly happens in the browser, same as storyboard review.

**Do Option A (Resolve) first because it unblocks Kim TODAY. Build Option B in the background because it is the correct architecture.**

The cost of Option A is 2–4 hours of Kim's time once. The cost of NOT doing Option A is continuing to spend 5-hour sessions on what should be a 20-minute task.

---

### One More Thing: The File Identity Problem

The single biggest source of wasted time today was not the video editing itself — it was figuring out which file was the right file. The session spent significant time discovering that the Phase B in the current full video was the wrong version (the stitched/cues version without gong/intro/outro), that the "whoah" lipsync never existed, that `beat01_tessa_glow_startend_20260422T182043Z.mp4` was the canonical Kling source for Beat 01.

**None of this should require investigation.** It should be a lookup.

The beat-slot editor fixes this because it only shows Kim clips that are in Directus with `status = 'approved'` and `kim_verdict = 'approved'`. There is no ambiguity. The canonical file is the one Directus points to. If it is wrong, fix the Directus record, not the editor.

Until the editor exists: at the start of every assembly session, Claude runs a Directus query to produce a simple table:

| Segment | Approved File | Duration | Notes |
|---------|--------------|----------|-------|
| Intro   | arc1_event1_intro_v1.mp4 | 57.4s | approved 2026-04-20 |
| Phase A | phase_a_modified_v2.mp4  | 29.7s | bed normalized |
| Phase B | m1_phase_b_canonical_v1_20260420.mp4 | 148.1s | stereo, gong+intro+outtro |
| Win     | res_lipsync_A_v1.mp4 + tessa_magic_live_composite_v5.mp4 | TBD | stitch these two |

This table takes 2 minutes to produce and saves hours of searching.

---

*End of document. Written 2026-04-26 after session cb6fe1f0.*

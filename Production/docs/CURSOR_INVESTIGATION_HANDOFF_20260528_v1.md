# MindfulNest Storyboard v59 — Root Cause Investigation Handoff
**Date:** 2026-05-28  
**For:** Cursor (use claude-4-opus model, MAX context, enable web search)  
**Purpose:** Understand WHY the v59 React storyboard rendering pipeline keeps breaking despite repeated fixes, and produce a concrete repair plan  
**Tone required:** Adversarial self-audit. Assume every prior "fix" is potentially wrong.

---

## How to Use Cursor Effectively for This Investigation

- **Model:** Use `claude-opus-4` (or `claude-4-opus` depending on UI). Do NOT use Sonnet for this — you need the reasoning depth.
- **Context window:** Enable MAX context / long context mode if available.
- **File reading:** Read WHOLE files, not excerpts. The bugs are in interactions between files, not single lines.
- **Do NOT use Explore agent** for this task — it reads excerpts and will miss cross-file interactions.
- **Iteration:** Use `--resume <chatId>` to continue a session across turns rather than starting fresh each time.
- **What to do:** Read the files listed below in full. Then answer the diagnostic questions. Then produce the repair plan.

---

## Project Layout (Two-Tree Architecture — CRITICAL)

```
~/Projects/mindfulnest-tooling/   ← CODE (git repo, source of truth for code)
  Production/tools/
    production_server.py          ← Python HTTP server (runs on :5111)
    server_handlers/
      background.py               ← magic_video, watercolor_animate handlers
      phases.py                   ← watercolor_list, watercolor_file handlers
    magic_compositor.py           ← FFmpeg composite pipeline
    path_picker.html              ← Path drawing + animate popup (served at /magic)
    storyboard-v2/src/            ← React/Preact TypeScript storyboard app
      components/StoryboardTab.tsx
      components/phase/PhaseProducer.tsx
      components/tabs/PhaseBTab.tsx
      api/endpoints.ts

~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/  ← DATA + DEPLOY TARGET
  Production/
    Event_1/
      production_state.json       ← Live state (beats, phase_b cues, magic_video_path, etc.)
      storyboard_v59_prod.html    ← Deployed React bundle (single HTML file)
      animation_clips/            ← Lipsync MP4 files (beat_01_lipsync_*.mp4)
      magic_video_beat_01_*.mp4   ← Magic video composites
    assets/
      watercolor_library/         ← hands_rubbing.png + hands_rubbing_animated_*.mp4
    tools/                        ← DEPLOY COPY of Python files (must match tooling/)
```

**Deploy script:** `bash Production/scripts/deploy_storyboard_v59.sh`  
This (1) runs `npm run build` in storyboard-v2, (2) rsync-mirrors tooling→Dropbox, (3) restarts server.  
**NEVER edit Python files in Dropbox directly.** Always edit in `~/Projects/mindfulnest-tooling/` and deploy.

---

## Current State as of 2026-05-28 03:34 UTC

**Server:** PID 66673, port 5111, build sha `b53f630`  
**Branch:** `feature/overnight-watercolor-rebuild-20260526`  
**Git log (recent):**
```
b53f630 chore: update .last_deploy
a7f415e Revert phases.py animated-glob: fixes broken black thumbnails in Phase B
5cb444f Fix Bug 2: suppress TTS audio when magic_video preview active
46d7654 fix: correct watercolor state schema — use disk glob + watercolor_animated_overrides
ed361ee fix: 3-bug fix — trail position, audio doubling, watercolor state writeback
7e54ff0 ... (prior session: 5 magic_video ffmpeg fixes)
```

**production_state.json Phase B cues:**
```json
[
  {"animation": "fade_in", "cue_type": "png", "duration_ms": 25000, "key": "spell_title", "timestamp_ms": 13307},
  {"animation": "fade_in", "cue_type": "png", "duration_ms": 40000, "key": "hands_rubbing", "timestamp_ms": 29937},
  {"animation": "fade_in", "cue_type": "png", "duration_ms": 50000, "key": "hands_original", "timestamp_ms": 41420},
  {"animation": "fade_in", "cue_type": "png", "duration_ms": 60000, "key": "hands_far", "timestamp_ms": 81593}
]
```
All cues still have `key: "hands_rubbing"` (static), `cue_type: "png"`. The animated key (`hands_rubbing_animated_20260527-223413`) was never persisted because of the RC1 chain failure described below.

---

## The Three Presenting Bugs

### Bug 1 — Magic trail in wrong position
**Symptom:** Kim draws a path circling Tessa's shell; the rendered trail appears diagonally across the screen.  
**Root cause (diagnosed):** path_picker.html used browser `<video>.currentTime` to extract a frame. This timed out, fell back to a still image (`/api/beat/thumbnail/beat_01`) with different aspect ratio. Path coordinates (normalized 0–1) were authored against the fallback still's aspect ratio but applied to the video (720×544). Aspect ratio mismatch → coordinates map to wrong pixel positions.  
**Fix applied:** Added server-side ffmpeg endpoint `/api/storyboard/video_frame?path=<encoded>&t=0` that returns a PNG. path_picker.html now fetches this PNG as background. `window.__pathAuthoredAgainst = {width: 720, height: 544}` set from the PNG. `_aspect_correct()` method in `magic_compositor.py` remaps coordinates if authored-against differs from compositor canvas.  
**Smoke test result:** PASS — frame extraction confirmed (683KB PNG, canvas 720×544, `__pathAuthoredAgainst` set, no fallback used).  
**UNVERIFIED:** Whether the trail actually appears at the correct pixel position in the rendered magic video. This requires Kim to draw a path and visually inspect. The mechanical fix is in place but the visual hasn't been confirmed.

### Bug 2 — Audio doubled ("whoah where is it going now?" plays twice)
**Symptom:** When previewing a magic_video beat, dialogue audio plays twice simultaneously.  
**Root cause (diagnosed):** StoryboardTab.tsx `handlePreviewOption` and its `useEffect` both call `safePlay(audioRef.current)` for any non-lipsync preview (`!isLipsyncPreview`). For magic_video preview (`optIdx === -1`, `_magicVideoOk = true`), the `<video>` already has baked-in lipsync audio. The separate TTS `<audio>` element also plays → doubled.  
**Fix applied:** Added `hasMagicVideoAudio = isStillFinalPreview && _magicVideoOk` guard at 4 locations in StoryboardTab.tsx. Dep arrays updated.  
**Build:** Compiled clean, deployed sha `e42db8f` (now `b53f630` includes this).  
**UNVERIFIED:** Browser audio element states not confirmed with playback test. The guard is in the source and compiled correctly, but actual runtime audio behavior unconfirmed.

### Bug 3 — Watercolor not animated in Phase B despite successful animation
**Symptom:** Kim ran watercolor animate successfully (created `hands_rubbing_animated_20260527-223413.mp4`). Phase B tab still shows static watercolors.  
**Root causes (multiple, layered):**

**3a — Phase B display is INTENTIONALLY static (LD-821)**  
Per `LD-821 WATERCOLOR_OVERLAY_PNG_CSS_ARCHITECTURE_V1`, the Phase B browser PREVIEW always shows a static PNG with CSS opacity animation. The animated MP4 is used only for SERVER-SIDE Stitcher output. The browser never plays the animated MP4 inline. Kim may be expecting to see the animation playing in the browser, but this is not implemented.

**3b — RC1 cue update never fired**  
After animation, `path_picker.html` sends `postMessage({type: 'mn-magic-or-animate-complete', ...})` to the opener window. `PhaseProducer.tsx` listens and calls `persistCues()` to update the cue's `watercolor_key` from `"hands_rubbing"` to `"hands_rubbing_animated_20260527-223413"`. This update never fired because:
- Kim's 22:34 animation ran under old server code (before 23:12 fix)
- The old cursor-agent code had wrong state schema → returned HTTP 500 → `path_picker.html` threw on `if (!resp.ok)` → postMessage never sent → RC1 never fired

**3c — Broken thumbnails caused by our own fix (NOW FIXED)**  
commit `46d7654` added an "animated-glob-first" block to `handle_phase_watercolor_file` that made `?key=hands_rubbing` return MP4 instead of PNG. `watercolor_list` sets `thumb_url = ?key=hands_rubbing` (base key) for animated entries. `<img src={thumb_url}>` received MP4 → black broken thumbnails. Reverted in `a7f415e`.

**3d — watercolor_animated_overrides never written**  
The state writeback code (writing `state["watercolor_animated_overrides"][key]`) is now deployed correctly. But it has never successfully fired because Kim's most recent animation predates the fix. Running a fresh animation should trigger it.

---

## What Needs Investigation: The Systemic Question

Kim's question is not "find this bug" — it's **"why does this pipeline keep breaking, and why do fixes repeatedly fail to hold?"**

Here is the honest diagnosis of the systemic failure:

### Failure Mode 1: Verification at the wrong layer
Every fix has been verified at the **server layer** (curl returns correct HTTP status + Content-Type, py_compile passes, grep finds the code). But bugs manifest at the **browser rendering layer** (what `<img>` displays, what `<audio>` plays, what the canvas draws). These are different contracts. A server that returns `200 video/mp4` is "working" by server metrics but broken by browser metrics. The verification methodology needs to START from the browser, not the server.

### Failure Mode 2: Fix side effects create new breaks
Each fix changes behavior that other consumers depend on. The animated-glob fix made thumbnail requests return MP4. The state writeback added a 500-returning verify that blocked the postMessage chain. No one is maintaining a contract table: "watercolor_file endpoint: consumer=thumbnail needs image/png; consumer=stitcher needs video/mp4."

### Failure Mode 3: Multiple state locations, no single source of truth
The watercolor animation state lives in:
1. `production_state.json` → `phase_b.phase_b_watercolor_cues_json[]` (cue key + cue_type)
2. `production_state.json` → `watercolor_animated_overrides` (just-added key)
3. Disk: `Production/assets/watercolor_library/` (actual files)
4. Directus: `prod_assets` rows (registered file metadata)
5. React component state: `watercolors[]` array (refreshed from `/api/phase/watercolor_list`)
6. React component state: `cues[]` (from `state.phase_b.phase_b_watercolor_cues_json`)

When these diverge (Kim animates → file on disk but cue key not updated), everything downstream breaks. There is no atomic operation that updates all layers consistently.

### Failure Mode 4: v59 React rewrite broke v2 patterns without clear replacement
Kim says v2 worked. v2 was a standalone HTML storyboard (built by `build_storyboard.py`). v59 is a full React/Preact TypeScript app. The watercolor overlay, path picker integration, and Phase B display were all reimplemented from scratch. Some v2 patterns that worked:
- v2 watercolor display: probably just `<img>` with a static PNG URL — simple, no dynamic key management
- v2 path picker: probably simpler, no server-side frame extraction, no aspect correction
- v2 audio: probably just one audio element, no complex lipsync guard logic

The v59 rewrite added complexity (RC1 cue updates, animated key management, lipsync guards, state writeback, postMessage chains) that v2 never had. Each layer of new complexity adds a new failure point.

### Failure Mode 5: "Found the root cause" is a diagnosis problem, not a lying problem
When Claude says "found the root cause," it means "found ONE contributing bug in the chain." But the actual symptoms have 3-5 concurrent bugs interacting. Fixing bug 1 doesn't move the symptom because bugs 2-5 are still active. And sometimes fixing bug 1 creates bug 6 (as happened with the animated-glob). The correct approach is: **enumerate ALL contributing bugs before patching any of them.**

---

## Files to Read for Investigation

Read these files IN FULL before forming any hypothesis:

```
~/Projects/mindfulnest-tooling/Production/tools/server_handlers/phases.py
~/Projects/mindfulnest-tooling/Production/tools/server_handlers/background.py    (lines 3800-4150 most relevant for watercolor)
~/Projects/mindfulnest-tooling/Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx
~/Projects/mindfulnest-tooling/Production/tools/storyboard-v2/src/components/StoryboardTab.tsx   (lines 1680-2040 most relevant)
~/Projects/mindberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1/production_state.json
```

---

## Diagnostic Questions for the Investigation

Answer each with POSITIVE EVIDENCE (grep output, file read, curl result) — not reasoning alone:

**Q1 — Watercolor thumbnail contract:**
What does `GET /api/phase/watercolor_file?key=hands_rubbing` return right now (after revert)? What does `?key=hands_rubbing_animated_20260527-223413` return? Do these match what `<img>` and `<video>` elements respectively need?

**Q2 — RC1 chain completeness:**
Trace the full chain: animate button click → path_picker.html → POST `/api/watercolor/animate` → `handle_watercolor_animate` → response body → postMessage → `PhaseProducer.onMsg` → `persistCues()` → server PATCH. At each step: what is the expected value and what is the actual value? At which step does the chain break?

**Q3 — Phase B display contract (LD-821):**
What exactly does LD-821 say? Is the "animated watercolor" feature supposed to be visible in the Phase B browser preview at all, or only in the Stitcher output? If only Stitcher: is the Stitcher working correctly with the current cue `key: "hands_rubbing"`, `cue_type: "png"`?

**Q4 — Cue state after fresh animation:**
If Kim runs a fresh `hands_rubbing` animation RIGHT NOW (with the current deployed server): (a) Does `handle_watercolor_animate` return HTTP 200? (b) Does `watercolor_animated_overrides` get written to production_state.json? (c) Does the postMessage fire? (d) Does the cue key get updated? Run through the full chain mechanically.

**Q5 — v2 vs v59 watercolor architecture:**
Look at git log for any v2-era code. How did v2 handle watercolor overlays in Phase B? Did v2 have animated watercolors at all, or just static PNGs? If v2 worked without animated watercolors, what exactly is v59 trying to add that v2 didn't have?

**Q6 — Bug 1 visual verification gap:**
The server-side frame extraction works (683KB PNG confirmed). The `_aspect_correct()` math is deployed. But the visual hasn't been confirmed. What would need to be true for the trail to appear at the correct position? What's the complete path from "Kim draws path" to "frame appears at correct pixels"? Are there any other coordinate transformations in the chain that haven't been audited?

**Q7 — Bug 2 runtime confirmation gap:**
The `hasMagicVideoAudio` guard is in source and compiled correctly. But: does the guard ACTUALLY prevent `audioRef.current.play()`? Is there any other code path that starts TTS audio for a magic_video beat? Check for: useEffect deps not updated, other event handlers that call safePlay, any "Play All" function that ignores the guard.

---

## What a Successful Investigation Looks Like

Produce a document with:

1. **Contract table**: For each endpoint and component, WHO calls it, WHAT format it expects (PNG/MP4/JSON), and WHETHER that contract is currently satisfied.

2. **State sync map**: For each piece of state (cue key, animated file, watercolor_animated_overrides), WHERE it lives, HOW it gets updated, and WHEN it diverges.

3. **Full bug chain for Bug 3**: Every step from "Kim clicks Animate" to "Phase B Stitcher uses animated MP4", with the current status (working/broken/untested) at each step.

4. **v2 vs v59 delta for watercolors**: Specifically what v2 had that worked, what v59 changed, and whether those changes were improvements or regressions.

5. **Repair plan**: Not "fix this line." A full plan that addresses: (a) broken thumbnails (b) RC1 chain reliability (c) whether LD-821 design is correct (d) whether the state layering can be simplified.

---

## Known Working Baseline

- `GET /api/phase/watercolor_file?key=hands_rubbing` → `image/png` ✓ (post-revert)
- `GET /api/phase/watercolor_file?key=hands_rubbing_animated_20260527-223413` → `video/mp4` ✓
- `GET /api/storyboard/video_frame?path=<lipsync>&t=0` → `image/png` 683KB ✓
- `beat_01.magic_video_path_exists: true` ✓
- `hasMagicVideoAudio` guard compiled into storyboard sha `b53f630` ✓
- All 4 Python files pass py_compile ✓
- Tooling ↔ Dropbox: all files SHA256 identical ✓

---

## What Is NOT Yet Verified (Requires Browser Observation)

- Whether the magic trail appears at the correct pixel position (visual)
- Whether audio plays exactly once during magic_video preview (audio)
- Whether the RC1 cue update fires and persists after a fresh animation
- Whether the Stitcher uses the animated MP4 when cue_type is still "png"


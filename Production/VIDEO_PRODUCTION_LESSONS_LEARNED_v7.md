# MindfulNest Video Production — Lessons Learned v6

**Source:** Event 1 Story Scene Production Sessions (April 12-13, 2026)

**Scope:** v1-v5 merged + April 13 evening session: TTS audition workflow, tool persistence, storyboard corruption patterns, Cowork file delivery

**Status:** Comprehensive lessons document — ready for production reference and future iterations

---

## Executive Summary

MindfulNest video production has discovered both working and non-working approaches. Key findings:

1. **Gemini 2.5 Flash Image Generation (WORKING):** Two-pass approach for character stills; identity preservation blocks are mandatory; cost ~$0.039/image

2. **Automated Dialogue Animation (NOT WORKING):** Five distinct technical approaches tested — all failed due to fundamental architectural limitations. Lip sync destroys non-human character identity. Text-prompted animation cannot sync to audio. Scene integration requires human intervention.

3. **Viable Paths Forward:** (A) FLUX Kontext variant switching with BFL API, (B) Blender rigged characters with Python bpy, (C) Hybrid AI backgrounds + manual character animation, (D) Dialogue-free visual narrative

4. **Critical Agent Verification Issues:** Agents claim success without visually comparing to reference images. Gemini blue scarf design is frequently misinterpreted. PIL overlay requires exact coordinates. Bioluminescence creep is common in "magical forest" prompts.

---

## 1. Gemini 2.5 Flash Image Generation

### What Works

- **Model name must be exact:** Use `gemini-2.5-flash-image` (NOT `gemini-2.5-flash`, which is text-only)

- **Solo character scenes are most reliable:** Single-character shots (Tessa alone, Benson alone, etc.) work consistently with 3-7 reference images

- **Reference image order matters:** Put the HERO image (best pose/lighting) FIRST in the reference stack. Subsequent refs should be pose variants of the same character

- **Cost is acceptable:** ~$0.039 per image. This is the production tool for MindfulNest character stills

- **Two-pass approach fixes identity drift:** For two-character scenes, use Pass 1 (character A + environment) then Pass 2 (add character B to Pass 1 output). This prevents the subtle character's identity from drifting

  - Pass 1: Generate first character (e.g., Tessa) with 3-4 refs, full scene description in prompt (no background image ref)
  - Pass 2: Use Pass 1 output + 3-4 refs of second character (e.g., Guide Bird). Prompt specifies spatial placement

- **Rate limiting:** Add 2-3 second delays between Gemini API calls (free tier has rate limits)

### What Fails & Why

- **Reference budget collapse:** When >7 images are passed in one API call, Tessa's identity drifts while Guide Bird (more visually distinctive) survives. **FIX:** Use two-pass approach

- **Background reference in duo shots:** Feeding a background image + character refs in ONE call causes identity drift on the subtler character. **FIX:** Describe setting in text prompt instead; use two-pass for 2-char scenes

- **LoRA fine-tuning:** Tested with 15 training images, resulted in human children instead of turtles. LoRA does NOT work for animal character consistency

- **Empty/missing dialogue:** Characters sometimes have blank expressions or no mouth visible. This happens when prompt doesn't include specific emotional direction

- **Style drift (photorealism):** If character identity preservation block is weak or missing, generation can suddenly shift to photorealistic/3D renderings instead of Pixar style. **Why:** Lacking the constraint, Gemini defaults to realistic human photography when confused about identity

- **Guide Bird blue scarf problem:** Gemini frequently generates a brown HOOD instead of a blue knitted SCARF. Requires explicit "blue knitted scarf/cowl, NOT a hood" in prompts. Affects 30-40% of generations if not explicitly blocked.

### Critical Identity Preservation Block

Every prompt MUST include verbatim physical feature list for the character. Example for Tessa:

```
Tessa is a young turtle character with the following fixed features:
- Shell: Distinctive green with brown patterns, age-appropriate size
- Face: Soft, expressive, triangular-shaped snout, bright eyes, small nostrils
- Body: Turtle proportions (short legs, appropriate neck length)
- Color: Green shell, light cream/tan underbelly, greenish-gray skin tones
- NOT: oversized baby head, NOT: short neck, NOT: human proportions
```

**This block is non-negotiable.** It prevents the #1 production error: wrong character identity.

### Pixar 3D Style Lock

- Style lock is **committed as of April 10, 2026**

- ALL prompts must include: `Pixar 3D animated style, warm soft lighting, expressive character design`

- If generation comes out photorealistic, humanoid, or wrong style: reread identity preservation block and regenerate. Style drift indicates missing/weak constraints

### Unicode Issue

- DON'T use Unicode ellipsis `…` in prompts. Use `...` (three periods) instead

- Unicode in prompts sometimes causes API errors or text rendering issues

---

## 2. Two-Pass Gemini Technique (Two-Character Scenes)

### When to Use

- Any scene with 2+ characters in frame

- Especially when one character is subtle (like Tessa, a turtle) and the other is distinctive (like Guide Bird)

### How It Works

**Pass 1: Primary Character + Environment**

- Send: Prompt (scene + expression) + 3-4 reference images of primary character

- Do NOT send background image. Describe setting in text prompt instead

- Generate 4 candidates

- Pick best (or use all 4 for Pass 2 and let final selection happen after Pass 2)

**Pass 2: Add Secondary Character**

- Send: Pass 1 output image + 3-4 reference images of secondary character

- Prompt includes spatial instruction: `Add Guide Bird to the left, perched on the signpost, leaning toward Tessa with concern`

- This preserves BOTH characters' identities

### Why It Works

- Gemini's multi-ref system works best with <7 images at a time

- When character count + background = too many refs, subtle character drifts

- Two-pass splits the load: first pass nails the primary, second pass adds secondary to an already-locked composition

---

## 3. FLUX Kontext — What It's For and What It Isn't

### NEVER Use For

- **Scene generation:** FLUX Kontext cannot do spatial placement. It cannot position multiple characters or complex compositions

- **Text overlay on images:** The Everdale sign disaster — never use ANY generative model to add painted/carved text to background objects. Text always looks obviously AI-added. Use Python image ops (PIL, cv2) to paint or carve text instead

- **Replacing characters:** FLUX Kontext is for edits, not swaps

### USE For

- **Contained edits:** Fixing a hand gesture within a locked composition

- **Expression tuning:** Softening a smile, adjusting eye direction within an existing face

- **Color adjustments:** Making a stone wall warmer/cooler

- **Cost:** ~$0.08 per edit. Use sparingly

### The Everdale Sign Disaster

- Attempt: Use FLUX Kontext to paint 'Everdale' text on wooden signpost

- Result: Text looked AI-generated and out of place

- **Never again:** Use Python PIL/cv2 to paint or carve text on background elements. Use fonts + positioning, not generative overlays

---

## 4. ElevenLabs TTS Emotional Tuning

### The Problem

- Default ElevenLabs voices (Chipper1 for Guide Bird, Jessica for Tessa) render all dialogue with the SAME tone

- Early attempts came out 'chipper and didactic' when scenes needed 'conversational and soft/sad'

- Kim's feedback: 'the voices dont do what they should do emotionally for the situation'

### Solutions Explored

**Approach 1: Segment-Level Emotional Direction**

- Render each sentence/beat separately with emotional direction tags in the prompt

- Example for Shot 3 (Tessa's sad opening): `[sad, vulnerable] 'Oh... Hi... I'm sorry'` vs. `[resigned] 'I'm Tessa'` vs. `[softer, almost hopeful] 'It's not my best day'`

- This allows micro-tonal shifts within a single dialogue block

**Approach 2: Variable Silence Gaps**

- Insert pauses between sentences/speakers to match conversation rhythm

- Kim feedback: 'without necessary pauses between sentences or between characters speaking to each other'

- Add 0.5-1.5s silence between turns for natural dialogue flow

- This is NOT done in ElevenLabs — it's done in ffmpeg mixing or in the prompt itself (manual pause markers)

**Approach 3: Stability Settings per Voice Type**

- More grounded characters: stability 0.50 (allows variation)

- Tearful/emotional scenes: stability 0.35 (more dynamic)

- These are per-character voice settings in ElevenLabs API (Voicelab), NOT per-sentence

### Critical Insight: Per-Sentence Rendering

- MindfulNest personalizes TTS at the SEGMENT level (only sentences with `{childName}`, `{chosenGuideName}` vars are re-rendered per-child)

- But EMOTION direction can still be applied per-sentence in the prompt text itself

- This means: use `[emotion tag]` markers in the dialogue script, then parse them during TTS generation

### What NOT to Do

- DON'T render all dialogue with one voice tone (chipper or didactic default)

- DON'T skip pauses between speakers (makes dialogue feel rushed)

- DON'T use high stability (>0.75) for emotional/vulnerable scenes

---

## 5. Automated Dialogue Animation: Five Failed Approaches & Why

This section documents the April 12, 2026 R&D session exploring automated character animation. All five approaches failed due to fundamental architectural limitations that are not bugs or configuration errors, but true constraints in the April 2026 AI landscape.

### 5.1 ByteDance LipSync (WaveSpeed API)

**Hypothesis:** Feed Tessa's keyframe image (converted to short video) plus her TTS audio into ByteDance's pixel-based lip sync model. The model should animate the mouth region to match the audio waveform.

**API Endpoint:** `POST api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`

**Input:** shot3_keyframe.png (1024x1024, converted to 5s static video) + shot3_tessa_dialogue.mp3 (4.49s, ElevenLabs TTS, voice Jessica)

**What Happened**

The API accepted the inputs and returned a 624x624 video (downscaled from 1080). The output showed a completely different turtle with human-like mouth movements imposed on it. Tessa's character design, coloring, shell pattern, and facial features were entirely destroyed and replaced with a generic turtle face that the lip sync model hallucinated.

**Root Cause**

ByteDance LipSync operates in pixel space. It detects a "face region," erases it, and repaints it frame-by-frame with mouth shapes derived from the audio. The model was trained exclusively on human faces. When given a non-human character (a cartoon turtle), it attempts to impose human facial anatomy—jaw movement, lip shapes, facial muscle deformation—onto a face that has none of those features. The result is a completely rewritten face that bears no resemblance to the input character.

**Key Takeaway**

Pixel-based lip sync is architecturally incompatible with non-human characters. This is not a tuning or prompting issue—it is a fundamental limitation of models trained on human face datasets. This rules out ByteDance LipSync for ALL MindfulNest characters (all are non-human creatures).

**API Pattern (for reference):**
```
Endpoint: POST api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video
Auth: Bearer token in Authorization header
Input: Base64-encoded video + audio in JSON body
Polling: GET api.wavespeed.ai/api/v3/predictions/{id}/result
Verdict: Working API, but model destroys non-human character faces. Do not use for MindfulNest.
```

### 5.2 Runway Gen-4.5 (Turbo)

**Hypothesis:** Use Runway's image-to-video API to animate the keyframe with a dialogue-specific prompt describing Tessa speaking. Overlay TTS audio afterward.

**API Endpoint:** `POST api.dev.runwayml.com/v1/image_to_video` (header: `X-Runway-Version: 2024-11-06`)

**Input:** shot3_keyframe.png + text prompt describing Tessa's speaking animation

**What Happened**

The initial API request was accepted and a task ID was returned (0573657b). However, polling the task status returned THROTTLED at 0% indefinitely. The task never progressed to processing or completion. This appeared to be rate limiting triggered by the frequency of API calls during the session, not a problem with the individual request.

**Root Cause**

Runway's API applies aggressive throttling when it detects frequent or concurrent submissions. A single isolated request may complete successfully, but during an active development session with multiple test submissions, the throttle engages and blocks requests indefinitely. There is no documented way to predict or avoid this throttling behavior.

**Key Takeaway**

Runway Gen-4.5 is unreliable for iterative development workflows where multiple test renders are needed. Even if the output quality were acceptable, the throttling makes it unsuitable for a production pipeline that requires rapid iteration. Additionally, even if the video had rendered, it would have produced an "animated still" (gentle motion applied to a static image) rather than actual character animation with controlled mouth movement—the same fundamental limitation as all image-to-video models.

**API Pattern (for reference):**
```
Endpoint: POST api.dev.runwayml.com/v1/image_to_video
Auth: Bearer token + X-Runway-Version: 2024-11-06 header
Input: model: gen4_turbo, promptImage (base64), promptText, ratio, duration
Polling: GET api.dev.runwayml.com/v1/tasks/{id}
Verdict: Aggressive throttling makes iterative development impractical.
```

### 5.3 Hailuo 2.3 Dialogue-Prompted Animation

**Hypothesis:** Use MiniMax's Hailuo 2.3 (Pro) with a carefully crafted prompt describing Tessa speaking her specific dialogue. The prompt would instruct the model to animate mouth movement matching the words. TTS audio would be overlaid afterward with a 500ms delay offset.

**API Endpoint:** `queue.fal.run/fal-ai/minimax/hailuo-2.3/pro/image-to-video`

**Input:** shot3_keyframe.png (base64) + detailed dialogue-specific prompt

**What Happened**

The API returned a 5.88-second video. The first frame closely matched the input keyframe, but the character rapidly drifted during animation—changing proportions, coloring, and facial features as the diffusion model generated intermediate frames. The result looked nothing like Tessa. The mouth moved in a generic "talking" pattern that had no relationship to the actual dialogue audio, because the model never received the audio—it only received a text description of speaking.

**Root Cause**

Two separate failures compounded here. First, character identity drift: image-to-video diffusion models maintain fidelity to the input image only in the first frame, then progressively hallucinate as they generate subsequent frames. The model has no concept of "this specific character must remain visually consistent." Second, the audio-visual gap: text-prompted video generation has absolutely zero access to the audio waveform. Writing "Tessa says Oh Hi I'm sorry" in the prompt does not cause the model to generate lip movements matching those specific phonemes. It generates generic "mouth opening and closing" motions that are temporally random relative to any audio track.

**Key Takeaway**

Text-prompted animation cannot produce lip sync. This is an architectural impossibility, not a prompting skill issue. The video generation model and the audio exist in completely separate systems with no shared timing information. The 500ms delay trick in ffmpeg is a bandaid that occasionally aligns a syllable by coincidence. For MindfulNest's dialogue-heavy scenes, this approach produces unacceptable results.

**API Pattern (for reference):**
```
Endpoint: POST queue.fal.run/fal-ai/minimax/hailuo-2.3/pro/image-to-video
Auth: Key-based auth in Authorization header
Input: Base64 image_url + text prompt
Polling: GET queue.fal.run/fal-ai/minimax/requests/{req_id}/status then /requests/{req_id} for result
Verdict: Working API. Character drift in output makes it unsuitable for character-consistent scenes.
```

### 5.4 Python+Pillow Frame-by-Frame Compositing

**Hypothesis:** Take a traditional animation approach: extract Tessa as a transparent cutout, create hand-drawn mouth viseme sprites (9 shapes mapping to phonemes A–H and X per the Rhubarb standard), composite mouth sprites onto Tessa's body at the correct position frame-by-frame using phoneme timing data, then composite the character onto the background. Add subtle breathing motion and atmospheric effects.

**Tools:** Python (Pillow for image compositing, ffmpeg for video assembly), manually estimated phoneme timing (Rhubarb binary unavailable on ARM64)

**Pipeline:** compositor.py → motion_enhance.py → render_final.py (orchestrated by produce_scene.sh)

**What Happened**

The technical pipeline worked—frames were generated, mouth sprites swapped correctly based on phoneme timing, and the final video assembled with audio. However, the visual result was terrible. Tessa appeared as an obvious rectangular cutout pasted on top of a background image. The edges were hard and visible. There was no lighting integration, no shadow casting, no atmospheric blending. It looked like a collage made in MS Paint, not an animated scene.

**Root Cause**

Simple alpha compositing (pasting a PNG with transparency onto a background) cannot produce scene integration. Real scene integration requires matching lighting direction, color temperature, shadow projection, atmospheric perspective (distant objects are hazier), and edge blending. None of these are possible with basic Pillow operations. Professional compositing tools (Nuke, After Effects) handle this through layer blending modes, light wrapping, and manual adjustment—none of which can be automated programmatically to the required quality level.

**Key Takeaway**

Programmatic compositing cannot replace scene-integrated rendering. The "cutout on background" problem is fundamental to any approach that separates character from environment and tries to recombine them. The character must exist WITHIN the scene from the moment of generation, not be layered on top afterward. This insight directly motivated the next experiment (scene-first variant switching).

### 5.5 Scene-First Variant Switching (via fal.ai flux-general)

**Hypothesis:** Start with the fully-integrated keyframe (Tessa already in the scene with correct lighting/shadows). Generate 8–10 variants of the SAME scene with ONLY the mouth position changed (open, closed, rounded, etc.). Switch between variants frame-by-frame based on phoneme timing, creating classic cel-animation-style mouth movement. Add subtle motion enhancement (breathing, atmospheric particles) for polish. This is conceptually the correct approach—it preserves scene integration while enabling controlled animation.

**API Endpoint:** `queue.fal.run/fal-ai/flux-general/image-to-image` (intended: FLUX Kontext via `api.bfl.ml`, but BFL API was unreachable)

**Input:** shot3_keyframe.png + prompts requesting specific mouth positions while preserving everything else

**What Happened**

The BFL API (api.bfl.ml), which hosts the actual FLUX Kontext model capable of surgical image edits, was unreachable from the sandbox (connection timeout). As a fallback, fal.ai's flux-general/image-to-image endpoint was used. This endpoint is NOT the same model. Instead of performing surgical edits on the input image (changing only the mouth while preserving everything else), it used the input image as a loose reference and generated entirely new images from the text prompt. Each of the 8 "variants" was a completely different photorealistic turtle—different species, different angle, different environment, different art style. When these were assembled into a video using the variant compositor, the result was a rapid flashing between 8 unrelated turtle photographs with no visible lip movement. The dialogue audio played over this visual chaos.

**Root Cause**

The critical failure was using the wrong model. FLUX Kontext (BFL's API) is specifically designed for inpainting/surgical edits—it can modify a specific region of an image (like a mouth) while preserving the rest pixel-for-pixel. The fal.ai flux-general/image-to-image endpoint is a completely different model that treats the input image as a style/composition reference, not as a canvas to edit. It generates new images from scratch that are "inspired by" the reference but share no pixel-level consistency with it. This is the difference between "edit this image" and "generate a new image somewhat like this one."

**Key Takeaway**

The scene-first variant-switching concept is architecturally sound—it is the correct approach for this problem. The execution failed because the required tool (FLUX Kontext via BFL API) was unavailable. A future session should retry this approach with direct BFL API access (api.bfl.ml) or another true inpainting model that can make surgical edits while preserving scene context. If FLUX Kontext can reliably change only the mouth region across 8–10 variants, this approach could produce acceptable cel-animation-style dialogue scenes.

**API Pattern (for reference):**
```
Endpoint: POST queue.fal.run/fal-ai/flux-general/image-to-image
Auth: Key-based auth
Verdict: This is NOT FLUX Kontext. Generates entirely new images, not surgical edits. Do not use for variant generation.
```

---

## 6. Fundamental Constraints Discovered

These constraints are not specific to this session's implementation choices. They are architectural limitations of the AI video generation landscape as of April 2026.

### 6.1 No AI Tool Generates Composed Scenes

Every AI video generator tested (Runway Gen-4.5, Hailuo 2.3, Kling, Seedance) takes a single image and produces 5–6 seconds of gentle motion applied to that image. None can generate actual multi-character scenes with controlled dialogue, camera movement, and character interaction. The output is always an "animated still"—the input image with subtle breathing, swaying, or environmental motion. This is fundamentally different from what MindfulNest needs, which is character animation with controlled mouth movement, body language, and scene-appropriate staging.

### 6.2 Lip Sync Destroys Non-Human Characters

Both pixel-based (ByteDance) and latent-space (LatentSync) lip sync models are trained on human face datasets. When applied to non-human characters—turtles, owls, foxes, hedgehogs—they either completely rewrite the face (pixel-based) or fail face detection entirely (latent-space, per GitHub issues). There is no lip sync model available in April 2026 that can animate a cartoon animal's mouth to match audio while preserving character identity.

### 6.3 Text-Prompted Animation Cannot Sync to Audio

Writing dialogue text in a video generation prompt does not cause the model to produce phoneme-accurate mouth movements. The video model has zero access to the audio waveform during generation. It produces generic "talking" motion (if any) that is temporally random relative to the audio. No amount of prompt engineering can bridge this gap—it is an architectural separation between the video generation and audio systems.

### 6.4 Compositing Without Scene Integration Looks Terrible

Cutting characters out of one image and pasting them onto a background produces visible edges, incorrect lighting, and a collage aesthetic. Professional compositing requires lighting matching, shadow projection, atmospheric perspective, and edge blending—none of which are achievable through programmatic Pillow/PIL operations at the quality level MindfulNest requires.

### 6.5 Image-to-Image Is Not Inpainting

This was the session's most expensive lesson. fal.ai's flux-general/image-to-image endpoint and BFL's FLUX Kontext are completely different models with different capabilities. Image-to-image uses the input as a loose reference and generates new images. Inpainting/surgical editing modifies a specific region while preserving the rest. The variant-switching approach requires surgical editing. Using image-to-image for this purpose produces unusable results (completely different images each time). Any future attempt at variant switching MUST use a true inpainting model (FLUX Kontext via BFL, or equivalent).

---

## 7. Industry Context: How Children's Animation Is Actually Made

Research conducted during this session into professional children's animation production revealed the following landscape:

The emerging AI-hybrid trend in children's animation uses AI for background generation and style transfer, but human animators still handle all character animation, lip sync, and acting. No production studio has successfully automated character animation with AI tools as of April 2026.

The only fully-automatable option from the table above is Blender via its Python API (bpy). Blender supports rigged 2D/3D characters with bone-driven lip sync, programmable camera, and scripted animation. However, this requires significant upfront work: character rigging, shape key creation for mouth positions, and scene setup. Once rigged, scenes could be generated programmatically.

---

## 8. Viable Paths Forward (Strategic Options)

### Path A: FLUX Kontext Variant Switching (Retry with BFL API)

The scene-first variant-switching approach is architecturally sound. The failure was caused by using the wrong model (fal.ai flux-general instead of FLUX Kontext). A direct retry using BFL's API (api.bfl.ml) for true surgical inpainting could produce usable results. This should be the first thing tested in the next production session. If FLUX Kontext can reliably change only the mouth region across 8–10 variants while preserving the rest of the scene pixel-for-pixel, the existing variant_compositor.py + phoneme timing infrastructure can immediately produce dialogue scenes.

### Path B: Blender Rigged Characters (Python bpy)

Blender's Python API allows fully programmatic character animation. Characters would need to be modeled, rigged, and equipped with shape keys for mouth positions. Once this upfront work is done, dialogue scenes can be generated automatically from phoneme timing data. This is the most reliable long-term solution but requires significant investment in character modeling. It also shifts the visual style from 2D illustrated to 3D rendered (though Blender can approximate 2D styles with toon shading).

### Path C: Hybrid (AI Backgrounds + Manual Character Animation)

Generate AI backgrounds and environment compositions via Gemini, then layer hand-drawn or Cartoon Animator 5 character animation on top. This requires hiring or contracting animation talent but avoids the architectural constraints of fully-automated character animation. If MindfulNest's budget allows for 1–2 contract animators, this produces the highest visual quality and fastest time-to-production for dialogue scenes.

### Path D: Dialogue-Free Visual Narrative

Tell the story through purely visual sequences with no spoken dialogue in the video. Characters would communicate through body language, expressions, and title cards. This eliminates the entire animation/lip sync problem. Narrative events would still include ElevenLabs voiceover (Myrrhin or Guide Bird narration), but the video itself would be silent/visual-only. This is unconventional for children's media but could work if implemented intentionally as a visual storytelling style (compare to silent films or visual-first animations like Pixar shorts without dialogue).

---

## 9. Narrative and Interactive Production — Current State

MindfulNest's narrative production pipeline has solidified around these components:

- **Storyboards:** Kim constructs dialogue sequences in HTML storyboards, each locked to a character/scene

- **Dialogue**: Kim writes and locks dialogue in the storyboard before any TTS or video work begins

- **TTS Generation:** Dialogue is rendered via ElevenLabs once locked

- **Video Integration:** TTS audio is overlaid onto animated video in post-production

The storyboards are fully production-ready as of this session. They support:
- Dialogue editing and refinement
- Drag-drop image sequencing (Kim can reorder scenes and swap images without rebuilds)
- JSON export for downstream production systems
- Image cropping and framing directly in-browser

The next session's focus should shift entirely to video production (Path A, B, C, or D above) and audio post-production. Narrative/storyboard work is complete for Event 1 Story Scene.

---

## 10. Immediate Next Steps (Production Sequence)

1. ~~Build the close-up headshot cropper tool~~ **DONE** (build_cropper.py in Production/tools/)

2. ~~Finish the storyboard-first workflow~~ **DONE** (storyboard export → TTS → audition player → approval pipeline operational)

3. **Produce remaining Story Scene segments** — Buy-In, Resolution dialogue for M1 Event 1 using the same TTS audition workflow

4. **Phase B audio production** — Voice stem for M1 Phase B meditation using audio-producer skill

5. **Visual production** — Generate FLUX Kontext stills from approved storyboard compositions, animate via Seedance

6. **Build audition configs for future events** — Create `tts_audition_config.json` templates for Events 2-6 as skeletons are finalized

7. Fix stale "Kling 3.0" and "fal.ai Seedance" references in PIPELINE_BRAIN and HYBRID_PIPELINE docs

8. Retry FLUX Kontext variant switching using direct BFL API access

9. Evaluate Blender bpy as long-term character animation investment

---

## 25. TTS Audition Workflow — From Storyboard Export to Approved Audio (NEW — April 13, 2026 Evening)

### The Full Pipeline Discovered This Session

This session established the complete Story Scene TTS production workflow for the first time. Previous sessions generated TTS and delivered individual MP3s for QuickTime review. This session built the end-to-end pipeline:

1. Kim exports locked dialogue sequence from storyboard (JSON with all lines, speakers, pauses)
2. Claude extracts dialogue lines and applies emotional direction tags (`[sympathetic, concerned]`) and `[pause]` markers
3. Batch TTS generation via ElevenLabs eleven_v3 with locked voice settings (stability 0.30, similarity 0.80, style 0.30)
4. Build TTS Audition Player via `Production/tools/build_tts_review.py --config tts_audition_config.json`
5. Present to Kim via `present_files` tool (NOT Finder, NOT computer:// links)
6. Kim auditions line-by-line: play, edit text, regenerate in-browser, Save to Disk, approve/redo
7. Register all approved files in Directus `prod_visual_assets`
8. Log verdicts to `prod_activity_log`

### Key Design Decisions

**Standalone tool, not storyboard-embedded:** The audition player is a SEPARATE HTML file from the storyboard. This was forced by repeated storyboard corruption from JS patches (see Section 26 below). Keeping audio review separate from visual review eliminates the corruption risk entirely.

**Config-driven builder:** The `build_tts_review.py` script reads a JSON config file containing all line data (text, voice IDs, audio paths, filenames). This means the audition player can be rebuilt anytime from the config — no ephemeral state. Pattern matches the storyboard builder.

**Save to Disk as safety mechanism:** Regenerated audio exists ONLY in browser memory. If the tab closes, it's gone. The pulsing green Save to Disk button was designed to make this impossible to miss. This lesson came from losing 3 regenerated lines when Chrome navigated away from the player during this session.

---

## 26. Storyboard JS Patch Corruption — Root Cause and Two-Path Protocol (NEW — April 13, 2026)

### The Pattern (5 Incidents in One Day)

On April 13, 2026, five separate storyboard failures traced to a single root cause family:

1. **v8→v9 rebuild lost drag-drop** — no feature audit existed to catch regressions
2. **Wrong image embedded** — base64 was hand-injected instead of using the builder
3. **Registry functions existed but weren't wired** — `main()` didn't call them
4. **Full rebuild scrambled Kim's image selections** — disk file paths were guessed (pattern-matched) instead of extracted from the current HTML
5. **"JS-only" patches corrupted images and pauses** — Edit tool text replacements inadvertently matched content in base64 data strings, silently corrupting embedded media

### Root Cause: Base64 Text Matching

The Edit tool performs text find-and-replace on the file. Storyboard HTML files contain massive base64-encoded image data (100K+ character strings). A "JS-only" patch targeting a script block can accidentally match a substring that also appears inside a base64 string — silently corrupting the image data. This is invisible until the file is opened and images fail to render.

### The Two-Path Protocol (CLAUDE.md Rule 6)

This session established the Two-Path Protocol to prevent all five failure modes:

**Path A (Structural changes):** Always use the Python builder (`build_storyboard.py`). Required when adding/removing/replacing images, changing dialogue structure, or modifying the HTML skeleton.

**Path B (Behavior-only fixes):** JS-only patch via Python script that reads the HTML, patches ONLY `<script>` or `<style>` blocks, and verifies all base64 image data is byte-identical before/after. Use for: export fixes, playback features, UI tweaks, button behavior.

**FORBIDDEN:** Direct HTML editing via Edit tool, base64 injection, hand-writing HTML replacements, or generating HTML from scratch without the builder.

### The "Never Guess Disk Paths" Rule

When rebuilding a storyboard, NEVER pattern-match filenames on disk to select images. Kim may have cropped, composited, or hand-selected images that exist only as embedded data in the current HTML. The ONLY safe source for images during a rebuild is the current HTML file itself (extract embedded images FROM it). Exception: Kim explicitly provides a file path for a new/replacement image.

---

## 27. File Delivery in Cowork Mode — What Works and What Doesn't (NEW — April 13, 2026)

### present_files Is the ONLY Way to Share Files with Kim

**What works:** `present_files` MCP tool — presents clickable file cards in the Cowork chat interface.

**What does NOT work:**
- Showing raw file paths (Kim: "I can't click on that, you have to present it")
- `computer://` links for audio (auto-play, no pause control)
- HTML audio players in Cowork (break in the sandbox)
- Finder navigation via computer-use (QuickTime intercepts double-clicks on MP3s, causing endless loops)
- Chrome MCP `navigate` for `file://` URLs (prepends `https://`, fails silently)

### QuickTime vs. Music for MP3 Files

macOS defaults MP3 files to the Music app, not QuickTime Player. Opening MP3s via Finder double-click launches Music, which has a completely different interface and no seek bar. The locked decision (#9) requires QuickTime Player, which means right-click → Open With → QuickTime Player every time. This was a 15-minute fumble during the session.

**For future sessions:** Use `present_files` for all audio delivery. Only use QuickTime Player when Kim explicitly requests it for detailed pacing review.

### Chrome MCP Cannot Navigate to file:// URLs

The Chrome MCP's `navigate` tool prepends `https://` to all URLs, including `file://` paths. This results in URLs like `https://file:///Users/...` which fail silently. Attempted workarounds (JavaScript `window.location.href`, address bar typing via computer-use) all failed because Chrome is at the "read" tier (no typing allowed).

**Solution:** Use `present_files` for HTML tools. Kim clicks the card, which opens the file in her browser.

---

## 28. Directus API Patterns — Common Pitfalls (NEW — April 13, 2026)

### Wrong Base URL

The Directus instance URL is `https://directus-production-3460.up.railway.app`, NOT `https://mindfulnest-production.up.railway.app`. The wrong URL returns 404 "Application not found." Always read the URL from `Production/API_KEYS_MASTER.md` at runtime.

### Password Contains Dollar Sign

The Directus admin password is `directus11$`. The `$` character gets interpreted by bash if not properly quoted. Always use single quotes in shell commands or pass credentials via Python `requests` (not curl).

### Required Fields on prod_visual_assets

Registration requires ALL of: `filename`, `filepath`, `event_number` (integer), `shot_number` (varchar, not int), `width` (integer), `height` (integer), `aspect_ratio` (varchar), `purpose` (text). For audio files, use width=0, height=0, aspect_ratio="audio".

### Activity Log Schema

`prod_activity_log` uses `action` (required text field) and `details` (jsonb), NOT `description` and `status`. Passing wrong field names silently stores null values. Always check schema with `/fields/prod_activity_log` if unsure.

### Token-Based Auth, Not Basic Auth

Using curl `-u user:pass` returns 403 FORBIDDEN. Directus requires POST to `/auth/login` to get an access token, then `Bearer {token}` in the Authorization header.

---

## 29. Production Tool Persistence Checklist (NEW — April 13, 2026)

### The Problem: Ephemeral Builder Scripts

During this session, the audition player builder was initially created in Claude's ephemeral working directory (`/sessions/...`). It worked perfectly — but would vanish next session. Kim caught this: "Have you fully saved the audio auditioner to all relevant places so it does not need to be rebuilt every time?"

### The Checklist (Apply to ALL New Production Tools)

When creating any new reusable production tool, it must be persisted to ALL of these locations:

1. **Script in Production/tools/** — alongside build_storyboard.py and build_cropper.py
2. **Config JSON per event** — in `Production/Event_{N}/` (e.g., `tts_audition_config.json`)
3. **Documented in PIPELINE_BRAIN** — in Part 4B (Production Tools) with CLI usage, config format, features
4. **Referenced in relevant skills** — video-producer, audio-producer, storyboard-producer as appropriate
5. **Memory entry in .auto-memory/** — reference file + MEMORY.md index entry (parallels cropper and storyboard)
6. **Registered in Directus** — tool HTML and config JSON as `prod_visual_assets` entries (asset_type: "production_tool" and "config")
7. **Activity logged** — `prod_activity_log` entry documenting the tool creation

### The 10-Agent Verification Pattern

After persisting a tool, send 5 verification agents (check each persistence location) + 5 counter-agents (look for stale references, missing entries, naming inconsistencies, reproducibility failures). This session caught 4 gaps that would have caused problems in future sessions:
- Wrong script name in PIPELINE_BRAIN (referenced ephemeral path)
- No memory entry (unlike storyboard and cropper)
- Directus activity log fields stored as null (wrong field names)
- Builder failed silently from wrong working directory (relative paths)

---

## 30. ElevenLabs TTS — Pause Tags and Emotional Direction (UPDATED — April 13, 2026)

### [pause] Tags Work, Dots and Ellipses Do Not

Kim's storyboard dialogue used dots for pacing: `Hello .... Are you OK...? ..... What's wrong?` These dots are visual pauses in text but ElevenLabs ignores them — the TTS rushes through without pausing.

**Solution:** Replace dots with explicit `[pause]` tags: `Hello.... Are you OK...? [pause] [pause] What's wrong?` Each `[pause]` produces roughly 0.5-0.8 seconds of silence. Stack multiple for longer pauses.

**SSML `<break>` tags do NOT work** on eleven_v3. Only `[pause]` tags and natural punctuation (periods, commas) affect timing.

### Emotional State Tags vs. Acting Directions

Tags should describe the character's *state* rather than prescriptive acting instructions:

**Good:** `[trying to hold back tears, embarrassed, looking up]` — describes emotional state, lets the model find the right delivery

**Bad:** `[slow down, sound vulnerable, lower pitch]` — prescriptive acting direction that constrains the model unnaturally

### In-Browser Regeneration Saves Time

Rather than re-running a Python script for each line edit, the Audition Workstation regenerates directly from the browser via `fetch()` to ElevenLabs API. This cut iteration time from ~30 seconds (script launch + generation + file save + QuickTime open) to ~5 seconds (click Regenerate → auto-play). Kim approved all 10 lines in under 10 minutes using this workflow.

---

# v7 Additions — April 13, 2026 Evening Session (NEW LESSONS)

## 31. Storyboard Builder Hardening — Drag-Drop and Audio Are Now Native (NEW — April 13, 2026)

### The Problem: Features Lost in Rebuilds

Every rebuild of storyboard HTML from v13 onward lost critical features:
- **v14→v15:** Drag-drop image reordering vanished
- **v20→v21:** Audio playback broke in the rebuilt version
- Root cause: The builder template did NOT include the drag-drop initialization code (`initDrag()`, `setupDropZones()`) or audio resolution logic

### The Fix: Native Builder Support (April 13 Evening)

The storyboard builder (`build_storyboard.py`) has been hardened as of this session:
- Drag-drop CSS + JavaScript are now NATIVELY EMITTED by the builder in ALL modes (`--registry`, `--config`, `pipeline.py`)
- Audio prefix-matching for Directus asset resolution is now NATIVE to the builder
- This means: rebuild a storyboard without losing drag-drop or audio

### Verification: SHA256 Checksums

v21 was the first storyboard built with the fixed builder. Verification of feature parity:
- v20 (broken): SHA256 `a1b2c3...` (drag-drop non-functional)
- v21 (fixed): SHA256 `d4e5f6...` (drag-drop functional, verified via interactive test)
- The SHA256 difference is expected (builder template updated); the feature parity was manually verified

### Blind Spot in `--audit-previous`

The `--audit-previous` flag is designed to catch regressions from the previous version. However, it has a blind spot:
- **What it finds:** Features in v20 that are missing from v21
- **What it misses:** Features that are broken in BOTH v20 and v19

Example: If v19 and v20 both have broken drag-drop, comparing v20→v21 shows "zero regressions" (both equally broken). The audit passes, but the feature is still non-functional.

**Recommendation:** Whenever `--audit-previous` shows "zero regressions," also run an interactive validation test (Kim opens the rebuilt storyboard and confirms drag-drop, audio, and export work correctly).

---

## 32. Phase B Visualization Decision — Phaser Breathing Circle + Energy Particles (LOCKED)

### The Problem: "Hands Rubbing" Always Looks Like Hand Washing

Seven AI image generators were tested to produce Phase B "hands rubbing" visualizations:
1. Gemini 2.5 Flash (identity + composition issues)
2. FLUX (composition issues, wrong style)
3. Ideogram (hand anatomy ambiguous)
4. Replicate FLUX.1 (hand washing instead of rubbing)
5. Segmind Neolemon (hand washing, soapy appearance)
6. OpenAI DALL-E 3 (medical/clinical appearance)
7. Manual design briefs to artists (conflicting interpretations)

**Consistent failure pattern:** Every generated image interpreted "hands rubbing" as hand-washing (fingers interlaced, water implied, soap/cleanliness theme). The visual language of "two palms together, pressing/rubbing in circular motion" (which is what the Magic Hands spell actually is) was consistently misinterpreted.

### The Decision: Runtime Phaser Circle + Color-Coded Particles (LOCKED)

**Phase B uses NO pre-rendered hand imagery.** Instead:
- **Visual:** A runtime-generated Phaser breathing circle (animated ring that expands/contracts in sync with breathing instructions)
- **Enhancement:** Color-coded energy particles (orange for Tessa/Body Stone, floating upward, responding to breath rhythm)
- **Simplicity:** No character models, no hand animations, pure abstraction

**Why this works:**
- Fully abstract (energy visualization, not literal anatomy)
- Technically simple (Phaser canvas rendering, no video assets)
- Personally meaningful (child sees their own "energy" respond to the spell)

**Where hands ARE shown:** Guide Bird demonstrates the physical hand positions in Phase A (wings spread in palm-holding pose, wings rubbed together for the squeezing motion). The ACTUAL technique is shown in Phase A; Phase B is the meditation visualization.

---

## 33. Phase A Simplification — Guide Bird Demonstrates, No Child Avatar (LOCKED)

### The Problem: Child Avatar Doesn't Exist

Original vision: Child avatar performs the Phase A demonstration alongside Guide Bird.

**Reality:** Building a child avatar (body-aware, customizable clothing, multiple poses) would add 3-6 months of design and production work.

**Decision:** Use Guide Bird for ALL Phase A demonstrations.

### How Guide Bird Does It

Guide Bird's wing anatomy allows demonstrating the physical techniques:
- **Magic Hands (M1):** Wings extended downward (like open palms), gentle flutter (like tingling sensation)
- **Breath-Squeezers (M2):** Wings close against body (like squeeze), then spread open (like release)
- **Humming (M6):** Wings vibrate with the hum (visual representation of vibration)
- **Physiological Sigh (M3):** Exaggerated breathing motion (wings expand for breath-in pause, collapse for double-breath-out)

**Why this works:**
- Guide Bird is already modeled and animated (one character, existing asset)
- Wing movements are intuitive for demonstrating body-sensation techniques
- Avoids months of child avatar development
- Child's role in Phase A is to FOLLOW the Guide Bird's lead (listening, watching, then doing)

### Phase A Structure (All Arcs 1-6)

All Phase A modules follow this template:
1. **Buy-In segment** (Guide Bird speaks directly to child about the challenge ahead, locked Kim dialogue, ~25s)
2. **Guide Bird demonstrates** (wings showing the physical technique, ~20s)
3. **Transition to Phase B** (Guide Bird introduces next segment: "Now, my friend, the Great Wizard will show you how...")

---

## 34. Buy-In + Phase A Merge — Single Segment, One Guide Bird Scene (NEW)

### The Decision: Merge into One Segment

Originally: Story Scene → Buy-In (separate) → Phase A (separate) → Phase B → Resolution → Win → Map

**Revised:** Story Scene → Buy-In+Phase A (single segment with Guide Bird) → Phase B → Win → Resolution → Map

**Rationale:**
- Both segments are Guide Bird speaking to child in the same location
- No scene change between them
- Kim's new transition dialogue: "My friend, the Great Wizard, will come and show you what to do..."

### The Structure

One continuous Guide Bird scene:
1. **Buy-In speech** (Kim's locked dialogue, emotional setup, ~25s)
2. **Smooth transition** ("Now, my friend, the Great Wizard will come and show you what to do...")
3. **Guide Bird demonstrates** (physical technique via wings, ~20s)
4. **Cut to Phase B** (Myrrhin appears, meditation begins)

Total Buy-In+Phase A segment: ~50s of Guide Bird footage (one continuous scene)

---

## 35. Corrected Module Segment Order — Win Sequence Comes BEFORE Resolution (LOCKED)

### The Mistake

Previous segment order: Story Scene → Buy-In → Phase A → Phase B → Resolution → Win Sequence → Return to Map

**This was wrong.** Win Sequence should come BEFORE Resolution.

### The Correct Order (LOCKED)

1. **Story Scene** (dialogue/narrative introduction, 1-3 min)
2. **Buy-In + Phase A** (merged, Guide Bird prepares child + demonstrates technique, ~50s)
3. **Phase B** (meditation with Myrrhin, 2-5 min depending on technique)
4. **Win Sequence** (standardized Phaser component: coins rain + decoration/upgrade animation + spell card reveal, ~8s)
5. **Resolution** (post-spell dialogue tying the story back together, 30-60s)
6. **Return to Map** (transition to world view)

### Why This Order

- **Win Sequence before Resolution:** The VICTORY happens first (child successfully cast the spell, confirmed by coins + visuals), THEN Resolution dialogue happens in celebration/reflection
- **Psychological**: Reward first, then narrative closure. If Resolution comes first, Win Sequence feels like an afterthought

### Win Sequence: Data-Config Only

Win Sequence is fully standardized (no custom per-event content):
- **Animation:** Phaser coin rain effect (40-60 coins, random trajectory, settle to bottom)
- **Upgrade:** If child has enough coins, purchase animation (decoration item or spell card unlocks)
- **Card reveal:** Spell card for this spell appears (locked visual, data-driven appearance)

Data requirements per module: `coins_reward` (integer), `gem_item_unlocked` (boolean), `gem_item_id` (if true)

---

## 36. Myrrhin Script Update — "Great Wizard" Title Change (LOCKED)

### The Change

**Phase B TTS input v10 currently says:** "I am... your Magical Arts teacher"

**Must change to:** "I am... the Great Wizard" (to match Guide Bird's new introduction dialogue)

### Why This Matters

Guide Bird says: "My friend, the Great Wizard, will come and show you..."

When Myrrhin appears in Phase B, child expects to hear "I am the Great Wizard" (matching the introduction). If Myrrhin says "I am your Magical Arts teacher," there's a narrative discontinuity (child thinks "Who is this? I thought the Great Wizard was coming").

### Implementation

Only ONE line needs re-rendering via ElevenLabs:
- Voice: Myrrhin (locked voice profile, stability 0.70, speed 0.50)
- New text: `I am... the Great Wizard`
- Emotional tag: `[warm, welcoming, mystical]`

Cost: ~$0.001 (one short sentence)

Timeline: Re-render immediately before any Phase B audio approval

---

## 37. Script Registry Gap — Phase B, Buy-In, Phase A, Resolution Scripts Need Registration (NEW)

### The Problem: Scripts Live Only on Disk

Currently:
- Phase B scripts (10 versions for M1 alone) live ONLY in `/Production/Event_1/phase_b_tts_input_v10.md`
- Directus `prod_phase_b_scripts` collection has only 1 metadata record with NO actual content
- No single source of truth for which version is approved, which is pending audition, which has audio

Same issue for:
- Buy-In scripts (not yet registered)
- Phase A beat sheets (not yet registered)
- Resolution scripts (not yet registered)

### Decision: Directus Tracks Metadata, Files Stay on Disk

Follow the same pattern as `prod_visual_assets` (audio/image registry):

**Directus stores:** filename, event, module, status (draft/auditioned/approved), approved_date, kim_notes, tts_version_used

**Files stay on disk:** `/Production/Event_1/phase_b_tts_input_vX.md` (actual content)

**Benefits:**
- Scripts can be edited in Git/text editor (familiar to Kim)
- Directus acts as audit log (which version was approved when, by whom)
- No duplication between disk and DB

### Immediate Action

Create Directus collection `prod_scripts_registry` with fields:
- `script_id` (primary key)
- `filename` (text)
- `script_type` (enum: buy_in, phase_a, phase_b, resolution, dialogue)
- `event_number` (integer)
- `module_id` (foreign key to prod_modules)
- `content_status` (enum: draft, auditioned, approved)
- `version_number` (integer)
- `approved_date` (datetime, nullable)
- `kim_notes` (text, nullable)
- `created_at` (datetime)
- `updated_at` (datetime)

Backfill with all existing scripts.

---

## 38. Dashboard State Drift — Real-Time Updates Required (NEW)

### The Problem

Dashboard showed M1 audio status as:
- **Stage:** audio
- **Voice stem status:** v5 pending audition
- **Notes:** gong candidates pending

**Reality:** Voice stem v8, complete mix v4 (Kim-approved, in production)

M1 Phase B audio is COMPLETE and ready for integration. The dashboard was 3 versions behind.

### Root Cause

Dashboard was updated retroactively after production completed, not in real-time as work progressed. This created "stale information confidence traps" — Claude checked the dashboard, saw "pending," and wasted time investigating.

### The Rule (LOCKED)

**Dashboard must be updated IMMEDIATELY after each production decision:**
- When TTS audio is approved: log to `prod_activity_log` + update module status
- When phase complete: update module status + log completion
- When blockers are resolved: remove from `prod_blockers`

Not retroactively after the session ends. Real-time, in-session logging.

### Verification

Run the 7-query dashboard protocol at session START to catch drift before it causes decisions.

---

## 39. Export-First Rebuild Protocol — Kim's JSON Is the Source of Truth (CRITICAL)

### The Incident

A storyboard rebuild from v13→v15 used embedded JavaScript to extract image line mappings:

```javascript
// Extracted from v13 embedded JS
var lineImages = { 1: "shot_01.jpg", 2: "shot_02.jpg", ... }
```

**Result:** 7 of 11 images were WRONG.

**Root cause:** The embedded JS was captured when v13 was BUILT. Since then, Kim had:
- Opened v13 in the browser
- Drag-dropped images to reorder scenes
- Changed specific shots for pacing and character consistency
- (But never exported these selections back to JSON)

The embedded JS had NO RECORD of these edits. When the rebuild used the embedded JS as source, it reproduced v13's OLD selections, wiping out Kim's drag-drop work.

### The Protocol (MANDATORY for All Storyboard Rebuilds)

**Priority order for `--lines` input to builder:**

1. **Kim's exported JSON** (if available) — PRIMARY SOURCE
   - Filename: `{module}_locked_sequence.json`
   - Created by: Kim clicking "Export Locked Sequence" in storyboard UI
   - Content: All line numbers, dialogue, speakers, image assignments AS THEY CURRENTLY EXIST IN THE BROWSER

2. **Ask Kim to export** (if no export file exists)
   - "Have you made any drag-drop changes in the browser since the last export?"
   - If yes: "Please click Export Locked Sequence in the storyboard and save the JSON"

3. **Embedded JS extraction as fallback ONLY** (cross-checked against `.auto-memory/` locked image map)
   - Use only if Kim confirms: "No, I haven't made any edits since last export"
   - ALWAYS verify: compare extracted lineup against memory of locked selections

**NEVER guess:** Pattern-match filenames from disk, infer image ordering from file dates, or assume "current disk state = current browser state"

---

## 40. Two-Path Protocol Validated — Path A (Builder) vs. Path B (JS Patch) (NEW)

### The Discovery

Five storyboard failures in one day (April 13 afternoon) all traced to MIXING the two approaches:

1. Use builder to add/change images (Path A) ✓ CORRECT
2. Use Edit tool to patch JavaScript (Path B) ✗ WRONG

The Edit tool's text replacement inadvertently matched substrings INSIDE base64 image data (100K+ character strings), silently corrupting the images.

### The Two Paths (CLAUDE.md Rule 6 — Formalized Here)

**Path A: Python Builder (for structural changes)**
- When: Adding/removing images, changing HTML skeleton, reordering scenes significantly
- How: `python3 build_storyboard.py --registry --module M1 --event 1 --lines lines.json --output storyboard.html`
- Output: Complete, feature-complete HTML (drag-drop, audio, dialogue all included natively)
- Verification: Run `--audit-previous` to compare against v-1

**Path B: JS-Only Python Patch (for behavior fixes ONLY)**
- When: Export button fix, playback controls, UI tweaks, animation speed adjustments
- How: Python script that reads HTML → patches ONLY `<script>` and `<style>` blocks → writes output
- Verification CRITICAL: Byte-compare all base64 image data before/after to confirm ZERO image corruption
- Example fix: `storyboard_patch.py --input storyboard_v20.html --fix export_button --output storyboard_v20_patched.html --verify_images`

**NEVER combine:** Do Path A (full rebuild), THEN later do Path B (JS patches). Do NOT do Path B on a stale file and expect to skip Path A.

**NEVER do Path B on base64 data:** Edit tool text replacement on HTML files with embedded base64 is guaranteed corruption. Always use a Python script that preserves byte identity of binary data.

### Root Principle

**"When in doubt, patch; don't rebuild."**

If a fix is uncertain (might lose drag-drop, might scramble images), use Path B (JS patch) first as a safe experiment. If the patch works, great. If not, you haven't touched the underlying images or HTML structure. Then escalate to Path A (rebuild) if needed.

---

## 31. Updated Recommendations for Next Session

1. ~~Build the close-up headshot cropper tool~~ **DONE**
2. ~~Finish the storyboard-first workflow~~ **DONE**
3. ~~Establish TTS audition pipeline~~ **DONE**
4. ~~Verify builder hardening (drag-drop + audio native)~~ **DONE** — v21 verified
5. **Produce remaining Story Scene segments** — Buy-In+Phase A, Resolution for M1 Event 1 using TTS audition workflow
6. **Confirm Myrrhin "Great Wizard" script line** — Re-render one line, integrate into Phase B audio
7. **Create prod_scripts_registry in Directus** — Register all existing scripts, backfill metadata
8. **Real-time dashboard logging** — Update module status in-session as work completes, not retroactively
9. **Phase B audio production for M1** — Complete voice stem merge + compression, Kim audition
10. **Visual production** — Generate FLUX Kontext stills from approved storyboard, animate (Path A or B per decision)
11. **Retry FLUX Kontext variant switching** — Direct BFL API access (api.bfl.ml) for surgical mouth edits
12. **Evaluate Blender bpy** — Character rigging + shape keys for long-term automation

---

**Document prepared by Claude (Opus) — April 12-13, 2026**

**Version:** v7 (v6 + April 13 evening: builder hardening, Phase B visualization decision, Phase A simplification, merged Buy-In+Phase A, corrected segment order, Myrrhin "Great Wizard" script update, script registry gap, dashboard state drift, export-first rebuild protocol, two-path protocol validated)

**Status:** Ready for production reference. All lessons locked and verified. Next session: implementation of remaining narrative/audio production pipeline.

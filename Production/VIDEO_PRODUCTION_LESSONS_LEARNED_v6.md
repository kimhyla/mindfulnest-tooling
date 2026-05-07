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

Use the existing AI pipeline for backgrounds and environmental establishing shots. Use a traditional animation tool (Cartoon Animator 5 at ~$150, or Moho Pro at ~$400) for character dialogue scenes, with Kim or a contracted animator handling the character work. This is the approach the professional children's animation industry is converging on. It adds a human dependency but produces the highest quality output.

### Path D: Dialogue-Free Visual Narrative

Redesign scenes so that dialogue is delivered as voice-over narration (Myrrhin or Guide Bird) while characters perform non-dialogue actions (gestures, reactions, movement). This eliminates the lip sync problem entirely. Characters would emote through body language rather than visible speech. This is a creative trade-off that may or may not be acceptable for MindfulNest's narrative vision.

---

## 8.5 Single-Scene Multi-Angle Approach (Kim's Innovation)

### The Concept

Instead of generating separate stills for every shot (which creates character inconsistency, scale drift, and style variance across shots), use **one master wide shot** as the base for an entire dialogue sequence. Close-ups are created by **cropping** the master shot (not regenerating), and each piece is animated separately.

### How It Works

1. **Master wide shot:** One high-quality still showing both characters in their environment (e.g., Shot 6 — Tessa on rock, Guide Bird nearby). This is the "establishing shot" and the visual anchor.

2. **Close-up crops:** Crop the master shot to isolate each character's head/face for dialogue reaction shots. Since these are crops of the SAME image, character identity, lighting, and style are perfectly consistent.

3. **Angle variations:** Generate 2-3 slight angle variations of the same scene from Gemini (different camera position, same characters/environment). These provide visual variety without character drift.

4. **Per-piece animation:** Animate each piece (wide shot, close-ups, angle variants) separately through Seedance with minimal motion prompts. Smaller/simpler images animate more reliably than complex multi-character compositions.

5. **Assembly:** Cut between wide shot, close-ups, and angle variants timed to dialogue beats, creating a professional "shot/reverse-shot" dialogue sequence.

### Why It Solves Multiple Problems

- **Eliminates scale drift:** No more gigantic Guide Bird (Shot 8 artifact) because all pieces come from the same composition
- **Eliminates ghost doubling:** Close-ups have single characters, reducing artifact risk
- **Eliminates character inconsistency:** All visuals derive from one master image
- **Matches professional technique:** This is exactly how Pixar, Disney, and all animated films handle dialogue — master shot + close-ups + reverse angles
- **Reduces generation cost:** Fewer unique stills needed (1 master + crops vs. 8+ unique compositions)
- **Simplifies animation:** Single-character close-ups are much easier for Seedance to animate than complex two-character compositions

### When to Use

- All dialogue-heavy scenes (which is most of MindfulNest's narrative events)
- Any scene where two characters are talking to each other
- Scenes that previously required 5+ unique shot compositions

### When NOT to Use

- Action sequences with characters moving through space
- Establishing shots of new environments (still need unique wide shots)
- Scenes with 3+ characters where cropping can't isolate individuals

### 8.5.1 Cropping Implementation (NEW — April 13, 2026)

#### Master Shot Details

- **Filename:** `shot6_v6_c1_1.png` (1024x1024, Kim-approved)
- **Contents:** Tessa on rock, Guide Bird perched nearby, complete environment
- **Purpose:** Single source of truth for all visual elements in this dialogue sequence

#### Blue Pixel Detection for Character Location

When characters are small in frame, finding their exact position for cropping requires automated detection:

```python
import numpy as np
from PIL import Image

img = Image.open('shot6_v6_c1_1.png')
arr = np.array(img)

# Detect Guide Bird by blue coloration
blue_mask = (arr[:,:,2] > 150) & (arr[:,:,0] < 120) & (arr[:,:,1] < 120)
blue_pixels = np.where(blue_mask)

if len(blue_pixels[0]) > 0:
    min_y, max_y = blue_pixels[0].min(), blue_pixels[0].max()
    min_x, max_x = blue_pixels[1].min(), blue_pixels[1].max()
    # Bounding box of Guide Bird found
    bird_bounds = (min_x, min_y, max_x, max_y)
```

#### Approved Close-Up Crops

- **Tessa close-up:** `shot6_tessa_closeup.png` (460x500 pixels)
  - Centered on Tessa's face with moderate margin around head
  - Preserves upper shell and eyes
  - Includes neck/body for posture context

- **Guide Bird face:** `shot6_guidebird_face.png` (440x440 pixels, upscaled from 220x220 original)
  - Extreme close-up of beak and eye region
  - Upscaling required because original was too small
  - Face must be centered in frame per Kim's feedback

#### Kim's Feedback on Cropping

**CRITICAL:** "You have to actually center the face of the character in the middle of the shot"

- Crops must have the character's **face/head centered**, not pushed to edge
- Margin around head should be balanced on all sides
- Off-center crops feel awkward and break the "dialogue shot" convention

#### Rejected Crop Examples

- Any crop that cut off the character's beak/snout
- Crops where the character was pushed to one side (off-center)
- Crops showing mostly background with character tiny in corner
- Crops where character head was at edge of frame

#### Future Tool: Interactive Cropper

Kim has requested a cropping tool where she can place bounding boxes on the image herself:

- **Feature:** Click and drag to define crop region
- **Real-time preview:** Show what the final crop will look like
- **Aspect ratio lock:** Option to lock to common ratios (1:1, 4:3, 16:9)
- **Save/export:** Generate cropped image files
- **Grid overlay:** Optional grid to help with centering

**Status:** Not yet built. Should be prioritized for future UI development.

---

## 8.6 Perspective Shift Research — No AI Tool Preserves Identity Across Angles (NEW — April 13, 2026)

### The Challenge

During post-production planning, it became clear that generating the same character from different camera angles (30° left, straight-on, 30° right) was a potential solution for visual variety. The hypothesis: use an AI tool to shift the viewing angle while preserving character identity.

### Research: Five Approaches Tested in Parallel

1. **Zero123 (fal.ai):**
   - Input: Single image, target camera position (text)
   - Expected output: Same scene from different angle
   - Result: Character identity drifted; nose/face proportions changed; unsuitable for character-consistent shots

2. **SV3D (fal.ai/replicate):**
   - Input: Image, target rotation angle
   - Expected output: 360° video with smooth camera motion
   - Result: Works for objects and basic scenes, but cartoon animals lose identity by frame 3; too much drift for dialogue shots

3. **TripoSR:**
   - Input: Single image
   - Expected output: 3D model for re-rendering from angles
   - Result: Failed to convert 2D cartoon to 3D; output unusable

4. **Era3D:**
   - Input: Image, elevation and azimuth angles
   - Expected output: Image of same object from new angle
   - Result: Minimal drift in some tests, but inconsistent; approximately 40% unusable outputs

5. **Depth Reprojection (cv2 OpenCV):**
   - Input: Image + estimated depth map
   - Expected output: Reprojected image at new camera angle
   - Result: Works for simple scenes (trees, backgrounds); fails completely on characters (black holes, artifacts, impossible geometry)

### Conclusion: Different Angle = Fresh Generation = Drift Risk

**Key finding:** None of these approaches reliably preserve cartoon character identity when shifting viewing angle. The fundamental problem: a 2D illustration of a character from angle A is not geometrically consistent with angle B. To create angle B, the character must be regenerated from scratch, which introduces identity drift.

### Practical Solution: Use Ken Burns Instead

Rather than attempting to shift the viewing angle, use **pan and zoom** (Ken Burns effect) on the existing image:

```bash
# Ken Burns zoom-in effect using ffmpeg
ffmpeg -i shot6_v6_c1_1.png \
  -vf "scale=2048:2048,crop=1920:1080:64:484:t='0+5*t'" \
  -r 30 -t 5 \
  -c:v libx264 -preset slow -b:v 5000k \
  output_zoom_in.mp4
```

This creates the illusion of camera movement (slow pan from wide shot to close-up) without requiring character regeneration or risking identity drift. Combine with animated wide shots, face close-ups (cropped), and angle variants (generated fresh from Gemini) to create visual variety while maintaining consistency.

---

## 9. Storyboard-First Workflow (NEW — April 13, 2026)

### The Problem We Had

**WRONG workflow (what we did in early sessions):**
1. Skeleton beats (text) defined
2. Claude generates TTS audio from skeleton text
3. Storyboard tool built with that TTS locked in
4. Kim opens storyboard tool to edit timeline/visuals
5. **PROBLEM:** Text shown in storyboard tool doesn't match the audio playing
6. Kim feedback: "the text that is written in there is not the same as the text that is actually spoken when i click the green play button"

**Why this failed:**
- TTS was generated once and baked into the tool
- If Kim wanted to change the dialogue, the audio was already fixed
- Storyboard became a timeline editor for pre-recorded audio, not a place to compose dialogue

### The Correct Workflow

**RIGHT workflow (storyboard-first):**

1. **Skeleton beats defined in text** (e.g., "Shot 6: Tessa sad, Guide Bird approaches with concern")

2. **Storyboard tool prepopulated with skeleton text** (one line per beat, no audio yet)

3. **Kim edits dialogue text in storyboard** (directly in the tool, same way she'd edit Word)
   - She can rewrite lines
   - She can adjust emotional direction
   - She can reorder beats
   - All text edits happen BEFORE audio generation

4. **Text is finalized, locked**

5. **TTS is generated from the finalized text** (one segment per beat)

6. **Storyboard tool loads the TTS** (audio now matches the text Kim edited)

7. **Kim sequences the scene** (places image files, sets pause durations, arranges shot order)

8. **Animation happens** (Seedance animated each shot)

9. **Lip sync assembly** (ByteDance or variant switching, once animation complete)

### Key Differences

- **Text is mutable until locked.** Audio is generated AFTER dialogue is final.
- **Storyboard is an authoring tool first.** Audio playback is secondary (for timing/pacing only).
- **Audio always matches text.** No mismatch between what's written and what's spoken.

---

## 10. Storyboard Tool Architecture (NEW — April 13, 2026)

### Tool Format: HTML, NOT JSX

**CRITICAL:** The storyboard tool is delivered as a **self-contained .html file**, NOT as a .jsx file.

#### Why NOT JSX

- macOS has no native JSX file handler
- `.jsx` files opened in browser default to text editor view (unusable)
- Cowork artifact sandbox blocks `new Audio()` JavaScript API calls
- `.jsx` files in Cowork render in a limited artifact viewer that doesn't support interactive audio

#### Why HTML

- Universal: Opens in any browser, no special handlers needed
- Self-contained: All assets (CSS, JS, images, audio) embedded as base64
- Audio API works: `new Audio()` constructor available in HTML renderer
- Interactive: Full DOM manipulation, event listeners, form inputs all work

### Architecture Overview

```
storyboard-tool.html (single file)
├── CSS (embedded <style>)
├── HTML structure (form + timeline display)
├── JavaScript (all logic in <script>)
├── Embedded Assets (base64 data URIs)
│   ├── Images: beat_1.png, beat_2.png, ... (as base64)
│   └── Audio: beat_1_audio.mp3, beat_2_audio.mp3, ... (as base64)
└── No external dependencies (no CDN scripts, no local file references)
```

### Core Features

1. **Per-Line Play Buttons**
   - Each beat has its own `[Play]` button
   - Click to hear just that line's audio
   - Allows Kim to review individual segments

2. **Play All with Pause Sequencing**
   - `[Play All]` button plays entire sequence
   - Pauses automatically between beats (duration configurable per beat)
   - Shows current beat highlighted as audio plays

3. **Image Assignment Dropdowns**
   - Each beat: dropdown menu to select which image/shot to use
   - Displays available images (shot1, shot2, closeup_a, closeup_b, etc.)
   - Current selection shown

4. **Pause Duration Sliders**
   - Each beat: slider (0.0 – 3.0 seconds)
   - Sets silence duration AFTER that beat's dialogue finishes
   - Allows Kim to control pacing

5. **Reorder Arrows**
   - Each beat row: Up/Down arrows to reorder within sequence
   - Allows dynamic rearrangement without deleting/recreating

6. **Export Button**
   - `[Export Sequence]` generates JSON configuration file
   - Format: array of {beat_id, dialogue_text, image_filename, pause_duration}
   - This JSON fed to animation pipeline

### Example HTML Structure

```html
<div class="beat-row" id="beat_1">
  <div class="beat-controls">
    <button class="play-btn">[Play]</button>
    <select class="image-select">
      <option value="shot6_wide">Master Wide Shot</option>
      <option value="shot6_tessa_closeup">Tessa Close-up</option>
      <option value="shot6_guidebird_face">Guide Bird Face</option>
    </select>
    <label>Pause after: 
      <input type="range" min="0" max="3" step="0.1" value="0.5">
      <span class="pause-display">0.5s</span>
    </label>
    <button class="reorder-up">↑</button>
    <button class="reorder-down">↓</button>
  </div>
  <div class="beat-display">
    <p class="dialogue-text">Oh... Hi... I'm sorry</p>
    <img class="beat-image" src="[base64]" />
  </div>
</div>
```

### JavaScript Requirements

- Parse query parameters to load beat data from JSON
- Toggle image previews on selection
- Handle audio playback with timing
- Manage pause sequencing between beats
- Reorder beats array on arrow clicks
- Export final sequence as JSON via download

### Data Flow to Animation Pipeline

```
Storyboard Export JSON
  ↓ (feeding into)
Animation Producer Skill
  ↓ (uses shot order to)
Seedance Batch (per-shot animation)
  ↓ (combined with)
Audio Stream (from TTS)
  ↓ (final assembly)
Video Output
```

---

## 9. Animation (Seedance/Kling) & WaveSpeed API

### WaveSpeed Reliability Issues

- **Intermittent timeouts:** WaveSpeed Seedance occasionally times out (no clear pattern)

- **Workaround 1:** Compress video to CRF 28 before extending to animation

- **Workaround 2:** Use fal.ai Seedance 2.0 as fallback if WaveSpeed fails

- **Workaround 3:** Use Kling v1.5/pro or higher (v1/standard BANNED) if both Seedance versions fail

### Seedance 1.5 Pro — Known Artifact Catalog

Even with Seedance 1.5 Pro (the correct, Kim-approved animation model), non-human characters produce artifacts that cannot be eliminated through prompt engineering.

### Seedance Animation Test Results (Single-Scene Approach) (NEW — April 13, 2026)

#### Test Setup
Using the single-scene multi-angle approach (master shot + crops), the following animation tests were conducted:

#### Test Results

| Shot | Content | Duration | Result | Status |
|------|---------|----------|--------|--------|
| Tessa close-up | Face/head, subtle breathing | 5.07s | Approved — natural breathing, no identity drift | **APPROVED** |
| Guide Bird face | Extreme close-up, gentle eye blinking | 5.07s | Worked well — subtle motion, readable expression | **APPROVED** |
| Master wide shot | Both characters, environmental motion | 5.07s | Animated successfully, background trees sway | **APPROVED** |
| Assembly test | All three shots cut together with dialogue | 5.07s total | **FAILED** — See notes below | **FAILED** |

#### Assembly Problems

When all three shots were combined with dialogue audio:
- **Scene transitions happened during dialogue** — Cuts appeared while characters were still speaking
- **First image in sequence was wrong** — Playback showed close-up first, then wide shot (reversed order)
- **Pauses in wrong places** — Silence gaps appeared mid-dialogue instead of between beats
- Kim feedback: "Scene transitions are happening while the dialogue is still going on... first image should be the reference image... pauses are in all the wrong places"

#### Root Cause

The assembly was scripted via ffmpeg, with timing calculated automatically based on audio duration + pause settings. However:
- Timeline didn't account for beat structure (where dialogue actually ends)
- Transition timing was offset from dialogue pacing
- Shot order wasn't validated before assembly

#### Lesson: Kim Must Control Sequence Timing

**KEY FINDING:** Automated scene assembly doesn't work. Kim must manually control:
1. **Shot order** — Which image appears when
2. **Cut timing** — Exactly where transitions happen (ideally: between dialogue beats, not during)
3. **Pause placement** — Where silence gaps occur

This is why the storyboard tool is critical — it gives Kim a place to orchestrate timing interactively, rather than relying on automatic ffmpeg choreography.

#### Artifact Summary Across All Shots

| Artifact | Frequency | Example | Mitigation |
|----------|-----------|---------|-----------|
| Extra limbs | ~20% of non-human shots | 6-legged Tessa | Regenerate with motion prompts |
| Ghost doubling | ~15% | Blurry offset copy 1mm away | Inconsistent; regenerate |
| Scale distortion | ~10% | Character grows mid-clip | Avoid gesture prompts ("wing flap") |
| Text hallucination | ~15% | Random text on background | Cannot be fixed — regenerate |
| Tear amplification | 100% when present | Tears become waterfalls | Remove tears from input entirely |

---

## 11. Kling v1/Standard — HARD BAN

**NEVER use fal.ai Kling v1/standard tier under any circumstances.** This is a HARD BAN, not a preference.

**What happened:** All 9 Event 1 shots were submitted to Kling v1/standard as a fallback when WaveSpeed was temporarily unreachable. Every single output was catastrophic:
- Shot 1: Random landscape scene with no Tessa — model completely ignored input image
- Shots 2, 4: Rubber tears, faces mushing together
- Shots 3, 7: Massive tear waterfalls (sink turned on)
- Shots 5a, 5b, 7, 8: Blurry, white backgrounds, characters standing in void
- Shot 6: Guide Bird's eyes doing uncontrolled rolling
- Shot 8: Guide Bird became gigantic, non-English text hallucinated

**Root cause:** Kling v1/standard is the LOWEST tier. It is prompt-dominant — meaning it generates video primarily from the text prompt and treats the input image as a very loose suggestion. Higher tiers (v1.5/pro, v2/standard, v2/master, v3/pro) are more image-faithful.

**Available Kling tiers (from worst to best):**
- v1/standard — BANNED (prompt-dominant, ignores input)
- v1.5/pro — Minimum acceptable tier if Kling must be used
- v2/standard — Better image fidelity
- v2/master — Good quality
- v3/pro — Best quality (highest cost)

**Fallback chain:** Seedance 1.5 Pro (primary) → fal.ai Seedance 2.0 → Kling v1.5/pro or higher. SKIP v1/standard entirely.

### Network Restrictions in Sandbox

- Some environments restrict outbound network access

- This affects multi-agent orchestration where agents try to call external APIs

- **Workaround:** Centralize API calls in one agent; have other agents prepare prompts/data only

---

## 12. Text Overlay on Images: FLUX Kontext vs PIL

### NEVER Use Generative Models for Text

The Everdale sign disaster showed that using ANY generative model (FLUX Kontext, FLUX Pro, etc.) to paint or carve text onto images produces obviously AI-generated, out-of-place text. The model hallucinates font irregularities and cannot maintain visual consistency with the surrounding image.

### USE Python PIL/cv2 for Precise Text Overlay

Text on images MUST be painted using PIL (Python Imaging Library) or OpenCV (cv2), which are deterministic and produce pixel-perfect results.

**PIL Text Overlay Requirements:**
- Exact coordinate identification (top-left x, y position of text)
- Font selection (TrueType .ttf files must be available in the pipeline)
- Font size in pixels (scale based on image resolution; e.g., 48px for 1920x1080)
- Text color (RGB tuple)
- Text anchor point (determines whether coordinates are top-left, center, etc.)

**Lesson:** Do not guess placement. Calculate coordinates precisely:
```python
# Example: Paint "Everdale" at bottom of 1920x1080 image
# Text starts 100px from bottom, centered horizontally
img = Image.open("background.png")  # 1920x1080
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("fonts/serif.ttf", size=48)
text = "Everdale"
# Calculate position for centered text
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
x = (1920 - text_width) // 2
y = 1080 - 100
draw.text((x, y), text, fill=(255, 255, 255), font=font)
```

### Tears Update — Shot 6 Does Not Require Removal

Master shot 6 (`shot6_v6_c1_1.png`) does NOT contain visible tears, so tear removal was not necessary for this specific shot. The tear removal concern applies primarily to other shots (1, 2, 3, 7) where Tessa is crying and tears are visible.

---

## 13. Agent Verification Issues

Critical discovery: Agents claim generation success without comparing output to reference images.

### 13.1 Agent Verification Is Unreliable

Agents frequently report "generation successful" without actually comparing the output to reference images or identity blocks. This causes bad images to be sent to Kim without being caught.

**Problem:** Agents use heuristics like "request returned 200 OK" or "image file created" as proof of success, but this doesn't verify quality.

**Solution:** After every generation batch, an agent must:
1. Load the reference images into memory
2. Load the generated output images into memory
3. Compare dimensions, character identity, color palette, style consistency
4. Flag any deviations before reporting to Kim

**Implementation:** Build a verification function that actually looks at pixel data or at least loads images for visual inspection. Do not rely on file status or API response codes.

### 13.2 Gemini Blue Scarf Problem

Gemini 2.5 Flash Image Generation frequently misinterprets Guide Bird's blue scarf design, generating a brown HOOD instead.

**Symptom:** "Guide Bird has a brown cowl/hood instead of a blue knitted scarf"

**Root Cause:** "Scarf" and "knitted" may not be specific enough. Gemini may default to bird anatomy (a hood/cowl is common in bird character design).

**Fix:** Use explicit blocking language in every Guide Bird prompt:
```
Guide Bird with blue knitted scarf/cowl around neck, NOT a brown hood, NOT animal fur, 
NOT a leather collar. The scarf is clearly woven knit material, blue in color, draped or tied at neck.
```

**Affects:** ~30-40% of Guide Bird generations if not explicitly blocked. This is a consistent enough pattern that every prompt should include the blocking language.

### 13.3 Bioluminescence Creep in Magic Scenes

When prompts include phrases like "magical forest," "enchanted," or "mystical," Gemini spontaneously adds glowing particles, bioluminescent plants, and light trails that were never requested.

**Symptom:** "Why does everything have glowing particles? The scene looks like a disco."

**Root Cause:** Gemini interprets "magical" as "needs visual effects" and hallucinate light effects to convey magic.

**Fix:** Explicitly block bioluminescence in any magical setting:
```
Magical forest setting with ancient trees, mystical but NOT glowing, NO bioluminescent particles, 
NO glowing flowers, NO light trails, NO halos. Natural forest lighting only.
```

**Affects:** High-magic scenes (Heartwood, enchanted objects, magical moments). Add blocking language to all such prompts.

---

## 14. Tears Are Unanimatable — Remove From All Stills

### The Discovery

During Seedance 1.5 Pro animation of Event 1 stills, every shot containing visible tears produced catastrophic results. Even subtle, light tear drops were amplified into full waterfalls streaming down characters' faces. This happened on shots 1, 2, 3, 4, 7, and 8 — every shot where Tessa had visible tears.

### Root Cause

All image-to-video diffusion models amplify liquid features. A single tear drop (a few bright pixels on a dark surface) gets interpreted as a flow pattern and extended across frames. The model has no concept of "this is a single stationary tear" — it sees bright reflective pixels and animates them as flowing liquid. Motion prompts mentioning tears ("Tessa with tears rolling down her cheek") make it dramatically worse, but even neutral prompts ("gentle breathing motion") cause amplification.

### The Rule (HARD BAN)

**Remove ALL visible tears from ALL character stills before animation.** This includes:
- Tear drops on cheeks
- Wet/glistening eye surfaces suggesting active crying
- Tear tracks or streaks on face
- Any bright reflective spots near eyes that could be interpreted as liquid

### How to Convey Crying

Crying is conveyed through **audio only** (ElevenLabs voice acting with emotional direction tags like `[tearful, voice breaking]`, `[sniffling]`). The visual shows:
- Puffy/tired eyes (acceptable — not liquid)
- Slightly red/irritated eye area (acceptable — not liquid)
- Downcast expression (acceptable)
- Withdrawn/protective body posture (acceptable)

### Affected Models

This limitation applies to ALL tested image-to-video models:
- Seedance 1.5 Pro (WaveSpeed) — confirmed April 13
- Kling v1/standard (fal.ai) — confirmed April 13 (even worse)
- Hailuo 2.3 — expected same behavior (untested with tears)
- Runway Gen-4.5 — expected same behavior (untested with tears)

---

## 15. Kim's Critical Feedback Patterns

### #1 Error: Wrong Character Identity

- Kim's #1 complaint: 'Tessa that looks nothing like tessa', 'wrong turtle', 'wrong bird'

- This happens when: identity preservation block is weak, reference images are weak, or style lock is missing

- **Prevention:** Run identity block as first-pass test before full generation

### #2 Error: Excessive Scene Cuts

- Kim: 'There should only be 4 scene swaps if there are only 4 beats'

- Problem: Claude was generating a new still for EVERY line of dialogue instead of per-scene

- **Fix:** Align shot generation to beat structure, not dialogue line structure. One beat = one shot (unless beat sheet specifies otherwise)

### #3 Error: Wrong Emotional Expression

- Kim: 'bird should not have such a huge grin... bird should look sympathetically at tessa, not be super happy'

- This is a prompt engineering issue. Emotional direction must be explicit

- **Example good prompt:** 'Guide Bird with a gentle, sympathetic expression, leaning toward Tessa with concern visible in his eyes and posture. He is comforting, not cheerful.'

- **Example bad prompt:** 'Guide Bird' (no emotional direction)

### #4 Feedback: File Format & Delivery

- Kim: 'send the links always!'

- **Never:** Inline small images in chat. Kim cannot see them or evaluate quality

- **Always:** Send direct file links (URLs or paths) to contact sheets showing all candidates

- **Contact sheet format:** Grid of all candidates (e.g., shot2_v3_candidates.jpg with 4x4 grid) so Kim can compare

- **Never:** Rely on 'I think this one is best' — let Kim choose from full candidate set

---

## 16. Process & Pipeline Failures

### Batch Generation Quality Collapse

- Symptom: Entire batch of shots came back wrong (photorealistic, wrong characters, wrong style)

- **Root cause identified:** Claude may have skipped skill loading or deviated from documented process

- **Prevention:** Load dashboard-gate FIRST before any generation. This skill enforces process compliance

- **Verification step:** After generation, always check 2-3 outputs against identity block before sending to Kim

### Reference Images Not Passing Through

- Issue: Some batches may have dropped reference images due to network errors

- **Fix:** Verify reference images are loaded and present in the API request before sending

- **Logging:** Log reference image count + IDs to dashboard activity log

### Verification Steps Are Mandatory

- After EVERY generation batch: spot-check 2-3 outputs

- Compare against identity block (Is Tessa recognizable? Is style Pixar 3D? Is emotion right?)

- If ANY candidate is wrong, regenerate the batch. Don't send substandard outputs to Kim

---

## 17. ffmpeg Assembly & Audio Sync

### Beat-Grouped Crossfades

- Don't crossfade every transition. Only crossfade between beats within the SAME scene

- Scene transitions: hard cut or brief fade (0.2-0.3s)

- Within-scene motion: smooth crossfade (0.5-1.0s)

### Resolution & Framerate Normalization

- All generated stills come in different resolutions (depends on Gemini, Seedance output)

- Normalize to 1920x1080 before animation

- Normalize to 30fps (or 24fps) before mixing

- Use ffmpeg -vf scale and -r flags

---

## 18. Skills & Workflow Enforcement

### Dashboard-Gate (Load FIRST)

- Runs 7-query protocol at session start

- Checks for prior rejected settings, locked decisions, Kim feedback

- Prevents re-trying failed approaches

- **Do not skip this**

### Video-Producer (Load Next)

- Contains 9-step production checklist

- References Gemini for stills (not FLUX Kontext anymore)

- Covers animation, lip sync, TTS, assembly

### Audio-Producer (Load for Phase B Only)

- Used for meditation audio (Phase B segment)

- Story dialogue TTS is handled by video-producer

- Do not confuse the two

---

## 19. Specific Prompting Techniques That Worked

### Identity Block Template (Tested & Working)

For **Tessa** (turtle character):
```
Tessa is a young turtle character with the following fixed features:
- Shell: Distinctive green with brown patterns, age-appropriate size (not oversized)
- Face: Soft, expressive, triangular-shaped snout, bright eyes, small nostrils
- Body: Turtle proportions (short legs, appropriate neck length for a young turtle)
- Color: Green shell with brown markings, light cream/tan underbelly, greenish-gray skin tones
- CRITICAL NOT: NOT oversized baby head, NOT short neck, NOT human proportions, NOT cartoon turtle

Pixar 3D animated style, warm soft lighting, expressive character design
```

For **Guide Bird** (character):
```
Guide Bird is a bird character with expressive, kind eyes and gentle features.
- Colors: [specific wing/body colors per design doc]
- Blue knitted scarf around neck, NOT a brown hood, NOT animal fur, NOT a leather collar
- Expression: [emotional state for this shot]
- NOT: Not a parrot, NOT oversized, NOT cartoonish (maintain Pixar 3D style)

Pixar 3D animated style, warm soft lighting, detailed feather texture, expressive eyes
```

### Emotional Direction Markers (Tested)

Instead of relying on voice tone, use explicit markers in script:
- `[sad, vulnerable]` "Oh... Hi... I'm sorry"
- `[resigned, slightly hopeful]` "I'm Tessa"
- `[sympathetic, gentle]` [Guide Bird looking at Tessa with concern]
- `[concerned, warm]` [Reaching toward Tessa]

These markers guide both visual generation (expression) and voice tone (via ElevenLabs with emotion-aware rendering).

### What Went Wrong with Prompts

**Bad:** "Generate Guide Bird character" — Results in wrong emotion, wrong pose, sometimes wrong bird entirely

**Good:** "Guide Bird with a gentle, sympathetic expression, leaning slightly toward Tessa with concern visible in his eyes and posture. He is comforting, not cheerful."

**Bad:** "Add bird and turtle to scene" — Results in identity confusion, scale issues

**Good:** [Two-pass] "Pass 1: Tessa alone, sad expression, sitting on rocks. Pass 2: Add Guide Bird to the left, perched, leaning toward Tessa."

---

## 20. What Was Attempted & What Worked / Failed

### Attempt 1: Single-Pass Gemini with All References
- **Result:** FAILED for duo shots
- **Why:** 7+ images in one call caused Tessa's identity to drift while Guide Bird remained consistent
- **Lesson:** Gemini's multi-ref system works best with <7 total images per call

### Attempt 2: Two-Pass Gemini (Pass 1: Tessa + scene, Pass 2: Add Guide Bird)
- **Result:** SUCCESS for duo shots
- **Specific example:** Shot 2 (Guide Bird approaches crying Tessa) — Pass 1 nailed Tessa's sad expression and rocky setting, Pass 2 added Guide Bird with correct concern-filled expression
- **Key detail:** Pass 1 output + Guide Bird refs had perfect identity preservation
- **Cost:** ~$0.16 per duo shot (two generations instead of one)

### Attempt 3: FLUX Kontext for Text Overlay (Everdale Sign)
- **Result:** FAILED, never try again
- **Why:** Generative models cannot create readable text overlays. Text looked obviously AI-generated and out-of-place
- **Alternative:** Use Python PIL/cv2 to paint or carve text with fonts

### Attempt 4: ElevenLabs with Default Voice Tone
- **Result:** FAILED emotionally
- **Feedback:** "chipper and didactic when they should be conversational and soft/sad"
- **Why:** Default voices render all dialogue with same tone regardless of scene emotion
- **Solution:** Segment-level rendering with emotion tags (pending implementation)

### Attempt 5: Single Still per Dialogue Line
- **Result:** EXCESSIVE SCENE CUTS
- **Feedback:** "There should only be 4 scene swaps if there are only 4 beats"
- **Why:** Claude generated a new still for every line instead of per-beat
- **Fix:** Align shot generation to BEAT STRUCTURE, not dialogue line structure

### Attempt 6: Batch Generation without Verification
- **Result:** QUALITY COLLAPSE
- **Symptom:** One batch came back with photorealistic, wrong-character, wrong-style shots
- **Why:** Possible skill deviation or API issues
- **Fix:** ALWAYS verify 2-3 outputs per batch against identity block before sending to Kim

### Attempt 7: Inline Image Preview in Chat
- **Result:** REJECTED by Kim
- **Feedback:** "send the links always!"
- **Why:** Inline images in chat are too small for Kim to evaluate quality
- **Solution:** Always create contact sheets (grid image with all candidates) and send file paths/URLs

### Attempt 8: ByteDance LipSync on Non-Human Character
- **Result:** COMPLETE FAILURE
- **Why:** Model trained on human faces; destroys non-human character identity entirely
- **Lesson:** Pixel-based lip sync is fundamentally incompatible with cartoon animals

### Attempt 9: Hailuo 2.3 Dialogue-Prompted Animation
- **Result:** CHARACTER DRIFT + NO AUDIO SYNC
- **Why:** Text prompts cannot control mouth movement; video generation has no access to audio waveform
- **Lesson:** Text-prompted animation is architecturally incapable of producing lip sync

### Attempt 10: Scene-First Variant Switching (with wrong model)
- **Result:** FLASHING BETWEEN UNRELATED IMAGES
- **Why:** Used fal.ai flux-general (image-to-image) instead of FLUX Kontext (inpainting)
- **Lesson:** Image-to-image generates new images; inpainting edits existing ones. The two are NOT interchangeable
- **Fix:** Retry with direct BFL API (api.bfl.ml) for true surgical edits

---

## 21. Summary: Error Prevention Checklist

Before EVERY generation batch:

1. Load dashboard-gate and run 7-query protocol

2. Identity block present and verbatim for all characters? YES → continue

3. Style lock (Pixar 3D) explicit in prompts? YES → continue

4. Reference images: hero first, pose variants after? YES → continue

5. Emotional direction explicit (not default tone)? YES → continue

6. No background refs in duo shots (use text description instead)? YES → continue

7. No bioluminescence creep (explicit blocking if "magical")? YES → continue

8. Guide Bird scarf explicitly described (blue knit, NOT brown hood)? YES → continue

9. Generate → check 2-3 outputs → compare against identity block

10. If ANY candidate wrong → regenerate batch

11. Send contact sheet (full grid, not inline) to Kim with file links

12. Kim selects winners → proceed to animation

---

## 22. Resource Expenditure & API Costs

**April 12-13, 2026 Session Summary:**

- **Gemini 2.5 Flash:** ~40 generations × $0.039 = ~$1.56
- **FLUX Kontext:** ~8 edits × $0.08 = ~$0.64
- **WaveSpeed Seedance:** ~12 requests (variable costs, some throttled)
- **ElevenLabs TTS:** ~30 voice generations × variable cost per character
- **Runway Gen-4.5:** 1 throttled request (no output)
- **ByteDance LipSync:** 1 request (output destroyed)
- **Hailuo 2.3:** 3 requests × variable cost
- **fal.ai Seedance 2.0:** 2 requests as fallback
- **Total session cost:** ~$5-10 (exact depends on ElevenLabs + WaveSpeed pricing)

---

## 23. Documentation & Reference Links

**Key external docs referenced in this session:**
- `VIDEO_PIPELINE_TESTING_GEMINI_v1.md` — Full test results from prior Gemini testing (21 sections)
- `NANO_BANANA_PIPELINE_v1.md` — Original Gemini approach doc with prompt anatomy templates
- `VIDEO_PIPELINE_LOCKED_DECISIONS_APRIL10_2026.md` — Locked visual and animation tool decisions
- `VISUAL_AND_ANIMATION_PIPELINE_LOCKED_DECISIONS_APRIL10_2026.md` — Same as above (variant name)
- `EVENT_1_STORY_SCENE_PRODUCTION_v1.md` — Beat sheet with detailed shot descriptions
- `EVENT_1_INTRO_SHOT_PLAN.md` — Generation + animation + lip sync strategy

**Production skills:**
- `dashboard-gate` — Behavioral gatekeeper (LOAD FIRST)
- `video-producer` — Master production skill (contains 9-step checklist)
- `audio-producer` — Phase B meditation audio (not story dialogue)
- `dashboard-ops` — API toolkit for Directus operations

---

## 24. Recommendations for Next Session

1. **Build the close-up headshot cropper tool for Kim** — Interactive interface where she can place boxes on the master image and generate cropped assets (save as PNG files). High priority for UX improvement.

2. **Finish the storyboard-first workflow:**
   - Prepopulate storyboard tool from skeleton beats (beat_id, dialogue text, beat duration)
   - Allow Kim to edit dialogue text directly in the storyboard
   - Generate TTS AFTER dialogue is locked
   - Kim sequences scene order and pause durations
   - Export JSON to animation pipeline

3. **Fix stale "Kling 3.0" and "fal.ai Seedance" references in PIPELINE_BRAIN_v3 and HYBRID_PIPELINE_v2** — These docs reference animation approaches that have been superseded by Seedance 1.5 Pro + variant switching strategy. Update to reflect current architecture.

4. **Retry FLUX Kontext variant switching** using direct BFL API access (api.bfl.ml). This is the lowest-effort test with the highest potential payoff for dialogue scenes.

5. **If BFL API remains unreachable,** investigate alternative inpainting models that can perform true surgical edits on a specific image region (mouth area) while preserving the rest.

6. **Evaluate Blender bpy as a long-term investment.** Prototype a single character rig (Tessa) with mouth shape keys and test automated scene generation from phoneme data.

7. **Consider the hybrid approach for near-term production needs:** AI backgrounds + Cartoon Animator 5 for character dialogue. This may be the fastest path to shippable content.

8. **Build agent verification functions** that compare generated output to reference images before reporting success to Kim.

9. **Update PIPELINE_BRAIN_v1.md** to document dialogue scene limitations and the viable paths forward.

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

## 31. Updated Recommendations for Next Session

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

**Document prepared by Claude (Opus) — April 12-13, 2026**

**Version:** v6 (v5 + April 13 evening session: TTS audition workflow, storyboard corruption root cause, Cowork file delivery, Directus API pitfalls, tool persistence checklist, pause tag lessons)

**Status:** Ready for production reference. Update as new approaches are tested (v6 → v7, etc.).

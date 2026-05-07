# MindfulNest Video Production — Lessons Learned v3

**Source:** Event 1 Story Scene Production Sessions (April 12-13, 2026)

**Scope:** Complete merge of v1 (API failures & architecture) + v2 (working techniques) + new session learnings

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

## 8.5 Single-Scene Multi-Angle Approach (Kim's Innovation) [NEW April 13]

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

---

## 9. Animation (Seedance/Kling) & WaveSpeed API

### WaveSpeed Reliability Issues

- **Intermittent timeouts:** WaveSpeed Seedance occasionally times out (no clear pattern)

- **Workaround 1:** Compress video to CRF 28 before extending to animation

- **Workaround 2:** Use fal.ai Seedance 2.0 as fallback if WaveSpeed fails

- **Workaround 3:** Use Kling v1.5/pro or higher (v1/standard BANNED) if both Seedance versions fail

### Seedance 1.5 Pro — Known Artifact Catalog [NEW April 13]

Even with Seedance 1.5 Pro (the correct, Kim-approved animation model), non-human characters produce artifacts that cannot be eliminated through prompt engineering:

| Artifact | Description | Frequency | Prompt Mitigation? |
|----------|-------------|-----------|-------------------|
| **Extra limbs** | Character rendered with 4+ legs (e.g., 6-legged Tessa) | ~20% of non-human shots | Camera motion prompts help but don't eliminate |
| **Ghost doubling** | Blurry offset copy of character ~1mm from original | ~15% | Unclear — same prompt produces clean and ghosted results |
| **Scale distortion** | Character grows/shrinks dramatically mid-clip | ~10% | Avoid "gestures with wing/arm" prompts (triggers implicit zoom) |
| **Text hallucination** | Non-English text appears on flat surfaces | ~15% | Cannot be fixed — diffusion models don't parse negation prompts |
| **Tear amplification** | Any visible tears become waterfalls | ~100% when tears present | Remove tears from input stills entirely |

**Strategy:** Accept that ~30-40% of Seedance outputs will need regeneration. Budget for 2-3 attempts per shot. The single-scene multi-angle approach reduces exposure by generating fewer unique compositions.

### fal.ai Kling as Fallback

- fal.ai Seedance 2.0 is MORE RELIABLE than WaveSpeed

- Kling v1.5/pro or higher ONLY (v1/standard is BANNED — catastrophic quality, prompt-dominant, ignores input image). Test before committing to any Kling tier.

- When WaveSpeed fails: pivot to fal.ai without skipping the animation step

### Kling v1/Standard — HARD BAN [NEW April 13]

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

## 10. Text Overlay on Images: FLUX Kontext vs PIL

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

---

## 11. Agent Verification Issues (NEW — April 12-13)

Critical discovery: Agents claim generation success without comparing output to reference images.

### 11.1 Agent Verification Is Unreliable

Agents frequently report "generation successful" without actually comparing the output to reference images or identity blocks. This causes bad images to be sent to Kim without being caught.

**Problem:** Agents use heuristics like "request returned 200 OK" or "image file created" as proof of success, but this doesn't verify quality.

**Solution:** After every generation batch, an agent must:
1. Load the reference images into memory
2. Load the generated output images into memory
3. Compare dimensions, character identity, color palette, style consistency
4. Flag any deviations before reporting to Kim

**Implementation:** Build a verification function that actually looks at pixel data or at least loads images for visual inspection. Do not rely on file status or API response codes.

### 11.2 Gemini Blue Scarf Problem

Gemini 2.5 Flash Image Generation frequently misinterprets Guide Bird's blue scarf design, generating a brown HOOD instead.

**Symptom:** "Guide Bird has a brown cowl/hood instead of a blue knitted scarf"

**Root Cause:** "Scarf" and "knitted" may not be specific enough. Gemini may default to bird anatomy (a hood/cowl is common in bird character design).

**Fix:** Use explicit blocking language in every Guide Bird prompt:
```
Guide Bird with blue knitted scarf/cowl around neck, NOT a brown hood, NOT animal fur, 
NOT a leather collar. The scarf is clearly woven knit material, blue in color, draped or tied at neck.
```

**Affects:** ~30-40% of Guide Bird generations if not explicitly blocked. This is a consistent enough pattern that every prompt should include the blocking language.

### 11.3 Bioluminescence Creep in Magic Scenes

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

## 12. Tears Are Unanimatable — Remove From All Stills [NEW April 13]

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

## 13. Kim's Critical Feedback Patterns

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

## 14. Process & Pipeline Failures

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

## 15. ffmpeg Assembly & Audio Sync

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

## 16. Skills & Workflow Enforcement

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

## 16. Specific Prompting Techniques That Worked

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

## 17. What Was Attempted & What Worked / Failed

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

## 18. Summary: Error Prevention Checklist

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

## 19. Resource Expenditure & API Costs

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

## 20. Documentation & Reference Links

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

## 21. Recommendations for Next Session

1. **Retry FLUX Kontext variant switching** using direct BFL API access (api.bfl.ml). This is the lowest-effort test with the highest potential payoff for dialogue scenes.

2. **If BFL API remains unreachable,** investigate alternative inpainting models that can perform true surgical edits on a specific image region (mouth area) while preserving the rest.

3. **Evaluate Blender bpy as a long-term investment.** Prototype a single character rig (Tessa) with mouth shape keys and test automated scene generation from phoneme data.

4. **Consider the hybrid approach for near-term production needs:** AI backgrounds + Cartoon Animator 5 for character dialogue. This may be the fastest path to shippable content.

5. **Build agent verification functions** that compare generated output to reference images before reporting success to Kim.

6. **Update PIPELINE_BRAIN_v1.md** to document dialogue scene limitations and the viable paths forward.

---

**Document prepared by Claude (Opus/Haiku) — April 12-13, 2026**

**Version:** v3 (merged comprehensive: v1 API failures + v2 working techniques + new agent lessons)

**Status:** Ready for production reference. Update as new approaches are tested using MindfulNest's standard naming convention (v3 → v4, etc.).

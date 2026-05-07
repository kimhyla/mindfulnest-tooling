# MindfulNest Video Production — Lessons Learned v2

**Source:** Event 1 Story Scene Production Session (April 12-13, 2026)

**Generated:** Extracted from full conversation transcript (585 entries)

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

- **Style drift (photorealism):** If character identity preservation block is weak or missing, generation can suddenly shift to photorealistic/3D renderings instead of Pixar style. **Why:** Lacking the constraint, Gemini defaults to realistic human photograpy when confused about identity


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

- ALL prompts must include: 'Pixar 3D animated style, warm soft lighting, expressive character design'

- If generation comes out photorealistic, humanoid, or wrong style: reread identity preservation block and regenerate. Style drift indicates missing/weak constraints


### Unicode Issue


- DON'T use Unicode ellipsis `…` in prompts. Use `...` (three periods) instead

- Unicode in prompts sometimes causes API errors or text rendering issues


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

- Prompt includes spatial instruction: 'Add Guide Bird to the left, perched on the signpost, leaning toward Tessa with concern'

- This preserves BOTH characters' identities


### Why It Works

- Gemini's multi-ref system works best with <7 images at a time

- When character count + background = too many refs, subtle character drifts

- Two-pass splits the load: first pass nails the primary, second pass adds secondary to an already-locked composition


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


## 5. Animation (Seedance/Kling) & WaveSpeed API


### WaveSpeed Reliability Issues

- **Intermittent timeouts:** WaveSpeed Seedance occasionally times out (no clear pattern)

- **Workaround 1:** Compress video to CRF 28 before extending to animation

- **Workaround 2:** Use fal.ai Seedance 2.0 as fallback if WaveSpeed fails

- **Workaround 3:** Use Kling 3.0 (alternative animation model) if both Seedance versions fail


### fal.ai Kling as Fallback

- fal.ai Seedance 2.0 is MORE RELIABLE than WaveSpeed

- Kling 3.0 also works but has different motion style (test before committing)

- When WaveSpeed fails: pivot to fal.ai without skipping the animation step


### Network Restrictions in Sandbox

- Some environments restrict outbound network access

- This affects multi-agent orchestration where agents try to call external APIs

- **Workaround:** Centralize API calls in one agent; have other agents prepare prompts/data only


## 6. Kim's Critical Feedback Patterns


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

- **Example good prompt:** 'Guide Bird with a gentle, sympathetic expression, leaning toward Tessa with concern in his eyes'

- **Example bad prompt:** 'Guide Bird' (no emotional direction)


### #4 Feedback: File Format & Delivery

- Kim: 'send the links always!'

- **Never:** Inline small images in chat. Kim cannot see them or evaluate quality

- **Always:** Send direct file links (URLs or paths) to contact sheets showing all candidates

- **Contact sheet format:** Grid of all candidates (e.g., shot2_v3_candidates.jpg with 4x4 grid) so Kim can compare

- **Never:** Rely on 'I think this one is best' — let Kim choose from full candidate set


## 7. Process & Pipeline Failures


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


## 8. ffmpeg Assembly & Audio Sync


### Beat-Grouped Crossfades

- Don't crossfade every transition. Only crossfade between beats within the SAME scene

- Scene transitions: hard cut or brief fade (0.2-0.3s)

- Within-scene motion: smooth crossfade (0.5-1.0s)


### Resolution & Framerate Normalization

- All generated stills come in different resolutions (depends on Gemini, Seedance output)

- Normalize to 1920x1080 before animation

- Normalize to 30fps (or 24fps) before mixing

- Use ffmpeg -vf scale and -r flags


## 9. Skills & Workflow Enforcement


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


## 10. Specific Prompting Techniques That Worked

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

## 11. What Was Attempted & What Worked / Failed

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

## 12. Summary: Error Prevention Checklist


Before EVERY generation batch:

1. Load dashboard-gate and run 7-query protocol

2. Identity block present and verbatim for all characters? YES → continue

3. Style lock (Pixar 3D) explicit in prompts? YES → continue

4. Reference images: hero first, pose variants after? YES → continue

5. Emotional direction explicit (not default tone)? YES → continue

6. No background refs in duo shots (use text description instead)? YES → continue

7. Generate → check 2-3 outputs → compare against identity block

8. If ANY candidate wrong → regenerate batch

9. Send contact sheet (full grid, not inline) to Kim with file links

10. Kim selects winners → proceed to animation

## 13. Documentation & Reference Links

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


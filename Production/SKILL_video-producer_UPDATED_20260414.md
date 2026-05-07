---
name: video-producer
description: |
  Master production skill for MindfulNest module events. Orchestrates the full pipeline: skeleton → shot breakdown → FLUX Kontext stills → Seedance/Kling animation → ByteDance lip sync → ElevenLabs TTS → Phase B audio → ffmpeg assembly. Covers all 7 segments (Story Scene, Buy-In, Phase A, Phase B, Resolution, Win, Map Return). Trigger on: 'produce event', 'produce module', 'video production', 'shot breakdown', 'animation', 'lip sync', 'TTS generation', 'Phase B audio', 'assemble video', 'FLUX Kontext', 'Seedance', 'Kling', 'ByteDance', 'ElevenLabs', 'render audio', 'generate stills', 'animate clips', 'let's produce', 'start production', 'build the video', 'production checklist', or ANY task converting skeleton content into finished video/audio. If you are about to do ANY production work for MindfulNest, load this skill FIRST.
---

# Video Producer: End-to-End Module Production for MindfulNest

## What This Skill Does

This skill orchestrates the complete production of a MindfulNest module event — from reading the skeleton to delivering finished video and audio files. It consolidates the scene-to-production, phase-a-designer, and phase-b-writer workflows into a single production pipeline with the current (April 2026) toolchain.

**Kim's workflow context:** Kim is a solo founder who works with AI tools in real-time sessions. Production happens in a single sitting (2-4 hours per event), not across weeks. Claude makes API calls; Kim reviews outputs as they come. There is no production team, no weekly cadences, no handoffs. Plan accordingly.

## The Cardinal Rules

These rules override everything else. Violations are production-stopping errors.

### 1. Source Fidelity Protocol
Kim-authored dialogue is preserved VERBATIM — never retyped through Claude's text generation. When producing TTS scripts, shot breakdowns, or any document containing dialogue, COPY Kim's text character-for-character from the skeleton. Only change dialogue where Kim explicitly instructs.

### 2. The Skeleton IS the Screenplay
The arc skeleton is the authoritative source for all scene content: dialogue, stage directions, camera moves, visual descriptions, production notes. This skill DECOMPOSES existing scenes into production assets. It does NOT generate new creative content, rewrite dialogue, add scenes, or change the narrative.

### 3. Screen Direction Is Binding
When the skeleton says "Camera slowly pans left to reveal the Heartwood Tree," the shot breakdown must include that exact camera move. Screen direction in the skeleton is not a suggestion — it's a production instruction.

### 4. Three Questions Gate (Before Phase A/B Work)
Before designing Phase A or writing Phase B for any module, answer:
1. **What to show conceptually?** (the therapeutic mechanism in Everdale terms)
2. **How does the creature show it?** (creature-specific physical vocabulary)
3. **What technique solves it?** (the actual clinical technique)

If you can't answer all three clearly, stop and ask Kim.

### 5. No Corporate Timelines
Never produce multi-week project plans, weekly review cadences, or team-based workflows. One event = one production session. Cost should be single digits of dollars. Kim reviews in real-time, not at scheduled checkpoints.

### 6. One Module Per Session
Produce ONE module event per session only. Do not attempt to batch two events in parallel or sequence. Each event requires fresh API calls, separate approval gates, and individual Kim review cycles. If Kim asks for two, finish event 1 completely (through Step 9) before starting event 2 in a new session.

### 7. Event 0 Is Pre-Produced — Do Not Run This Pipeline On It
The Opening Storybook (Event 0) is a pre-produced video asset — NOT runtime-composed. It uses Myrrhin's narrator voice baked in, contains NO personalization variables, and plays once on first app launch. If the event you're producing is Event 0, STOP. Do not proceed with Steps 1-9. Flag for Kim to handle separately.

### 8. No Midjourney — Use FLUX Kontext Only
Midjourney was used for early visual development but is no longer part of the production pipeline. Use FLUX Kontext [max] via Replicate API ONLY for still generation. If FLUX Kontext API is unavailable, ask Kim before attempting any fallback tool.

## The 7-Segment Module Event Pipeline

Every module event contains up to 7 segments, produced in this order:

| # | Segment | Type | Who Produces |
|---|---------|------|-------------|
| 1 | **Story Scene** | Pre-produced video (runtime-composed) | This skill: stills + animation + TTS |
| 2 | **Buy-In** | Runtime: Guide Bird Rive + TTS + gradient BG | This skill: script only (visual is automated) |
| 3 | **Phase A** | Interactive (Phaser code) | Design brief only — see §Phase A below |
| 4 | **Phase B** | Guided meditation audio | This skill: full audio production pipeline |
| 5 | **Resolution** | Pre-produced video (runtime-composed) | This skill: stills + animation + TTS |
| 6 | **Win Sequence** | Standardized Phaser component | Data config only (coins, spell, decoration) |
| 7 | **Return to Map** | Phaser sprites + Firestore | Data config only (sprites, dialogue, state) |

Non-module narrative events (Opening Storybook, Guide Bird Intro, Oliver, Agent encounters) are pure story scenes — segments 2-7 don't apply.

## Production Checklist (The Actual Workflow)

This is the step-by-step order for producing one module event. Each step has a Kim gate where she reviews before proceeding.

### Gate 0: Pre-Production Readiness

Before touching any tools, confirm:
- [ ] Which event are you producing? State the M-number and creature name.
- [ ] Is this Event 0 (Opening Storybook)? If YES → STOP. Event 0 is pre-produced. Do not run this pipeline.
- [ ] Is the skeleton locked/current for this event? (Check file dates, ask Kim if unsure.)
- [ ] Does a Phase A design brief exist and is it approved? If not, note as prerequisite.
- [ ] Does a Phase B script exist and is it approved? If not, note as prerequisite.

Ask Kim: "I'm about to produce Event [N] ([Creature]). Is the skeleton current, and are Phase A and Phase B approved?"

### Step 1: Read and Decompose the Skeleton Event

Read the full skeleton event text. Extract:
- Every dialogue line (speaker, exact text, emotional register)
- Every stage direction and camera instruction
- Every production note
- The [DATA] block (if present) for win/map configuration
- Which segments this event contains

**Dialogue completeness check:** For each line, verify it's VERBATIM dialogue from Kim — not a placeholder. Placeholders look like: `[Character speaks about X]`, `[TODO]`, `[KIM TO WRITE]`, or `[DRAFT]`. Any placeholder = STOP and ask Kim for the final wording. Do not write new dialogue without explicit Kim approval.

**Variable validation:** Scan all extracted dialogue for hardcoded names that MUST be variables: "Pip" (should be `{chosenGuideName}`), any specific child name (should be `{childName}`). Flag and confirm with Kim before rendering.

**Output:** A structured extraction document with dialogue numbered sequentially and all visual beats identified.

### Step 2: TTS Voice Setup (Skip If Already Done)

Verify voice profiles are locked for every character in this event.

**VOICE ROSTER (LOCKED):**

| Character | Voice Name | ElevenLabs ID | Notes |
|-----------|-----------|---------------|-------|
| Guide Bird | Chipper1 | `7o9pyvsN0ob5GO6LBQp6` | Warm, energetic, slightly self-deprecating |
| Myrrhin | (library) | `oR4uRy4fHDUGGISL0Rev` | Old wise wizard, grandparent warmth |
| Tessa | Jessica | (select from library) | Turtle, gentle, hurt but hopeful |
| Luna | Miranda | (select from library) | Owl, excitable, dramatic, scholarly |
| Ember | Katie | (select from library) | Fox, warm, kind |
| Bramble | Northern Terry | (select from library) | Irish accent, tree creature |
| Benson | Gigi | (select from library) | Bear, brave, gruff but gentle |
| Bork | Bork2 | (select from library) | Porcupine, defensive, loud |
| Oliver | Brayden | (select from library) | Deer, wise, emotional |
| Grizzle | Gotham Boss | (select from library) | Deer, agent, authoritative |
| King | Carter | (select from library) | Regal, commanding |
| Lady Willow | Alisha | (select from library) | Gentle, ancient wisdom |

**TTS Production Rules:**
- Model: `eleven_v3` for ALL characters
- Settings: Stability 0.30, Similarity 0.80, Style 0.30
- "MindfulNest" ALWAYS spelled "Mindful-Nest" (hyphenated) in TTS scripts
- Emotional direction tags on EVERY line: `[excitedly]`, `[with relief]`, `[gently]`, etc.
- `{chosenGuideName}` is the child's chosen name for Guide Bird — NOT "Pip"
- Personalization variables: `{childName}`, `{chosenGuideName}`, `{childPronounObject}`, `{childPronounPossessive}`, `{therapistName}`, `{parentTitle}`, `{parentName}`

**Segment-level rendering optimization:**
- Lines with NO variables → render once, share across all children (universal)
- Lines WITH variables → only the sentence containing the variable is rendered per-child
- This keeps per-child TTS cost at ~$2.82 for the entire app

**Kim gate:** Generate 2-3 test lines per new character voice → Kim validates tone and emotion before batch rendering.

### Step 3: Generate All TTS Audio

Batch-render dialogue lines from Step 1 that have FINALIZED text. This covers Story Scene dialogue, Buy-In script (if written), and Resolution dialogue from the skeleton. Phase B narration is rendered separately in Step 7 (requires its own approved script). Phase A Guide Bird lines are rendered after the Phase A design brief is approved.

**Emotional direction tags:** Add emotional direction tags to every line (e.g., `[excitedly]`, `[with concern]`, `[gently]`). These are production annotations that help the TTS voice match the skeleton's emotional intent — they don't modify Kim's dialogue text. Derive the emotion from the skeleton's stage directions and context.

For each line:

```
Line [N]: [Speaker] — "[Exact dialogue from skeleton]"
Voice ID: [from roster]
Emotional direction: [tag]
Personalized: [yes/no]
Pronunciation: ["Mindful-Nest" hyphenated, other notes]
```

**Lines with variables** (rendered per-child at runtime): Any line containing `{childName}`, `{chosenGuideName}`, or pronoun variables.

**Universal lines** (render once): Everything else.

**Sentence-level splitting for mixed lines:** When a single dialogue line contains BOTH variable and non-variable sentences, split at sentence boundaries before rendering. Example: "Well you've come to the right place. I'm {chosenGuideName}. This is my new apprentice, {childName}." splits into: (A) "Well you've come to the right place." [universal], (B) "I'm {chosenGuideName}." [personalized], (C) "This is my new apprentice, {childName}." [personalized]. Render universal sub-sentences once; personalized sub-sentences render per-child at runtime.

### Step 4: Generate Key Stills (FLUX Kontext)

Use FLUX Kontext [max] on Replicate to generate scene stills from existing character reference images. No LoRA training needed — 382+ character images in `Production/` subfolders serve as direct references.

**Pipeline:** FLUX Kontext [max] via Replicate API → $0.08/image

**For each still, specify:**

```
STILL [number]
Description: [What the image shows]
Reference images: [Which existing character/background images to use as refs]
Composition: [Shot type, framing, camera angle]
Lighting: [Key light, mood]
Color palette: [Primary colors]
Style: Pixar 3D (luminous, warm, cinematic lighting, soft materials)
Continuity: [What must match adjacent stills]
```

**Critical rules for stills:**
- Use 2-3 existing character reference images per generation for consistency
- Include character's key visual identifiers in EVERY prompt
- First appearance of a character → that still becomes the reference for all subsequent shots
- Background references from `Production/Backgrounds/` and `video_pipeline/`
- Style is **Pixar 3D** (NOT painterly, NOT Midjourney watercolor — that's superseded)
- Never cross-paste between AI generators — clone/hue-shift within same image only

**Keyframe strategy:** You don't need one still per beat. With keyframe-to-keyframe generation (Kling 3.0), you can provide START and END images and the AI fills motion between. This can reduce stills needed to 2-3 per scene segment instead of one per shot. Use keyframe mode when you have clear start/end compositions; use single-still mode with video extension for continuous motion sequences.

**Resolution stills — FIRST-PERSON CAMERA:** All Resolution segment stills use first-person perspective. The child is NOT visible on screen — the child IS the camera. Compose as if the camera is positioned where the child's eyes are. Example: "Tessa's shell glowing, seen from 3 feet away, looking down at her" ✓. "Child with hands outstretched toward Tessa" ✗.

**Kim gate:** Quick visual check of stills before animating (~2 minutes). Confirm characters look right and Pixar 3D style is consistent.

**If a still looks wrong:** (A) Check reference images — are they clear and representative? Swap refs and regenerate. (B) If refs are good but output is off, tighten the prompt to emphasize the specific visual detail. (C) If style is wrong (too painterly, wrong lighting), regenerate with explicit "Pixar 3D" style language. Cost: ~$0.08/still per iteration, acceptable for up to 2-3 tries per still.

### Step 5: Animate Clips (Seedance 2.0 / Kling 3.0)

Take approved stills, animate them with motion prompts, chain clips via video extension.

**Tool selection:**

| Use Case | Tool | Cost | Notes |
|----------|------|------|-------|
| Character motion, expressions, body movement | Seedance 2.0 | ~$0.05/sec | Best for creature-specific movement |
| Keyframe-to-keyframe (start→end image) | Kling 3.0 | ~$0.10/sec | Fills motion between two stills |
| Scene transitions, magic effects | Pika Pikaframes | ~$0.20/video | Good for VFX-heavy sequences |

**Video extension / clip chaining (MANDATORY — no freeze frames):** When audio exceeds the animation tool's max clip duration (5s for Kling/Seedance), generate continuation clips by extracting the last frame of clip N and submitting it as input for clip N+1 with the same motion prompt. Concatenate all clips seamlessly, then trim to exact audio duration. NEVER use freeze-frame extension (tpad/stop_mode=clone) — frozen frames are forbidden in production output. This is how you build 50+ second continuous sequences from 4-5 second clips. Cost: ~$0.375 per additional 5s clip (EvoLink). Locked rule as of April 14, 2026.

**Tool consistency rule:** Once you select a tool for a video segment (e.g., Seedance 2.0 for Intro), use the SAME tool for all clips in that segment. Mixing tools within a segment creates style inconsistency. If a tool's API fails mid-segment: (A) retry after 60 seconds, (B) if still unavailable, ask Kim whether to wait, switch tools for the entire segment (regenerating earlier clips), or move on to another step.

**For each animation clip:**

```
CLIP [number]
Input: [Still number or "extend from C[N] last frame"]
Motion prompt: [60-100 words using 6-step formula]
Duration: [estimated seconds]
Tool: [Seedance 2.0 / Kling 3.0 / Pika]
Dialogue overlay: [which TTS line plays during this clip, or "none"]
Cost estimate: [$X.XX]
```

**Seedance 6-step motion prompt formula:**
1. SUBJECT: "[Character] with [key visual details]"
2. ACTION: "[specific movement — creature-anatomy-appropriate]"
3. ENVIRONMENT: "[setting details from skeleton]"
4. CAMERA: "[ONE camera movement only — matches skeleton screen direction]"
5. STYLE: "[Pixar 3D, lighting + mood]"
6. CONSTRAINTS: "[duration, no dialogue in video, specific limitations]"

**Creature movement must be anatomy-specific:** Tessa (turtle) = slow, deliberate shell movements, head tucks. Luna (owl) = wing flaps, head tilts, excited hopping. Benson (bear) = heavy footfalls, chest puffs. Each creature has unique physical vocabulary derived from the skeleton's character descriptions.

### Step 6: Lip Sync (ByteDance)

Only for clips where a character speaks on-screen dialogue. Narration/voice-over clips skip this.

**Pipeline:** ByteDance Lip Sync API → ~$0.15 per 5-second clip

**For each lip-sync clip:**

```
LIPSYNC [number]
Source clip: C[N]
Dialogue: "[exact text]"
Voice ID: [from roster]
Duration: [seconds]
Personalized: [yes/no — if yes, lip sync must run per-child at runtime]
```

**Skip lip sync for:** Clips with no dialogue, voice-over/narration clips (character not on screen), ambient/SFX-only clips.

### Step 7: Phase B Audio Production

**PREREQUISITE:** Phase B script must be written AND approved by Kim before starting this step. If the script doesn't exist, STOP and ask Kim: "Phase B script isn't ready. Should I write it using the phase-b-writer skill (full 9-step process), or proceed with other production steps and return to Phase B later?" For writing Phase B scripts, use the Skill tool: `skill='phase-b-writer'`.

For the meditation audio segment. This is a 5-step sub-pipeline:

**7a. Voice stem** — ElevenLabs TTS (Myrrhin voice, ID: `oR4uRy4fHDUGGISL0Rev`), render full approved Phase B script. Myrrhin tuning: Stability 65-75%, Clarity 75-85%, Style Exaggeration 15-25%.

**7b. Cue point mapping** — Run Vosk STT on generated audio to map exact timestamps for `{{BELL_CUE}}`, `{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, `{{NOTICING_CUE}}` markers embedded in the script. **Critical placement rule:** Markers go on the line BEFORE the narration they accompany. Sound starts when narrator begins that line. Getting this wrong causes 1-2 second timing errors.

**7c. breathCycle rhythms** — Assign per-section breathing patterns:
- Instruction rhythm: 4s in, 2s hold, 5s out (11s total)
- Deepening rhythm: 3s in, 1s hold, 4s out (8s total)
- Counted rhythm: matches technique-specific count patterns

**7d. SFX integration** — Layer: bell sounds, breath wind sounds, ambient texture, transition tones. Each domain has its own sonic palette (see `PHASE_B_SOUND_DESIGN_VISION_v1.md`).

**7e. Mix to flat MP3** — Levels: Voice -12 dB, breath -24 dB, transitions -18 dB, ambient -36 dB.

**Kim gate:** Listen-through of final Phase B mix. Does it FEEL right? If timing feels off, check cue point mapping (7b) first — that's the most common source of audio timing issues.

### Step 8: Assembly (ffmpeg)

Claude assembles all components:

**For each video segment (Story Scene, Resolution):**
- Concatenate clips in order with crossfade transitions (0.5-1s)
- Mix TTS dialogue audio at correct timestamps
- Layer ambient/nature SFX + background music
- Output: `M[N]_[CREATURE]_[SEGMENT].mp4` (1080p)

**For Phase B audio:**
- Output: `M[N]_PHASE_B_FINAL_MIX.mp3`

**Naming convention:** `M1_TESSA_INTRO.mp4`, `M1_TESSA_RESOLUTION.mp4`, `M1_PHASE_B_FINAL_MIX.mp3`

**Output location:** Save all production files to `Production/Event_[N]/` in the project folder.

### Step 9: Kim Final Review

Watch/listen to everything once through:
- [ ] Story scene video — characters look right, dialogue syncs, emotional flow works
- [ ] Resolution video — healing feels earned, visible magic present, runestone moment hits
- [ ] Phase B audio — pacing, warmth, breathing cues land naturally

If something's off, Kim flags the specific clip. Claude regenerates ONLY that clip. No full re-review needed.

## Buy-In Script Production

Buy-In is produced as a script only — the visual is fully automated at runtime (Guide Bird Rive animation + domain gradient background + TTS).

**Buy-In script rules:**
- Connects the Ancient Art (domain) to the child's real life
- Two patterns: Recognition ("You know when...") or Discovery ("I'm going to tell you something...")
- Language must match Phase A vocabulary (Phase A sets language, Buy-In wraps it)
- May promise an OUTCOME but must NOT reveal the MECHANISM (that's Phase A's job)
- Always ends with empowerment: "You already have this magic"
- No clinical language. Skill framed as enhancement, not repair.
- Names the application context explicitly (bedtime, a test, a fight)
- Duration: 15-30 seconds

## Phase A Design Brief

Phase A is an interactive Phaser component — this skill produces the DESIGN BRIEF, not code.

**The core rule:** Phase A shows WHAT the child will do (ingredients + outcome), not HOW. The HOW is Phase B's job. Phase A is brief and instructional: Guide Bird narrates over a character demonstration. One demo cycle, done.

**Two absolute rules:**
1. Guide Bird ALWAYS narrates — never silent during Phase A
2. The child's character performs the action, not Guide Bird

**For full Phase A design process, use the Skill tool: `skill='phase-a-designer'`.**

Output: Numbered beats (typically 3-5), metaphor map, timeout fallback, visual asset requirements.

**Phase A validation gate:** Before approving any Phase A design brief, verify: (1) One demo cycle only? (2) No sensation vocabulary ("tingling," "warmth," "calm")? (3) No vocabulary transfer cards? (4) Guide Bird narrates throughout — never silent? (5) Child's character performs the action, not Guide Bird? (6) Runtime duration under 30 seconds? If any check fails, return to the phase-a-designer skill for simplification.

## Win Sequence and Return to Map (Data Config Only)

**Win Sequence:** Standardized reusable Phaser component. Provide:
- Coin count
- Spell name
- Decoration item (name + rarity)
- Guide Bird celebration line

**Return to Map:** Three-section format:
- **TRIGGER SPRITE:** Character name, visual description, pose, location
- **MAP SPRITES:** Every visible sprite with spoken dialogue
- **MAP STATE CHANGES:** Runestones glowing, paths brightening, repositions

## Cost Model (Per Module Event)

| Component | Typical Cost |
|-----------|-------------|
| FLUX Kontext stills (8-10) | ~$0.64-0.80 |
| Animation (8-12 clips) | ~$2.50-4.00 |
| Lip sync (4-8 clips) | ~$1.00-2.00 |
| ElevenLabs TTS | Included in $22/mo plan |
| Phase B audio mixing | $0 (ffmpeg + free libraries) |
| **Total per event** | **~$4-7** |

Kim's time: ~30-45 min review spread across the session.

## Lessons Learned (Hard-Won, Do Not Ignore)

These come from actual production sessions. Each one represents a real mistake or discovery.

1. **Module scope is ONE event.** Don't try to produce multiple modules in one session. One module = one production run.
2. **Voice quality requires human selection.** ElevenLabs library voices need Kim to listen and choose. Don't auto-select voices.
3. **Emotional register is script-level.** Emotional direction tags go on every TTS line. The voice actor (TTS) needs direction, not just text.
4. **"Mindful-Nest" hyphenation is mandatory.** TTS pronounces "MindfulNest" as one garbled word. Always hyphenate in scripts.
5. **{chosenGuideName} is NOT "Pip."** It's whatever the child named their Guide Bird. In TTS scripts, it's a variable — never hardcode a name.
6. **Personalization is segment-level, not line-level.** Only the sentence with the variable gets re-rendered per child. The rest of the line is universal.
7. **The skeleton IS the screenplay.** Don't rewrite, don't summarize, don't "improve." Decompose.
8. **Screen direction is binding.** "Camera pans left" means the shot has a left pan. Period.
9. **Never cross-paste between AI generators.** A character generated in FLUX Kontext cannot be pasted into a Seedance frame. Clone/hue-shift within the same tool's output.
10. **Three Questions before Phase A/B.** If you can't answer what to show, how the creature shows it, and what technique solves it — stop.
11. **Phase A must be simple.** One demo cycle. No vocabulary cards, no sensation language, no discovery mechanics (unless discovering IS the skill shape).
12. **Phase B owns sensation language.** "Tingling," "warmth," "calm" — these words belong to Myrrhin in Phase B. Phase A uses observable language only ("The ball glows").
13. **Breathing cue placement:** Marker goes on the line BEFORE the narration it accompanies. Sound starts when narrator begins that line.
14. **Resolution has NO recap dialogue.** The child just finished Phase B. Don't summarize what they did.
15. **Magic radiates outward in resolution.** The child doesn't aim it. It flows from the child naturally.
16. **First-person camera in resolution videos.** The child is not visible — they ARE the camera.
17. **Rescue sustain is structural HOLD only.** "That's great... stay right there..." — NOT therapeutic content.
18. **Every resolution needs visible magic.** Mandatory. No exceptions.
19. **Luna's voice is animated and physical.** "Sputtering around, flapping wings, freaking out." Don't flatten Kim's writing voice for Luna.
20. **Bork's loudspeaker line is exact:** "WE DO NOT PLAY, BOBBLE-HEADED CREATURE" — not "WE ARE NOT A STORY."
21. **Video extension enables long sequences.** Don't plan each clip independently — plan chains. Feed last frame → new prompt → continuous scene.
22. **Keyframes reduce still count.** With Kling 3.0 keyframe mode, you need START and END images, not one per beat.
23. **Style is Pixar 3D.** Luminous, warm, cinematic lighting, soft materials. NOT painterly watercolor (that's superseded as of April 10, 2026).
24. **LoRA training is obsolete.** 382+ existing character images + FLUX Kontext = consistent characters without fine-tuning.
25. **Voice iteration is a human process.** Kim selects voices by listening. Claude generates test lines, Kim decides. Don't skip this gate.
26. **Opening Storybook (Event 0) is pre-produced.** No personalization, no runtime composition. Myrrhin narrator baked in. The one exception.
27. **Agent is named "Grizzle" in dialogue.** Not "the Agent" or "the King's agent."

## Sub-Skill References

For deep-dive processes, load these sub-skills via the Skill tool (do NOT attempt to read the SKILL.md files directly — the Skill tool handles loading from the correct location):

| Sub-Skill | Skill Tool Name | When to Load |
|-----------|----------------|-------------|
| Phase A Designer | `phase-a-designer` | Designing Phase A interactive demo brief |
| Phase B Writer | `phase-b-writer` | Writing Phase B meditation scripts (9-step process) |
| Scene-to-Production | `scene-to-production` | Detailed shot decomposition format |
| Video Expander | `video-expander` | Expanding thin video descriptions with camera/stage direction |
| ElevenLabs TTS | `elevenlabs-tts` | TTS generation specifics |

## Source Documents

- `Arc Skeletons/ARC_1_SKELETON_DRAFT.md` — Primary source for scene content
- `Canon/ARC_PRODUCTION_BIBLE_v2_10.md` — Module format, resolution rules, return-to-map format
- `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` — Technique definitions and clinical sources
- `Canon/TTS_PERSONALIZATION_PIPELINE_v1.md` — Segment-level personalization spec
- `video_pipeline/ELEVENLABS_VIDEO_PRODUCTION_HANDOFF_April5_2026.md` — Pipeline tools, API endpoints, cost model
- `Production/MODULE_PRODUCTION_MASTER_PLAN_v2_0.md` — 10-stage production pipeline
- `Production/MODULE_AUTHORING_GUIDE_v4_6.md` — Call/Buy-In/Resolution rules
- `Production/LESSONS_LEARNED_VIDEO_AUDIO_SESSION_April5_2026.md` — Full lessons learned
- `Production/Event_1_Plans/EVENT_1_PRODUCTION_CHECKLIST.md` — Reference production checklist

# Skill Correction Diff Report — April 11, 2026

Generated after full verified-edit protocol: Phase 1 (editing) → Phase 2 (self-verification) → Phase 3 (3 independent validators) → Phase 4 (this report)

---
## audio-producer
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/audio-producer/SKILL_backup_20260411.md"	2026-04-11 11:09:47.539370308 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/audio-producer/SKILL.md"	2026-04-11 11:19:26.459692437 -0400
@@ -45,11 +45,13 @@
 
 | Character | Voice ID | Role | Settings |
 |-----------|----------|------|----------|
-| **Myrrhin** | `oR4uRy4fHDUGGISL0Rev` | ALL Phase B narration | stability: 0.5, similarity: 0.75, style: 0.3 |
-| **Guide Bird** | `7o9pyvsN0ob5GO6LBQp6` | Call/Buy-In dialogue (NOT Phase B) | stability: 0.5, similarity: 0.75, style: 0.35 |
+| **Myrrhin** | `oR4uRy4fHDUGGISL0Rev` | ALL Phase B narration | stability: 0.30, similarity_boost: 0.80, style: 0.30 |
+| **Guide Bird** | `7o9pyvsN0ob5GO6LBQp6` | Call/Buy-In dialogue (NOT Phase B) | stability: 0.30, similarity_boost: 0.80, style: 0.30 |
 
 **API:** ElevenLabs (`api.elevenlabs.io/v1/text-to-speech/{voice_id}`). Creator plan ($22/mo). API key in `Production/API_KEYS_MASTER.md`.
 
+**Model:** `eleven_v3` for ALL characters. Low stability (0.30 = "Creative" mode) enables expressive interpretation of emotional direction tags. Per VOICE_ROSTER_LOCKED_v2 (April 6, 2026).
+
 **TTS formatting rules (critical for pacing):**
 - Counted breathing: NO punctuation between numbers → `"two three four"` not `"two. three. four."` — achieves ~1 count/second
 - Preamble replaces count one → `"Breathe in for two three four"` not `"one two three four"` — proper ratio timing
@@ -85,7 +87,7 @@
 curl -X POST "https://api.elevenlabs.io/v1/text-to-speech/oR4uRy4fHDUGGISL0Rev" \
   -H "xi-api-key: $ELEVENLABS_KEY" \
   -H "Content-Type: application/json" \
-  -d '{"text": "<cleaned script>", "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3}}' \
+  -d '{"text": "<cleaned script>", "model_id": "eleven_v3", "voice_settings": {"stability": 0.30, "similarity_boost": 0.80, "style": 0.30}}' \
   --output "m{N}_voice_stem.mp3"
 ```
 
@@ -244,7 +246,7 @@
 
 11. **Directional specificity for breath sounds.** Inhale sounds rise in pitch/volume; exhale sounds descend. They are NOT interchangeable. ElevenLabs SFX prompts must specify direction.
 
-12. **Observation modules use silence, not breathing.** M3 (Thought Clouds) uses 8s+5s+8s spacer silence with noticing tones at boundaries — no breathing cues at all. Don't force breathCycle onto non-breathing modules.
+12. **Observation modules use silence, not breathing.** M3 (Breath-Squeezers Spell) uses 8s+5s+8s spacer silence with noticing tones at boundaries — no breathing cues at all. Don't force breathCycle onto non-breathing modules.
 
 ## Reference Documents
 
@@ -279,3 +281,12 @@
 - [ ] Step 5: ffmpeg mix → `m{N}_phase_b_complete_mix.mp3`
 - [ ] Dashboard: Update audio_status, advance to listen_through
 - [ ] Kim listen-through → approval → record in prod_approvals
+
+---
+## Changelog
+### April 11, 2026 — Voice Settings Alignment
+- A1-A2: Voice table updated from 0.5/0.75/0.3 to 0.30/0.80/0.30 per VOICE_ROSTER_LOCKED_v2
+- A3: Model ID updated from eleven_multilingual_v2 to eleven_v3
+- A4: Curl example voice settings aligned to v2 standard
+- A5: Added model/settings rationale note
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md (triple-blind agent evaluation)
```

---
## scene-to-production
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/scene-to-production/SKILL_backup_20260411.md"	2026-04-11 11:09:47.548205356 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/scene-to-production/SKILL.md"	2026-04-11 11:14:00.962849288 -0400
@@ -1,7 +1,7 @@
 ---
 name: scene-to-production
 description: |
-  Convert MindfulNest skeleton scenes into production-ready video assets: shot breakdowns, Seedance/Midjourney prompts, buy-in scripts, and resolution scene specs. Use this skill whenever producing video content for MindfulNest — narrative event scenes, opening storybook pages, Guide Bird intro, creature encounters, buy-in scripts, resolution/rescue videos, or any visual production work. This skill handles ALL video segments of a module event (narrative setup, buy-in, resolution) plus non-module narrative events and arc-level scenes. Trigger on: 'video production', 'shot breakdown', 'Seedance prompt', 'Midjourney prompt', 'scene production', 'buy-in script', 'resolution video', 'narrative event', 'storyboard', 'visual production', 'camera direction', 'shot list', 'video scene', 'produce the video', 'make the video', 'screen by screen', 'screenplay', or any task involving converting skeleton text into production-ready visual assets. If you are about to produce any video or visual content for MindfulNest, load this skill FIRST.
+  Convert MindfulNest skeleton scenes into production-ready video assets: shot breakdowns, Seedance/FLUX Kontext prompts, buy-in scripts, and resolution scene specs. Use this skill whenever producing video content for MindfulNest — narrative event scenes, opening storybook pages, Guide Bird intro, creature encounters, buy-in scripts, resolution/rescue videos, or any visual production work. This skill handles ALL video segments of a module event (narrative setup, buy-in, resolution) plus non-module narrative events and arc-level scenes. Trigger on: 'video production', 'shot breakdown', 'Seedance prompt', 'FLUX Kontext prompt', 'scene production', 'buy-in script', 'resolution video', 'narrative event', 'storyboard', 'visual production', 'camera direction', 'shot list', 'video scene', 'produce the video', 'make the video', 'screen by screen', 'screenplay', or any task involving converting skeleton text into production-ready visual assets. If you are about to produce any video or visual content for MindfulNest, load this skill FIRST.
 ---
 
 # Scene-to-Production: Video Asset Production for MindfulNest
@@ -12,6 +12,8 @@
 
 **This skill does NOT generate new creative content.** Kim's skeleton IS the screenplay. The dialogue is locked under the Source Fidelity Protocol. This skill decomposes existing scenes into numbered shots and generates the technical prompts needed to produce them as video.
 
+**Pipeline position:** This skill produces the shot breakdown that feeds directly into video-producer Step 1. It is the FIRST step of the video production pipeline, not a standalone stage. The output is consumed by video-producer for still generation, animation, and assembly.
+
 ## The Three Video Segment Types
 
 Every module event contains up to three video segments (plus the interactive Phase A and audio Phase B, which are handled by separate skills):
@@ -21,7 +23,7 @@
 The creature encounter, dialogue, inscription discovery, party reactions. This is the bulk of what the skeleton describes. Runtime-composed: pre-produced visual animation with timing marks + TTS audio layered at runtime.
 
 **Source:** Arc skeleton event text (dialogue, stage directions, production notes).
-**Output:** Shot breakdown + Seedance/Midjourney prompts + TTS dialogue list with voice IDs.
+**Output:** Shot breakdown + Seedance/FLUX Kontext prompts + TTS dialogue list with voice IDs.
 
 ### 2. Buy-In
 
@@ -48,7 +50,7 @@
 Child opens eyes after Phase B and sees the result. Creature responds to magic, stone glows, inscription revealed, party reacts. 20-30 seconds. Runtime-composed (same system as story scenes).
 
 **Source:** Skeleton resolution section + Production Bible resolution rules.
-**Output:** Shot breakdown + Seedance/Midjourney prompts + TTS dialogue list.
+**Output:** Shot breakdown + Seedance/FLUX Kontext prompts + TTS dialogue list.
 
 **Resolution rules (from MODULE_AUTHORING_GUIDE §6 and Production Bible):**
 - Rescue sustain is structural HOLD only ("That's great... stay right there...") — NOT therapeutic content
@@ -106,14 +108,14 @@
 
 For each shot, generate prompts for the video pipeline:
 
-#### Midjourney Prompt (Hero Image)
+#### FLUX Kontext Prompt (Hero Image)
 
 The static image that anchors the shot. Use specific composition terminology:
 - **Shot type:** Extreme closeup, closeup, medium shot, full body, wide/establishing
 - **Framing:** Rule of thirds (dynamic), centered (formal/intimate), shallow DOF (emotional focus)
 - **Lighting:** Golden hour (safety), three-point (control), backlighting (glow), soft light (calming)
 - **Color:** Warm (comfort), cool (calm/mystery), muted (restraint), cinematic teal+orange
-- **Style reference:** "watercolor-painted, warm, hand-animated, lush and painterly, luminous" (per Opening Storybook art direction)
+- **Style reference:** "Pixar 3D, warm, hand-animated, lush and luminous" (per Opening Storybook art direction)
 
 **Be specific, not vague:**
 - BAD: "looks scared" → GOOD: "pupils dilated, body tense, shell pulled tight"
@@ -142,6 +144,17 @@
 - Whether the line contains personalization variables (runtime TTS) or is universal (pre-rendered)
 - The exact dialogue text
 
+### Multi-Character Scene Decomposition
+
+Party scenes with 3+ characters in rapid dialogue require special handling. These appear frequently in Events 3-6 as the party grows.
+
+**Decomposition rules:**
+1. **One speaker per shot.** Never generate a prompt with two characters speaking simultaneously.
+2. **Reaction shots are separate.** If Luna reacts to Tessa's line, that's a separate shot with Luna as subject.
+3. **Establish → Isolate → Reestablish.** Start with a wide establishing shot showing all characters present, then isolate to speaker close-ups, then reestablish the group at scene transitions.
+4. **Lip-sync flagging:** Any shot where a character speaks MUST be flagged `lip_sync: true` with the dialogue text and character voice ID. Silent reaction shots are `lip_sync: false`.
+5. **Max 4 speakers per scene.** If a scene has 5+ characters, identify the 2-3 primary speakers and keep others as background presence in establishing shots.
+
 ### Step 4: Produce the TTS Dialogue List
 
 Extract every dialogue line from the event. For each line:
@@ -168,7 +181,7 @@
 The complete output for one event:
 
 1. **Shot Breakdown Document** — numbered shots with all technical specs
-2. **Midjourney Prompts** — one per shot (hero images)
+2. **FLUX Kontext Prompts** — one per shot (hero images)
 3. **Seedance Prompts** — one per shot (animation/motion)
 4. **TTS Dialogue List** — all lines with voice IDs, emotional tags, pronunciation notes
 5. **Lip-Sync Flag List** — shots requiring ByteDance processing
@@ -190,7 +203,7 @@
 
 ## Character Visual Consistency
 
-The hardest production challenge is making each character look consistent across all their shots. When generating Midjourney/Seedance prompts:
+The hardest production challenge is making each character look consistent across all their shots. When generating FLUX Kontext/Seedance prompts:
 
 - Include the character's key visual identifiers in EVERY prompt (Tessa: brown shell, small, warm eyes; Luna: scholarly owl, magnifying glass, feathered; etc.)
 - Reference the same style keywords consistently across all prompts for one event
@@ -204,7 +217,7 @@
 ```
 [This Skill] Shot Breakdown + Prompts
          ↓
-[Midjourney] Hero images per shot
+[FLUX Kontext] Hero images per shot
          ↓
 [Seedance] Motion/animation from hero images
          ↓
@@ -226,7 +239,7 @@
 - [ ] Character expressions explicit in every shot (not vague)
 - [ ] Creature movement tied to their specific anatomy
 - [ ] Seedance prompts follow 6-step formula
-- [ ] Midjourney prompts use specific composition terminology
+- [ ] FLUX Kontext prompts use specific composition terminology
 - [ ] All personalized lines flagged for runtime TTS
 - [ ] Lip-sync shots flagged for ByteDance
 - [ ] Visual continuity tracked between adjacent shots
@@ -246,6 +259,18 @@
 - `Production/MODULE_VISUAL_PRODUCTION_GUIDE_v1.md` — Visual composition specs, Guide Bird Rive pipeline
 - `Production/MODULE_AUTHORING_GUIDE_v4_6.md` — Sections 2-3 (Call/Buy-In rules), Section 6 (Resolution)
 - `Canon/TTS_PERSONALIZATION_PIPELINE_v1.md` — Segment-level personalization, rendering modes
-- `Canon/ARC_PRODUCTION_BIBLE_v2_9.md` — Module format template, resolution rules, return-to-map format
+- `Canon/ARC_PRODUCTION_BIBLE_v2_10.md` — Module format template, resolution rules, return-to-map format
 - `Canon/CLAUDE_Everdale_World_Design_Bible_v13_10.md` — Character profiles, world design
 - `SCREENWRITING_QUICK_REFERENCE_v1.md` — Seedance 6-step formula, composition terminology
+
+---
+## Changelog
+
+### April 11, 2026 — Visual Pipeline Alignment
+
+- S1: Midjourney references updated to FLUX Kontext (April 10 pipeline pivot)
+- S2: Painterly art direction updated to Pixar 3D (April 10 style lock)
+- S3: ARC_PRODUCTION_BIBLE version reference updated from v2_9 to v2_10
+- S4: Added Multi-Character Scene Decomposition section with 5 decomposition rules
+- S5: Added pipeline position clarification to intro (first step of video-producer pipeline)
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md
```

---
## video-producer
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/video-producer/SKILL_backup_20260411.md"	2026-04-11 11:09:47.554010569 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/video-producer/SKILL.md"	2026-04-11 11:13:50.432770054 -0400
@@ -43,7 +43,7 @@
 The Opening Storybook (Event 0) is a pre-produced video asset — NOT runtime-composed. It uses Myrrhin's narrator voice baked in, contains NO personalization variables, and plays once on first app launch. If the event you're producing is Event 0, STOP. Do not proceed with Steps 1-9. Flag for Kim to handle separately.
 
 ### 8. No Midjourney — Use FLUX Kontext Only
-Midjourney was used for early visual development but is no longer part of the production pipeline. Use FLUX Kontext [max] via Replicate API ONLY for still generation. If FLUX Kontext API is unavailable, ask Kim before attempting any fallback tool.
+Midjourney was used for early visual development but is no longer part of the production pipeline. Use FLUX Kontext [max] via BFL API (api.bfl.ai) ONLY for still generation. If FLUX Kontext API is unavailable, ask Kim before attempting any fallback tool.
 
 ## The 7-Segment Module Event Pipeline
 
@@ -151,9 +151,9 @@
 
 ### Step 4: Generate Key Stills (FLUX Kontext)
 
-Use FLUX Kontext [max] on Replicate to generate scene stills from existing character reference images. No LoRA training needed — 382+ character images in `Production/` subfolders serve as direct references.
+Use FLUX Kontext [max] on BFL API to generate scene stills from existing character reference images. No LoRA training needed — 382+ character images in `Production/` subfolders serve as direct references.
 
-**Pipeline:** FLUX Kontext [max] via Replicate API → $0.08/image
+**Pipeline:** FLUX Kontext [max] via BFL API (api.bfl.ai) → $0.08/image
 
 **For each still, specify:**
 
@@ -184,7 +184,7 @@
 
 **If a still looks wrong:** (A) Check reference images — are they clear and representative? Swap refs and regenerate. (B) If refs are good but output is off, tighten the prompt to emphasize the specific visual detail. (C) If style is wrong (too painterly, wrong lighting), regenerate with explicit "Pixar 3D" style language. Cost: ~$0.08/still per iteration, acceptable for up to 2-3 tries per still.
 
-### Step 5: Animate Clips (Seedance 2.0 / Kling 3.0)
+### Step 5: Animate Clips (Seedance 1.5 Pro / Kling 3.0)
 
 Take approved stills, animate them with motion prompts, chain clips via video extension.
 
@@ -192,13 +192,13 @@
 
 | Use Case | Tool | Cost | Notes |
 |----------|------|------|-------|
-| Character motion, expressions, body movement | Seedance 2.0 | ~$0.05/sec | Best for creature-specific movement |
+| Character motion, expressions, body movement | Seedance 1.5 Pro | ~$0.05/sec | Best for creature-specific movement |
 | Keyframe-to-keyframe (start→end image) | Kling 3.0 | ~$0.10/sec | Fills motion between two stills |
 | Scene transitions, magic effects | Pika Pikaframes | ~$0.20/video | Good for VFX-heavy sequences |
 
-**Video extension / clip chaining:** Generate initial clip → feed last frame as input to next generation → scene continues with new motion prompt. Supported by Seedance 2.0 and Kling 3.0. This is how you build 50+ second continuous sequences from 4-5 second clips.
+**Video extension / clip chaining:** Generate initial clip → feed last frame as input to next generation → scene continues with new motion prompt. Supported by Seedance 1.5 Pro and Kling 3.0. This is how you build 50+ second continuous sequences from 4-5 second clips.
 
-**Tool consistency rule:** Once you select a tool for a video segment (e.g., Seedance 2.0 for Intro), use the SAME tool for all clips in that segment. Mixing tools within a segment creates style inconsistency. If a tool's API fails mid-segment: (A) retry after 60 seconds, (B) if still unavailable, ask Kim whether to wait, switch tools for the entire segment (regenerating earlier clips), or move on to another step.
+**Tool consistency rule:** Once you select a tool for a video segment (e.g., Seedance 1.5 Pro for Intro), use the SAME tool for all clips in that segment. Mixing tools within a segment creates style inconsistency. If a tool's API fails mid-segment: (A) retry after 60 seconds, (B) if still unavailable, ask Kim whether to wait, switch tools for the entire segment (regenerating earlier clips), or move on to another step.
 
 **For each animation clip:**
 
@@ -207,7 +207,7 @@
 Input: [Still number or "extend from C[N] last frame"]
 Motion prompt: [60-100 words using 6-step formula]
 Duration: [estimated seconds]
-Tool: [Seedance 2.0 / Kling 3.0 / Pika]
+Tool: [Seedance 1.5 Pro / Kling 3.0 / Pika]
 Dialogue overlay: [which TTS line plays during this clip, or "none"]
 Cost estimate: [$X.XX]
 ```
@@ -243,24 +243,11 @@
 
 ### Step 7: Phase B Audio Production
 
-**PREREQUISITE:** Phase B script must be written AND approved by Kim before starting this step. If the script doesn't exist, STOP and ask Kim: "Phase B script isn't ready. Should I write it using the phase-b-writer skill (full 9-step process), or proceed with other production steps and return to Phase B later?" For writing Phase B scripts, use the Skill tool: `skill='phase-b-writer'`.
+**Invoke the audio-producer skill for this step.** The full Phase B audio pipeline (TTS voice stem → Vosk STT cue extraction → breathCycle rhythms → ffmpeg mixing) is documented in `audio-producer/SKILL.md`.
 
-For the meditation audio segment. This is a 5-step sub-pipeline:
+**Quick reference:** Myrrhin voice (oR4uRy4fHDUGGISL0Rev), eleven_v3 model, stability 0.30/similarity 0.80/style 0.30. See audio-producer skill for complete pipeline, asset library, and mixing recipes.
 
-**7a. Voice stem** — ElevenLabs TTS (Myrrhin voice, ID: `oR4uRy4fHDUGGISL0Rev`), render full approved Phase B script. Myrrhin tuning: Stability 65-75%, Clarity 75-85%, Style Exaggeration 15-25%.
-
-**7b. Cue point mapping** — Run Vosk STT on generated audio to map exact timestamps for `{{BELL_CUE}}`, `{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, `{{NOTICING_CUE}}` markers embedded in the script. **Critical placement rule:** Markers go on the line BEFORE the narration they accompany. Sound starts when narrator begins that line. Getting this wrong causes 1-2 second timing errors.
-
-**7c. breathCycle rhythms** — Assign per-section breathing patterns:
-- Instruction rhythm: 4s in, 2s hold, 5s out (11s total)
-- Deepening rhythm: 3s in, 1s hold, 4s out (8s total)
-- Counted rhythm: matches technique-specific count patterns
-
-**7d. SFX integration** — Layer: bell sounds, breath wind sounds, ambient texture, transition tones. Each domain has its own sonic palette (see `PHASE_B_SOUND_DESIGN_VISION_v1.md`).
-
-**7e. Mix to flat MP3** — Levels: Voice -12 dB, breath -24 dB, transitions -18 dB, ambient -36 dB.
-
-**Kim gate:** Listen-through of final Phase B mix. Does it FEEL right? If timing feels off, check cue point mapping (7b) first — that's the most common source of audio timing issues.
+**Dashboard update after audio:** Set `audio_status = 'mix_complete'` and advance to `listen_through` stage via dashboard-ops skill.
 
 ### Step 8: Assembly (ffmpeg)
 
@@ -387,6 +374,7 @@
 | Scene-to-Production | `scene-to-production` | Detailed shot decomposition format |
 | Video Expander | `video-expander` | Expanding thin video descriptions with camera/stage direction |
 | ElevenLabs TTS | `elevenlabs-tts` | TTS generation specifics |
+| audio-producer | `audio-producer` | Phase B audio pipeline (TTS → cue extraction → mixing) |
 
 ## Source Documents
 
@@ -399,3 +387,14 @@
 - `Production/MODULE_AUTHORING_GUIDE_v4_6.md` — Call/Buy-In/Resolution rules
 - `Production/LESSONS_LEARNED_VIDEO_AUDIO_SESSION_April5_2026.md` — Full lessons learned
 - `Production/Event_1_Plans/EVENT_1_PRODUCTION_CHECKLIST.md` — Reference production checklist
+
+---
+
+## Changelog
+
+### April 11, 2026 — Pipeline Alignment
+- V1: Seedance 2.0 → Seedance 1.5 Pro (current WaveSpeed API version)
+- V2: FLUX Kontext via Replicate → via BFL API (api.bfl.ai)
+- V3: Inline Phase B audio replaced with audio-producer skill pointer
+- V4: audio-producer added to Sub-Skill References table
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md
```

---
## elevenlabs-tts
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/elevenlabs-tts/SKILL_backup_20260411.md"	2026-04-11 11:09:47.545503892 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/elevenlabs-tts/SKILL.md"	2026-04-11 11:12:41.547863186 -0400
@@ -25,6 +25,21 @@
 - API key is in `Production/API_KEYS_MASTER.md`
 - Low stability (0.30 = "Creative" mode) gives the model room to interpret emotional tags expressively
 
+## ElevenLabs Creator Plan Quota
+
+**Plan:** Creator ($22/mo). Monitor character usage to avoid hitting the cap mid-production.
+
+**Tracking:** Before each batch TTS run, check remaining quota:
+```bash
+curl -s "https://api.elevenlabs.io/v1/user/subscription" \
+  -H "xi-api-key: $ELEVENLABS_KEY" \
+  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Used: {d[\"character_count\"]}/{d[\"character_limit\"]} ({d[\"character_count\"]/d[\"character_limit\"]*100:.1f}%)')"
+```
+
+**Per-module estimate:** ~500-1500 characters per voice stem (depends on script length). Budget ~2000 chars/module including iteration variants.
+
+**Warning threshold:** If usage exceeds 80%, alert Kim before proceeding. Consider waiting for monthly reset or upgrading plan.
+
 ## Emotional Direction Tags
 
 All dialogue MUST be scripted with inline emotional direction tags before TTS generation. Tags go in square brackets before the text they affect:
@@ -55,6 +70,18 @@
 | Caution | `[cautious]`, `[uneasy]`, `[slightly wary]`, `[careful, compassionate]` |
 | Fear | `[tiny, nervous]`, `[barely audible from inside the hole]`, `[scared but determined]` |
 
+## Error Handling & Retry Logic
+
+| Error | Response | Action |
+|-------|----------|--------|
+| 429 Too Many Requests | Rate limited | Exponential backoff: wait 2s, 4s, 8s, max 3 retries |
+| 500/503 Server Error | ElevenLabs outage | Wait 60s, retry once. If still failing, alert Kim. |
+| Malformed audio response | Truncated/corrupt file | Check file size (>10KB expected). Retry up to 2x. |
+| Voice ID not found | Wrong voice_id | Verify against VOICE_ROSTER_LOCKED_v2.md |
+| Character quota exceeded | Monthly limit hit | STOP. Alert Kim. Do NOT retry. |
+
+**Batch generation:** When generating multiple lines, process sequentially with 1s delay between calls. Do not parallelize — ElevenLabs rate limits are per-second.
+
 ## Pronunciation Rules
 
 **CRITICAL:** Before sending ANY text to ElevenLabs, apply these substitutions:
@@ -82,6 +109,18 @@
   - `{childPronounObject}` → "her"
   - `{childPronounPossessive}` → "her"
 
+## Personalization Variable Sentence Splitting
+
+For per-child TTS rendering, identify which sentences contain personalization variables (`{childName}`, `{guideName}`, `{therapistName}`):
+
+1. **Scan script text** for `{variableName}` patterns
+2. **Split sentences** into two queues:
+   - **Universal queue:** Sentences with NO variables — render ONCE, shared across all children
+   - **Per-child queue:** Sentences WITH variables — render per-child after variable substitution
+3. **Cost optimization:** Only per-child sentences cost per child. Universal sentences are a one-time cost.
+
+See `TTS_PERSONALIZATION_PIPELINE_v1.md` for the full rendering architecture and cost model.
+
 ## Pacing Rules
 
 - Guide Bird lines need `[pause]` tags between sentences for natural breathing room
@@ -112,6 +151,24 @@
 
 All dialogue text is Kim's authored content — preserved VERBATIM. Only emotional direction tags `[in brackets]` are added. Never rewrite, paraphrase, or "improve" Kim's dialogue. If a line sounds wrong, flag it for Kim rather than changing it.
 
+## Voice Stem Assembly
+
+Individual TTS line files must be concatenated into a single voice stem before handoff to audio-producer:
+
+```bash
+# Concatenate individual lines into one voice stem
+ffmpeg -f concat -safe 0 -i filelist.txt -c copy m{N}_voice_stem.mp3
+```
+
+Where `filelist.txt` contains:
+```
+file 'line_001.mp3'
+file 'line_002.mp3'
+...
+```
+
+**Output:** Single `m{N}_voice_stem.mp3` file — this is what audio-producer expects as input for Step 2 (Vosk cue extraction).
+
 ## Batch Generation Pattern
 
 For generating multiple lines efficiently:
@@ -131,3 +188,13 @@
 - [ ] Update the voice roster if any voices, settings, or rules changed
 - [ ] Log any dialogue changes in the roster's Dialogue Changes Log
 - [ ] Flag any lines that sound wrong for Kim's review
+
+---
+## Changelog
+### April 11, 2026 — Production Readiness
+- E1: Added Creator Plan quota tracking
+- E2: Added error handling and retry logic
+- E3: Added voice stem concatenation/assembly step
+- E4: Added personalization variable sentence splitting
+- E5: Model ID aligned to eleven_v3 per VOICE_ROSTER_LOCKED_v2
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md
```

---
## phase-a-designer
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/phase-a-designer/SKILL_backup_20260411.md"	2026-04-11 11:09:47.551366772 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/phase-a-designer/SKILL.md"	2026-04-11 11:13:25.682281444 -0400
@@ -94,7 +94,7 @@
 
 **Cue 3: Bridge to Phase B.** Prefer a question: "Ready to try it for real?" (5 words) beats a 3-sentence recap. One bridge, then done.
 
-**Cue count is variable:** Simple watch-only demo: 3 cues. Richer interactive demo: 4-6 cues. NO sequential round cues (cues like "after_breath_1" imply repetition, which is Phase B thinking).
+**Cue count is variable:** Simple watch-only demo: 3 cues. Richer interactive demo: 3-6 cues (match approved module complexity — M4 uses 3 beats, others may use more). NO sequential round cues (cues like "after_breath_1" imply repetition, which is Phase B thinking).
 
 ### Step 3b: Consequence Design
 
@@ -205,15 +205,34 @@
 5. **Checklist verification** (all items checked above)
 
 DO NOT produce:
-- phaseAFlow JSON (that's an implementation detail, not a design step)
-- Interaction sequences (beats contain this)
+- Interaction sequences beyond the beat sheet (beats contain this)
 - Visual rules (use the section above)
 - Candidate metaphors or discovery scaffolding
 
+**JSON assembly** is a SEPARATE sub-step after beat sheet approval. This skill produces the beat sheet design; JSON build follows as Stage 4b after Kim approves the beat sheet. See MODULE_PRODUCTION_MASTER_PLAN for Stage 4 details.
+
 Deliver only what the child will actually see and do.
 
+## JSON Build Handoff (Stage 4b)
+
+After Kim approves the Phase A beat sheet:
+1. Beat sheet design (this skill's output) → Kim approval gate
+2. JSON assembly: Convert approved beat sheet into `phaseAFlow` JSON structure
+3. Schema validation: Verify against MODULE_JSON_SCHEMA_GUARDRAILS
+4. Integration: JSON is consumed by the app runtime for Phase A interactive scenes
+
+**Note:** JSON assembly may require a separate skill or manual step. This skill's scope ends at beat sheet approval.
+
 ## Source Documents
 
 - `Production/MODULE_AUTHORING_GUIDE_v4_6.md` — §4.1-4.12 (primary authority for Phase A rules)
 - `Production/M4_PHASE_A_BEAT_SHEET_v1.md` — Reference implementation (canonical example)
 - `Canon/ARC_PRODUCTION_BIBLE_v2_10.md` — Module format
+
+---
+## Changelog
+### April 11, 2026 — Pipeline Gap Fix
+- P1: Removed JSON prohibition; clarified Stage 4a/4b split
+- P2: Added JSON Build Handoff section
+- P3: Cue count guidance widened from 4-6 to 3-6
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md
```

---
## phase-b-writer
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/phase-b-writer/SKILL_backup_20260411.md"	2026-04-11 11:09:47.556431703 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/phase-b-writer/SKILL.md"	2026-04-11 11:14:00.713338223 -0400
@@ -283,6 +283,10 @@
 - No DEEPENING section (counting occupies attention continuously)
 - Both cycles structurally identical
 
+## Myrrhin Voice Configuration
+
+**Myrrhin Voice ID:** `oR4uRy4fHDUGGISL0Rev` (ElevenLabs, eleven_v3 model). All Phase B meditations use Myrrhin's narrator voice. Settings: stability 0.30, similarity_boost 0.80, style 0.30 per VOICE_ROSTER_LOCKED_v2.
+
 ## breathCycle Audio Rules
 
 From Phase B Audio Engine Architecture v1.1:
@@ -324,6 +328,8 @@
 8. **Any Mismatch Flags**
 9. **Audio Cue Markers** (after Kim approval only)
 
+**audioProductionType:** One of: `breathing`, `observation`, `compassion`, `tension_arc`, `containment`, `body_awareness`. This field tells the audio-producer skill which cue pattern and ffmpeg recipe to apply. Inferred from the module's technique, not its narrative domain.
+
 ## Source Documents
 
 - `Production/PHASE_B_PRODUCTION_PROCESS_v1_2.md` — The 9-step process (primary authority)
@@ -333,3 +339,10 @@
 - `Production/MODULE_AUTHORING_GUIDE_v4_6.md` — Section 5 + Child Experience Rule
 - `Production/MODULE_PRODUCTION_MASTER_PLAN_v2_0.md` — Pipeline stages 5-6
 - `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` — Technique definitions, clinical sources
+
+---
+## Changelog
+### April 11, 2026 — Audio Handoff Improvements
+- PB1: Added audioProductionType output field
+- PB2: Added Myrrhin voice ID reference
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md
```

---
## dashboard-ops
```diff
--- "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/dashboard-ops/SKILL_backup_20260411.md"	2026-04-11 11:09:47.542797803 -0400
+++ "/sessions/eager-affectionate-noether/mnt/Claude Mindfulnest Project Files/.claude/skills/dashboard-ops/SKILL.md"	2026-04-11 11:13:16.331625119 -0400
@@ -68,6 +68,10 @@
 |-------|------|----------------|---------------|
 | `current_stage` | text (FK → prod_stages.stage_key) | `intake`, `kim_seeds`, `phase_b`, `phase_a_json`, `audio`, `listen_through` | Which pipeline stage the module is in |
 | `stage_status` | PostgreSQL enum `prod_stage_status` | `not_started`, `in_progress`, `blocked`, `completed` | Status within that stage |
+| `audio_status` | text | `not_started`, `voice_stem`, `cue_mapped`, `mix_complete`, `approved` | Tracks audio production sub-status |
+| `visual_status` | text | `not_started`, `stills_done`, `animated`, `lip_synced`, `composited` | Tracks visual production sub-status |
+
+**Added April 11, 2026.** The `audio_status` and `visual_status` fields provide granular tracking within the `audio` stage. Updated by audio-producer and video-producer skills respectively.
 
 **The enum is enforced at the database level.** If you try to set `stage_status` to anything other than those 4 values (like `phase_b_approved`), PostgreSQL will reject the write with an "invalid input value for enum" error.
 
@@ -148,6 +152,31 @@
 2. Record the approval in `prod_approvals` first
 3. Then advance the module
 
+### Hard Gate Verification (MANDATORY)
+
+Before advancing a module past a hard gate (`phase_b` or `listen_through`), you MUST verify that an approval record exists:
+
+```bash
+# Check for approval before advancing past hard gate
+APPROVAL=$(curl -s "$BASE/items/prod_approvals?filter[module_id][_eq]=MODULE_ID&filter[gate_type][_eq]=GATE_TYPE&filter[status][_eq]=approved" \
+  -H "Authorization: Bearer $TOKEN" \
+  | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print('APPROVED' if len(d)>0 else 'NO_APPROVAL')")
+
+if [ "$APPROVAL" != "APPROVED" ]; then
+  echo "BLOCKED: No approval record found. Cannot advance past hard gate."
+  echo "Ask Kim for explicit approval, then record it with POST to prod_approvals."
+  exit 1
+fi
+```
+
+**Enforcement rule:** If no approval record exists for the module + gate combination, the PATCH to advance the module MUST be rejected. This is a production-stopping safety check. Never skip it.
+
+**Sequence:** 
+1. Kim says "approved" in conversation
+2. POST to `prod_approvals` (see Creating Records section)
+3. Verify with GET above
+4. Only THEN advance the module with PATCH
+
 ### Creating Records
 
 ```bash
@@ -170,6 +199,24 @@
   -d '{"module_id": ID, "gate_type": "phase_b|listen_through", "status": "approved", "approved_by": "kim"}'
 ```
 
+### Creating a New Module Record
+
+```bash
+curl -s -X POST "$BASE/items/prod_modules" \
+  -H "Authorization: Bearer $TOKEN" \
+  -H "Content-Type: application/json" \
+  -d '{
+    "m_number": M_NUM,
+    "creature_name": "CREATURE",
+    "spell_name": "SPELL_NAME",
+    "arc_number": ARC_NUM,
+    "module_index": INDEX,
+    "current_stage": "intake",
+    "stage_status": "not_started",
+    "notes": "Created for Arc N production"
+  }'
+```
+
 ### Resolving a Blocker
 
 ```bash
@@ -201,6 +248,24 @@
 
 ---
 
+## Cross-Skill Handoffs
+
+Other production skills update dashboard state through this skill's API patterns:
+
+| Skill | When | Dashboard Action |
+|-------|------|-----------------|
+| **phase-b-writer** | Script draft complete | Set `stage_status = 'completed'` on `phase_b`. Record approval in `prod_approvals` after Kim review. |
+| **audio-producer** | Voice stem generated | Set `audio_status = 'voice_stem'` |
+| **audio-producer** | Mix complete | Set `audio_status = 'mix_complete'`. Advance to `listen_through`. |
+| **video-producer** | Stills generated | Set `visual_status = 'stills_done'` |
+| **video-producer** | Animation complete | Set `visual_status = 'animated'` |
+| **video-producer** | Lip sync complete | Set `visual_status = 'lip_synced'` |
+| **phase-a-designer** | Beat sheet approved | Advance to `phase_a_json` stage |
+
+**Rule:** Always log transitions to `prod_activity_log`. The dashboard is the single source of truth for production state.
+
+---
+
 ## Operational Rules
 
 1. **Read API_KEYS_MASTER.md for credentials every time.** Never hardcode.
@@ -237,3 +302,14 @@
 **MCP Server:** `@railway/mcp-server` — can be installed as a plugin for native integration.
 
 As of April 10, 2026: Railway API token has NOT been created yet. Directus API works independently of Railway — Railway access is only needed for infrastructure changes.
+
+---
+
+## Changelog
+
+### April 11, 2026 — Hard Gate Enforcement + New Fields
+- D1: Added hard gate verification curl pattern with enforcement rule
+- D2: Added audio_status and visual_status fields to schema reference
+- D3: Added POST operation for creating new module records
+- D4: Added cross-skill integration guide
+- Source: SKILL_CORRECTION_MASTER_PLAN_v1.md
```


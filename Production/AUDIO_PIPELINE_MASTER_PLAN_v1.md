# AUDIO PIPELINE MASTER PLAN v1

**Date:** March 27, 2026
**Status:** COMPLETE — Production-ready pipeline specification
**Goal:** Kim's role = APPROVE/REJECT only. Never producing, editing, mixing, or manually timing anything.
**Companion to:** VISUAL_PIPELINE_MASTER_PLAN_v5.md

---

## TABLE OF CONTENTS

1. [Week-Estimate Methodology (Why Timelines Look the Way They Do)](#1-week-estimate-methodology)
2. [Audio Pipeline Overview](#2-audio-pipeline-overview)
3. [Tools & Costs](#3-tools--costs)
4. [Complete Step-by-Step Audit](#4-complete-step-by-step-audit)
5. [Phase B Meditation Audio Pipeline (The Big One)](#5-phase-b-meditation-audio-pipeline)
6. [Narrative Event Audio Pipeline](#6-narrative-event-audio-pipeline)
7. [TTS Personalization Pipeline](#7-tts-personalization-pipeline)
8. [Sound Library Build (One-Time)](#8-sound-library-build-one-time)
9. [Guide Bird Dialogue Pipeline](#9-guide-bird-dialogue-pipeline)
10. [Map & UI Audio](#10-map--ui-audio)
11. [Dashboard Audio (Separate Pipeline)](#11-dashboard-audio)
12. [Timeline & Prompt Estimates](#12-timeline--prompt-estimates)
13. [Kim's Total Time Commitment](#13-kims-total-time-commitment)
14. [Risk Register](#14-risk-register)
15. [Quality Benchmarks](#15-quality-benchmarks)
16. [COPPA & Compliance](#16-coppa--compliance)
17. [Open Questions](#17-open-questions)

---

## 1. WEEK-ESTIMATE METHODOLOGY

**Kim asked:** "I'm not sure why you are arranging these steps in the week format that you are, how are you deciding how many of these steps fit into a week? Is it totally random?"

**Honest answer:** It's not random, but the logic was poorly communicated. Here's what actually drives the week boundaries:

### What determines a "week" boundary

**Dependency gates, not work volume.** A week boundary appears wherever Kim needs to approve something before the next batch of work can start. The work WITHIN a week is all stuff Claude can do autonomously. The gap BETWEEN weeks is Kim's review + approval.

Concrete example:
- **Week 1:** Claude generates voice candidates, ambient bed candidates, functional sound candidates. All parallelizable. Takes ~20-40 prompts, maybe 2 hours of processing wait.
- **GAP:** Kim listens to everything and says "this voice yes, this bed no, regenerate." This takes Kim 30-60 minutes but might not happen until the next day or the day after.
- **Week 2:** Claude takes Kim's feedback, regenerates rejected items, does the assembly/mixing. Again ~15-30 prompts.
- **GAP:** Kim listens to assembled mixes. Approves or requests changes.

**So "weeks" really mean "approval cycles."** If Kim reviews same-day, a "week" could collapse to a single day. If Kim reviews once a week, it's literally a week. The calendar time is entirely determined by Kim's review cadence, not Claude's work volume.

### Why the visual pipeline showed 28 weeks

The visual pipeline has MORE dependency gates because outputs from one phase feed into the next (you can't animate a creature that hasn't been drawn, you can't rig what hasn't been approved). Audio has FEWER dependency gates because most audio assets are independent of each other.

### This document's approach

Instead of "Week X" framing, this document uses **Phase + Approval Gate** framing:
- **Phase** = a batch of work Claude does autonomously
- **🚪 Approval Gate** = Kim reviews, approves/rejects, provides feedback
- **Calendar time** = entirely dependent on how fast Kim reviews

---

## 2. AUDIO PIPELINE OVERVIEW

MindfulNest has **5 distinct audio streams**, each with different production requirements:

| Stream | What It Is | Modules Affected | Unique per Child? |
|--------|-----------|-----------------|-------------------|
| **Phase B Meditation** | Voice stem + ambient bed + functional sounds, mixed | All 54 modules (6 per arc × 9 arcs) | Partially (personalized voice stem) |
| **Narrative Events** | Character dialogue (Guide Bird, creatures, Oliver, etc.) | 54+ narrative events across all arcs | Yes ({childName} in dialogue) |
| **TTS Personalization** | Per-child rendering of variable-containing lines | All dialogue with {childName} etc. | Yes (that's the point) |
| **Guide Bird AI Dialogue** | Haiku-generated text → TTS | 6 fields per module × 54 modules | Yes (contains {childName}) |
| **Map/UI/SFX** | Tap responses, UI sounds, transition effects | Global + per-creature | Mostly universal |

**The Phase B meditation pipeline is by far the most complex.** It's also the most automated. The other 4 streams are simpler.

---

## 3. TOOLS & COSTS

| Tool | Purpose | Cost | Required? |
|------|---------|------|-----------|
| **ElevenLabs** (Creator plan) | TTS for all character voices + SFX generation for ambient beds, breath sounds, functional sounds | $22/mo | YES — core of entire pipeline |
| **Vosk** (open source) | Offline speech-to-text for cue point extraction | $0 | YES — proven in M1/M2 production |
| **ffmpeg** | Audio mixing, format conversion | $0 (pre-installed) | YES |
| **Python** (pydub, wave) | Mix scripting, cue point automation | $0 | YES |
| **Claude** | Script generation, JSON config generation, pipeline orchestration | Already paying | YES |

**Total monthly cost during active production:** $22/mo (ElevenLabs Creator)
**Total one-time cost:** $0 (all tools are free or already subscribed)

### Budget comparison to existing docs

The PHASE_B_SOUND_PRODUCTION_BRIEF estimated $1,300–$4,200 total, which included $1,000–$2,500 for commissioned ambient beds and $200–$600 for commissioned functional sounds/mixing. **This plan eliminates all commissioned work.** ElevenLabs SFX v2 generates ambient beds and functional sounds directly. Claude handles all mixing via ffmpeg scripts. The only cost is the ElevenLabs subscription.

**Revised total production budget: ~$66–$132** (3–6 months of ElevenLabs Creator at $22/mo).

---

## 4. COMPLETE STEP-BY-STEP AUDIT

### Legend

- 🟢 **FULLY AUTOMATED** — Claude does it, no human input needed
- 🟡 **APPROVE ONLY** — Claude produces it, Kim listens and says yes/no
- 🔴 **HUMAN REQUIRED** — Someone other than Claude must do actual work

**Result: This pipeline contains ZERO 🔴 items.** Every step is either fully automated (🟢) or approve-only (🟡). The 🔴 category is defined for completeness and to match the visual pipeline audit format, but the audio pipeline achieves the goal: Kim never produces, edits, mixes, or manually times anything. The only contingency that could introduce 🔴 work is commissioning an ambient music producer if ElevenLabs SFX v2 can't produce acceptable beds (see Risk Register §14).

---

### Stream 1: Phase B Meditation Audio (per module)

| # | Step | Level | Who | Prompts | Kim Time | Notes |
|---|------|-------|-----|---------|----------|-------|
| 1 | Write Phase B meditation script | 🟢 | Claude | 2–3 | 0 | From locked arc skeleton + technique inventory. Includes {{INHALE_CUE}} markers. |
| 2 | Review/approve script | 🟡 | Kim | 0 | 5 min | Read-through. Approve or mark changes. |
| 3 | Generate voice stem (ElevenLabs TTS) | 🟢 | Claude | 1 | 0 | Myrrhin voice (locked ID: oR4uRy4fHDUGGISL0Rev). Generate 3 takes, auto-select best by duration match. |
| 4 | Review voice stem | 🟡 | Kim | 0 | 2 min | Listen to selected take. "Yes" or "regenerate." |
| 5 | Extract cue points (Vosk STT) | 🟢 | Claude | 1 | 0 | Word-level timestamps + cue marker disambiguation. Zero human timing input. Proven pipeline. |
| 6 | Assign breathCycle rhythms | 🟢 | Claude | 1 | 0 | Deterministic rules from script section → rhythm table. Automatic overlap check. |
| 7 | Generate phaseBMixConfig JSON | 🟢 | Claude | 1 | 0 | Complete cuePoints[] array + domain + durations. Feeds runtime player. |
| 8 | Mix to flat MP3 (ffmpeg) | 🟢 | Claude | 1 | 0 | Voice stem + shared library sounds + cue points → single 192kbps MP3. Proven script from M1/M2. |
| 9 | Final listen-through | 🟡 | Kim | 0 | 2 min | Play the mixed MP3. "Sounds right" or "the exhale tone is too loud at cycle 3." |
| 10 | Generate per-child personalized stem | 🟢 | Claude | 1 | 0 | Replace {childName} in opening/closing lines → ElevenLabs → cache. Cue points stay universal (recommended approach from TTS Pipeline spec §6.4). |

**Per-module totals:**
- Claude prompts: ~8–10
- Kim time: ~9 minutes (script review + voice review + final listen)
- Calendar time: 1 day if Kim reviews same-day

**For all 54 modules:**
- Claude prompts: ~430–540
- Kim time: ~8 hours total (spread across production)
- Processing wait: ~4–6 hours total compute time

---

### Stream 2: Sound Library Build (one-time)

| # | Step | Level | Who | Prompts | Kim Time | Notes |
|---|------|-------|-----|---------|----------|-------|
| 1 | Generate transition bell candidates | 🟢 | Claude | 3–5 | 0 | ElevenLabs SFX. 10+ candidates, auto-filter by duration (3–5s) and frequency content. |
| 2 | Select transition bell | 🟡 | Kim | 0 | 5 min | Listen to top 3 candidates. Pick one. Used identically in ALL modules. |
| 3 | Generate landing shimmer base + 6 domain tints | 🟢 | Claude | 3–5 | 0 | Base shimmer + EQ/filtering per domain. |
| 4 | Approve shimmer set | 🟡 | Kim | 0 | 5 min | Listen to 6 variants. Approve or request "warmer" / "brighter." |
| 5 | Generate breath sounds (inhale/exhale/hold) | 🟢 | Claude | 5–8 | 0 | ElevenLabs SFX v2 with directional prompts. 10+ candidates each, verify direction by ear (automated spectral analysis for rising vs. falling energy). |
| 6 | Approve breath sound pair | 🟡 | Kim | 0 | 3 min | Listen to inhale/exhale pair together. |
| 7 | Generate exhale shimmers (3 progressive variants) | 🟢 | Claude | 2–3 | 0 | Subtle → medium → pronounced crystalline cascade. |
| 8 | Generate 6 domain ambient beds | 🟢 | Claude | 10–15 | 0 | ElevenLabs SFX v2 with looping ON. 10+ candidates per domain, filter for: no melody, no percussion, seamless loop, warm. |
| 9 | Approve ambient beds | 🟡 | Kim | 0 | 10 min | Listen to 6 beds (~30s each). Each bed defines the sonic identity of its domain forever. |
| 10 | Generate specialty sounds (noticing tone, bowl strike, warmth tones, tension arc, squeeze/release, step markers, containment) | 🟢 | Claude | 8–12 | 0 | 15 additional library files per the Sound Library Manifest. |
| 11 | Approve specialty sounds | 🟡 | Kim | 0 | 8 min | Listen to ~15 sounds. Most are 1–3 seconds. Quick passes. |

**Sound library totals:**
- Claude prompts: ~31–48
- Kim time: ~31 minutes (one dedicated "Sound Library Review" session)
- Output: 33 shared audio files, used across ALL 54 modules forever
- Calendar time: 1–2 days

---

### Stream 3: Narrative Event Audio (per event)

| # | Step | Level | Who | Prompts | Kim Time | Notes |
|---|------|-------|-----|---------|----------|-------|
| 1 | Dialogue text exists in arc skeleton | 🟢 | Already done | 0 | 0 | Kim's authored dialogue is the source. |
| 2 | Assign voice IDs to each line | 🟢 | Claude | 1 | 0 | Guide Bird, creature, Oliver, etc. Deterministic from character name in stage directions. |
| 3 | Generate TTS for each line | 🟢 | Claude | 1–2 | 0 | ElevenLabs TTS per voice profile. Universal lines (no {childName}): render once. Variable lines: template stored for per-child rendering. |
| 4 | Generate animation timing marks from TTS durations | 🟢 | Claude | 1 | 0 | Each dialogue line = one animation beat. TTS output duration drives pacing. |
| 5 | Review narrative event audio | 🟡 | Kim | 0 | 3–5 min | Listen to full event dialogue sequence. "Voices sound right" or "Luna needs more energy." |

**Per-event totals:**
- Claude prompts: 3–4
- Kim time: 3–5 min
- For ~54 narrative events across all arcs: ~160–215 prompts, ~3–4.5 hours Kim time

---

### Stream 4: Guide Bird AI Dialogue (per module)

| # | Step | Level | Who | Prompts | Kim Time | Notes |
|---|------|-------|-----|---------|----------|-------|
| 1 | Haiku generates 6 text fields (Call, Buy-In, Rescue Transition, Win, Nudge, Bridge) | 🟢 | Claude (Haiku) | 1 | 0 | System prompt includes childName and guideName. |
| 2 | TTS render each field | 🟢 | Claude | 1 | 0 | Guide Bird voice profile. Short lines (~10–30 words each). |
| 3 | Cache audio per child | 🟢 | Claude | 0 | 0 | Pre-cached at module unlock. |

**Per-module totals:**
- Claude prompts: 2
- Kim time: 0 (Guide Bird lines are AI-generated by design — no human review per-child)
- Kim reviews the Haiku system prompt ONCE: 🟡 ~15 min
- For all 54 modules: ~108 prompts, 0 ongoing Kim time

---

### Stream 5: Map Sprite & UI Audio

| # | Step | Level | Who | Prompts | Kim Time | Notes |
|---|------|-------|-----|---------|----------|-------|
| 1 | Write map sprite tap lines | 🟢 | Claude | 1–2 per creature | 0 | Short (1–2 sentences). From personality in Bible. |
| 2 | Review tap lines | 🟡 | Kim | 0 | 10 min total | All creatures' lines in one batch. |
| 3 | TTS render tap lines | 🟢 | Claude | 1 per creature | 0 | Each creature's voice profile. |
| 4 | Generate UI sounds (tap, swipe, unlock, coin collect, etc.) | 🟢 | Claude | 3–5 | 0 | ElevenLabs SFX v2 or free sound libraries (Freesound.org). |
| 5 | Approve UI sound set | 🟡 | Kim | 0 | 5 min | Listen to ~10 UI sounds. |
| 6 | Tomorrow Hook TTS | 🟢 | Claude | 1 per module | 0 | Guide Bird voice. ~10 words each. Runtime TTS (Mode 2). |

**Totals:**
- Claude prompts: ~20–30 (one-time for full game)
- Kim time: ~15 min (one-time review)

---

### Stream 6: Parent Dashboard Audio

| # | Step | Level | Who | Prompts | Kim Time | Notes |
|---|------|-------|-----|---------|----------|-------|
| 1 | "Play Spell" button streams child's pre-rendered Phase B audio | 🟢 | Already built | 0 | 0 | Reuses per-child Phase B stems. No additional TTS cost. |

**Totals:** $0 additional cost, 0 additional work. This is a playback feature, not a production pipeline.

---

## 5. PHASE B MEDITATION AUDIO PIPELINE — DEEP DIVE

This is the most complex audio stream. Here's the full automation flow, proven in M1 and M2 production:

```
┌─────────────────────────────────────────────────────────────────┐
│ INPUT: Approved Phase B script WITH {{CUE_MARKERS}}            │
│                                                                 │
│ Step 1: Strip cue markers → send clean text to ElevenLabs TTS  │
│         🟢 AUTOMATED (string processing)                       │
│                                                                 │
│ Step 2: TTS generation → voice stem MP3                        │
│         🟢 AUTOMATED (ElevenLabs API, ~$0.50/module)           │
│                                                                 │
│ Step 3: Vosk STT → word-level timestamps                       │
│         🟢 AUTOMATED (offline, free, ~10s processing)          │
│                                                                 │
│ Step 4: Cue marker disambiguation → exact cue timestamps       │
│         🟢 AUTOMATED (pattern match Nth occurrence per markers) │
│         CRITICAL: Prevents 8-second timing errors (M2 lesson)  │
│                                                                 │
│ Step 5: breathCycle rhythm assignment (deterministic tables)    │
│         🟢 AUTOMATED + automatic overlap check                 │
│                                                                 │
│ Step 6: ffmpeg multi-track mix → flat MP3                      │
│         🟢 AUTOMATED (voice + shared library + cue timing)     │
│         Track layout: voice (1.0) + bed (0.08) + functional    │
│                                                                 │
│ Step 7: Generate phaseBMixConfig JSON for runtime player       │
│         🟢 AUTOMATED (deterministic from cue points + domain)  │
│                                                                 │
│ 🚪 APPROVAL GATE: Kim listen-through (~2 min)                 │
│                                                                 │
│ OUTPUT: M{n}_phase_b_complete_mix.mp3 + phaseBMixConfig JSON   │
│ COST: ~$0.50 per module                                        │
│ TIME: ~2 min compute + 2 min Kim review                        │
└─────────────────────────────────────────────────────────────────┘
```

### What makes this fully automatable

1. **Rhythm-lock pattern:** Breath sounds are placed by rhythm rules (inDur + holdDur + outDur), not by manually marking every inhale/exhale in the waveform. Vosk finds the CUE WORD timestamp; the rhythm table does the rest.

2. **Script-level cue markers:** `{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, etc. are embedded in scripts BEFORE TTS. They tell the pipeline which word occurrence is the actual cue, preventing the disambiguation error that caused an 8-second shift in M2.

3. **Shared sound library:** 33 files generated once, reused across all 54 modules. Only the voice stem is per-module unique.

4. **Deterministic mixing:** The ffmpeg script is a template. Replace the cue array and file paths per module — mixing logic is identical every time.

### Module types and their cue patterns

| Module Type | Cue Pattern | Automation Complexity |
|-------------|-------------|----------------------|
| Breathing (M1, M2, and equivalents across arcs) | breathCycle with rhythm tables | Medium (most cues, rhythm math) |
| Observation (Thought Clouds, etc.) | Noticing tones at "notice"/"watch" | Simple (instantaneous cues) |
| Singing Bowl (Mindful Listening) | Bowl strikes at focus points | Simple (one cue type) |
| Compassion (Warm Heart, Friend Fix) | Warmth expansion tones | Simple (3 progressive cues) |
| Tension Arc (Brave Steps) | Rise/peak/fall tones | Medium (duration-based tones) |
| Containment (Worry Box) | Step transitions + sealing | Simple (instantaneous cues) |
| Body Awareness (Sense Anchor, Squeeze & Release, Body Softening) | Region shifts + squeeze/release | Medium (multiple body regions) |

All patterns are defined in the Audio Engine Architecture §6.2. The automation logic is identical: find phrase via Vosk → disambiguate → fire cue → apply volume.

---

## 6. NARRATIVE EVENT AUDIO PIPELINE

Narrative events (Tessa's Fall, Luna's Discovery, etc.) are **runtime-composed scenes**:
- Visual layer: pre-produced animation with timing marks
- Audio layer: TTS-rendered dialogue mixed at runtime with ambient + SFX

### Per-event production flow

```
1. Dialogue exists in arc skeleton (Kim's authored text)
2. Claude assigns voice IDs per line (deterministic from character names)
3. Lines WITHOUT {variables} → render once as universal audio
4. Lines WITH {childName} etc. → store as templates for per-child rendering
5. Animation timing marks = TTS line durations (flexible ±0.5s)
```

### Voice profiles needed

| Character | Voice Source | When Designed |
|-----------|-------------|---------------|
| Myrrhin | ElevenLabs library (locked: oR4uRy4fHDUGGISL0Rev) | ✅ Done |
| Guide Bird | ElevenLabs library (TBD — warm, energetic, slightly self-deprecating) | Arc 1 production |
| Tessa (M1) | ElevenLabs library or clone | Arc 1 production |
| Luna (M2) | ElevenLabs library or clone (excitable, dramatic) | Arc 1 production |
| Ember (M4) | ElevenLabs library or clone | Arc 1 production |
| Bramble (M6) | ElevenLabs library or clone | Arc 1 production |
| Benson (M3) | ElevenLabs library or clone | Arc 1 production |
| Bork (M5) | ElevenLabs library or clone (loudspeaker energy) | Arc 1 production |
| Oliver | ElevenLabs library or clone | Arc 1 production |
| Agent (Grizzle) | ElevenLabs library or clone | Arc 1 production |

**Voice design process per character:**
1. 🟢 Claude drafts voice profile description (from Bible personality notes)
2. 🟢 Claude generates 3–5 ElevenLabs voice candidates with test lines from the skeleton
3. 🟡 Kim listens to candidates, picks one (~3 min per character)
4. 🟢 Claude locks voice ID and settings

**Arc 1 voice design session: ~10 characters × 3 min = ~30 min Kim time.** One-time. Future arcs add 1–3 new characters each.

### Exception: Opening Storybook (Event 0)

Pre-produced video with baked Myrrhin audio. No personalization. No per-child rendering. TTS-generated once at build time, mixed into video asset. 🟢 Fully automated after Kim approves the voice take.

---

## 7. TTS PERSONALIZATION PIPELINE

### How it works

Only sentences containing personalization variables ({childName}, {chosenGuideName}, etc.) are rendered per-child. All other sentences are universal (rendered once, shared).

### Cost model (from TTS Pipeline spec §4)

| Metric | Value |
|--------|-------|
| Per-child TTS cost (full app, all 9 arcs, 54 modules) | ~$2.82 |
| Scales with usage? | NO — one-time render per child |
| Re-render trigger | Only if therapist changes child's name |
| Phase B personalization | {childName} in opening + closing lines only (cue points stay universal) |

### Rendering modes

| Mode | When | Latency | Used For |
|------|------|---------|----------|
| **Mode 1: Pre-cached** | At module unlock | 0 (pre-rendered) | Phase B stems, Buy-In dialogue, narrative event lines |
| **Mode 2: Runtime** | On interaction | ~0.5s | Map sprite taps, Tomorrow Hooks, short Guide Bird lines |

### Automation level

| Step | Level | Notes |
|------|-------|-------|
| Variable substitution in templates | 🟢 | String replacement |
| TTS API call per variable-containing segment | 🟢 | ElevenLabs API |
| Cue point recalculation (if variable in mid-meditation) | 🟢 | But AVOIDED by design: {childName} only in opening/closing |
| Storage per child | 🟢 | `audio/children/{childId}/` |
| Kim involvement | NONE | Per-child rendering is invisible to Kim |

---

## 8. SOUND LIBRARY BUILD (ONE-TIME)

### The 33 files

| Category | Count | Generation Method | Kim Review |
|----------|-------|------------------|------------|
| Universal (bell + 6 landing shimmers) | 7 | ElevenLabs SFX v2 | 🟡 Pick from candidates |
| Ambient beds (6 domains) | 6 | ElevenLabs SFX v2 (looping, 30s) | 🟡 Pick from candidates |
| Breathing (inhale, hold, exhale + 3 exhale shimmers) | 6 | ElevenLabs SFX v2 | 🟡 Pick from candidates |
| Observation (noticing tone) | 1 | ElevenLabs SFX v2 | 🟡 Quick listen |
| Singing bowl | 1 | ElevenLabs SFX v2 | 🟡 Quick listen |
| Heart/expansion (3 warmth variants) | 3 | ElevenLabs SFX v2 | 🟡 Quick listen |
| Step process (marker + containment) | 2 | ElevenLabs SFX v2 | 🟡 Quick listen |
| Tension arc (rise + peak + fall) | 3 | ElevenLabs SFX v2 | 🟡 Quick listen |
| Body awareness (sense shift, region shift, squeeze, release) | 4 | ElevenLabs SFX v2 | 🟡 Quick listen |
| **TOTAL** | **33** | | **~30 min Kim time** |

### Generation strategy

For each sound: Claude generates 10+ candidates via ElevenLabs SFX v2 → auto-filters by duration, frequency content, and loop quality → presents top 3 to Kim → Kim picks.

**Critical quality gate for ambient beds:** The 6 domain beds define the sonic identity of MindfulNest forever. Kim should listen to these carefully. Budget 10 min for beds alone.

**Critical quality gate for transition bell:** Heard hundreds of times per child. Must be beautiful enough to never fatigue. Budget 5 min for bell selection.

### ElevenLabs SFX v2 capabilities

- Text-to-SFX with directional prompts
- Seamless looping at 48kHz
- Better accuracy than SFX v1 (fewer candidates needed)
- Covers ambient drones, bells, tones, nature textures, breath sounds
- **Cannot do:** Complex musical compositions, specific instrument performances, exact pitch control

### Fallback for ambient beds

If ElevenLabs SFX v2 can't produce beds that meet the spec (warm, non-melodic, non-rhythmic, loopable), alternatives:

| Fallback | Cost | Effort |
|----------|------|--------|
| Suno/Udio AI music generation | $10–30/mo | Medium (need to filter heavily for non-melodic output) |
| Freesound.org CC-licensed ambient recordings | $0 | Medium (search + layer + process) |
| Artlist/Epidemic Sound stock | $15–30/mo | Low (search + trim) |
| Commission ambient producer (Fiverr Pro / SoundBetter) | $200–500/domain | Low (hand them the spec) |

**Recommendation:** Try ElevenLabs SFX v2 first. It worked for breath sounds in M1/M2. If beds aren't up to standard, commission Calm domain only ($200–500) and generate the remaining 5 domains from that reference.

---

## 9. GUIDE BIRD DIALOGUE PIPELINE

### How it works

1. Claude Haiku generates 6 text fields per module: Call, Buy-In, Rescue Transition, Win Celebration, Nudge, Bridge
2. {childName} and {guideName} are naturally included (system prompt instructs Haiku to use them)
3. Each field → ElevenLabs TTS → Guide Bird voice → cached audio

### Automation level: 100% 🟢

No Kim involvement per-module. Kim reviews:
- The Haiku system prompt ONCE (🟡 ~15 min)
- Guide Bird's voice profile ONCE (🟡 ~3 min)

After that, all 54 modules × 6 fields = 324 TTS renders happen automatically at module unlock.

### Tomorrow Hooks

Same pipeline. Template text with {childName} → runtime TTS (Mode 2, ~10 words, negligible latency). 🟢 Fully automated.

---

## 10. MAP & UI AUDIO

### Map sprite tap lines

- Short (1–2 sentences) spoken when child taps a creature on the map
- Lines without {childName}: universal audio (render once)
- Lines with {childName}: runtime TTS on tap (~0.5s latency, acceptable)
- Each line tagged with voiceId for the speaking creature

### UI sounds

Standard app interaction sounds: tap, swipe, unlock, coin collect, level complete, etc. Generated via ElevenLabs SFX or sourced from free libraries.

| Sound | Source | Cost |
|-------|--------|------|
| Tap feedback | ElevenLabs SFX or Freesound | $0 |
| Coin collect | ElevenLabs SFX | $0 |
| Module unlock | ElevenLabs SFX (custom for MindfulNest — magical quality) | $0 |
| Zap send/receive | ElevenLabs SFX (crystalline/light quality) | $0 |
| Stone placement (runestone) | ElevenLabs SFX (resonant, satisfying) | $0 |

**Total Kim time:** ~5 min to approve a batch of UI sounds (one-time).

---

## 11. DASHBOARD AUDIO (SEPARATE PIPELINE)

The Parent Dashboard and Therapist Dashboard are web apps (React + CSS). Audio elements:

- **"Play Spell" button:** Streams the child's pre-rendered Phase B audio. No additional production needed — it's a playback feature.
- **No ambient audio on dashboard.** Dashboards are data/admin interfaces.

**Production work: Zero.** This is not an audio production task.

---

## 12. TIMELINE & PROMPT ESTIMATES

### Phase structure

**PHASE 0: Sound Library + Voice Design**
- Build 33 shared sound library files
- Design 10 character voice profiles for Arc 1
- Claude prompts: ~50–70
- Kim time: ~60 min (one "Audio Foundation" session)
- 🚪 Approval Gate: Kim approves bell, beds, breath sounds, voices

**PHASE 1: Calm Domain Prototype (M1 + M2 re-production)**
- Re-produce M1 and M2 with final library sounds (replacing placeholder wooden flute)
- Full pipeline validation: script → TTS → Vosk → mix → JSON
- Claude prompts: ~15–20
- Kim time: ~20 min (listen to 2 completed mixes)
- 🚪 Approval Gate: Kim confirms "this is what MindfulNest sounds like"

**PHASE 2: Arc 1 Full Production (remaining 4 modules + 8–10 narrative events)**
- 4 more Phase B modules (M3/Benson, M4/Ember, M5/Bork, M6/Bramble)
- ~8–10 narrative events with multi-character dialogue
- Claude prompts: ~60–80
- Kim time: ~60 min (module listens + narrative event voice checks)
- 🚪 Approval Gate: Arc 1 audio complete

**PHASE 3: Arcs 2–9 (templated, faster)**
- 48 more modules + ~44 more narrative events
- Pipeline proven, no new tool setup
- Claude prompts: ~350–450
- Kim time: ~6–8 hours (spread across arc production)
- 🚪 Approval Gates: per-arc reviews

### Summary table

| Phase | Claude Prompts | Kim Time | Calendar Time (intensive) | Calendar Time (relaxed) |
|-------|---------------|----------|--------------------------|------------------------|
| Phase 0 (library + voices) | 50–70 | 60 min | 1–2 days | 1 week |
| Phase 1 (Calm prototype) | 15–20 | 20 min | 1 day | 3 days |
| Phase 2 (Arc 1 complete) | 60–80 | 60 min | 2–3 days | 1–2 weeks |
| Phase 3 (Arcs 2–9) | 350–450 | 6–8 hrs | 2–4 weeks | 6–8 weeks |
| **TOTAL** | **~475–620** | **~9–11 hrs** | **~3–5 weeks** | **~8–11 weeks** |

**Important:** "Intensive" means Kim reviews same-day and Claude batch-processes overnight. "Relaxed" means Kim reviews a few times per week. The Claude prompts themselves take minutes; the calendar time is almost entirely waiting for Kim's approval gates.

### Comparison to visual pipeline

| Metric | Visual Pipeline | Audio Pipeline |
|--------|----------------|----------------|
| Total Claude prompts | ~310–575 | ~475–620 |
| Total Kim time | ~20–35 hrs | ~9–11 hrs |
| Calendar time (intensive) | ~8–13 weeks | ~3–5 weeks |
| Monthly tool cost | ~$40/mo (Scenario.gg + Spine) | ~$22/mo (ElevenLabs) |
| One-time tool cost | ~$369 (Spine Pro) | $0 |

Audio is MORE prompts but LESS Kim time because most audio production has no visual review component — Kim just listens to a finished mix and says yes/no.

---

## 13. KIM'S TOTAL TIME COMMITMENT

| Activity | When | Time | Frequency |
|----------|------|------|-----------|
| Sound library review (bell, beds, breath, specialty) | Phase 0 | 30 min | Once ever |
| Voice profile selection (10 Arc 1 characters) | Phase 0 | 30 min | Once per arc (1–3 new chars) |
| Phase B script review (read-through) | Per module | 5 min | 54 times |
| Voice stem listen (selected take) | Per module | 2 min | 54 times |
| Final mix listen-through | Per module | 2 min | 54 times |
| Narrative event voice check | Per event | 3–5 min | ~54 events |
| Haiku system prompt review | Once | 15 min | Once ever |
| UI sound batch review | Once | 5 min | Once ever |
| Map sprite line batch review | Once | 10 min | Once ever |

**Grand total: ~9–11 hours across the entire project.**

All of it is listening and saying yes/no. Zero production work, zero editing, zero timing, zero mixing.

---

## 14. RISK REGISTER

| Risk | Probability | Impact | Mitigation | Cost of Mitigation |
|------|------------|--------|------------|-------------------|
| ElevenLabs SFX v2 can't produce acceptable ambient beds | Low | Medium | Fall back to commissioned producer for Calm domain ($200–500), then generate remaining from that reference | $200–500 |
| Myrrhin voice (PVC) doesn't respond well to v3 Audio Tags | Medium | Low | Fall back to ellipsis-only pacing (proven in M1/M2) | $0 |
| Vosk STT misidentifies cue words in complex scripts | Low | Medium | Script cue markers prevent this. Validated in M2. Worst case: human verification via Cue Point Mapper tool | $0 |
| ElevenLabs pricing changes | Medium | Medium | Sound library is one-time build. Voice stems are small. Even at 2× cost, total production is <$300 | $0 (budget buffer) |
| Child name length causes cue point drift in Phase B | Low | Low | AVOIDED BY DESIGN: {childName} appears only in opening/closing lines, outside cue point range | $0 |
| Voice quality inconsistency across 54 modules | Low | High | Same voice ID + same settings + same voice model version for all modules in a batch. Regenerate outliers. | $0 |

---

## 15. QUALITY BENCHMARKS

### Phase B mix quality checklist (automated + manual)

**Automated checks (🟢 Claude runs before Kim hears anything):**
- [ ] Voice stem duration within ±20% of script estimate
- [ ] All cue markers have corresponding Vosk timestamps (no orphans)
- [ ] No breathCycle overlaps (gap ≥ 0 between all cycles)
- [ ] Final MP3 loudness: -16 LUFS ± 1 (podcast/audiobook standard)
- [ ] True peak: ≤ -1 dBTP
- [ ] Mono compatibility check (no phase cancellation artifacts)

**Kim listen-through (🟡 subjective quality):**
- [ ] Voice sounds warm and present (not robotic, not rushed)
- [ ] Breath sounds fire at natural moments (inhale with instruction, exhale at release)
- [ ] Ambient bed is felt but not distracting
- [ ] Landing moment feels like recognition ("there it is")
- [ ] A 7-year-old would feel safe listening to this

### Voice profile quality checklist

- [ ] Consistent across test phrases (Stability 65–75%)
- [ ] Not breathy/whisper (meditation cliché)
- [ ] Not robotic or flat
- [ ] Matches character personality from Bible
- [ ] Works on device speakers (not just headphones)

---

## 16. COPPA & COMPLIANCE

| Requirement | How Audio Pipeline Complies |
|-------------|---------------------------|
| No child data collection | TTS rendering uses only {childName} provided by authenticated therapist/parent. No voice recording from children. |
| Parental consent for personalization | Therapist provides child profile at onboarding (behind auth). Personalization is text-to-speech, not speech-to-text. |
| Data storage | Per-child audio stored in authenticated Firebase paths. Accessible only to that child's therapist + parent. |
| COPPA-safe Phase B parent playback | Behind parent auth. Reuses child's pre-rendered audio. No additional data collection. |
| No microphone access in v1 | Future breath detection via microphone deferred to v2. v1 uses no device audio input. |

---

## 17. OPEN QUESTIONS

1. **Ambient bed production method:** Will ElevenLabs SFX v2 produce beds good enough for production, or do we need a commissioned producer for the Calm domain prototype? → **Answer after Phase 0 testing.**

2. **ElevenLabs Scribe v2 vs. Vosk:** Head-to-head test pending. Scribe may offer better accuracy on Myrrhin's stylized delivery. Vosk is proven and free. → **Test during Phase 1.**

3. **Per-child total cost beyond TTS:** Kim wants to evaluate total per-child costs across ALL systems (TTS + Firebase storage + compute). TTS is ~$2.82/child. Storage + compute TBD. → **Depends on infrastructure decisions.**

4. **Number of modules:** Documents reference both 12 (Arc 1 only) and 54 (all 9 arcs × 6 modules). This plan uses 54 for full-game estimates. Confirm module count per arc is 6. → **Verify against Bible.**

5. **SFX v2 re-generation:** The Assembly Guide recommends re-generating the shared breath sound library with SFX v2 for Arc 2+ production. Should this happen during Phase 0 or deferred? → **Recommend Phase 0 to avoid rework.**

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | March 27, 2026 | Initial specification. Complete audit of all 6 audio streams. Every step classified 🟢🟡🔴. Prompt-based estimates (not hours). Phase + Approval Gate structure replaces week-based timeline. Sound library build spec. Risk register. Quality benchmarks. COPPA compliance. Week-estimate methodology explanation. |

---

*— End of Audio Pipeline Master Plan —*

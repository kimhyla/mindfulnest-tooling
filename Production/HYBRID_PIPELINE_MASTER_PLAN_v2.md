# MindfulNest Hybrid Video Production Pipeline — Master Plan v1

**Date:** April 13, 2026  
**Status:** Consolidated from fragments scattered across handoffs, memory files, and research docs  
**Purpose:** Single canonical reference for all video/visual asset production decisions  
**Maintained by:** Claude (dashboard-ops, video-producer skills)

---

## Overview

MindfulNest uses a **3-stage hybrid video pipeline** combining multiple specialized services. Each production task (character generation, scene composition, animation, lip sync) routes to the optimal service for that specific task, with documented fallbacks.

**Total estimated cost per 5-second scene:** ~$0.26 (Pixar 3D style, character-centered, dialogue-heavy)

---

## Service Matrix: What Tool For What Task

| Production Task | Primary Service | Cost/Unit | Fallback | Fallback Cost | Proven? | Notes |
|---|---|---|---|---|---|---|
| **Character reference stills** | FLUX Kontext Max (species swap from Tessa hero) | $0.08/img | Midjourney --cref (85-90% consistency) | $0/img (within quota) | ✅ PROVEN (April 7-8) | Kontext does "species replacement" (contained edit: same pose, lighting, composition, just different creature). Used to generate all 8 creature hero reference images from the approved Tessa hero base. Replaces old Neolemon approach. |
| **Scene stills (solo character)** | FLUX Kontext Max (inpainting edits on FLUX base) | $0.08/img | Gemini 2.5 Flash (Nano Banana) for difficult poses/expressions | ~$0.039/img standard | ✅ PROVEN (April 4+) | Kontext cannot compose complex multi-object scenes or position objects reliably. For solo character in already-composed scene, Kontext works well for contained edits (style change, recolor, text on objects). Nano Banana (Gemini) used for character expression variants when Kontext struggled (e.g., Bramble angry with hammer, Tessa crying on rock). |
| **Scene stills (duo/multi-character composition)** | Gemini 2.5 Flash two-pass (char A solo → add char B) | ~$0.078/img (two passes) | Midjourney v6.1 --cref | $0/img (within quota) | ✅ PROVEN (April 12-13) | Two-pass Gemini approach: Pass 1 generates primary character + scene, Pass 2 adds secondary character to Pass 1 output. Eliminates reference budget competition. Midjourney retained as fallback for 3+ character scenes. |
| **Text on images (carved stone, placards)** | FLUX Kontext Max | $0.08/img | PIL/ImageMagick (manual) | $0 (non-viable) | ✅ PROVEN (April 4) | Kontext produced production-quality carved stone placards on first try. PIL/ImageMagick attempts produced ghostly/flat results across 4+ hours testing. Kontext is the locked solution for inscriptions. |
| **Animation (image-to-video)** | Seedance 1.5 Pro (via WaveSpeed) | $0.06/clip | fal.ai Seedance 2.0 (with video-extend), or Kling v1.5/pro+ (v1/standard BANNED) | $0.03/img (fal) or per-use (Kling) | ✅ PROVEN (April 3) | Seedance 1.5 Pro is the workhorse. Kim confirmed "perfect" on painted fox (April 3). Known issue: extra limbs in output — mitigate with camera-motion prompts. WaveSpeed API intermittent (connection refused / timeouts cycling every 5-10 min). Fallback: compress input to CRF 28, retry with 15-20s intervals, or switch to fal.ai Seedance 2.0. |
| **Lip sync (mouth animation)** | ByteDance Lipsync | $0.15/5s | Rhubarb Lip Sync (local, free, phoneme-based) | $0 | ✅ PROVEN (April 3) | ByteDance lipsync applied AFTER Seedance video — input: Seedance output + TTS audio → mouth-synced video. Kim confirmed result was "perfect" on April 3. Skip for non-dialogue scenes (establishing shots, transitions). V2 (post-launch): Rhubarb extracts phoneme timing from TTS, maps to Spine mouth bone positions for more accurate sync. |
| **TTS voice generation** | ElevenLabs (eleven_v3 model) | ~$2.82 one-time per child | None (locked service) | — | ✅ PROVEN (12-voice roster) | All character voices generated via ElevenLabs API. 12 characters locked as of April 5-6. Model: eleven_v3 with emotional direction tags (e.g., "[bursting with relief]"). Personalization variables rendered at segment level (only sentences with {childName} rendered per-child; universal sentences shared). One-time render cost ~$2.82/child for full app. |
| **Audio mixing (Phase B meditation)** | ffmpeg (Claude-orchestrated multi-track) | $0 | — | — | ✅ PROVEN | Audio producer skill orchestrates: TTS voice stem + breathCycle timing + Vosk STT cue-point extraction + ffmpeg mix. Result: flat MP3 with embedded breathing rhythm and cue markers. Handles all Phase B meditation audio production autonomously. |
| **Video assembly (final composite)** | ffmpeg (segment concatenation + transitions) | $0 | — | — | ✅ PROVEN | video-producer skill orchestrates: stills → Seedance animation → ByteDance lipsync → ElevenLabs TTS → Phase B audio → ffmpeg assembly. Outputs final module video ready for playback in app. All orchestration via Claude automation. |

---

## Visual Production Rules [NEW April 13]

**HARD RULES — Non-negotiable production constraints discovered during Event 1 production:**

1. **NO TEARS IN STILLS:** All image-to-video models amplify liquid features into waterfalls. Remove ALL visible tears before animation. Convey crying through audio only.

2. **NO Kling v1/standard:** BANNED. Prompt-dominant, ignores input image. Fallback chain: Seedance 1.5 Pro → fal.ai Seedance 2.0 → Kling v1.5/pro+.

3. **Single-scene multi-angle for dialogue:** One master wide shot + cropped close-ups. Animate each piece separately. Eliminates multi-character artifacts.

4. **Gemini two-pass for duo shots:** Pass 1 = primary char + scene. Pass 2 = add secondary char. Never 7+ refs in one call.

5. **Anti-bioluminescence:** Explicitly block in all magical forest prompts.

6. **Blue scarf enforcement:** Every Guide Bird prompt must block brown hood explicitly.

---

## Service Details & Specifications

### 1. FLUX Kontext Max (BFL API)

**Endpoint:** `https://api.bfl.ai/v1/flux-kontext-max`

**What it does:**
- Takes a reference image + text prompt → outputs edited version
- Performs contained image edits: species replacement, style changes, recoloring, text on objects
- Image consistency at 90%+ (same composition, pose, lighting, just modified details)

**What it CANNOT do:**
- Precise spatial placement of multiple objects (tested 3+ times on heartwood tree — always fails at positioning and counting)
- Complex multi-object scene composition
- Reliable counting or spatial relationships between objects

**Pricing:** $0.08 per image

**Account status:** <REDACTED_PER_LD208_USE_DOPPLER>, ~920 credits remaining (started with 1000, used ~80 on April 4)

**Parameters (locked):**
- `guidance_scale=2.0`
- `steps=28`
- Seeds: 43, 44, 45 (or creature-specific seeds)

**Species swap recipe (proven April 7-8):**
```
Prompt pattern: "same pose, same lighting, same white background, same art style, 
[creature description]"
Input: base64-encoded reference image (Tessa hero 4096x4096)
Output: 3+ variants in signed URL (valid 10 min)
Cost: $0.08 per seed, typically 3 seeds/creature = $0.24/creature hero
```

**Key lesson:** Species replacement ≠ spatial placement. Species replacement is a *contained edit* (pose/lighting/background unchanged, only creature identity changes). Kontext excels here. Do NOT use Kontext for multi-object composition or repositioning.

---

### 2. Seedance 1.5 Pro (WaveSpeed API)

**Endpoint:** `POST api.wavespeed.ai/api/v3/bytedance/seedance-v1.5-pro/image-to-video`

**What it does:**
- Takes a still image + optional motion prompt → outputs 4-5 second video with smooth camera/character motion
- Maintains character identity better than Runway Gen-3
- Responds to camera-motion prompts to reduce artifacts (e.g., "camera pulling back, character stays centered")

**Pricing:** $0.06 per clip (polling-based; submit → get job ID → poll `/api/v3/predictions/{id}/result` until Ready)

**Known issues & workarounds:**
- **Extra limbs in output:** Known Seedance artifact. Mitigate by adding camera-motion direction to prompt ("camera pulling back, character gesturing at runestone"). This constrains the character's limb space.
- **WaveSpeed API intermittent failures:** Experiences connection-refused / timeouts cycling every 5-10 min (likely rate limiting on Bronze tier, 5 videos/min cap). 
  - **Workaround:** Always compress video-extend inputs to CRF 28 before submitting (keeps base64 < 30MB). Use resilient retry loops with 15-20s intervals. Jobs that got a job ID will likely complete even if polling fails — keep retrying.
  - **Fallback:** fal.ai Seedance 2.0 (needs credits topped up) or Kling v1.5/pro+ ONLY (per-use pricing). HARD BAN on Kling v1/standard — catastrophic quality, prompt-dominant, ignores input image entirely.

**Prompt format:**
```
"slow 360-degree turnaround of [character name], white background, no camera cuts"
or
"[character name] reaching toward the glowing runestone, camera pulling back, warm golden light"
```

**Output:** WebM or MP4 video (~4-5 sec, 512-1024px width typical)

---

### 3. ByteDance Lipsync

**Endpoint:** `POST api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video`

**What it does:**
- Takes a video (from Seedance) + audio (from ElevenLabs TTS) → outputs mouth-synced video
- Automatically detects speech and deforms mouth to match phoneme timing
- Kim confirmed result "perfect" on painted fox (April 3, 2026)

**Pricing:** $0.15 per 5-second video

**When to use:**
- All dialogue scenes (narrative, buy-in, creature reactions)
- NOT for non-dialogue scenes (establishing shots, transitions, instrumental passages)

**When to skip:**
- Scenes with no speech
- Background creatures (off-screen voices)
- Instrumental-only audio segments

**Input requirements:**
- Video: Seedance output (WebM or MP4)
- Audio: ElevenLabs TTS MP3 (mono, 22kHz or 44.1kHz)

**Output:** Mouth-synced video ready for final assembly

---

### 4. ElevenLabs TTS (Character Voices)

**Service:** ElevenLabs API (eleven_v3 model)

**Voice roster (locked April 5-6, 2026):**

| Character | Voice | Stability | Similarity | Style | Notes |
|-----------|-------|-----------|------------|-------|-------|
| Guide Bird | Chipper1 | 0.30 | 0.80 | 0.30 | Warm, energetic, slightly self-deprecating |
| Myrrhin | Library voice | 0.70 | — | — | Old wise wizard, narrates ALL Phase B meditations |
| Tessa (M1) | Jessica | 0.30 | 0.80 | 0.30 | Gentle, curious |
| Luna (M2) | Miranda | 0.30 | 0.80 | 0.30 | Excitable, physical, dramatic |
| Benson (M3) | Gigi | 0.30 | 0.80 | 0.30 | Warm, encouraging |
| Ember (M4) | Katie | 0.30 | 0.80 | 0.30 | Brave, energetic |
| Bramble (M6) | Northern Terry (Irish) | 0.30 | 0.80 | 0.30 | Calm, grounded, with accent |
| Bork (M5) | Bork2 | 0.30 | 0.80 | 0.30 | Deep, resonant, serious |
| Oliver | Brayden | 0.30 | 0.80 | 0.30 | Warm, mentoring |
| Grizzle | Gotham Boss | 0.30 | 0.80 | 0.30 | Authoritative, formal |
| King | Carter | 0.30 | 0.80 | 0.30 | Regal, commanding |
| Lady Willow | Alisha | 0.30 | 0.80 | 0.30 | Wise, maternal |

**Pricing:** ~$2.82 one-time per child for full app (all 9 arcs, 54 modules)
- Segment-level personalization: only sentences with {childName}, {therapistName}, pronouns rendered per-child
- Universal sentences (no variables) shared across all children

**Rendering rules:**
- Every dialogue line must have emotional direction tag: `[bursting with relief]`, `[quiet, reflective]`, `[energetic]`
- Personalization variables: `{childName}`, `{therapistName}`, `{chosenGuideName}` (child names the Guide Bird), `{childPronoun}`, `{childPronounObject}`, `{childPronounPossessive}`, `{therapistPronoun}`, `{parentPronoun}`
- Pronouns derived automatically: boy → he/him/his, girl → she/her/her (no they/them option)
- "mindful-nest" always hyphenated in dialogue
- Myrrhin narrates Opening Storybook (Event 0) + ALL Phase B meditations (Events 1-6)

**Output:** MP3 audio files, mono, 44.1kHz (or 22kHz for smaller file size)

---

### 5. Gemini 2.5 Flash (Nano Banana) — Character Expressions

**Service:** Google Gemini API (gemini-2.5-flash-image model)

**What it does:**
- Multi-reference image generation: takes 2-4 reference images → generates new pose/expression consistent with all references
- Used for difficult character expression variants when FLUX Kontext inpainting failed
- Examples: Bramble angry with hammer, Tessa crying on rock, character pose variants

**Pricing:** ~$0.039/image standard, ~$0.0195/image batch

**When to use:**
- Character expression variants (worried, shocked, happy, angry)
- Non-human creatures in specific poses/emotions
- When Kontext inpainting cannot achieve the desired result

**When NOT to use:**
- Scene composition (use Midjourney instead)
- Text on objects (use Kontext instead)

**API key:** `<REDACTED_PER_LD208_USE_DOPPLER>`  
**Project:** mindfulnest-mvp (projects/870911417500)  
**SDK:** google-genai (NOT the deprecated google-generativeai)  

**Proven results (April 9, 2026):**
- Luna: 10 approved expression files (worried, shocked_openmouth, shocked_halfsmile)
- Benson, Ember: 12 approved files each
- Bork, Oliver: 10 approved files each (with backups for extra-hand and whiskers fixes)
- Guide Bird, King, Willow: 12 approved files each
- Bramble: 10 angry variants (base + hammer + beltloop) ✓
- Tessa: 8 crying-on-rock variants ✓

**Status:** 157 primary character expression files + 21 backup files approved by Kim (April 9, 2026)

---

### 6. Midjourney v6.1 (Scene Composition & Reference Bootstrap)

**What it does:**
- Multi-creature scene composition with --cref character reference
- Bootstrap reference sets for Scenario.gg custom model training
- Consistency: 75-85% across variations (acceptable for watercolor style; Scenario training smooths further)

**Pricing:** $0/image within paid Discord tier (~200 free images/month)

**Best practices:**
- Use `--v 6.1` explicitly (--cref does NOT work with v7)
- Use `--cref [hero URL] --cw 80-100` for pose/angle variants from approved hero
- Use `--style raw` to reduce stylization interference
- Use `--s 50` (medium randomness) for balance

**When to use:**
- Initial scene composition with multiple characters
- Bootstrap reference generation (20-30 variations → CLIP scoring → top 10-15 → Scenario training)
- Establishing shots, environmental context, multi-creature interactions

**When NOT to use:**
- When character consistency must be 100% (use Kontext species swap instead)
- For contained edits (use Kontext instead)
- For difficult non-human poses (use Nano Banana instead)

**Consistency QA workflow:**
1. Generate 20-30 variations with --cref
2. Run CLIP embedding similarity scoring (0-1 scale, threshold 0.85+)
3. Auto-reject images below threshold
4. Present only top-scoring images to Kim
5. If Kim flags specific images, analyze exact drift (color histogram, proportion measurement) and target replacement

---

### 7. WaveSpeed API (Video Delivery Hub)

**What it does:**
- Central hub for Seedance, ByteDance lipsync, and video-extend operations
- Polling-based job submission (submit → get job ID → poll for result)

**Pricing:**
- Seedance: $0.06/clip
- ByteDance lipsync: $0.15/5s
- Video-extend (if used): varies

**Reliability notes:**
- Bronze tier (5 videos/min cap) experiences intermittent timeouts
- Solution: compress inputs to CRF 28, use resilient retry loops (15-20s intervals)
- WaveSpeed credits: refilled April 11 to $150.13 (video pipeline unblocked)
- Fallback: fal.ai has Seedance 2.0 with video-extend (needs credits)

---

### 8. ffmpeg (Audio Mixing & Video Assembly)

**What it does:**
- Multi-track audio mixing (TTS voice + breathCycle rhythm + ambient background)
- Video concatenation and segment assembly
- Format conversion and compression

**Pricing:** $0 (open-source)

**Used in:**
- **Audio producer:** Combines TTS stem + breathCycle with ffmpeg multi-track mixing → flat MP3 with embedded rhythm markers
- **video-producer:** Concatenates stills → Seedance animation → ByteDance lipsync → Phase B audio → final MP4

**Process:**
```
TTS MP3 (voice) + breathCycle MP3 (rhythm) → ffmpeg -f concat -i input.txt -c copy output.mp3
Segment stills + animation + lipsync + audio → ffmpeg -f concat -safe 0 -i segments.txt -c:v copy -c:a aac output.mp4
```

---

## What's Proven vs. Aspirational

### ✅ PROVEN IN PRODUCTION (April 2026)

| Task | Service | Evidence | Status |
|------|---------|----------|--------|
| Character reference still (species swap) | FLUX Kontext Max | Guide Bird generated from Tessa hero (April 7-8) + all 8 creature heroes | LOCKED |
| Scene still (solo character) | FLUX Kontext Max | Heartwood inscriptions, style edits (April 4+) | LOCKED |
| Character expressions | Gemini Nano Banana | 157 approved files, Kim sign-off (April 9) | LOCKED |
| Image-to-video animation | Seedance 1.5 Pro | Painted fox "perfect" Kim approval (April 3) | LOCKED |
| Lip sync | ByteDance Lipsync | Painted fox "perfect" Kim approval (April 3) | LOCKED |
| TTS voice generation | ElevenLabs eleven_v3 | 12-voice roster, 146 dialogue lines (April 5-6) | LOCKED |
| Audio mixing | ffmpeg | Phase B meditation mixing (in progress, verified April 11) | LOCKED |
| Video assembly | ffmpeg + script orchestration | Module event pipeline architecture (April 6+) | LOCKED |

---

### 🟡 TESTED BUT NOT FULL PRODUCTION SCALE (Theoretical/Partial)

| Task | Service | Evidence | Status | Notes |
|------|---------|----------|--------|-------|
| Multi-character scene composition | Midjourney v6.1 | Initial testing 85-90% consistency | WORKING | Consistency drifts ~10-15%, acceptable. Used for multi-creature scenes. |
| Scene still (multi-character) | FLUX Kontext | NOT TESTED for multi-object composition | AVOID | Testing showed Kontext fails at spatial placement of multiple objects. Do NOT use. |
| Reference bootstrap | Midjourney + CLIP scoring | Initial workflow (no full Scenario.gg training yet) | THEORETICAL | Workflow proven, full production test pending. |
| Spine JSON animation | Claude programmatic generation | JSON structure designed, not yet rendered at runtime | THEORETICAL | Recipe designed, full Phaser integration pending. |

---

### 🔴 REJECTED (Do NOT Use)

| Task | Service | Reason |
|------|---------|--------|
| Character consistency (non-human) | Replicate fofr/consistent-character | InstantID cannot process animal faces — architectural limitation |
| Character consistency (non-human) | FLUX.2 Pro IP-Adapter | Inconsistent proportions and colors at scale |
| Character consistency (non-human) | Segmind Neolemon V3 API | Kim verdict: "this is not going to work" — more humanoid, less cute |
| Animation (image-to-video) | Runway Gen-3 | Inferior to Seedance 1.5 Pro |
| Animation (image-to-video) | Kling 3.0 | Wrong aesthetic (rejected April 6) |
| Multi-object scene composition | FLUX Kontext Max | Fails at spatial placement and object counting |
| Text carving (old approach) | PIL/ImageMagick | Ghostly/flat results across 4+ hours testing |

---

## Arc 1 Module Cost Breakdown (Single Module, 6 Segments)

| Segment | Tasks | Service | Cost |
|---------|-------|---------|------|
| **Story Scene** | 1-2 stills + Seedance animation | Midjourney + Kontext + Seedance | $0.06 (Seedance) |
| **Buy-In** | Guide Bird portrait still | ElevenLabs TTS (pre-authored) | $0 (shared across children, personalization variables) |
| **Phase A** | Interactive demo (custom React) | Claude code | $0 |
| **Phase B** | Meditation audio (narration + breathing) | ElevenLabs + ffmpeg mixing | $0 (shared) |
| **Resolution** | 1-2 stills + Seedance animation | Kontext + Seedance | $0.06 (Seedance) |
| **Win Sequence** | Standardized component (no custom production) | Phaser FX (Claude code) | $0 |
| **Return to Map** | No new visuals (reuse sprites) | — | $0 |
| **TOTAL PER MODULE** | — | — | **~$0.12** |
| **+ Character expressions (one-time)** | 157 files approved | Nano Banana | **~$6.10** (one-time per arc set) |
| **+ TTS for all modules in arc** | 54 modules × ~2.82 | ElevenLabs | **~$2.82** (one-time per child) |
| **TOTAL ARC 1 (per child, one-time)** | — | — | **~$9.04** (TTS + char expressions amortized) |

---

## Fallback Hierarchy

**When primary service fails, use this priority order:**

### Image Generation Fallback Tree
```
FLUX Kontext Max (contained edits)
    ├─ If inpainting fails → Gemini Nano Banana (multi-reference)
    └─ If Nano Banana fails → Manual PIL/ImageMagick (non-viable last resort)

Midjourney v6.1 (scene composition)
    ├─ If consistency drifts > 20% → regenerate with adjusted prompt or CLIP filtering
    └─ If multi-character fails → Nano Banana solo character variants + manual composite

Scenario.gg custom model (character consistency)
    ├─ If model training insufficient → Midjourney --cref volume + CLIP scoring
    └─ If neither available → Use approved reference sheets and limit to 2-3 poses
```

### Video Generation Fallback Tree
```
Seedance 1.5 Pro (primary workhorse)
    ├─ If WaveSpeed API timeout → retry with CRF 28 compression + 15-20s intervals
    ├─ If job fails → submit to fal.ai Seedance 2.0
    └─ If video-extend needed → use fal.ai (higher reliability for extend operations)

ByteDance Lipsync (dialogue sync)
    ├─ If audio/video mismatch → re-render TTS with tighter audio bounds
    ├─ If lipsync fails → skip lipsync, use amplitude-based mouth states (Phaser tween)
    └─ If critical → Rhubarb Lip Sync (local, free, phoneme-based) as V2 post-launch

ffmpeg assembly (final composite)
    ├─ If segment concatenation fails → check segment formats match (codec, fps, audio)
    └─ If transcoding fails → compress segments to H.264 + AAC before concat
```

### TTS Voice Fallback
```
ElevenLabs eleven_v3 (locked)
    └─ No fallback — ElevenLabs is the only service in use for character voices
        (cost too low, consistency too high, no viable alternative meets Kim's bar)
```

---

## API Keys & Credentials (Production Use)

**Read these at runtime from `Production/API_KEYS_MASTER.md` — NEVER hardcode:**

| Service | Key Name | Endpoint | Note |
|---------|----------|----------|------|
| BFL (FLUX Kontext) | `<REDACTED_PER_LD208_USE_DOPPLER>` | `api.bfl.ai/v1/` | 920 credits remaining |
| WaveSpeed (Seedance + ByteDance) | In `API_KEYS_MASTER.md` | `api.wavespeed.ai/api/v3/` | Auth via key header |
| ElevenLabs | In `API_KEYS_MASTER.md` | `api.elevenlabs.io` | Voice roster locked |
| Gemini (Nano Banana) | `<REDACTED_PER_LD208_USE_DOPPLER>` | `generativelanguage.googleapis.com` | Free tier, project `mindfulnest-mvp` |
| Midjourney | Via Discord API | Discord | Per-server subscription (~200 free images/month) |

---

## File Hosting for API Inputs

**External services require URLs for image/video inputs. Use these hosts:**

| Type | Host | Notes |
|------|------|-------|
| Audio | uguu.se | Temporary file hosting, auto-delete after 24h |
| Video | uguu.se or imgur | For Seedance animation inputs |
| Images | imgur.com | Permanent image hosting for Midjourney --cref URLs, reference anchors |
| Character refs | CDN URL (Heartwood assets) | Locked character reference URLs (Tessa hero, Bramble, etc.) |

---

## Production Anti-Patterns (What NOT To Do)

### 🔴 CRITICAL MISTAKES TO AVOID

1. **Using FLUX Kontext for multi-object composition or spatial placement**
   - Kontext will fail at counting objects and positioning
   - Use Midjourney for scenes with 2+ creatures
   - Use Kontext only for solo-character edits or contained modifications

2. **Using Midjourney for character consistency when Kontext can do species swap**
   - Midjourney drifts 10-15% consistency
   - Kontext species swap locks consistency at 90%+
   - If you have an approved base creature, use Kontext swaps, not Midjourney re-generation

3. **Combining species swap + costume in single Kontext call**
   - Run two separate calls: one for species, one for costume/color
   - Combined prompt confuses the model — each property should be isolated

4. **Using Kling 3.0 or Runway Gen-3 for animation when Seedance is available**
   - Kling has wrong aesthetic (rejected April 6)
   - Runway is inferior to Seedance 1.5 Pro
   - Seedance is proven, locked, $0.06/clip
   - Do not chase alternatives — Seedance is the standard

5. **Submitting large uncompressed videos to WaveSpeed without CRF 28 compression**
   - Base64 payload will exceed 30MB limit
   - Always compress to CRF 28 before submitting
   - This solves 90% of WaveSpeed timeout issues

6. **Trying to do character consistency with Replicate, FLUX.2, or Segmind**
   - All failed on non-human creatures (tested April 7)
   - $15+ wasted with zero results
   - Use Kontext species swap (proven) or Nano Banana (proven) only

7. **Mixing Seedance output styles across a single arc**
   - Seedance has consistent motion signature
   - All animations should use same seed/settings for visual continuity
   - Do not regenerate with different prompts mid-arc — will break visual cohesion

---

## Service Integration Checklist (Pre-Production)

Before starting video production for a module:

- [ ] **TTS voices locked?** Verify all 12 characters have approved ElevenLabs voices (VOICE_ROSTER_LOCKED_v2.md)
- [ ] **Character expressions approved?** All needed expression variants in `/Production/[Character]/poses/` (NANO_BANANA_ACCEPTED_MANIFEST_2026-04-09.md)
- [ ] **Skeleton dialogue finalized?** All dialogue locked, no re-recording needed mid-pipeline
- [ ] **Scene composition planned?** Shot breakdown + Seedance prompts ready (scene-to-production skill)
- [ ] **WaveSpeed credits sufficient?** ~$0.26/scene = $1.56/module (6 segments). Check WaveSpeed balance.
- [ ] **API keys current?** Read fresh from `Production/API_KEYS_MASTER.md` (BFL, WaveSpeed, ElevenLabs, Gemini)
- [ ] **Fallbacks reviewed?** If WaveSpeed down, know which fal.ai call you'll use instead
- [ ] **File hosting ready?** Have imgur/uguu.se logins for URL hosting (if needed)
- [ ] **Phase B audio mixing verified?** ffmpeg setup tested with breathCycle rhythm
- [ ] **Lip sync QA ready?** Know which scenes require lipsync vs. can skip

---

## Historical Context: Why These Choices

**Why FLUX Kontext for character stills?**  
Tested 5 tools across April 6-7 (Replicate, FLUX.2, Segmind, Neolemon, Midjourney). All failed on non-human creatures except Kontext species swap. Kontext proved out April 7-8 with Guide Bird generation from Tessa hero — single call, perfect consistency.

**Why Seedance over Kling/Runway?**  
Kling tested April 6, rejected wrong aesthetic. Runway tested prior, inferior motion quality. Seedance 1.5 Pro Kim-confirmed "perfect" April 3 on painted fox. Proved across multiple creatures. Locked.

**Why ByteDance lipsync?**  
Only lipsync solution that works at scale on non-human mouths. Kim confirmed "perfect" April 3. Alternative (Rhubarb) reserved for V2 (phoneme-based refinement post-launch).

**Why Nano Banana for difficult expressions?**  
Kontext inpainting struggled on angry Bramble with hammer (spatial placement), crying Tessa on rock (pose complexity). Nano Banana multi-reference solved both. April 9 approval: 157 expression files across 8 characters.

**Why Midjourney for multi-creature scenes?**  
Only tool that reliably composes 2+ creatures in one frame with scene context. Consistency 85-90% acceptable for watercolor/painterly style. Scenario.gg training smooths further.

---

## Future Enhancements (Post-Launch)

- **Rhubarb Lip Sync V2:** Phoneme-based mouth bone animations (free, open-source) for more accurate sync
- **Spine Animation V2:** Transition from amplitude-based mouth states to Rhubarb phoneme mapping
- **LoRA Fine-Tuning:** If character consistency needs exceed 90%, train custom LoRA on approved character set (cost ~$2-8, payoff across all animations)
- **ComfyUI Local Pipeline:** Self-hosted Seedance alternative if WaveSpeed becomes unreliable long-term
- **Scenario.gg Custom Models:** Per-creature trained models (currently experimental, evaluated for future pipeline enhancement)

---

## Document Maintenance

**Last updated:** April 12, 2026 (consolidated from fragments)  
**Maintained by:** Claude Code (via dashboard-ops, video-producer skills)  
**Version:** v1 (initial comprehensive consolidation)  
**Next review:** When new service tested or workflow changes  

**Source documents consolidated:**
- HANDOFF_Visual_Pipeline_Solution_April8_v2.md
- HANDOFF_VIDEO_PRODUCTION_April6_2026.md
- project_video_pipeline_pivot.md (auto-memory)
- project_flux_kontext.md (auto-memory)
- project_wavespeed_reliability.md (auto-memory)
- reference_gemini_api.md (auto-memory)
- VISUAL_PIPELINE_MASTER_PLAN_v5.md
- NANO_BANANA_FINAL_AUDIT_2026-04-09.md
- NANO_BANANA_ACCEPTED_MANIFEST_2026-04-09.md

---

*This is the canonical reference for all MindfulNest video/visual production decisions. If a workflow question arises, check this document FIRST.*

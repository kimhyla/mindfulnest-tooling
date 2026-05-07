# Phase B Audio Assembly Guide

## From Approved Script to Playable Module — The Complete Pipeline

### Version 1.4 — March 13, 2026

---

## Purpose

This document defines the step-by-step process for producing Phase B audio from an approved meditation script for ALL module types. It covers voice stem generation, cue point mapping, multi-track mixing, and automation pathways for scaling to infinite modules.

The initial worked example is breathing modules (M1, M2), which surfaced the rhythm-locked breathCycle pattern. As each new module type is produced (observation, tension arc, body awareness, etc.), its specific learnings will be added to Part 6: Module-Specific Notes. The core pipeline — voice stem → cue point extraction → shared library mixing → flat MP3 — is identical across all module types. Only the cue types and their triggering patterns differ.

**This guide begins where the Production Process ends.** The Production Process (v1.1) takes a module from research dossier through approved script. This guide takes an approved script through to a playable, mixed audio file.

**When this guide and another document conflict, the resolution order is:**

1. Everdale World Design Bible v9b (highest authority)
2. Phase B Sound Design Vision v1 (sonic principles)
3. Phase B Audio Engine Architecture v1 (technical schema)
4. This guide (production workflow)
5. ElevenLabs Sound Recipe v1 (generation prompts)

---

## Prerequisites

Before starting, confirm you have:

- [ ] Approved Phase B meditation script (from Production Process steps 0-9)
- [ ] Access to ElevenLabs (Starter plan minimum, Creator recommended)
- [ ] The shared sound library files (bell, inhale, exhale, noticing, ambient beds)
- [ ] ffmpeg installed (for automated mixing)
- [ ] The slim JSX demo file (for interactive validation, optional)

---

## PART 1: CONCEPTS

### 1.1 Two Output Formats

Every module produces two audio outputs:

| Format | File | Purpose | When Used |
|---|---|---|---|
| Pre-baked MP3 | `M{n}_phase_b_complete_mix.mp3` | Single flat file, plays anywhere | MVP, fallback, stakeholder review, therapist demos |
| Dynamic mix config | `phaseBMixConfig` JSON in module data | Voice stem + cue points, mixed at runtime by player engine | Production app (v2+), enables personalization |

Both formats are generated from the same source data. The pre-baked MP3 is produced by a mixing script that simulates what the runtime engine would do.

### 1.2 The Voice Stem Is the Timing Master

Everything in the mix aligns to the voice stem. The voice dictates when breathing happens, when the landing occurs, when the exit begins. No sound plays at a time that wasn't derived from the voice.

This has a critical implication: **you cannot finalize cue points until the voice stem exists.** Estimated timestamps from the script text (~2 words/second) are useful for prototyping but will be wrong. Real timestamps come from either:

- Human marking (the Cue Point Mapper tool)
- Vosk speech-to-text with word-level timestamps (automated — see §2.2 Method B)

### 1.3 The breathCycle Pattern

**Problem discovered during M1 production:** When a narrator says "In... and out..." as a quick verbal phrase, the words are much closer together than a real breath. If you place inhale/exhale sounds exactly where the narrator says those words, the breathing sounds are unnaturally rushed — especially in Deepening sections where the narrator speaks less.

**Solution: rhythm-locked breath cycles.** The narrator's words tell us when a breath cycle *starts*, but the inhale → hold → exhale rhythm is fixed at a natural pace regardless of how quickly the narrator speaks.

```
breathCycle cue:
  t: 26.7        ← when narrator says "Breathe in..." (cycle START)
  inDur: 4       ← inhale sound plays for 4 seconds
  holdDur: 2     ← silence (natural pause at top of breath)
  outDur: 5      ← exhale sound plays for 5 seconds
                   TOTAL: 11 seconds per cycle
```

The engine fires:
- Inhale sound at `t`
- (silence during hold)
- Exhale sound at `t + inDur + holdDur`

**Standard rhythms by module phase:**

| Phase | In | Hold | Out | Total | When |
|---|---|---|---|---|---|
| Instruction (guided) | 4s | 2s | 5s | 11s | Narrator is talking the child through each breath |
| Deepening (natural) | 3s | 1s | 4s | 8s | Child has the rhythm, narrator uses fewer words |
| Counted (M2 only) | matches count | matches count | matches count | varies | 4-7-8 pattern drives timing, not this table |

**Why hold matters:** Even in belly breathing (M1), which does NOT use explicit breath-holding, there is a natural 1-2 second pause at the top of an inhale before the exhale begins. Without the hold, inhale and exhale sounds blur into each other and lose the feeling of a complete breath.

**Anti-pattern: voice-synced exhale.** Never place the exhale sound where the narrator says "out." Always place it at the rhythm-locked offset from the inhale. The narrator's "out" is a verbal nudge, not a timing trigger.

### 1.4 Overlap Prevention

Before finalizing cue points, verify that no breath cycle overlaps the next:

```
Cycle N exhale ends at: t + inDur + holdDur + outDur
Cycle N+1 starts at:    t(next)
Gap = t(next) - (t + inDur + holdDur + outDur)
```

**Rules:**
- Gap must be ≥ 0 (no overlap)
- Gap < 1s is acceptable — creates a sense of continuous rhythm
- Gap > 10s is fine — the child is breathing on their own (mind-wandering sections, narrator asides)
- If gap is negative, shorten the Deepening rhythm (3+1+4=8s) or adjust the cycle start time

### 1.5 Volume Architecture

The voice is always loudest. Everything else is relative to voice volume.

**Proven defaults from M1 production (expressed as gain multiplier, 0.0-1.0):**

| Layer | Gain | Character |
|---|---|---|
| Voice stem | 1.00 | Clear, warm, always intelligible |
| Ambient bed | 0.08 | Barely perceptible texture — reduces cognitive load for children. Previous 0.20 default was too prominent. |
| Transition bell | 0.50 | Prominent moment — the "crossing the threshold" signal |
| Inhale wind | 0.30 | Present but subordinate to voice |
| Exhale wind | 0.55 | Boosted relative to inhale (exhale sounds are naturally softer) |
| Noticing tone | 0.15 | Gentlest accent — awareness marker, not attention-grabber |

**Key learning:** Inhale and exhale sounds generated by ElevenLabs SFX often have different inherent loudness even when prompted identically. Always listen to the pair together and adjust the quieter one up. The exhale needed ~1.8× the inhale's gain to sound balanced in M1.

---

## PART 2: STEP-BY-STEP PRODUCTION

### Step 1: Generate Voice Stem

**Input:** Approved Phase B script
**Output:** Single MP3/WAV file of the complete narration
**Tool:** ElevenLabs Text to Speech

#### 1.1 Voice Selection

Use the same voice across ALL modules. The narrator voice is a conditioned cue — children learn to associate it with safety and calm. Changing voices between modules breaks this conditioning.

Voice characteristics (from Sound Production Brief):
- Warm, wise, unhurried
- Gender-neutral preferred (or warm male)
- NOT breathy/whisper (meditation cliché)
- NOT robotic or flat
- Think: beloved grandparent at bedtime

**Test phrase:** "Ahh... you've come to learn the magic of Calm. Good."

#### 1.2 Voice Settings

| Setting | Value | Why |
|---|---|---|
| Stability | 65-75% | Enough consistency to feel reliable, enough variation to sound alive |
| Clarity + Similarity | 75-85% | Keeps voice character strong |
| Style Exaggeration | 15-25% | Touch of personality, not overacting |

#### 1.3 Generation

1. Paste the full script into the TTS text box
2. Use `...` (ellipses) for natural pauses
3. Generate 3 versions with identical settings
4. Pick the take with the best pacing and warmth
5. Export as MP3 (or WAV for archival)

**ElevenLabs v3 Audio Tags:** Phase B scripts may include inline emotional direction tags to shape Myrrdin's delivery without re-prompting. Insert tags immediately before the target word or phrase:

| Tag | Use for |
|---|---|
| `[gently]` | Invitations, soft instructions ("breathe in gently") |
| `[warmly]` | Landing phrases, affirmations ("that feeling right there") |
| `[softly]` | Exit phrases, stillness moments |
| `[slowly]` | Drawn-out breath cues needing extra pacing |

Example: `[gently] Breathe in... and [softly] let it go.`

**PVC CAVEAT:** Myrrdin (Voice ID: `oR4uRy4fHDUGGISL0Rev`) is a Professional Voice Clone. ElevenLabs v3 Audio Tag behavior may differ for PVCs vs. standard voices. **Test a full §1.3 generation run with tags on a short script segment before committing a production batch.** If tag response is inconsistent, fall back to ellipsis-only pacing for that session.

**Pacing check:** The output should be approximately 2 words/second for spoken content, with 3-5 second natural pauses where ellipses appear. If the AI rushes through pauses, add extra periods (`......`) or `<break>` tags.

#### 1.4 Duration Verification

The voice stem should land within the script's estimated duration (noted in Production Specs). For M1: 85-90 seconds estimated, 91.5 seconds actual — acceptable.

If the stem is significantly longer than estimated (>20% over), the AI may have added unnatural pauses or the pacing is too slow. Re-generate rather than time-stretching.

### Step 2: Map Cue Points

**Input:** Voice stem MP3 + approved script
**Output:** Timestamped list of cue events

This is where you identify the exact moments in the voice stem where each breathing instruction, landing phrase, and structural marker occurs.

#### 2.1 Method A: Human Marking (Current — M1 Process)

Use the Cue Point Mapper tool (HTML file with embedded voice audio):

1. Claude generates the mapper HTML with the voice stem embedded
2. Open in a browser (must be opened directly in Chrome, NOT in Claude.ai artifact preview which sandboxes audio)
3. Play the audio and click buttons at the exact moment you hear each cue
4. Copy the timestamps and paste them back to Claude

**What to mark:**

| Cue | What to Listen For | Notes |
|---|---|---|
| Each "Breathe in" / "In..." | The moment the narrator begins the inhale instruction | This becomes the breathCycle start time |
| Landing phrase | "That feeling right there..." or equivalent | The moment of naming what the child achieved |
| Exit phrase | "Stay right there..." or equivalent | Signals ambient bed fade-out |

**What NOT to mark:** Exhale moments. The exhale is placed by the breathCycle rhythm, not by when the narrator says "out."

#### 2.2 Method B: Automated Extraction via Speech-to-Text (Proven — M2 Process)

Run offline speech-to-text on the voice stem to get word-level timestamps, then pattern-match against cue words. This was validated during M2 production (February 24, 2026) and is now the recommended method for all modules.

**Tool:** Vosk (open-source, runs locally, no API cost). Install: `pip install vosk` + download `vosk-model-small-en-us-0.15`.

**Candidate upgrade — ElevenLabs Scribe v2** (released January 9, 2026): Cloud-based transcription with word-level timestamps, reported higher accuracy than Vosk on naturalistic speech. Potential benefit: better cue word detection on Myrrdin's slightly stylized delivery. **Do not switch from Vosk until a head-to-head test on an existing M1 or M2 voice stem confirms accuracy parity or improvement.** Vosk remains primary until test is run. If switching: replace the 16kHz mono WAV conversion step with the Scribe v2 API call; downstream pipeline (offset, pattern-match, disambiguation) is identical.

**Pipeline:**

1. Convert voice stem to 16kHz mono WAV (vosk requirement)
2. Run vosk with `SetWords(True)` to get `{ word, start, end }` for every word
3. Add voice delay offset (e.g., +3.0s if voice starts at 3s in the mix)
4. Pattern-match against cue identification rules (see Audio Engine Architecture §6.2)
5. **Apply disambiguation** (see §2.2.1 below) — cue words often appear multiple times
6. Apply standard breathCycle rhythms (see §1.3 above)
7. Run overlap check (see §1.4 above)
8. Output: `phaseBMixConfig` JSON

```python
# Core vosk pipeline (proven working)
from vosk import Model, KaldiRecognizer
import wave, json

model = Model("vosk-model-small-en-us-0.15")
wf = wave.open("voice_stem_16k.wav", "rb")
rec = KaldiRecognizer(model, wf.getframerate())
rec.SetWords(True)

all_words = []
while True:
    data = wf.readframes(4000)
    if len(data) == 0:
        break
    if rec.AcceptWaveform(data):
        result = json.loads(rec.Result())
        if 'result' in result:
            all_words.extend(result['result'])
final = json.loads(rec.FinalResult())
if 'result' in final:
    all_words.extend(final['result'])

# all_words = [{ "word": "breathe", "start": 25.53, "end": 25.89 }, ...]
```

**This method requires zero human timing input.** The only human review is a listen-through to confirm the mix sounds right.

**Alternative tool:** ElevenLabs Forced Alignment API (returns word-level timestamps from TTS output). Works similarly but requires API access. Vosk is preferred because it runs offline, is free, and has been production-tested.

#### 2.2.1 CRITICAL: Cue Word Disambiguation

**Problem discovered in M2 production:** Cue words like "breathe," "hold," and "release" can appear multiple times in a script — some as descriptive mentions, some as actual breathing instructions. Naive pattern matching picks the FIRST occurrence, which may be wrong.

**Example (M2 script):** The word "breathe" appears 4 times:
1. "the long **breath** out is where the magic is" — descriptive, NOT a cue
2. "all you have to do is **breathe** along" — setup, NOT a cue
3. "**Breathe** in... 2, 3, 4" — C1 inhale instruction ← ACTUAL CUE
4. "**Breathe** in... 2, 3, 4" — C2 inhale instruction ← ACTUAL CUE

**Solution:** Use script-level cue markers (§2.2.2) to identify WHICH occurrence of a cue word is the actual cue. The pipeline reads the markers to know the Nth occurrence is the target, then uses vosk timestamps to find its exact time.

**Rule:** NEVER place a tone at the first occurrence of a cue word without verifying it against the script cue markers. Always count occurrences.

#### 2.2.2 Script-Level Audio Cue Markers

Embed audio cue markers directly in meditation scripts. These markers are the SINGLE SOURCE OF TRUTH for where sounds go. They are consumed by the automated pipeline and ignored by ElevenLabs TTS (they're removed before sending to TTS).

**Marker syntax:**
- `{{INHALE_CUE}}` — place inhale wind sound here
- `{{EXHALE_CUE}}` — place exhale wind sound here
- `{{BELL_CUE}}` — place transition bell here
- `{{NOTICING_CUE}}` — place noticing tone here
- `{{PAUSE:Xs}}` — silent pause of X seconds

**Placement rule:** The cue marker goes on the line BEFORE the narration it accompanies. The tone starts at the same moment the narrator begins speaking that line.

**Example (M2 Cycle 1):**
```
Here we go.

{{INHALE_CUE}}
Breathe in... 2, 3, 4

Hold it... 2, 3, 4, 5, 6, 7

{{EXHALE_CUE}}
Release... 2, 3, 4, 5, 6, 7, 8
```

**Pipeline integration:** The pipeline strips `{{...}}` markers before sending to TTS, but records which narration line each marker precedes. After vosk returns word timestamps, the pipeline finds the first word of that narration line and places the tone there.

**QA check (add to Guardrails):** Every breathing cycle must have `{{INHALE_CUE}}` and `{{EXHALE_CUE}}` markers. No orphaned markers.

#### 2.3 Method C: Hybrid (Recommended for First Modules)

Use automated extraction to generate initial timestamps, then human-verify with the Cue Point Mapper. This builds confidence in the automation before removing the human from the loop.

### Step 3: Assign breathCycle Rhythms

**Input:** Cue point timestamps
**Output:** Complete cue point array with rhythm durations

For breathing modules (M1, M2, M11, M12), each breathing cue becomes a `breathCycle` with standardized timing:

1. **Identify the script section** each cue falls in (Instruction, Deepening, etc.)
2. **Assign the standard rhythm** for that section (see table in §1.3)
3. **Run overlap check** — compute every gap between cycle end and next cycle start
4. **Adjust if needed** — shorten Deepening rhythms or shift cycle start times

For non-breathing modules (M3, M4, M5, etc.), cues are simpler:
- `noticing` cues fire a single tone (no rhythm)
- `bowlStrike` cues fire a single strike (no rhythm)
- `stepTransition` cues fire between process steps
- See Audio Engine Architecture §2.4 for the full CueType enum

### Step 4: Validate in Demo (Optional but Recommended)

**Input:** Voice stem MP3 + cue points + accent sounds + ambient bed
**Output:** Subjective confirmation that timing feels right

Load all elements into the Phase B demo JSX (v8+):
1. Voice stem → Voice Stem upload panel
2. Ambient bed → Ambient Bed upload panel
3. Accent sounds are embedded (bell, inhale, exhale, noticing)

Play through and verify:
- [ ] Inhale sounds fire when narrator says "Breathe in" (within ~0.5s)
- [ ] Exhale sounds fire at a natural offset — NOT necessarily when narrator says "out"
- [ ] Hold gap between inhale and exhale feels like a real breath pause
- [ ] No breath cycles overlap
- [ ] Bell leads voice by 2-3 seconds (comfortable threshold)
- [ ] Ambient bed is felt but not distracting
- [ ] Landing feels like a moment of recognition
- [ ] A 7-year-old would feel safe

**If timing is off:** Adjust cue point times or rhythm durations, NOT the voice stem. The voice is the master; everything else adapts to it.

### Step 5: Mix to Flat MP3

**Input:** All audio assets + finalized cue points + volume settings
**Output:** Single self-contained MP3 file

#### 5.1 Track Layout

The mixing script assembles these tracks:

```
Track 1: VOICE STEM
  ├─ Delay: {VOICE_START}s from file start (default 5s)
  ├─ Volume: 1.0
  └─ The timing master — everything references this

Track 2: AMBIENT BED (looped)
  ├─ Start: 0.5s (before bell, before voice)
  ├─ Volume: 0.08
  ├─ Fade in: 4s
  ├─ Fade out: starts at EXIT cue, 8s duration
  └─ Looped from a 30s source to cover full duration

Track 3: TRANSITION BELL
  ├─ Time: VOICE_START - 3s (bell strike leads voice by 3s)
  ├─ Volume: 0.50
  └─ Single strike, natural decay

Tracks 4-N: BREATH SOUNDS (one inhale + one exhale per cycle)
  ├─ Inhale time: VOICE_START + cue.t
  ├─ Inhale volume: 0.30
  ├─ Exhale time: VOICE_START + cue.t + cue.inDur + cue.holdDur
  ├─ Exhale volume: 0.55
  └─ Each cycle generates two track instances
```

#### 5.2 Timeline Structure

```
0.0s ─── Ambient bed begins fading in
2.0s ─── Bell strikes (VOICE_START - 3)
5.0s ─── Voice enters (VOICE_START)
         ├── Welcome
         ├── Connection
         ├── Setup
         ├── Instruction (breath cycles 1-2, guided rhythm)
         ├── Deepening (breath cycles 3-N, natural rhythm)
         ├── Landing ("that's your magic")
         └── Exit ("stay right there")
~89s ─── Exit cue → ambient bed begins 8s fade-out
~97s ─── Ambient bed reaches silence
~100s── File ends (pad 3s of silence after bed fade)
```

#### 5.3 The Mixing Script

The M1 mix was produced with an ffmpeg-based Python script. The pattern for any breathing module:

```python
# Core parameters (adjust per module)
VOICE_START = 5.0           # seconds of bed+bell lead-in
BELL_TIME = VOICE_START - 3 # bell strikes 3s before voice
EXIT_TIME = VOICE_START + exit_cue_time
TOTAL_DUR = EXIT_TIME + 10  # room for bed fade-out

# Breath cycles from cue points
cycles = [
    {"t": 26.7, "inDur": 4, "holdDur": 2, "outDur": 5},
    {"t": 44.3, "inDur": 4, "holdDur": 2, "outDur": 5},
    # ... etc
]

# ffmpeg approach:
# 1. Split inhale input into N copies (one per cycle)
# 2. Split exhale input into N copies (one per cycle)
# 3. Delay each copy to its absolute time (VOICE_START + cue.t)
# 4. Set volume on each track
# 5. Mix all tracks with amix
# 6. Apply limiter to prevent clipping
# 7. Export as MP3 at 192kbps
```

See `/home/claude/mix_m1.py` for the complete working script. Future modules replace only the cycle array and file paths — the mixing logic is identical.

#### 5.4 Output Naming Convention

```
M{module_number}_phase_b_complete_mix.mp3
```

Examples: `M1_phase_b_complete_mix.mp3`, `M2_phase_b_complete_mix.mp3`

---

## PART 3: SOUND LIBRARY

### 3.1 Shared Assets (Built Once, Used Forever)

These files are generated once using the ElevenLabs Sound Recipe and never touched again:

| Asset | File | Used By | Duration |
|---|---|---|---|
| Transition bell | `bell_transition.wav` | All modules | ~5s |
| Inhale wind | `breath_inhale.wav` | M1, M2, M11, M12 | ~4s |
| Exhale wind | `breath_exhale.wav` | M1, M2, M11, M12 | ~4s |
| Noticing tone | `tone_noticing.wav` | M3, M13 | ~2s |
| Calm ambient bed | `bed_calm.wav` | M1, M2 | 30s loop |
| Focus ambient bed | `bed_focus.wav` | M3, M4 | 30s loop |
| Heart ambient bed | `bed_heart.wav` | M5, M6 | 30s loop |
| Brave ambient bed | `bed_brave.wav` | M7, M8 | 30s loop |
| Grounding ambient bed | `bed_grounding.wav` | M9, M11 | 30s loop |
| Rest ambient bed | `bed_rest.wav` | M12, M13 | 30s loop |

See ElevenLabs Sound Recipe v1 for exact generation prompts.

### 3.2 Per-Module Assets (One Per Module)

| Asset | Generation Method | Cost |
|---|---|---|
| Voice stem | ElevenLabs TTS from approved script | ~$0.50 in API credits |

That's it. One file per module. Everything else is shared.

### 3.3 ElevenLabs SFX Prompts for Breath Sounds

> **SFX v2 NOTE (March 2026):** ElevenLabs SFX v2 is now available on existing subscriptions. The breath sound prompts below were developed on the original SFX model. SFX v2 uses the same prompt interface but with improved audio quality and directional accuracy. **Re-generate the shared breath sound library using v2 when moving into Arc 2+ production** — the improved accuracy should reduce the 10+ candidate generation requirement. Use the same prompts below; no changes needed.
>
> SFX v2 also covers all Everdale world ambient sound design (per-arc homeland ambient beds, runestone tones, spell cast audio, creature audio signatures). See VPG §3.3 and ECOSYSTEM_INTEGRATION_STRATEGY §2.8 for full world sound design scope and prompt patterns.

Breath sounds are directionally specific. The key is making the direction unambiguous:

**Inhale (air drawn IN):**
```
Sound of air being slowly drawn inward through the nose, gentle sustained
suction pulling air in, 3 seconds, starts from silence and builds as lungs
fill, rising energy, gathering inward. Like wind being pulled into a cave
mouth — air rushing gently inward not outward. Soft organic warmth, clearly
audible, not faint. No blowing out, no release, no settling. This is air
coming IN. No music, no reverb.
```

**Exhale (air blown OUT):**
```
Sound of air being slowly blown outward through softly parted lips, gentle
sustained blowing out, 4 seconds, starts full and gradually fades as lungs
empty, falling energy, releasing outward. Like a long slow blow across a
candle flame without extinguishing it — air pushing gently away from the
mouth. Soft organic warmth, clearly audible, not faint. No sucking in, no
gathering. This is air going OUT, a slow blow. No music, no reverb.
```

**Critical learning:** ElevenLabs often reverses inhale/exhale direction. The words "drawn inward" / "suction pulling in" vs. "blown outward" / "pushing away from the mouth" are the clearest directional anchors. Generate 10+ candidates and verify direction by ear.

**Volume balancing:** Exhale sounds are typically softer than inhale sounds from the same generation session. Boost exhale volume to ~1.8× inhale volume to achieve perceptual balance.

---

## PART 4: AUTOMATION PIPELINE

### 4.1 The Full Automated Flow

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: Script exists (from Production Process)                  │
│         Input: Approved markdown script WITH cue markers         │
│         Output: Script text ready for TTS (markers stripped)     │
│                                                                  │
│ Step 2: TTS generation (ElevenLabs API)                          │
│         Input: Script text + voice ID + voice settings           │
│         Output: Voice stem MP3 + audio duration                  │
│         Cost: ~$0.50 per module                                  │
│                                                                  │
│ Step 3: Cue point extraction (Vosk STT — proven)                 │
│         Input: Voice stem WAV + script cue markers               │
│         Method: Vosk word timestamps + marker disambiguation     │
│         Output: Exact timestamps for each cue word               │
│         CRITICAL: Uses §2.2.1 disambiguation to match the        │
│         correct occurrence of each cue word                      │
│                                                                  │
│ Step 4: Rhythm assignment (deterministic rules)                  │
│         Input: Cue timestamps + module metadata (type, domain)   │
│         Method: Assign standard breathCycle rhythms per phase     │
│         Output: Complete cuePoints[] array                       │
│         Validation: Overlap check (automatic)                    │
│                                                                  │
│ Step 5: Mix to MP3 (ffmpeg script)                               │
│         Input: Voice stem + shared library + cuePoints           │
│         Method: Multi-track mix with delays + volumes             │
│         Output: M{n}_phase_b_complete_mix.mp3                    │
│                                                                  │
│ Step 6: Generate phaseBMixConfig JSON (deterministic)            │
│         Input: cuePoints + domain + voice duration               │
│         Output: JSON config for runtime player engine             │
│                                                                  │
│ TOTAL HUMAN INPUT: Review listen-through (5 minutes)             │
│ TOTAL COST: ~$0.50 per module                                    │
│ TOTAL TIME: ~2 minutes compute + 5 minutes review                │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 What Requires the Shared Sound Library

The shared library (§3.1) must be built once before any automated module production. This is a one-time ~$22 cost (one month of ElevenLabs Creator plan) and ~8-12 hours of generation and selection.

After the library exists:
- Steps 2-6 above are fully automated per module
- New modules beyond the original 12 cost exactly one TTS generation + one mix
- The library covers all 6 domains and all functional sound types

### 4.3 What Makes breathCycle Automatable

The rhythm-lock pattern is what enables full automation. Without it, a human would need to mark every individual inhale AND exhale moment in every voice stem. With it:

1. Vosk STT finds every word's timestamp in the voice stem
2. Script cue markers (`{{INHALE_CUE}}`) identify which word occurrence is the actual cue
3. Standard rhythm (inDur + holdDur + outDur) is applied automatically based on script section
4. Overlap check runs automatically
5. Zero human timing input required

**WARNING:** Step 2 is critical. Without cue markers, naive pattern matching on "Breathe in" will match the FIRST occurrence, which may be a descriptive mention (e.g., "the long breath out is where the magic is") rather than the actual instruction. This caused an 8-second timing error in M2 production. See §2.2.1.

### 4.4 Extending to Non-Breathing Modules

Non-breathing modules (M3-M9, M12-M13) are simpler to automate because their cue types are instantaneous events, not rhythmic cycles:

| Module Type | Cue Pattern | Automation |
|---|---|---|
| Breathing (M1, M2) | breathCycle with rhythm | Pattern match + rhythm table |
| Observation (M3, M13) | Noticing tone at observation prompts | Pattern match on "notice" / "watch" / "there" |
| Singing bowl (M4) | Bowl strike at focus points | Pattern match on "[bowl strike]" stage directions |
| Compassion (M5, M6) | Warmth tones at expansion points | Pattern match on "send warmth" / "someone you love" |
| Anxiety wave (M7) | Tension rise/peak/fall | Pattern match on "building" / "the top" / "coming down" |
| Containment (M8) | Step transitions + sealing | Pattern match on "Now..." / "seal it" |
| Body awareness (M9, M11, M12) | Sense/body shifts + squeeze/release | Pattern match on body part + action words |

All patterns are already defined in Audio Engine Architecture §6.2. The automation logic is identical: find the phrase in vosk STT word timestamps → disambiguate using script cue markers → fire the cue type → apply default volume for that type.

---

## PART 5: WORKING WITH CLAUDE — CONTEXT EFFICIENCY

### 5.1 The Space Problem

Audio files are large. A single MP3 voice stem is ~1.5MB. Base64-encoding for JSX embedding inflates that ~33%. Keeping audio data in conversation context wastes tokens and risks hitting limits.

### 5.2 Rules for Claude Sessions

These rules are documented in CLAUDE_WORKING_RULES.md and repeated here for completeness:

1. **NEVER read base64 audio into conversation context.** Always work with audio programmatically on disk.
2. **To build the playable JSX demo:** Use a Python script that reads the slim JSX from disk, base64-encodes each MP3 on disk, injects into the EMBEDDED block on disk, and writes the full playable JSX to disk. This keeps ~400K+ of audio data out of the conversation.
3. **To mix a flat MP3:** Use an ffmpeg-based Python script on disk. Source files stay on disk. Only the script logic is in the conversation.
4. **File locations:** Uploaded MP3s are in `/mnt/user-data/uploads/`. Build scripts work in `/home/claude/`. Final outputs go to `/mnt/user-data/outputs/`.

### 5.3 The Build Scripts

Two Python scripts handle all assembly:

**`build_v8.py`** — Builds the playable JSX demo
- Reads slim JSX from disk
- Base64-encodes 4 accent MP3s (bell, inhale, exhale, noticing)
- Optionally base64-encodes voice stem
- Injects into EMBEDDED constant
- Writes playable JSX to outputs

**`mix_m1.py`** — Mixes flat MP3 (template for all modules)
- Takes voice stem + shared library + cue points
- Constructs ffmpeg filter graph with delays, volumes, splits, and amix
- Outputs single MP3 at 192kbps
- Replace only the cycle array and file paths per module

### 5.4 What the Demo JSX Is For

The demo JSX is an **engineering prototype**, not the production deliverable. It exists to:

- Validate cue point timing interactively
- Test volume balances with real-time sliders
- Preview the breath cycle rhythm
- Demonstrate the audio engine architecture to stakeholders

It is NOT:
- The format shipped to users (that's the runtime player engine + pre-baked fallback)
- A space-efficient delivery format (it embeds base64 audio)
- Necessary for every module (once the pipeline is automated, the flat MP3 and JSON config are sufficient)

---

## PART 6: MODULE-SPECIFIC NOTES

### 6.1 M1 — Belly Breathing (Completed)

| Attribute | Value |
|---|---|
| Voice | Myrrdin (ElevenLabs voice library) |
| Duration | 91.5s voice + 5s lead-in + 8s fade-out = ~104s total |
| Breath cycles | 4 (2 Instruction, 1 Deepening, 1 "One more") |
| Instruction rhythm | 4s in + 2s hold + 5s out = 11s |
| Deepening rhythm | 3s in + 1s hold + 4s out = 8s |
| Cue points mapped | Human (Cue Point Mapper tool) |
| Ambient bed | Wooden flute loop (placeholder — replace with generated Calm domain bed) |

**Finalized cue times (absolute, from voice start):**

| Cue | Time | Type |
|---|---|---|
| Bell | -3.0s | bell (fires at 2.0s absolute) |
| Cycle 1 | 26.7s | breathCycle (Instruction) |
| Cycle 2 | 44.3s | breathCycle (Instruction) |
| Cycle 3 | 58.5s | breathCycle (Deepening) |
| Cycle 4 | 73.0s | breathCycle ("One more") |
| Exit | 88.6s | exit |

### 6.2 M2 — 4-7-8 Calm Down (Completed)

| Attribute | Value |
|---|---|
| Voice | Myrrdin (ElevenLabs voice library) |
| Duration | 76.4s voice + 3s lead-in + 8.6s tail = 88s total |
| Breath cycles | 2 complete 4-7-8 cycles (guide counts aloud) |
| Cue pattern | Separate inhale/exhale cues (not breathCycle rhythm) — counting IS the rhythm |
| Cue points mapped | Vosk STT with word-level timestamps (Method B) |
| Ambient bed | Wooden flute loop #3 at 0.08 gain (lighter than M1's 0.20 — reduces cognitive load) |

**Finalized cue times (absolute, in final mix timeline):**

| Cue | Time | Type | Vosk Source Word |
|---|---|---|---|
| Bell | 0.0s | bell | — |
| Ambient bed start | 1.0s | ambient | — |
| Voice start | 3.0s | voice | — |
| C1 Inhale tone | 28.53s | inhale | "Breathe" (3rd occurrence, at script line "Breathe in... 2, 3, 4") |
| C1 Exhale tone | 38.64s | exhale | "release" (1st occurrence, at script line "Release... 2, 3, 4, 5, 6, 7, 8") |
| C2 Inhale tone | 51.21s | inhale | "Breathe" (4th occurrence, at script line "Breathe in... 2, 3, 4") |
| C2 Exhale tone | 61.35s | exhale | "release" (2nd occurrence) |

**Key learnings from M2 production:**

1. **Vosk STT is essential for cue placement.** Waveform energy analysis cannot distinguish between words — it maps speech onsets but cannot tell "breathe" (descriptive) from "Breathe in" (instruction). The word "breathe" appeared 4 times in M2's script; naive matching placed the tone 8 seconds early on the wrong occurrence.

2. **Script cue markers prevent disambiguation errors.** Adding `{{INHALE_CUE}}` and `{{EXHALE_CUE}}` markers to the script before TTS generation tells the pipeline exactly which occurrence of a cue word is the actual cue.

3. **Lighter ambient bed preferred.** 0.08 gain (vs M1's 0.20) was judged easier to focus on by Kim. Adopted as new default.

4. **2 cycles not 3 in production.** The produced version uses 2 cycles (not the 3 in the original script draft). "The air feels different now" was removed from the transition to avoid non-experiential language.

5. **Counting as whole phrases.** ElevenLabs produces better prosody when generating "Breathe in... 2, 3, 4" as one sentence rather than individual number clips. Individual clips sound mechanical.

6. **"The air feels different now" removed.** This phrase was cut from M2's transition because it tells the child what to feel rather than letting them discover it. The produced version uses "Good. One more." between cycles instead.

---

## PART 7: CHECKLIST

### Per-Module Audio Production Checklist

- [ ] Script approved (Production Process complete)
- [ ] Script contains audio cue markers (`{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, etc.) — see §2.2.2
- [ ] Voice stem generated (ElevenLabs TTS, 3 takes, best selected)
- [ ] Voice stem duration within expected range
- [ ] Cue points mapped via vosk STT (Method B) with disambiguation verified
- [ ] breathCycle rhythms assigned per section (breathing modules) or cue types assigned (other modules)
- [ ] Overlap check passed (all gaps ≥ 0)
- [ ] Demo validation (interactive JSX playback — optional but recommended)
- [ ] Volume balance confirmed (voice clear, breath sounds present, bed at 0.08)
- [ ] Flat MP3 mixed (ffmpeg script)
- [ ] phaseBMixConfig JSON generated (for runtime engine)
- [ ] Listen-through by Kim (final approval)

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial guide. Complete pipeline from approved script to mixed MP3. breathCycle pattern with rhythm-locked timing. Volume architecture from M1 production. Automation pathway via Forced Alignment API. ElevenLabs SFX prompts for directional breath sounds. Context efficiency rules for Claude sessions. M1 production notes with finalized cue times. |
| 1.1 | February 23, 2026 | Clarified scope: guide covers all module types, not just breathing. Breathing modules are the initial worked example. Module-specific notes section (Part 6) to be extended as each module type is produced. |
| 1.2 | February 23, 2026 | M2 production complete. New rules: (1) ffmpeg `amix normalize=0` + `volume=2.0` + `alimiter` required to prevent quiet mixes. (2) Preamble replaces count one for counted breathing. (3) TTS punctuation rule. (4) Bell timing varies per module. (5) Ambient bed rotation within measuring bar families. Updated volume defaults. |
| 1.4 | March 13, 2026 | BUILT FROM: v1.3. Pipeline tool amendments from March 2026 AI landscape review. §1.3: ElevenLabs v3 Audio Tags directive added with tag table, usage example, and PVC CAVEAT for Myrrdin (test before batch). §2.2: ElevenLabs Scribe v2 noted as candidate upgrade for cue extraction — Vosk remains primary until head-to-head test run. §3.3: SFX v2 note added — re-generate shared breath sound library with v2 at Arc 2+ production; world ambient sound design scope cross-referenced to VPG §3.3 and ECOSYSTEM §2.8. Source: PIPELINE_AMENDMENTS_v1.md. |
| 1.3 | February 24, 2026 | **Breaking change: vosk STT replaces waveform analysis for cue point mapping.** Method B rewritten from speculative ElevenLabs Forced Alignment to proven vosk pipeline. New §2.2.1 Disambiguation Rule (cue words can appear multiple times — must count occurrences). New §2.2.2 Script-Level Audio Cue Markers spec (`{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, etc.). Ambient bed default lowered from 0.20 to 0.08. M2 module notes completed with vosk-verified cue times. Checklist updated to require cue markers and vosk. "The air feels different now" removed from M2 transition. |

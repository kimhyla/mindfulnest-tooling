# Phase B Audio Engine Architecture
## Version 1.1 — February 24, 2026

**Purpose:** Define how the module player assembles rich, layered Phase B meditation audio at runtime from a voice stem + reusable sound library + cue point metadata. This replaces pre-baked single-file audio with a dynamic mixing system that scales to any number of modules with zero manual audio production per module.

**Key insight:** The voice stem is the only per-module unique audio asset. Everything else — ambient beds, functional sounds, transitions — is drawn from a shared library and triggered by cue point metadata.

**Dependencies:**
- Canonical Data Model v1.1 (frozen — this document proposes additions)
- Module JSON Schema Guardrails v2 (this extends `guidedAudioRef`)
- Phase B Sound Design Vision v1 (sonic principles)
- Phase B Sound Production Brief v1 (generation recipes)

---

## PART 1: THE CORE IDEA

### Before (Single File)
```
guidedAudioRef: "audio/guided/m2_calm_down.mp3"
                ↓
        [ Player plays one file ]
```

### After (Dynamic Mix)
```
phaseBVoiceStem: "audio/stems/m2_voice.mp3"
phaseBMixConfig: { domain, cuePoints[] }
                ↓
        [ Player loads voice stem ]
        [ Player selects ambient bed from domain ]
        [ Player reads cue points ]
        [ Player triggers library sounds at cue times ]
        [ Player mixes all layers in real-time ]
```

### Why This Is Better
1. **Automated module generation:** AI writes script → TTS generates voice → AI identifies cue points from script text → done. No audio production.
2. **Consistency:** Every module in a domain shares the same sonic palette automatically.
3. **Updatability:** Improve an ambient bed once → all modules in that domain improve.
4. **Personalization potential (v2+):** Adjust ambient bed volume per child preference. Disable functional sounds for sensory-sensitive children. Adjust pacing.
5. **One-time sound library:** ~35 audio files cover all 12 modules forever. Each new module beyond 12 costs exactly one TTS generation.

### TTS Personalization Integration

The `phaseBVoiceStem` URL may point to either:
- **Universal stem** (`audio/universal/m1_phaseB_body.mp3`) — shared by all children. Used for the meditation body (no `{childName}`).
- **Per-child stem segments** (`audio/children/{childId}/m1_phaseB_opening.mp3`) — personalized opening/closing lines containing `{childName}`.

At playback, the audio engine assembles: per-child opening → universal body → per-child closing, with ~50ms crossfades between segments. The mixing engine (ambient bed + cue points + functional SFX) operates on the assembled stream identically to the current single-stem model.

**Cue point stability:** Because `{childName}` appears only in the opening line (before first cue point) and closing line (after last cue point), universal cue points remain valid for all children. No per-child cue point recalculation is needed.

**Full spec:** See `TTS_PERSONALIZATION_PIPELINE_v1.md` §6 for the complete Phase B personalization architecture.

---

## PART 2: SCHEMA ADDITIONS

### 2.1 Changes to Module JSON

The existing `guidedAudioRef` field is **preserved for backward compatibility** (it can point to a pre-baked mix for v1 fallback). Two new fields are added:

```typescript
// Existing field (unchanged)
guidedAudioRef: string;  // "audio/guided/m2.mp3" — fallback single file

// New fields
phaseBVoiceStem: string; // "audio/stems/m2_voice.mp3" — isolated voice
phaseBMixConfig: PhaseBMixConfig; // mixing instructions
```

### 2.2 PhaseBMixConfig Schema

```typescript
interface PhaseBMixConfig {
  // Domain determines ambient bed + shimmer tinting
  domain: "calm" | "focus" | "heart" | "brave" | "grounding" | "rest";

  // Total duration of voice stem in seconds (for player timing)
  voiceDurationSeconds: number;

  // Ambient bed behavior
  ambient: {
    // Fade in X seconds before voice starts
    fadeInLeadSeconds: number;  // default: 3
    // Volume relative to voice (0.0 - 1.0)
    volume: number;             // default: 0.08 (lowered from 0.15 — Feb 24 production testing)
  };

  // Ordered list of cue points synchronized to voice stem
  cuePoints: CuePoint[];
}
```

### 2.3 CuePoint Schema

```typescript
interface CuePoint {
  // Seconds into the voice stem when this cue fires
  time: number;

  // What kind of sonic event to trigger
  type: CueType;

  // Which cycle this belongs to (for progressive scaling)
  // null for non-cyclical cues
  cycle?: number;

  // Total cycles in the module (for calculating progression)
  // Only needed on the first cue point that has a cycle value
  totalCycles?: number;

  // Duration hint in seconds (for tones that need to sustain)
  // null for instantaneous sounds (shimmers, strikes)
  durationSeconds?: number;

  // Optional override for specific modules with unusual needs
  volumeOverride?: number;  // 0.0 - 1.0, overrides default for this type
}
```

### 2.4 CueType Enum — Complete Definition

```typescript
type CueType =
  // ─── UNIVERSAL (all modules) ───────────────────────────
  | "phaseStart"        // Transition bell
  | "landing"           // Landing shimmer
  | "exit"              // Signal to begin fade to Rescue

  // ─── BREATHING (M1, M2) ───────────────────────────────
  | "inhale"            // Rising breath-sync tone
  | "hold"              // Sustained breath-sync tone (M2 only)
  | "exhale"            // Descending breath-sync tone
  | "cycleEnd"          // Exhale shimmer (progressive)

  // ─── OBSERVATION (M3, M13) ────────────────────────────
  | "spacer"            // Extended silence — ambient only
  | "noticing"          // Gentle awareness marker tone

  // ─── SINGING BOWL (M4) ───────────────────────────────
  | "bowlStrike"        // Singing bowl ring + decay

  // ─── EXPANSION (M5) ──────────────────────────────────
  | "warmthSelf"        // Warmth tone — inner (smallest)
  | "warmthLoved"       // Warmth tone — expanding
  | "warmthDifficult"   // Warmth tone — widest expansion

  // ─── STEP PROCESS (M6, M8) ───────────────────────────
  | "stepTransition"    // Soft marker between process steps
  | "containment"       // Satisfying closing/sealing sound (M8)

  // ─── TENSION ARC (M7) ────────────────────────────────
  | "tensionRise"       // Gradually ascending tension tone
  | "tensionPeak"       // Brief intensity peak
  | "tensionFall"       // Resolving descent

  // ─── BODY AWARENESS (M9, M11, M12) ──────────────────
  | "senseShift"        // Attention shifts between senses (M9)
  | "bodyRegionShift"   // Attention moves to new body area (M12)
  | "squeeze"           // Tension/squeeze tone (M11)
  | "release"           // Release/opening tone (M11)
  ;
```

---

## PART 3: SOUND LIBRARY MANIFEST

### 3.1 Universal Sounds

| ID | File | Description | Duration | Used By |
|---|---|---|---|---|
| `bell_transition` | `lib/universal/bell_transition.wav` | Resonant singing bowl strike, warm decay | 5s | All 12 modules |
| `shimmer_landing_calm` | `lib/shimmers/landing_calm.wav` | Landing shimmer, warm tint | 2s | M1, M2 |
| `shimmer_landing_focus` | `lib/shimmers/landing_focus.wav` | Landing shimmer, clean tint | 2s | M3, M4 |
| `shimmer_landing_heart` | `lib/shimmers/landing_heart.wav` | Landing shimmer, rich tint | 2s | M5, M6 |
| `shimmer_landing_brave` | `lib/shimmers/landing_brave.wav` | Landing shimmer, grounded tint | 2s | M7, M8 |
| `shimmer_landing_grounding` | `lib/shimmers/landing_grounding.wav` | Landing shimmer, earthy tint | 2s | M9, M11 |
| `shimmer_landing_rest` | `lib/shimmers/landing_rest.wav` | Landing shimmer, softest tint | 2s | M12, M13 |

### 3.2 Ambient Beds (one per domain, looping)

| ID | File | Character | Duration |
|---|---|---|---|
| `bed_calm` | `lib/beds/calm.wav` | Warm golden pad, D major, minimal movement | 30s loop |
| `bed_focus` | `lib/beds/focus.wav` | Clear sky, higher register, spacious silence | 30s loop |
| `bed_heart` | `lib/beds/heart.wav` | Warmest palette, rich/full, subtle pulse | 30s loop |
| `bed_brave` | `lib/beds/brave.wav` | Grounded, low anchor, steady presence | 30s loop |
| `bed_grounding` | `lib/beds/grounding.wav` | Most physical, earth tones, sub-bass | 30s loop |
| `bed_rest` | `lib/beds/rest.wav` | Quietest, slow low pad, vast silence | 30s loop |

### 3.3 Breathing Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `breath_inhale` | `lib/breath/inhale.wav` | Gentle rising tone, warm sine quality | 5s |
| `breath_hold` | `lib/breath/hold.wav` | Sustained warm tone, slight bloom | 8s |
| `breath_exhale` | `lib/breath/exhale.wav` | Descending tone, breathy wind texture | 9s |
| `exhale_shimmer_1` | `lib/breath/exhale_shimmer_1.wav` | Barely-there single crystalline tone | 1s |
| `exhale_shimmer_2` | `lib/breath/exhale_shimmer_2.wav` | Two-tone gentle sparkle | 1s |
| `exhale_shimmer_3` | `lib/breath/exhale_shimmer_3.wav` | Three-four tone crystalline cascade | 1.5s |

### 3.4 Observation Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `noticing_tone` | `lib/observation/noticing.wav` | Gentle single tone, "there — you noticed" | 1.5s |

Note: `spacer` type triggers no sound — it's a player instruction to maintain ambient bed only for the specified duration. The absence of voice IS the design.

### 3.5 Singing Bowl

| ID | File | Description | Duration |
|---|---|---|---|
| `bowl_strike` | `lib/bowl/strike.wav` | Full singing bowl ring with long natural decay | 15s |

Note: M4 may need multiple bowl strikes at different volumes. The player handles volume variation; only one file needed.

### 3.6 Heart / Expansion Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `warmth_inner` | `lib/heart/warmth_inner.wav` | Warm tone, close, intimate | 3s |
| `warmth_expanding` | `lib/heart/warmth_expanding.wav` | Same tone, wider stereo, richer | 3s |
| `warmth_widest` | `lib/heart/warmth_widest.wav` | Full warmth, widest stereo spread | 3s |

### 3.7 Step Process Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `step_marker` | `lib/steps/marker.wav` | Soft transitional tone between process steps | 1.5s |
| `containment_close` | `lib/steps/containment.wav` | Satisfying closing/sealing sound — like a lid settling | 2s |

### 3.8 Tension Arc Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `tension_rise` | `lib/arc/rise.wav` | Slowly ascending tone, building presence | 10s |
| `tension_peak` | `lib/arc/peak.wav` | Brief intensity moment, then immediate softening | 2s |
| `tension_fall` | `lib/arc/fall.wav` | Resolving descent, opening, releasing | 10s |

### 3.9 Body Awareness Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `sense_shift` | `lib/body/sense_shift.wav` | Subtle attention-directing marker (distinct from step_marker — lighter, more "focus here") | 1s |
| `body_region_shift` | `lib/body/region_shift.wav` | Very subtle downward settling tone (attention moving through body) | 1s |
| `squeeze_tone` | `lib/body/squeeze.wav` | Gently tightening tone, building pressure | 4s |
| `release_tone` | `lib/body/release.wav` | Opening, releasing tone — contrast to squeeze | 3s |

### 3.10 Library Totals

| Category | Files | One-Time Production |
|---|---|---|
| Universal (bell + shimmers) | 7 | ✅ |
| Ambient beds | 6 | ✅ |
| Breathing | 6 | ✅ |
| Observation | 1 | ✅ |
| Singing bowl | 1 | ✅ |
| Heart / expansion | 3 | ✅ |
| Step process | 2 | ✅ |
| Tension arc | 3 | ✅ |
| Body awareness | 4 | ✅ |
| **TOTAL** | **33 files** | **One-time build** |

---

## PART 4: PLAYER MIXING RULES

### 4.1 Layer Architecture

The player maintains 4 audio channels that are mixed together in real-time:

```
Channel 1: VOICE STEM          — always playing, always loudest
Channel 2: AMBIENT BED          — loops continuously, domain-selected
Channel 3: FUNCTIONAL TONES     — breath tones, tension arcs, warmth tones
Channel 4: ACCENT SOUNDS        — shimmers, markers, strikes, containment
```

### 4.2 Default Volume Table

All volumes relative to voice stem (1.0):

| Channel | Default Volume | Notes |
|---|---|---|
| Voice | 1.0 | Reference — never adjusted by engine |
| Ambient bed | 0.08 | Barely perceptible texture — reduces cognitive load for children (lowered from 0.15 based on M2 production testing) |
| Functional tones | 0.10 - 0.16 | Scales with cycle progression |
| Accent sounds | 0.12 - 0.20 | Landing shimmer loudest, exhale shimmer quietest |

### 4.3 Cycle Progression Rule

When cue points have `cycle` and `totalCycles` values, the player applies progressive scaling to functional tones and accent sounds within that cycle:

```
progressionFactor = 1.0 + (cycle - 1) * 0.3 / (totalCycles - 1)

// Example for 3 cycles:
// Cycle 1: factor = 1.0  (baseline)
// Cycle 2: factor = 1.15 (+15%)
// Cycle 3: factor = 1.3  (+30%)
```

Applied to:
- Functional tone volume: `baseVolume * progressionFactor`
- Exhale shimmer selection: `cycle` value selects which variant (`exhale_shimmer_1`, `_2`, or `_3`)
- Ambient bed: subtle warmth increase — `bedVolume * (1.0 + (cycle - 1) * 0.07)` (barely perceptible)

### 4.4 Cue Type → Sound Mapping

This table defines exactly what the player does when it encounters each cue type:

```
┌───────────────────┬──────────────────────┬────────┬──────────────┬──────────────────────────────────────────┐
│ CueType           │ Library Sound        │Channel │ Base Volume  │ Behavior                                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ phaseStart        │ bell_transition      │ 4      │ 0.40         │ Play once. Start ambient bed fade-in     │
│                   │                      │        │              │ simultaneously. Voice begins after bell   │
│                   │                      │        │              │ decay (~3s).                             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ landing           │ shimmer_landing_*    │ 4      │ 0.20         │ Play domain-tinted variant once.          │
│                   │ (domain-selected)    │        │              │ Select by phaseBMixConfig.domain.        │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ exit              │ (none)               │ —      │ —            │ Begin ambient bed fade-out over 10s.     │
│                   │                      │        │              │ Rescue audio takes over.                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ inhale            │ breath_inhale        │ 3      │ 0.10         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Apply cycle progression.                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ hold              │ breath_hold          │ 3      │ 0.10         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Apply cycle progression.                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ exhale            │ breath_exhale        │ 3      │ 0.12         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Apply cycle progression.                 │
│                   │                      │        │              │ Slightly louder than inhale (exhale is   │
│                   │                      │        │              │ the reward).                             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ cycleEnd          │ exhale_shimmer_*     │ 4      │ 0.08         │ Select variant by cycle number:           │
│                   │ (cycle-selected)     │        │              │   cycle 1 → shimmer_1 (0.08)             │
│                   │                      │        │              │   cycle 2 → shimmer_2 (0.12)             │
│                   │                      │        │              │   cycle 3 → shimmer_3 (0.16)             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ spacer            │ (none)               │ —      │ —            │ No action. Ambient bed continues.        │
│                   │                      │        │              │ The silence IS the experience.            │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ noticing          │ noticing_tone        │ 4      │ 0.12         │ Play once. Marks the moment of           │
│                   │                      │        │              │ awareness — the skill itself.             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ bowlStrike        │ bowl_strike          │ 3      │ 0.50         │ Play at high volume — the bowl IS        │
│                   │                      │        │              │ the meditation object. Child tracks      │
│                   │                      │        │              │ its natural decay. If cycle is set,      │
│                   │                      │        │              │ progressive volume decrease (each        │
│                   │                      │        │              │ successive strike softer — attention     │
│                   │                      │        │              │ training gets harder).                   │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ warmthSelf        │ warmth_inner         │ 3      │ 0.10         │ Play once. Intimate, close stereo.       │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ warmthLoved       │ warmth_expanding     │ 3      │ 0.13         │ Play once. Wider, warmer.                │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ warmthDifficult   │ warmth_widest        │ 3      │ 0.16         │ Play once. Widest, richest.              │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ stepTransition    │ step_marker          │ 4      │ 0.12         │ Play once. Soft boundary between         │
│                   │                      │        │              │ process steps.                           │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ containment       │ containment_close    │ 4      │ 0.18         │ Play once. The satisfying "closed"       │
│                   │                      │        │              │ moment. Slightly louder than markers     │
│                   │                      │        │              │ — this is a payoff.                      │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ tensionRise       │ tension_rise         │ 3      │ 0.10         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Gradually ascending. Volume ramps        │
│                   │                      │        │              │ from 0.10 to 0.18 over duration.         │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ tensionPeak       │ tension_peak         │ 3      │ 0.20         │ Play once. Brief intensity.              │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ tensionFall       │ tension_fall         │ 3      │ 0.18         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Gradually descending. Volume ramps       │
│                   │                      │        │              │ from 0.18 to 0.08 over duration.         │
│                   │                      │        │              │ The relief IS the therapeutic moment.     │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ senseShift        │ sense_shift          │ 4      │ 0.10         │ Play once. Very subtle.                  │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ bodyRegionShift   │ body_region_shift    │ 4      │ 0.08         │ Play once. Softest marker — attention    │
│                   │                      │        │              │ is already inward, don't interrupt.      │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ squeeze           │ squeeze_tone         │ 3      │ 0.12         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Gentle tightening quality.               │
│                   │                      │        │              │ Apply cycle progression (body region     │
│                   │                      │        │              │ cycles — each squeeze/release pair       │
│                   │                      │        │              │ goes slightly deeper).                   │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ release           │ release_tone         │ 3      │ 0.14         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Opening quality. Slightly louder than    │
│                   │                      │        │              │ squeeze — release is the reward.         │
│                   │                      │        │              │ Apply cycle progression.                 │
└───────────────────┴──────────────────────┴────────┴──────────────┴──────────────────────────────────────────┘
```

### 4.5 Ambient Bed Lifecycle

```
[phaseStart cue - 3s]    [phaseStart cue]              [exit cue]        [+10s]
        │                       │                           │                │
        ▼                       ▼                           ▼                ▼
   ┌─────────┐  ┌──────────────────────────────────────┐  ┌─────────┐
   │ Fade In │  │         Full Level (looping)          │  │Fade Out │
   │  3 sec  │  │                                       │  │ 10 sec  │
   └─────────┘  └──────────────────────────────────────┘  └─────────┘
                 ↑                                         ↑
           Bell strike                              Voice says "Stay
           + voice begins                           right there..."
```

The bed fades in BEFORE the voice starts (overlapping with the transition bell's decay). It loops continuously at the domain-selected volume. It begins fading out at the `exit` cue and continues fading during the Rescue transition. The Rescue stage may have its own ambient audio; the Phase B bed should be fully faded by the time Rescue audio begins.

### 4.6 Duration Trimming

Several cue types use `durationSeconds` to control how long a functional tone plays. The player trims (or time-stretches) the library sound to match:

- **If library sound is longer than `durationSeconds`:** Fade out at the specified time.
- **If library sound is shorter than `durationSeconds`:** Loop or stretch (implementation TBD — for v1, choose library sounds long enough that trimming is always the case).
- **If `durationSeconds` is null/missing:** Play the full library sound at its natural length.

### 4.7 Stereo Width (Future Enhancement)

Some cue types in the Sound Design Vision describe stereo width changes (exhale tones "opening" in the stereo field, warmth tones "expanding"). For v1, these are baked into the library sound files themselves. For v2, the player could apply real-time stereo width automation — but this is not required for launch.

---

## PART 5: WORKED EXAMPLES

### 5.1 Module 1 — Belly Breathing (Calm, Breathing)

```json
{
  "moduleId": "belly_breathing",
  "phaseBVoiceStem": "audio/stems/m1_belly_breathing_voice.mp3",
  "phaseBMixConfig": {
    "domain": "calm",
    "voiceDurationSeconds": 95,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 25,   "type": "inhale",   "cycle": 1, "totalCycles": 4, "durationSeconds": 4 },
      { "time": 32,   "type": "exhale",   "cycle": 1, "durationSeconds": 6 },

      { "time": 54,   "type": "inhale",   "cycle": 2, "durationSeconds": 3 },
      { "time": 59,   "type": "exhale",   "cycle": 2, "durationSeconds": 4 },

      { "time": 69,   "type": "inhale",   "cycle": 3, "durationSeconds": 3 },
      { "time": 74,   "type": "exhale",   "cycle": 3, "durationSeconds": 4 },

      { "time": 84,   "type": "inhale",   "cycle": 4, "durationSeconds": 3 },
      { "time": 89,   "type": "exhale",   "cycle": 4, "durationSeconds": 4 },
      { "time": 93,   "type": "cycleEnd", "cycle": 4 },

      { "time": 94,   "type": "landing" },
      { "time": 98,   "type": "exit" }
    ]
  }
}
```

**What the player does:**
1. At time -3s: Starts `bed_calm` fade-in + plays `bell_transition`
2. At time 0s: Voice begins
3. Times 25-93: Plays `breath_inhale` and `breath_exhale` with progressive volume scaling across 4 cycles. Cycle 4 exhale shimmer (`exhale_shimmer_3`) plays at the final `cycleEnd`.
4. Time 94: Plays `shimmer_landing_calm`
5. Time 98: Begins `bed_calm` fade-out over 10s

### 5.2 Module 2 — 4-7-8 Calm Down (Calm, Breathing + Hold)

```json
{
  "moduleId": "calm_down_478",
  "phaseBVoiceStem": "audio/stems/m2_calm_down_voice.mp3",
  "phaseBMixConfig": {
    "domain": "calm",
    "voiceDurationSeconds": 115,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 22,   "type": "inhale",   "cycle": 1, "totalCycles": 3, "durationSeconds": 4 },
      { "time": 26,   "type": "hold",     "cycle": 1, "durationSeconds": 7 },
      { "time": 34,   "type": "exhale",   "cycle": 1, "durationSeconds": 8 },
      { "time": 43,   "type": "cycleEnd", "cycle": 1 },

      { "time": 48,   "type": "inhale",   "cycle": 2, "durationSeconds": 4 },
      { "time": 52,   "type": "hold",     "cycle": 2, "durationSeconds": 7 },
      { "time": 60,   "type": "exhale",   "cycle": 2, "durationSeconds": 8 },
      { "time": 69,   "type": "cycleEnd", "cycle": 2 },

      { "time": 75,   "type": "inhale",   "cycle": 3, "durationSeconds": 5 },
      { "time": 80,   "type": "hold",     "cycle": 3, "durationSeconds": 9 },
      { "time": 89,   "type": "exhale",   "cycle": 3, "durationSeconds": 10 },
      { "time": 100,  "type": "cycleEnd", "cycle": 3 },

      { "time": 106,  "type": "landing" },
      { "time": 111,  "type": "exit" }
    ]
  }
}
```

### 5.3 Module 3 — Thought Clouds (Focus, Observation)

Completely different pattern — long silences, noticing markers, no breathing.

```json
{
  "moduleId": "thought_clouds",
  "phaseBVoiceStem": "audio/stems/m3_thought_clouds_voice.mp3",
  "phaseBMixConfig": {
    "domain": "focus",
    "voiceDurationSeconds": 100,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.12
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 18,   "type": "spacer",   "durationSeconds": 8 },
      { "time": 28,   "type": "noticing" },

      { "time": 38,   "type": "spacer",   "durationSeconds": 10 },
      { "time": 50,   "type": "noticing" },

      { "time": 60,   "type": "spacer",   "durationSeconds": 12 },
      { "time": 74,   "type": "noticing" },

      { "time": 85,   "type": "spacer",   "durationSeconds": 6 },

      { "time": 93,   "type": "landing" },
      { "time": 98,   "type": "exit" }
    ]
  }
}
```

**What the player does differently:**
No breathing tones. No cycle progression. The ambient bed carries more weight here — it IS the sonic world the child is observing in. The `noticing` markers are tiny gentle tones that say "there — you just watched one go by." The `spacer` cues are instructions to the player: do nothing here, let the silence work.

### 5.4 Module 7 — Brave Steps (Brave, Tension Arc)

```json
{
  "moduleId": "brave_steps",
  "phaseBVoiceStem": "audio/stems/m7_brave_steps_voice.mp3",
  "phaseBMixConfig": {
    "domain": "brave",
    "voiceDurationSeconds": 105,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 20,   "type": "tensionRise",  "durationSeconds": 20 },
      { "time": 40,   "type": "tensionPeak" },
      { "time": 42,   "type": "tensionFall",  "durationSeconds": 25 },

      { "time": 75,   "type": "spacer",       "durationSeconds": 10 },

      { "time": 90,   "type": "landing" },
      { "time": 100,  "type": "exit" }
    ]
  }
}
```

**What the player does:** The tension arc tones create a physical sonic representation of the anxiety wave — rising, peaking, falling. The child hears/feels the wave in the sound environment while the voice narrates staying present with it. After the fall, a spacer lets the child sit with the calm that comes after.

### 5.5 Module 10 — Squeeze & Release (Grounding, Body Cycles)

```json
{
  "moduleId": "squeeze_release",
  "phaseBVoiceStem": "audio/stems/m10_squeeze_release_voice.mp3",
  "phaseBMixConfig": {
    "domain": "grounding",
    "voiceDurationSeconds": 110,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 15,   "type": "squeeze", "cycle": 1, "totalCycles": 4, "durationSeconds": 5 },
      { "time": 20,   "type": "release", "cycle": 1, "durationSeconds": 4 },

      { "time": 32,   "type": "squeeze", "cycle": 2, "durationSeconds": 5 },
      { "time": 37,   "type": "release", "cycle": 2, "durationSeconds": 4 },

      { "time": 52,   "type": "squeeze", "cycle": 3, "durationSeconds": 5 },
      { "time": 57,   "type": "release", "cycle": 3, "durationSeconds": 4 },

      { "time": 72,   "type": "squeeze", "cycle": 4, "durationSeconds": 5 },
      { "time": 77,   "type": "release", "cycle": 4, "durationSeconds": 4 },

      { "time": 95,   "type": "landing" },
      { "time": 105,  "type": "exit" }
    ]
  }
}
```

---

## PART 6: AUTOMATED MODULE GENERATION PIPELINE

### 6.1 How a New Module Gets Its Phase B Audio — Zero Manual Work

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: AI writes Phase B script                                 │
│         (following PHASE_B_PRODUCTION_PROCESS)                   │
│         Output: Markdown script with 7 sections                  │
│                                                                  │
│ Step 2: Script → ElevenLabs TTS                                  │
│         Input: Script text + selected voice ID                   │
│         Output: voice_stem.mp3                                   │
│                                                                  │
│ Step 3: AI generates cue points                                  │
│         Input: Script text + module metadata (domain, technique) │
│         Method: Pattern matching on script content               │
│         Output: cuePoints[] array with timestamps                │
│                                                                  │
│ Step 4: AI writes phaseBMixConfig                                │
│         Input: Module domain + cuePoints + voice duration        │
│         Output: Complete JSON config                             │
│                                                                  │
│ Step 5: Done.                                                    │
│         Player engine handles the rest at runtime.               │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 Cue Point Identification Rules

The AI identifies cue points by recognizing patterns in the script text. These rules are deterministic enough for automated extraction:

| Script Pattern | CueType | Timestamp |
|---|---|---|
| Start of script | `phaseStart` | 0 |
| "Breathe in..." / "In..." (breathing context) | `inhale` | At phrase onset |
| "Keep the air inside..." / "Hold..." | `hold` | At phrase onset |
| "Let it out..." / "And out..." / "Breathe out..." | `exhale` | At phrase onset |
| End of exhale in a counting/breathing sequence | `cycleEnd` | At cycle completion |
| Extended gap between voice segments (>5s) | `spacer` | At gap onset |
| "notice" / "watch" / "there" (observation context) | `noticing` | At phrase onset |
| "[singing bowl]" / "[bowl strike]" (stage direction) | `bowlStrike` | At direction |
| "send that warmth to yourself" / "to your own heart" | `warmthSelf` | At phrase onset |
| "someone you love" / "someone who makes you smile" | `warmthLoved` | At phrase onset |
| "someone you're having trouble with" | `warmthDifficult` | At phrase onset |
| Step boundary in a process ("Now..." / "Next...") | `stepTransition` | At phrase onset |
| "close the lid" / "put them in" / "seal it" | `containment` | At phrase onset |
| Rising anxiety description / "feel it building" | `tensionRise` | At phrase onset |
| Peak / "right there at the top" | `tensionPeak` | At phrase onset |
| "coming down" / "wave falling" / "it passes" | `tensionFall` | At phrase onset |
| "what can you see" / "what do you hear" (new sense) | `senseShift` | At phrase onset |
| "now move to your..." (new body area) | `bodyRegionShift` | At phrase onset |
| "squeeze" / "tighten" / "make a fist" | `squeeze` | At phrase onset |
| "release" / "let go" / "soften" | `release` | At phrase onset |
| "that's your magic" / "that's the spell" | `landing` | At phrase onset |
| "Stay right there" / final phrase | `exit` | At phrase onset |

**⚠️ DISAMBIGUATION RULE (added v1.1):** Many of these pattern words appear multiple times in a typical script — some as descriptive mentions, some as actual cue instructions. For example, "breathe" may appear in "the long breath out is where the magic is" (descriptive) AND in "Breathe in... 2, 3, 4" (actual instruction). Pattern matching MUST use script-level audio cue markers (`{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, etc.) to identify which occurrence is the actual cue. See Audio Assembly Guide §2.2.1 for the full disambiguation rule and §2.2.2 for the cue marker spec. Failure to disambiguate caused an 8-second timing error in M2 production.

### 6.3 Timestamp Extraction (Proven Method)

**Primary method (proven in M2 production):** Run vosk speech-to-text on the voice stem with word-level timestamps enabled (`SetWords(True)`). This returns the exact start/end time of every spoken word. Combined with script-level cue markers for disambiguation, this provides sub-second accuracy with zero human input.

**Tool:** Vosk (`pip install vosk` + `vosk-model-small-en-us-0.15`). Free, offline, no API cost. See Audio Assembly Guide §2.2 for the complete pipeline and code.

**Alternative:** ElevenLabs `with_timestamps` parameter on TTS generation, which returns word timestamps at generation time. Not yet tested in production but architecturally equivalent.

**Fallback for prototyping only:** Timestamps can be estimated from script text using speaking rate (~2 words/second for narration, ~1 count/second for breathing counts). These estimates are useful for rough planning but MUST NOT be used for final tone placement — they were consistently off by 5-10 seconds in practice.

**⚠️ NEVER use waveform energy analysis to guess which speech segment corresponds to which word.** This approach cannot distinguish between words and was the root cause of the M2 timing failure.

---

## PART 7: TECHNICAL IMPLEMENTATION NOTES

### 7.1 Web Audio API (Browser)

The module player uses the Web Audio API for real-time mixing:

```javascript
// Simplified architecture
const audioContext = new AudioContext();

// Channel nodes
const voiceGain = audioContext.createGain();     // Channel 1
const ambientGain = audioContext.createGain();   // Channel 2
const tonesGain = audioContext.createGain();     // Channel 3
const accentsGain = audioContext.createGain();   // Channel 4

// All channels → master output
[voiceGain, ambientGain, tonesGain, accentsGain]
  .forEach(g => g.connect(audioContext.destination));

// Set default volumes
voiceGain.gain.value = 1.0;
ambientGain.gain.value = 0.08;
tonesGain.gain.value = 0.10;
accentsGain.gain.value = 0.12;
```

### 7.2 Cue Point Scheduling

```javascript
// Schedule cue points relative to voice stem start
function scheduleCuePoints(cuePoints, voiceStartTime) {
  cuePoints.forEach(cue => {
    const triggerTime = voiceStartTime + cue.time;

    switch (cue.type) {
      case 'phaseStart':
        playSound('bell_transition', accentsGain, triggerTime, 0.40);
        startAmbientBed(triggerTime);
        break;

      case 'inhale':
        const vol = applyProgression(0.10, cue.cycle, cue.totalCycles);
        playSoundTrimmed('breath_inhale', tonesGain, triggerTime,
                         vol, cue.durationSeconds);
        break;

      case 'cycleEnd':
        const shimmerVariant = `exhale_shimmer_${cue.cycle}`;
        const shimmerVol = [0.08, 0.12, 0.16][cue.cycle - 1];
        playSound(shimmerVariant, accentsGain, triggerTime, shimmerVol);
        break;

      case 'landing':
        const domainShimmer = `shimmer_landing_${config.domain}`;
        playSound(domainShimmer, accentsGain, triggerTime, 0.20);
        break;

      case 'exit':
        fadeOutAmbient(triggerTime, 10); // 10s fade
        break;

      // ... other types
    }
  });
}
```

### 7.3 Fallback Strategy

If the player environment doesn't support multi-channel mixing (e.g., very old devices), fall back to `guidedAudioRef` — the pre-baked single-file mix. This means:

- For the 12 seed modules, produce BOTH a pre-baked mix (using the ElevenLabs recipe) AND the dynamic mix config
- For AI-generated modules beyond 12, pre-baked mixes can be generated offline as a batch process
- The player checks device capability and chooses the appropriate strategy

### 7.4 Preloading

All 33 library sounds should be preloaded when the app starts (total size estimate: ~5-8 MB). Per-module, only the voice stem needs to be fetched at module load time.

---

## PART 8: RELATIONSHIP TO EXISTING DOCUMENTS

| Document | Relationship |
|---|---|
| Canonical Data Model v1.1 | Add `phaseBVoiceStem` and `phaseBMixConfig` to modules collection |
| Module JSON Schema Guardrails v2 | `guidedAudioRef` preserved as fallback; new fields extend Phase B audio capability |
| Phase B Sound Design Vision v1 | This architecture IMPLEMENTS the vision. Domain palettes, three-layer architecture, classical conditioning principles — all realized through the cue point system |
| Phase B Sound Production Brief v1 | The brief becomes the recipe for building the 33-file sound library. The per-module cue sheets become unnecessary (replaced by `cuePoints[]` in the JSON) |
| ElevenLabs Sound Recipe v1 | Used to produce the 33 library files. After that, only Step 1 (voice generation) is needed per module |
| Phase B Production Process v1.1 | Step 9 (production assembly) is automated by this engine. Steps 1-8 (script creation) remain human/AI-authored |

---

## PART 9: PRODUCTION SEQUENCE

### Phase 1: Build the Sound Library (one-time)
Use the ElevenLabs Sound Recipe to produce all 33 library files. Priority order:
1. Universal sounds (bell, landing shimmers) — used by all 12 modules
2. Calm domain bed — needed for M1 and M2 (already locked)
3. Breathing sounds — needed for M1 and M2
4. Focus domain bed + observation sounds — needed for M3 and M4
5. Remaining domain beds and functional sounds — as scripts are produced

### Phase 2: Implement the Player Audio Engine
Build the 4-channel mixer, cue point scheduler, and ambient bed lifecycle. Test with M1 and M2 configs against the locked voice stems.

### Phase 3: Produce Voice Stems for Modules 1-2
Use ElevenLabs TTS with the locked M1 and M2 scripts. Generate cue point configs.

### Phase 4: Validate
Does M1 sound like the M1 we imagined? Does the transition bell → ambient bed → breath tones → exhale shimmer → landing shimmer → fade-out sequence feel magical, safe, and effective? Adjust library sounds and volumes until it does.

### Phase 5: Scale
As each module's Phase B script is produced, generate voice stem + cue point config. The library and player already exist. Each new module costs one TTS generation + one JSON config — maybe 30 minutes of work.

### Parent Delivery: Play Spell Button (NEW March 25, 2026)

Phase B audio is also delivered to parents via a **"Play Spell" button** on each parent technique card (Spell Card) in the parent dashboard. The button streams the same assembled Phase B audio — voice stem + ambient bed + cue point SFX. Parents hear exactly what their child practiced.

- **Free with the app.** Not a premium feature.
- **COPPA-safe.** Behind parent authentication gate. Not exposed to child's side of the app.
- **Not a browsable library.** One button per card, one meditation per button.
- **No additional audio production.** Reuses the same audio assets already produced for the child's module.

See PARENT_DASHBOARD_ARCHITECTURE_v1_2.md §3B and NARRATIVE_DECISIONS_UNIFIED_v2_4.md §6.4 for full spec.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial architecture. 23 cue types covering all 12 module patterns. 33-file sound library manifest. 4-channel player mixing rules with cycle progression. 5 worked examples spanning breathing, observation, tension arc, and body cycle patterns. Automated pipeline from script to playable module. Schema additions for phaseBVoiceStem and phaseBMixConfig. |
| 1.1 | February 24, 2026 | §6.2: Added disambiguation warning — cue words appear multiple times in scripts, must use script-level cue markers to identify correct occurrence. §6.3: Rewritten — vosk STT is now the proven timestamp extraction method (tested in M2 production). Waveform energy analysis explicitly deprecated. ElevenLabs Forced Alignment listed as untested alternative. Ambient bed default volume lowered from 0.15 to 0.08 in schema, volume table, and code examples (based on M2 production testing). |

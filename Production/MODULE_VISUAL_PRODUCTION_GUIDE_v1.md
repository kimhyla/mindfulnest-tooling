# Module Visual Production Guide

## Integrated Visual Strategy Across the 5-Step Module Flow

### Version 1.0 — February 23, 2026

---

## Purpose

This document defines how every visual element in the module player is produced, rendered, and automated — from the Buy-In through Phase B to the Win screen. It ensures that visual production decisions are integrated across all five steps rather than designed in isolation.

**Scope:** This covers runtime visuals (what the child sees while using a module). It does NOT cover marketing assets, therapist dashboard UI, or map/navigation visuals, which are separate production concerns.

**When this guide and another document conflict, the resolution order is:**

1. Everdale World Design Bible v9b (highest authority)
2. Visual Production Guide v3 (asset pipeline)
3. Module Authoring Guide v4.3 (content rules)
4. This guide (visual production strategy)

---

## PART 1: THE VISUAL MAP

Every module passes through 5 steps. Each step has distinct visual requirements, but they share a continuous aesthetic — the child should never feel a jarring transition between steps.

```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: THE CALL (10-20s)                                         │
│  ├── Creature sprite (distress state)                              │
│  ├── Guide Bird sprite + speech bubble                             │
│  └── "Help [creature]" button                                      │
│                                                                     │
│  STEP 2: THE BUY-IN (15-30s)                                       │
│  ├── Guide Bird animated sprite (zoomed in, prominent)             │
│  ├── Domain-tinted gradient background                             │
│  ├── ElevenLabs audio (Guide Bird voice)                           │
│  └── "Ready" button                                                │
│  ↑ Bible: "NOT a pre-produced video file. Assembled automatically  │
│    from existing components. Fully automated — no human in loop."  │
│                                                                     │
│  STEP 3A: TRAINING PHASE A (60-90s)                                │
│  ├── Guide Bird (left 1/3, persistent)                             │
│  ├── Interactive demo area (right 2/3)                             │
│  ├── Speech bubbles for dialogue cues                              │
│  └── Pattern-specific React component                              │
│                                                                     │
│  STEP 3B: TRAINING PHASE B (60-120s)                               │
│  ├── Case A: Ambient procedural animation (eyes-closed modules)    │
│  │   └── Breathing circle, particles, domain-tinted glow           │
│  ├── Case B: Lottie/Rive body figure (eyes-open body modules)      │
│  │   └── Rigged character showing poses, triggered by cue points   │
│  └── Meditation narrator audio (NOT Guide Bird voice)              │
│                                                                     │
│  STEP 4: THE RESCUE (20-30s)                                       │
│  ├── Creature sprite (receiving state, eyes closed)                │
│  ├── Glow overlay building                                         │
│  ├── Guide Bird voice fading in (continuous from Phase B)          │
│  └── Creature opens eyes + smiles                                  │
│                                                                     │
│  STEP 5: THE WIN (15-30s)                                          │
│  ├── XP animation                                                  │
│  ├── Rune stone pulse                                              │
│  ├── Measuring bar circle fill                                     │
│  └── Decoration unlock (if applicable)                             │
└─────────────────────────────────────────────────────────────────────┘
```

**Continuous flow requirement (Bible):** The transition from Phase B → Rescue → Win must be seamless. The child never has a "stop meditating, now look at screen" moment.

---

## PART 2: SHARED VISUAL ASSETS

### 2.1 Assets Built Once, Used Across All Modules

| Asset | Format | Used In | Count | Build Once? |
|---|---|---|---|---|
| Guide Bird sprite (idle, talking, happy) | Rive/Lottie or spritesheet | Steps 1, 2, 3A, 4, 5 | 1 character, ~5 states | ✅ |
| Creature sprites (distress, receiving, healed) | PNG or Rive | Steps 1, 4, 5 | 6 creatures × 3 states = 18 | ✅ |
| Domain gradient backgrounds | CSS/SVG | Step 2 (Buy-In), Step 3B | 6 gradients | ✅ |
| Speech bubble component | React/CSS | Steps 1, 2, 3A | 1 component | ✅ |
| Breathing circle component | React/CSS | Step 3B (Case A) | 1 component | ✅ |
| Body figure rig | Rive | Step 3B (Case B) | 1 rig, ~25 poses | ✅ |
| Glow overlay effect | CSS/shader | Step 4 (Rescue) | 1 effect, domain-tinted | ✅ |
| Coins/reward animations | React/Lottie | Step 5 (Win) | 1 set | ✅ |

**Total unique visual assets for all 12 modules:** ~35-40 items, all reusable.
**Per-module unique assets:** Zero. Every module assembles from the shared library.

**Audio assets follow the same "build once" pattern:**

| Asset | Type | Used in | Build Once? |
|-------|------|---------|-------------|
| Character voice profiles | ElevenLabs voice config | All dialogue rendering | ✅ (one profile per character, all arcs) |
| Universal voice segments | MP3 | Phase B body, non-personalized dialogue | ✅ (shared by all children) |
| Per-child voice segments | MP3 | Lines with `{childName}` | ❌ (rendered per child at module unlock) |
| Ambient beds | WAV/MP3 | Phase B background | ✅ (one per domain, all modules) |
| Functional SFX library | WAV | Phase B cue points | ✅ (~35 files cover all modules) |

See `TTS_PERSONALIZATION_PIPELINE_v1.md` §4.3 for the segment-level personalization cost model (~$2.82 per child for the full app).

### 2.2 Domain Color Palettes

Already defined in the demo codebase and consistent with the Bible:

```javascript
const DOMAIN_PALETTES = {
  calm:      { bg: "#1a1510", accent: "#D4A574", glow: "rgba(212,165,116,0.15)" },
  focus:     { bg: "#101520", accent: "#7BA4C7", glow: "rgba(123,164,199,0.15)" },
  heart:     { bg: "#1A1015", accent: "#C77B8B", glow: "rgba(199,123,139,0.15)" },
  brave:     { bg: "#101A10", accent: "#8BA47B", glow: "rgba(139,164,123,0.15)" },
  grounding: { bg: "#1A1510", accent: "#A08060", glow: "rgba(160,128,96,0.15)" },
  rest:      { bg: "#0E0E14", accent: "#8080A0", glow: "rgba(128,128,160,0.15)" },
};
```

These tint everything: Buy-In gradients, Phase B ambient visuals, Rescue glow overlays, breath circle color.

---

## PART 3: STEP 2 — THE BUY-IN

### 3.1 What the Bible Says

The Buy-In is explicitly defined as:

> "Guide Bird's animated sprite on a soft gradient background with AI-generated ElevenLabs audio — NOT a pre-produced video file. Assembled automatically from existing components. Fully automated pipeline — no human in the loop."

This means: no per-module video production. The Buy-In screen is a runtime composition of shared assets + generated audio.

### 3.2 Visual Composition

```
┌─────────────────────────────────────────┐
│          Domain gradient background      │
│                                         │
│         ┌───────────────────┐           │
│         │                   │           │
│         │   Guide Bird      │           │
│         │   (animated,      │           │
│         │    zoomed in,     │           │
│         │    talking state) │           │
│         │                   │           │
│         └───────────────────┘           │
│                                         │
│     [ Speech text / subtitle area ]     │
│                                         │
│            [ Ready button ]             │
└─────────────────────────────────────────┘
```

### 3.3 Components Needed

| Component | Source | Per-Module Cost |
|---|---|---|
| Guide Bird animated sprite | Shared asset (§2.1) | $0 |
| Domain gradient background | CSS from domain palette | $0 |
| ElevenLabs audio | Generated from cached Buy-In script | ~$0.10 API credits |
| Speech text overlay | Pulled from cached Buy-In script | $0 |

### 3.4 The Guide Bird Character

The Guide Bird needs to be an animated character that can:
- Idle (subtle breathing/swaying)
- Talk (beak/body animation synced to audio, or triggered by audio playback)
- Emote (happy, encouraging, concerned — for Call and Rescue)

**Recommended approach: Rive state machine.**

Rive supports state machines natively — define states (idle, talking, happy, concerned) and trigger transitions from code. The same Rive file works in every step of every module. State transitions are driven by the module player logic, not by per-module animation work.

**Production steps:**
1. Design the Guide Bird character in Rive (one-time, ~1-2 days)
2. Rig with bone structure for beak, wings, body sway
3. Define animation states: idle (looping), talking (looping while audio plays), happy, concerned
4. Export as `.riv` file (~10-50KB)
5. Load in React via `@rive-app/react-canvas`

**Lip sync option (v2+):** Rive supports audio-driven lip sync. For MVP, a simple talking loop (beak opens/closes rhythmically) during audio playback is sufficient. True lip sync from the ElevenLabs audio would be a polish feature.

**Cost:** Rive free tier covers this. React runtime is open source.

### 3.5 Automation Pipeline for Buy-In

The Buy-In is fully automated per the Bible. The pipeline:

```
┌──────────────────────────────────────────────────────┐
│ 1. AI Narrative Service generates Buy-In script       │
│    (from measuring bar context — see Bible)           │
│                                                       │
│ 2. Script → ElevenLabs API → Guide Bird voice audio  │
│    (different voice from meditation narrator)         │
│                                                       │
│ 3. Module player composes at runtime:                 │
│    ├── Load Guide Bird Rive file (shared)             │
│    ├── Set domain gradient background (from palette)  │
│    ├── Play ElevenLabs audio                          │
│    ├── Trigger "talking" state on Rive character      │
│    ├── Display subtitle text (from cached script)     │
│    └── Show "Ready" button when audio completes       │
│                                                       │
│ Per-module cost: ~$0.10 (TTS API)                     │
│ Per-module human input: Zero                          │
└──────────────────────────────────────────────────────┘
```

---

## PART 4: STEP 3B — PHASE B VISUALS

Phase B has two visual modes depending on whether the child's eyes are open or closed.

### 4.1 Case A: Eyes-Closed Modules (M1-M8, M13)

**Design principle:** The visual is ambient, not instructional. It exists for three audiences: the peeking child (safety, calm), the observing therapist (progress awareness), and marketing screenshots (beauty).

**Approach: Procedural cue-driven animation.**

The same `cuePoints[]` array that drives the audio drives the visuals. A single React component reads cue events and renders domain-tinted abstract animations.

#### What the Child Sees (If They Peek)

| Cue Event | Visual Response |
|---|---|
| `phaseStart` / bell | Soft light bloom, scene "arrives" |
| `breathCycle` inhale | Breathing circle expands, glow intensifies |
| `breathCycle` hold | Circle holds steady, glow sustains |
| `breathCycle` exhale | Circle contracts, glow softens, gentle particle release |
| `noticing` | Soft pulse of light, like a firefly |
| `landing` | Warm shimmer bloom across screen |
| `exit` | Everything slowly fades |

The breathing circle (or domain-appropriate shape — could be Shelly's shell outline for Calm, a cloud for Focus, etc.) is the primary visual element. It moves in sync with the audio breath sounds, creating a multi-sensory rhythm: hear the breath, see the circle, feel the timing.

#### Technical Implementation

```jsx
// Conceptual — the Phase B visual component
function PhaseBVisual({ domain, cuePoints, currentTime }) {
  const palette = DOMAIN_PALETTES[domain];
  const activeCue = getActiveCue(cuePoints, currentTime);

  // Breathing circle scale driven by cue state
  const scale = useMemo(() => {
    if (!activeCue || activeCue.ty !== 'breathCycle') return 1.0;
    const elapsed = currentTime - activeCue.t;
    if (elapsed < activeCue.inDur) {
      // Inhale: expand from 1.0 to 1.4
      return 1.0 + 0.4 * (elapsed / activeCue.inDur);
    } else if (elapsed < activeCue.inDur + activeCue.holdDur) {
      // Hold: stay at 1.4
      return 1.4;
    } else {
      // Exhale: contract from 1.4 to 1.0
      const exElapsed = elapsed - activeCue.inDur - activeCue.holdDur;
      return 1.4 - 0.4 * (exElapsed / activeCue.outDur);
    }
  }, [activeCue, currentTime]);

  return (
    <div style={{ background: palette.bg }}>
      <BreathingCircle
        scale={scale}
        color={palette.accent}
        glow={palette.glow}
      />
      <AmbientParticles color={palette.accent} />
    </div>
  );
}
```

#### Cost and Automation

| Item | Cost | Per-Module Work |
|---|---|---|
| Breathing circle component | $0 (React + CSS) | None — reads cue points |
| Domain tinting | $0 (palette lookup) | None — reads module domain |
| Particle effect | $0 (Canvas or CSS) | None — ambient loop |
| **Total per module** | **$0** | **Zero** |

Build once. Works for all eyes-closed modules forever. New modules provide cue points and domain — the visual generates itself.

### 4.2 Case B: Eyes-Open Body Modules (M9, M11, M12)

**Design principle:** The visual IS the instruction. The child needs to see what body part to focus on and what action to take.

**Approach: Rive character rig with cue-point-driven pose transitions.**

#### Why Rive

| Feature | Why It Matters |
|---|---|
| State machines | Define states like "hands_relaxed" → "hands_squeezing" → "hands_relaxed" and trigger from code |
| Smooth transitions | Rive interpolates between poses — no jarring crossfades |
| Tiny file size | A rigged character with 25 poses is ~50-100KB |
| React integration | `@rive-app/react-canvas` — native, well-maintained |
| Free tier | Covers our needs (3 files, unlimited viewers) |
| Reusable rig | One character, infinite poses. New modules = new state, not new art |

#### The Body Figure Design

A simple, friendly, child-proportioned, gender-neutral figure. NOT realistic — think Headspace's abstract figures or a warm line-art character consistent with Everdale's aesthetic.

The figure is rigged with control points at: hands, shoulders, toes, legs, arms, face, torso. Each body region can be highlighted (glow), animated (squeeze/release), or pointed to (attention indicator).

#### Pose Library

The initial rig needs ~25 poses to cover M9 (five senses), M11 (squeeze/release), and M12 (body scan):

**M11 — Squeeze & Release:**
| Pose State | Trigger Cue | Visual |
|---|---|---|
| hands_relaxed | default / `release` | Hands open, soft |
| hands_squeezing | `squeeze` | Hands forming fists, glow on hands |
| shoulders_relaxed | default / `release` | Shoulders down, soft |
| shoulders_scrunching | `squeeze` | Shoulders up near ears, glow on shoulders |
| toes_relaxed | default / `release` | Toes flat, soft |
| toes_curling | `squeeze` | Toes curled up, glow on toes |

**M12 — Body Scan:**
| Pose State | Trigger Cue | Visual |
|---|---|---|
| feet_focus | `bodyRegionShift` | Gentle glow on feet |
| legs_focus | `bodyRegionShift` | Glow moves to legs |
| belly_focus | `bodyRegionShift` | Glow moves to belly |
| chest_focus | `bodyRegionShift` | Glow moves to chest |
| hands_focus | `bodyRegionShift` | Glow moves to hands |
| face_focus | `bodyRegionShift` | Glow moves to face |
| whole_body | `landing` | Entire figure glows softly |

**M9 — Five Senses:**
| Pose State | Trigger Cue | Visual |
|---|---|---|
| eyes_focus | `senseShift` | Glow on eyes, visual icon |
| ears_focus | `senseShift` | Glow on ears, sound wave icon |
| hands_focus | `senseShift` | Glow on hands, touch icon |
| nose_focus | `senseShift` | Glow on nose |
| mouth_focus | `senseShift` | Glow on mouth |

#### Integration with Cue Points

The Rive state machine is driven by the exact same cue point system as the audio:

```javascript
// In the module player
cuePoints.forEach(cue => {
  if (cue.type === 'squeeze') {
    riveInstance.fire('squeeze_' + cue.bodyRegion);
  } else if (cue.type === 'release') {
    riveInstance.fire('release_' + cue.bodyRegion);
  } else if (cue.type === 'bodyRegionShift') {
    riveInstance.fire('focus_' + cue.bodyRegion);
  }
});
```

This means the cue point schema needs a `bodyRegion` field for body modules:

```typescript
interface CuePoint {
  time: number;
  type: CueType;
  bodyRegion?: "hands" | "shoulders" | "toes" | "legs" | "feet"
             | "belly" | "chest" | "face" | "eyes" | "ears"
             | "nose" | "mouth" | "whole";
  // ... existing fields
}
```

#### Cost and Automation

| Item | Cost | Per-Module Work |
|---|---|---|
| Rive character design + rigging | ~2 days (one-time) | N/A |
| Rive free tier | $0 | $0 |
| New pose for novel body action | ~30 min in Rive editor | Only if module uses a body action not in the library |
| Cue-point-driven transitions | $0 (code) | Zero — reads cue points |
| **Total per module** | **$0** | **Zero (if poses exist) or ~30 min (novel pose)** |

#### Building the Rive Rig — Production Steps

1. **Design character** in Rive editor — simple, friendly, Everdale-consistent (~4 hours)
2. **Rig with bones** — control points at each body region (~2 hours)
3. **Create pose states** — the 25 initial poses listed above (~4 hours)
4. **Build state machine** — transitions between poses triggered by named inputs (~2 hours)
5. **Export `.riv` file** — embed in app (~50-100KB)
6. **React integration** — `@rive-app/react-canvas`, trigger states from cue point scheduler (~2 hours)

**Total one-time investment:** ~2 days.
**After that:** New modules either reuse existing poses ($0) or add a new pose (~30 min).

---

## PART 5: THE GUIDE BIRD — A UNIFYING VISUAL ASSET

The Guide Bird appears in steps 1, 2, 3A, 4, and 5. It is the single most-reused visual asset in the entire app. Investing in a well-built Guide Bird pays dividends across every module.

### 5.1 Recommended: Single Rive File With State Machine

One `.riv` file containing:

| State | Used In | Trigger |
|---|---|---|
| idle | All steps (default) | Looping |
| talking | Steps 1, 2, 3A, 4 | Audio playback starts |
| happy | Step 5 (Win) | Module complete |
| concerned | Step 1 (Call) | Creature in distress |
| encouraging | Step 3A (Phase A) | Child interacting |
| quiet | Step 3B (Phase B) | Not visible or minimized |

### 5.2 Two Voices, One Character

The Guide Bird has its own ElevenLabs voice (used in Call, Buy-In, Phase A dialogue, Rescue, Win). This is a DIFFERENT voice from the Phase B meditation narrator. The child learns two vocal identities:

- **Guide Bird voice:** Friendly, energetic, encouraging — a peer/mentor
- **Meditation narrator voice:** Warm, wise, unhurried — a grandparent

The Guide Bird voice is generated by the AI Narrative Service (fully automated, cached on bar document). The meditation narrator voice is generated from the Phase B script (see Audio Assembly Guide).

### 5.3 Guide Bird in Buy-In vs. Phase A

| Attribute | Buy-In (Step 2) | Phase A (Step 3A) |
|---|---|---|
| Size | Large, centered, prominent | Left 1/3, persistent |
| Background | Domain gradient, nothing else | Module-specific interactive scene |
| Interaction | None — child listens | Child interacts with right 2/3 |
| Voice | ElevenLabs (Guide Bird voice) | ElevenLabs (Guide Bird voice) |
| Animation | Talking state, idle between sentences | Talking when speaking, idle when child interacts |
| Text | Subtitle overlay or speech bubble | Speech bubble near bird |

The visual transition from Buy-In → Phase A is: Guide Bird slides from center to left 1/3, background crossfades from gradient to interactive scene. This can be a CSS transition (~0.5s).

---

## PART 6: RESCUE AND WIN VISUALS

### 6.1 Rescue (Step 4)

**Components:**
- Creature sprite in receiving state (eyes closed, settled)
- Glow overlay building (domain-tinted, uses palette.glow)
- Guide Bird voice fading in (continuous from Phase B audio — no gap)

**The glow overlay** is a single CSS/Canvas effect: a radial gradient centered on the creature that slowly increases in opacity and radius over 20-30 seconds. It's domain-tinted and identical in structure across all modules — only the color changes.

**Automation:** Fully automated. The module player loads the creature's receiving-state sprite, applies the domain glow, plays the cached Rescue audio. Zero per-module visual work.

### 6.2 Win (Step 5)

**Components:**
- Coins number animation (count up)
- Rune stone pulse effect
- Measuring bar circle fill animation
- Decoration unlock reveal (if applicable)

**All animations are deterministic from module JSON** (Coins amount, which rune, which decoration). Built once as React components, configured per module via data.

---

## PART 7: PRODUCTION SEQUENCE

### 7.1 Priority Order

Build shared assets in this order (highest impact first):

| Priority | Asset | Unlocks |
|---|---|---|
| 1 | Guide Bird Rive character | Steps 1, 2, 3A, 4, 5 for ALL modules |
| 2 | Domain gradient backgrounds (CSS) | Step 2 (Buy-In) for ALL modules |
| 3 | Breathing circle component (React) | Step 3B (Phase B) for all eyes-closed modules |
| 4 | 6 creature sprites × 3 states | Steps 1, 4, 5 for ALL modules |
| 5 | Glow overlay effect | Step 4 (Rescue) for ALL modules |
| 6 | Coins/reward animations | Step 5 (Win) for ALL modules |
| 7 | Body figure Rive rig | Step 3B (Phase B) for body modules only (M9, M11, M12) |
| 8 | Speech bubble component | Steps 1, 2, 3A |

### 7.2 One-Time vs. Per-Module Costs (Scaling to 60+ Modules)

| Category | One-Time Cost | Per-Module Cost |
|---|---|---|
| Guide Bird Rive character | ~2 days design + rig | $0 |
| Body figure Rive rig | ~2 days design + rig | $0 (poses are additive — see below) |
| Phase A pattern components (~10-12) | ~2-3 weeks total | $0 (AI selects pattern + generates config) |
| 6 creature sprites × 3 states | ~2-3 days (AI generation + curation) | $0 |
| Domain gradients | ~1 hour (CSS) | $0 |
| Breathing circle | ~1 day (React + CSS) | $0 |
| Glow overlay | ~2 hours (CSS/Canvas) | $0 |
| Coins/reward animations | ~1 day (React/Lottie) | $0 |
| Speech bubble component | ~2 hours (React/CSS) | $0 |
| **Total one-time** | **~4-5 weeks** | — |
| **Total per module (after library exists)** | — | **~$0.10 (TTS API for Buy-In audio)** |

**Rive body figure poses are additive.** The initial rig ships with ~25 poses covering M9, M11, M12. Future body modules that need a novel action (e.g., "elbows bending") simply add a new state to the existing rig file (~30 min in Rive editor). All prior poses remain untouched. At 60 modules, the pose library might grow to ~40-50 states — still one file, still one character, still the same React integration code.

**At 60 modules, the economics are:**
- One-time visual investment: ~4-5 weeks
- Per-module marginal cost: ~$0.10 (Buy-In TTS)
- Per-module human time: One approval review (~15-30 min)
- Total visual production for 60 modules: ~4-5 weeks + 60 × 15 min reviews = ~4-5 weeks + ~15 hours of review

### 7.3 Automation Summary

| Step | Visual | Automated? | How |
|---|---|---|---|
| 1. Call | Creature sprite + Guide Bird + dialogue | ✅ Fully | AI generates dialogue, sprites are shared, player composes |
| 2. Buy-In | Guide Bird + gradient + audio | ✅ Fully | Bible mandates automated pipeline, zero human in loop |
| 3A. Phase A | Guide Bird + interactive component | ✅ AI-generated, human-approved | AI selects pattern + generates config JSON; human approves |
| 3B. Phase B (eyes-closed) | Breathing circle + particles | ✅ Fully | Cue points drive animation, domain tints automatically |
| 3B. Phase B (eyes-open) | Rive body figure | ✅ Fully | Cue points drive pose states, rig is shared |
| 4. Rescue | Creature + glow | ✅ Fully | Sprites shared, glow is domain-tinted CSS |
| 5. Win | Coins + rune + bar + decoration | ✅ Fully | All data-driven from module JSON |

**Every step is fully automated with human approval as the only gate.**

Phase A (Step 3A) uses a library of ~10-12 reusable pattern components (breathing visualizer, cloud/observation scene, body outline, containment box, wave/arc, bell/focus orb, etc.) that are configured by JSON, not hand-coded per module. The per-module workflow is:

1. AI determines which pattern fits the skill (breathing → breathing pattern, observation → cloud pattern, body awareness → body outline, etc.)
2. AI generates the Phase A config JSON: visual elements, Guide Bird dialogue cues, interaction logic, metaphor map
3. AI generates the phaseAFlow steps linking dialogue to visual transitions
4. Human reviews and approves (same approval gate as meditation scripts)

This scales to 60+ modules because the pattern library is finite (~10-12 patterns) while the configuration space is infinite. Module 47 (a new breathing variant) uses the breathing pattern with different config JSON. Module 53 (a new body awareness technique) uses the body outline pattern with different region highlights. The AI generates the configuration; the human confirms therapeutic soundness.

**New patterns are rare additions, not per-module work.** The initial 12 modules will surface most of the ~10-12 patterns. Modules 13-60 will overwhelmingly reuse existing patterns with new configurations. A genuinely novel therapeutic mechanic might require one new pattern component — but that's a one-time addition to the library, not a per-module cost.

---

## PART 8: TOOL RECOMMENDATIONS

### 8.1 Character Animation — Rive

| Attribute | Details |
|---|---|
| Tool | Rive (rive.app) |
| Cost | Free tier: 3 files, unlimited viewers |
| Output | `.riv` files (~10-100KB each) |
| React integration | `@rive-app/react-canvas` (npm, open source) |
| Key feature | State machines — define character states, trigger from code |
| Used for | Guide Bird character, body figure rig |
| Learning curve | ~1 day of tutorials for basic rigging + state machines |

### 8.2 Ambient Animation — React + CSS

| Attribute | Details |
|---|---|
| Tool | React with CSS animations / Framer Motion |
| Cost | $0 |
| Output | React components |
| Used for | Breathing circle, particle effects, glow overlays, gradient transitions |
| Key feature | Cue-point-driven — animations respond to `currentTime` vs. `cuePoints[]` |

### 8.3 Creature Sprites — AI Generation

| Attribute | Details |
|---|---|
| Tool | Midjourney or DALL-E (for generation), manual curation |
| Cost | ~$20-40 total for all creatures across all states |
| Output | PNG sprites with transparency |
| Used for | Creature distress/receiving/healed states |
| Key concern | Style consistency across 6 creatures × 3 states = 18 images |
| Approach | Generate all 18 in one session with strong style-locking prompts |

### 8.4 Video Clips (Vignettes, Arc Climaxes) — AI Video

| Attribute | Details |
|---|---|
| Tool | Runway, Pika, or Kling (evaluating — technology improving rapidly) |
| Cost | $12-20/month subscription |
| Output | Short video clips (5-10s) |
| Used for | Vignettes (~20-30 clips), arc climaxes (2-4 clips) |
| Key concern | Style consistency across clips |
| Note | NOT used for Buy-In (which is runtime-composed, not pre-produced) |

---

## PART 9: RELATIONSHIP TO EXISTING DOCUMENTS

| Document | Relationship |
|---|---|
| World Design Bible v9b | Defines Buy-In as automated composition (not video), Phase B visual as gentle guide, 5-step module flow. This guide IMPLEMENTS those specifications. |
| Visual Production Guide v3 | Defines the asset production pipeline and phase sequence. This guide provides the HOW for runtime visual production specifically. |
| Module Authoring Guide v4.3 | Defines Phase A screen layout (1/3 + 2/3 grid), Phase B constraints, Phase A visual rules. This guide's implementations must comply. |
| Audio Assembly Guide v1.1 | Defines cue points that drive Phase B visuals. The audio and visual systems share the same cue point array. |
| Audio Engine Architecture v1 | Defines CueType enum and cue point schema. The visual system reads the same cuePoints[]. This guide proposes adding `bodyRegion` field for body modules. |

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial guide. Integrated visual strategy across all 5 module steps. Buy-In defined as runtime composition per Bible mandate. Phase B split into Case A (procedural ambient for eyes-closed) and Case B (Rive body rig for eyes-open). Guide Bird as single Rive character with state machine. Shared asset inventory (~35-40 items, all reusable). Production sequence prioritized. All steps fully automated with human approval gate only. Tool recommendations: Rive, React+CSS, AI generation. Schema extension proposed: bodyRegion field on CuePoint. Scaled to 60+ modules: ~4-5 weeks one-time build, ~$0.10 + 15 min review per module thereafter. Phase A pattern library (~10-12 components) configured by AI-generated JSON, not hand-coded. Rive pose library is additive — new poses extend existing rig without touching prior states. |

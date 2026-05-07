# Module Technical Architecture — How Module Components Map to Production Systems

**Version:** 1.0
**Date:** April 2, 2026
**Companion to:** TTS Personalization Pipeline v1, Phase B Audio Engine Architecture v1.1, Module Production Master Plan v2.0

---

## Purpose

The TTS Personalization Pipeline (v1) defined how personalized audio is rendered and assembled. This document defines **what each component of a module IS technically** — which production system handles it, what assets it requires, and what (if anything) needs to be custom-built per module.

---

## The Core Principle

A module is not one monolithic interactive. It is a sequence of **different types of content**, each handled by a different system. Only ONE of those types requires custom interactive code per module.

The six component types are:

1. Narrative Story Scenes (runtime-composed)
2. Buy-In (runtime-composed)
3. Phase A — Technique Demo (custom interactive)
4. Phase B — Guided Meditation (audio engine)
5. Resolution (runtime-composed)
6. Win Display (standardized component)

---

## Component Map

### 1. Narrative Story Scenes

*Story setup, creature arrival, dialogue, inscription puzzle, etc.*

**System:** Runtime Scene Composer

**What it is:** Pre-produced visual animation (character sprites, backgrounds, camera movements, particle effects) exported as a visual-only asset with timing marks. TTS-rendered character dialogue is layered on top at runtime. Personalized segments (`{childName}`) are assembled per-child; universal segments are shared across all children.

**Custom per module?** Yes — each module has unique story content. But the SYSTEM is standardized. The custom work is authoring the scene description (dialogue, stage directions, voice IDs) and producing the visual assets. No custom code.

**Assets required:**
- Visual animation with timing marks (flexible hold frames at dialogue boundaries, ±0.5s flex based on TTS duration)
- TTS dialogue scripts (sourced from arc skeleton)
- Voice ID assignments per line (Guide Bird, creature, Oliver, etc.)

**Child interaction:** None. Child watches and listens. May tap to advance between scenes (like turning a page), but no gameplay interaction.

**Personalization:** Handled by segment-level TTS rendering (per TTS Personalization Pipeline v1 §4.3). Only sentences containing personalization variables are rendered per-child. Universal sentences are rendered once and shared.

**Sync mechanism:** Animation timing marks correspond to dialogue line boundaries. The TTS audio drives the pacing — if `{childName}` is a longer name (e.g., "Alexander" vs. "Kim"), the animation holds slightly longer on that beat.

---

### 2. Buy-In

*Guide Bird explains why this spell matters for the child's real life.*

**System:** Runtime Scene Composer (same system as story scenes)

**What it is:** Guide Bird on screen, speaking to the child. No interaction — child listens. Visually it is Guide Bird with a background, possibly with simple animation (Guide Bird gesturing, hopping, etc.).

**Custom per module?** Yes — the buy-in script is unique per module (different spell, different real-life application). But no custom code is required. Just a scene description + TTS script.

**Assets required:**
- Guide Bird visual (reusable across modules)
- Background
- TTS script for buy-in dialogue

**Child interaction:** None.

**Note on dynamic generation:** The buy-in text may be AI-generated per session (Haiku-generated, varies per session, rendered via Runtime TTS Mode 2 with ~0.5-1.5s latency). This is different from the story scenes which use pre-cached TTS (Mode 1). The buy-in is the one place where the runtime scene composer works with dynamically generated dialogue rather than pre-authored scripts.

---

### 3. Phase A — Technique Demo

*The interactive moment. The child performs the technique for the first time.*

**System:** Custom interactive React component

**What it is:** The child performs the technique for the first time in a guided, simplified way. Guide Bird narrates instructions via TTS while the child taps specific on-screen targets. Visual feedback responds to the child's actions (magic trails, brightening, particle effects). Timing is child-driven — the experience waits for taps, not on a fixed timeline.

**Custom per module?** YES. This is the ONLY component that requires custom interactive code per module. Each technique has different tap targets, different visual feedback, different interaction sequences.

**Assets required:**
- Character/object visuals (creature, spell targets, child avatar)
- Background
- Guide Bird TTS for narration
- Interaction logic (what to tap, in what order, what happens visually)
- Visual effect definitions (magic trails, glows, particle effects)

**Child interaction:** Active. Tapping specific targets on screen. The interaction is instructional (guided, not creative) — the child follows Guide Bird's directions.

**What the Phase A jsx contains:**
- Tap targets with clear, specific labels (e.g., "Tap your character to create a kind thought", "Tap the thought bubble to send it") — instructions must name the specific element to tap, not just say "tap to send"
- State management for interaction sequence (waiting for tap → tap received → visual response → next instruction)
- Visual effects triggered by child's actions
- Guide Bird TTS cue points (which audio clip plays at which interaction state)
- Transition trigger to Phase B when interaction sequence completes (Guide Bird hands off to Myrrhin)

**Personalization:** Guide Bird's narration may include `{childName}`. Visual elements do not need personalization.

**Example — M4 Heart-Sending Spell:**
- Tap 1: "Tap your character to create a kind thought" → thought bubble appears with auto-generated text ("Grow big and strong!")
- Tap 2: "Tap the thought bubble to send it" → magic trail travels to the Sweetrose → trail circles back to child's avatar → both Sweetrose and avatar brighten simultaneously
- Guide Bird: "See? Kind thoughts have a double-up magic power. They help whoever gets them AND whoever sends them."
- Handoff: "Now close your eyes. Listen to the voice on the wind..." → Myrrhin's Phase B audio begins

---

### 4. Phase B — Guided Meditation

**System:** Phase B Audio Engine (per Phase B Audio Engine Architecture v1.1)

**What it is:** Myrrhin's voice guiding the child through the real technique. A standalone audio experience with ambient bed, cue-pointed sound effects, and breathing cycle rhythms. The child closes their eyes and listens.

**Custom per module?** The audio content is unique per module, but the PLAYBACK SYSTEM is standardized. Custom work is the Phase B script + audio production, not code.

**Assets required:**
- Voice stem (universal body + per-child opening/closing segments)
- Ambient bed (selected by domain — e.g., Kindness domain)
- Cue point map
- Functional SFX from library

**Child interaction:** None. Eyes closed, listening.

**Personalization:** Opening and closing lines contain `{childName}`. Universal cue points remain valid for all children because `{childName}` appears only before the first cue point and after the last (per TTS Pipeline v1 §4.3). No per-child cue point recalculation needed.

**Handoff from Phase A:** Guide Bird's closing line transitions to Myrrhin's voice. Example: "Now close your eyes. Listen to the voice on the wind..." → Myrrhin fades in with the meditation.

**Phase B is a separate audio file.** It is not embedded in the Phase A jsx or any other interactive component. The module controller triggers Phase B playback after Phase A completes.

---

### 5. Resolution

*Rescue payoff, stone ceremony, party reaction, departure.*

**System:** Runtime Scene Composer

**What it is:** The child opens their eyes after Phase B and sees the result — the creature responding to the magic, the stone glowing, the inscription revealed, the party reacting. This is a narrative scene: character animation + TTS dialogue + sound effects.

**Custom per module?** Yes — unique narrative content per module. No custom code. Same runtime scene composer system as story scenes.

**Assets required:**
- Visual animation showing the creature's transformation/healing
- Stone glow effects, inscription reveal animation
- TTS dialogue (creature reacting, Guide Bird commenting, party responding)
- Timing marks

**Child interaction:** None. Child watches the payoff.

---

### 6. Win Display

*Shows the child what they earned.*

**System:** Standardized app-level reward component

**What it is:** Shows the child what they earned: Coins, Spell Learned, Decoration item. Same structure every module — just different data plugged in.

**Custom per module?** NO. This is a single reusable component that receives reward data and displays it. Not built per module.

**Assets required:**
- Icon/image for the decoration item (e.g., Sweetrose Cutting for M4)
- Spell name string (e.g., "Heart-Sending Spell")
- Coin count (e.g., 35)
- All defined in module JSON configuration, not in custom code

**Child interaction:** Minimal — tap to dismiss/continue, possibly tap to view decoration in backpack.

---

## Summary: What Needs to Be Built Per Module

| Component | Custom Code? | Custom Assets? | Custom Script/Dialogue? |
|-----------|-------------|---------------|------------------------|
| Story Scenes | No — scene composer | Yes — visual animation | Yes — from arc skeleton |
| Buy-In | No — scene composer | Minimal — reuses Guide Bird | Yes — buy-in script |
| **Phase A** | **YES — custom jsx** | **Yes — interaction visuals** | **Yes — Guide Bird narration** |
| Phase B | No — audio engine | Yes — voice stem + SFX | Yes — meditation script |
| Resolution | No — scene composer | Yes — visual animation | Yes — from arc skeleton |
| Win Display | No — standardized | Minimal — decoration icon | No — data from module JSON |

**The only custom code artifact per module is the Phase A interactive jsx.**

Everything else is content (scripts, dialogue, visual assets) fed into standardized systems.

---

## Module Playback Sequence

The module controller manages the handoffs between systems:

```
[Runtime Scene Composer] Story Scenes
         ↓
[Runtime Scene Composer] Buy-In
         ↓
[Custom React Component] Phase A — child taps, visual feedback
         ↓ (Guide Bird hands off to Myrrhin)
[Phase B Audio Engine]   Phase B — eyes closed, meditation audio
         ↓ (child opens eyes)
[Runtime Scene Composer] Resolution — rescue payoff, stone ceremony
         ↓
[Standardized Component] Win Display — coins, spell, decoration
```

Each transition is a handoff from one system to the next. The module controller triggers each system in sequence, passing control when the previous system signals completion.

---

## Implications for the 10-Stage Production Pipeline

The current Module Production Master Plan (v2.0) stages should be understood through this architectural lens:

**Stages 1-6** (Intake through Phase B Drafting) produce the CONTENT that feeds into these systems: dialogue scripts from the arc skeleton, Phase B meditation scripts, research dossiers, seed cards.

**Stage 7** (Phase B Approval + Phase A Beat Sheet) is the critical gate. The approved Phase B script becomes the input for audio production. The approved Phase A beat sheet becomes the spec for the ONE custom jsx per module.

**Stage 8** (Design Review) — Kim reviews the Phase A jsx interaction specifically, not a monolithic module component. This is the only piece that requires code review / interactive testing.

**Stages 9-10** (Audio Production + Listen-Through) produce the audio assets that the Phase B audio engine uses (voice stems, cue points, ambient beds).

**Not yet covered in the pipeline:** Production of visual animation assets for the runtime scene composer (story scenes, buy-in, resolution). This is a separate visual production workflow that feeds into the scene composer alongside the TTS audio assets.

---

## Relationship to Other Documents

- **TTS Personalization Pipeline v1** — Defines HOW personalized audio is rendered and assembled. This document defines WHAT each module component is and which system handles it.
- **Phase B Audio Engine Architecture v1.1** — Defines the audio playback system for Phase B. This document defines Phase B's place in the overall module sequence.
- **Module Production Master Plan v2.0** — Defines the 10-stage pipeline for producing module content. This document defines which production system consumes that content.
- **Arc Skeleton (current working draft)** — Source of truth for story dialogue, stage directions, and narrative structure. Scene descriptions in the skeleton feed directly into the runtime scene composer as scene authoring.
- **Phase A Beat Sheet (per module)** — The human-readable spec for the Phase A interactive, produced at Stage 7. Reviewed by Kim before the jsx is built.
- **Phase B Production Process v1.3** — Defines the 9-step process for writing Phase B scripts. The output feeds into the Phase B audio engine.

---

*v1.0 — April 2, 2026. Initial version documenting module component architecture derived from M4 (Ember/Heart-Sending Spell) production.*

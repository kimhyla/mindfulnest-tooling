# MODULE PRODUCTION MASTER PLAN

## MindfulNest — From Arc Skeleton to Playable Module

**Version:** 1.1 — March 17, 2026
**Status:** DRAFT — for Kim approval
**Replaces:** The module-production sections of MINDFULNEST_BUILD_EXECUTION_PLAN_v1_2.md
**Does NOT replace:** Phase B Production Process v1.2, Phase B Research Dossier Process v1, Module Authoring Guide v4.4, Audio Assembly Guide v1.3, Module Lifecycle Reference v1.1 — those remain valid reference documents. This plan changes HOW and WHEN they are used, not WHAT they contain.
**Document Hierarchy:** The Bible > Module Authoring Guide > This document

---

# THE CORE INSIGHT

Modules are context-free reusable content units. The same module JSON — same Phase A interaction, same Phase B meditation audio, same technique card — plays every time that technique appears in the game. When Belly Breathing appears in Arc 1 (Tessa panicking) and again in Arc 5 (Tessa's belly-breathing Evolution in Dragonshell), the child practices the SAME meditation. The difficulty comes from the narrative context (harder emotional situation, different creature, different visual dressing), not from a different meditation.

This is already documented in the Module Lifecycle Reference v1.1, which states: "The same grounding breathing module can appear in Arc 1 (Bramble excited, joy-grounding) and Arc 2 (Bramble angry, anger-grounding) with completely different narrative wrappers. The therapeutic content (how to do grounding breathing) is identical. The story context (why we're doing it now) changes."

The narrative wrapper — Call dialogue, Buy-In dialogue, Rescue transition, Win celebration — is AI-generated at runtime by Haiku from the arc skeleton's therapeutic notes. It changes every time. The therapeutic core does not.

**What this means for production:** We do not produce 54 modules. We produce ~20-24 unique technique modules. Everything else is an Evolution — a re-encounter with a known technique in a harder narrative context — that reuses the existing module and generates a fresh narrative wrapper.

---

# THE MATH

## Unique Techniques (New Spells + First Spells) — Each Needs Full Production

| Arc | Modules | New/First Spells | Techniques |
|-----|---------|-----------------|------------|
| 1 | M1–M6 | 6 First Spells | Belly Breathing, Thought Clouds, Brave Steps, Warm Heart, Letting Go, Ground-Strong |
| 2 | M7–M13 | 2 New Spells | Strong Push (CO-M3), Dragon Stomp (BI-M1) |
| 3 | M14–M19 | TBD (~3–4) | Arc 3 skeleton pending upload |
| 4 | M20–M25 | 6 New Spells | Steady Hum (C-1), Sorting Spell (F-4), Heartbeat Spell (G-5), Brave Words (CO-2), PerfectPlace (C-2), OutBlessings (K-2) |
| 5 | M26–M31 | 0 | All Evolutions |
| 6 | M32–M36 | 1 New Spell | The Weaver's Touch (MS-1) |
| 7–9 | M37–M54 | TBD (~3–6) | Arc skeletons pending |

**Estimated total unique techniques: ~20–24**

## Phase B Scripts — The Actual Authoring Load

| Status | Count | Notes |
|--------|-------|-------|
| Already written and approved | 2 confirmed | M1 (Belly Breathing), old-M3/new-M2 (Thought Clouds). Old M2 script (4-7-8) is orphaned under the reuse model — 4-7-8 is now an Evolution that reuses M1's audio. |
| Remaining for Arc 1 | 4 | Brave Steps (M3), Warm Heart (M4), Letting Go (M5), Ground-Strong (M6). M4 has a Research Dossier completed. |
| Remaining for Arcs 2–9 | ~15–19 | One per New Spell across remaining arcs |
| NOT needed | ~29–33 | All Evolutions reuse the base technique's Phase B audio |

**Kim's Phase B writing load: ~19–23 scripts total, not 54.** Of these, 2 are done, 4 are next (Arc 1), and ~15–19 follow as New Spells appear in later arcs.

## Evolutions — Nearly Zero Production Overhead

An Evolution module in the game engine is the base technique's module JSON, loaded into a narrative event that provides a different story context. The module player combines:

- Module JSON: REUSED from the base technique (same `phaseAPattern`, same `guidedAudioRef`, same `techniqueCard`)
- AI Narrative Cache: GENERATED FRESH by Haiku from the arc skeleton's therapeutic notes

**What an Evolution needs authored:** The arc skeleton narrative (already done for all locked arcs). That's it. The skeleton's Narrative Setup, Therapeutic Note, Spell Evolution Mechanic dialogue, and Resolution paragraph become the creative brief that Haiku uses to generate the Call, Buy-In, Rescue transition, and Win celebration at runtime.

**What an Evolution does NOT need:** No new Phase B script. No new Research Dossier. No new Phase A demo. No new audio production. No new module JSON.

---

# WHAT EACH EXISTING DOCUMENT NOW COVERS

| Document | Still Valid? | Scope Change |
|----------|-------------|--------------|
| **Phase B Production Process v1.2** | YES | Applies to ~20–24 New Spell scripts only. NOT to Evolutions. |
| **Phase B Research Dossier Process v1** | YES | Applies to New Spells only. Evolutions do not need dossiers. |
| **Module Discovery Dossier Process v1** | YES | Applies to New Spells in Arcs 3+ where the technique hasn't been chosen yet. |
| **Module Authoring Guide v4.4** | YES | Canonical authoring rules for all module JSON. No change. |
| **Module Lifecycle Reference v1.1** | YES | Already correctly describes the reuse architecture. No change. |
| **Audio Assembly Guide v1.3** | YES | Applies to ~20–24 unique audio tracks only. |
| **Audio Engine Architecture v1.1** | YES | No change. |
| **ElevenLabs Sound Recipe v1.1** | YES | No change. |
| **Sound Design Vision v1** | YES | No change. |
| **Sound Production Brief v1.2** | YES | No change. |
| **Cowork Plugin Spec v3.6** | NEEDS UPDATE | `/new-script` command should check if this is an Evolution first. If yes, skip — no script needed. |
| **Build Execution Plan v1.2** | SUPERSEDED (module sections) | This document replaces the module production timeline. Non-module sections (engineering, art, video) remain valid. |

---

# THE TWO PRODUCTION TRACKS

Every module in the game follows one of two tracks. The track is determined by the arc skeleton's Classification field on the module header.

## Track 1: NEW SPELL — Full Production (~20–24 modules)

A genuinely new therapeutic technique the child has never practiced. Requires full authoring of all module content.

**Steps:**

1. **Research Dossier** (Claude drafts, Kim validates)
   - Follow PHASE_B_RESEARCH_DOSSIER_PROCESS_v1.md
   - Survey 26 clinical sources for this specific technique
   - Output: Compiled dossier with cross-source synthesis
   - Gate: Kim approves dossier before script writing begins

2. **Phase B Meditation Script** (Kim writes, Claude assists)
   - Follow PHASE_B_PRODUCTION_PROCESS_v1_2.md Steps 1–9
   - The script IS the therapy — every word matters
   - Duration: 60–120 seconds at ~2 words/second
   - Gate: Kim approves script before audio production begins

3. **Phase A Design** (Claude drafts from pattern library, Kim reviews)
   - Select Phase A pattern from library (or design new if none fits)
   - Configure: `phaseAPattern`, `phaseAConfig`, `instructionCues[]`
   - Follow Module Authoring Guide v4.4 §4 (Phase A rules)
   - If pattern is new: build interactive demo, Kim validates
   - If pattern is from library: configure and verify against script

4. **Module JSON** (Claude generates, Kim reviews clinical fields)
   - Combine: Phase A config + Phase B audio ref + technique card + clinical fields
   - Follow Module JSON Schema Guardrails v2.2
   - Gate: Passes all guardrail checks Q1–Q19

5. **Audio Production** (Claude Code, autonomous — Kim listen-through)
   - Follow PHASE_B_AUDIO_ASSEMBLY_GUIDE_v1_3.md
   - ElevenLabs TTS → Vosk timestamps → ffmpeg mixing → cue points
   - Can run in PARALLEL with Steps 3–4 (audio doesn't depend on Phase A)
   - Gate: Kim listen-through approval (~5 min)

6. **Integration Verification**
   - Module plays correctly in module player
   - Phase A → Phase B transition is seamless
   - Rescue visual matches skeleton's Resolution brief

**Time estimate per New Spell:** ~3–5 hours Kim time (mostly Step 2). ~2–3 hours Claude time (Steps 1, 3, 4, 5).

## Track 2: EVOLUTION — Narrative Only (~30–34 modules)

A re-encounter with a technique the child already knows, in a harder emotional context. The module JSON is reused. Only the narrative wrapper changes.

**Steps:**

1. **Verify arc skeleton completeness** (Claude checks)
   - Skeleton has: Narrative Setup with scripted dialogue, Spell Evolution Mechanic (5-step Guide Bird sequence), Technique-First Match with clinical reasoning, 4-section Therapeutic Note, Resolution with Visible Magic, Win block, Return to Map with sprite dialogue
   - All §4.6 elements present
   - Gate: Skeleton section passes ArcBuilder v1.3 §4.2 Module Internal Structure checklist

2. **Configure narrative event** (Claude generates)
   - Create `narrativeEvent` document pointing to the BASE technique's `moduleId`
   - Set `narrativeContextHint` from the skeleton's therapeutic notes (this is what Haiku reads to generate the Call/Buy-In/Rescue)
   - Set trigger conditions, video asset refs, map state changes from skeleton

3. **Verify AI narrative generation** (Claude tests, Kim spot-checks)
   - Feed the skeleton's therapeutic notes to Haiku
   - Verify Call dialogue uses correct Spell Evolution Mechanic framing
   - Verify Buy-In connects to child's real-world experience per the skeleton
   - Verify Rescue transition matches skeleton's Resolution emotional tone
   - Gate: Generated narrative reads naturally, matches skeleton's intent

**Time estimate per Evolution:** ~15–30 minutes Kim time (spot-check narrative output). ~30–60 minutes Claude time (Steps 1–3).

---

# STAGED PRODUCTION PLAN

## Stage 1: Complete the Seed Set (Arc 1, M1–M6)

**What:** Finish the 6 First Spell modules that establish the canonical quality bar.

**Status:** 2 Phase B scripts approved (M1 Belly Breathing, M2 Thought Clouds). M4 has a Research Dossier completed. M3, M5, M6 scripts not yet started.

**Work:**
- Write M3 (Brave Steps), M4 (Warm Heart), M5 (Letting Go), M6 (Ground-Strong) Phase B scripts — Kim
- Complete Phase A designs for all 6 — from existing demos
- Generate module JSON for all 6 — Claude
- Produce audio for all 6 — Claude Code
- Kim reviews complete module set as a batch

**Output:** 6 fully playable modules. The reference set for everything that follows.

**Why this first:** These 6 modules are the training corpus. Every Evolution references one of them. Every New Spell follows their format. They must be perfect.

## Stage 2: Arc 2 as the Evolution Forge (M7–M13)

**What:** Produce Arc 2's 4 Evolutions + 2 New Spells. This is the first test of the two-track system.

**Work:**
- 4 Evolutions (M7, M9–M12): Track 2 — skeleton already complete, configure narrative events pointing to M1, M4, M5, M2 base modules, verify AI narrative generation
- 2 New Spells (M8 Dragon Stomp, M13 Strong Push): Track 1 — Research Dossier → Phase B script → Phase A design → module JSON → audio
- Kim reviews the full arc as a batch

**Output:** Proven two-track system. Timing data for both tracks. 8 total module JSONs (6 seed + 2 New Spells). 4 Evolution narrative events verified.

**Why this second:** Arc 2 is the ideal test because all 4 Evolutions map directly to Arc 1's First Spells. The reuse architecture gets its first real validation. If an Evolution's AI-generated narrative doesn't work, we catch it here with the simplest possible case.

## Stage 3: Extract the Phase A Pattern Library

**What:** After 7 unique modules are complete, formalize which Phase A interaction patterns recur.

**Work (Claude, Kim reviews):**
- Catalog every Phase A pattern used in M1–M13
- Map: which pattern, which modules use it, what's configurable
- Formalize into a reusable library with named patterns and configuration parameters
- Cross-reference against VPG v4.2 §2.1 pattern definitions

**Output:** Phase A Pattern Library document. For any future New Spell, check the library first.

**Why this third:** Need enough modules (7+) to identify real patterns vs one-offs. Extracting too early from only 6 modules risks missing patterns that emerge with diverse techniques.

## Stage 4: Arcs 3–4 Batch Production

**What:** Produce ~12 modules across two arcs using both tracks at speed.

**Work:**
- New Spells (~7–10): Track 1, batched by step — all Research Dossiers first, then all Phase B scripts, then all Phase A configs, then all module JSONs. Audio pipeline runs in parallel.
- Evolutions (~2–5): Track 2 — batch-configure narrative events, batch-verify AI narrative
- Kim writes Phase B scripts one at a time (never more than 2–3 per session)
- Kim batch-reviews each arc as a complete set

**Output:** Arcs 1–4 fully playable. MVP module set complete (~24 modules).

**Why this fourth:** Arcs 3–4 introduce the most New Spells of any arc pair (~10 new techniques). Batching the research and scripting work is efficient but requires the pattern library (Stage 3) to avoid designing Phase A from scratch for each one.

## Stage 5: Arcs 5–9 at Speed

**What:** Produce ~30 modules across 5 arcs, mostly Evolutions.

**Work:**
- New Spells (~4–8): Track 1, full treatment. But Phase A almost always comes from the pattern library. Demo-for-verification, not demo-for-production.
- Evolutions (~22–26): Track 2, batch-configured. At this point, the AI narrative generation pipeline is proven and Kim's review is spot-check only.
- Claude Code generates Evolution narrative events in batches of 6 (one arc at a time)
- Kim writes the remaining New Spell Phase B scripts
- Kim batch-reviews each arc

**Output:** Full game (~54 modules). All 9 arcs playable.

**Efficiency at this stage:** Evolutions take ~15 min Kim time each. New Spells take ~3–5 hours. An arc with 5 Evolutions + 1 New Spell = ~4–6 hours Kim time total. Five such arcs = ~20–30 hours Kim time for Arcs 5–9.

---

# KIM'S TIME — THE REAL BUDGET

| Task | Per Unit | Count | Total Kim Hours |
|------|----------|-------|-----------------|
| Phase B scripts (New Spells) | 1–2 hrs | ~18–22 | ~22–40 hrs |
| Phase B script review (revisions) | 0.5 hrs | ~18–22 | ~9–11 hrs |
| Research Dossier review | 0.5 hrs | ~18–22 | ~9–11 hrs |
| Phase A pattern review | 0.25 hrs | ~20–24 | ~5–6 hrs |
| Module JSON clinical field review | 0.25 hrs | ~20–24 | ~5–6 hrs |
| Audio listen-through | 0.1 hrs | ~20–24 | ~2–3 hrs |
| Evolution narrative spot-checks | 0.25 hrs | ~30–34 | ~8–9 hrs |
| Arc-level batch reviews (9 arcs) | 1 hr | 9 | ~9 hrs |
| **TOTAL** | | | **~70–100 hrs** |

This is spread across the entire production timeline. At ~10 hrs/week of available Kim time, module production takes ~7–10 weeks. Engineering, art, and video run in parallel.

Compare to the old plan: 54 modules × ~3–5 hrs each = ~160–270 hrs Kim time. The reuse architecture cuts Kim's module production load by roughly half.

---

# QUALITY GATES

## Per New Spell Module

1. Research Dossier: Kim approves clinical synthesis before script writing
2. Phase B Script: Kim approves every word before audio production
3. Phase A: Kim verifies interaction serves the pedagogical sequence
4. Module JSON: Passes Guardrails Q1–Q19
5. Audio: Kim listen-through confirms therapeutic quality
6. Integration: Module plays correctly end-to-end

## Per Evolution

1. Skeleton completeness: All §4.6 elements present
2. AI narrative generation: Call/Buy-In/Rescue match skeleton intent
3. Spot-check: Kim reviews generated narrative for 1 in 3 Evolutions minimum (all flagged if any fail)

## Per Arc

1. Emotional register: No consecutive modules with same primary emotion
2. Thread continuity: Oliver, Willow, homeland threads within silence limits
3. Technique diversity: No domain appears in consecutive modules without narrative justification
4. Hint management: Active hints under ceiling, all planted hints have planned payoffs

---

# WHAT THIS PLAN DOES NOT COVER

- **Video production** (Phase 5, fal.ai pipeline — separate track)
- **Sprite art production** (Midjourney — separate track)
- **Engineering** (module player, map engine, dashboards — separate track)
- **Therapist/parent dashboard content** (derived from Research Dossiers — downstream)
- **CE provider strategy** (professional training — separate workstream)

These tracks run in parallel with module production. They converge at integration testing.

---

# DECISION LOG

| Decision | Date | Rationale |
|----------|------|-----------|
| Phase B audio reused for Evolutions | March 9, 2026 | The child practices the SAME technique — only the narrative context changes. We don't need 54 distinct meditations. |
| Evolutions use base module JSON | March 9, 2026 | Confirmed by Module Lifecycle Reference v1.1 architecture: modules are context-free reusable units. |
| Phase B scripts: ~21–25, not 54 | March 9, 2026 | Direct consequence of Evolution reuse. Only New Spells need new Phase B scripts. (Updated March 17: +1 from Dragon Stomp reclassified as New Spell.) |
| Stage 1 = Seed Set, Stage 2 = Arc 2 forge | March 9, 2026 | Build the reference set first, then validate the two-track system with the simplest possible Evolution case (Arc 2 Evolutions all map to Arc 1 First Spells). |
| Demo-for-verification (not production) after Stage 3 | March 9, 2026 | Once the pattern library exists, new Phase A configs can be verified against existing patterns rather than built from scratch. Full demo-for-production reserved for genuinely new Phase A mechanics. |

---

## DOCUMENT HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | March 9, 2026 | Initial creation. Module production plan based on context-free reusable module architecture. |
| 1.1 | March 17, 2026 | **BUILT FROM: v1.0.** Ground-Strong + Dragon Stomp cascade. M6 technique: Wiggle Squeezers → Ground-Strong (3 locations). Arc 2 New Spell count: 1 → 2 (Dragon Stomp added — was Evolution, now New Spell). Phase B script estimates adjusted throughout: Arcs 2–9 remaining ~14–18 → ~15–19; NOT needed ~30–34 → ~29–33; total writing load ~18–22 → ~19–23. Decisions log updated. Source: Kim decisions, March 17 session. |

---

*— End of Document —*

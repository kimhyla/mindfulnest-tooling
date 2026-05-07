# SEED MODULES -- Lock Record

## Module 1: Belly Breathing
**Status:** LOCKED (revised and re-locked Feb 17 2026)

**What changed from v1.0:**
- Instruction cues completely rewritten per Kim's dialogue (8 cues, up from 5)
- New logical teaching sequence: explain chest vs belly -> reveal belly magic -> show chest consequence -> choice -> belly consequence -> bridge
- "tummy" -> "belly" throughout (terminology consistency)
- "trembling" -> "shaking" throughout (child-natural language)
- exampleCall: "Shelly is shaking in her shell..."
- exampleBuyIn: rewritten to match Phase A "upset" framing per new Language Consistency Rule (S3.2)
- exampleWin: "stopped shaking" (was "stopped trembling")
- phaseAFlow expanded from 12 to 13 steps to accommodate new dialogue sequence
- phaseBTransitionCue updated: "hand on your belly" (was "hands on your tummy")

**Unchanged in v1.1:** No further changes. Module 1 was already correct in APPROVED v1.0.

---

## Module 2: 4-7-8 Calm Down
**Status:** LOCKED (corrected Feb 20 2026 in v1.1)

**What changed from v1.0 to v1.1:**
- Instruction cues reduced from 5 to 3 per Kim's "minimal language when data heavy" rule
- Old cues narrated counting ("Watch the circle. Breathe in... 1, 2, 3, 4") — WRONG, counting should be visual-only
- New on_demo_begin: "4 seconds in. 7 seconds hold. 8 seconds out. 4, 7, 8. Like this."
- New on_complete: "Got it? 4-7-8. The 8 is when the magic comes through."
- exampleCall completely rewritten: removed "stop spinning" language, added "advanced Calm magic"
- exampleBuyIn completely rewritten: added "before a big test" specificity, "the secret is the long breathe out"
- exampleRescue revised: "that long, slow breath out" (was "you're breathing in a rhythm now")
- exampleWin revised: "stopped pacing and her shell is steady" + "that's advanced stuff!" (was generic)
- phaseAFlow note added: counting visible but NOT narrated
- Clinical description expanded: full polyvagal explanation

**Root cause:** Corrected dialogue existed in Feb 16 "Mindfulnest project review" conversation but was never written back to previewer v5.

---

## Module 3: Thought Clouds
**Status:** LOCKED (COMPLETELY REWRITTEN Feb 20 2026 in v1.1)

**What changed from v1.0 to v1.1 — EVERYTHING:**
- Core therapeutic mechanism changed: passive "watch-only observer" → active "selective attention with magical power metaphor"
- phaseAPattern: `thought_cloud_observer` → `thought_clouds` (interactive)
- Instruction cues: 6 watch-only cues → 10 interactive cues with Tolle activation, wave prompts, choice prompts
- phaseAFlow: 11-step watch-only → 15-step interactive with Wave 1 (neutral clouds), Wave 2 (choice pair), behavioral shaping loop
- Cloud content: generic positive/negative labels → specific text: "Am I doing it right?", "I need a glass of water", "I'm awesome!", "I'm mad", "I'm good at this", "I'm gonna win"
- exampleCall: completely rewritten — "Magic is only powerful when you can control it"
- exampleBuyIn: completely rewritten — Kim's full "magical power" metaphor (thoughts go away by themselves unless you send them your magical power)
- exampleRescue: revised — "feel that stillness" (was "keep watching those clouds")
- exampleWin: revised — "Luna's thoughts are settling! Your Focus magic did that!" (was "sky is clearing, quiet watching")
- clinicalLabel: "Cognitive Defusion — Observer Stance" → "Cognitive Defusion with Selective Attention"
- clinicalDescription: completely rewritten for selective attention + Hayes ACT + Tolle observer
- parentTips: completely rewritten around "magical power" metaphor
- techniqueCard: completely rewritten around choosing which thoughts get your magic

**Root cause:** Kim's interactive design was developed in Feb 16 "Prompt response request" conversation, then correctly built as standalone demo JSX in Feb 18 "Project files review" conversation. Neither version was ever written back to previewer v5, which still contained the OLD passive observer design from the original spec. When APPROVED v1.0 was rebuilt from the previewer, the wrong version was locked.

---

## Module 4: Mindful Listening
**Status:** LOCKED (corrected Feb 20 2026 in v1.1)

**What changed from v1.0 to v1.1:**
- on_start expanded from short prep frame to full therapeutic front-load (prep + concept + instruction in one speech)
- Cue names changed: on_bell_ring → on_bell_fading, on_silence_moment → on_silence_found
- New cue added: on_tap_too_early ("Almost... not quite. It's still singing. Keep listening.")
- phaseAFlow: 9 steps → 11 steps with explicit tap-too-early branching and golden silence bloom
- exampleCall: completely rewritten — "Luna keeps jumping at every sound" (was "can hear too many sounds")
- exampleBuyIn: completely rewritten — "so jumpy that every little noise made your heart beat fast" (was "so much noise you can't think")
- exampleRescue: revised — "feel that quiet focus... stay in that listening place" (was "stay in that quiet place")
- exampleWin: revised — "Luna isn't jumping anymore!" + "those incredible ears of yours" (was generic)
- Clinical description: expanded to reference all 5 traditions (Kabat-Zinn, Tolle, Thich Nhat Hanh, Wells, Benson)
- parentTips: richer, more specific suggestions

**Root cause:** "Follow the Sound Home" enrichment proposal was developed in Feb 16 conversations and correctly applied to previewer v3 in that session, but previewer v5 was rebuilt in a later session without carrying forward all v3 corrections.

---

## Modules 5-8: REVIEW (pending lock, revised Feb 17 2026)
- Module 5 (Warm Heart): "cold inside" removed, reframed around friendships, on_complete shortened
- Module 6: Renamed from "Sorry Bridge" to "Friend-Fix Bridge", timeout fallback added to planks
- Module 7 (Brave Steps): Call rewritten (child's magic emphasis), Buy-In uses Kim's exact text, sampleScenario adds "worried the king might not like it"
- Module 8 (Worry Box): Call uses Kim's exact text, Buy-In/on_start overlap fixed, on_complete shortened

---

## Modules 9-12: STUB (no phaseAFlow)
Not yet enriched.

---

## Systemic Issue Identified (Feb 20 2026)

**Pattern:** Dialogue corrections developed in conversation threads were not consistently written back to the previewer v5 data structure. When SEED_MODULES_APPROVED v1.0 was rebuilt from the previewer, it faithfully extracted stale data — propagating old versions of 3 out of 4 modules.

**Prevention:** See conversation thread for agreed prevention measures.

---

## v1.2 Lock-Break Record (March 9, 2026)

### Authorization

Lock-break authorized by Kim via explicit request. Changes driven by Bible v11 Arc 1 session-by-session assignments (lines 444–448) and March 8, 2026 Arc 2 skeleton decisions (documented in ARC_1_AUDIT_DECISIONS_MARCH_6_2026.md §2H and ARC_2_SKELETON_THE_KINGS_VISIT_v2.docx).

### Change 1: Creature Rename — "Shelly" → "Tessa"

**Affected modules:** M1 (Belly Breathing), Appendix A (formerly M2, 4-7-8 Calm Down)

**What changed:**
- All `creature` metadata fields: `Shelly (turtle)` → `Tessa (turtle)`
- All sample scenario text: "Shelly" → "Tessa"
- All example dialogue (Call, Buy-In, Rescue, Win): every "Shelly" → "Tessa"
- Total replacements: 8 instances across 2 modules

**What did NOT change:** Therapeutic content, instruction cues (no Shelly references in cue text), phaseAFlow, clinical descriptions, parent content, technique cards.

**Root cause:** Creature rename cascade. Shelby→Tessa rename approved by Kim (documented in memory, March 2026).

### Change 2: Domain Key Updates

**calm → breathing (affects M1 + Appendix A)**
- `moduleId`: `calm_belly_breathing` → `breathing_belly_breathing`; `calm_478_calm_down` → `breathing_478_calm_down`
- `domain` metadata: `calm` → `breathing`
- Art name in headings and dialogue: "Art of Calm" → "Art of Calm-Breathing"; "Calm magic" → "Calm-Breathing magic"; "Calm spell" → "Calm-Breathing spell"

**focus → watching (affects M2 + Appendix B)**
- `moduleId`: `focus_thought_clouds` → `watching_thought_clouds`; `focus_mindful_listening` → `watching_mindful_listening`
- `domain` metadata: `focus` → `watching`
- Art name in headings and dialogue: "Art of Focus" → "Art of Now-Watching"; "Focus magic" → "Now-Watching magic"

**Root cause:** Rune stone mapping update (SKILL_DOMAIN_RESTONE_MAPPING_CHANGE_SPEC_v1_1.md, March 7, 2026). Domain keys standardized to match Bible v11 runestone system: `runeStates: { breathing: N, watching: N, ... }`.

### Change 3: Module Renumbering (Arc 1 Alignment)

**Bible v11 Arc 1 canonical order (lines 444–448):**

| Session | Module | Creature | Domain | Art |
|---------|--------|----------|--------|-----|
| 1 | M1 — Belly Breathing | Tessa | Breath Awareness | Calm-Breathing |
| 2 | M2 — Thought Clouds | Luna | Present-Moment Awareness | Now-Watching |
| 3 | M3 — Brave Steps | Benson | Courage | Courage |
| 4 | M4 — Warm Heart | Ember | Kindness | Kindness |

**Old seed module assignments vs. new:**

| Old Slot | Technique | Old Creature | New Status |
|----------|-----------|-------------|------------|
| M1 | Belly Breathing | Shelly→Tessa | **Stays M1** (creature + domain rename only) |
| M2 | 4-7-8 Calm Down | Shelly→Tessa | **Reassigned → Arc 2 M7** (moved to Appendix A) |
| M3 | Thought Clouds | Luna | **Renumbered → M2** (domain rename only) |
| M4 | Mindful Listening | Luna | **Orphaned from Arc 1** (moved to Appendix B) |

**What happened to each module's content:**
- **M1 Belly Breathing:** Stays as MODULE 1. Creature rename + domain key update only. All therapeutic content preserved exactly.
- **Old M3 Thought Clouds → new MODULE 2.** Heading renumbered. Domain key update. All therapeutic content preserved exactly. `isFirstModule: true` remains correct (Luna's first appearance is now M2 per Bible v11).
- **Old M2 4-7-8 → APPENDIX A.** Marked as reassigned to Arc 2 M7 (Evolution of M1, grief/anticipated loss context). All therapeutic content preserved. Creature rename + domain key update applied. Content locked and available for Arc 2 production.
- **Old M4 Mindful Listening → APPENDIX B.** Marked as orphaned from Arc 1. Technique remains valid for future module slot assignment. Domain key update applied. Content locked and available for future production.

**No content was deleted.** All four modules' therapeutic content (instruction cues, phaseAFlow, example dialogue, clinical metadata, parent content, technique cards) is preserved verbatim except for the creature name and domain/Art name label changes documented above.

### Change 4: Document Hierarchy Update

Bible reference updated from v9b to v11 in the document hierarchy section.

### Verification Checks (Post-Edit)

| Check | Result |
|-------|--------|
| Zero "Shelly" in module content | ✅ PASS (1 instance in version history changelog — intentional, documents the change) |
| Zero `calm` as domain key value | ✅ PASS |
| Zero `focus` as domain key value | ✅ PASS |
| Zero `focus_` in moduleId | ✅ PASS |
| Zero `calm_` in moduleId | ✅ PASS |
| M1 = Belly Breathing / Tessa / breathing | ✅ PASS |
| M2 = Thought Clouds / Luna / watching | ✅ PASS |
| Appendix A = 4-7-8 / Tessa / breathing / reassigned Arc 2 M7 | ✅ PASS |
| Appendix B = Mindful Listening / Luna / watching / orphaned | ✅ PASS |
| Bible v11 Arc 1 order matches M1-M2 | ✅ PASS |
| No therapeutic content modified | ✅ PASS |

# Module 2 — Calm Down 4-7-8: Phase B Meditation Script

> **⚠️ OBSOLETE — DO NOT USE FOR PRODUCTION**
> This script predates the Arc 1 comet revision (March 2026). M2 is now Luna the Owl / Breath-Squeezers Spell (Squeeze-and-Release) / Now-Watching domain. This 4-7-8 script for "Shelly the Snail" no longer applies. A new Phase B script will be written from scratch when M2 enters the pipeline via phase-b-writer. Preserved for reference only.

**Status:** OBSOLETE (superseded by comet revision — technique, creature, and domain all changed)
**Version:** 2.0
**Date:** February 23, 2026
**Module:** calm_478 (Module 2) — NOW OBSOLETE: M2 is now breath_squeezers / Now-Watching domain
**Domain:** Calm — NOW OBSOLETE: M2 domain is now Now-Watching
**Creature:** Shelly the Snail — NOW OBSOLETE: M2 creature is now Luna the Owl

---

## The Script (As Recorded)

### WELCOME
Ahh... you're back. And you're ready for something more powerful... Good.

### CONNECTION
You saw the breathing circle. 4 in... 7 hold... 8 out. The long breath out is where the magic is. Now it's your turn.

### SETUP
I'm going to count for you. All you have to do... is breathe along.

### INSTRUCTION — Cycle 1
Here we go. Breathe in for two three four.

Hold it for two three four five six seven.

Release for two three four five six seven eight.

### TRANSITION
Good... The air feels different now... One more.

### INSTRUCTION — Cycle 2
Breathe in for two three four.

Hold it for two three four five six seven.

Release for two three four five six seven eight.

### LANDING
You're doing it...

That deep... tingly feeling of relaxation... that's your magic coming through.

### EXIT
Stay right there.

---

## Production Specs

| Attribute | Value |
|---|---|
| Word count | 131 |
| Recorded duration | 76.4 seconds |
| Total mix duration | ~91 seconds (with 5s lead-in + 10s fade-out) |
| Breathing cycles | 2 complete 4-7-8 cycles (guide counts aloud) |
| Count pace | ~1 count/second (achieved via no-punctuation TTS formatting) |
| Target range | 60–120 seconds ✅ |
| Voice | Myrrdin (ElevenLabs voice library) — same narrator as M1 |
| Voice settings | Stability 70%, Clarity 80%, Style 20% |
| Ambient bed | Wooden flute loop #1 |
| Bell timing | 0.5s (immediate — child is returning) |

---

## Voice Direction Notes

**Welcome:** "You're back" — warm recognition, implying the meditation voice remembers this child from M1. "Something more powerful" — slight forward lean, respect for the child's readiness. "Good." — same quiet satisfaction as M1, its own beat.

**Setup:** "I'm going to count for you" — reassuring. The child doesn't have to figure anything out. "All you have to do is breathe along" — removes performance pressure. The voice takes responsibility for the counting; the child just breathes.

**Counting pace:** ~1 count per second. Each number is warm and rhythmic, not clipped or mechanical. Think of someone counting to help a child fall asleep — not a drill sergeant, not a metronome. The voice breathes WITH the child. On inhale counts, the voice has a slight rising quality. On hold counts, the voice is steady and calm. On exhale counts, the voice descends and softens.

**"Hold it for":** Gentle instruction, not strain. The child's cheeks shouldn't puff. This is "the air is resting in there" — not "clamp down." The voice conveys ease during the hold.

**Transition:** "Good... The air feels different now..." — delivered with genuine curiosity, as if the voice is noticing the change too. Natural pauses (ellipses). "One more." — invitational.

**"You're doing it...":** Quiet affirmation after the second cycle completes. A beat to let the child feel what they've accomplished before the landing names it.

**Landing:** "That deep... tingly feeling of relaxation..." — noticing. The child's body IS different now. "That's your magic coming through." — ownership transfer.

**Exit:** Just "Stay right there." — minimal. The Rescue sustain picks up seamlessly.

---

## TTS Formatting (Critical for Counted Breathing)

The script above is the **narrative version** (what the child hears). The **TTS input version** uses specific punctuation rules to control ElevenLabs pacing:

```
No punctuation between count numbers:    "two three four" (not "two. three. four.")
Ellipses in narrative sections:           "Good... The air feels different now..."
Preamble replaces count one:             "Breathe in for two three four" (not "one two three four")
```

**Why:** Periods between numbers create ~1.5s pauses (too slow, inflates hold to 10s+). No punctuation yields ~1s/count (matches child lung capacity target). The preamble phrase ("Breathe in for") takes ~1s to speak, replacing the "One" count so total phase duration hits the 4-7-8 target. See Audio Assembly Guide v1.2 §1.4-1.5 for full documentation.

**Actual TTS input used for recording:**
```
Ahh... you're back. And you're ready for something more powerful... Good.

You saw the breathing circle. 4 in... 7 hold... 8 out. The long breath out is where the magic is. Now it's your turn.

I'm going to count for you. All you have to do... is breathe along.

Here we go. Breathe in for two three four.

Hold it for two three four five six seven.

Release for two three four five six seven eight.

Good... The air feels different now... One more.

Breathe in for two three four.

Hold it for two three four five six seven.

Release for two three four five six seven eight.

You're doing it...

That deep... tingly feeling of relaxation... that's your magic coming through.

Stay right there.
```

---

## Preceding Context (for voice continuity reference)

**Phase A bridge (Guide Bird speaks):**
"4 in, 7 hold, 8 out. The long breath out is the spell. Now you're going to try it for real."

**Transition cue (Guide Bird speaks):**
"Now close your eyes. Keep breathing with the 4-7-8 rhythm. Let the voice on the wind guide you..."

**[Phase B script begins here]**

**Following context — Rescue sustain (Guide Bird speaks):**
"OK now feel that deep, tingly calm... you're breathing in a rhythm now... keep that right there, that's the magic coming through you..."

---

## Clinical Grounding

### Technique
Extended exhale breathing with counted rhythm (4 counts in, 7 counts hold, 8 counts out). The extended exhale engages the vagal brake (Porges, Polyvagal Theory), shifting autonomic state from sympathetic to parasympathetic dominance. The counting serves as cognitive anchor (Benson, Relaxation Response) and attention training tool (Wells). The hold phase at full lungs mildly activates the baroreceptor reflex and reduces breathing rate to ~3 breaths/minute.

### Breath-Hold Clinical Note
The 7-count hold is clinically sound for the general population. Generation Mindful's PreK-12 caution about breath-holding applies primarily to unstructured holds and trauma-exposed children. This script mitigates through language framing ("hold it for" rather than "hold your breath") and structured counting through the hold (known endpoint, full lungs). **Therapist-facing note:** For trauma-exposed children, therapists may recommend shortening the hold to 4 counts or substituting Module 1 (Belly Breathing, no hold).

### Source Traceability

| Script element | Clinical source |
|---|---|
| Guide counts aloud (not child silently) | Saltzman (children need external counting), Kaiser Greenland (ages 7-10 need guide) |
| ~1 count/second pace | Kaiser Greenland (child lung capacity), Kabat-Zinn (count follows breath) |
| "Hold it for" (not "hold your breath") | Generation Mindful (trauma-informed breath-hold reframe) |
| Extended exhale emphasis (8 counts out) | Porges (vagal brake engagement), Phase A ("the long breath out is where the magic is") |
| Consistent cycle structure (both cycles identical) | Production learning: consistency reduces cognitive load vs. progressive scaffolding |
| "The air feels different now" | Brewer (curiosity engagement), physiologically grounded (breathing pattern HAS changed) |
| "You're doing it" | Saltzman (brief affirmations in counted practice) |
| "Tingly feeling of relaxation" | Somatic noticing — directs attention to body state without prescribing emotion |
| No mind-wandering beat | Counting occupies attention continuously; no unstructured quiet where mind wanders |
| No hand-on-belly instruction | Phase A didn't establish this for M2; attention anchor is the COUNT |

### Design Decisions

1. **Guide counts aloud for all cycles** — Saltzman, Kaiser Greenland (cognitive load too high for silent counting + new pattern)
2. **"Hold it for" not "hold your breath"** — Generation Mindful trauma-informed reframe
3. **~1 count/second pace** — Kaiser Greenland (child lung capacity), achieved via TTS no-punctuation formatting
4. **2 cycles not 3** — Benson (relaxation response within 60-90s); 2 cycles fills duration window; child attention span favors ending while engaged rather than risking drift on a third cycle
5. **Both cycles use identical structure** — Production learning: consistent preamble format ("Breathe in for / Hold it for / Release for") reduces cognitive load and enables reliable TTS pacing. Progressive scaffolding from v1.0 (fully labeled → short labels → slower) was replaced with consistency.
6. **"Release" not "let it out"** — Production choice; "Release" is a single-beat preamble (~1s) that cleanly replaces count one
7. **No mind-wandering beat** — counting provides continuous attention occupation (unlike M1)
8. **No "That's the spell" callback** — Removed with cycle 3; "You're doing it" serves as the affirmation beat
9. **No hand-on-belly** — M2's anchor is the count, not the belly (M1's domain)
10. **Welcome acknowledges M1** — "You're back" implies progression; "something more powerful" matches Call's "advanced magic" framing
11. **Preamble replaces count one** — "Breathe in for two three four" ensures child's actual inhale is ~4s, not ~5s

### Research Dossier
See M2_PHASE_B_RESEARCH_DOSSIER.md for the full 7-source survey with cross-source synthesis and breath-hold tension resolution.

---

## Production Process Audit Trail

All 8 production steps completed per PHASE_B_PRODUCTION_PROCESS_v1_1.md:

| Step | Result |
|---|---|
| 0. Research Dossier | Complete — 7 sources surveyed (Porges, Benson, Kabat-Zinn, Saltzman, Generation Mindful, Kaiser Greenland, van der Kolk). Central tension: breath-holding caution resolved via framing. |
| 1. Clinical Extraction | Extended exhale via vagal tone + counting as cognitive anchor; observable: breathing rate drops to ~3/min; failure modes: rushing count, straining on hold, running out of air on exhale |
| 2. Language Audit | Vocabulary card complete — must use: spell, magic, rhythm, 4-7-8, breathe in, hold, release, slow. Must not: belly (M1's anchor), relax, new metaphors |
| 3. Draft Script | v1.0: 175 words, 3 cycles. v2.0: 131 words, 2 cycles |
| 4. Body Test | All lines pass (every count maps to observable breathing action) |
| 5. Negative Space | All patterns clear; "Good" acceptable as confirmatory; "hold it for" acceptable as safety reframe; "You're doing it" acceptable as brief affirmation |
| 6. Age-Down Pass | All checks pass; counting IS the verbal guidance (no gaps); energy arc correct; lung capacity considered |
| 7. Clinical Cross-Check | 4-7-8 ratio preserved; extended exhale preserved; every decision traceable to source; zero mismatch flags |
| 8. Alignment | Bridge → Transition → Script → Rescue: vocabulary consistent ("tingly," "rhythm," "magic coming through"), energy arc smooth, promise fulfilled |
| 9. Kim Review | v1.0 approved, then modified during production to v2.0 (see revision history) |
| 10. Audio Production | Voice stem recorded (Myrrdin, 76.4s), cue points mapped, flat MP3 mixed. See Audio Assembly Guide v1.2 §6.2. |

---

## Changes from v1.0 to v2.0 (Production Modifications)

| Element | v1.0 (Approved) | v2.0 (Recorded) | Reason |
|---|---|---|---|
| Cycles | 3 | 2 | Child attention span; 2 cycles delivers therapeutic dose without drift risk |
| Count format | "one... two... three... four..." | "two three four" | Preamble replaces count one; no punctuation prevents TTS pace inflation |
| Cycle 1 hold | "Now keep the air inside... one..." | "Hold it for two three..." | Consistent preamble format across all phases |
| Cycle 1 exhale | "And let it out, nice and slow... one..." | "Release for two three..." | "Release" is single-beat preamble; cleaner timing |
| Cycle 2 format | Different from cycle 1 (short labels) | Identical to cycle 1 | Consistency reduces cognitive load; reliable TTS pacing |
| Transition | "Good. The air feels different now. Again." then "Can you feel it? One more." | "Good... The air feels different now... One more." | Single transition between 2 cycles |
| Post-cycle | "That's the spell." | "You're doing it..." | Different affirmation beat for 2-cycle structure |
| Landing | "That deep, deep calm... that rhythm... that's your magic now." | "That deep... tingly feeling of relaxation... that's your magic coming through." | Somatic noticing ("tingly") replaces abstract naming ("rhythm") |
| Exit | "Stay right there. Keep the rhythm going." | "Stay right there." | Simpler; Rescue sustain handles continuation |

**Clinical impact of changes:** None. The 4-7-8 ratio, extended exhale emphasis, trauma-informed hold language, and counting-as-cognitive-anchor are all preserved. The changes are structural (fewer cycles) and production-driven (TTS pacing control). The therapeutic mechanism is identical.

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial approved script. 3 cycles with progressive scaffolding. Produced via 8-step Production Process with Kim review. |
| 2.0 | February 23, 2026 | Production version. Reduced to 2 cycles for child attention span. Both cycles use identical "preamble replaces count one" format for reliable TTS pacing. "Release" replaces "let it out." Landing changed to somatic noticing ("tingly feeling of relaxation"). All production modifications documented in changes table above. Voice stem recorded, cue points mapped, flat MP3 mixed. |

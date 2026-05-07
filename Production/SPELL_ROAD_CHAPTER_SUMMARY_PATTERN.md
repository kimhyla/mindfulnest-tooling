# SPELL ROAD — CHAPTER SUMMARY AUTHORING PATTERN

**Date:** March 14, 2026
**For insertion into:** THERAPIST_DASHBOARD_ARCHITECTURE §5B, within the Spell Road subsection
**Authored by:** Kim (during skeleton production)
**Data field:** `arcChapterSummary` on `arcDefinitions` document — one per arc, dynamic child name/pronouns

**WARNING:** The earlier document `SPELL_ROAD_DASHBOARD_INSERTION_PROMPT.md` (also produced March 14) describes an outdated horizontal-road design and assumes the Arc Context Indicator remains. That document must be replaced before the execution thread runs. The approved design is: chapter-based 2×3 grid with modal overlay detail cards, and the Arc Context Indicator is struck. The approved demo is `spell_road_demo_v21.jsx`.

---

## SUPERSESSION NOTICE

**The Arc Context Indicator (added in v4.1) is superseded by the Spell Road Chapter Summary.**

The Arc Context Indicator was a single clinical-language sentence per arc, displayed above the MindfulNest section of the Child Profile, sourced from `arcTherapistFraming` on the `arcDefinitions` document. Example: *"Jamie is learning foundational regulation skills — breathing, attention, approach behavior, compassion, acceptance, and body awareness."*

The Chapter Summary replaces it because:
1. It provides the same emotional context but in warmer, more actionable language
2. It positions the child as a competent helper (aligned with CRI Theory), not a passive learner
3. It directly bridges to the therapist's session work ("tools you can reference and/or practice in session")
4. It connects to the visual UI ("each checkmarked technique")
5. It never uses clinical jargon that the Arc Context Indicator relied on

**Execution thread actions:**
- Strike the Arc Context Indicator subsection from §5B (currently at line ~177 of THERAPIST_DASHBOARD_ARCHITECTURE_v4_1.md)
- Replace `arcTherapistFraming` with `arcChapterSummary` in all references
- The `arcParentFraming` field (Parent Dashboard Architecture §7, daily digest email) is NOT affected — it remains as-is
- Update the Canonical Data Model if/when `arcTherapistFraming` is added there: replace with `arcChapterSummary`
- Note in the dashboard document changelog: "Arc Context Indicator (v4.1) superseded by Spell Road Chapter Summary. arcTherapistFraming field replaced by arcChapterSummary."

---

## The Three-Part Template

Every chapter summary follows a strict three-part structure in 2–3 sentences total. The therapist reads it in under 10 seconds between sessions.

**Part 1 — Narrative setup (1 sentence):**
Describe the emotional situation the characters face, using universal human language. No creature names, no game-world locations, no arc titles. Any adult should immediately connect this to real-life situations children face.

**Part 2 — Child's therapeutic action (1 sentence):**
Describe what the child does about it — at the level of therapeutic capacity, not individual technique names. Position the child as the helper and agent. Use accessible clinical language (fight-flight-fawn, self-regulation, calm and clear thinking) — not clinical jargon (vagal tone, cognitive defusion, interoceptive discrimination).

**Part 3 — Standard closing line (always the same):**
> "Each checkmarked technique is a tool you can reference and/or practice in session right now; [Name] now has a recent felt experience of each of them working."

This line is the constant. It appears in every chapter summary because it is always true and always the therapist's leverage point. It does three things simultaneously: connects to the visual UI (checkmarked cards), tells the therapist exactly what to do (reference/practice in session), and explains why it works (the child has felt these tools succeed, not just been told about them).

---

## Authoring Rules

1. Always use the child's name and correct pronouns (populated dynamically from child profile)
2. **Never** reference game-world specifics (Everdale, creature names, rune stones, spell names, arc names, the Mountain King, the MindfulNest structure)
3. **Never** suggest the app is causing emotional distress — characters face difficulty, the child helps them
4. The child is always positioned as the **competent helper**, not a passive recipient of instruction
5. Maximum 3 sentences total
6. Accessible clinical language only — a school counselor, OT, or pediatrician reading this should understand it immediately
7. Authored by Kim during skeleton production — not AI-generated
8. Part 3 (closing line) is identical across all chapters — do not vary it

---

## Locked Examples

**Chapter 1 — Foundational Skills:**
> "Six new friends are introduced in the first chapter, each with [his/her] own emotional problem. To help each friend, [Name] must master foundational self-regulation skills. Each checkmarked technique is a tool you can reference and/or practice in session right now; [Name] now has a recent felt experience of each of them working."

**Chapter 2 — Emotional Resilience:**
> "In the second chapter, [Name] and [his/her] new friends must cope with unfair circumstances beyond their control. [Name] helps [his/her] friends manage their fight-flight-fawn reactions and return to a place of calm and clear thinking. Each checkmarked technique is a tool you can reference and/or practice in session right now; [Name] now has a recent felt experience of each of them working."

Chapters 3–9: Authored by Kim during each arc's skeleton production session, following this template.

---

## Data Model

| Field | Location | Type | Author | Status |
|-------|----------|------|--------|--------|
| `arcChapterSummary` | `arcDefinitions` document | String with tokens | Kim | NEW — replaces `arcTherapistFraming` |
| `arcTherapistFraming` | `arcDefinitions` document | String | Kim | STRUCK — superseded by `arcChapterSummary` |
| `arcParentFraming` | `arcDefinitions` document | String | Kim | UNCHANGED |

**Tokens** replaced at render time: `{childName}` → child's first name, `{pronoun}` → he/she/they, `{possessive}` → his/her/their.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| v1 | March 14, 2026 | Initial. Three-part template with standard closing line. Supersedes Arc Context Indicator (v4.1). Two locked examples (Chapters 1–2). Data model: arcChapterSummary replaces arcTherapistFraming; arcParentFraming unchanged. BUILT FROM: Spell Road demo session March 14, 2026. |

*— End of Document —*

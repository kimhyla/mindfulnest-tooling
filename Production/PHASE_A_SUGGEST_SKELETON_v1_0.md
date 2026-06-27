# Phase A Suggest Script — Beat Skeleton v1.0

**Status:** APPROVED — Kim, June 2026  
**Purpose:** Canonical beat-purpose spec for Storyboard **Suggest Script** on the Phase A tab.  
**Narrative position:** Phase A plays **before** Phase B in the child's journey. Arlo (guide bird) sells the child on the **meaning and benefits** of the spell they are about to learn from the Great Wizard in Phase B.  
**Speaker:** Arlo / Chipper (guide bird voice)  
**Output:** Plain spoken text only — no stage directions, no markdown headers, no speaker prefixes.

---

## Playback order (kid timeline)

```
Intro → Phase A (Arlo sell + handoff) → Phase B (Great Wizard lesson) → Resolution
```

Phase A does **not** demonstrate technique steps. Phase A does **not** restate Phase B meditation. Phase B teaches HOW; Phase A sells WHY.

---

## Beat skeleton (purpose beats — words change per module)

Each beat has a **job**. Satisfy the purpose using the Therapeutic Note + Technique Inventory for **this** module. Do not copy M1 illustration lines for other modules.

| Beat ID | Purpose | Output rules |
|---------|---------|--------------|
| **RE_ENTRY** | Warm return; re-engage the child with Arlo | 1 short sentence. Familiar, not hypey. |
| **WIZARD_INCOMING** | Set expectation: the Great Wizard is on the way to teach **this** spell | 1–2 sentences. Must name `{spell_name}` from Therapeutic Note. |
| **MEANING_PROMISE** | Why this magic matters — pick the frame that fits the technique | **Exactly 1 sentence.** Frame is module-dependent: **body** (e.g. clear stress from your body), **mind** (e.g. help your brain slow down), or **tool** (e.g. a useful trick you can use anytime). Source: Therapeutic Note mechanism in kid language. No clinical jargon. |
| **BENEFIT_SELL** | Sell why this spell is worth learning with real-life relatable examples | **1–3** short sentences. Stop when the sell is complete; do not pad to a fixed count. Draw scenarios from Therapeutic Note + Technique Inventory age band (school, bedtime, anger, worry, etc.). New examples per module. |
| **INTEREST_JOSTLER** | Nudge curiosity / readiness right before the wizard arrives | **Exactly 1** short phrase. Vary wording per module — e.g. "Wanna try?", "Cool, right?", "This one's advanced." Permission, pride, or intrigue — not new teaching. |
| **HANDOFF** | Bridge into Phase B (wizard entrance) | 1 short line. Wizard-arrival cue (e.g. "Oh — here he comes!"). No technique HOW. |

---

## Pause rhythm

- Use `[pause]` for a breath (~1s). Stack for longer holds: `[pause][pause]`, `[pause][pause][pause]`.
- Place pauses **between** benefit-sell examples when rhythm needs space.
- Do **not** use `[silence:Ns]` in Suggest Script drafts (Phase B pipeline marker).
- Ellipsis (`…` or `....`) acceptable for sub-beat hesitation.

---

## Personalization

- Prefer universal kid-facing phrasing in rendered audio (no `{childName}` in TTS output).
- Spell name, benefit examples, and meaning frame must come from **this module's** Therapeutic Note.

---

## Phase B alignment (optional)

When a Phase B draft exists in state, use it **only** to align vocabulary (spell name, wizard tone). Phase A still plays **before** Phase B — do not write as if the child already heard the meditation.

---

## Producer output format (Storyboard Phase A tab)

- Output **plain spoken text only** — no beat labels, no markdown, no commentary.
- Target length: roughly **20–45 seconds** spoken (flexible; completeness beats word count).
- Arlo voice: warm guide bird — encouraging, not bouncy sales-pitch.
- Do **not** teach technique steps, body sensations, or meditation instructions (Phase B owns HOW).

---

## Approved illustration — M1 Magic Hands only

**Do not copy these benefit examples for other modules.** Structure only.

```
OK, We're back!  The Great Wizard is on his way.  He's going to teach you a simple Magic Spell. You'll use magic to clear the stress right out of your body.  This one's super useful.  You can use it at school if you can't stop wiggling. [pause][pause] You can use it to help you fall asleep faster at night. [pause][pause][pause] Oh- and it's a great trick if you're feeling angry and want to get back in control.  Wanna try? [pause] Oh- here he comes!
```

---

## Revision history

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | June 2026 | Initial beat-purpose skeleton: pre-Phase B sell, flexible 1–3 benefit examples, interest-jostler beat, body/mind/tool meaning frame. M1 illustration appended. |

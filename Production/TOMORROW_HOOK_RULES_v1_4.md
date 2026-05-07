> ## ⚠️ RETIRED — SUPERSEDED 2026-04-18
>
> **This document is retired.** Its architectural premise (runtime TTS substitution for Tomorrow Hooks) was killed by `NO_RUNTIME_TTS_PERSONALIZATION_V1`.
>
> Tomorrow Hooks still exist as a narrative mechanic, but they are now **plain UI text notifications** (home screen, push notifications, email) — not spoken audio. Text-UI personalization is fine and retained; audio-side hooks are gone.
>
> **Current canonical authority:** `APP_ARCHITECTURE_MASTER_v1.md` (app architecture) and `NARRATIVE_DECISIONS_UNIFIED_v2_8.md` or successor for narrative/content guidance.
>
> **Do not follow the runtime-TTS architecture described below.** If you need to author a Tomorrow Hook, write a universal text notification — no `{childName}` substitution, no audio rendering, no TTS API dependency.
>
> _Banner added by task_id `size-budget-arch-cascade-1caa1e0b`, preflight id=84._
>
> ---

# TOMORROW HOOK RULES
## MindfulNest — Guide Bird Session-End Hooks
## Version 1.3 — March 13, 2026

---

## §1 — WHAT A TOMORROW HOOK IS

One sentence spoken by Pip (Guide Bird) at the very end of the Win
sequence, after the Spell Card and before Return to Map. The last thing
the child hears before closing the app. Its sole job: make the child
want to come back.

---

## §2 — PRODUCTION APPROACH

**Tomorrow hooks are HANDWRITTEN TEMPLATES, not AI-generated.**

Each module has a locked hook template authored during skeleton
production. The template contains one variable: `{childName}`, which is
replaced at runtime with the child's inputted name. This is a simple
string substitution — no Haiku call, no AI generation, no prompt.

**Why not Haiku:** Iterative testing (March 11, 2026) showed that
tightly constrained prompts converge on identical output — meaning the
"generation" is deterministic. A handwritten template is simpler, faster
(zero latency), cheaper (zero API cost), and more reliable (zero prompt
fragility). Haiku was valuable as a WRITING PARTNER during the drafting
process but is not needed at runtime for this feature.

**Exception — conditional hooks:** For free-order modules (M7/M8 in the
Emergency Meeting Collection), the hook depends on which module the
child completed first. This is handled with a simple if/else selecting
between two handwritten templates based on completion state. Still not
Haiku — just branching logic.

**Voice rendering:** Tomorrow hooks are rendered to audio via ElevenLabs TTS using the `guidebird` voice profile (same voice as all Guide Bird dialogue). The `{childName}` substitution happens before TTS rendering. Runtime TTS (Mode 2) is used — hooks are short enough (~10 words) that latency is negligible (~0.5s). No pre-caching required. The child hears Guide Bird say their name as the last thing before returning to the map. See `TTS_PERSONALIZATION_PIPELINE_v1.md` §7.3.

**Data model:** Each module's JSON includes:
```
tomorrowHook: {
  template: "Whoa... {childName}, something big just flew into those trees!",
  conditional: false
}
```

For conditional hooks:
```
tomorrowHook: {
  conditional: true,
  variants: {
    "m8_not_complete": "...",
    "m8_complete": "..."
  }
}
```

---

## §3 — HOOK WRITING RULES (for skeleton authors)

These rules were derived from iterative testing with Kim (March 11,
2026). They govern how hooks are written during skeleton production.

### Length and Structure
- One SHORT sentence. Under 10 words. Concise beats descriptive.
- ONE clause only. No "did you hear that" + description combos.
- No questions. Pip states what he noticed, doesn't ask.

**Exception — Two-clause state-transition hooks.** When a hook must
both (a) acknowledge the state the child is in and (b) point to what's
next, two clauses are permitted if it's the most economical phrasing
available. Single clause is always preferred; two clauses require a
reason. Within named parallel collections (Emergency Meeting, Quest
Collection), the reason is typically that the child needs both
confirmation of the sequence and a redirect to the next module. The
two-clause exception does not permit questions — the second clause must
be declarative.

**Interjections are permitted when they carry emotional content.**
Short leading interjections ("Umm," "Uhh," "OK, well") are allowed when
they express Pip's genuine emotional state — surprise/wonder ("Umm"),
resigned acknowledgment ("OK, well"). Test: remove the interjection.
Does the hook lose tonal or emotional information? If yes, the
interjection is doing real work and is allowed. Pure filler that could
be removed without loss is still forbidden.

**Name-calls are not questions.** `{childName}?` used as a surprised
name-call (followed by a declarative statement) is not a question and
does not violate the no-questions rule. Pip is getting the child's
attention, not asking them something.

### Pointing Language
- Use demonstratives: "those trees", "that sound", "over there."
- Demonstratives make Pip gesture at a SPECIFIC spot. "Those trees"
  points. "The trees" describes.

### Destination Verbs
- Use verbs that imply a place to investigate: flew INTO, ducked
  BEHIND, dove UNDER, crawled INTO.
- NEVER use directionless verbs: flew PAST, flew AWAY, disappeared.
  These leave the child nowhere to go.

**Exception — Named parallel collections.** When a hook fires within a
named, visually-tracked parallel collection (Emergency Meeting
Collection, Quest Collection, etc.) where the child's next action is
already established by active game-state cues (pulsing sprites, visible
checkbox overlay), a destination verb is not required. In this context
the hook's job is to redirect attention *within a known process*, not to
create a new investigative impulse. The UI is already doing the
investigative work; Pip contextualizes the redirect.

### Action Over Ambient
- Prefer action verbs implying a living thing with intention: flew,
  darted, splashed, dove, bolted, ducked.
- NOT ambient verbs: rustled, shifted, flickered, settled.
- The child's imagination activates more when the hook implies something
  alive doing something on purpose.

### Punchline Position
- Put the UNEXPECTED or WEIRD word at the END of the sentence.
- Use an ellipsis (...) before the punchline word to create a beat of
  suspense.
- "Something under those bushes just... hiccuped" beats "Something
  hiccuped under those bushes."
- The surprise word needs the landing position.

### Child's Name
- Use `{childName}` once per hook.
- Vary placement naturally across modules — sometimes start, sometimes
  middle, sometimes end. Don't default to the same position every time.
- The name should feel like Pip turning to the child mid-discovery.

### Narrative Grounding (HARD RULE)
- Every hook must reference something that ACTUALLY HAPPENS in the arc
  skeleton's upcoming narrative events.
- The hook is a window into the next real story beat — not invented
  atmospheric scenery.
- If the hook describes something, that thing must exist in the game
  world at the moment the hook fires or on the child's next return.
- Hooks for hidden-sprite introductions point at AMBIENT CLUES (sounds,
  movement, shadows) because the creature isn't visible yet.

### What Hooks Must Never Do
- Never summarize what just happened. The Win celebrates the session.
  The hook opens what's next.
- Never attribute credit to the child ("you made that happen").
- Never express that the child is needed, missed, or should return.
- Never use: adventure, journey, feelings, magic, brave, heart, still.
- Never invent character actions, dialogue, or motives not in the
  skeleton.

---

## §4 — APPROVED HOOK TEMPLATES (M1-M13)

### Arc 1 Hooks

| Module | Template | Type | Notes |
|--------|----------|------|-------|
| M1 | "Whoa... {childName}, something big just flew into those trees!" | Hidden sprite clue (Luna) | Luna's hiding spot appears on NEXT return |
| M2 | "{childName}, something under those bushes just... hiccuped!" | Hidden sprite clue (Benson) | Benson's burrow appears on NEXT return |
| M3 | "{childName}... um, I think that tree over there just... moved." | Ambient clue (Oliver arriving) | Oliver walks in as sprite — no hiding mechanic |
| M4 | "{childName}, something just darted behind that rock." | Hidden sprite clue (Bork) | Bork's hiding spot appears on NEXT return. Replaces two-sentence draft in Arc 1 skeleton. |
| M5 | "{childName}, I think there's a BEAR coming down that path." | Creature visible (Bramble walks in) | Replaces narrative-mismatch draft ("OMG something BIG coming") in Arc 1 skeleton. Bramble is visible, not hidden — hook must point at him, not imply mystery. |
| M6 | "{childName}... it looks like the King is coming." | Mood shift (post-Agent Encounter) | Arc transition hook — next return is Arc 2. Based on draft in Arc 1 skeleton; "Well," filler removed per §3. No destination verb (correct for mood-shift type). |

### Arc 2 Hooks

| Module | Template | Type | Notes |
|--------|----------|------|-------|
| M7 | CONDITIONAL — see below | Emergency Meeting | Free-order with M8 |
| M8 | CONDITIONAL — see below | Emergency Meeting | Free-order with M7 |
| M9 | [TO BE AUTHORED] | Pre-King tension | Points toward Oliver/Willow + King's approach |
| M11 | [TO BE AUTHORED] | Post-King urgency | Points toward remaining distressed creatures + Willow investigating |
| M12 | [TO BE AUTHORED] | Post-King urgency | Points toward last distressed creature + Willow's discovery |
| M13 | [TO BE AUTHORED] | Pre-Revelation anticipation | Points toward Willow calling everyone to Heartwood |

### Conditional Hooks (Emergency Meeting)

**M7 hook (Luna/clear thinking):**
- If M8 NOT complete: `"OK, well, {childName}... maybe Bramble has an idea we can use."`
- If M8 already complete: `"Umm, {childName}? There's someone standing over there with a spear."`

**M8 hook (Bramble/anger):**
- If M7 NOT complete: `"OK, well, {childName}... maybe Luna has an idea we can use."`
- If M7 already complete: `"Umm, {childName}? There's someone standing over there with a spear."`

**Note:** The Variant B hooks (M8 already done / M7 already done) are
identical — both point at Willow arriving from the tree line with a
spear. This is correct: the child's situation is identical regardless of
which module they just finished. The Variant A hooks use the two-clause
and interjection exceptions (see §3) because the child is inside a named
parallel collection (Emergency Meeting) and the redirect is to a known
next action, not an investigative mystery.

---

### Arc 3 Hooks (Foxhollow)

M14, M15, M16 are a **Quest Collection** (any-order parallel). Their hooks
are **position-based** — the hook fired is determined by how many of the
three modules have been completed including the current one, not by which
specific module just ran. All three modules carry the same three conditional
variants in their JSON. The module system evaluates `questCollectionPosition`
(1, 2, or 3) at session end and fires the matching template.

| Position / Module | Template | Type | Notes |
|-------------------|----------|------|-------|
| M14–M16: 1st of 3 complete | "Those empty jars on the shelf just... clinked, {childName}." | Quest progress — 1/3 | One jar filled; two NPCs still tappable |
| M14–M16: 2nd of 3 complete | "That last empty jar just... trembled, {childName}." | Quest progress — 2/3 | Two jars filled; one NPC remaining; pattern emerging |
| M14–M16: 3rd of 3 complete | "{childName}, Grandpa Stanley just ducked behind those roots." | Quest complete — 3/3 | All jars full; points at M17 trigger (Grandpa's root entrance) |
| M17 | "That dark passage just... breathed, {childName}." | Passage open | Points at underground passage entrance — M18 trigger area |
| M18 | "{childName}, that feast table just appeared in the square." | Pre-community | Points at feast table in market square — M19 trigger |
| M19 | "{childName}, Grandpa Stanley just called Ember into that foxhole." | Arc departure | Points at Ember's Goodbye scene — Grandpa's foxhole |

### Conditional Hooks (Quest Collection — M14/M15/M16)

All three modules carry the same conditional block. The system fires the
template matching the current collection completion count (1, 2, or 3).

**Position 1 of 3 (one jar filled):**
"Those empty jars on the shelf just... clinked, {childName}."

**Position 2 of 3 (two jars filled):**
"That last empty jar just... trembled, {childName}."

**Position 3 of 3 (all jars filled — Quest Collection complete):**
"{childName}, Grandpa Stanley just ducked behind those roots."

### Skeleton Corrections Required (Arc 3 v8)

Two pre-existing hooks in the Arc 3 v8 skeleton do not comply with the §3
rules and must be replaced before skeleton lock:

**M18 existing (non-compliant — 29 words, multi-clause, uses forbidden word
"magic", summarizes the session):**
> *"{childsName}, we mirrored the runestone, and it worked! .... Now we just
> need one last PULL to bring the magic back above ground, and into the
> Flowers!"*

**M18 replacement (locked):**
`{childName}, that feast table just appeared in the square.`

**M19 existing (non-compliant — 14 words, two clauses):**
> *"Hey {ChildsName}, something's going on with Grandpa Stanley and Ember.
> It looks important."*

**M19 replacement (locked):**
`{childName}, Grandpa Stanley just called Ember into that foxhole.`

---

## §5 — DRAFTING NOTES FOR UNFINISHED HOOKS

### M6 — Arc Transition Hook (hardest to write)

Context: The Agent Encounter just happened. The child heard "the King is
coming." A hawk flew toward the mountain. All six creatures are stunned.
The next return opens Arc 2 with the Emergency Meeting.

The challenge: This hook can't point at a hidden sprite or a new
creature. It points at a MOOD SHIFT. The MindfulNest is blazing but the
feeling has completely changed. Pip needs to convey dread without being
scary.

Candidates for testing:
- "That hawk just flew toward the mountain, {childName}... it's not coming back."
- "Everyone just went... quiet, {childName}."
- "{childName}... I don't think things are going to be the same after today."

### M4, M5 — Authored March 13, 2026

M4 and M5 hooks drafted in Arc 1 skeleton, rule-checked March 13, 2026,
and locked in §4. M4 draft was two sentences (violation) — replaced with
single-clause version. M5 draft had a narrative mismatch (implied hidden
arrival for a visible creature) — replaced with Bramble-pointing version.
M6 draft passed rules; locked with minor cleanup (filler word removed).

### M6 — Arc Transition Hook — Authored March 13, 2026

See §5 above for the original drafting notes and candidate options.
Hook locked: `{childName}... it looks like the King is coming.`
This is the mood-shift type — no destination verb is expected.

### M7, M8 — Authored March 13, 2026

M7 and M8 are conditional hooks — two variants each depending on
free-order completion state. All four variants locked in §4.

The Variant A hooks ("OK, well... maybe X has an idea we can use") use
the two-clause exception and interjection allowance from §3 because the
child is inside the Emergency Meeting named parallel collection — the
next pulsing sprite is already visible, so no destination verb or action
verb is needed. Pip's job is to redirect within the known process.

The Variant B hooks are identical for both M7 and M8 — both point at
Willow arriving from the tree line with a spear, because that's the
same situation regardless of which module just completed.

### M9-M13 — To Be Authored

These hooks should be authored during their respective skeleton
production sessions using the rules in §3. Each hook is drafted, tested
with Kim, and locked as a template in §4.

### M14–M19 — Authored March 13, 2026

All Arc 3 hooks authored and locked in §4. Two pre-existing skeleton
hooks (M18, M19) replaced for rule compliance — see §4 Skeleton
Corrections Required. Quest Collection position-based conditional system
documented in §4.

---

## §6 — HIDDEN SPRITE DISCOVERY MECHANIC

Four of six Arc 1 creature introductions use a hidden-sprite mechanic:

| Creature | What the child sees | Reveal on tap |
|----------|-------------------|---------------|
| Tessa (M1 intro) | Tangle of storm vines with something moving inside | Vines part → Tessa revealed |
| Luna (M2 intro) | Rustling tree with scroll sticking out, near pond | Leaves part → Luna revealed |
| Benson (M3 intro) | Small dark burrow opening with hiccup sounds | Benson peeks out |
| Bork (M5 intro) | Faint flickering glow behind/inside something | Bork revealed |

**Not hidden:** Ember (M4 intro — walks in), Bramble (M6 intro — walks
in), Oliver (post-M3 — walks in), Agent (Arc 1 end — present).

**Timing:** Hiding spots appear on the child's NEXT RETURN to the app,
not at the end of the previous session. The tomorrow hook fires at
session end pointing at an ambient clue (sound, movement). The hiding
spot is the payoff when the child returns.

**Two-step reward loop:**
1. End of session: Pip says hook (ambient clue — sound, shadow, movement)
2. Next return: Child sees hiding spot on map → taps → creature revealed → video starts

---

## §7 — RELATIONSHIP TO OTHER DOCUMENTS

- **Arc skeletons:** Each module's Win section includes a `TOMORROW HOOK`
  field with the locked template from §4.
- **Module JSON schema:** `tomorrowHook` object with `template` string
  and `conditional` boolean (+ `variants` if conditional).
- **Guide Bird System Prompt:** The `tomorrowHook` field description
  should reference this document and note that hooks are templates, not
  AI-generated.
- **ArcBuilder:** §4.6 Module Format Template includes a TOMORROW HOOK
  section after the Win block.
- **Module Authoring Guide:** §7.4 describes the hook's purpose and
  points here for rules.

---

## DOCUMENT HISTORY

| Version | Date | Changes |
|---------|------|---------|
| v1 | March 11, 2026 | Initial creation. Production approach locked: handwritten templates, not Haiku. Writing rules derived from iterative testing (15 prompt versions). Hidden sprite mechanic documented. M1-M3 hooks locked. M4-M13 hooks to be authored. |
| v1.4 | March 17, 2026 | **BUILT FROM: v1.3. M7/M8 creature swap.** M7 creature changed Tessa → Luna (Arc 2 M7 redesign). M7 hook header updated: "Tessa/grief" → "Luna/clear thinking." M8-A variant updated: "maybe Tessa has an idea we can use" → "maybe Luna has an idea we can use." Source: UTI v1.7, Kim decisions March 17, 2026. |
| v1.3 | March 13, 2026 | **M7/M8 conditional hooks locked.** Four variants: M7-A ("OK, well, {childName}... maybe Bramble has an idea we can use."), M7-B / M8-B ("Umm, {childName}? There's someone standing over there with a spear."), M8-A ("OK, well, {childName}... maybe Tessa has an idea we can use." — superseded in v1.4 → Luna). B-variants are shared (Willow arrival). **§3 rule amendments (three):** (1) Two-clause exception for state-transition hooks within named parallel collections. (2) Interjection allowance when interjection carries emotional content. (3) Name-call clarification — {childName}? as name-call is not a question. **Destination Verbs:** Named parallel collection exception added. **§5:** M7/M8 authored section added. |
| v1.2 | March 13, 2026 | Arc 1 hooks M4, M5, M6 authored and locked in §4. M4: replaced two-sentence draft with single-clause rule-compliant version. M5: replaced narrative-mismatch draft (implied hidden arrival) with Bramble-pointing version. M6: locked arc-transition mood-shift hook from draft (filler word removed). §5 drafting notes updated: M4/M5/M6 sections marked authored. M9-M13 "To Be Authored" retained as separate section. |
| v1.1 | March 13, 2026 | Arc 3 hooks authored and locked (M14–M19). Quest Collection position-based conditional system documented. Two non-compliant pre-existing skeleton hooks (M18, M19) replaced with rule-compliant versions. §5 updated to reflect Arc 3 completion. |

*— End of Document —*

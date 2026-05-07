# Module Authoring Guide

## MindfulNest / Everdale — Consolidated Rules for Module Content Creation

### Version 4.6 • March 13, 2026

---

## Purpose

This document compiles every rule, principle, and reference needed to author module content for MindfulNest. It is the single reference for anyone writing modules — human authors, AI drafting pipelines, or quality reviewers.

**When this guide and another document conflict, the resolution order is:**

1. Everdale World Design Bible v13.1 (intended canonical source — surface conflicts to Kim)
2. This guide (compiled from Bible + design session decisions)
3. Module JSON Schema Guardrails v2
4. Canonical Data Model v1.1

---

## 0. Module Design Process

Before writing any content, follow this sequence. Skipping steps — especially jumping straight to visual design or technique demonstration — is the most common source of module design failures.

### 0.1 Step 1: Identify the Core Insight

**What single thing does the child need to understand before this skill makes sense?**

The insight is not the technique. "Belly breathing" is a technique. "Your belly has magic in it, and breathing into it is different from breathing into your chest" is the insight. Every good module teaches an insight; the technique follows naturally from understanding it.

**Test:** Can you state the insight in one sentence a 7-year-old would find interesting? If not, you haven't found it yet.

**Anti-pattern:** Starting from the clinical technique ("How do I visualize 5-4-3-2-1?") and working backward toward the child. This produces a demonstration of the technique rather than a teaching of the insight.

**Validate the Therapeutic Mechanism (§0.1a).** Before proceeding past Step 1, confirm all four:

1. **Clinically supported?** Cite at least one primary source.
2. **Age-appropriate for 7–10?** Not a scaled-down adult technique. If the mechanism requires metacognitive overhead a 7-year-old can't sustain, redesign it.
3. **Distinct from existing modules?** A child who completed all prior modules would experience this as a NEW skill, not the same skill in a new context. Test: "Would a 7-year-old who already did [most similar module] say 'I already learned this'?"
4. **Efforting or releasing?** When the therapeutic goal is relaxation, release, or sleep onset, check whether the mechanism asks the child to DO something new (efforting) or STOP doing something (releasing). Asking a child to perform a cognitive task to achieve relaxation is self-defeating.

If any answer is no, redesign the mechanism before touching visuals. Rebuilding visuals is expensive. Rebuilding mechanisms is cheap.

### 0.2 Step 2: Ground It in the Child's Universal Experience

**When has EVERY child experienced this?**

Not "children in therapy" — every child. The experience must be universal enough that no specific pathology is assumed.

- "Your brain gets busy thinking stuff up and forgets where your body is" — every child
- "Everything is spinning and too much" — some children in crisis
- "You've felt a feeling so big it took over everything" — many children, but frames the skill as crisis-specific

**For introductory modules:** The entry point must be a life skill, not a crisis tool. The child should think "I can use this anytime" not "I'll use this when things go bad." Reserve crisis-application framing for intermediate modules where the base skill is already established.

**For intermediate modules:** The entry point can be more specific because the child already has the foundational skill. "Remember how you can find your body? Now you're going to learn that your body holds onto feelings — and you can help it let go."

### 0.3 Step 3: Choose Discovery vs. Recognition Frame

**Has the child already noticed this phenomenon?**

- **Recognition frame** (child has noticed): "You know when [experience]? That's what this magic is about."
- **Discovery frame** (child hasn't noticed): "I'm going to tell you something you might not know yet. [Revelation with concrete examples.]"

Most introductory modules use the discovery frame — the child hasn't noticed what their brain/body does automatically. Most intermediate modules use recognition — "Remember when we learned X? Now we're going to..."

### 0.4 Step 4: Design the Pedagogical Sequence

**What concepts does the child need, in what order?**

Write out the sequence of understanding before touching any visuals:

1. [First thing the child needs to know]
2. [Second thing, which builds on the first]
3. [The interaction moment — where understanding becomes action]
4. [The result — what the child sees happen because of their action]
5. [The bridge — connecting this to what they'll practice for real]

**Every visual element and every piece of dialogue must serve one step in this sequence.** If a visual doesn't map to a concept in the sequence, cut it. Visual complexity should serve understanding, not spectacle.

### 0.5 Step 5: Build the Metaphor Map

Now — and only now — design the visuals.

**For each concept in the pedagogical sequence, ask: "What is the simplest visual that communicates this?"**

The metaphor must match **what the skill feels like from the child's perspective**, not what it looks like in a clinical textbook. Ask: "If a 7-year-old could see what's happening inside them, what would they see?" — NOT "What does the clinician's model look like?"

See §4.3 for full metaphor mapping requirements.

### 0.6 Step 6: Write Dialogue (Phase A First, Then Backward)

Write Phase A dialogue first — this is where the teaching happens. Then write the Buy-In to set up what Phase A teaches. Then write the Call to set up the Buy-In. Working backward ensures each section serves the next without repeating it.

**State the learning goal explicitly** (§0.6a). Tell the child what they're going to learn and what it gives them, before beginning the demo. Don't leave the purpose mysterious. "We're going to learn magic to help your brain think stuff up AND remember your body at the same time." The child should know what skill they're gaining.

### 0.7 Step 7: Verify the Technique Follows From the Insight

Read the complete module flow aloud. Does the Phase B meditation feel like a natural "now you try it" after what the child just learned? Or does it feel like a separate exercise grafted onto the demo?

If Phase A teaches "your brain forgets where your body is, but you can find it by noticing your feet and hands," then Phase B should guide the child through finding their own feet and hands. The connection should be obvious and seamless.

---

## 1. The 5-Step Module Flow

Every module follows the same structure. The child is training an Ancient Art — never doing a therapy exercise.

| Step | Name | Time | Content Source | Key Rules |
|------|------|------|---------------|-----------|
| 1 | The Call | 10–20s | AI-generated, cached on bar document | See Section 2 |
| 2 | The Buy-In | 15–30s | AI-generated, cached on bar document | See Section 3 |
| 3A | Training: Phase A | 60–90s | Human-authored module JSON | See Section 4 |
| 3B | Training: Phase B | 60–120s | Human-authored ElevenLabs audio | See Section 5 |
| 4 | The Rescue | 20–30s | AI transition + module JSON visuals | See Section 6 |
| 5 | The Win | 15–30s | AI celebration + module JSON rewards | See Section 7 |

---

## 2. Step 1 — The Call

### 2.1 Emphasis Hierarchy (CRITICAL)

The Call is about the CHILD's training opportunity. The creature's problem is context, not the point.

**Sentence structure:**
- **Sentence 1:** Creature context (brief, secondary). State the creature's situation in one short sentence.
- **Sentence 2–3:** Magical training emphasis (primary). This is what the child is here to learn. The magic/skill is the central reason.

**Correct pattern:**
> "Tessa is shaking in her shell. There was a loud crash near the beach, and she can't calm down. This is a great chance to practice your Breath Awareness magic."

**Anti-pattern (NEVER):**
> "Tessa is trembling in her shell — there was a loud crash near the beach and she can't calm down. This is the perfect chance to practice your Breath Awareness magic. If you learn belly breathing, you can help Tessa feel safe again."

**Why the anti-pattern fails:** It frames the creature as the one who benefits from the child's practice. The child should feel they are growing their OWN magical power. The creature benefits during Rescue (Step 4), not during The Call.

**Call Excludes Experiential Description (§2.1a).** The Call never describes the child's experience of the problem. Creature context is brief and observable ("his brain is still going"). Experiential descriptions ("thoughts about tomorrow, thoughts about today, round and round") belong in the Buy-In, where Guide Bird connects the skill to the child's real life. The Call's job is creature context + magic emphasis + spiker. Nothing else.

### 2.2 Never Frame the Creature as Practitioner

The child learns; the creature benefits later. Never imply the creature will practice the skill.

**Anti-pattern:** "Tessa is pacing — her breathing is fast and shallow and she can't settle down."
**Why it fails:** It sounds like Tessa is the one who needs to breathe. The child may think they're teaching Tessa to breathe rather than developing their own magic.

**Correct:** "Tessa is upset and pacing back and forth. Our belly-breathing magic helped, but not all the way. We need to learn a stronger spell."

### 2.3 Full Call vs. Transitional Call

Modules are stacked in measuring bars. Only the **first module** in a bar gets a Full Call. All subsequent modules get a Transitional Call.

**Full Call** (first module in bar):
- Creature context + magical training framing
- Establishes the situation from scratch
- Pattern: "[Creature] is [problem]. [Brief context]. This is a [great chance / perfect moment] to [practice / sharpen / train] your [Art] magic."

**Transitional Call** (subsequent modules in same bar):
- Acknowledges previous success + introduces next skill
- Pattern: "Your [previous Art] magic worked — [brief creature progress]. Now it's time to learn an even stronger spell. This is some [advanced / powerful] magic."
- Example: "Our belly-breathing magic helped Tessa stop spinning, but she's still too rattled to think clearly. We need to learn a stronger spell. This is some advanced magic."

**Technical:** The AI narrative generation service produces both types. The module player checks circle index in the bar to determine which to display. The `callType` is determined at runtime, not stored in the module JSON (modules are context-free reusable units).

### 2.4 Call Framing Rule

**For intermediate/advanced modules:** Frame new techniques as more powerful versions of something the child already knows — ideally by showing that a simpler approach already failed.

"Ember already said 'sorry' but it didn't work" is stronger than "Ember needs to apologize." The first creates need for an UPGRADE; the second implies the child doesn't know the basic skill.

**Principle:** Frame new techniques as more powerful versions of something the child already knows, not first introductions. This respects what the child already knows while motivating them to learn more.

**Examples:**
- **Upgrade framing (good):** "Ember said 'sorry' but it didn't work. This is a great chance to learn an extra-strong Kindness spell — the Friend-Fix Bridge."
- **First-introduction framing (avoid for intermediate):** "Ember needs to learn how to apologize." (implies the child doesn't know how)

**For introductory modules:** Upgrade framing doesn't apply because this is the child's first skill in the domain. Instead, the Call establishes WHY the domain matters by showing the creature's specific, relatable situation. The creature's problem should demonstrate the NEED for this type of magic, not reference previous skills.

### 2.5 Excitement Spiker Rule

Every Call must include a brief excitement spiker — a short phrase that makes the child feel energized about the upcoming training. This is not the creature's problem and not the magic description — it's a pure motivational beat aimed at the child.

**Examples:** "This one's fun!" / "You'll be much stronger after this!" / "This is some advanced-level magic." / "You're going to love this one."

The spiker can be its own sentence or tagged onto the magic-emphasis sentence. It should feel natural, not forced — like an enthusiastic mentor, not a commercial.

**Vary Spiker Language Across Modules.** Do not use the same excitement spiker in every module. If the child hears "You're going to love this one" in Module 1, 2, 3, and 4, they stop believing it. Rotate spikers across modules so each one feels fresh.

**Examples of variety:** "You're going to love this one." / "Wait till you try this one." / "This one's unusual." / "This is powerful." / "You won't believe this one." / "This is some advanced-level magic." / "You'll be much stronger after this!"

**Rule:** No two modules in the same domain may use the same spiker phrase.

### 2.6 Personalization in Dialogue (TTS Pipeline)

All character dialogue is rendered via TTS (ElevenLabs), enabling personalization. When writing any spoken dialogue — Call, Buy-In, narrative setup, map sprites, resolution — use `{childName}` where a character would naturally address or reference the child. Use `{chosenGuideName}` when referencing the Guide Bird by name. Frequency: 1-2 uses of `{childName}` per scene is natural. Do NOT use it in every sentence.

**Stage directions and production notes** continue to say "the child" — only SPOKEN dialogue uses variables.

**Available variables:** `{childName}`, `{chosenGuideName}`, `{therapistName}`, `{therapistPronoun}`, `{parentTitle}`, `{parentPronoun}`, `{childPronoun}`, `{childPronounObject}`, `{childPronounPossessive}`. See `TTS_PERSONALIZATION_PIPELINE_v1.md` for the full variable registry, substitution rules, and rendering pipeline.

**Phase B personalization:** Myrrhin (the meditation narrator) uses `{childName}` exactly twice per stem — opening line and closing line only. The body of the meditation uses "you."

### 2.7 Call Emphasizes Child's Power, Not Abstract Problem Weakness

The Call should make the child feel powerful about what they're going to learn. Avoid abstract descriptions of what the skill does to the problem ("worries have a secret weakness," "this spell makes worries shrink"). Instead, tell the child how powerful THEY will become after learning this.

**Anti-pattern:** "Time for some seriously powerful Courage magic. This spell? Worries are SCARED of this one." (Abstract — what does "scared" mean for a worry?)

**Correct:** "Time for some seriously powerful Courage magic — you'll be SO much stronger after this one." (Concrete — the child becomes stronger.)

**Test:** Would a 7-year-old understand what happens to THEM, or only what happens to the problem?

### 2.7 Creature Scenario Design

The creature's problem in the Call sets the stage for the entire module. Getting it wrong cascades through Buy-In and Phase A.

**2.7a — Creature Problem Must Match Phase A Concept.** The creature's scenario should demonstrate the SAME phenomenon the module teaches about. If the module teaches "your brain gets busy and forgets your body," the creature's problem should be brain-busy-forgot-body — not sensory overwhelm, not emotional crisis, not something only tangentially related.

**2.7b — Creature Thoughts Must Be Relatable.** When describing what a creature is experiencing, include 2–3 specific thoughts that children in the target age range actually have, stated in the child's own language. The child should recognize their own thoughts in the creature's head.

- **Abstract (avoid):** "Everything is hitting Bramble at once — too loud, too bright, too much."
- **Relatable (correct):** "Bramble's brain is thinking up a storm! He wonders where his mom is. He thinks his friends may be having fun without him. He wants to play a game."

**Test:** Would a 7-year-old hear this and think "oh, I think those things too"?

**2.7c — Playful Energy for Foundational Skills.** Creature scenarios for introductory/foundational skills (body awareness, present-moment awareness, listening) should feel like a brain being busy or silly, not a creature in distress. Reserve distress framing for modules where the emotion itself is the subject (worry, anger, sadness, fear).

- **Distress framing (for emotion-focused modules):** "Benson can't stop worrying — every thought feels scary."
- **Playful framing (for foundational skill modules):** "Bramble's brain is thinking up a storm! He tripped over a rock because his brain forgot his feet were there. Silly brain."

**Why this matters:** Distress framing for a foundational skill implies the skill is only for bad moments. Playful framing positions it as something cool you can do anytime.

### 2.8 Call Checklist

- [ ] Magic/skill emphasis is the sentence that lands (not the creature's problem)
- [ ] Creature's state is described briefly — one sentence max
- [ ] Child is never told the creature will practice the skill
- [ ] No clinical language (anxiety, regulation, coping, therapy, mindfulness)
- [ ] 2–3 sentences max total
- [ ] Uses "magic" or "spell" language, never technique names in isolation
- [ ] Where possible, upgrade framing for intermediate modules (§2.4)
- [ ] Discovery framing for introductory modules (§2.4)
- [ ] Contains an excitement spiker (§2.5)
- [ ] Spiker language varies from other modules in same domain (§2.5)
- [ ] Call emphasizes child's power growth, not abstract problem weakness (§2.6)
- [ ] Creature scenario uses specific relatable thoughts (§2.7b)
- [ ] Creature energy matches skill type: playful for foundational, distress for emotion-focused (§2.7c)
- [ ] Application context named explicitly — creature's situation is concrete, not vague (§3.8)

---

## 3. Step 2 — The Buy-In

### 3.1 Core Pattern

Guide Bird connects the Ancient Art to the child's real life. Frames the skill as magic the child already possesses.

**Two patterns depending on discovery vs. recognition frame (see §0.3):**

**Recognition pattern** (child has already noticed this phenomenon):
> "You know when [relatable kid experience]? [Brief normalization]. But [reframe as magic the child already has]."

> Example: "Ever gotten upset about something that happened at home or at school, and had a hard time calming back down? Belly breathing is how you calm yourself down. You already have this magic inside you."

**Discovery pattern** (child may not have noticed this yet):
> "[Revelation the child hasn't considered]. [Concrete examples they recognize]. [Affectionate humor]. [State learning goal explicitly]. [Empowerment — this is magic you'll master.]"

> Example: "I'm going to tell you something you might not know yet. Your brain? It is really smart, and that means it's really good at thinking stuff up. It imagines what might happen tomorrow. It remembers your breakfast. It hopes good things will happen. It worries bad things might happen. Sometimes your smart brain gets SO busy thinking stuff up, that... it kind of forgets where your body is. Silly brain. We're going to learn some magic to help your brain think about stuff, and also remember your body, at the same time. It's called Body Awareness magic. Body Awareness magic makes you a real master."

**When to use which:** Introductory modules in domains where the base phenomenon is unconscious (body awareness, present-moment awareness, self-grounding) typically need the discovery pattern. Modules in domains where children already recognize the feeling (breath awareness, courage, kindness) typically use the recognition pattern.

### 3.2 Language Consistency Rule (Phase A Sets the Language)

**The metaphor and emotional framing used in Phase A's instruction cues must set the language for the Call and Buy-In.** If Phase A describes being "upset" and needing to calm down, the Buy-In must use "upset" language — not "shaky," "buzzy," or a different emotional frame.

The Call and Buy-In are narrative wrappers that LEAD INTO Phase A. If they describe a different emotional experience than what Phase A teaches, the child hears a disconnect: "Wait, I thought we were talking about feeling shaky, now we're talking about being upset?"

**Process:** Write Phase A first. Then write the Buy-In and Call using the same emotional vocabulary Phase A establishes.

**Example of mismatch (bad):**
- Buy-In: "You know that shaky feeling when something loud happens? Like your body buzzes?"
- Phase A: "Watch what happens when you're upset and only breathe into your chest."
- *Problem: "shaky/buzzy" ≠ "upset" — different emotional frames.*

**Example of match (good):**
- Buy-In: "Ever gotten upset about something and had a hard time calming back down?"
- Phase A: "Watch what happens when you're upset and only breathe into your chest."
- *Both use "upset" — seamless transition.*

### 3.3 Buy-In Length and Density

**The Buy-In should be as long as it needs to be and no longer.** The previous rule of "2–3 sentences maximum" is superseded. A recognition-frame Buy-In for a familiar concept may need only 2 sentences. A discovery-frame Buy-In that introduces a concept the child has never considered may need 6–8 sentences.

**The test is purposefulness, not word count.** Every sentence must do one of these jobs:
1. Reveal something the child didn't know, or connect to something they do know
2. Give a concrete example the child can picture
3. Normalize with warmth or humor
4. State the learning goal
5. Empower ("you already have this magic" / "this makes you a master")

If a sentence doesn't serve one of those five purposes, cut it.

### 3.4 Skill Framing Principles

These three principles govern how the skill is POSITIONED for the child — not what it does, but how the child feels about learning it.

**3.4a — Compliment Before Redirect.** When introducing a concept that involves something the child does unconsciously, frame the existing behavior as a strength first. The skill being taught is an enhancement, not a correction.

- **Correction framing (avoid):** "Sometimes your brain wanders away and you need to bring it back."
- **Compliment framing (correct):** "Your brain is really smart, and that means it's really good at thinking stuff up. Sometimes it gets SO busy that it forgets where your body is."

The brain isn't broken for wandering. It's smart. This skill makes the child even MORE capable.

**3.4b — Both/And Framing.** Never imply the child needs to STOP doing something. Frame the skill as adding a new ability alongside what they already do. The child's existing behavior is fine; the skill makes them more, not less.

- **Either/or (avoid):** "Stop your brain from wandering and come back to your body."
- **Both/and (correct):** "Help your brain think about stuff AND also remember your body at the same time."

This applies to all modules: belly breathing doesn't replace chest breathing, it adds a tool. Thought observation doesn't stop thoughts, it adds awareness alongside them. Worry naming doesn't eliminate worry, it adds manageability.

**3.4c — Skill as Enhancement, Not Repair.** Frame every skill as a new ability the child gains, not as a fix for a deficit. The child should feel they are gaining a superpower, not receiving treatment.

- **Repair framing (avoid):** "When your brain gets too busy, this helps fix it."
- **Enhancement framing (correct):** "Body Awareness magic makes you a real master."

### 3.5 Containment Language: Softer, Not Weaker

When describing the effect of naming, containing, or managing emotions in Buy-In or Phase A dialogue, use "smaller and softer" — never "smaller and weaker." "Weaker" frames worries as adversaries to be defeated (combat metaphor). "Softer" frames worries as losing their sharpness (containment metaphor). This aligns with the clinical model: regulation, not suppression. The worry still exists; it just becomes manageable.

**Anti-pattern:** "Worries get smaller and weaker. Once they're weak..."
**Correct:** "Worries get smaller and softer. Once they're small and soft..."

### 3.6 Affectionate Humor

When normalizing a brain/body phenomenon, use warm, playful language. The child should feel amused, not diagnosed.

- **Clinical neutrality (avoid):** "Your brain sometimes loses track of your body. That's called dissociation."
- **Affectionate humor (correct):** "Sometimes your smart brain gets SO busy thinking stuff up that it forgets where your body is. Silly brain."

**"Silly brain" > "wandering brain" > "dysregulated brain."** The first makes the child laugh. The second is neutral. The third is clinical. Always aim for the first.

### 3.7 Rules

- Buy-In length is driven by purpose, not word count (§3.3)
- The Buy-In is narrative wrapper (motivation/connection), NOT therapeutic instruction — bright line maintained
- **Buy-In may promise an OUTCOME but must not reveal the MECHANISM (§3.7a).** "Slows the thought-stream down" promises what the skill achieves. "Give your brain something peaceful to focus on" reveals how it works. The mechanism is Phase A's job. If the Buy-In explains how the skill works, Phase A has nothing left to demonstrate.
- Always ends with empowerment: "You already have this magic" / "Body Awareness magic makes you a real master"
- No clinical language
- No technique instruction (that belongs in Phase A)
- Age 7–10 vocabulary throughout
- Skill framed as enhancement, not repair (§3.4c)
- Existing behavior complimented before new skill introduced (§3.4a)
- Both/and framing — skill adds, never removes (§3.4b)
- Containment language uses "softer" not "weaker" (§3.5)
- Uses affectionate humor where appropriate (§3.6)

### 3.8 Name the Application Context

When a module targets a specific real-world situation (bedtime, a test, a fight, waiting at the dentist), the Call and Buy-In must name that situation explicitly. The child should be able to answer: "When would I use this?" after hearing the Call.

Vague situational language ("those times when you lie down") robs the child of a concrete anchor in their own life. Specific language ("those nights when you lie down to sleep") gives the child a memory to attach the skill to.

**Anti-pattern:** "Bork's trying to settle in, but his body keeps twitching."
**Correct:** "Bork's trying to settle in and fall asleep, but his body keeps twitching."

**Anti-pattern:** "You know those times when you lie down but your body won't stop moving?"
**Correct:** "You know those nights when you lie down to sleep but your body won't stop moving?"

**Test:** After hearing the Call/Buy-In, can the child name ONE specific moment in their life where this applies? If the language is too vague for that, make it more concrete.

---

## 4. Step 3A — Training: Phase A

### 4.1 What Phase A IS and IS NOT

**Phase A IS:** Instructional. The Guide Bird SHOWS the child how the spell works using a visual metaphor the child interacts with. The child learns the CONCEPT.

**Phase A IS NOT:** Experiential. The child does not practice the skill. They do not close their eyes. They do not breathe in pattern. That is Phase B.

**Phase A is Training Only.** Phase A does not repeat content already covered in the Call and Buy-In. It is ONLY the instructional demonstration. If the prep frame is re-explaining why the skill is needed, the author is doing the Call's job inside Phase A.

**Phase A Starts Where the Buy-In Left Off.** The Buy-In's job is to explain the concept and create motivation. Phase A's job is to SHOW it. If the Buy-In already told the child what kind words do, Phase A doesn't tell them again — it just talks the child thru the demonstration. The prep frame should contain at most one short bridge sentence to set attention, never a re-introduction of the concept. **Test:** cover the Buy-In text and read only Phase A's dialogue. If Phase A makes complete sense on its own without the Buy-In, it's probably repeating it.

**Phase A Setup Is Self-Contained (§4.1a).** Phase A setup introduces the current scene without referencing previous modules. If the creature's state implies previous work (e.g., body already calm because an earlier module taught body softening), that state is simply VISIBLE — the child sees it without being told about it. Narrating "we helped with that before" adds complexity without teaching value and breaks the module's self-containment. **Exception:** Transitional Calls (§2.3) DO reference previous success because that's the Call's job. Phase A does not.

**Warmth/Kindness Physicalization (§4.1b).** Phase A for warmth and kindness techniques must ground the experience in physical sensation — hands on heart, warmth spreading in the chest, the feeling of a hug. Phase A must NOT deliver a cognitive instruction ("think kind thoughts" or "imagine sending kindness"). The body must do the therapeutic work, not the metaphor. If a child cannot FEEL the warmth physically, the technique has not been demonstrated.

**Phase A Demonstrates in the Game World, Not the Child's Life (§4.1c).** Phase A uses the game world to demonstrate the technique. "Watch Luna's thought-clouds drift past" is correct. "Imagine YOUR thoughts as clouds" crosses from demonstration into the child's personal experience — that belongs in Phase B. Phase A narrates what the CREATURE does; Phase B is when the child does it themselves.

**Count-Structured Techniques Need Visual Scaffolding (§4.1d).** For techniques with counting patterns (4-7-8 breathing, sequential steps), Phase A should demonstrate the count VISUALLY — a countdown display, Guide Bird counting aloud, or numbered visual beats — rather than relying on the child to maintain an internal count while emotionally activated. A 7-year-old holding a breath for a count of 7 while upset cannot also count internally. The screen counts for them.

### 4.2 The One Demo Cycle Rule

Phase A is ONE demonstration, narrated, done. The child watches (and possibly interacts with) one pass through the concept, then moves to Phase B.

**This means:**
- One breathing cycle, not three
- One cloud sequence, not repeated rounds
- One bell, one tap
- Error correction within a single flow (e.g., child taps wrong target, gets feedback, tries again) is NOT a second cycle — it's behavioral shaping within one pass

**Clarification — concept completeness, not tap count.** Multiple taps demonstrating sequential steps of ONE concept is still one demo cycle. Building a bridge takes three planks — that's one demo of bridge-building. Softening the body requires visiting multiple parts — two body parts is one demo of "visit each part one at a time." The rule prohibits repeating the same concept for practice (that's Phase B's job). It does NOT prohibit the number of interactions needed to demonstrate the concept once.

**If we must choose between including an interactive component and respecting the One Demo Cycle rule, we ALWAYS choose to respect the One Demo Cycle rule.** It is more important to teach the core insight clearly and concisely than to include interaction for its own sake.

**Once the core mechanic has been demonstrated, go directly to the bridge. No bonus content, no cascading consequences, no "and also..." effects.** Each additional consequence extends Phase A beyond the core cycle and may introduce concepts that don't transfer to Phase B.

**The test:** Will the child experience this effect during the eyes-closed Phase B meditation? If no, cut it from Phase A.

### 4.3 Metaphor Mapping (Mandatory Pre-Work)

**Before writing any Phase A flow, the author must produce a Metaphor Map listing every on-screen element, what therapeutic concept it represents, and what the child's interaction with it teaches.** This map appears at the top of the Phase A proposal, before the flow steps.

Every visual element, every interaction, and every piece of Guide Bird dialogue must serve this mapping logically. If something doesn't map — if it's decorative, redundant, or breaks the metaphor — it doesn't belong.

**Format:**

> **Module X: [Title] — Metaphor Map**
>
> *Visual elements:*
> - [Element] = [what it represents]
> - [Element] = [what it represents]
>
> *Child's interaction:*
> - [Action] = [what cognitive/behavioral act this teaches]
>
> *Consequence:*
> - [What changes on screen] = [what therapeutic mechanism this makes visible]

**Example — Module 5: Warm Heart**

> *Visual elements:*
> - Heart (dim, grey) = child's capacity for kindness (the source)
> - Outward path → creature = directing kindness to others
> - Inward path → back to heart = directing kindness to yourself (the heart loving itself)
> - Glow-orb = the kindness/warmth that travels
>
> *Child's interaction:*
> - Tap inward path = choosing to try self-kindness
>
> *Consequences:*
> - Heart grows gold = self-kindness works, it changes you
> - Glow-orb fades on timeout = not ready yet, that's normal (no failure)

**Example — Module 9: Sense Anchor**

> *Visual elements:*
> - Child silhouette = the child's body (always here)
> - Thought bubbles around head = busy brain thinking stuff up (normal, not pathological)
> - Dim contact points at feet/hands = body the brain isn't paying attention to yet
> - Contact point lighting up gold = brain noticing the body
> - Thought bubbles settling (not vanishing) = brain still thinks but also knows where body is (both/and)
>
> *Child's interaction:*
> - Tap feet contact point = choosing to notice "feet on the ground"
> - Tap hand contact point = choosing to notice "hands right here"
>
> *Consequences:*
> - Contact point glows gold = brain found the body there
> - Thoughts settle but remain = thoughts are fine, body awareness is ADDED (not substituted)
> - Scene brightens = "grounded" — brain and body connected

**Every element in the Phase A flow must trace back to this map. If an element isn't on the map, it doesn't belong in the flow.**

**Metaphor Consistency Rule:** Every on-screen element must map to the module's core metaphor. Before adding any visual element, check: "What does this represent in the metaphor?" If the answer is "nothing, it just looks nice" or "it reinforces the feeling" — it doesn't belong.

**Metaphor Must Match Child's Experience (§4.3a).** The visual metaphor should represent what the skill feels like FROM THE CHILD'S PERSPECTIVE, not what it looks like in a clinical textbook. Ask: "If a 7-year-old could see what's happening inside them, what would they see?" — NOT "What does the clinician's model look like?"

- **Clinical model (avoid):** A room-scanning exercise visualized as fog clearing from objects in the environment (visualizes the 5-4-3-2-1 technique)
- **Child's experience (correct):** A silhouette with a busy brain and unnoticed body — tap to notice (visualizes the insight: your brain forgot where your body is)

**Abstract Metaphors Must Map to Concrete Actions (§4.3b).** Phase A metaphors must depict real-world situations a child recognizes, not abstract representations of internal processes. A wave graph of anxiety rising and falling is abstract — a child standing at the base of a slide wanting to climb it is concrete. Test: "Can a 7-year-old point to this situation in their actual life?" If not, make it more concrete.

**Start With Something the Child Can Already See (§4.3c).** When introducing a Phase A scene, start with at least one element that is already labeled, readable, or recognizable — not a wall of blank unknowns. Pre-label one element to reduce overwhelm and give the child an anchor. Example: one worry cloud already has visible text ("What if something bad happens?") before the child is asked to name anything.

**Merge Setup Narration and Visuals (§4.3d).** When the visual setup and Guide Bird's description of it serve the same purpose, combine them into a single integrated step. Don't have a separate "show clouds" visual step followed by a separate "describe clouds" dialogue step when both could happen simultaneously.

### 4.4 Interaction Design Rules

**Minimum Necessary Interaction.** Use only the minimum number of interactions needed to logically convey the concept to the child. Don't add interactivity for interactivity's sake. We are not teaching children to press buttons. Interactions exist to help the child understand the concept through action. If a concept can be taught with one tap, don't use two. If it genuinely requires three taps (like building a three-plank bridge), use three — but be sure each tap teaches something the others don't.

Don't add alternative interaction paths (like a "skip" button) when they don't serve the concept. If the teaching only needs one action target, adding a second target is unnecessary complexity. If the child doesn't tap, a timeout handles it.

**Interaction Shape Matches Skill Shape.** The interaction mechanic should mirror the shape of the therapeutic skill being taught. Don't default to the same pattern for every module.

| Skill Shape | Interaction Mechanic | Example |
|---|---|---|
| Choosing (this vs. that) | Choice mechanic — two targets, consequence feedback | Chest vs. belly (Module 1), positive vs. negative thought (Module 3) |
| Building (piece by piece) | Construction mechanic — sequential assembly steps | Three-plank Sorry Bridge (Module 6) |
| Staying (enduring/waiting) | Stay/leave mechanic — binary choice with dramatic consequence | Stay vs. run on the anxiety wave (Module 7) |
| Naming (labeling/externalizing) | Naming mechanic — tap to reveal label, see the effect | Name the worry, watch it shrink (Module 8) |
| Noticing (finding/discovering) | Discovery mechanic — tap to notice what was already there | Find the feet, find the hands (Module 9) |
| Observing (watching/noticing) | Watch-only — auto-demo with distinct visual phases, no interaction | 4-7-8 breathing circle (Module 2) |
| Permitting (releasing/letting go) | Permission mechanic — tap target is CREATURE (or creature's relationship with problem), not the problem itself; problem resolves as secondary consequence | Tap Bork to stop grabbing thoughts (Module 12) |

Prioritize teaching the skill clearly over concerns about interaction count — but within that, always use the minimum steps needed for that particular skill shape. Phase A can have multiple interactions if they're fast and sequential. One Demo Cycle means one demo of the concept, not one tap. Three quick taps building a bridge is still ONE demo of bridge-building.


**One Clear Prompt Per Interaction (§4.4b).** Each interaction moment should have exactly one action target and one clear prompt. "Tap that worry and give it a name" — one action, one target. Don't present competing actions (tap path vs. tap skip) because that forces a decision between engagement and avoidance, which is a different cognitive load than the module intends. If the child doesn't act, the timeout handles it.

**Exception:** When the skill involves choosing WHERE to act (e.g., "find one of his hands" — left or right), multiple targets for the same action are fine because the child isn't choosing between different actions, just where to perform the same action.

**Active/Magical Framing in Prompts (§4.4c).** Guide Bird uses active, Keeper-role language when prompting interactions. "Anyone you want to help" (active, agency) > "someone you care about" (passive, existing feelings). The child is a Keeper who acts — not a recipient of pre-existing emotions.

**Interaction Serves the Lesson, Not the Format.** Phase A demos should use the minimum interaction necessary to teach the concept. Some modules are pure auto-play with zero taps — if the lesson is "watch what happens," watching IS the learning. Other modules require a tap because the lesson IS the choice — the child must consciously decide to act. The test: "Does the concept being taught require the child to make a conscious decision?" If yes, that decision must be a tap. If the concept is "observe this process" or "see what this looks like," auto-play teaches it better than a tap would. Never add taps to make a demo feel more "interactive." Never remove taps when the lesson is "you choose to do this."

**Running Away Works (Short-Term) (§4.4d).** When demonstrating avoidance vs. approach, don't pretend avoidance fails. Avoidance DOES reduce fear — that's why people do it. The lesson is that avoidance removes the choice. Show both honestly: running makes fear smaller BUT puts you far from the thing you wanted. The contrast is about agency, not about which path reduces fear.

**Fear Doesn't Disappear — You Leave It Behind (§4.4e).** When teaching approach behavior, show fear still present but no longer controlling the child's position. A shadow staying big while the child walks away from it is more honest than the shadow shrinking. Courage isn't the absence of fear; it's acting despite fear. Phase A visuals for courage modules should show the fear element remaining visible but left behind.

### 4.5 Consequence Feedback

Every interactive moment has a visible result — the child sees what their choice DOES. This is the therapeutic mechanism, not gamification. Self-regulation requires understanding that your actions change your internal state.

- Correct choice → positive visual transformation (environment brightens, warmth, sparkles)
- Incorrect choice → gentle correction with a second chance (never punishment, never "wrong!")

**Consequences Must Be Addition, Not Elimination (§4.5a).** When the skill is about awareness or regulation (not about defeating a problem), the consequence should ADD something visible — a gold glow appearing, clarity increasing, the body becoming more vivid — rather than REMOVE something. Thoughts settling but remaining present is therapeutically honest. Thoughts vanishing implies suppression.

**Traceable Causal Chain (§4.5b).** The Phase A demo must show a visually traceable path from the child's action to the creature's stated problem improving. Three links must be visible on screen and readable without narration:

1. Child acts (tap/interaction)
2. Something changes (immediate visual consequence)
3. Creature's stated problem visibly improves

If the child can't point to what they did, what changed, and how the creature got better — the causal chain is broken. A metaphor that only represents the skill's occurrence (abstract change elsewhere on screen) is weaker than one that shows the skill's effect flowing to the creature.

**Test:** Cover the dialogue. Can a child watching the animation alone trace: "I did that → that changed → creature is better"?

### 4.6 Timeout / Fallback Rule

**Every interaction must have a timeout fallback.** The child must always see the complete visual consequence regardless of whether they complete the interaction.

If the child doesn't tap, drag, or otherwise respond within ~8 seconds, Guide Bird gently assists. Timeout assistance is framed as SHOWING, never as helping or correcting:

- **"Let me show you where to put it"** (I'm demonstrating) ✔
- **"Let me help you"** (you need help) ✗
- **"You didn't do it"** (failure) ✗

The visual consequence plays automatically after timeout. The therapeutic teaching moment cannot be contingent on the child's motor skill execution or willingness to interact.

For emotionally sensitive interactions (e.g., self-kindness in Module 5), the opt-out should be passive (timeout) rather than active (skip button). A timeout lets the child simply not engage without self-judgment. A skip button forces the child to consciously declare avoidance.


**Timeout Says "Just Watch," Not "That's OK."** When a child doesn't interact within the timeout window, Guide Bird says "Just watch" (or similar observational redirect) and the animation plays automatically. Guide Bird does NOT say "That's OK" — because "That's OK" assumes the child made a conscious choice to skip. The child may have been confused, distracted, or simply couldn't respond fast enough. "Just watch" is neutral — it redirects attention to the visual without interpreting the child's behavior. This applies to ALL timed-out interactions universally, with no exceptions.

### 4.7 Instruction Cue Rules

**Cue 1 is ALWAYS a preparatory frame** — "I'm going to show you how this works first, then you'll try it for real" — BEFORE any instruction content. This eliminates the child's perception of doing the same thing twice.

**Prep Frame Brevity.** If the Buy-In did its job, the prep frame needs at most one short sentence of setup + "Watch — then you'll try for real." Don't re-explain in the prep frame what the Buy-In already established. Use minimizing language when the skill could feel intimidating ("just three little pieces" > "it takes three pieces"). The prep frame's only job is to set attention.

**Active Invitation Over Passive Observation (§4.7a).** Setup language should invite the child to help ("Let's help him do some Body Awareness magic and remember") not to passively observe ("Watch what happens, see that?"). The child is a participant from the beginning. Even during the demo phase where the child is observing, frame it as preparation for THEIR action: "Let's help him... then you'll try it for real on yourself."

**Explicit Self-Application Bridge (§4.7b).** Setup must explicitly connect the demo to the child's own body/experience. "Then you'll try it for real on yourself" — not just "then you'll try it for real." The child needs to know that what they're seeing demonstrated on the creature or silhouette is something they will do WITH THEIR OWN BODY.

**Middle cues narrate the demo** — what the child SEES on screen, framed as instruction ("here's what will happen") not experience ("you're doing it now").

**Final cue bridges to Phase B** — "Now you're going to try it for real."

**Bridge Brevity.** Bridge cues should be as brief as possible. Prefer questions over statements. Never summarize the demo. If the demo was clear, the bridge needs almost nothing. "Ready to try it for real?" (5 words) is often better than a 3-sentence recap. Summarizing the demo signals the author doesn't trust the visuals to have taught. Questions ("Ready to try?") hand the transition to the child and create internal motivation. Statements ("Now you're going to try") direct the child.

**One Bridge, Then Done.** The bridge from Phase A to Phase B is a single beat — one line or one short dialogue that moves the child forward. If the settled-state observation already contains a bridge ("Let's practice this magic sleeping trick right now…"), do not add a second state with another bridge ("Ready to try it on yourself for real?"). Two consecutive bridge statements are redundant — the first already did the job. The settled observation and the bridge can live in the same line. If they do, that line is the last Phase A dialogue before Phase B begins.

**Cue count is VARIABLE** — driven by what the demo actually needs:
- Simple watch-only demo: 3 cues (prep frame, data delivery, bridge)
- Rich interactive demo: 4–6 cues (prep frame, demo narration, consequence narration, bridge)

**NO sequential round cues.** Triggers like `after_breath_1`, `after_breath_3` imply repetition, which is experiential (Phase B thinking). Phase A is one demo, narrated, done.

**Minimal surrounding language when data-heavy.** When explicit rules or data points are heavy (e.g., "4 seconds in, 7 seconds hold, 8 seconds out"), keep surrounding language minimal. The VISUAL does the teaching.

### 4.8 Phase A Visual Rules

**Observable Language Only.** Phase A visual descriptions describe what things LOOK LIKE on screen, not what things FEEL LIKE to the child.

- **Observable:** "The heart grows slightly, gold colors, magic, beautiful." / "The cloud visibly SHRINKS." / "The screen opens up — more space, more light."
- **Somatic/experiential (avoid in Phase A):** "Warmth fills the silhouette from the chest outward — slower, quieter, deeper." / "You can feel the lightness."

Phase A is instructional. The child SEES concepts demonstrated. Phase B (eyes closed, guided meditation) is where feelings live.

**Proximity Drives Intensity (§4.8b).** If the metaphor involves approaching something scary, the fear indicator should scale with proximity. Shadow grows as child walks toward the slide; shadow shrinks as child walks away. This is somatically accurate — anxiety increases with approach — and teaches the child to expect and recognize the feeling without being surprised by it.

**The Scene Must Be Wide Enough for the Metaphor (§4.8c).** If the lesson requires visible spatial separation (child here, fear there, goal over there), the scene layout must have enough room for each element to be clearly distinct. 20px of separation between objects that are supposed to be "far apart" defeats the metaphor. Test: after the key visual moment, can the child clearly see that two things are in different places?

**No Potentially Activating Content on Screen (§4.8d).** Phase A demo content should be universal and non-triggering. "What if nobody likes me?" could mirror a child's real fear and create distress. "Fear" is a safe, abstract label. Specific anxious thoughts belong in Phase B (personalized practice), not Phase A (concept teaching). When a module involves naming emotions, the naming targets should be EMOTION LABELS ("Fear," "Worry," "Sadness"), not specific anxious thoughts ("What if nobody likes me?").

**Exception for creature thought bubbles:** When the module uses thought bubbles to show what a creature is thinking (as in Module 9), the thoughts should be RELATABLE and ORDINARY ("where's mom?", "I wanna play a game"), not distressing or anxiety-provoking. The thoughts demonstrate a busy brain, not a troubled one.

**Bridge Visual Objects to the Child's Experience.** When a new visual object appears, Guide Bird explicitly labels what it represents, connecting the abstract visual to something the child already knows. Don't assume a 7-year-old recognizes what an on-screen heart, wave, or cloud represents.

- "This is your heart, like the one in your chest."
- "See this? This is what the scared feeling looks like."
- "Those are like worries in your mind."

Use similes ("like worries," "like the one in your chest") when appropriate — this preserves the instructional frame by keeping the visual as a teaching object rather than collapsing it into the real thing.

**The Child Is Always a Silhouette.** In Phase A demos, the child's avatar is always represented as a silhouette — never as a detailed character pretending to be the child. The silhouette maintains the child's projection space (they see themselves in it) and stays consistent across all modules. A specific character with hair, clothes, and expressions collapses the projection space into someone who isn't the child.

### 4.9 Guide Bird Dialogue Rules

**Never Assume the Child's Inner State.** Guide Bird never tells the child what they're thinking, feeling, expecting, or finding difficult. This includes assumptions about preconceptions ("It's not what you think"), emotional states ("You're feeling scared right now"), expectations ("You probably thought it would keep going"), or difficulty ("This is the hard part"). Guide Bird describes what's on screen, labels concepts, and asks questions — it doesn't narrate the child's inner experience. If Bird needs to reference a common experience, it uses "most people" or shares its own experience, never "you."

**No Assumed Pathology.** Guide Bird never assumes the child has a particular emotional difficulty, especially adult-characteristic pathologies. Never tell the child what they will find hard.

What's difficult varies enormously by individual child. Some children find self-kindness effortless. Some find it impossible. Guide Bird doesn't predict or label which parts are "hard" or "harder" — that assumes a pathology the child may not have.

- **Wrong:** "That's the harder magic" / "Sending kindness to yourself is the hardest part" / "Most people find this one tricky"
- **Right:** [child skips/times out] "That's OK — it takes practice."

**Exception:** Framing something as "advanced magic" in the Everdale context is fine, because that's game-world difficulty, not emotional diagnosis. "This is a really powerful Breath Awareness spell" ≠ "This will be emotionally hard for you."

Normalization happens AFTER the child's response, not before. If the child skips, normalize gently. If they don't skip, celebrate. Never pre-normalize by warning that something will be difficult.

**Normalize by Sharing, Not Analyzing.** When normalizing an experience, Guide Bird shares its own experience rather than describing the child's.

- **Sharing (good):** "Have you ever worried that worry? I sure have."
- **Analyzing (avoid):** "When you don't name them, they stay big and scary."

Sharing is relational and bidirectional — Guide Bird is a companion who has also experienced this. Analyzing is observational and clinical. Guide Bird is a friend, not a therapist.

**Concrete Examples, Not Abstract Categories (§4.9a).** When describing mental, emotional, or sensory experiences in any dialogue, use specific scenarios a child in the target age range would recognize, rather than abstract categories. Each example should be a thought or feeling the child has actually had.

- **Abstract categories (avoid):** "It thinks about things, it notices things, it worries about things"
- **Concrete examples (correct):** "It imagines what might happen tomorrow. It remembers your breakfast. It hopes good things will happen. It worries bad things might happen."

**Test: Can the child picture this?** If a sentence describes an abstract state ("your body knows where you are"), replace it with a concrete scenario the child can visualize ("your brain imagines what might happen tomorrow, it remembers your breakfast"). If you can't generate a specific visual for a sentence, the sentence is too abstract.

**Simultaneous Movement and Dialogue (§4.9b).** When the visual IS the lesson (child approaching = shadow growing), dialogue and movement should happen together. Don't freeze the child in place while Bird talks, then animate silently. The child watching the shadow grow WHILE hearing the explanation is the teaching moment.

**Combine Sequential Single-Sentence Dialogues (§4.9c).** If two consecutive dialogue beats have no visual change between them and flow as one thought, they belong in one popup. "The scared feeling decides for them. It's the boss." is one beat, not two. Unnecessary splitting breaks reading flow and makes the module feel choppy. Test: is there a visual event or interaction between these two lines? If not, combine them.

**Confirm Actions with Validation (§4.9d).** When the child completes a key interaction, Guide Bird confirms the action with brief validation + rationale. "You named it 'Fear.' That's exactly the right name, because it's what it really is." Guide Bird doesn't just move on; it validates the choice and explains why it matters. Keep to 1–2 sentences. Not every tap needs verbal confirmation — alternate with silent visual consequences.

**Non-Response Handling.** If the child fails to complete an interaction (timeout), Guide Bird does not explain, analyze, or name what the child did or didn't do. Guide Bird proceeds with the lesson.

- **Wrong:** "That's OK — sending kindness to yourself is the hardest part. It takes practice." (analyzes, diagnoses)
- **Right:** "That's OK — it takes practice. You'll get to try for real in a moment." (normalizes, moves on)

Maximum 2 short sentences for any timeout/skip response. Brevity IS the kindness.

**Child-Natural Language.** All word-bubble text, plank labels, and on-screen prompts must use language a 7-year-old would actually say. Test: read the text aloud and ask "would a second-grader naturally say this on a playground?"

- "I'm sorry I said that" ✔ vs. "I'm sorry I said that mean thing" ✗ (over-specified)
- "It hurt your feelings" ✔ vs. "That probably made you feel sad and left out" ✗ (hedged, compound)
- "I'll try not to do that anymore" ✔ vs. "Next time, I'll ask you first" ✗ (scenario-specific)

Additional principles:
- Keep on-screen text GENERIC, not scenario-specific — planks/bubbles are templates for transferable skills
- Use honest language ("I'll try") over aspirational language ("I will")
- Remove hedging from empathy statements — direct acknowledgment is stronger

**Text + Voice Rule.** All text shown on screen must also be spoken by Guide Bird. Never rely on the child reading screen text to receive instructional content. The app serves ages 7–10; many 7-year-olds are still developing reading fluency. Guide Bird's voice is the primary delivery channel; on-screen text is visual reinforcement. When writing phaseAFlow steps, always specify when Guide Bird SPEAKS text, not just when text is displayed.

### 4.10 Phase A Screen Layout

The Guide Bird occupies the **left third** of the screen as a persistent, emotionally engaging character — large enough to see clearly and connect with even while the interactive element is active.

The **right two-thirds** of the screen is the interactive/visual area where the module's demonstration plays out (breathing silhouette, thought clouds, bell orb, etc.).

**When Guide Bird speaks:** Dialogue appears as text overlay or speech bubble near the bird. The interactive area holds or pauses.

**When interactive element is active:** Guide Bird is quiet. The child's attention is on the right two-thirds.

**Responsive behavior:**
- iPad landscape (primary target): 1/3 + 2/3 side by side
- iPad portrait: Same layout, slightly narrower
- Phone landscape: Same layout
- Phone portrait: Bird becomes floating character overlay in lower-left corner; interactive area goes full-width

**Technical implementation:** CSS Grid with one media query. `grid-template-columns: 1fr 2fr`. Phone portrait breakpoint switches bird to `position: fixed` overlay.

**UI Elements Must Not Obscure Each Other.** Word bubbles, character sprites, labels, and interactive targets must have adequate spacing so that no element overlaps or hides behind another. If characters are too close, bubbles become unreadable. Interactive targets must be fully visible and tappable without obstruction. When designing Phase A layouts, test: "Can a child read every word and tap every target without anything being hidden?"

### 4.11 Phase A Demo Flow (phaseAFlow)

`phaseAFlow[]` is a mandatory field for all modules (not optional).

Every step must have `step` (number), `type` (one of: dialogue, visual, visual-phase, interaction, branch, note), and `description`.

- `dialogue` steps must include `cueRef` linking to the corresponding instruction cue trigger
- `branch` steps must include `condition` describing when they fire
- Both paths of every branch must be documented (tap/no-tap, right/wrong, etc.)

**Instruction cues define WHAT Guide Bird says. phaseAFlow defines EVERYTHING ELSE — what's on screen, what the child does, what happens on each tap, visual transitions, and branching logic. Both are required.**

---


### 4.12 Use All Available Screen Space

Phase A scenes must fill the available viewport width. Visual elements should be sized proportionally to their emotional weight in the metaphor. Small, centered elements floating in whitespace undermine the metaphor's impact.

If worries are supposed to feel overwhelming, they need to fill the screen. If a fear is supposed to feel far away, the scene needs to be wide enough to show distance. If a heart is supposed to feel warm and central, it should dominate the view.

**Test:** Would the visual still feel emotionally correct on a large tablet? Or would it look like a tiny animation in a sea of white?

### 4.13 Visual Elements Appear When They Have Meaning

Never place a visual element on screen before its purpose has been established. If a box appears at the start of the demo but isn't explained until halfway through, the child spends 30 seconds wondering "what's that box?" instead of focusing on the current teaching moment.

Each new visual element should appear at the moment Bird introduces it or the child needs it. The appearance itself becomes a narrative beat.

**Anti-pattern:** Box sits at bottom of screen from Scene 1, ignored until Scene 5.
**Correct:** Box slides in from below when Bird says "Now you can put it somewhere safe."

### 4.14 Silent Animation Beats Need No Dialogue (or Labels)

When an animation clearly communicates what's happening (mass dropping into box, bridge extending, cloud dissolving), Bird should stay quiet. Narrating self-evident animation is redundant and breaks the visual rhythm.

Silent beats (0.5–1.5s) between key moments create dramatic pacing. The animation speaks; then Bird reacts to the result.

**This extends to on-screen labels.** If the visual change is self-evident (wings stop flapping, legs stop bouncing, glow shifts from blue to amber), do not add labels like "wings resting" or "legs resting" on top of the creature. The animation IS the feedback. Bird's dialogue confirms the result after the beat. Redundant labels clutter the creature and undermine the visual's own communicative power.

**Anti-pattern:** Bird says "Watch it go into the box!" while the mass visibly drops into the box.
**Anti-pattern:** "wings resting" label appears on creature whose wings visibly stopped moving.
**Correct:** Mass drops silently into box (0.9s). Box glows. THEN Bird says "See? The box holds onto the Fear so you don't have to carry it around."
**Correct:** Wings stop flapping (visual beat). THEN Bird says "See that? You visited his wings, and they listened."

### 4.15 Labels That Counter-Scale Must Cap or Hide During Extreme Transforms

When a named label (like "FEAR") uses counter-scaling to stay readable as its parent element shrinks, the counter-scale will blow up during absorb/disappear animations (e.g., 1/0.08 = 12.5x). Labels must either hide when their parent enters a flight/absorb state, or cap their counter-scale at a reasonable maximum (3x).

### 4.16 Timeout State Resets Between Interactions

If a Phase A flow has multiple tap interactions (e.g., tap worry, then tap box), the timeout state from the first interaction must not carry into the second. Each interaction starts fresh with its own timeout window and its own tap indicator. Failing to reset causes downstream UI bugs (e.g., pulse ring not appearing on the second target because the first interaction timed out).

### 4.17 Technical: Prefer CSS Animations for Oscillation

When implementing fidget, bounce, flicker, or other oscillating visual effects in demos, prefer CSS `@keyframes` animations over JavaScript animation hooks that compute float values for CSS string concatenation. JS hooks can produce `NaN` or edge-case values during React state transitions, creating invalid CSS (e.g., `rgba(122,200,232,NaN)`). CSS keyframes are computed by the browser's animation engine and cannot produce invalid values.

**Anti-pattern:** `var flickerVal = useFlicker(active, 300);` → `opacity: flickerVal` (may produce NaN during state change)
**Correct:** `@keyframes wingFlap { from { transform: rotate(-30deg); } to { transform: rotate(-10deg); } }` → `animation: wingFlap 0.4s infinite alternate`

When a part transitions from "active" to "rested," set `animation: "none"` with a CSS `transition` property for the smooth settle.

### 4.18 Phase A Settled State Stays on the Creature

After the demo succeeds and before the bridge question, there is a "settled" beat where the author narrates the result. **This narration must stay focused on the creature's visible change — never preview the child's Phase B experience.**

The danger: the demo worked, and the author's instinct is to bridge by describing what the child will do or feel next. But describing the Phase B sequence ("imagine doing that for YOUR whole body… feet, legs, tummy, arms…") IS experiential content — it's a compressed meditation script that leaks backward from Phase B into Phase A.

**The settled state has exactly two jobs:**
1. Observe the creature's result ("Look, his whole body is starting to get the idea")
2. Bridge to action ("Let's practice this right now" / "Ready to try it for real?")

It does NOT preview the child's experience, list body parts they'll scan, describe feelings they'll have, or walk through the Phase B sequence.

**Anti-pattern:** "Imagine doing that for YOUR whole body… feet, legs, tummy, arms, shoulders, face… one at a time, each one softening."
**Problem:** This is the Phase B body scan script delivered verbally in Phase A. The child hears the meditation instructions before Phase B starts.

**Correct:** "Look, his whole body is starting to get the idea… now he's falling asleep! Let's practice this magic sleeping trick right now…"
**Why it works:** Stays on the creature (observational), then bridges to action (motivational). Phase B delivers the actual meditation.

**Cross-reference — the "Phase B Leak" pattern:** This rule and §5.3 (Phase B Transition Is Handoff Only) catch the same underlying error at two different boundaries. The instinct is always the same: "the child needs to know what's coming next, so I'll preview it." But the preview IS the meditation — whether it leaks into the settled state ("imagine doing that for your whole body… feet, legs, tummy…") or into the transition cue ("start with your feet, tell them they can rest now"). Reviewers should check both boundaries as a pair. If Phase B content leaked into one, it likely leaked into the other.

---

## 5. Step 3B — Training: Phase B

### 5.1 Core Rules

- Eyes-closed guided meditation with voiceover
- The child practices the skill for real — this is where the therapeutic work happens
- Audio-guided (ElevenLabs, warm grandparent-like narrator voice)
- Screen shows gentle visual guide for children who peek (breathing circle, body outline)
- Duration: 60–120 seconds of real practice (introductory modules target ~90s; later modules in the same domain may use the full range as child develops practice capacity)
- No module is Phase A only — every module has both phases

### 5.2 Phase B Transition Cue

Each module has a human-authored `phaseBTransitionCue` — a short sentence the Guide Bird speaks before Phase B audio begins.

**Pattern:** "Now close your eyes. [Optional skill-specific physical bridge]. Listen to the voice on the wind..."

**Examples:**
- "Now close your eyes. Keep your hands on your tummy. Listen to the voice on the wind..."
- "Close your eyes. Listen to the voice on the wind."
- "Now close your eyes. Keep breathing with the 4–7–8 rhythm. Let the voice on the wind guide you..."


### 5.3 Phase B Transition Is a Handoff, Never a Start (CRITICAL)

The Phase B transition cue hands the child off to the audio guide. It NEVER begins the meditation itself. No meditation instructions, no therapeutic content, no skill guidance. The cue says some variation of "close your eyes and listen" — nothing more. All therapeutic instruction in Phase B comes from the pre-recorded guided audio.

**Anti-pattern:** "Close your eyes. Picture the worries in your mind. Now imagine naming each one..."
**Anti-pattern:** "Close your eyes. Feel your feet on the floor. Notice where your body touches the chair..."
**Correct:** "Close your eyes. Listen to the voice on the wind."

The transition cue may include a brief skill-specific **physical** bridge if one was established in Phase A: "Close your eyes. Keep your hands on your tummy. Listen to the voice on the wind." But the bridge is a physical cue (hands on tummy, keep breathing the rhythm), never new instruction or guided imagery.

**Why this boundary exists:** The guided meditation audio is a separate deliverable, clinically authored, with precise timing and therapeutic pacing. The transition cue is a structural handoff. If the transition cue contains meditation content, the child receives fragmented, duplicated, or contradictory therapeutic instruction.

**Cross-reference — the "Phase B Leak" pattern (§4.18):** This rule and §4.18 (Phase A Settled State Stays on the Creature) catch the same underlying error at two different boundaries. If Phase B content leaked into the transition cue, check the settled state too — the same instinct ("preview what's coming") likely produced both violations.

### 5.4 Phase B Scripts Validate Phase A Design

Phase B meditation scripts should be written against the locked visual specifications BEFORE building the module player engine. Phase B is where the actual therapeutic experience happens — Phase A is just the tutorial. If a Phase B script reveals that Phase A's metaphor doesn't set up what the meditation needs the child to do, the Phase A demo can be corrected while demos are still editable.

**The meditation script is the validation layer for Phase A's design.** If writing the Phase B script for Module 12 reveals that Phase A's "grabbing" metaphor doesn't translate to eyes-closed guidance — that the meditation naturally wants different language — then Phase A needs adjustment before anything is locked for production.

**Production sequence:** Lock Phase A demos → Write Phase B meditation scripts → Verify Phase A metaphors transfer to eyes-closed guidance → Correct any mismatches → Build engine against validated specs.

**Phase B Practices DURING Emotional Activation, Not After (§5.4a).** For self-compassion and acceptance techniques, Phase B must guide the child's practice WHILE the creature is still emotionally activated — not after the feeling settles. If the creature calms down before the child practices warmth or letting go, the clinical mechanism does not fire. The child must experience applying the technique IN the presence of the difficult feeling. Settling happens BECAUSE of the practice, not before it.

### 5.5 Phase B Voice and Personalization

The Phase B meditation is delivered by a distinct **meditation voice** — not Guide Bird. When the transition cue says "Listen to the voice on the wind," a new presence arrives. This voice is warm, wise, and unhurried (grandparent-like narrator via ElevenLabs).

**Welcome:** Every Phase B script opens with a brief welcome that acknowledges the child's arrival and names the domain magic being practiced. The welcome gives the meditation voice character and makes the child feel personally received.

**Gender personalization:** The welcome uses the child's gender from their profile ("young man" / "young lady"). This personalization is low-cost, high-impact — children feel recognized and special. The app profile setup must include gender selection to support this.

### 5.6 Physical Setup Execution (Described ≠ Executed)

If Phase A's bridge *described* a physical action in future tense ("you're going to put your hand on your belly") but no explicit instruction to *perform* it was given before Phase B begins, the Phase B script must include the instruction. The meditation voice must guide any physical anchor into place, not assume it happened.

**Why this matters:** The bridge describes what will happen. The transition cue says "close your eyes." In that transition, a 7-year-old may not have actually placed their hand. Described ≠ executed. If the child needs a hand on their belly, the meditation voice says "Put your hand right on your belly" before proceeding.

**Rule:** Phase B scripts must audit every physical anchor assumed in the Instruction section and verify that either (a) an explicit instruction to perform it was given in the transition cue, or (b) the Phase B script itself includes the instruction in its Setup section.

---

## 6. Step 4 — The Rescue

### 6.1 Core Pattern

SUSTAIN, not repeat. The child maintains the state they just reached in Phase B while the creature responds. Magic RADIATES outward — the child doesn't aim it.

**Pattern:** "That's great... stay right there..." → transition to sending magic → silent creature response → confirmation.

**IMPORTANT: The rescue sustain is a structural HOLD, not therapeutic content.** The sustain tells the child to maintain whatever state they're in. It does NOT name the state, guide them to feel something specific, or provide any meditation instruction. "That's great... stay right there..." is correct. "Feel that calm... feel your feet on the ground... keep that right there..." is WRONG — it's therapeutic content that belongs in the Phase B audio.

### 6.2 Rules

- The child SUSTAINS, never repeats the exercise
- For movement modules (yoga, PMR): child sustains the settled state AFTER movement, not the movement itself
- Creature is on screen in a receiving state (distressed → settling)
- Visual effect plays (domain-specific: storm_clearing, clouds_dissolving, flowers_blooming, etc.)
- Duration: 20–30 seconds
- **Rescue transition language must vary across modules** — no identical magic-acknowledgment phrasing between modules in the same domain. Vary the magic-feeling language.

- **Rescue visuals must match Phase A training.** The visual magic effect shown during Rescue must use the same visual language the child learned in Phase A. If Phase A showed thought bubbles settling, the Rescue shows thought bubbles settling around the creature — not abstract glow, not generic sparkles. The child should recognize "that's the thing I just learned" when they see the Rescue happen.

### 6.3 Rescue Must Include a Child Action

The Rescue is not passive observation. The child performs a SUSTAIN action while the creature responds.

For mental exercise modules (breathing, visualization, cognitive): "Hold it" — the child sustains the calm/focused state they reached in Phase B.

For physical exercise modules (yoga, PMR, movement): The child sustains the settled state AFTER movement ends — not the movement itself.

The Rescue sequence must include Bird explicitly asking the child to hold/sustain before the creature receives the magic. The child must feel they are actively doing something, not just watching a cutscene.

**Pattern (4 beats):**
1. "That's great... stay right there..." (CHILD SUSTAIN — structural hold, no therapeutic content)
2. "Now we're going to send your [Art] magic out to [creature]..." (TRANSITION)
3. [Silent — creature responds visually, glow builds] (VISUAL BEAT)
4. "Your [Art] magic reached him. Did you feel that?" (CONFIRMATION)

**Beat Consolidation (§6.3a).** Adjacent rescue beats that serve similar purposes may be combined into a single line. "That's great... stay right there... we're sending your Self-Grounding magic to Bork" combines beats 1 and 2 naturally. Don't split into separate timed phases what can be said in one breath. Similarly, the confirmation beat can include the celebration: "Your Self-Grounding magic worked — Bork is fast asleep! YOUR Self-Grounding magic did that!" The 4-beat structure is the logical sequence, not a mandatory 4-phase timer.

### 6.4 Rescue Has No Recap Dialogue

The Rescue never opens with a recap of what the child just learned ("You know the trick now," "Remember what we practiced," etc.). The child JUST finished practicing — they don't need a summary. Jump straight to the sustain action. Every word in the Rescue either directs the child to sustain or celebrates the creature's response.

### 6.5 Problem-Resolution Scope Match

If the Call establishes a multi-part problem ("wings, legs, glow, everything"), the Rescue must visually resolve the FULL scope. Phase A can demonstrate the mechanism on a subset of parts (One Demo Cycle) while explicitly leaving the rest unresolved — that's the teaching moment ("See? His legs are still bouncing. Each part needs its own visit."). But the Rescue must then show ALL parts settling as magic arrives.

The child needs to see the complete payoff. Showing a big problem and only fixing part of it is narratively unsatisfying and therapeutically incomplete — it implies the skill only partially works.

**Anti-pattern:** Call says "wings, legs, glow, everything" → Phase A settles wings → Rescue only settles wings (legs still bouncing during Win)
**Correct:** Call says "wings, legs, glow, everything" → Phase A settles wings + legs (demo of mechanism) → Rescue settles EVERYTHING (full payoff as magic arrives)

---

## 7. Step 5 — The Win

### 7.1 Core Pattern

Guide Bird names the child's specific magic. Rune stone pulses. Coins awarded. Measuring bar circle fills. Decoration may unlock.

**Pattern:** "Your [Art] magic [specific observation]! [Connection to creature or Everdale]."

### 7.2 Rules

- Guide Bird names the SPECIFIC magic — never generic praise ("great job!")
- Win dialogue is realistic — celebrates the outcome without asserting specific behavioral performance the Guide Bird cannot verify
- **Anti-pattern:** "You watched every cloud without chasing a single one!" (Guide Bird can't know this)
- **Correct pattern:** "Luna's thoughts are settling! She can see clearly again. Your Present-Moment Awareness magic did that!"
- Coins: scales up with module level (higher levels award bigger Coins rewards)
- Decoration rewards distributed across ~20–30 of ~54 modules
- **No new concepts in Win.** The Win step celebrates what the child already learned and did. It never introduces a new concept, object, reward, or terminology that wasn't established earlier in the module. If the child hasn't heard about a pendant, the Win doesn't mention a pendant. If the module didn't teach a specific named spell, the Win doesn't name one for the first time.

**Win Language Centers the Child's Magical Power, Not Creature Needs (§7.2a).** The Win celebrates that the child's magic WORKED and REACHED the creature. It does not celebrate that the child was attentive to what the creature needed. Correct: "Your Calm-Breathing magic reached even that." Wrong: "You knew just what Tessa needed." The modules exist to develop the child's magical power identity, not their helper identity. Guide Bird Win lines should name the child's spell and reference the magic landing.

### 7.3 Win Celebrates Magic Transfer, Not Creature Learning

The Win dialogue celebrates that the child's magic REACHED the creature and helped them — not that the creature independently learned the skill. The creature doesn't "name her worries" or "learn to breathe." The creature receives the child's magic and feels better.

**Anti-pattern:** "Benson named his worries! He put them in the box!"
**Correct:** "Wow! Benson got your magic, and he feels so much stronger now!"

This preserves the True Keeper identity: the child is the source of the magic. The creature is the beneficiary, not a parallel learner.

---

## 8. Cross-Module Design Patterns

### 8.1 Clinical Progression Within Domains

Each domain has an introductory module that teaches a foundational awareness skill, and an intermediate module that applies or extends that skill.

**Introductory modules** teach base awareness — a life skill the child can use anytime, anywhere, not just during emotional difficulty. The entry point is universal ("every kid's brain does this"). Frame as discovery and enhancement.

**Intermediate modules** apply the foundational skill to specific situations or teach a more advanced version. The entry point can be more specific ("remember what you learned? Here's the next level"). Frame as upgrade.

| Domain | Introductory Module | What It Teaches | Intermediate Module | What It Teaches |
|--------|-------------------|-----------------|-------------------|-----------------|
| Breath Awareness | Belly Breathing | WHERE to breathe (belly, not chest) | 4-7-8 Calm Down | HOW LONG to breathe (extended exhale) |
| Present-Moment Awareness | Thought Clouds | MENTAL attention (watching thoughts) | Mindful Listening | SENSORY attention (following sounds) |
| Kindness | Warm Heart | GENERATING warmth (self + others) | Friend-Fix Bridge | REPAIRING connections (structured apology) |
| Courage | Brave Steps | THE ANXIETY CURVE (fear rises, peaks, falls) | Worry Box | CONTAINING worry (name it to tame it + externalization) |
| Body Awareness | Sense Anchor | FINDING your body (brain-body reconnection) | Squeeze & Release | RELEASING tension (body holds stress, you can let go) |
| Self-Grounding | Body Scan | SOFTENING the body (noticing without changing) | Guided Imagery | REDIRECTING the mind (safe place visualization) |

### 8.2 Narration Density Principle

Match narration density to conceptual complexity:
- **Most dialogue:** Modules teaching abstract concepts (metacognition, empathy). The concept needs more verbal framing.
- **Least dialogue:** Modules with heavy data points (4-7-8 counts) or clear visual metaphors. The visual does the teaching.

### 8.3 Therapeutic Bright Line

ALL therapeutic content (skill instruction, guided meditation, technique descriptions) is **human-authored** and clinically validated. The Guide Bird's contextual narrative dialogue is AI-generated, cached before sessions, and constrained to **story wrapper only** — never therapeutic content.

| Content Type | Source | Lives In |
|-------------|--------|----------|
| How to breathe, what to visualize, body scan instructions | Human-authored | Module JSON (phaseAConfig, guidedAudioRef) |
| Creature problems, emotional hooks, celebrations | AI-generated | Bar document (aiNarrativeCache) |
| Technique card steps, clinical descriptions | Human-authored | Module JSON (techniqueCard, clinicalDescription) |
| Parent tips, skill summaries | Human-authored | Module JSON (parentTips, parentSkillSummary) |

### 8.4 No Trademarked Technique Names

Never use branded technique names in module content. Use generic clinical shorthand or original game-world names.

- "4-7-8" is generic clinical shorthand (safe)
- "The Relaxing Breath" is Dr. Weil's trademark (never use)
- "RAIN technique" — use the concept, not the acronym as a brand
- Reference the tradition/practitioner in internal documentation; use game-world language in child-facing content

### 8.5 Magic Operationalization Principles

These five rules govern how every module's "magic" is designed. They ensure that each module teaches a producible skill, not an abstract concept.

**Rule 1: Magic Is a Production Skill, Not a Transfer.** Every module teaches the child *how to produce* the therapeutic effect, not merely that the effect exists. "Say kind words on purpose" is a production skill. "Send warmth" is a transfer of something assumed produced. If the Phase A demo can't answer "what exactly does the child DO to make this happen," the lesson is underspecified.

**Rule 2: The Mechanism Must Be Visible.** The specific action that produces the magic must be something a child can see, hear, or feel in the demo. Breathing is visible (belly moves). Kind words are visible (word bubble). Listening is visible (ears, attention, silence). If the mechanism is invisible ("generate warm feelings"), it can't be demonstrated and therefore can't be taught.

**Rule 3: Name the Ingredients, Not Just the Outcome.** The magic's ingredients must be nameable in kid language. "Kind words, said on purpose, to someone specific" has three nameable ingredients. "Warmth" has zero. "Three pieces: what you did, how they feel, what you'll change" has three. If you can't list what goes INTO producing the magic, the module teaches recognition, not skill.

**Rule 4: The Glow Is the Consequence, Not the Lesson.** Brightening, warming, glowing — these are the visible *results* of performing the skill correctly. They are never the skill itself. Phase A shows: action → consequence. The child learns the action. The consequence is confirmation, not curriculum. If the demo can only show glowing without showing what caused it, the demo is incomplete.

**Rule 5: Phase B Practices the Production, Not the Feeling.** The guided meditation should rehearse the *mechanism* taught in Phase A. If Phase A teaches "say kind words on purpose," Phase B guides the child through saying kind words to specific people. If Phase A teaches "notice where your feet are," Phase B guides the child through finding their own feet and hands. The meditation is skill rehearsal, not mood induction.

---


### 8.6 Pronoun Consistency for Creatures

Each creature has established pronouns in the Bible. Authors must verify and use the correct pronouns throughout all module content — Call, Buy-In, Phase A, Rescue, Win.

| Creature | Animal | Pronouns |
|----------|--------|----------|
| Tessa | Turtle | she/her |
| Luna | Owl | she/her |
| Ember | Fox | she/her |
| Benson | Bunny | he/him |
| Bramble | Bear | he/him |
| Bork | Firefly | he/him |

When in doubt, check the Bible's creature section for gendered language patterns.

---

## 9. Enrichment Proposal Requirements

### 9.1 Proposal Structure

Every enrichment proposal must include:

1. **Clinical Foundation** — 1 primary + 2–4 supporting traditions
2. **Therapeutic Insight** — one sentence stating the core insight the module teaches (§0.1)
3. **Universal Entry Point** — what experience every child has had that this module addresses (§0.2)
4. **Discovery vs. Recognition Frame** — which frame applies and why (§0.3)
5. **Call and Buy-In context** — how the Call sets up the need and the Buy-In creates personal connection. Phase A is designed relative to what these already established. Proposing Phase A in isolation risks duplicating content or missing setup framing.
6. **Metaphor Map** (§4.3) — mandatory, before the flow
7. **Phase A Demo Flow** — full step-by-step with branches
8. **What It Teaches / What It Avoids** — explicit lists

### 9.2 Character References in Proposals

Phase A flow descriptions should be character-agnostic where possible, using placeholder slots that the Call/scenario fills in. Distinguish between character-specific dialogue (Call, Rescue, Win — uses creature names) and concept-specific flow (Phase A — teaches a concept bigger than any one character).

### 9.3 No Unicode Escapes in Design Documents

Design documents, preparatory write-ups, enrichment proposals, and module specifications must use plain text characters (apostrophes, em dashes, quotes), not Unicode escape sequences (\u2019, \u2014, \u201c). Escape sequences are JSX implementation details. In design documents they obscure readability and propagate copy-paste errors when dialogue transfers between contexts. Reserve escape sequences for the JSX demo code only.

### 9.4 Design Document Before Demo

Every module begins with a written design document following §0's seven-step process. The design document is reviewed and approved before any demo code is written. The document serves as the baseline truth that both author and reviewer can reference. Corrections to the design document take priority over corrections to the demo — the document is the source of truth, the demo is a rendering of it.

---

## 10. Dialogue Anti-Patterns

These are patterns that have appeared in drafts and must be caught during review.

### 10.1 Call and Buy-In Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| "Luna can't stop her thoughts from racing — she needs someone who can learn to watch thoughts" | Creature's problem is the emphasis; child's training is subordinate | Lead with magic: "Luna's thoughts are racing. This is a great chance to sharpen your Present-Moment Awareness magic." |
| "If you learn belly breathing, you can help Tessa feel safe again" | Frames the creature as the beneficiary during The Call; child should be growing their OWN power | Remove creature-as-beneficiary framing from Call entirely |
| "Tessa's breathing is fast and shallow and she can't settle down" | Sounds like Tessa is the one who will practice breathing | Describe creature's emotional state, not the skill deficit: "Tessa is upset and pacing" |
| "Regular belly breathing isn't enough this time" | Diminishes previous skill; should build on it | "Our belly-breathing magic helped, but not all the way. We need a stronger spell." |
| "Everything is hitting him at once — too loud, too bright, too much" (for body awareness intro) | Assumes crisis/overwhelm — narrows to clinical subset, not universal experience | "His brain is thinking up a storm — he forgot where his body is" (universal busy-brain) |
| "You know when everything feels like too much?" (for discovery skill) | Assumes the child has already noticed the phenomenon | "I'm going to tell you something you might not know yet" (discovery frame) |
| "It thinks about things, it notices things, it worries about things" | Abstract categories — child can't picture any of this | Concrete examples: "It imagines what might happen tomorrow. It remembers your breakfast." |
| "Your body already knows where you are, even when your brain forgets" | Adult mindfulness language disguised as child-friendly — abstract concept a child can't picture | Use concrete examples the child can visualize, not repackaged Kabat-Zinn |
| "When your brain gets too busy, this helps fix it" | Repair framing — implies the brain is broken | Enhancement framing: "This magic helps your brain think AND remember your body" |
| "Bork's trying to settle in, but..." / "You know those times when you lie down but..." | Vague situation — child can't anchor to a specific life moment | Name the context: "trying to settle in and fall asleep" / "those nights when you lie down to sleep" (§3.8) |
| "Bork's brain is still going — thoughts about tomorrow, thoughts about today, round and round" | Call includes experiential description that belongs in Buy-In (§2.1a) | Creature context only: "Bork's body is ready for sleep but his brain is still going" |
| "The trick is: you can give your brain something peaceful to look at" (in Buy-In) | Reveals the HOW/mechanism — Phase A has nothing left to demonstrate (§3.7a) | Promise outcome only: "The magic trick you're going to learn slows the thought-stream down" |

### 10.2 Phase A Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| "after_breath_1 / after_breath_3" triggers | Sequential round cues imply experiential repetition | Use concept-based triggers: "on_demo_begin", "on_tap_belly", "on_complete" |
| "That's the harder magic" / "This is the hardest part" | Assumes the child has a specific emotional difficulty; predicts what they'll find hard | Remove. Normalize AFTER skip if it happens, not before: "That's OK — it takes practice." |
| "When you don't name them, they stay big and scary" | Analyzes the child's experience clinically | Normalize by sharing: "Have you ever worried that worry? I sure have." |
| "Warmth fills the silhouette from the chest outward — slower, quieter, deeper" | Somatic/experiential language in Phase A (describes feeling, not appearance) | Observable language: "The heart grows slightly — gold colors, magic, beautiful." |
| "Drag it into the box. You're not throwing it away — you're putting it somewhere safe so YOU don't have to carry it." | Describes emotional benefit instead of visual consequence | Describe what's on screen: "Put it somewhere safe so it doesn't block your view." |
| Prep frame re-explaining Call context: "I'm going to show you how to build a Sorry Bridge. It takes three pieces." | Repeating Buy-In content in the prep frame; Phase A is training only | Cut to the concept: "A Sorry Bridge is just three little pieces. Watch — then you'll practice for real." |
| Three-sentence bridge summarizing the demo: "Here's the secret: naming a worry is the bravest part..." | Bridge re-teaches what the demo already showed visually | Brief question: "Ready to try it for real?" |
| Phase A opening re-explains concept: "You can send kind words to someone on purpose. Tap to send them to Ember." when Buy-In already taught this | Phase A repeating the Buy-In; child hears same information twice | Cut to action: "Watch this." Then show the tappable bubble. |
| "Watch what happens" / "See that?" as setup language | Passive observation framing — child is a spectator | Active invitation: "Let's help him do some Body Awareness magic. Then you'll try it for real on yourself." |
| Thoughts/feelings vanishing when skill is applied | Implies suppression — skill eliminates the problem | Thoughts settle but remain visible — skill is ADDITION (both/and), not elimination |
| Starting design from clinical technique (5-4-3-2-1) | Produces visualization of technique, not teaching of insight | Start from: "What does the child need to understand?" — technique follows insight |
| On-screen labels ("wings resting", "legs resting") on creature after visual state change | Redundant — the animation IS the feedback; labels clutter the creature | Let the visual change speak; Bird confirms verbally after the beat (§4.14) |
| Single tap for a concept that requires sequence to demonstrate | Under-demonstrates the concept — "one at a time" needs at least two parts | Multiple taps = one demo if they demonstrate sequential steps of one concept (§4.2) |
| "Imagine doing that for YOUR whole body… feet, legs, tummy, arms, shoulders, face…" in settled/bridge state | Phase B meditation script leaked backward into Phase A — previews the child's experience instead of observing the creature's result | Settled state stays on creature: "Look, his whole body is getting the idea… Let's practice this right now" (§4.18) |
| Settled state says "Let's practice this right now…" followed by separate COMPLETE state saying "Ready to try it for real?" | Redundant bridge — two consecutive lines both moving the child toward Phase B | One bridge, then done. Settled observation + bridge in one line, then straight to Phase B (§4.7) |
| Stars dimming abstractly across the sky when child taps (elsewhere on screen) | Abstract consequence with no traceable path from child's action to creature's problem improving (§4.5b) | Consequence must flow visibly: child taps creature → creature stops fighting → stream above creature slows → creature's eyes droop |
| "Bork keeps swatting at his thoughts" | Combat metaphor — implies thoughts are enemies to defeat | Attention metaphor: "Bork keeps grabbing for his thoughts" (engagement that can be released) |
| "Bork's wings and legs are laying calm — we helped him with that stuff before" in Phase A setup | References previous module — adds complexity without teaching value, breaks self-containment (§4.1a) | State is simply visible: "Look at all those bright thoughts moving through Bork" — body already calm on screen |

### 10.3 Phase B and Rescue Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| "Now try to feel calm" | Instruction during Rescue (Step 4) — therapeutic content after Step 3 | Rescue is SUSTAIN only: "That's great... stay right there..." |
| "Feel that calm... keep that right there, that's the magic coming through you" | Therapeutic content in Rescue sustain — names what child should feel | Structural hold: "That's great... stay right there..." (no therapeutic content) |
| "Close your eyes. Feel your feet on the floor. Notice where your body touches the chair..." | Meditation content in Phase B transition — begins the meditation instead of handing off | "Close your eyes. Listen to the voice on the wind." (handoff only) |
| "Close your eyes. Start with your feet. Tell them they can rest now. Listen to the voice on the wind." | Meditation sequence embedded in handoff — "start with your feet, tell them they can rest" IS the body scan | Strip to handoff only: "Close your eyes. Listen to the voice on the wind." (§5.3, §4.18 cross-ref) |
| "You know the trick now — let's see if your magic can reach Bramble" | Rescue opens with recap of what was learned | Jump to sustain: "That's great... stay right there..." |

---

## 11. Clinical Sources Reference

All module authoring draws from these 29 validated clinical traditions. Reference during authoring; never surface to users.

### 11.1 Foundational Mindfulness

| Source | Key Concepts | Domain Relevance |
|--------|-------------|-----------------|
| **Jon Kabat-Zinn** (MBSR) | Breath anchor, sound meditation, thoughts as clouds, non-judgmental awareness | Breath Awareness, Present-Moment Awareness — primary source for breath and attention modules |
| **Eckhart Tolle** (The Power of Now) | Observer activation ("I wonder what my next thought will be?"), silence as presence, one conscious breath | Present-Moment Awareness — the Thought Clouds observer stance; Self-Grounding — silence discovery |
| **Michael Singer** (The Untethered Soul) | Thoughts as objects of awareness ("you are the one who hears them") | Present-Moment Awareness — reinforces observer vs. thinker distinction |
| **Thich Nhat Hanh** | Deep listening, walking meditation, bell of mindfulness, child-accessible language | Present-Moment Awareness — Mindful Listening bell framing; all modules — accessible language model |
| **Pema Chödrön** | Sitting with discomfort, "places that scare you" as growth | Courage — validates discomfort as pathway, not obstacle |
| **Jack Kornfield** | Loving awareness (not detached observation), forgiveness meditation | Kindness — warmth-based rather than clinical-distance approach |
| **Tara Brach** (RAIN) | Recognize, Allow, Investigate, Nurture; radical acceptance | Kindness, Courage — self-compassion framework |

### 11.2 Neuroscience & Clinical Research

| Source | Key Concepts | Domain Relevance |
|--------|-------------|-----------------|
| **Stephen Porges** (Polyvagal Theory) | Ventral vagal activation via diaphragmatic breathing, extended exhale activates parasympathetic | Breath Awareness — PRIMARY for belly breathing and 4-7-8; explains WHY these techniques work physiologically |
| **Bessel van der Kolk** | Stress lives in body, "body needs to learn it is safe" | Body Awareness — PRIMARY for body-anchored awareness; validates body-based approaches |
| **Peter Levine** (Somatic Experiencing) | Pendulation, felt sense, body-based resolution | Body Awareness — squeeze & release rationale; body as teacher |
| **Herbert Benson** (Relaxation Response) | Focused attention + passive disregard = measurable autonomic changes | Present-Moment Awareness — Mindful Listening (bell-to-silence as compressed relaxation response) |
| **Richard Davidson** | Structural brain changes from mindfulness, children show improved attention/regulation | All domains — research validation that this works for children |
| **Daniel Goleman** | Emotional intelligence five components, long-term meditation effects | All domains — overarching framework |
| **Judson Brewer** | Mindful awareness interrupts habit loops, "curiosity over craving" | Present-Moment Awareness, Courage — curiosity as alternative to anxiety-driven attention |
| **Rick Hanson** | "Taking in the good" — savoring 15–30 seconds creates neural changes | ALL MODULES — validates Win step design (celebrate + hold the feeling) |
| **Shauna Shapiro** | Intention, Attention, Attitude (IAA) framework | All domains — organizing framework for what each module emphasizes |
| **Eugene Gendlin** (Focusing) | Body-based emotional location, "felt sense" — attending to the body's implicit knowing | Body Awareness — validates body-as-teacher approach; "felt sense" concept underlies interoceptive awareness modules |
| **Edmund Jacobson** (PMR) | Progressive muscle relaxation — systematic tension/release cycle; historical inventor of the technique | Body Awareness — PRIMARY clinical foundation for Squeeze & Release (M11); tense-then-release as body awareness gateway |

### 11.3 Self-Compassion

| Source | Key Concepts | Domain Relevance |
|--------|-------------|-----------------|
| **Kristin Neff** | Self-kindness, common humanity, mindfulness as three components; reduces anxiety in children | Kindness — Warm Heart module (self-directed kindness component) |
| **Christopher Germer** | "Backdraft" — emotional resistance when first trying self-kindness | Kindness — anticipate difficulty when child turns warmth inward |
| **Sharon Salzberg** | K-2 Directed Metta, expanding circles of compassion (self → friend → neutral → all) | Kindness — PRIMARY for directed loving-kindness progression in Warm Heart module |

### 11.4 Cognitive / Behavioral

| Source | Key Concepts | Domain Relevance |
|--------|-------------|-----------------|
| **Steven Hayes** (ACT) | Cognitive defusion — thoughts as mental events not facts | Present-Moment Awareness — Thought Clouds PRIMARY clinical foundation |
| **Mark Williams, Zindel Segal, John Teasdale** (MBCT) | Mindfulness + CBT cognitive model, "decentering" | Present-Moment Awareness — supports defusion approach with clinical evidence |
| **Adrian Wells** (MCT, ATT) | Selective attention, attention switching, sustained attention | Present-Moment Awareness — Mindful Listening (sustained attention on fading stimulus) |

### 11.5 Child-Specific

| Source | Key Concepts | Domain Relevance |
|--------|-------------|-----------------|
| **Daniel Siegel & Tina Payne Bryson** | "Name it to tame it," upstairs/downstairs brain | All domains — age-appropriate neuroscience metaphors |
| **Susan Kaiser Greenland** (Inner Kids) | New ABCs (Attention, Balance, Compassion), meditation as playful | All domains — play-as-practice philosophy |
| **Amy Saltzman** | Body-anchoring for children, clinically validated pediatric mindfulness | Body Awareness, Breath Awareness — body-based approaches validated for 7–10 age range |
| **Stuart Shanker** (Self-Reg) | Regulation vs. control (regulation not suppression) | All domains — CRITICAL: we teach regulation, never suppression. Thought Clouds is defusion, not thought-stopping. |
| **Goldie Hawn / MindUP** | Evidence-based school curriculum, improved executive function/emotional regulation | All domains — curriculum-level validation |
| **Ross Greene** | "Kids do well if they can" (not "if they want to") | All domains — validates entire non-coercive design philosophy. No guilt, no pressure, no punishment. |
| **Generation Mindful** | Age-appropriate framing ("mindful ears"), body-awareness language | All domains — vocabulary and framing for 7–10 year olds |

### 11.6 Usage Rules

- Module Clinical Foundation sections cite 1 primary + 2–4 supporting traditions
- Phase A interaction design grounded in clinical insight, not just technique mechanics
- Trademarked names never used in child-facing content — reference tradition/practitioner internally only
- Child-specific sources take priority for 7–10 age range applicability
- Rick Hanson validates Win step design across ALL modules (savoring the good for neural encoding)
- Ross Greene validates entire non-coercive approach (no guilt, no shame, no pressure)

---

## 12. QA Checklist

Run this checklist against every module before finalizing.

### Module Design Process (§0)
- [ ] Core insight identified and stated in one child-friendly sentence (§0.1)
- [ ] Therapeutic mechanism validated: clinically supported, age-appropriate, distinct from existing modules, effort-type matches goal (§0.1a)
- [ ] Universal entry point identified — experience every child has had (§0.2)
- [ ] Discovery vs. recognition frame chosen and justified (§0.3)
- [ ] Pedagogical sequence written before any visual design (§0.4)
- [ ] Metaphor matches child's experience, not clinical model (§0.5, §4.3a)
- [ ] Technique follows naturally from insight — not the other way around (§0.7)

### The Call
- [ ] Magic/skill emphasis is primary (sentences 2–3)
- [ ] Creature context is secondary (sentence 1, brief)
- [ ] Child is never told the creature will practice the skill
- [ ] No clinical language
- [ ] 2–3 sentences max
- [ ] Transitional Call pattern used for non-first modules in bar
- [ ] Where possible, upgrade framing for intermediate modules (§2.4)
- [ ] Discovery framing for introductory modules (§2.4)
- [ ] Contains an excitement spiker (§2.5)
- [ ] Spiker language varies from other modules in same domain (§2.5)
- [ ] Call contains only creature context + magic emphasis + spiker — no experiential descriptions (§2.1a)
- [ ] Call emphasizes child's power growth, not abstract problem weakness (§2.6)
- [ ] Creature scenario uses specific relatable thoughts, not abstract states (§2.7b)
- [ ] Creature energy matches skill type: playful for foundational, distress for emotion-focused (§2.7c)
- [ ] Creature problem matches the same phenomenon Phase A teaches (§2.7a)

### The Buy-In
- [ ] Uses correct frame: discovery or recognition (§3.1)
- [ ] Length matches purpose — every sentence serves one of the five jobs (§3.3)
- [ ] Ends with empowerment ("You already have this magic" / "makes you a real master")
- [ ] No therapeutic instruction (bright line)
- [ ] Buy-In promises outcome but does NOT reveal mechanism — HOW is Phase A's job (§3.7a)
- [ ] Skill framed as enhancement, not repair (§3.4c)
- [ ] Existing behavior complimented before new skill introduced (§3.4a)
- [ ] Both/and framing — skill adds, never removes (§3.4b)
- [ ] Containment language uses "softer" not "weaker" (§3.5)
- [ ] Concrete examples, not abstract categories — child can picture each one (§4.9a)
- [ ] Learning goal stated explicitly before demo (§0.6a)
- [ ] Application context named explicitly — child can answer "when would I use this?" (§3.8)

### Training: Phase A
- [ ] Metaphor Map present and complete (§4.3)
- [ ] Every on-screen element maps to a therapeutic concept
- [ ] No elements that don't trace back to the metaphor map
- [ ] Metaphor matches child's experience, not clinical technique (§4.3a)
- [ ] Cue 1 is preparatory frame ("I'm going to show you how this works first")
- [ ] Prep frame is brief — doesn't repeat Call/Buy-In content
- [ ] Phase A dialogue makes NO sense without Buy-In (if it does, it's repeating — §4.1)
- [ ] Setup uses active invitation, not passive observation (§4.7a)
- [ ] Setup explicitly bridges to child's own body/experience (§4.7b)
- [ ] No sequential round cues (no after_breath_1 triggers)
- [ ] One Demo Cycle — one pass through the concept, then done
- [ ] No bonus content after core mechanic is demonstrated
- [ ] Interactions use minimum necessary steps for the skill shape
- [ ] Interaction shape matches skill shape (choice/building/staying/naming/noticing/observing/permitting)
- [ ] If interactive: consequence feedback on every choice
- [ ] Consequences add rather than eliminate when skill is awareness-based (§4.5a)
- [ ] Traceable causal chain: child action → visible change → creature problem improves — all three links on screen (§4.5b)
- [ ] Phase A setup is self-contained — no references to previous modules (§4.1a)
- [ ] Every interaction has a timeout/fallback path
- [ ] Timeout responses are ≤2 sentences, no analysis
- [ ] Timeout dialogue says "Just watch" or observational redirect, not "That's OK" (§4.6)
- [ ] If data-heavy: minimal surrounding language
- [ ] Final cue bridges to Phase B — brief, preferably a question
- [ ] Bridge does not summarize the demo
- [ ] Buy-In emotional framing matches Phase A language (§3.2 Language Consistency Rule)
- [ ] Phase A is INSTRUCTIONAL, not experiential
- [ ] Visual descriptions use observable language (looks like), not somatic (feels like)
- [ ] Guide Bird bridges new visual objects to child's experience ("like the one in your chest")
- [ ] No assumed pathology — Guide Bird never predicts what child will find hard
- [ ] Guide Bird never assumes child's inner state — no "you're thinking/feeling/expecting" (§4.9)
- [ ] Guide Bird normalizes by sharing ("I sure have"), not analyzing
- [ ] All dialogue uses concrete examples, not abstract categories (§4.9a)
- [ ] All on-screen text is also spoken by Guide Bird
- [ ] On-screen text uses child-natural language (would a 7-year-old say this?)
- [ ] On-screen text is generic (template for transferable skill), not scenario-specific
- [ ] phaseAFlow present and complete
- [ ] Every dialogue step has cueRef
- [ ] Every branch has condition + both paths documented
- [ ] Flow matches enrichment proposal (if one exists)
- [ ] Metaphor maps to concrete real-world situation child recognizes (§4.3b)
- [ ] At least one visual element is pre-labeled/readable before child acts (§4.3c)
- [ ] Setup narration and visuals merged where possible (§4.3d)
- [ ] Each interaction has one clear prompt and one target (§4.4b)
- [ ] Avoidance shown honestly — works short-term but removes choice (§4.4d, if applicable)
- [ ] Fear/difficulty elements remain visible, not magically eliminated (§4.4e, if applicable)
- [ ] Scene has enough spatial width for metaphor to read clearly (§4.8c)
- [ ] No specific anxious thoughts on screen — emotion labels only; creature thoughts are ordinary/relatable (§4.8d)
- [ ] Movement and dialogue happen simultaneously when visual IS the lesson (§4.9b)
- [ ] No unnecessary single-sentence dialogue splits (§4.9c)
- [ ] Child avatar is silhouette, never detailed character (§4.8)
- [ ] UI elements do not obscure each other — all text readable, all targets tappable (§4.10)
- [ ] Scene fills available viewport width — no tiny centered elements (§4.12)
- [ ] Visual elements appear only when their purpose is established (§4.13)
- [ ] Self-evident animations play silently — Bird reacts to result, not process; no redundant on-screen labels (§4.14)
- [ ] Counter-scale labels cap at 3x or hide during extreme transforms (§4.15)
- [ ] Timeout state resets between sequential interactions (§4.16)
- [ ] Oscillation animations use CSS @keyframes, not JS-computed CSS values (§4.17)
- [ ] Interactions serve the lesson: taps only where conscious choice IS the concept (§4.4)
- [ ] Multi-step concepts use enough interactions to demonstrate "one at a time" or "step by step" (§4.2)
- [ ] Settled/bridge dialogue stays on creature's result — no preview of child's Phase B experience (§4.18)
- [ ] One bridge to Phase B only — no redundant second bridge in a separate state (§4.7)

### Training: Phase B
- [ ] phaseBTransitionCue is skill-specific
- [ ] Guided audio reference exists (or placeholder noted)
- [ ] Phase B transition cue is handoff only — no meditation content, no guided imagery, no skill instruction (§5.3)
- [ ] If §4.18 was violated (settled state previewed Phase B), also re-check transition cue — same instinct produces both (§5.3 cross-ref)
- [ ] Physical bridge only if established in Phase A (hands on tummy, keep breathing rhythm)
- [ ] Duration 60–120 seconds
- [ ] Script opens with Welcome that names domain magic and uses gender personalization (§5.5)
- [ ] Every physical anchor assumed in Instruction was explicitly guided into place — described ≠ executed (§5.6)
- [ ] Script uses 7-section structure: Welcome → Connection → Setup → Instruction → Deepening → Landing → Exit

### The Rescue
- [ ] SUSTAIN pattern, not repeat
- [ ] Rescue sustain is structural hold only — "stay right there," not "feel that calm" (§6.1)
- [ ] Rescue language varies from other modules in same domain
- [ ] Magic RADIATES — child doesn't aim it
- [ ] No therapeutic instruction after Step 3
- [ ] Rescue includes explicit child SUSTAIN action — "stay right there" or equivalent (§6.3)
- [ ] Rescue opens with sustain, not recap of what was learned (§6.4)
- [ ] Rescue visuals match Phase A training visual language (§6.2)
- [ ] Rescue resolves FULL scope of problem established in Call — not just the parts demonstrated in Phase A (§6.5)
- [ ] Rescue beats consolidated where natural — don't split into separate timed phases what can be said in one breath (§6.3a)

### The Win
- [ ] Guide Bird names specific magic (not generic praise)
- [ ] Win dialogue is realistic (no over-claiming behavioral performance)
- [ ] Coins: scales up with module level (not flat — higher levels award bigger Coins rewards)
- [ ] Full win sequence present: creature settled state → Coins badge → measuring bar fill → decoration unlock
- [ ] Decoration reward noted or null
- [ ] No new concepts, objects, or terminology introduced (§7.2)
- [ ] Win celebrates magic reaching creature, not creature learning independently (§7.3)

### General
- [ ] No trademarked technique names
- [ ] Age 7–10 vocabulary in child-facing text
- [ ] Adult language in parent/therapist text
- [ ] Clinical Foundation cites 1 primary + 2–4 supporting traditions
- [ ] Creature pronouns match Bible (§8.6)
- [ ] moduleId follows {domain}_{snake_case_title} convention
- [ ] estimatedDurationSeconds falls within 180–270 seconds (shorter end for introductory modules, longer for advanced)

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 2026 | Initial compilation from Bible v9b, Phase A Enrichment Proposals (Modules 1–4), Guardrails v2, design session decisions |
| 2.0 | February 2026 | Added 17 rules derived from Kim's edit feedback on Modules 5–8 enrichment proposals. New sections: §4.3 Metaphor Mapping (mandatory pre-work), §4.4 Interaction Design Rules, §4.6 Timeout/Fallback, §4.8 Visual Rules, §4.9 Guide Bird Dialogue Rules, §9 Enrichment Proposal Requirements. Expanded §2.4 Call Framing, §4.7 Instruction Cue Rules (prep frame + bridge brevity), §10 Dialogue Anti-Patterns (7 new entries), §12 QA Checklist (18 new checks). Updated §8.1 Courage domain progression to reflect anxiety curve + worry containment. |
| 2.1 | February 2026 | Added §8.5 Magic Operationalization Principles (5 rules). Added §2.5 Excitement Spiker Rule. Added to §4.1: Phase A Starts Where Buy-In Left Off. Added to §4.4: Interaction Serves the Lesson. Added to §4.6: Timeout Says "Just Watch" (universal). Added to §4.8: Child Is Always a Silhouette. Added to §4.9: Never Assume the Child's Inner State. Added to §4.10: UI Elements Must Not Obscure Each Other. Added to §6.2: Rescue Visuals Match Phase A Training. Added to §7.2: No New Concepts in Win. New anti-pattern: Phase A repeating Buy-In concept. Updated §12 QA Checklist. All derived from Modules 5-7 design sessions. |
| 3.0 | February 2026 | Added 16 rules from Module 7 (Brave Steps) design iterations and Module 5-8 candidate rules from Feb 18 edit analysis session. New: §4.3b Abstract Metaphors Must Map to Concrete Actions, §4.3c Start With Something Visible, §4.3d Merge Setup Narration and Visuals, §4.4b One Clear Prompt Per Interaction, §4.4c Active/Magical Framing, §4.4d Running Away Works (Short-Term), §4.4e Fear Doesn't Disappear, §4.8b Proximity Drives Intensity, §4.8c Scene Must Be Wide Enough, §4.8d No Potentially Activating Content, §4.9b Simultaneous Movement and Dialogue, §4.9c Combine Sequential Dialogues, §4.9d Confirm Actions with Validation. Updated §2.5 Excitement Spiker (vary across modules). Updated §12 QA Checklist (12 new checks). |
| 3.1 | February 22, 2026 | Added 12 rules from Module 8 (Worry Box) design session. New: §2.6 Call Emphasizes Child's Power, §3.4 Containment Language (Softer Not Weaker), §4.12 Use All Available Screen Space, §4.13 Visual Elements Appear When They Have Meaning, §4.14 Silent Animation Beats, §4.15 Counter-Scale Label Caps, §4.16 Timeout State Resets, §5.3 Phase B Transition Is Handoff Only, §6.3 Rescue Must Include Child Action, §6.4 Rescue Has No Recap, §7.3 Win Celebrates Magic Transfer, §8.6 Pronoun Consistency Table. Updated §12 QA Checklist (12 new checks). |
| 4.0 | February 22, 2026 | Major revision from Module 9 (Sense Anchor) design post-mortem. **New section §0: Module Design Process** — 7-step sequence requiring concept-before-technique, universal entry point identification, discovery vs. recognition frame selection, pedagogical sequence before visual design. **New in §2:** §2.4 updated with introductory vs. intermediate carve-out; §2.7 Creature Scenario Design (problem matches Phase A, relatable thoughts, playful energy for foundational skills). **New in §3:** §3.1 expanded with discovery pattern (alongside recognition); §3.3 revised — length driven by purpose, not word count (supersedes 2–3 sentence max); §3.4 Skill Framing Principles (compliment before redirect, both/and framing, enhancement not repair); §3.6 Affectionate Humor. **New in §4:** §4.3a Metaphor Must Match Child's Experience; §4.4 "Noticing" added to interaction shape table; §4.4b exception for same-action multiple targets; §4.5a Consequences Must Be Addition Not Elimination; §4.7a Active Invitation Over Passive Observation; §4.7b Explicit Self-Application Bridge; §4.8d exception for creature thought bubbles (ordinary, not anxious); §4.9a Concrete Examples Not Abstract Categories (with "can the child picture this" test). **Fixed:** §6.1 rescue sustain example corrected — removed therapeutic content, now structural hold only. §8.1 Grounding domain updated from "SENSING the present (5-4-3-2-1)" to "FINDING your body (brain-body reconnection)." **Expanded:** §5.3 with additional anti-pattern example and explanation of why boundary exists. §9.1 enrichment proposal structure expanded (now requires insight, universal entry point, frame selection). §10 anti-patterns reorganized into three tables (Call/Buy-In, Phase A, Phase B/Rescue) with 11 new entries. §12 QA Checklist expanded with 12 new checks for §0 design process, skill framing, creature scenario, active invitation, self-application bridge, consequence type, rescue sustain boundary. **Cleanup:** Removed duplicate QA checklist entries. Fixed document history chronological order. |
| 4.1 | February 22, 2026 | Rules from Module 10 (Squeeze & Release) and Module 11 (Body Softening) design sessions. **New:** §3.8 Name the Application Context (Call/Buy-In must name specific real-world situation where skill applies — "fall asleep" not "settle in"). §4.17 Technical: Prefer CSS Animations for Oscillation (JS hooks can produce NaN CSS values). §4.18 Phase A Settled State Stays on the Creature (settled/bridge narration observes creature result, never previews child's Phase B experience — prevents meditation script leaking backward; cross-referenced with §5.3 as the "Phase B Leak" pattern). §6.5 Problem-Resolution Scope Match (Rescue must resolve full scope of problem established in Call). **Clarified:** §4.2 One Demo Cycle — multiple taps demonstrating sequential steps of one concept is still one demo (two body parts = one body-softening demo). §4.7 Bridge Brevity — added "One Bridge, Then Done" paragraph (settled observation + bridge in one line, no redundant second bridge state). §4.14 extended to cover on-screen labels, not just dialogue — visual change IS the feedback. §5.3 added cross-reference to §4.18 "Phase B Leak" pattern — reviewers check both boundaries as a pair. **New anti-patterns:** Vague application context in Call/Buy-In, redundant on-screen labels on creature, single-tap for sequential concepts, Phase B script leaked into Phase A settled state, redundant double-bridge at end of Phase A, meditation sequence embedded in transition cue handoff. **QA Checklist:** 8 new checks (application context in Call and Buy-In, scope match in Rescue, CSS animation safety, multi-step concept completeness, label redundancy, settled state boundary, single bridge, Phase B Leak cross-check). |
| 4.2 | February 23, 2026 | Rules from Module 12 (Sleepy Stargazing) design session — three mechanism redesigns (guided imagery → cognitive shuffling → acceptance/release). **New in §0:** §0.1a Therapeutic Mechanism Validation Gate — 4-point check (clinically supported, age-appropriate, distinct from existing modules, effort-type matches goal) before proceeding to visual design. Includes distinctiveness test ("Would a 7-year-old say 'I already learned this'?") and efforting-vs-releasing check. **New in §2:** §2.1a Call Excludes Experiential Description (creature context is brief/observable; experiential descriptions belong in Buy-In). **New in §3:** §3.7a Buy-In Outcome vs. Mechanism (may promise outcome but must not reveal HOW — mechanism is Phase A's job). **New in §4:** §4.1a Phase A Setup Is Self-Contained (no references to previous modules; creature state is visible, not narrated). §4.4 "Permitting" interaction shape added to table (tap target is creature, not problem; problem resolves as secondary consequence). §4.5b Traceable Causal Chain (child action → visible change → creature problem improves; all three links on screen). **New in §5:** §5.4 Phase B Scripts Validate Phase A Design (meditation scripts written before engine work; scripts are the validation layer for Phase A metaphors). **New in §6:** §6.3a Rescue Beat Consolidation (adjacent beats serving similar purposes may be combined; 4-beat structure is logical sequence, not mandatory 4-phase timer). **New in §9:** §9.3 No Unicode Escapes in Design Documents. §9.4 Design Document Before Demo. **New anti-patterns (§10.1):** Call with experiential description, Buy-In revealing mechanism. **New anti-patterns (§10.2):** Abstract consequence with no traceable path, combat metaphor for engagement, Phase A referencing previous modules. **QA Checklist:** 7 new checks (mechanism validation, Call experiential exclusion, Buy-In outcome/mechanism, traceable causal chain, Phase A self-containment, rescue consolidation, full win sequence). |
| 4.3 | February 23, 2026 | Rules from Module 1 Phase B script production. **Timing revisions:** estimatedDurationSeconds updated from 240–300s to 180–270s based on child engagement research (attention span data, Headspace benchmarks, gamified app session length studies). Phase B duration updated from 45–90s to 60–120s to accommodate 7-section script template. Research basis: children ages 7–10 have 14–30 minute attention spans for engaging tasks; leaving them wanting more builds return rate; Headspace kids sessions are 3–9 minutes with our gamified wrapper providing superior engagement scaffolding. **New in §5:** §5.5 Phase B Voice and Personalization (meditation voice is distinct from Guide Bird; Welcome opens every script; gender personalization from user profile — "young man" / "young lady"). §5.6 Physical Setup Execution (described ≠ executed — if Phase A bridge described a physical action in future tense, Phase B script must include the instruction; caused by Arrival rule conflating completed vs. described actions). **QA Checklist:** 3 new checks (Welcome with gender personalization, physical anchor execution audit, 7-section structure). |
| 4.5 | March 13, 2026 | **Clinical authoring rules — 5 insertions.** BUILT FROM: v4.4. Source: VIABILITY_THREAD_PENDING_INSERTIONS_TRACKER.md Items 4–8 (March 13, 2026). **§4.1b — Warmth/Kindness Physicalization:** Phase A must ground warmth/kindness in physical sensation, not cognitive instruction. **§4.1c — Phase A in Game World Only:** Phase A narrates the creature; crossing to child's personal experience belongs in Phase B. **§4.1d — Visual Count Scaffolding:** Count-structured techniques must demonstrate the count visually; child cannot count internally while emotionally activated. **§5.4a — Practice During Activation:** For self-compassion/acceptance techniques, Phase B must run WHILE creature is still activated. **§7.2a — Win Language Centers Magical Power:** Win celebrates magic worked and reached creature, not child's attentiveness to creature needs. |
| 4.6 | March 13, 2026 | Bible authority rule updated: "the Bible wins" replaced with "surface the conflict to Kim rather than silently resolving — the Bible is the intended canonical source but may lag behind recent session decisions." Bible version references updated from v11 to v13.1 in active content (header hierarchy + footer). BUILT FROM: v4.5. |
| 4.4 | March 9, 2026 | **Bible v11 alignment pass.** BUILT FROM: CLAUDE_Everdale_World_Design_Bible_v11.md, SKILL_DOMAIN_RESTONE_MAPPING_CHANGE_SPEC_v1_1.md, ARC_1_AUDIT_DECISIONS_MARCH_6_2026.md. **Domain label updates (§8.1, §11, throughout):** Calm → Breath Awareness, Focus → Present-Moment Awareness, Grounding (Bramble's domain) → Body Awareness, Rest (Bork's domain) → Self-Grounding. Context-sensitive: adjective/verb uses of "calm," "focus," "rest," "grounding" preserved. **Art name references:** Art of Calm → Art of Calm-Breathing, Art of Focus → Art of Now-Watching, Art of Grounding → Art of Body-Sensing, Art of Rest → Art of Self-Grounding (no instances existed in v4.3; documented for future reference). **Creature renames (§8.6, throughout):** Shelly → Tessa (9 instances), Clover → Benson (4 instances, pronouns she/her → he/him), Flicker → Bork (10 instances, pronouns unchanged he/him). **Module count:** 60 → ~54 modules. **Arc count:** 9 arcs (MVP = 4). **Clinical sources (§11):** Added Salzberg (Kindness — Directed Metta), Gendlin (Body Awareness — Focusing/felt sense), Jacobson (Body Awareness — PMR). Source count 26 → 29. **Footer:** Bible reference updated v9b → v11. |

---

*This document is a compilation reference. When it conflicts with the Bible v13.1, surface the conflict to Kim rather than silently resolving — the Bible is the intended canonical source but may lag behind recent session decisions.*

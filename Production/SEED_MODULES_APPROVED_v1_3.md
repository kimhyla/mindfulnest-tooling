# Seed Modules — Approved & Locked

## MindfulNest / Everdale — Frozen Module Content Reference

### Version 1.2 • Updated March 9, 2026

---

## Purpose

This document is the **canonical frozen reference** for approved seed module content. It records the exact instruction cues, Phase A demo flows, example dialogue, and clinical metadata for each approved module.

**Authority:** If the previewer JSX and this document ever disagree, **this document wins.**

**Lock rule:** Do not modify any content in this document without explicit approval from Kim. Any Claude session that encounters a request to change locked module content must flag the lock and ask for confirmation before proceeding.

**Scope:** This document covers Modules 1–2 (approved, active Arc 1 assignments) plus two reassigned/orphaned modules preserved in Appendix A and B. Modules 5–12 remain in draft status in the previewer and are NOT covered by this lock.

---

## Document Hierarchy

1. **The Bible** — wins all narrative/design conflicts
2. **This document (SEED_MODULES_APPROVED)** — wins all module content conflicts for approved modules
3. **Module Authoring Guide v2** — structural rules for all modules
4. **MODULE_JSON_SCHEMA v1.0** — frozen data format
5. **CANONICAL_DATA_MODEL v1.1** — frozen Firestore schema
6. **Previewer JSX v5** — living implementation (must match this doc for approved modules)

---

## Required Fields for All Modules

Every module — approved or draft — MUST include:

- `instructionCues[]` — Guide Bird dialogue triggers
- `phaseAFlow[]` — Full screen choreography (visuals, interactions, branches, consequences)
- `exampleCall` — The Call dialogue (magic emphasis first, creature second)
- `exampleBuyIn` — The Buy-In dialogue
- `exampleRescue` — The Rescue dialogue
- `exampleWin` — The Win dialogue
- `phaseBTransitionCue` — Phase A → B transition
- `clinicalLabel` + `clinicalDescription` — Therapist-facing metadata
- `parentSkillSummary` + `parentTips[]` — Parent-facing content
- `techniqueCard` — Take-home skill card

`phaseAFlow` step types: `dialogue`, `visual`, `visual-phase`, `interaction`, `branch`, `note`

Every `branch` step must include a `condition` field describing when it fires.
Every `dialogue` step should include a `cueRef` linking to the corresponding instruction cue trigger.

---

# MODULE 1: Belly Breathing (Art of Calm-Breathing — Introductory)

## Metadata

| Field | Value |
|-------|-------|
| moduleId | `breathing_belly_breathing` |
| domain | breathing |
| creature | Tessa (turtle) |
| difficulty | introductory |
| isFirstModule | true |
| duration | ~265 seconds |
| phaseAPattern | breath_placement |
| decorationReward | shell_lantern_blue |

## Sample Scenario

Tessa is overwhelmed by a sudden noise or commotion. Her shell starts to shake and she needs to calm down. The child learns WHERE the breath goes — and why that changes everything.

## Instruction Cues

| Trigger | Text |
|---------|------|
| `on_start` | "Most of the time, when you breathe in, you breathe only halfway down, to the middle of your chest. But if you want, you can breathe in deeper. You can breathe ALL THE WAY DOWN to your belly." |
| `on_belly_magic` | "Bellies have a special kind of magic, you know. When you're upset about anything, you can breathe all the way down and touch the magic; and you'll start to feel calmer right away. For real. It's true." |
| `on_chest_demo` | "Watch what happens when you're upset and only breathe into your chest — see? You stay upset." |
| `on_choice` | "If you want to feel calmer, where should you breathe into? Tap the chest or the belly." |
| `on_tap_chest` | "That's OK, but if you want to feel calmer, try the belly." |
| `on_retry` | "What happens if you breathe into your belly instead?" |
| `on_tap_belly` | "See that? When the breath goes all the way down to your belly, the magic starts working. You start to feel calmer." |
| `on_complete` | "When it's time to start, you're going to put your hand right on your belly so you can feel the air moving in. Let's try it for real." |

## Phase A Demo Flow

| Step | Type | Description | CueRef |
|------|------|-------------|--------|
| 1 | 🗣️ dialogue | Guide Bird explains that most breathing goes only halfway down, to the chest — but you CAN breathe deeper, all the way to the belly. | on_start |
| 2 | 🎨 visual | Screen shows child's silhouette with two glowing zones: CHEST (upper, small, blueish) and BELLY (lower, larger, warm gold). A dashed arrow shows "halfway" to chest. Silhouette breathes fast, shallow — chest zone pulses. | |
| 3 | 🗣️ dialogue | Guide Bird reveals belly magic — breathe all the way down to touch it and you feel calmer. "For real. It's true." | on_belly_magic |
| 4 | 🎨 visual | Belly zone glows warmer. A dashed arrow extends from mouth all the way down to belly with label "all the way!" — visually showing the deeper path. | |
| 5 | 🗣️ dialogue | Guide Bird shows the chest-only consequence. | on_chest_demo |
| 6 | 🎨 visual | Environment shifts to tense: storm clouds, muted colors, slight shake. Chest breathing continues — child SEES that staying in the chest means staying upset. | |
| 7 | 🎨 visual | A glowing breath-orb appears at the silhouette's mouth. It drifts downward and hovers between the chest and belly zones. | |
| 8 | 👆 interaction | Two soft tap-targets appear — the chest zone and the belly zone. Guide Bird asks: "If you want to feel calmer, where should you breathe into?" | on_choice |
| 9 | 🔀 branch | **IF: Child taps CHEST** — Breath-orb goes to chest. Nothing changes — still tense. Guide Bird: "That's OK, but if you want to feel calmer, try the belly." | on_tap_chest |
| 10 | 🎨 visual | Orb reappears at mouth and drifts down again. Belly-only tap target appears. | on_retry |
| 11 | 🔀 branch | **IF: Child taps BELLY** — Breath-orb sinks into belly zone. Belly glows bright gold. Breathing slows dramatically. Environment transforms: storm clears, colors warm, sparkles appear. | on_tap_belly |
| 12 | 🗣️ dialogue | Guide Bird bridges to Phase B. Consistent "belly" terminology (not "tummy"). | on_complete |
| 13 | 📝 note | SKIP PATH: If child taps belly first (skipping chest), on_tap_chest and on_retry are skipped — child still gets the belly consequence + bridge. TIMEOUT: If child doesn't tap within ~8s, Guide Bird gently prompts and orb pulses toward belly. | |

## Phase B Transition Cue

"Now close your eyes. Keep your hand on your belly. Listen to the voice on the wind..."

## Example Dialogue

**The Call:** "Tessa is shaking in her shell — there was a loud crash near the beach. This is the perfect chance to learn your first Calm-Breathing spell. Belly breathing is where all Calm-Breathing magic begins."

**The Buy-In:** "Ever gotten upset about something that happened at home or at school, and had a hard time calming back down? Belly breathing is how you calm yourself down. You already have this magic inside you."

**The Rescue:** "OK now feel that calm... keep that right there, that's the magic coming through you... hold it... now we're going to send your Calm-Breathing magic out to Tessa..."

**The Win:** "Tessa stopped shaking! Her shell is still and warm again. Your Calm-Breathing magic is growing — that was your very first spell!"

## Clinical Content

**Label:** Diaphragmatic Breathing — Chest vs. Belly Contrast

**Description:** Visual teaching of the chest-vs-belly breathing contrast through choice mechanic. Polyvagal Theory (Porges): diaphragmatic breathing stimulates the ventral vagal complex, shifting from sympathetic activation to parasympathetic regulation. The child learns the CONCEPT (where the breath goes changes the body's state) through interactive visual consequence, then practices in Phase B.

## Parent Content

**Skill Summary:** Your child is learning that WHERE they breathe changes how their body feels — belly breathing activates their built-in calm-down system.

**Tips:**
1. Practice belly breathing together at bedtime — put a stuffed animal on your child's tummy and watch it rise and fall.
2. When your child seems anxious, try: "Where is your breath right now? Is it up in your chest or down in your belly?"
3. Model it yourself — when you feel stressed, say out loud: "My breath is up in my chest. I'm going to send it down to my belly."

## Technique Card

**Name:** Belly Breathing
**Summary:** Sending your breath deep into your belly instead of keeping it in your chest — your body's built-in calm-down switch.
**Steps:**
1. Notice where your breath is right now — is it fast and high in your chest?
2. Place both hands on your belly, just below your ribs.
3. Breathe in slowly through your nose — send the air DOWN into your belly.
4. Feel your belly push your hands out as it fills up.
5. Breathe out slowly through your mouth and feel your belly sink back down.

---

# MODULE 2: Thought Clouds (Art of Now-Watching — Introductory)

## Metadata

| Field | Value |
|-------|-------|
| moduleId | `watching_thought_clouds` |
| domain | watching |
| creature | Luna (owl) |
| difficulty | introductory |
| isFirstModule | true |
| duration | ~270 seconds |
| phaseAPattern | `thought_clouds` |
| decorationReward | (none) |
| clinicalLabel | Cognitive Defusion with Selective Attention |
| rescueVisualEffect | `clouds_dissolving` |

## Sample Scenario

Luna's thoughts are racing. Worry-thoughts are swirling and she can't settle. The child helps by learning that thoughts are like clouds — they go away by themselves, unless you send them your magical power. The child practices choosing which thoughts get their attention.

## Instruction Cues

| Trigger | Text |
|---------|------|
| `on_start` | "I'm going to show you how this works. Watch what happens on screen — then you'll try it for real with your eyes closed." |
| `on_tolle_activation` | "When you close your eyes, you're going to sit very still and ask yourself: 'I wonder what my next thought will be?'" |
| `on_example_a` | "Maybe your next thought might be... 'Am I doing it right?'" (Cloud w1a enters as Bird speaks) |
| `on_example_b` | "Or... 'I need a drink of water!'" (Cloud w1b enters as Bird speaks) |
| `on_tap_prompt` | "Tap one of the thoughts to send it your attention magic!" |
| `on_tap_nudge` | "Go ahead — tap one!" |
| `on_w1_tapped` | "Look what happened! You gave the thought your attention, and it got big!" (Tapped cloud grows + swirls, then both drift off-screen.) |
| `on_choice_clouds` | "Now pick which thought gets your magic!" |
| `on_choice_nudge` | "Tap the one you want to give your magical power to!" |
| `on_positive_consequence` | (No Bird dialogue — positive visual consequence. Cloud grows + swirls with happy particles, environment shifts to positive blue, ~2 seconds. Both clouds drift off.) |
| `on_negative_consequence` | (No Bird dialogue — negative visual consequence. Cloud grows + swirls with red particles, environment shifts to reddish, ~2 seconds. Both clouds drift off.) |
| `on_shaping_msg` | "Look what happened! Your attention magic made that unhappy thought so big. Try giving your attention magic to the happy thought instead." (New positive cloud scrolls in behind.) |
| `on_shaping_tap` | (Positive consequence plays → bridge.) |
| `on_shaping_timeout` | "No problem. Ready to try it for real?" |
| `on_w2_timeout` | "That's OK, let's try it for real with your eyes closed." (Both clouds drift off naturally.) |
| `on_complete` | "That's how you control the magical attention power in your mind. You choose which thoughts get your magic. Let's try it for real with eyes closed." |

## Phase A Demo Flow

| Step | Type | Description | CueRef |
|------|------|-------------|--------|
| 1 | 🗣️ dialogue | Guide Bird delivers prep frame. | on_start |
| 2 | 🗣️ dialogue | Guide Bird delivers Tolle observer activation: "I wonder what my next thought will be?" | on_tolle_activation |
| 3a | 🗣️🎨 synced | Bird says "Maybe your next thought might be... 'Am I doing it right?'" — Cloud w1a enters as Bird speaks those words. | on_example_a |
| 3b | 🗣️🎨 synced | Bird says "Or... 'I need a drink of water!'" — Cloud w1b enters as Bird speaks. Cloud w1a already visible. | on_example_b |
| 4 | 👆 interaction | Both clouds tappable with pulsing glow + "tap!" hint. Bird: "Tap one of the thoughts to send it your attention magic!" | on_tap_prompt |
| 5a | 🔀 branch | **IF: No tap after 5s** — Bird nudges: "Go ahead — tap one!" Wait 5 more seconds. | on_tap_nudge |
| 5b | 🔀 branch | **IF: Still no tap** — Both clouds drift off-screen naturally to the left. Proceed to Wave 2. | |
| 6 | 🔀 branch | **IF: Child taps either cloud** — Tapped cloud grows 1.6x + swirls with particles. Bird: "Look what happened! You gave the thought your attention, and it got big!" Both clouds drift off. Clear sky moment. Proceed to Wave 2. | on_w1_tapped |
| 7 | 🎨 visual | **WAVE 2 begins.** Two clouds enter: blue "I'm awesome!" (positive) and red "I'm mad." (negative). | |
| 8 | 👆 interaction | Bird: "Now pick which thought gets your magic!" Clouds tappable with glow + hints. | on_choice_clouds |
| 9a | 🔀 branch | **IF: Child taps positive** — Cloud grows + swirls with happy blue particles, environment shifts to positive blue. Both drift off. Proceed to bridge. | on_positive_consequence |
| 9b | 🔀 branch | **IF: Child taps negative** — Cloud grows + swirls with red particles, environment shifts reddish. Both drift off. Proceed to shaping (step 10). | on_negative_consequence |
| 9c | 🔀 branch | **IF: No tap after nudge** — Both clouds drift off naturally. Bird: "That's OK, let's try it for real with your eyes closed." Proceed to bridge. | on_w2_timeout |
| 10 | 🗣️🎨 shaping | Bird: "Look what happened! Your attention magic made that unhappy thought so big. Try giving your attention magic to the happy thought instead." New positive cloud ("I'm good at this!") scrolls in. | on_shaping_msg |
| 11a | 🔀 branch | **IF: Child taps positive cloud** — Positive consequence plays → bridge. | on_shaping_tap |
| 11b | 🔀 branch | **IF: Timeout** — Cloud drifts off. Bird: "No problem. Ready to try it for real?" → bridge. | on_shaping_timeout |
| 12 | 🗣️ dialogue | Bridge: "That's how you control the magical attention power in your mind. You choose which thoughts get your magic. Let's try it for real with eyes closed." | on_complete |

## Phase B Transition Cue

"Now close your eyes. Listen to the voice on the wind..."

## Example Dialogue

**The Call:** "I'm going to teach you how to control the magical power in your mind. Then you can use it to help Luna — her thoughts are racing and she can't slow them down."

**The Buy-In:** (Delivered in short paragraphs for digestion)

"You know when your brain gets stuck on a worry and keeps playing it over and over?"

"Thoughts are like clouds. They float in, and then they float away by themselves. That is — unless you send them your magical power. You send your magic by paying lots of attention to a thought and believing in it."

"When a thought gets your magic, it goes around in circles and gets bigger and bigger instead of floating away."

"So we're going to practice choosing which thoughts get your magic... and which ones don't."

**The Rescue:** "Feel that stillness... just let the thoughts float by... that's the magic coming through you... Now send your Now-Watching magic out to Luna..."

**The Win:** "Luna's thoughts have settled! She can see clearly again. Your Now-Watching magic did that!"

## Clinical Content

**Label:** Cognitive Defusion with Selective Attention

**Description:** ACT cognitive defusion combined with selective attention training. The "magical power" metaphor teaches that attention is a resource the child can direct — thoughts only grow when fed with attention (Hayes, ACT). Tolle's observer activation ("I wonder what my next thought will be?") creates the gap between thinker and thought. The choice-pair mechanic (positive vs. negative cloud) with consequence feedback teaches that choosing which thoughts get attention changes felt experience. Behavioral shaping after negative choice gently redirects without punishment. MBCT decentering: seeing thoughts as passing events rather than reality.

## Parent Content

**Skill Summary:** Your child is learning to choose which thoughts get their attention — and to notice that choosing good-feeling thoughts feels better than feeding the worries.

**Tips:**
1. When your child seems stuck in worry, try asking: "Which thought is getting your magic right now? Is that the one you want to feed?"
2. Practice together: name a worry-thought cloud and a good-feeling cloud. Which one do you want to give your attention to?
3. If your child says "I can't stop thinking about it," try: "That thought is getting all your magic. What if you gave your magic to a different thought instead?"

## Technique Card

**Name:** Thought Clouds
**Summary:** Choosing which thoughts get your magical power (attention) — good-feeling thoughts grow bright, worry thoughts fade when you stop feeding them.
**Steps:**
1. Sit still and ask yourself: "I wonder what my next thought will be?"
2. Watch the thought appear — like a cloud drifting in.
3. Choose: do you want to give this thought your magic?
4. If it's a good-feeling thought, give it your attention and watch it grow bright.
5. If it's a worry, let it drift past — don't send it your power.

---

# APPENDIX A: 4-7-8 Calm Down (Art of Calm-Breathing — Intermediate)

> **⚠️ UNASSIGNED (March 17, 2026).** This module was previously reassigned to Arc 2 M7 (March 8, 2026). As of March 17, 2026, Arc 2 M7 has been redesigned with a new technique (Big-Little Spell / F-2 Attention Shifting / Luna). The 4-7-8 Breathe Spell returns to unassigned/available status. The module's content is therapeutically valid and locked. The creature (Tessa), domain (Breath Awareness), and all therapeutic content remain unchanged. Available for future arc assignment.


## Metadata

| Field | Value |
|-------|-------|
| moduleId | `breathing_478_calm_down` |
| domain | breathing |
| creature | Tessa (turtle) |
| difficulty | intermediate |
| isFirstModule | false |
| duration | ~280 seconds |
| phaseAPattern | breathing_circle_478 |
| decorationReward | wind_chime_silver |

## Sample Scenario

Tessa is so nervous she can't stop pacing. Her breath is fast and shallow. She needs a more powerful calming technique — the extended exhale.

## Instruction Cues

| Trigger | Text |
|---------|------|
| `on_start` | "This is a really powerful Calm-Breathing spell. I'm going to show you how it works first, and then you'll try it for real with your eyes closed." |
| `on_demo_begin` | "4 seconds in. 7 seconds hold. 8 seconds out. 4, 7, 8. Like this." |
| `on_complete` | "Got it? 4-7-8. The 8 is when the magic comes through. Now you're going to try it for real." |

## Phase A Demo Flow

| Step | Type | Description | CueRef |
|------|------|-------------|--------|
| 1 | 🗣️ dialogue | Guide Bird delivers prep frame. | on_start |
| 2 | 🗣️ dialogue | Guide Bird delivers the data — minimal language. Just the numbers and the pattern. | on_demo_begin |
| 3 | 🎨 visual | The breathing circle auto-animates through ONE complete 4-7-8 cycle. No child interaction — pure watch-and-learn. The circle has THREE DISTINCT VISUAL PHASES: | |
| 4 | 🎬 visual-phase | **INHALE (4 counts):** Circle expands. Soft blue glow gathers inward, like drawing energy in. Quiet, gentle. Small numbers count visibly on screen: 1… 2… 3… 4. Numbers are visible but NOT narrated (minimal language when data is heavy). | |
| 5 | 🎬 visual-phase | **HOLD (7 counts):** Circle holds steady. The blue glow intensifies, concentrates, builds. A quiet hum or shimmer — energy being stored. The anticipation is visual. Numbers count on screen: 1… 2… 3… 4… 5… 6… 7. | |
| 6 | 🎬 visual-phase | **EXHALE (8 counts):** Circle contracts slowly. The stored energy RELEASES as a warm golden wave that radiates outward across the entire screen. This is THE SPECTACLE — sparkles, warmth, the environment brightening. The exhale is unmistakably the most visually powerful phase. Numbers count: 1… 2… 3… 4… 5… 6… 7… 8. | |
| 7 | 📝 note | The visual hierarchy (subtle inhale → building hold → spectacular exhale) teaches the polyvagal insight without words: the exhale is where the magic happens. The child SEES it. | |
| 8 | 🗣️ dialogue | Guide Bird bridges to Phase B. The "8" callback reinforces the therapeutic insight. | on_complete |
| 9 | 📝 note | DESIGN NOTE: This module has NO interactive component in Phase A. The One Demo Cycle rule takes priority. It is more important to teach the core insight clearly and concisely in less time than to include an interactive component just for the sake of it. | |

**IMPORTANT:** Demo animations run at compressed instructional speed — the circle animates over ~9 total seconds (3s inhale + 2s hold + 4s exhale) with the correct numbers (4, 7, 8) displaying as digits on screen. This is an INSTRUCTIONAL demo, not an EXPERIENCE. The child sees the concept at a pace appropriate for instruction.

## Phase B Transition Cue

"Now close your eyes. Keep breathing with the 4-7-8 rhythm. Let the voice on the wind guide you..."

## Example Dialogue

**The Call:** "Tessa is upset and pacing back and forth. Our belly-breathing magic helped, but not all the way. We need a stronger spell — the 4-7-8. This is advanced Calm-Breathing magic."

**The Buy-In:** "Sometimes, when you're super upset — like really, really upset — you might need a magic even stronger than belly breathing. The 4-7-8 spell is for those times. The secret is the long breathe out — it tells your body 'you're safe' in a way nothing else can."

**The Rescue:** "OK now feel that calm... that long, slow breath out... keep that right there, that's the magic coming through you... hold it... now we're going to send your Calm-Breathing magic out to Tessa..."

**The Win:** "Tessa's breathing slowed down! She's stopped pacing and her shell is steady. Your 4-7-8 Calm-Breathing magic is powerful — that's advanced stuff!"

## Clinical Content

**Label:** 4-7-8 Extended Exhalation Breathing

**Description:** Extended exhalation breathing (Polyvagal Theory, Porges). The exhale activates the parasympathetic nervous system via vagal tone — when the exhale is longer than the inhale, the body receives a stronger "safe" signal. The hold creates a CO2 pause that paradoxically promotes relaxation. Visual hierarchy (subtle inhale → building hold → spectacular exhale) teaches the polyvagal insight without words.

## Parent Content

**Skill Summary:** Your child is learning a powerful calming technique — breathing in for 4, holding for 7, and breathing out for 8. The long breath out is where the calming magic happens.

**Tips:**
1. Practice 4-7-8 breathing together before stressful moments — the counting gives anxious minds something to focus on.
2. If the hold feels too long for your child, start with 3-5-6 and work up gradually.
3. Remind your child: "The long breath out is the magic part" — emphasize the exhale, not the inhale.

## Technique Card

**Name:** 4-7-8 Breathing
**Summary:** A structured breathing pattern where the long exhale tells your body it's safe. The exhale is where the magic happens.
**Steps:**
1. Breathe in through your nose for 4 counts.
2. Hold your breath gently for 7 counts — feel the energy build.
3. Breathe out slowly through your mouth for 8 counts — this is the magic part.
4. Feel the calm spread out from the long breath out.
5. Repeat 3–4 times.

---

# APPENDIX B: Mindful Listening (Art of Now-Watching — Intermediate)

> **⚠️ ORPHANED FROM ARC 1.** This module's content is therapeutically valid and locked. It was originally Arc 1 M4 but has been displaced by the March 8, 2026 renumbering (M4 is now Warm Heart / Ember / Kindness per the Bible). The technique (Mindful Listening / Sustained Auditory Attention) remains in the production pipeline for future assignment. Creature (Luna) and domain (watching) are unchanged.


## Metadata

| Field | Value |
|-------|-------|
| moduleId | `watching_mindful_listening` |
| domain | watching |
| creature | Luna (owl) |
| difficulty | intermediate |
| isFirstModule | false |
| duration | ~260 seconds |
| phaseAPattern | listening_bell |
| decorationReward | (none) |

## Sample Scenario

Luna heard a strange sound in the forest and now she can't concentrate — every little noise makes her jump. She needs to learn to follow sounds calmly all the way to silence, instead of reacting to every noise.

## Instruction Cues

| Trigger | Text |
|---------|------|
| `on_start` | "I'm going to show you how this listening spell works first, and then you'll try it for real with your eyes closed. The magic comes through when you listen to a sound, all the way, through until it disappears all the way. Then you listen to the silence. Let me show you what I mean. Here's a bell making a sound. When the sound disappears all the way, tap the bell." |
| `on_bell_fading` | "Follow the sound all the way into silence…" |
| `on_tap_too_early` | "Almost… not quite. It's still singing. Keep listening." |
| `on_silence_found` | "Did you feel that? That quiet place at the end? That's when your magic comes through." |
| `on_complete` | "Now let's practice this spell for real." |

## Phase A Demo Flow

| Step | Type | Description | CueRef |
|------|------|-------------|--------|
| 1 | 🗣️ dialogue | Guide Bird delivers the full opening: prep frame + concept explanation ("the magic comes through when you listen to a sound all the way through until it disappears") + instruction ("when the sound disappears all the way, tap the bell"). This is one continuous speech — intentionally long because it front-loads the therapeutic concept before the bell plays. | on_start |
| 2 | 🎨 visual | A round singing bowl bell plays — a warm, resonant tone. On screen, a soft glowing orb appears at the center, pulsing gently outward in 360 degrees, mimicking the movement of sound waves. | |
| 3 | 🎨 visual | Visible "sound rings" ripple outward from the orb, like ripples on water. The rings are bright and closely spaced at first. | |
| 4 | 🎬 visual-phase | As the bell decays, the rings slow down, spread apart, and grow fainter. The orb's glow dims gradually. The screen itself subtly shifts — colors cooling, details softening — as if the whole world is quieting with the sound. | |
| 5 | 🗣️ dialogue | Guide Bird prompts mid-demo, while bell is fading. | on_bell_fading |
| 6 | 🎨 visual | The bell continues to fade. The rings become barely visible. The orb is now a faint shimmer. A soft tap-target appears around the orb — it's clear the child should tap, but WHEN is the question. | |
| 7 | 🔀 branch | **IF: Child taps TOO EARLY (sound still faintly audible)** — The orb gently pulses back brighter for a moment — the sound is still there. One more faint ring ripples out. The sound continues its natural decay. The tap-target stays available. | on_tap_too_early |
| 8 | 🔀 branch | **IF: Child taps at the RIGHT MOMENT (true silence)** — The orb doesn't pulse back. Instead, it dissolves into the screen — and the entire screen blooms with a soft, warm golden glow. No sound at all. Just light. A moment of absolute stillness. 2–3 seconds of beautiful nothing. This is Tolle's "awareness of the gap" made visible. | |
| 9 | 🗣️ dialogue | Guide Bird speaks AFTER the silence holds for 2–3 seconds. The delay is intentional — the silence IS the experience. | on_silence_found |
| 10 | 🗣️ dialogue | Guide Bird bridges to Phase B. | on_complete |
| 11 | 📝 note | ONE bell ring only. The single fading tone IS the complete demo. Error path: if child doesn't tap bell within the full decay window, the golden silence bloom happens automatically, and Guide Bird proceeds to on_silence_found. The silence moment is the therapeutic peak — don't rush past it. | |

## Phase B Transition Cue

"Now close your eyes. Just listen. The voice on the wind will guide you..."

## Example Dialogue

**The Call:** "Luna keeps jumping at every sound in the forest. This is the perfect time to sharpen your Now-Watching magic — you're going to learn to follow sounds all the way to silence."

**The Buy-In:** "Have you ever been so jumpy that every little noise made your heart beat fast? Like you couldn't tell if a sound was something to worry about or not? Mindful listening is how you train your ears to really hear what's there — instead of reacting to everything."

**The Rescue:** "OK now feel that quiet focus... keep that right there, that's the magic coming through you... hold it... stay in that listening place... now we're going to send your Now-Watching magic out to Luna..."

**The Win:** "Luna isn't jumping anymore! She can listen to the forest calmly now. Your Now-Watching magic — those incredible ears of yours — did that!"

## Clinical Content

**Label:** Mindful Listening / Sustained Auditory Attention

**Description:** MBSR-derived sound meditation (Kabat-Zinn) with consequence feedback. Sustained attention on a decaying stimulus — the fading bell gets harder to attend to as it decays, requiring increasing concentration (Wells, ATT). The "too early" feedback teaches that patience IS the skill, not an obstacle to the skill. The golden silence moment is Tolle's "awareness of the gap" made visible — the child doesn't just notice silence, they experience it as something warm and safe. Bell-to-silence arc produces parasympathetic activation (Benson). Thich Nhat Hanh's "bell of mindfulness" framing — the bell is an invitation, not a test.

## Parent Content

**Skill Summary:** Your child is learning to follow sounds all the way to silence — and to discover that the quiet at the end is safe and even beautiful.

**Tips:**
1. Try a "listening walk" together — pick one sound and follow it until it fades completely.
2. At bedtime, ring a small bell (or use a phone app) and both listen until it's gone. Notice the silence together.
3. When your child seems jumpy or reactive to sounds, try: "Let's follow that sound all the way to the end. What's there when it stops?"

## Technique Card

**Name:** Follow the Sound Home
**Summary:** Following a sound all the way to silence — and discovering that the quiet at the end is where your magic comes through.
**Steps:**
1. Sit comfortably and close your eyes.
2. Listen for a sound — a bell, a bird, anything.
3. Follow the sound all the way, even as it gets quieter and quieter.
4. Don't jump ahead — stay with it until it disappears completely.
5. Notice the silence. Stay in that quiet moment. That's where the magic is.

---

## Version History

| Date | Version | Change |
|------|---------|--------|
| Feb 16, 2026 | v1.0 | Initial frozen document. Modules 1–4 approved and locked. |
| Feb 17, 2026 | — | Module 1 dialogue revised per Kim's feedback (8 cues, chest/belly logic chain, "shaking" not "trembling"). Previewer updated. Lock record created. |
| Feb 20, 2026 | v1.1 | **CRITICAL CORRECTION.** Modules 2, 3, and 4 updated to match corrected dialogue from Feb 16–17 conversations. Module 3 completely rewritten: passive "watch-only" observer design replaced with Kim's interactive "magical power" selective attention design. Module 2 cues reduced from 5 to 3 (minimal language rule). Module 4 on_start expanded with full therapeutic front-load; phaseAFlow updated with tap-too-early branching. All example dialogue (Call, Buy-In, Rescue, Win) updated across Modules 2–4. Root cause: dialogue corrections lived in conversation threads but were never written back to previewer v5 data structure; APPROVED v1.0 was rebuilt from stale previewer, propagating old versions. |
| March 9, 2026 | v1.2 | **LOCK-BREAK: RENUMBERING + RENAME.** (1) Creature rename: "Shelly" → "Tessa" in M1 and former M2 (now Appendix A). (2) Domain key updates throughout: `calm` → `breathing`, `focus` → `watching`. Art names updated: "Art of Calm" → "Art of Calm-Breathing", "Art of Focus" → "Art of Now-Watching". moduleId prefixes updated accordingly. (3) Module renumbering per Bible v11 Arc 1 session order: old M1 (Belly Breathing) stays M1; old M3 (Thought Clouds) becomes new M2; old M2 (4-7-8) reassigned to Arc 2 M7 (moved to Appendix A); old M4 (Mindful Listening) orphaned from Arc 1 (moved to Appendix B). No therapeutic content was deleted or modified — only metadata, creature names, domain keys, and Art name labels. Bible v9b reference updated to v11 in document hierarchy. |
| March 17, 2026 | v1.3 | **4-7-8 module returns to UNASSIGNED status.** Arc 2 M7 redesigned (Big-Little Spell / Luna / F-2 Attention Shifting — New Spell). 4-7-8 Breathe Spell (Tessa, Breath Awareness, Evolution of M1) is no longer assigned to any arc module. Appendix A status note updated from "REASSIGNED — Arc 2 M7" to "UNASSIGNED." Module content, therapeutic notes, Phase B script, and JSON schema remain valid and available for future arc assignment. Source: UTI v1.7, Kim decisions March 17, 2026. |

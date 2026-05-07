# PHASE B AUDIO PRODUCTION GUIDE

**Version:** 1.0 — March 12, 2026
**Status:** Merged reference for all Phase B audio production work
**Merged from:** Phase B Sound Design Vision v1.0, ElevenLabs Sound Recipe v1.1, Phase B Audio Engine Architecture v1.1
**Related docs (NOT merged here):** Phase B Audio Assembly Guide v1.3 (assembly instructions), Phase B Sound Production Brief v1.2 (production specs)

---

# PART 1: SOUND DESIGN VISION
## The Sonic Language of Everdale's Magic
### Originally: Version 1.0 — February 23, 2026

---

## The Core Idea

When a child closes their eyes in MindfulNest, the screen disappears. What remains is voice and sound. This is the most intimate moment in the app — a child alone with a warm presence, learning to do something new with their body and mind.

The sound design must do three things simultaneously:

1. **Make the meditation feel magical, not clinical.** A voice counting "one... two... three..." over silence is a doctor's office. The same voice over a living soundscape is a spell being cast in Everdale.

2. **Support the therapeutic mechanism without distracting from it.** Sound is scaffolding, not spectacle. The child's attention must stay on the practice (breathing, observing, listening, releasing). Sound enhances that focus — it never competes with it.

3. **Create a sonic signature that children recognize and crave.** When the child hears the first note of Phase B's ambient layer, their body should begin to settle before the voice even speaks. This is classical conditioning — the sound itself becomes a regulation cue over time. This is clinically real: repeated pairing of a neutral stimulus (the sound) with a relaxation response (the practice) creates an association. Eventually the sound alone can trigger partial calming. This is Pavlovian, and it's therapeutic.

---

## Architecture: Three Layers

Every Phase B meditation is built from three sonic layers:

### Layer 1: The Voice (foreground)
The meditation narrator. Warm, wise, unhurried. This is the layer that carries the script — the therapeutic content. Always the loudest and clearest element. The voice is human and present, never processed or effects-laden.

**Production:** ElevenLabs voice generation. One consistent voice across all 12 modules. Gender-neutral warmth — think "beloved grandparent" not "meditation app robot."

### Layer 2: The Ambient Bed (middle ground)
A continuous, evolving sonic texture that fills the space around the voice. This layer creates the feeling of BEING SOMEWHERE — not in a bedroom with a device, but in Everdale, surrounded by its magic.

The ambient bed is the primary differentiator between "guided meditation app" and "magical experience." It turns silence between instructions into atmosphere, and it gives the child something gentle to rest in when the voice pauses.

**Key principles:**
- **Always evolving, never looping.** Children notice loops. The ambient bed should shift subtly throughout the meditation — brighter as the child settles, warmer as they deepen. Even if changes are imperceptible moment-to-moment, the bed at the end should feel different from the bed at the beginning.
- **Keyed to the domain.** Each of the six domains has a distinct sonic palette (see below). A child should be able to close their eyes and know whether they're in a Calm meditation or a Brave one from the ambient bed alone.
- **Breathable.** The bed must have enough sonic space for the voice to sit clearly on top. No dense textures, no competing frequencies in the vocal range. Think: wide, soft, open.
- **Non-melodic.** Melody engages the brain's pattern-recognition systems and pulls attention toward the music. The ambient bed should be textural and tonal — pads, drones, subtle harmonic shifts — but never hummable. If a child could sing it back, it's too melodic.
- **Warm analog character.** Even if digitally produced, the sound should feel organic. Soft edges. Nothing synthetic-sounding, nothing cold, nothing sharp.

**Production:** Ambient music production (custom). Could be produced in Ableton/Logic or sourced from ambient composers with modification rights. Each domain needs a base ambient piece (~2-3 minutes) that can be trimmed to match individual script durations.

### Layer 3: Functional Sound Effects (foreground accents)
Brief, purposeful sounds that synchronize with specific moments in the script. These are not decorative — each one serves a therapeutic or engagement function.

**Types of functional sounds:**

**Breath-sync tones:** Subtle pitched sounds that rise on inhale and descend on exhale, giving the child an auditory guide for their breathing even during pauses in the voice. For M1 (belly breathing): a gentle rising tone on inhale, a soft descending tone on exhale. For M2 (4-7-8): the tones follow the count phases — ascending 4-count tone, sustained hold tone, long descending 8-count tone. These are quiet and background — the child should feel them more than consciously hear them.

**Phase markers:** Very brief sounds that mark transitions. A soft chime or tone when moving from Welcome to Connection. A slight shift in the ambient bed when entering Instruction. These are orienting cues — the child's body learns the structure even without conscious awareness.

**The landing shimmer:** A signature sound that plays during the Landing section — when the voice says "that's your magic." This is the most important functional sound in the entire design. It should feel like something crystallizing, settling, completing. Not triumphant (that's Win's territory) — more like a quiet "there it is." Over time, this sound becomes the child's internal signal that they've touched something real.

**The transition bell:** The sound that bridges Phase A → Phase B. When Bird says "Listen to the voice on the wind..." and the meditation voice arrives, there should be a distinctive sound that marks the threshold. A singing bowl tone, a wind chime, a resonant bell — something that says "you're crossing into a different space now." This is the same sound every time, across all 12 modules. It becomes the Pavlovian cue: "close your eyes, settle in, something good is about to happen."

**Production:** Sound design (custom or curated library). Must be recorded/rendered at high quality. Timing must be precise to script beats.

---

## Personalization in Phase B Voice

Phase B voice stems (Myrrhin narrator) now support personalization with `{childName}`. The child hears their own name spoken during the meditation — grounding them more powerfully than generic "you."

**Frequency:** Exactly 2 uses of `{childName}` per stem — the opening line and the closing line. The body of the meditation uses "you." Example: "Now, {childName}, hold your hands out..." (opening) and "Well done, {childName}." (closing).

**Placement rule:** `{childName}` must appear ONLY in the opening line (before the first cue point) and closing section (after the last cue point). This preserves universal cue point timing — the timed meditation section in the middle has no variable content, so breath-sync tones, shimmers, and phase markers stay consistent across all children.

**Rendering:** Stems with `{childName}` are pre-cached per child at module unlock using segment-level personalization. Only the personalized sentences are rendered per child (~80 characters); the universal body of the meditation is rendered once and shared. See `TTS_PERSONALIZATION_PIPELINE_v1.md` §4.3 for the cost model and §6 for the full Phase B personalization spec.

---

## Domain Sound Palettes

Each domain has a distinct sonic identity. Children experience two modules per domain — the ambient bed should feel related but not identical between the two.

### Calm Domain (Modules 1 & 2)
**Core feeling:** Warm bath. Safe cocoon. Settling.
**Sonic palette:**
- Warm pad in the lower-mid register (think: cello sustained note, but synthesized)
- Extremely slow harmonic movement — chords shifting over 30-60 second intervals
- Subtle air/breath texture underneath (not wind — closer to the sound of a room being still)
- No percussion, no rhythm (the child's breath IS the rhythm)
- Color: amber, golden (matching Calm domain's visual palette)

**M1 (Belly Breathing) specifics:** The simplest, sparest bed. This is the child's first meditation. Minimal layers. Just warmth and space. The bed should feel like being held.

**M2 (4-7-8) specifics:** Slightly richer than M1 — the child is ready for more. The counting creates inherent rhythm, so the bed can include very subtle tonal movement that follows the 4-7-8 arc: gentle rise during inhale counts, sustained warmth during hold counts, a soft blooming/opening during exhale counts. By Cycle 3, the exhale bloom is warmer and wider than Cycles 1-2.

### Focus Domain (Modules 3 & 4)
**Core feeling:** Clear sky. Quiet attention. Spacious.
**Sonic palette:**
- Higher register than Calm — clean, clear tones (think: glass bowls, crystalline pads)
- More space/silence in the texture — Focus meditations are about noticing what's already there
- Subtle high-frequency shimmer (like sunlight on water)
- Very gentle, irregular nature sounds at extreme background (a single distant bird, a leaf)
- Color: sky blue, silver (matching Focus domain's visual palette)

**M3 (Thought Clouds) specifics:** The ambient bed should feel like standing in an open field with a big sky. Spacious. Wide. The occasional barely-audible nature sound represents thoughts drifting through — but they're far away, not demanding attention. This is the sonic equivalent of the observer stance.

**M4 (Mindful Listening) specifics:** This module's Phase B uses the singing bowl as the primary stimulus. The ambient bed should be extremely minimal — almost silence — to let the bowl's resonance fill the space. The singing bowl itself IS the functional sound effect AND the ambient layer. Less is more.

### Heart Domain (Modules 5 & 6)
**Core feeling:** Warm fire. Soft embrace. Tenderness.
**Sonic palette:**
- The warmest palette of all six domains — rich, full, enveloping
- Slightly lower register than Calm, with more harmonic complexity
- A quality of "roundness" — nothing angular, nothing edged
- Very subtle heartbeat-like pulse at extreme background (not literal heartbeat — a soft rhythmic warmth, like being held against someone's chest)
- Occasional delicate melodic fragments — just 2-3 notes, not a melody, more like a lullaby half-remembered
- Color: rose gold, warm pink (matching Heart domain's visual palette)

**M5 (Warm Heart) specifics:** The loving-kindness meditation. The bed should feel like the warmth that spreads outward from the chest. It should start intimate and close, then gradually widen and open as the child extends warmth to others.

**M6 (Friend Fix Bridge) specifics:** This is the most emotionally complex module. The bed should start with a slight tension quality (not scary — more "unresolved") that gradually softens and warms as the child works through the apology/repair process. Resolution in the ambient bed mirrors the relational repair in the practice.

### Brave Domain (Modules 7 & 8)
**Core feeling:** Steady ground. Quiet strength. Approaching.
**Sonic palette:**
- Grounded, present — more body than the other palettes
- Low register anchor (not bass-heavy — more "rooted")
- A quality of forward motion — very subtle, like the feeling of walking steadily
- Wider dynamic range than other domains — can get quieter and then swell gently
- Elements of space and openness (you're standing at the edge of something, looking out)
- Color: deep green, forest (matching Brave domain's visual palette)

**M7 (Brave Steps) specifics:** The anxiety-approach module. The bed should embody the feeling of taking a step forward even when uncertain. A quality of gentle courage — not heroic fanfare, but the quiet bravery of a child facing something scary.

**M8 (Worry Box) specifics:** The containment module. The bed starts slightly more active/textured (representing the worries floating around) and gradually settles as the child names and contains them. By Landing, the bed should feel resolved and still.

### Grounding Domain (Modules 9 & 10)
**Core feeling:** Earth. Weight. Arriving in the body.
**Sonic palette:**
- The most physical/tactile palette — sounds you can almost feel
- Earth-tone textures: low, resonant, substantial
- Subtle sub-bass warmth (felt in the chest more than heard)
- Natural textures more prominent than other domains (distant rain, earth sounds, deep resonance)
- A quality of solidity and presence — "you are HERE, in this body, right now"
- Color: rich brown, deep amber (matching Grounding domain's visual palette)

**M9 (Sense Anchor) specifics:** The 5-senses grounding practice. The bed should be minimal and present — it creates the sonic space in which the child notices what they can hear, feel, see (if eyes open), smell, taste. The bed itself should include some very subtle sounds that the child might "discover" during the listening portion.

**M11 (Squeeze & Release) specifics:** The PMR module. The bed should mirror the tension-release pattern: very slight tightening quality during squeeze cues, then a soft opening/settling during release. Not dramatic — just a subtle breath in the texture that matches what the child's body is doing.

### Rest Domain (Modules 11 & 12)
**Core feeling:** Nighttime. Permission. Letting go.
**Sonic palette:**
- The quietest, softest palette — barely there
- Extremely slow, low-register pad that feels like it could be the sound of the night sky
- Spacious silence between gentle tones — the silence IS the content
- A quality of permission — nothing expects anything of you
- Occasional extremely distant tonal elements (like hearing music from very far away)
- Descending quality — tones drift downward over time, energy settles
- Color: deep indigo, starlight silver (matching Rest domain's visual palette)

**M12 (Body Softening) specifics:** The body scan permission-to-release module. The bed should feel like sinking into something soft. Very gradual descent in register and energy as the child softens body parts one by one.

**M13 (Sleepy Stargazing) specifics:** The acceptance/presence module. The bed should feel like lying on a hillside looking at stars — vast, quiet, peaceful. The most spacious and minimal of all 12 beds. Almost silence with breath-like tonal movement. This is the "just be" module — the sound design should model the permission to stop doing.

---

## Universal Sound Elements (Cross-Module)

### The Transition Bell
A single distinctive sound that plays at the moment between Phase A and Phase B — when Bird says "Listen to the voice on the wind..." and the meditation voice arrives.

**Requirements:**
- Identical across all 12 modules (consistency builds association)
- Resonant and sustained (3-5 seconds of decay)
- Not jarring — the child's eyes are closing
- Culturally neutral — no specific religious or cultural association
- High quality, beautiful in isolation

**Candidates:** Tibetan singing bowl (classic but may have cultural baggage), crystal bowl (cleaner, more neutral), custom-designed resonant tone, tuning fork, a chime that sounds like wind through Everdale's trees.

**Recommendation:** A custom tone that blends a singing bowl quality with a nature-inspired resonance — something that could be "the sound the wind makes when it passes through the ancient trees of Everdale." This ties it to the world lore without borrowing from any specific meditation tradition.

### The Landing Shimmer
A brief, distinctive sound that accompanies the Landing section — when the voice names the child's magic.

**Requirements:**
- Brief (1-2 seconds)
- Feels like something settling into place, crystallizing, completing
- Quiet enough to sit under the voice, not compete with it
- Emotionally warm — this is a moment of gentle recognition
- Slightly different per domain (tinted by the domain's color) but recognizably the same element

**Sound character:** A soft, multi-toned chime with a gentle sparkle. Like a snowflake landing. Like a key turning in a lock. The moment of "ah, there it is."

### Breath-Sync Tones (Breathing Modules Only)
Applicable to Modules 1, 2, and potentially 10 and 11.

**For inhale:** A very gentle rising tone. Starts at the beginning of the inhale instruction, rises smoothly, reaches its peak at full lungs. Volume: 20-30% of voice level. The child should feel guided by it without consciously tracking it.

**For hold (M2 only):** The rising tone sustains at its peak — a warm, held note. Not tense — just present. Gives the child an auditory anchor during the counted hold.

**For exhale:** The tone descends and opens. Slightly longer and warmer than the inhale tone. Can bloom outward (subtle widening in the stereo field) as it descends. The exhale tone is the most "rewarding" of the three — it should feel like a release.

**Cross-cycle evolution:** The breath-sync tones can get subtly warmer, wider, or richer across cycles. Cycle 1 is simple. By Cycle 3 or 4, the tones have more harmonic richness. The child's practice is literally making the sound world more beautiful — an invisible reward for continuing.

---

## The Conditioning Effect (Why This Matters Clinically)

This sound design isn't aesthetic decoration. It's a clinical tool.

**Classical conditioning:** The brain associates the ambient soundscape with the parasympathetic state achieved during practice. After repeated sessions, the sound begins to trigger partial calming on its own. The transition bell becomes a settling cue. The landing shimmer becomes a recognition cue. The domain palette becomes a body-state cue.

**Therapeutic acceleration:** A child who has done ten M1 sessions has had ~10 minutes of belly breathing paired with the Calm domain ambient bed. By session 11, their body begins settling the moment they hear the ambient bed — before the voice even speaks. This means the therapeutic "dose" of each session increases over time: the sound does some of the work, freeing the child's attention for deeper practice.

**Transfer potential:** If the ambient beds are available outside the app (e.g., as a "calm sounds" playlist a therapist can recommend for homework), the conditioning can extend beyond the module experience. A child who needs to calm down at school could put in earbuds and hear the Calm palette — and their body may begin the regulation process from sound alone.

**Engagement compounding:** The evolving sound design gives children a reason to close their eyes and pay attention even on their 20th session. The voice script is the same, but the sonic experience is rich enough to be slightly different each time. This counteracts the "I already know this one" fatigue that plagues children's apps.

---

## Production Approach

### Phase 1: Prototype with M1 and M2
Before producing all 12 ambient beds, create prototypes for the two Calm domain modules. These become the reference point for all other domains.

**M1 prototype deliverables:**
- Calm ambient bed (sparse version), ~2:00
- Breath-sync tones (inhale rise, exhale descend)
- Transition bell (one candidate)
- Landing shimmer (one candidate)
- Full layered mix: voice + ambient + functional sounds

**M2 prototype deliverables:**
- Calm ambient bed (richer version), ~2:30
- Breath-sync tones (inhale rise, hold sustain, exhale descend with 4-7-8 pacing)
- Cross-cycle evolution (tones warming Cycle 1 → 3)
- Full layered mix: voice + ambient + counting + functional sounds

**Evaluation criteria:**
- Does the child feel like they're somewhere magical? (or does it feel like a doctor's office with background music?)
- Does the sound support or distract from the practice?
- After listening 5 times, does it feel repetitive or does it retain gentle interest?
- Does the transition bell create a "settle in" response?
- Does the landing shimmer feel like a quiet arrival?

### Phase 2: Domain Palette Development
Once Calm is validated, produce palettes for the remaining five domains. Work in domain pairs (Focus, Heart, Brave, Grounding, Rest) to ensure sufficient contrast between them.

### Phase 3: Per-Module Customization
Customize each domain palette for its two modules. This is the subtlest layer — same palette, slightly different emphasis or evolution pattern.

### Phase 4: Mixing and Timing
Layer all three elements (voice, ambient, functional) and precisely time functional sounds to script beats. Each module gets a final mixed audio file as the production master.

---

## Technical Considerations

### Format
- Voice: High-quality speech synthesis (ElevenLabs), delivered as isolated stems
- Ambient beds: 48kHz/24bit WAV, delivered as stems for flexible mixing
- Functional sounds: Individual WAV files with precise timing markers
- Final mix: Per-module mixed audio file (voice + ambient + functional) for the app player

### App Integration
The module player receives a single audio file per module for Phase B. No dynamic mixing needed in v1 — the production pipeline delivers ready-to-play files. Future versions could support dynamic ambient layers that respond to real-time breathing sensor data (phone microphone detecting breath sounds).

### Duration Flexibility
Ambient beds should be produced at 2:30-3:00 to accommodate potential script revisions. Trim to match final script timing. The bed should have a natural fade-in at the start and a subtle opening at the end (no hard cut when Rescue begins).

### Accessibility
- Sound design must not be REQUIRED for the therapeutic experience to work. If a child uses the app with sound off (hearing-impaired, noisy environment), the voice script alone must be sufficient.
- Sound is an enhancement layer — powerful, clinically meaningful, but not load-bearing.
- The screen visual during Phase B (gentle breathing circle, ambient glow) provides an alternative anchor for children who peek.

---

## Budget Considerations

**Voice (ElevenLabs):** Per-module cost is minimal. 12 scripts × ~150 words average = ~1,800 words of voice generation. ElevenLabs pricing for high-quality voice is manageable.

**Ambient beds:** Options range from:
- **DIY with synths/samples** — lowest cost, highest effort, requires music production skill
- **Commission from ambient music producer** — moderate cost ($200-500 per domain × 6 = $1,200-3,000), professional quality
- **AI music generation** — emerging option (Suno, Udio), but quality control is challenging for something this specific
- **Stock ambient libraries with custom layering** — moderate cost, may lack the bespoke quality

**Functional sounds:** Can be created from high-quality sample libraries or custom recorded. A skilled sound designer could produce all universal elements (transition bell, landing shimmer, breath-sync tones) in a few hours.

**Recommended approach for MVP:** Commission one ambient music producer to create 6 domain beds + the 12 module-specific variations, plus produce the universal functional sounds. Total budget estimate: $3,000-5,000 for a complete Phase B audio production package across all 12 modules. This is a one-time production cost that scales to zero on a per-user basis.

---

## Relationship to Other Design Documents

- **Phase B scripts** (M1-M13 meditation scripts) define the VOICE layer timing and content
- **Visual Production Guide v3** defines what the screen shows during Phase B (the visual companion to the sound)
- **The Bible** establishes the world lore that the sound design expresses (Everdale's magic, the six domains, the creatures)
- **MODULE_AUTHORING_GUIDE v4.3 §5.5** establishes the meditation voice as a distinct character from Guide Bird

The sound design vision does NOT modify any locked document. It adds a new production layer that enhances the experience defined by existing specs.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial vision document. Three-layer architecture (voice, ambient bed, functional sounds). Six domain palettes defined. Universal elements specified (transition bell, landing shimmer, breath-sync tones). Clinical conditioning rationale established. Production phasing and budget outlined. |

---

# PART 2: ELEVENLABS SOUND RECIPE
# MindfulNest Sound Production Recipe
## ElevenLabs Step-by-Step — Modules 1 & 2
### Version 1.1 — February 24, 2026

**What this is:** The exact prompts to type into ElevenLabs, in the exact order, to produce every sound element for M1 and M2. No audio production skills required. One platform, one subscription.

**What you need:**
- ElevenLabs account (Starter plan minimum, $5/mo; Creator plan recommended, $22/mo for more credits)
- A few hours over a weekend
- Patience to generate multiple candidates and pick the best ones

**How this works:** You'll generate raw sound elements first (Steps 1-5), then assemble them on the ElevenLabs Studio 3.0 timeline (Step 6). Think of it like making a collage — AI creates the pieces, you arrange them.

---

# STEP 1: GENERATE THE MEDITATION VOICE

**Tool:** ElevenLabs → Text to Speech

### 1.1 Choose a Voice

Go to ElevenLabs Voice Library. You're looking for:
- Warm, wise, unhurried
- Gender-neutral (or warm male — think Morgan Freeman's calm, not his drama)
- NOT breathy/whisper (that's a meditation cliché)
- NOT robotic or flat
- American or British English, neutral accent

**Test method:** Paste this excerpt and generate with 3-4 different voices:

```
Ahh... you've come to learn the magic of Calm. Good.
You saw the breath travel all the way down to the belly — that's where the magic lives. Now it's your turn.
Put your hand right on your belly. You can feel yourself breathing in and out. Here's what I want you to do.
```

Pick the voice that sounds like a beloved grandparent sitting beside a child at bedtime. Not performing. Just... being there.

### 1.2 Voice Settings

Once you've chosen a voice, adjust these settings:
- **Stability:** 65-75% (enough consistency to feel reliable, enough variation to sound alive)
- **Clarity + Similarity Enhancement:** 75-85% (keeps the voice character strong)
- **Style Exaggeration:** 15-25% (a touch of personality, not overacting)

### 1.3 Generate M1 Voice Stem

Paste the full M1 script below into TTS. Use `...` for natural pauses and `<break time="Xs"/>` for timed pauses if SSML is supported on your plan.

```
Ahh... you've come to learn the magic of Calm. Good.

You saw the breath travel all the way down to the belly — that's where the magic lives. Now it's your turn.

Put your hand right on your belly. You can feel yourself breathing in and out. Here's what I want you to do.

Breathe in slowly through your nose... and feel your belly push your hand up.

Now let it out... nice and slow... and feel your belly come back down.

That's it. Let's do it again.

Breathe in... your belly rises... and breathe out... your belly falls... nice and easy.

Keep going just like that. In... and out...

If your brain starts thinking about other things, that's OK. Just feel your belly again.

In... and out...

One more. Nice and slow.

In... and out...

That feeling right there... that calm... that's your magic.

Stay right there. Just keep breathing.
```

**Important:** The ellipses (...) create natural pauses. If the voice rushes through them, try adding extra periods or `<break>` tags. The pacing should feel like ~2 words per second for spoken content, with 3-4 second breathing pauses where the child would actually breathe.

**Generate 3 versions.** Pick the one with the best pacing and warmth. Export as WAV.

### 1.4 Generate M2 Voice Stem

```
Ahh... you're back. And you're ready for something more powerful. Good.

You saw the breathing circle — 4 in, 7 hold, 8 out. The long breath out is where the magic is. Now it's your turn.

I'm going to count for you. All you have to do is breathe along.

Here we go. Breathe in... one... two... three... four...

Now keep the air inside... one... two... three... four... five... six... seven...

And let it out, nice and slow... one... two... three... four... five... six... seven... eight.

Good. Again.

In... one... two... three... four...

Hold... one... two... three... four... five... six... seven...

And out... one... two... three... four... five... six... seven... eight.

Can you feel it? One more.

Even slower this time. In... one... two... three... four...

Keep it right there... one... two... three... four... five... six... seven...

And out... all the way... one... two... three... four... five... six... seven... eight...

That's the spell.

That deep, deep calm... that rhythm... that's your magic now.

Stay right there. Keep the rhythm going.
```

**Counting pacing note:** The counts should land at roughly 1 per second. If the AI rushes the counting, try separating counts onto their own lines or adding more periods between them. Cycle 3 should be slightly slower than Cycles 1-2 — if ElevenLabs doesn't naturally slow down at "Even slower this time," you may need to generate Cycle 3 as a separate clip with adjusted speed settings and splice it in Studio.

**Generate 3 versions.** Export best as WAV.

### 1.5 Gender Variants (Optional — for production)

For each module, also generate the Welcome line in two additional versions:
- "Ahh... welcome, young man. You've come to learn the magic of Calm. Good."
- "Ahh... welcome, young lady. You've come to learn the magic of Calm. Good."

(And equivalent for M2's "you're back" welcome.)

---

# STEP 2: GENERATE THE AMBIENT BEDS

**Tool:** ElevenLabs → Sound Effects (SFX v2)

Why SFX instead of Eleven Music? The SFX generator handles drones and textures better than the music generator (which wants to create "songs"). SFX v2 also supports seamless looping at 48kHz — exactly what we need for continuous beds.

### 2.1 M1 Ambient Bed — "Being Held"

**Settings:**
- Duration: 30 seconds (we'll loop it)
- Looping: ON (critical — creates seamless loop)
- Prompt influence: HIGH (we want exactly what we describe)

**Prompt — generate 10+ candidates, pick the best 2-3:**

```
Warm ambient drone, deep pad in D major, extremely slow evolving harmonics, 
no melody, no rhythm, no percussion, no vocals. Soft analog synthesizer 
warmth, cello-like sustained tone in the lower-mid register. Gentle and 
enveloping, like a warm blanket. Minimal movement, mostly sustained. 
Meditative and safe. Very quiet and subtle.
```

**Alternate prompt if first results are too "musical":**

```
Deep warm drone, single sustained tone with very slow harmonic breathing, 
no notes no melody no beat. Pure texture. Like the hum of a warm room. 
Analog warmth, soft low-mid frequencies. Ambient soundscape for deep 
meditation. Extremely minimal and static.
```

**Alternate prompt if results are too dark/moody:**

```
Warm golden ambient texture, soft sustained pad, comforting and safe like 
sunlight through a window. No melody, no rhythm. Just warmth. Gentle 
harmonics in a major key. Analog synthesizer drone, very slow and peaceful. 
Children's meditation background.
```

**What to listen for:**
- ✅ Feels warm and safe
- ✅ No melody you could hum
- ✅ No beats or pulses
- ✅ You could listen to it for 5 minutes without getting bored or distracted
- ✅ Loops seamlessly (test by letting it repeat)
- ❌ Reject anything with recognizable instruments playing notes
- ❌ Reject anything dark, ominous, or tense
- ❌ Reject anything with nature sounds (rain, birds, etc.)

**Export:** WAV, 48kHz. Label it `M1_ambient_bed_warm.wav`

### 2.2 M2 Ambient Bed — "The Spell Working"

M2 needs a richer bed than M1. Same palette, more presence.

**Settings:**
- Duration: 30 seconds
- Looping: ON
- Prompt influence: HIGH

**Prompt:**

```
Rich warm ambient drone, evolving pad in D major with gentle harmonic 
movement, no melody, no rhythm, no percussion, no vocals. Warmer and 
fuller than a simple drone — multiple layered harmonics that slowly shift 
and breathe. Analog synthesizer warmth with a touch of shimmer in the 
upper harmonics. Meditative and enveloping, like being inside a warm 
golden cloud. Suitable for a children's breathing meditation.
```

**Alternate prompt:**

```
Lush warm ambient soundscape, sustained synthesizer pad with slow harmonic 
evolution, gentle tonal movement in major key. No melody no beat. Rich and 
full, multiple harmonic layers breathing together very slowly. Warm analog 
character. Feels like magic slowly building. Peaceful and safe.
```

**What to listen for:**
- ✅ Everything from M1 checklist PLUS:
- ✅ Noticeably richer/fuller than M1 bed
- ✅ Some gentle tonal movement (not static)
- ✅ Feels like "something is happening" without being distracting

**Export:** WAV, 48kHz. Label it `M2_ambient_bed_rich.wav`

---

# STEP 3: GENERATE THE UNIVERSAL ELEMENTS

**Tool:** ElevenLabs → Sound Effects (SFX v2)

### 3.1 Transition Bell

This is the most important single sound. It plays at the threshold between Phase A and Phase B — the moment the child closes their eyes. After hundreds of sessions, this sound alone will begin to calm the child.

**Settings:**
- Duration: 5 seconds
- Looping: OFF
- Prompt influence: HIGH

**Prompt — generate 15-20 candidates. Be very picky.**

```
Single resonant bell strike, warm metallic singing bowl tone, clear attack 
with long natural decay over 5 seconds. Not harsh or bright — warm and 
golden. Organic resonance with a subtle shimmering quality in the decay. 
Meditative, ancient, calming. Like wind passing through a crystal. 
Single strike, not repeated.
```

**Alternate prompts to try:**

```
Singing bowl strike, warm resonant tone, single hit with 5 second natural 
sustain and decay. Rich harmonics, not tinny. Peaceful and grounding. 
The kind of sound that makes you take a deep breath when you hear it.
```

```
Crystal bell tone, single clear strike decaying naturally over 5 seconds. 
Warm fundamental with shimmering overtones. Not a church bell, not a 
wind chime — something between. Ancient and organic. Meditation bell.
```

**What to listen for:**
- ✅ Beautiful enough to hear 500 times without fatigue
- ✅ Clear attack that says "something is beginning"
- ✅ Long, warm decay that says "settle in"
- ✅ Makes YOU take a breath when you hear it
- ❌ Reject anything harsh, bright, or startling
- ❌ Reject anything with multiple strikes or repetition
- ❌ Reject anything that sounds like a doorbell, alarm, or notification

**Export:** WAV, 48kHz. Label it `transition_bell.wav`

### 3.2 Landing Shimmer

Plays once per module during the "that's your magic" moment. Brief, crystalline, warm.

**Settings:**
- Duration: 2 seconds
- Looping: OFF
- Prompt influence: HIGH

**Prompt — generate 10+ candidates:**

```
Brief crystalline chime shimmer, multiple gentle high tones sounding 
almost simultaneously then fading quickly. Like a tiny cascade of light. 
Warm and magical, not cold or icy. The sound of something settling 
perfectly into place. A snowflake landing. 1.5 seconds total. Delicate 
and beautiful.
```

**Alternate prompt:**

```
Gentle magical sparkle sound, brief cluster of warm high-pitched bell 
tones, shimmering and settling. Like stardust falling. Not a harsh 
sparkle — soft and warm. Very brief, under 2 seconds. A quiet moment 
of wonder.
```

**What to listen for:**
- ✅ Brief (1-2 seconds)
- ✅ Feels like completion, like something clicked into place
- ✅ Warm, not cold
- ✅ Delicate, not showy
- ❌ Reject anything that sounds like a video game power-up
- ❌ Reject anything longer than 2 seconds
- ❌ Reject anything harsh or piercing

**Export:** WAV, 48kHz. Label it `landing_shimmer.wav`

### 3.3 Exhale Shimmers (3 Variants)

These play at the end of each exhale cycle — tiny rewards that grow across cycles.

**Variant 1 — "Barely There" (Cycle 1)**

Settings: Duration 1 second, Looping OFF, Prompt influence HIGH

```
Extremely subtle single crystalline tone, barely audible tiny sparkle, 
like a single star appearing. Very quiet, very brief, very delicate. 
Under 1 second. Just a hint of something magical. Almost inaudible.
```

**Variant 2 — "Something's Happening" (Cycle 2)**

Settings: Duration 1 second, Looping OFF, Prompt influence HIGH

```
Two gentle crystalline tones, a quiet sparkle slightly more present 
than a whisper. Like two stars appearing close together. Brief, warm, 
delicate. About 1 second. Subtle but noticeable.
```

**Variant 3 — "Magic Releasing" (Cycle 3 / Final Exhale)**

Settings: Duration 1.5 seconds, Looping OFF, Prompt influence HIGH

```
Brief cascade of crystalline chime tones, 3 or 4 warm sparkle notes 
in quick succession, settling and fading. Like a tiny shower of 
stardust. Magical but gentle. The most beautiful version of a small 
sparkle. 1.5 seconds. Warm and resolving.
```

**What to listen for across all 3:**
- ✅ They form a clear progression: whisper → present → beautiful
- ✅ They sound like they belong to the same family (similar tonal character)
- ✅ Variant 3 feels like a satisfying tiny payoff
- ❌ Reject if any variant is louder/more dramatic than the landing shimmer (the landing shimmer should be the biggest version)

**Export:** WAV, 48kHz. Label them `exhale_shimmer_1_subtle.wav`, `exhale_shimmer_2_medium.wav`, `exhale_shimmer_3_full.wav`

---

# STEP 4: GENERATE BREATH-SYNC TONES

**Tool:** ElevenLabs → Sound Effects (SFX v2)

These are the tones that rise on inhale, sustain on hold, and descend on exhale — creating the feeling that the sonic world is breathing with the child.

### 4.1 Strategy

We can't tell ElevenLabs "make a tone that rises for exactly 4 seconds." But we CAN generate rising tones, sustaining tones, and falling tones as separate clips and arrange them on the timeline. Think of it like building with Lego.

### 4.2 Inhale Tones (Rising)

**Settings:** Duration 5 seconds, Looping OFF, Prompt influence HIGH

**Prompt — generate 8-10 candidates:**

```
Gentle rising tone, soft pure synthesizer sound slowly ascending in pitch 
over 4-5 seconds. Warm sine wave quality with a touch of organic warmth. 
Like light slowly rising. Very subtle, very smooth, continuous upward 
glide. No abrupt changes. Meditative and gentle. Quiet volume.
```

**Alternate prompt:**

```
Smooth ascending drone, single warm tone gliding slowly upward over 
5 seconds. Clean and pure with slight warmth. Like a gentle inhale 
translated into sound. Ambient and atmospheric, not musical. Very soft.
```

**What to listen for:**
- ✅ Smooth continuous rise (no steps or jumps)
- ✅ Warm and pure, not harsh
- ✅ Feels like breathing in
- ✅ Quiet enough to sit under a speaking voice

**Export:** WAV, 48kHz. Label `inhale_tone_rising.wav`

You need 3 variants with increasing warmth for the 3 cycles. If you can't get 3 distinct versions from generation alone, use ONE good version and we'll handle the warmth evolution through volume/placement in the mix (simpler is fine for v1).

### 4.3 Hold Tone (M2 Only — Sustained)

**Settings:** Duration 8 seconds, Looping OFF, Prompt influence HIGH

```
Warm sustained synthesizer tone, single held note with very subtle 
harmonic blooming over 7-8 seconds. Like the sound of holding something 
precious and warm inside. Full, sustained, not tense — held gently. 
Slight increase in richness over the duration. Pure and meditative.
```

**What to listen for:**
- ✅ Feels warm and full, not tense
- ✅ Stays at one pitch (doesn't rise or fall)
- ✅ Slight organic variation (not robotic sustain)
- ❌ Reject if it sounds like a flatline/alarm

**Export:** WAV, 48kHz. Label `hold_tone_sustained.wav`

### 4.4 Exhale Tones (Descending + Breathy)

This is the most important breath-sync element — the exhale is where the magic is.

**Settings:** Duration 9 seconds, Looping OFF, Prompt influence HIGH

**Prompt — generate 10+ candidates:**

```
Gentle descending tone with breathy airy texture, soft synthesizer sound 
slowly falling in pitch over 8-9 seconds. Warm and opening, like a long 
peaceful exhale. The tone has a breathy wind-like quality mixed into it — 
not literal wind, but the sonic feeling of breath releasing. Gradually 
opens wider in the stereo field. Settling, releasing, peaceful. Very soft.
```

**Alternate prompt:**

```
Slow descending warm drone with breath texture, a tone that glides 
downward gently over 8 seconds while gaining a soft airy quality. 
Like magic slowly releasing into the air. Breathy and warm, not cold 
or windy. Organic synthesizer quality. Meditation exhale sound. 
Very subtle and quiet.
```

**What to listen for:**
- ✅ Smooth continuous descent
- ✅ Has that breathy/airy quality (the "wind texture" from the vision doc)
- ✅ Feels like releasing, letting go
- ✅ More satisfying than the inhale tone
- ❌ Reject if it sounds like a descending alarm or siren

**Export:** WAV, 48kHz. Label `exhale_tone_descending.wav`

### 4.5 Simplified Alternative

**If generating separate inhale/hold/exhale tones feels like too many pieces:**

Try generating a single "breathing cycle" clip instead:

```
Complete breathing cycle translated into ambient sound: a warm tone 
that slowly rises for 4 seconds, holds steady for 2 seconds, then 
gently descends with a breathy quality for 5 seconds. One continuous 
smooth arc. Like the sound of a single magical breath. Very subtle, 
meditative synthesizer quality.
```

Duration: 12 seconds. This gives you one piece instead of three to arrange. Generate several and pick the one with the best arc. For M2, you'd need a longer version (duration 20 seconds) with a 4-rise, 7-hold, 8-descent pattern.

---

# STEP 5: GENERATE THE BREATHY WIND BLOOM (M2 EXHALE ENHANCEMENT)

**Tool:** ElevenLabs → Sound Effects (SFX v2)

This is the element that makes M2's exhale counts feel like the sonic world is opening up. It's layered ON TOP of the descending exhale tone.

**Settings:** Duration 10 seconds, Looping OFF, Prompt influence HIGH

```
Soft ethereal wind bloom, a gentle breath-like texture that slowly opens 
and expands over 8-10 seconds. Not harsh wind — a warm, magical, breathy 
opening. Like the air itself is sighing with relief. Gradually widens in 
the stereo field. Very subtle, ambient, meditative. The feeling of space 
opening up around you.
```

**This is optional for v1.** If the exhale tones from Step 4.4 already have enough breathy character, you may not need this separate element. Listen to your exhale tones in context first. If they feel too "pure tone" and not enough "breath," add this wind bloom underneath.

**Export:** WAV, 48kHz. Label `exhale_wind_bloom.wav`

---

# STEP 6: ASSEMBLE IN ELEVENLABS STUDIO 3.0

**Tool:** ElevenLabs → Studio

This is where it all comes together. Studio 3.0 has a visual timeline where you can layer multiple audio tracks. Think of it like a simplified GarageBand built into the browser.

### 6.1 Create a New Project

Name it "MindfulNest M1 Phase B" (and later, a separate one for M2).

### 6.2 Import Your Elements

Upload these files to the project:
- `M1_voice.wav` (from Step 1.3)
- `M1_ambient_bed_warm.wav` (from Step 2.1)
- `transition_bell.wav` (from Step 3.1)
- `landing_shimmer.wav` (from Step 3.2)
- `exhale_shimmer_3_full.wav` (from Step 3.3 — M1 only uses Variant 3, on the final breath)
- `inhale_tone_rising.wav` (from Step 4.2)
- `exhale_tone_descending.wav` (from Step 4.4)

### 6.3 Arrange on the Timeline

**Track 1 (top): VOICE** — Place the voice stem. This is your timing master. Everything else aligns to it.

**Track 2: AMBIENT BED** — Place the looping ambient bed starting ~3 seconds BEFORE the voice begins. Set it to a very low volume (~8% of the voice level, gain 0.08). Previous default of 15-20% was too prominent — lighter bed reduces cognitive load for children.

**Track 3: TRANSITION BELL** — Place the transition bell so its strike happens ~3 seconds before the voice starts speaking. The bell's decay should overlap with the first word of the Welcome. This creates the "crossing the threshold" feeling.

**Track 4: BREATH-SYNC TONES** — Place the rising inhale tone at each point where the voice says "Breathe in..." and the falling exhale tone at each "let it out..." / "and out..." Trim clips to match the actual breathing duration in the voice stem. Set volume VERY low (10-15% of voice). You should feel these more than hear them.

> **⚠️ Cue placement method (v1.1):** Use vosk speech-to-text to find exact word timestamps. Do NOT guess from waveform analysis. Cue words like "breathe" may appear multiple times — use script cue markers (`{{INHALE_CUE}}`) for disambiguation. See Audio Assembly Guide §2.2 for the full pipeline.

**Track 5: SHIMMERS** — Place `exhale_shimmer_3_full.wav` right at the end of the last "and out..." before the Landing section. Place `landing_shimmer.wav` right as the voice says "that's your magic." Both at ~20-25% of voice volume.

### 6.4 M2 Assembly

Same process but with more elements:

**Track 1: VOICE** — M2 voice stem.

**Track 2: AMBIENT BED** — M2 richer bed. Same placement rules.

**Track 3: TRANSITION BELL** — Same as M1.

**Track 4: BREATH-SYNC TONES** — This is where the magic-building lives:

| Moment | Tone | Volume | Notes |
|---|---|---|---|
| Cycle 1 inhale (counts 1-4) | Inhale tone, trimmed to ~4s | 10% of voice | Pure and simple |
| Cycle 1 hold (counts 1-7) | Hold tone, trimmed to ~7s | 10% of voice | Warm sustain |
| Cycle 1 exhale (counts 1-8) | Exhale tone, trimmed to ~8s | 12% of voice | Gentle descent |
| Cycle 2 inhale | Same inhale tone | 12% of voice | Slightly louder |
| Cycle 2 hold | Same hold tone | 12% of voice | Slightly louder |
| Cycle 2 exhale | Same exhale tone | 14% of voice | Slightly louder |
| Cycle 3 inhale | Same inhale tone | 14% of voice | Warmest |
| Cycle 3 hold | Same hold tone | 14% of voice | Warmest |
| Cycle 3 exhale | Same exhale tone | 16% of voice | Warmest, longest |

The gradual volume increase across cycles creates the "getting richer" effect without needing 3 different tone files. Simple but effective.

**Track 5: EXHALE SHIMMERS** —

| Moment | Shimmer Variant | Volume |
|---|---|---|
| End of Cycle 1 exhale (at "eight") | `exhale_shimmer_1_subtle.wav` | 8% of voice |
| End of Cycle 2 exhale (at "eight") | `exhale_shimmer_2_medium.wav` | 12% of voice |
| End of Cycle 3 exhale (at "eight...") | `exhale_shimmer_3_full.wav` | 16% of voice |

**Track 6: LANDING SHIMMER** — At "that's your magic now." 20% of voice volume.

### 6.5 Mix Check

Before exporting, listen to the complete assembly and check:

- [ ] Can you hear every word of the voice clearly? (If not, lower other elements)
- [ ] Does the ambient bed feel "there" without being distracting?
- [ ] Does the transition bell feel like a threshold moment?
- [ ] Do the breath-sync tones feel like the world is breathing with you? (If you can't feel them at all, raise slightly. If they're distracting, lower.)
- [ ] Do the exhale shimmers grow across cycles? (M2)
- [ ] Does the landing shimmer feel like "yes, that's it"?
- [ ] Would a 7-year-old feel safe listening to this?

### 6.6 Export

Export the complete mix. Label it:
- `M1_phase_b_complete_mix.mp3` (for app)
- `M2_phase_b_complete_mix.mp3` (for app)

If Studio supports WAV export, also export WAV versions for archival.

---

# STEP 7: ALTERNATIVE ASSEMBLY (If Studio 3.0 Doesn't Work)

If ElevenLabs Studio doesn't give you enough timeline control (e.g., can't position clips precisely enough), here are free alternatives:

### Option A: Audacity (Free, Mac/Windows/Linux)
- Download from audacityteam.org
- Import each file as a separate track (File → Import → Audio)
- Drag clips to the right position on the timeline
- Adjust volume per track with the track volume slider
- Export as WAV or MP3 (File → Export)
- **Learning time:** Watch one 10-minute YouTube tutorial on "Audacity multitrack editing"

### Option B: GarageBand (Free, Mac only)
- Create new Empty Project
- Drag audio files onto tracks
- Position clips on the timeline
- Adjust track volumes
- Export (Share → Export Song to Disk)
- **Learning time:** If you've ever used GarageBand for anything, you're already set

### Option C: Bandlab (Free, browser-based)
- Go to bandlab.com, create free account
- Create new project
- Upload and arrange audio files on timeline tracks
- Adjust volumes
- Export
- **Learning time:** Very similar interface to Studio 3.0

---

# TOTAL EFFORT AND COST ESTIMATE

### Time Estimate

| Step | Time | Skill Level |
|---|---|---|
| Step 1: Voice generation (both modules) | 1-2 hours | Type and click |
| Step 2: Ambient beds (both modules) | 1-2 hours | Type, listen, pick |
| Step 3: Universal elements (bell, shimmers) | 1-2 hours | Type, listen, be picky |
| Step 4: Breath-sync tones | 1-2 hours | Type, listen, pick |
| Step 5: Wind bloom (optional) | 30 min | Type, listen |
| Step 6: Assembly | 2-3 hours | Drag and position |
| **Total** | **7-12 hours** | **Weekend project** |

### Cost Estimate

| Item | Cost |
|---|---|
| ElevenLabs Creator plan (1 month) | $22 |
| That's it. | — |
| **Total** | **$22** |

If you burn through credits during the generation phase (lots of regenerating to find the right sounds), you might need a second month or the Pro plan ($99/mo). Still trivially cheap compared to commissioning audio production.

---

# WHAT TO DO IF AI GENERATION ISN'T WORKING

### "The ambient beds keep having melody"
Add to your prompt: "absolutely no melody, no notes, no musical phrases, no harmonic progression, purely textural drone"

### "The tones sound robotic/digital"
Add to your prompt: "organic, analog synthesizer warmth, slightly imperfect, human-feeling"

### "Everything sounds too quiet/too loud"
This is a mixing issue, not a generation issue. Adjust volumes in the assembly step. The voice should always be loudest.

### "The shimmer sounds like a video game"
Add to your prompt: "natural, organic, not digital, not 8-bit, not retro, think acoustic chime not electronic sparkle"

### "I can't get the breathy exhale tone right"
Generate separately: (1) a pure descending tone, and (2) a soft breath/wind texture. Layer them on two tracks in assembly. This gives you independent control over the tonal and breathy components.

### "The transition bell sounds like a phone notification"
This is the hardest element to get right. Key phrase additions: "ancient," "resonant," "long natural decay," "singing bowl quality." Avoid: "chime," "ding," "alert." Generate 20+ candidates. The right one will be obvious when you hear it.

### "Cycle 3 of M2 doesn't sound slower"
Generate the voice stem for Cycle 3 separately at a slightly lower speed setting, then splice it into the full stem during assembly.

---

# SCALING TO ALL 12 MODULES

Once M1 and M2 are done and you're happy with the results, the remaining 10 modules follow the same pattern:

1. **Voice stem** — paste script, generate, export (same voice!)
2. **Ambient bed** — new domain palette prompt (I can write prompts for all 6 domains)
3. **Universal elements** — transition bell is IDENTICAL across all modules. Landing shimmer uses the same base sound.
4. **Functional sounds** — only breathing modules (M1, M2, and potentially M11, M12) need breath-sync tones. Non-breathing modules may need different functional sounds (e.g., M4 needs a singing bowl tone, M3 might need a gentle wind sound for thought clouds drifting).
5. **Assemble** — same process, gets faster each time

Estimated time for modules 3-12 after you've done 1-2: ~3-5 hours each (you'll be fast at it by then).

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Complete step-by-step recipe for M1 and M2 using ElevenLabs only. Seven steps covering voice, ambient beds, universal elements, breath-sync tones, wind bloom, assembly, and troubleshooting. |
| 1.1 | February 24, 2026 | Assembly section: added vosk STT cue placement note and cue marker reference for Track 4 breath-sync tones. Ambient bed volume lowered from 15-20% to 8%. Cross-references Audio Assembly Guide §2.2 for disambiguation pipeline. |

---

# PART 3: AUDIO ENGINE ARCHITECTURE
# Phase B Audio Engine Architecture
## Version 1.1 — February 24, 2026

**Purpose:** Define how the module player assembles rich, layered Phase B meditation audio at runtime from a voice stem + reusable sound library + cue point metadata. This replaces pre-baked single-file audio with a dynamic mixing system that scales to any number of modules with zero manual audio production per module.

**Key insight:** The voice stem is the only per-module unique audio asset. Everything else — ambient beds, functional sounds, transitions — is drawn from a shared library and triggered by cue point metadata.

**Dependencies:**
- Canonical Data Model (frozen — this document proposes additions)
- Module JSON Schema Guardrails (this extends `guidedAudioRef`)
- Sound Design Vision (Part 1 of this document)
- Phase B Sound Production Brief (separate document)

---

## PART 1: THE CORE IDEA

### Before (Single File)
```
guidedAudioRef: "audio/guided/m2_calm_down.mp3"
                ↓
        [ Player plays one file ]
```

### After (Dynamic Mix)
```
phaseBVoiceStem: "audio/stems/m2_voice.mp3"
phaseBMixConfig: { domain, cuePoints[] }
                ↓
        [ Player loads voice stem ]
        [ Player selects ambient bed from domain ]
        [ Player reads cue points ]
        [ Player triggers library sounds at cue times ]
        [ Player mixes all layers in real-time ]
```

### Why This Is Better
1. **Automated module generation:** AI writes script → TTS generates voice → AI identifies cue points from script text → done. No audio production.
2. **Consistency:** Every module in a domain shares the same sonic palette automatically.
3. **Updatability:** Improve an ambient bed once → all modules in that domain improve.
4. **Personalization potential (v2+):** Adjust ambient bed volume per child preference. Disable functional sounds for sensory-sensitive children. Adjust pacing.
5. **One-time sound library:** ~35 audio files cover all 12 modules forever. Each new module beyond 12 costs exactly one TTS generation.

---

## PART 2: SCHEMA ADDITIONS

### 2.1 Changes to Module JSON

The existing `guidedAudioRef` field is **preserved for backward compatibility** (it can point to a pre-baked mix for v1 fallback). Two new fields are added:

```typescript
// Existing field (unchanged)
guidedAudioRef: string;  // "audio/guided/m2.mp3" — fallback single file

// New fields
phaseBVoiceStem: string; // "audio/stems/m2_voice.mp3" — isolated voice
phaseBMixConfig: PhaseBMixConfig; // mixing instructions
```

### 2.2 PhaseBMixConfig Schema

```typescript
interface PhaseBMixConfig {
  // Domain determines ambient bed + shimmer tinting
  domain: "calm" | "focus" | "heart" | "brave" | "grounding" | "rest";

  // Total duration of voice stem in seconds (for player timing)
  voiceDurationSeconds: number;

  // Ambient bed behavior
  ambient: {
    // Fade in X seconds before voice starts
    fadeInLeadSeconds: number;  // default: 3
    // Volume relative to voice (0.0 - 1.0)
    volume: number;             // default: 0.08 (lowered from 0.15 — Feb 24 production testing)
  };

  // Ordered list of cue points synchronized to voice stem
  cuePoints: CuePoint[];
}
```

### 2.3 CuePoint Schema

```typescript
interface CuePoint {
  // Seconds into the voice stem when this cue fires
  time: number;

  // What kind of sonic event to trigger
  type: CueType;

  // Which cycle this belongs to (for progressive scaling)
  // null for non-cyclical cues
  cycle?: number;

  // Total cycles in the module (for calculating progression)
  // Only needed on the first cue point that has a cycle value
  totalCycles?: number;

  // Duration hint in seconds (for tones that need to sustain)
  // null for instantaneous sounds (shimmers, strikes)
  durationSeconds?: number;

  // Optional override for specific modules with unusual needs
  volumeOverride?: number;  // 0.0 - 1.0, overrides default for this type
}
```

### 2.4 CueType Enum — Complete Definition

```typescript
type CueType =
  // ─── UNIVERSAL (all modules) ───────────────────────────
  | "phaseStart"        // Transition bell
  | "landing"           // Landing shimmer
  | "exit"              // Signal to begin fade to Rescue

  // ─── BREATHING (M1, M2) ───────────────────────────────
  | "inhale"            // Rising breath-sync tone
  | "hold"              // Sustained breath-sync tone (M2 only)
  | "exhale"            // Descending breath-sync tone
  | "cycleEnd"          // Exhale shimmer (progressive)

  // ─── OBSERVATION (M3, M13) ────────────────────────────
  | "spacer"            // Extended silence — ambient only
  | "noticing"          // Gentle awareness marker tone

  // ─── SINGING BOWL (M4) ───────────────────────────────
  | "bowlStrike"        // Singing bowl ring + decay

  // ─── EXPANSION (M5) ──────────────────────────────────
  | "warmthSelf"        // Warmth tone — inner (smallest)
  | "warmthLoved"       // Warmth tone — expanding
  | "warmthDifficult"   // Warmth tone — widest expansion

  // ─── STEP PROCESS (M6, M8) ───────────────────────────
  | "stepTransition"    // Soft marker between process steps
  | "containment"       // Satisfying closing/sealing sound (M8)

  // ─── TENSION ARC (M7) ────────────────────────────────
  | "tensionRise"       // Gradually ascending tension tone
  | "tensionPeak"       // Brief intensity peak
  | "tensionFall"       // Resolving descent

  // ─── BODY AWARENESS (M9, M11, M12) ──────────────────
  | "senseShift"        // Attention shifts between senses (M9)
  | "bodyRegionShift"   // Attention moves to new body area (M12)
  | "squeeze"           // Tension/squeeze tone (M11)
  | "release"           // Release/opening tone (M11)
  ;
```

---

## PART 3: SOUND LIBRARY MANIFEST

### 3.1 Universal Sounds

| ID | File | Description | Duration | Used By |
|---|---|---|---|---|
| `bell_transition` | `lib/universal/bell_transition.wav` | Resonant singing bowl strike, warm decay | 5s | All 12 modules |
| `shimmer_landing_calm` | `lib/shimmers/landing_calm.wav` | Landing shimmer, warm tint | 2s | M1, M2 |
| `shimmer_landing_focus` | `lib/shimmers/landing_focus.wav` | Landing shimmer, clean tint | 2s | M3, M4 |
| `shimmer_landing_heart` | `lib/shimmers/landing_heart.wav` | Landing shimmer, rich tint | 2s | M5, M6 |
| `shimmer_landing_brave` | `lib/shimmers/landing_brave.wav` | Landing shimmer, grounded tint | 2s | M7, M8 |
| `shimmer_landing_grounding` | `lib/shimmers/landing_grounding.wav` | Landing shimmer, earthy tint | 2s | M9, M11 |
| `shimmer_landing_rest` | `lib/shimmers/landing_rest.wav` | Landing shimmer, softest tint | 2s | M12, M13 |

### 3.2 Ambient Beds (one per domain, looping)

| ID | File | Character | Duration |
|---|---|---|---|
| `bed_calm` | `lib/beds/calm.wav` | Warm golden pad, D major, minimal movement | 30s loop |
| `bed_focus` | `lib/beds/focus.wav` | Clear sky, higher register, spacious silence | 30s loop |
| `bed_heart` | `lib/beds/heart.wav` | Warmest palette, rich/full, subtle pulse | 30s loop |
| `bed_brave` | `lib/beds/brave.wav` | Grounded, low anchor, steady presence | 30s loop |
| `bed_grounding` | `lib/beds/grounding.wav` | Most physical, earth tones, sub-bass | 30s loop |
| `bed_rest` | `lib/beds/rest.wav` | Quietest, slow low pad, vast silence | 30s loop |

### 3.3 Breathing Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `breath_inhale` | `lib/breath/inhale.wav` | Gentle rising tone, warm sine quality | 5s |
| `breath_hold` | `lib/breath/hold.wav` | Sustained warm tone, slight bloom | 8s |
| `breath_exhale` | `lib/breath/exhale.wav` | Descending tone, breathy wind texture | 9s |
| `exhale_shimmer_1` | `lib/breath/exhale_shimmer_1.wav` | Barely-there single crystalline tone | 1s |
| `exhale_shimmer_2` | `lib/breath/exhale_shimmer_2.wav` | Two-tone gentle sparkle | 1s |
| `exhale_shimmer_3` | `lib/breath/exhale_shimmer_3.wav` | Three-four tone crystalline cascade | 1.5s |

### 3.4 Observation Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `noticing_tone` | `lib/observation/noticing.wav` | Gentle single tone, "there — you noticed" | 1.5s |

Note: `spacer` type triggers no sound — it's a player instruction to maintain ambient bed only for the specified duration. The absence of voice IS the design.

### 3.5 Singing Bowl

| ID | File | Description | Duration |
|---|---|---|---|
| `bowl_strike` | `lib/bowl/strike.wav` | Full singing bowl ring with long natural decay | 15s |

Note: M4 may need multiple bowl strikes at different volumes. The player handles volume variation; only one file needed.

### 3.6 Heart / Expansion Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `warmth_inner` | `lib/heart/warmth_inner.wav` | Warm tone, close, intimate | 3s |
| `warmth_expanding` | `lib/heart/warmth_expanding.wav` | Same tone, wider stereo, richer | 3s |
| `warmth_widest` | `lib/heart/warmth_widest.wav` | Full warmth, widest stereo spread | 3s |

### 3.7 Step Process Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `step_marker` | `lib/steps/marker.wav` | Soft transitional tone between process steps | 1.5s |
| `containment_close` | `lib/steps/containment.wav` | Satisfying closing/sealing sound — like a lid settling | 2s |

### 3.8 Tension Arc Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `tension_rise` | `lib/arc/rise.wav` | Slowly ascending tone, building presence | 10s |
| `tension_peak` | `lib/arc/peak.wav` | Brief intensity moment, then immediate softening | 2s |
| `tension_fall` | `lib/arc/fall.wav` | Resolving descent, opening, releasing | 10s |

### 3.9 Body Awareness Sounds

| ID | File | Description | Duration |
|---|---|---|---|
| `sense_shift` | `lib/body/sense_shift.wav` | Subtle attention-directing marker (distinct from step_marker — lighter, more "focus here") | 1s |
| `body_region_shift` | `lib/body/region_shift.wav` | Very subtle downward settling tone (attention moving through body) | 1s |
| `squeeze_tone` | `lib/body/squeeze.wav` | Gently tightening tone, building pressure | 4s |
| `release_tone` | `lib/body/release.wav` | Opening, releasing tone — contrast to squeeze | 3s |

### 3.10 Library Totals

| Category | Files | One-Time Production |
|---|---|---|
| Universal (bell + shimmers) | 7 | ✅ |
| Ambient beds | 6 | ✅ |
| Breathing | 6 | ✅ |
| Observation | 1 | ✅ |
| Singing bowl | 1 | ✅ |
| Heart / expansion | 3 | ✅ |
| Step process | 2 | ✅ |
| Tension arc | 3 | ✅ |
| Body awareness | 4 | ✅ |
| **TOTAL** | **33 files** | **One-time build** |

---

## PART 4: PLAYER MIXING RULES

### 4.1 Layer Architecture

The player maintains 4 audio channels that are mixed together in real-time:

```
Channel 1: VOICE STEM          — always playing, always loudest
Channel 2: AMBIENT BED          — loops continuously, domain-selected
Channel 3: FUNCTIONAL TONES     — breath tones, tension arcs, warmth tones
Channel 4: ACCENT SOUNDS        — shimmers, markers, strikes, containment
```

### 4.2 Default Volume Table

All volumes relative to voice stem (1.0):

| Channel | Default Volume | Notes |
|---|---|---|
| Voice | 1.0 | Reference — never adjusted by engine |
| Ambient bed | 0.08 | Barely perceptible texture — reduces cognitive load for children (lowered from 0.15 based on M2 production testing) |
| Functional tones | 0.10 - 0.16 | Scales with cycle progression |
| Accent sounds | 0.12 - 0.20 | Landing shimmer loudest, exhale shimmer quietest |

### 4.3 Cycle Progression Rule

When cue points have `cycle` and `totalCycles` values, the player applies progressive scaling to functional tones and accent sounds within that cycle:

```
progressionFactor = 1.0 + (cycle - 1) * 0.3 / (totalCycles - 1)

// Example for 3 cycles:
// Cycle 1: factor = 1.0  (baseline)
// Cycle 2: factor = 1.15 (+15%)
// Cycle 3: factor = 1.3  (+30%)
```

Applied to:
- Functional tone volume: `baseVolume * progressionFactor`
- Exhale shimmer selection: `cycle` value selects which variant (`exhale_shimmer_1`, `_2`, or `_3`)
- Ambient bed: subtle warmth increase — `bedVolume * (1.0 + (cycle - 1) * 0.07)` (barely perceptible)

### 4.4 Cue Type → Sound Mapping

This table defines exactly what the player does when it encounters each cue type:

```
┌───────────────────┬──────────────────────┬────────┬──────────────┬──────────────────────────────────────────┐
│ CueType           │ Library Sound        │Channel │ Base Volume  │ Behavior                                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ phaseStart        │ bell_transition      │ 4      │ 0.40         │ Play once. Start ambient bed fade-in     │
│                   │                      │        │              │ simultaneously. Voice begins after bell   │
│                   │                      │        │              │ decay (~3s).                             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ landing           │ shimmer_landing_*    │ 4      │ 0.20         │ Play domain-tinted variant once.          │
│                   │ (domain-selected)    │        │              │ Select by phaseBMixConfig.domain.        │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ exit              │ (none)               │ —      │ —            │ Begin ambient bed fade-out over 10s.     │
│                   │                      │        │              │ Rescue audio takes over.                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ inhale            │ breath_inhale        │ 3      │ 0.10         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Apply cycle progression.                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ hold              │ breath_hold          │ 3      │ 0.10         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Apply cycle progression.                 │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ exhale            │ breath_exhale        │ 3      │ 0.12         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Apply cycle progression.                 │
│                   │                      │        │              │ Slightly louder than inhale (exhale is   │
│                   │                      │        │              │ the reward).                             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ cycleEnd          │ exhale_shimmer_*     │ 4      │ 0.08         │ Select variant by cycle number:           │
│                   │ (cycle-selected)     │        │              │   cycle 1 → shimmer_1 (0.08)             │
│                   │                      │        │              │   cycle 2 → shimmer_2 (0.12)             │
│                   │                      │        │              │   cycle 3 → shimmer_3 (0.16)             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ spacer            │ (none)               │ —      │ —            │ No action. Ambient bed continues.        │
│                   │                      │        │              │ The silence IS the experience.            │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ noticing          │ noticing_tone        │ 4      │ 0.12         │ Play once. Marks the moment of           │
│                   │                      │        │              │ awareness — the skill itself.             │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ bowlStrike        │ bowl_strike          │ 3      │ 0.50         │ Play at high volume — the bowl IS        │
│                   │                      │        │              │ the meditation object. Child tracks      │
│                   │                      │        │              │ its natural decay. If cycle is set,      │
│                   │                      │        │              │ progressive volume decrease (each        │
│                   │                      │        │              │ successive strike softer — attention     │
│                   │                      │        │              │ training gets harder).                   │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ warmthSelf        │ warmth_inner         │ 3      │ 0.10         │ Play once. Intimate, close stereo.       │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ warmthLoved       │ warmth_expanding     │ 3      │ 0.13         │ Play once. Wider, warmer.                │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ warmthDifficult   │ warmth_widest        │ 3      │ 0.16         │ Play once. Widest, richest.              │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ stepTransition    │ step_marker          │ 4      │ 0.12         │ Play once. Soft boundary between         │
│                   │                      │        │              │ process steps.                           │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ containment       │ containment_close    │ 4      │ 0.18         │ Play once. The satisfying "closed"       │
│                   │                      │        │              │ moment. Slightly louder than markers     │
│                   │                      │        │              │ — this is a payoff.                      │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ tensionRise       │ tension_rise         │ 3      │ 0.10         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Gradually ascending. Volume ramps        │
│                   │                      │        │              │ from 0.10 to 0.18 over duration.         │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ tensionPeak       │ tension_peak         │ 3      │ 0.20         │ Play once. Brief intensity.              │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ tensionFall       │ tension_fall         │ 3      │ 0.18         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Gradually descending. Volume ramps       │
│                   │                      │        │              │ from 0.18 to 0.08 over duration.         │
│                   │                      │        │              │ The relief IS the therapeutic moment.     │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ senseShift        │ sense_shift          │ 4      │ 0.10         │ Play once. Very subtle.                  │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ bodyRegionShift   │ body_region_shift    │ 4      │ 0.08         │ Play once. Softest marker — attention    │
│                   │                      │        │              │ is already inward, don't interrupt.      │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ squeeze           │ squeeze_tone         │ 3      │ 0.12         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Gentle tightening quality.               │
│                   │                      │        │              │ Apply cycle progression (body region     │
│                   │                      │        │              │ cycles — each squeeze/release pair       │
│                   │                      │        │              │ goes slightly deeper).                   │
├───────────────────┼──────────────────────┼────────┼──────────────┼──────────────────────────────────────────┤
│ release           │ release_tone         │ 3      │ 0.14         │ Play, trim to durationSeconds.           │
│                   │                      │        │              │ Opening quality. Slightly louder than    │
│                   │                      │        │              │ squeeze — release is the reward.         │
│                   │                      │        │              │ Apply cycle progression.                 │
└───────────────────┴──────────────────────┴────────┴──────────────┴──────────────────────────────────────────┘
```

### 4.5 Ambient Bed Lifecycle

```
[phaseStart cue - 3s]    [phaseStart cue]              [exit cue]        [+10s]
        │                       │                           │                │
        ▼                       ▼                           ▼                ▼
   ┌─────────┐  ┌──────────────────────────────────────┐  ┌─────────┐
   │ Fade In │  │         Full Level (looping)          │  │Fade Out │
   │  3 sec  │  │                                       │  │ 10 sec  │
   └─────────┘  └──────────────────────────────────────┘  └─────────┘
                 ↑                                         ↑
           Bell strike                              Voice says "Stay
           + voice begins                           right there..."
```

The bed fades in BEFORE the voice starts (overlapping with the transition bell's decay). It loops continuously at the domain-selected volume. It begins fading out at the `exit` cue and continues fading during the Rescue transition. The Rescue stage may have its own ambient audio; the Phase B bed should be fully faded by the time Rescue audio begins.

### 4.6 Duration Trimming

Several cue types use `durationSeconds` to control how long a functional tone plays. The player trims (or time-stretches) the library sound to match:

- **If library sound is longer than `durationSeconds`:** Fade out at the specified time.
- **If library sound is shorter than `durationSeconds`:** Loop or stretch (implementation TBD — for v1, choose library sounds long enough that trimming is always the case).
- **If `durationSeconds` is null/missing:** Play the full library sound at its natural length.

### 4.7 Stereo Width (Future Enhancement)

Some cue types in the Sound Design Vision describe stereo width changes (exhale tones "opening" in the stereo field, warmth tones "expanding"). For v1, these are baked into the library sound files themselves. For v2, the player could apply real-time stereo width automation — but this is not required for launch.

---

## PART 5: WORKED EXAMPLES

### 5.1 Module 1 — Belly Breathing (Calm, Breathing)

```json
{
  "moduleId": "belly_breathing",
  "phaseBVoiceStem": "audio/stems/m1_belly_breathing_voice.mp3",
  "phaseBMixConfig": {
    "domain": "calm",
    "voiceDurationSeconds": 95,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 25,   "type": "inhale",   "cycle": 1, "totalCycles": 4, "durationSeconds": 4 },
      { "time": 32,   "type": "exhale",   "cycle": 1, "durationSeconds": 6 },

      { "time": 54,   "type": "inhale",   "cycle": 2, "durationSeconds": 3 },
      { "time": 59,   "type": "exhale",   "cycle": 2, "durationSeconds": 4 },

      { "time": 69,   "type": "inhale",   "cycle": 3, "durationSeconds": 3 },
      { "time": 74,   "type": "exhale",   "cycle": 3, "durationSeconds": 4 },

      { "time": 84,   "type": "inhale",   "cycle": 4, "durationSeconds": 3 },
      { "time": 89,   "type": "exhale",   "cycle": 4, "durationSeconds": 4 },
      { "time": 93,   "type": "cycleEnd", "cycle": 4 },

      { "time": 94,   "type": "landing" },
      { "time": 98,   "type": "exit" }
    ]
  }
}
```

**What the player does:**
1. At time -3s: Starts `bed_calm` fade-in + plays `bell_transition`
2. At time 0s: Voice begins
3. Times 25-93: Plays `breath_inhale` and `breath_exhale` with progressive volume scaling across 4 cycles. Cycle 4 exhale shimmer (`exhale_shimmer_3`) plays at the final `cycleEnd`.
4. Time 94: Plays `shimmer_landing_calm`
5. Time 98: Begins `bed_calm` fade-out over 10s

### 5.2 Module 2 — 4-7-8 Calm Down (Calm, Breathing + Hold)

```json
{
  "moduleId": "calm_down_478",
  "phaseBVoiceStem": "audio/stems/m2_calm_down_voice.mp3",
  "phaseBMixConfig": {
    "domain": "calm",
    "voiceDurationSeconds": 115,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 22,   "type": "inhale",   "cycle": 1, "totalCycles": 3, "durationSeconds": 4 },
      { "time": 26,   "type": "hold",     "cycle": 1, "durationSeconds": 7 },
      { "time": 34,   "type": "exhale",   "cycle": 1, "durationSeconds": 8 },
      { "time": 43,   "type": "cycleEnd", "cycle": 1 },

      { "time": 48,   "type": "inhale",   "cycle": 2, "durationSeconds": 4 },
      { "time": 52,   "type": "hold",     "cycle": 2, "durationSeconds": 7 },
      { "time": 60,   "type": "exhale",   "cycle": 2, "durationSeconds": 8 },
      { "time": 69,   "type": "cycleEnd", "cycle": 2 },

      { "time": 75,   "type": "inhale",   "cycle": 3, "durationSeconds": 5 },
      { "time": 80,   "type": "hold",     "cycle": 3, "durationSeconds": 9 },
      { "time": 89,   "type": "exhale",   "cycle": 3, "durationSeconds": 10 },
      { "time": 100,  "type": "cycleEnd", "cycle": 3 },

      { "time": 106,  "type": "landing" },
      { "time": 111,  "type": "exit" }
    ]
  }
}
```

### 5.3 Module 3 — Thought Clouds (Focus, Observation)

Completely different pattern — long silences, noticing markers, no breathing.

```json
{
  "moduleId": "thought_clouds",
  "phaseBVoiceStem": "audio/stems/m3_thought_clouds_voice.mp3",
  "phaseBMixConfig": {
    "domain": "focus",
    "voiceDurationSeconds": 100,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.12
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 18,   "type": "spacer",   "durationSeconds": 8 },
      { "time": 28,   "type": "noticing" },

      { "time": 38,   "type": "spacer",   "durationSeconds": 10 },
      { "time": 50,   "type": "noticing" },

      { "time": 60,   "type": "spacer",   "durationSeconds": 12 },
      { "time": 74,   "type": "noticing" },

      { "time": 85,   "type": "spacer",   "durationSeconds": 6 },

      { "time": 93,   "type": "landing" },
      { "time": 98,   "type": "exit" }
    ]
  }
}
```

**What the player does differently:**
No breathing tones. No cycle progression. The ambient bed carries more weight here — it IS the sonic world the child is observing in. The `noticing` markers are tiny gentle tones that say "there — you just watched one go by." The `spacer` cues are instructions to the player: do nothing here, let the silence work.

### 5.4 Module 7 — Brave Steps (Brave, Tension Arc)

```json
{
  "moduleId": "brave_steps",
  "phaseBVoiceStem": "audio/stems/m7_brave_steps_voice.mp3",
  "phaseBMixConfig": {
    "domain": "brave",
    "voiceDurationSeconds": 105,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 20,   "type": "tensionRise",  "durationSeconds": 20 },
      { "time": 40,   "type": "tensionPeak" },
      { "time": 42,   "type": "tensionFall",  "durationSeconds": 25 },

      { "time": 75,   "type": "spacer",       "durationSeconds": 10 },

      { "time": 90,   "type": "landing" },
      { "time": 100,  "type": "exit" }
    ]
  }
}
```

**What the player does:** The tension arc tones create a physical sonic representation of the anxiety wave — rising, peaking, falling. The child hears/feels the wave in the sound environment while the voice narrates staying present with it. After the fall, a spacer lets the child sit with the calm that comes after.

### 5.5 Module 10 — Squeeze & Release (Grounding, Body Cycles)

```json
{
  "moduleId": "squeeze_release",
  "phaseBVoiceStem": "audio/stems/m10_squeeze_release_voice.mp3",
  "phaseBMixConfig": {
    "domain": "grounding",
    "voiceDurationSeconds": 110,
    "ambient": {
      "fadeInLeadSeconds": 3,
      "volume": 0.08
    },
    "cuePoints": [
      { "time": 0,    "type": "phaseStart" },

      { "time": 15,   "type": "squeeze", "cycle": 1, "totalCycles": 4, "durationSeconds": 5 },
      { "time": 20,   "type": "release", "cycle": 1, "durationSeconds": 4 },

      { "time": 32,   "type": "squeeze", "cycle": 2, "durationSeconds": 5 },
      { "time": 37,   "type": "release", "cycle": 2, "durationSeconds": 4 },

      { "time": 52,   "type": "squeeze", "cycle": 3, "durationSeconds": 5 },
      { "time": 57,   "type": "release", "cycle": 3, "durationSeconds": 4 },

      { "time": 72,   "type": "squeeze", "cycle": 4, "durationSeconds": 5 },
      { "time": 77,   "type": "release", "cycle": 4, "durationSeconds": 4 },

      { "time": 95,   "type": "landing" },
      { "time": 105,  "type": "exit" }
    ]
  }
}
```

---

## PART 6: AUTOMATED MODULE GENERATION PIPELINE

### 6.1 How a New Module Gets Its Phase B Audio — Zero Manual Work

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: AI writes Phase B script                                 │
│         (following PHASE_B_PRODUCTION_PROCESS)                   │
│         Output: Markdown script with 7 sections                  │
│                                                                  │
│ Step 2: Script → ElevenLabs TTS                                  │
│         Input: Script text + selected voice ID                   │
│         Output: voice_stem.mp3                                   │
│                                                                  │
│ Step 3: AI generates cue points                                  │
│         Input: Script text + module metadata (domain, technique) │
│         Method: Pattern matching on script content               │
│         Output: cuePoints[] array with timestamps                │
│                                                                  │
│ Step 4: AI writes phaseBMixConfig                                │
│         Input: Module domain + cuePoints + voice duration        │
│         Output: Complete JSON config                             │
│                                                                  │
│ Step 5: Done.                                                    │
│         Player engine handles the rest at runtime.               │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 Cue Point Identification Rules

The AI identifies cue points by recognizing patterns in the script text. These rules are deterministic enough for automated extraction:

| Script Pattern | CueType | Timestamp |
|---|---|---|
| Start of script | `phaseStart` | 0 |
| "Breathe in..." / "In..." (breathing context) | `inhale` | At phrase onset |
| "Keep the air inside..." / "Hold..." | `hold` | At phrase onset |
| "Let it out..." / "And out..." / "Breathe out..." | `exhale` | At phrase onset |
| End of exhale in a counting/breathing sequence | `cycleEnd` | At cycle completion |
| Extended gap between voice segments (>5s) | `spacer` | At gap onset |
| "notice" / "watch" / "there" (observation context) | `noticing` | At phrase onset |
| "[singing bowl]" / "[bowl strike]" (stage direction) | `bowlStrike` | At direction |
| "send that warmth to yourself" / "to your own heart" | `warmthSelf` | At phrase onset |
| "someone you love" / "someone who makes you smile" | `warmthLoved` | At phrase onset |
| "someone you're having trouble with" | `warmthDifficult` | At phrase onset |
| Step boundary in a process ("Now..." / "Next...") | `stepTransition` | At phrase onset |
| "close the lid" / "put them in" / "seal it" | `containment` | At phrase onset |
| Rising anxiety description / "feel it building" | `tensionRise` | At phrase onset |
| Peak / "right there at the top" | `tensionPeak` | At phrase onset |
| "coming down" / "wave falling" / "it passes" | `tensionFall` | At phrase onset |
| "what can you see" / "what do you hear" (new sense) | `senseShift` | At phrase onset |
| "now move to your..." (new body area) | `bodyRegionShift` | At phrase onset |
| "squeeze" / "tighten" / "make a fist" | `squeeze` | At phrase onset |
| "release" / "let go" / "soften" | `release` | At phrase onset |
| "that's your magic" / "that's the spell" | `landing` | At phrase onset |
| "Stay right there" / final phrase | `exit` | At phrase onset |

**⚠️ DISAMBIGUATION RULE (added v1.1):** Many of these pattern words appear multiple times in a typical script — some as descriptive mentions, some as actual cue instructions. For example, "breathe" may appear in "the long breath out is where the magic is" (descriptive) AND in "Breathe in... 2, 3, 4" (actual instruction). Pattern matching MUST use script-level audio cue markers (`{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, etc.) to identify which occurrence is the actual cue. See Audio Assembly Guide §2.2.1 for the full disambiguation rule and §2.2.2 for the cue marker spec. Failure to disambiguate caused an 8-second timing error in M2 production.

### 6.3 Timestamp Extraction (Proven Method)

**Primary method (proven in M2 production):** Run vosk speech-to-text on the voice stem with word-level timestamps enabled (`SetWords(True)`). This returns the exact start/end time of every spoken word. Combined with script-level cue markers for disambiguation, this provides sub-second accuracy with zero human input.

**Tool:** Vosk (`pip install vosk` + `vosk-model-small-en-us-0.15`). Free, offline, no API cost. See Audio Assembly Guide §2.2 for the complete pipeline and code.

**Alternative:** ElevenLabs `with_timestamps` parameter on TTS generation, which returns word timestamps at generation time. Not yet tested in production but architecturally equivalent.

**Fallback for prototyping only:** Timestamps can be estimated from script text using speaking rate (~2 words/second for narration, ~1 count/second for breathing counts). These estimates are useful for rough planning but MUST NOT be used for final tone placement — they were consistently off by 5-10 seconds in practice.

**⚠️ NEVER use waveform energy analysis to guess which speech segment corresponds to which word.** This approach cannot distinguish between words and was the root cause of the M2 timing failure.

---

## PART 7: TECHNICAL IMPLEMENTATION NOTES

### 7.1 Web Audio API (Browser)

The module player uses the Web Audio API for real-time mixing:

```javascript
// Simplified architecture
const audioContext = new AudioContext();

// Channel nodes
const voiceGain = audioContext.createGain();     // Channel 1
const ambientGain = audioContext.createGain();   // Channel 2
const tonesGain = audioContext.createGain();     // Channel 3
const accentsGain = audioContext.createGain();   // Channel 4

// All channels → master output
[voiceGain, ambientGain, tonesGain, accentsGain]
  .forEach(g => g.connect(audioContext.destination));

// Set default volumes
voiceGain.gain.value = 1.0;
ambientGain.gain.value = 0.08;
tonesGain.gain.value = 0.10;
accentsGain.gain.value = 0.12;
```

### 7.2 Cue Point Scheduling

```javascript
// Schedule cue points relative to voice stem start
function scheduleCuePoints(cuePoints, voiceStartTime) {
  cuePoints.forEach(cue => {
    const triggerTime = voiceStartTime + cue.time;

    switch (cue.type) {
      case 'phaseStart':
        playSound('bell_transition', accentsGain, triggerTime, 0.40);
        startAmbientBed(triggerTime);
        break;

      case 'inhale':
        const vol = applyProgression(0.10, cue.cycle, cue.totalCycles);
        playSoundTrimmed('breath_inhale', tonesGain, triggerTime,
                         vol, cue.durationSeconds);
        break;

      case 'cycleEnd':
        const shimmerVariant = `exhale_shimmer_${cue.cycle}`;
        const shimmerVol = [0.08, 0.12, 0.16][cue.cycle - 1];
        playSound(shimmerVariant, accentsGain, triggerTime, shimmerVol);
        break;

      case 'landing':
        const domainShimmer = `shimmer_landing_${config.domain}`;
        playSound(domainShimmer, accentsGain, triggerTime, 0.20);
        break;

      case 'exit':
        fadeOutAmbient(triggerTime, 10); // 10s fade
        break;

      // ... other types
    }
  });
}
```

### 7.3 Fallback Strategy

If the player environment doesn't support multi-channel mixing (e.g., very old devices), fall back to `guidedAudioRef` — the pre-baked single-file mix. This means:

- For the 12 seed modules, produce BOTH a pre-baked mix (using the ElevenLabs recipe) AND the dynamic mix config
- For AI-generated modules beyond 12, pre-baked mixes can be generated offline as a batch process
- The player checks device capability and chooses the appropriate strategy

### 7.4 Preloading

All 33 library sounds should be preloaded when the app starts (total size estimate: ~5-8 MB). Per-module, only the voice stem needs to be fetched at module load time.

---

## PART 8: RELATIONSHIP TO EXISTING DOCUMENTS

| Document | Relationship |
|---|---|
| Canonical Data Model | Add `phaseBVoiceStem` and `phaseBMixConfig` to modules collection |
| Module JSON Schema Guardrails | `guidedAudioRef` preserved as fallback; new fields extend Phase B audio capability |
| Sound Design Vision (Part 1 of this document) | This architecture IMPLEMENTS the vision. Domain palettes, three-layer architecture, classical conditioning principles — all realized through the cue point system |
| Phase B Sound Production Brief | The brief becomes the recipe for building the 33-file sound library. The per-module cue sheets become unnecessary (replaced by `cuePoints[]` in the JSON) |
| ElevenLabs Sound Recipe v1 | Used to produce the 33 library files. After that, only Step 1 (voice generation) is needed per module |
| Phase B Production Process v1.1 | Step 9 (production assembly) is automated by this engine. Steps 1-8 (script creation) remain human/AI-authored |

---

## PART 9: PRODUCTION SEQUENCE

### Phase 1: Build the Sound Library (one-time)
Use the ElevenLabs Sound Recipe to produce all 33 library files. Priority order:
1. Universal sounds (bell, landing shimmers) — used by all 12 modules
2. Calm domain bed — needed for M1 and M2 (already locked)
3. Breathing sounds — needed for M1 and M2
4. Focus domain bed + observation sounds — needed for M3 and M4
5. Remaining domain beds and functional sounds — as scripts are produced

### Phase 2: Implement the Player Audio Engine
Build the 4-channel mixer, cue point scheduler, and ambient bed lifecycle. Test with M1 and M2 configs against the locked voice stems.

### Phase 3: Produce Voice Stems for Modules 1-2
Use ElevenLabs TTS with the locked M1 and M2 scripts. Generate cue point configs.

### Phase 4: Validate
Does M1 sound like the M1 we imagined? Does the transition bell → ambient bed → breath tones → exhale shimmer → landing shimmer → fade-out sequence feel magical, safe, and effective? Adjust library sounds and volumes until it does.

### Phase 5: Scale
As each module's Phase B script is produced, generate voice stem + cue point config. The library and player already exist. Each new module costs one TTS generation + one JSON config — maybe 30 minutes of work.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial architecture. 23 cue types covering all 12 module patterns. 33-file sound library manifest. 4-channel player mixing rules with cycle progression. 5 worked examples spanning breathing, observation, tension arc, and body cycle patterns. Automated pipeline from script to playable module. Schema additions for phaseBVoiceStem and phaseBMixConfig. |
| 1.1 | February 24, 2026 | §6.2: Added disambiguation warning — cue words appear multiple times in scripts, must use script-level cue markers to identify correct occurrence. §6.3: Rewritten — vosk STT is now the proven timestamp extraction method (tested in M2 production). Waveform energy analysis explicitly deprecated. ElevenLabs Forced Alignment listed as untested alternative. Ambient bed default volume lowered from 0.15 to 0.08 in schema, volume table, and code examples (based on M2 production testing). |

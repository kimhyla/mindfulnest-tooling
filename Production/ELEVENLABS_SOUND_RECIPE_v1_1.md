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

# STEP 1a: PERSONALIZED STEM GENERATION (Per-Child)

For modules where the Phase B script contains `{childName}`, generate per-child audio segments:

1. **Identify personalized lines.** Only the opening line ("Now, {childName}, hold your hands out...") and closing line ("Well done, {childName}.") contain variables. The meditation body is universal.
2. **Resolve variables.** Replace `{childName}` with the child's actual name.
3. **Generate via ElevenLabs** using the same Myrrhin voice settings from Step 1 (stability, clarity, style exaggeration — all identical).
4. **Store per-child segments** at `audio/children/{childId}/m{X}_phaseB_opening.mp3` and `m{X}_phaseB_closing.mp3`.
5. **Cue points are NOT recalculated.** Because `{childName}` appears only in the opening/closing (outside the cue point range), universal cue points from the standard stem apply to all children.

**Cost:** ~80 characters per module per child × $0.18/1000 chars = ~$0.014 per module per child. For all 54 modules: ~$0.78 per child.

**Trigger:** Pre-cache at module unlock. When a child completes a module and the next module unlocks, generate the personalized opening/closing segments in the background.

See `TTS_PERSONALIZATION_PIPELINE_v1.md` §4 and §6 for the full rendering strategy and cost model.

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

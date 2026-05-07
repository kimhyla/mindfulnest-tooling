# Phase B Sound Production Brief
## Calm Domain Prototype — Modules 1 & 2
### Version 1.2 — March 9, 2026

---

## PART 1: PROJECT CONTEXT

### What Is MindfulNest?
A therapeutic mindfulness app for children ages 7-10. Each of ~54 modules teaches a real clinical technique (belly breathing, cognitive defusion, progressive muscle relaxation, etc.) disguised as magical training in a fantasy world called Everdale. The app's primary customers are child therapists who assign modules to young patients as between-session tools.

### What Is Phase B?
Each module has two phases. Phase A is an interactive tutorial where the child watches a magical creature learn a skill — a visual, gamified experience with narration from a "Guide Bird" character. Phase B is the actual guided meditation — the child closes their eyes, and a different voice (the meditation narrator) guides them through the real practice.

Phase B is the most intimate moment in the app: a child alone with a warm voice, doing something new with their body and mind. Everything in this brief exists to make that moment feel magical, safe, and effective.

### Why Sound Design Matters Here
When the child closes their eyes, the screen disappears. What remains is voice and sound. The sound design must:

1. Make the meditation feel like casting a spell in Everdale — not like a clinical exercise
2. Support the therapeutic mechanism without competing for the child's attention
3. Create a sonic signature that becomes a conditioned relaxation cue over time (the sound itself eventually triggers partial calming — this is clinically real and intentional)

### What We're Building First
The Calm domain (Modules 1 & 2) as a complete prototype. This establishes the production pipeline and quality bar for all subsequent modules.

---

## PART 2: THE THREE LAYERS

Every Phase B meditation is built from three simultaneous sonic layers:

```
┌─────────────────────────────────────────┐
│  LAYER 1: VOICE (foreground)            │  ← The meditation narrator
│  ─────────────────────────────────────  │     Carries the script
│  LAYER 3: FUNCTIONAL SOUNDS (accents)   │  ← Brief purposeful sounds
│  ─────────────────────────────────────  │     Sync to script moments
│  LAYER 2: AMBIENT BED (background)      │  ← Continuous evolving texture
│                                         │     Creates "being somewhere"
└─────────────────────────────────────────┘
```

**Relative levels (approximate):**
- Voice: 0 dB (reference — always the loudest and clearest)
- Functional sounds: -12 to -18 dB (felt as much as heard)
- Ambient bed: -18 to -24 dB (enveloping but never competing)

These are starting points. The ear is the final judge — the voice must always sit clearly on top with zero masking.

---

## PART 3: LAYER 1 — VOICE PRODUCTION

### 3.1 The Character
The meditation narrator is a distinct character from the Guide Bird (who narrates Phase A). When the transition cue says "Listen to the voice on the wind..." a new presence arrives. This voice is:

- **Warm, wise, unhurried** — a beloved grandparent sitting beside the child
- **Gender-neutral warmth** — not gendered unless using the personalization variant ("young man" / "young lady")
- **Present and alive** — not a meditation app robot, not a breathy whisper, not affect-flat
- **Unprocessed** — no reverb, no effects on the voice itself (the ambient bed provides the "space")

### 3.2 Platform: ElevenLabs
**Why ElevenLabs:** High-quality AI voice synthesis with controllable warmth, pacing, and emotional tone. Allows rapid iteration on script delivery without booking voice talent for every revision.

**Voice selection approach:**
1. Test 3-4 voices from ElevenLabs' library against a 30-second excerpt from M1 (the Instruction section — the most demanding passage)
2. Evaluate on: warmth, clarity, pacing naturalness, ability to sound unhurried without sounding sleepy
3. Select one voice for all modules (consistency builds relationship)
4. Fine-tune with ElevenLabs' voice settings: stability (mid-high for consistency), similarity boost (high to maintain character), style (moderate — enough personality without overacting)

**Selected voice (LOCKED):**
- Voice name: **Myrrdin**
- Voice ID: `oR4uRy4fHDUGGISL0Rev`
- Model: Eleven Multilingual v2
- This voice is the conditioned safety cue. After repeated sessions, the child's nervous system associates Myrrdin's voice with safety and settling. Do NOT use any voice other than Myrrdin for any Phase B narration.

**Voice generation workflow per module:**
1. Input the full script with pause markers (see timing cue sheets below)
2. Generate with breathing-pace timing (~2 words/second for spoken content, ~1 count/second for M2 counting)
3. Export as isolated voice stem (48kHz/24bit WAV, mono)
4. Quality check: Is it warm? Is it clear? Does it sound like someone who cares about this child?
5. If needed, regenerate individual sections and splice

**ElevenLabs pricing estimate:**
- ~175 words per module × 12 modules = ~2,100 words total
- At current ElevenLabs pricing (Pro plan ~$22/month): well within limits
- Multiple regenerations for quality: budget 5-10x the raw word count = ~10,000-20,000 characters
- Total voice cost: effectively negligible ($22-99/month during production)

**Pause encoding:** ElevenLabs supports SSML-like pause control. Use these markers in the script input:

```
Breathe in slowly through your nose... <break time="3s"/> 
and feel your belly push your hand up. <break time="1s"/>
Now let it out... <break time="1s"/> nice and slow... <break time="4s"/>
and feel your belly come back down.
```

The exact pause durations are specified in the timing cue sheets (Part 6).

### 3.3 Gender Personalization
The Welcome line has a gender variant: "young man" / "young lady" from the child's profile. This means generating two versions of the Welcome section per module, with the rest of the script identical. The app selects the correct variant at runtime.

**Production:** Generate 3 Welcome variants per module:
1. Neutral (no gendered address): "Ahh... you've come to learn the magic of Calm. Good."
2. Male: "Ahh... welcome, young man. You've come to learn the magic of Calm. Good."
3. Female: "Ahh... welcome, young lady. You've come to learn the magic of Calm. Good."

---

## PART 4: LAYER 2 — AMBIENT BED

### 4.1 Calm Domain Palette

**Core feeling:** Warm bath. Safe cocoon. Settling.

**Sonic elements:**
- **Foundation:** Warm pad in the lower-mid register. Think sustained cello-like tone, but synthesized — organic character, not cold digital. Root note: suggest D3 or Eb3 (warm, not too low for small speakers, not too high to feel cerebral). Extremely slow chord movement — no faster than one harmonic shift per 30-60 seconds.
- **Texture layer:** Very subtle air/breath texture underneath. Not wind — closer to the sound of a room being still. The sonic equivalent of dust motes in warm light. This should be barely perceptible — remove it and you notice something is missing, but you can't identify what.
- **Harmonic movement:** Chords shift in thirds or fifths — nothing dissonant, nothing surprising. The harmony should feel inevitable, like settling into a warm bed. Suggested progression over a full 2-minute span: I → III → IV → I (in D: Dmaj → F#min/A → Gmaj → Dmaj). Extremely slow. Each chord melts into the next over 15-20 seconds.
- **Evolution:** The bed is slightly sparser at the beginning and very subtly warmer/richer by the end. This mirrors the child's journey: they arrive uncertain and leave settled. The bed "settles" with them. Specifically: the texture layer gains ~2-3 dB of warmth over the full duration. Not noticeable moment-to-moment, but the end feels different from the start.
- **What it is NOT:** No melody (nothing hummable). No percussion or pulse (the child's breath is the only rhythm). No nature sounds (Calm domain is internal, not environmental). No bell tones (those belong in Layer 3). No minor keys (this is safety, not melancholy).

### 4.2 M1 vs. M2 Differentiation

Both modules use the Calm palette, but with different emphasis:

**M1 (Belly Breathing) — "Being Held"**
- The sparest, simplest bed in the entire app. This is the child's first meditation.
- Foundation pad only, with minimal texture layer
- Almost no harmonic movement — one or two very slow shifts across the full 90 seconds
- Think: the sonic equivalent of a single candle in a quiet room
- The simplicity IS the design — there's nothing to process, nothing to track, just warmth

**M2 (4-7-8 Calm Down) — "The Spell Working"**
- Richer than M1 — the child is ready for more, and the technique is more structured
- Foundation pad plus a slightly more present texture layer
- The key differentiator: **subtle tonal movement that follows the 4-7-8 cycle**
  - During inhale counts (4s): the bed's pitch very subtly rises (~1 semitone, almost imperceptible)
  - During hold counts (7s): the bed sustains at its peak — warm and full
  - During exhale counts (8s): the bed descends and opens — the harmonics spread slightly wider in the stereo field
  - This creates a breathing feeling in the ambient bed itself — the world breathes with the child
- **Cross-cycle evolution:** Each cycle, the exhale bloom gets slightly warmer. By Cycle 3, the exhale is audibly (but still subtly) richer than Cycle 1. The child's practice is literally making the sonic world more beautiful.

### 4.3 Production Specifications

| Attribute | Specification |
|---|---|
| Format | 48kHz / 24bit WAV, stereo |
| Duration | 2:30 per module (trim to match final voice timing) |
| Stereo width | Moderate — wider than mono but not extreme LR panning (children often use device speakers, not headphones) |
| Low-frequency content | Roll off below 80Hz (most children's devices can't reproduce sub-bass; wasted energy causes muddiness) |
| High-frequency content | Gentle presence above 8kHz but nothing harsh. The bed should feel warm, not bright. |
| Dynamic range | Very compressed — no more than 3-4 dB of dynamic variation. The bed should be a consistent blanket, not a dynamic experience. |
| Fade in | 3-5 seconds from silence to full level. Begins BEFORE the voice starts (during the transition bell decay). |
| Fade out | No hard fade. The bed continues at level through the Exit section and into Rescue. It fades out during the Rescue stage (handled by the app's audio engine, not baked into the file). |

### 4.4 Tools and Platforms for Ambient Production

**Option A: Custom production in DAW (Highest quality, most control)**
- **Tools:** Ableton Live, Logic Pro, or Reaper
- **Synths:** Omnisphere (vast warm pad library), Valhalla Shimmer (ethereal reverb textures), Spitfire LABS (free, excellent pads), Native Instruments Pharlight (textural), Arturia Analog Lab (warm analog character)
- **Workflow:** Build each domain palette as a synth preset chain, then record 2:30 of real-time performance with slow automation for harmonic movement and evolution
- **Cost:** $0 if you have a DAW + free plugins (LABS, Vital, Surge); $200-500 if purchasing Omnisphere or similar
- **Skill required:** Intermediate music production
- **Recommended for:** If Kim or a collaborator has DAW experience

**Option B: Commission an ambient producer ($200-500 per domain)**
- **Brief:** Hand this document to the producer. They deliver stems per the spec.
- **Where to find:** SoundBetter, Fiverr Pro, or targeted outreach to ambient music artists on Bandcamp
- **What to send them:** This document (Part 4 specifically) + the M1 and M2 voice stems as timing references
- **Cost:** ~$200-500 per domain × 6 domains = $1,200-3,000. Calm domain is the first deliverable; remaining 5 domains commissioned after prototype is validated.
- **Recommended for:** Best quality-to-effort ratio

**Option C: AI music generation (Experimental)**
- **Tools:** Suno, Udio, Stable Audio
- **Approach:** Generate ambient bed candidates from text descriptions ("warm ambient pad, D major, extremely slow, no melody, no percussion, cello-like warmth, 2 minutes")
- **Challenge:** Quality control. AI generators tend toward melody and structure — getting truly non-melodic, evolving texture is difficult. Expect to generate 20-30 candidates and maybe find 2-3 usable ones.
- **Cost:** $10-30/month subscription
- **Recommended for:** Quick prototyping / proof of concept only. Not recommended for final production.

**Option D: Stock ambient libraries with custom layering**
- **Sources:** Artlist, Epidemic Sound, Musicbed — search for "ambient texture," "warm drone," "meditation bed"
- **Challenge:** Finding non-melodic, non-structured pieces that fit the specific palette. Most "meditation music" is too melodic and too structured for our purposes.
- **Cost:** $15-30/month subscription + time to search and edit
- **Recommended for:** Budget-constrained prototype

**Recommendation:** Option B for final production (commission a producer). Option A or D for quick prototyping if you want to hear something before committing budget.

---

## PART 5: LAYER 3 — FUNCTIONAL SOUNDS

### 5.1 Universal Elements (Used Across All 12 Modules)

#### The Transition Bell
**When it plays:** At the exact moment between Phase A and Phase B — after Bird says "Listen to the voice on the wind..." and before the meditation voice arrives. This sound IS the threshold between worlds.

**Character:** Resonant, sustained, beautiful. 3-5 seconds of decay from a clear attack to silence. Not jarring — the child's eyes are closing. Not religious — no specific cultural association. The sound of something ancient and calm awakening.

**Design direction:** A custom tone that blends singing bowl resonance with a nature-inspired quality — as if the wind itself is ringing as it passes through Everdale's ancient trees. Not a literal singing bowl (cultural baggage) and not a literal wind chime (too decorative). Something between — organic resonance with a metallic shimmer.

**Technical spec:**
- Fundamental: A4 (440Hz) or C5 (523Hz) — clear, present, works on all speaker sizes
- Sustain: 3-5 seconds of natural decay (no artificial reverb tail)
- Stereo: Slight stereo width in the decay (starts centered, spreads slightly)
- Level: Prominent but not startling. The child should feel "oh, something is beginning" not "what was that?"
- Delivery: Single WAV file, used identically in all 12 modules

**Conditioning function:** After 10-20 sessions, the child hears this bell and their body begins settling automatically — before the voice even speaks. This is the most valuable single sound in the entire design. It must be beautiful enough to hear hundreds of times without fatigue.

#### The Landing Shimmer
**When it plays:** During the Landing section — when the voice says "that's your magic" (M1) or "that's your magic now" (M2). This sound accompanies the naming moment.

**Character:** Brief (1-2 seconds), crystalline, warm. The sound of something settling into place. Like a snowflake landing. Like a key finding its lock. Not triumphant (that's Win territory) — more like a quiet "there it is."

**Design direction:** A multi-toned chime with gentle sparkle. Several high-register tones sounding almost simultaneously, then fading quickly. A tiny cascade of light.

**Technical spec:**
- Duration: 1-2 seconds total
- Frequencies: Cluster of harmonically related tones in the 1-4kHz range (present but not piercing)
- Level: -12 to -15 dB below voice (sits underneath the words, not on top)
- Domain tinting: The shimmer is 80% identical across all modules but subtly colored by domain. Calm domain shimmer is warmer (more low-mid harmonics). Focus domain shimmer is cleaner (more pure tones). Heart domain shimmer is the richest (most harmonics). This tinting is achieved through very subtle EQ/filtering on the same base sound.
- Delivery: One base WAV file + 6 domain-tinted variants (or one file + EQ settings per domain)

#### Breath-Sync Tones (Breathing Modules Only)
**When they play:** Throughout the Instruction and Deepening sections of breathing modules (M1, M2, and potentially M11, M12). They provide an auditory guide for the child's breathing even during pauses in the voice.

**Character:** Extremely subtle. The child should feel guided without consciously tracking the tones. These live at the boundary between Layer 2 (ambient) and Layer 3 (functional) — they're ambient in character but functional in purpose.

**Design:**

**Inhale tone:**
- A gentle rising tone. Starts at the beginning of the inhale instruction/pause, rises smoothly, reaches its peak at full lungs.
- Pitch: Rises ~3-4 semitones over the inhale duration (e.g., D4 → F#4). Not a dramatic swoop — a gentle lift.
- Timbre: Pure-ish sine with a touch of warmth. Think: the sound of light rising.
- Level: -18 to -22 dB below voice. You feel it more than hear it.

**Hold tone (M2 only):**
- The inhale tone sustains at its peak. A warm, held note — not tense, just present.
- Duration: Matches the hold count (7 seconds in M2)
- Slight harmonic richness added during the hold — the tone "blooms" slightly, as if the air inside is expanding.

**Exhale tone:**
- The tone descends and opens. Slightly longer and warmer than the inhale tone.
- Pitch: Descends back to the starting note, then continues down ~1-2 semitones below start (e.g., F#4 → D4 → C#4). The net downward movement gives a settling quality.
- **Texture: Breathy wind quality.** Unlike the inhale tone (which is pure/clean), the exhale tone should have a breathy, airy character — as if the child's out-breath is becoming part of the soundscape. Not a literal wind sound effect, but a tone with breath-noise layered into its timbre. Think: singing through a gentle exhale. This is the sonic signature of "letting the magic out."
- Stereo: Subtle widening during descent. The exhale "opens" in the stereo field. The breathy texture widens more than the pitched component — by the end of each exhale, the breath-texture wraps around the listener.
- **Bloom at the final count:** The exhale tone doesn't just end — it blooms. At count 8 (or the final count in M1's natural exhale), the tone briefly opens into a richer harmonic spread before fading. This is a micro-reward for completing each exhale. The bloom is subtle in Cycles 1-2 and more pronounced in the final cycle.
- The exhale tone is the most "rewarding" — it should feel like release, like calm magic flowing out of the child into Everdale.

**Cross-cycle evolution (M2):**
- Cycle 1: Tones are simple and pure
- Cycle 2: Tones gain ~10% more harmonic richness
- Cycle 3: Tones are the warmest and widest — the child's practice has made the sound world more beautiful
- This evolution is subtle. If you A/B Cycle 1 and Cycle 3 tones in isolation, you'd hear the difference. In context, it's a felt quality, not a conscious observation.

#### Per-Cycle Exhale Shimmer ("Magic Releasing")
A small crystalline shimmer that plays at the very end of each exhale — the moment the child has fully breathed out. This is distinct from the Landing Shimmer (which plays once at the naming moment). The exhale shimmer is a per-cycle micro-reward: the sound of calm magic releasing from the child into Everdale.

**Character:** Tiny, crystalline, delicate. Like a single ice crystal forming. Shorter and more subtle than the Landing Shimmer — this is a sparkle, not a chime. ~0.5-1 second.

**Evolution across cycles:**
- Cycle 1: Barely there. A single high tone that glimmers and vanishes. The child might not consciously notice it.
- Cycle 2: Slightly more present. Two tones instead of one, a hair wider in stereo.
- Cycle 3 (final exhale): The most pronounced — a brief cascade of 3-4 crystalline tones, still subtle but now unmistakably "something happened." This is the moment right before the silence that precedes "That's the spell."
- This progression tells a story the child feels but doesn't analyze: each exhale releases more magic. By the final cycle, the magic is real.

**Level:** -18 to -22 dB below voice (Cycle 1), -15 to -18 dB (Cycle 3). Always underneath, never competing.

**M1 application:** In M1 (belly breathing), the exhale shimmer plays on the final breath cycle only — a single quiet sparkle at the end of the last "and out..." before Landing. M1 is the child's first meditation; the shimmer is a surprise — a hint that something just happened.

**Relationship to Landing Shimmer:** The per-cycle exhale shimmer uses the same harmonic family as the Landing Shimmer but is smaller, briefer, and higher-pitched. Think of it as a fragment of the Landing Shimmer — a preview. When the full Landing Shimmer plays at "that's your magic," the child unconsciously recognizes it as the completed version of what they've been hearing in miniature.

**Technical spec:**
- Format: Per-cycle WAV stems (M1: 7 breath cycles × inhale/exhale pairs; M2: 3 cycles × inhale/hold/exhale sets)
- OR: Real-time synthesis in the app's audio engine (more flexible, harder to implement in v1)
- Recommendation for v1: Pre-rendered stems baked into the final mix. Simpler to produce, guaranteed timing.

### 5.2 Production Tools for Functional Sounds

**Singing bowl / bell sounds:**
- Best: Record a real singing bowl or crystal bowl (or purchase high-quality samples from Spitfire Audio, Native Instruments, or Output)
- The transition bell can be designed from a singing bowl sample processed through reverb and gentle pitch manipulation
- Budget option: Freesound.org has CC-licensed singing bowl recordings that could serve as raw material

**Shimmer / chime sounds:**
- Best: Layered from individual chime/bell samples tuned to specific pitches
- Tools: Any DAW with a sampler. Load 3-4 bell/chime samples at different pitches, trigger simultaneously with slight time offsets (10-30ms), apply gentle reverb
- Budget option: Splice or Freesound for individual chime samples

**Breath-sync tones:**
- Best: Synthesized. A simple sine/triangle oscillator with pitch automation is all that's needed.
- Tools: Any synth (even free ones like Vital or Surge). Automate pitch over the inhale/exhale duration. Add gentle low-pass filtering for warmth.
- This is the easiest element to produce — any DAW user can create these in an hour.

---

## PART 6: TIMING CUE SHEETS

These cue sheets are the production bible. They specify exactly when each sonic element enters, exits, and transitions for each module.

### 6.1 Module 1 — Belly Breathing

**Total duration:** ~85-90 seconds (with breathing synchronization)

```
TIME        VOICE CONTENT                                    AMBIENT BED          FUNCTIONAL SOUNDS
─────────── ──────────────────────────────────────────────── ──────────────────── ─────────────────────
-5s to 0s   [Silence — Phase A transition cue ending]        Fade in begins       TRANSITION BELL at -3s
                                                              (from silence)       (3-5s decay, overlaps
                                                                                    into Welcome)

0:00-0:06   WELCOME                                          Bed at full level    Bell decay finishes
            "Ahh... you've come to learn the                  M1 sparse palette    
            magic of Calm. Good."                             Foundation pad only   

0:06-0:17   CONNECTION                                       Steady               
            "You saw the breath travel all the                                     
            way down to the belly — that's where                                   
            the magic lives. Now it's your turn."                                  

0:17-0:25   SETUP                                            Steady               
            "Put your hand right on your belly.                                    
            You can feel yourself breathing in                                     
            and out. Here's what I want you to do."                                

0:25-0:61   INSTRUCTION (2 guided breath cycles)             Steady               BREATH-SYNC TONES begin
                                                                                   
0:25-0:28   "Breathe in slowly through your nose..."                               Inhale tone rises
0:28-0:32   [Inhale pause — child breathes in, ~4s]                                Tone sustains at peak
0:32-0:36   "and feel your belly push your hand up."                               Tone gently descends
0:36-0:37   [Brief pause]                                                          
0:37-0:39   "Now let it out..."                                                    Exhale tone begins
0:39-0:43   "nice and slow..."                                                     Tone descending
0:43-0:47   [Exhale continues — ~4 more seconds]                                   Tone settles
0:47-0:50   "and feel your belly come back down."                                  Exhale tone ends
0:50-0:51   [Brief pause]                                                          
0:51-0:53   "That's it. Let's do it again."                                        
0:53-0:54   [Brief pause]                                                          
0:54-0:56   "Breathe in..."                                                        Inhale tone rises
0:56-0:58   "your belly rises..."                                                  Tone at peak
0:58-0:61   "...and breathe out..."                                                Exhale tone begins
0:61-0:63   "your belly falls..."                                                  Tone descending
0:63-0:65   "nice and easy."                                                       Exhale tone settles

0:65-0:80   DEEPENING (2-3 independent breath cycles)        Bed subtly warmer    Tones continue, simpler
                                                              (+1-2 dB warmth)     
0:65-0:69   "Keep going just like that. In..."                                     Inhale tone
0:69-0:73   "and out..."                                                           Exhale tone
0:73-0:74   [Pause]                                                                
0:74-0:80   "If your brain starts thinking about                                   [No tones — spoken
            other things, that's OK. Just feel                                      content fills this
            your belly again."                                                      space]
0:80-0:84   "In... and out..."                                                     Inhale/exhale tone
0:84-0:87   "One more. Nice and slow."                                             
0:87-0:91   "In... and out..."                                                     Final inhale/exhale
                                                                                    (warmest tone)
                                                                                    EXHALE SHIMMER at
                                                                                    end of final out
                                                                                    (single sparkle)

0:91-0:96   LANDING                                          Bed at warmest       LANDING SHIMMER
            "That feeling right there..."                     point                 at "that's your magic"
            "that calm..."                                                         (1-2s, under voice)
            "that's your magic."                                                   

0:96-0:100  EXIT                                             Bed continues        Tones end
            "Stay right there. Just keep breathing."          (no fade — Rescue    
                                                              takes over)          

0:100+      [Rescue sustain — Guide Bird speaks]             Bed fades slowly     
                                                              over ~10s into       
                                                              Rescue audio         
```

**Note:** Timings are approximate. The voice stem is the timing master — all other layers sync to it. The cue sheet will be updated with exact timings once the voice stem is generated.

---

### 6.2 Module 2 — 4-7-8 Calm Down

**Total duration:** ~95-115 seconds (with breath-synchronized counting)

```
TIME        VOICE CONTENT                                    AMBIENT BED          FUNCTIONAL SOUNDS
─────────── ──────────────────────────────────────────────── ──────────────────── ─────────────────────
-5s to 0s   [Phase A transition cue ending]                  Fade in begins       TRANSITION BELL at -3s
                                                              M2 richer palette    

0:00-0:05   WELCOME                                          Bed at full level    Bell decay finishes
            "Ahh... you're back. And you're ready                                  
            for something more powerful. Good."                                    

0:05-0:14   CONNECTION                                       Steady               
            "You saw the breathing circle — 4 in,                                  
            7 hold, 8 out. The long breath out is                                  
            where the magic is. Now it's your turn."                               

0:14-0:19   SETUP                                            Steady               
            "I'm going to count for you. All you                                   
            have to do is breathe along."                                          

0:19-0:22   "Here we go."                                                         

            ─── CYCLE 1 (fully guided) ─────────                                  
0:22-0:26   "Breathe in... one... two...                                           Inhale tone rises
            three... four..."                                                      over 4 seconds

0:26-0:34   "Now keep the air inside...                      Bed sustains,        Hold tone: warm
            one... two... three... four...                    slight fullness       sustained note
            five... six... seven..."                                               at peak, 7 seconds

0:34-0:44   "And let it out, nice and slow...                Bed opens slightly   Exhale tone descends
            one... two... three... four...                    wider in stereo       over 8 seconds,
            five... six... seven... eight."                                        subtle stereo bloom.
                                                                                    EXHALE SHIMMER at
                                                                                    "eight" (barely
                                                                                    perceptible, 1 tone)

            ─── TRANSITION ─────────────────────                                  
0:44-0:48   "Good.                                            Bed steady            [Brief silence —
            Again."                                                                let the moment land]

            ─── CYCLE 2 (shorter labels) ──────                                   
0:48-0:52   "In... one... two... three... four..."                                 Inhale tone rises
                                                                                    (slightly warmer
                                                                                     than Cycle 1)

0:52-0:60   "Hold... one... two... three...                  Bed sustains         Hold tone
            four... five... six... seven..."                                       (slightly richer)

0:60-0:70   "And out... one... two... three...               Bed opens            Exhale tone descends
            four... five... six... seven...                                        (slightly wider
            eight."                                                                 bloom than Cycle 1)
                                                                                    EXHALE SHIMMER at
                                                                                    "eight" (2 tones,
                                                                                    slightly more present)

            ─── TRANSITION ─────────────────────                                  
0:70-0:73   "Can you feel it? One more."                     Bed steady            [Brief silence]

            ─── CYCLE 3 / DEEPENING (slowest) ──                                 
0:73-0:75   "Even slower this time."                                              

0:75-0:80   "In... one... two... three... four..."           Bed warmest          Inhale tone rises
            [~1.2s per count — slower pace]                   point reached         (warmest version)

0:80-0:89   "Keep it right there... one... two...            Bed full and         Hold tone
            three... four... five... six...                   sustained             (richest harmonics)
            seven..."                                                              

0:89-0:101  "And out... all the way... one...                Bed widest           Exhale tone:
            two... three... four... five...                   stereo spread         longest, warmest,
            six... seven... eight..."                                              widest bloom.
                                                                                    EXHALE SHIMMER at
                                                                                    "eight" — most
                                                                                    pronounced (3-4 tone
                                                                                    crystalline cascade).
                                                                                    The sound of calm
                                                                                    magic fully releasing.

0:101-0:104 [2-3 seconds of silence]                         Bed holds             

0:104-0:106 "That's the spell."                              Bed begins to        
                                                              settle back          

            ─── LANDING ─────────────────────────                                 
0:106-0:111 "That deep, deep calm... that rhythm...          Bed settled,         LANDING SHIMMER
            that's your magic now."                           warmest quality       at "that's your magic
                                                              maintained            now" (1-2s)

            ─── EXIT ────────────────────────────                                 
0:111-0:115 "Stay right there. Keep the rhythm               Bed continues        Tones end
            going."                                           (no fade)            

0:115+      [Rescue sustain — Guide Bird]                    Bed fades ~10s       
```

**Key mixing note for M2:** The breath-sync tones are more prominent than in M1 because the counting creates a natural rhythmic structure. In M1, the tones are atmospheric. In M2, they're part of the architecture — the child can feel the 4-7-8 arc in the tones.

**Cross-cycle evolution summary:**

| Element | Cycle 1 | Cycle 2 | Cycle 3 |
|---|---|---|---|
| Count pace | ~1 count/sec | ~1 count/sec | ~1.2 count/sec (slower) |
| Breath-sync tone warmth | Baseline | +10% harmonics | +20% harmonics |
| Exhale bloom width | Baseline stereo | +15% wider | +30% wider |
| Exhale shimmer | 1 tone, barely there | 2 tones, slightly present | 3-4 tone cascade, unmistakable |
| Ambient bed level | Baseline | +1 dB warmth | +2 dB warmth |

---

## PART 7: FINAL MIX SPECIFICATIONS

### Per-Module Deliverables

Each module produces these files:

| File | Description | Format |
|---|---|---|
| `M1_voice.wav` | Isolated voice stem with pauses | 48kHz/24bit WAV, mono |
| `M1_ambient.wav` | Ambient bed, trimmed to voice timing | 48kHz/24bit WAV, stereo |
| `M1_functional.wav` | All functional sounds (tones, shimmer) pre-timed to voice | 48kHz/24bit WAV, stereo |
| `M1_mix_full.wav` | Complete layered mix (voice + ambient + functional) | 48kHz/24bit WAV, stereo |
| `M1_mix_full.mp3` | Compressed version for app delivery | 192kbps MP3, stereo |
| `transition_bell.wav` | Universal element (same file, all modules) | 48kHz/24bit WAV, stereo |
| `landing_shimmer_calm.wav` | Domain-tinted shimmer | 48kHz/24bit WAV, stereo |
| `exhale_shimmer_set.wav` | Per-cycle exhale shimmers (3 variants: subtle/medium/full) | 48kHz/24bit WAV, stereo |

**App integration for v1:** The module player receives `M1_mix_full.mp3` and plays it as a single audio file during Phase B. No dynamic mixing. Simple, reliable.

**Future v2:** The app receives stems and mixes in real-time, enabling dynamic features (adjust voice volume, adjust ambient level, potentially respond to microphone input for breath detection).

### Mastering

The final mix should be:
- **Loudness:** -16 LUFS integrated (matches podcast/audiobook standards — comfortable on device speakers and headphones)
- **True peak:** -1 dBTP (prevents clipping on any playback system)
- **No hard limiting** — the mix should breathe. These are meditations, not pop songs.
- **Mono compatibility check:** Verify the mix doesn't lose important elements when summed to mono (many children will listen on phone/tablet speakers)

---

## PART 8: PRODUCTION TIMELINE

### Phase 1: Calm Domain Prototype (2-3 weeks)

| Week | Tasks |
|---|---|
| 1 | Generate M1 and M2 voice stems (ElevenLabs). Design transition bell (3 candidates). Design landing shimmer (3 candidates). Create breath-sync tone prototypes. |
| 2 | Produce M1 ambient bed (sparse). Produce M2 ambient bed (richer + breathing arc). Select transition bell and landing shimmer. First complete mixes of M1 and M2. |
| 3 | Listen testing (Kim + trusted listeners, ideally including a child). Revise based on feedback. Lock Calm domain prototype. |

### Phase 2: Remaining Domains (4-6 weeks after prototype locked)

| Domain | Modules | Priority |
|---|---|---|
| Focus | M3 (Thought Clouds), M4 (Mindful Listening) | High — M4's singing bowl is a unique sound design challenge |
| Heart | M5 (Warm Heart), M6 (Friend Fix Bridge) | Medium |
| Brave | M7 (Brave Steps), M8 (Worry Box) | Medium |
| Grounding | M9 (Sense Anchor), M11 (Squeeze & Release) | Medium |
| Rest | M12 (Body Softening), M13 (Sleepy Stargazing) | Lower (these come last in child's journey) |

### Phase 3: Per-Module Scripts (ongoing, parallel with Phase B script production)

As each module's Phase B script is locked, it enters the sound production pipeline:
1. Voice stem generation
2. Timing cue sheet
3. Ambient bed trimming + functional sound timing
4. Mix
5. Mastering
6. QA

---

## PART 9: BUDGET SUMMARY

| Item | Low Estimate | High Estimate | Notes |
|---|---|---|---|
| ElevenLabs voice | $22/mo × 3 mo | $99/mo × 3 mo | Pro vs Creator plan |
| Transition bell + landing shimmer | $0 (DIY) | $200 (commissioned) | One-time |
| Breath-sync tones | $0 (DIY synth) | $100 (commissioned) | Simple synthesis |
| Ambient beds — Calm domain (2 modules) | $200 (commissioned) | $500 (commissioned) | Prototype |
| Ambient beds — remaining 5 domains (10 modules) | $1,000 | $2,500 | After prototype validated |
| Mixing + mastering (12 modules) | $0 (DIY) | $600 ($50/module) | If outsourcing mix |
| **TOTAL** | **~$1,300** | **~$4,200** | One-time production cost |

For context: this is the total audio production cost for the entire app. It scales to zero per-user.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | February 23, 2026 | Initial integrated brief. Covers voice (ElevenLabs), ambient beds (Calm domain palette + M1/M2 differentiation), functional sounds (transition bell, landing shimmer, breath-sync tones), timing cue sheets for M1 and M2, mix specs, production timeline, and budget. |
| 1.1 | February 24, 2026 | M2 timeline: removed "The air feels different now" from Transition section (phrase cut from M2 script v1.1). |
| 1.2 | March 9, 2026 | Bible v11 alignment. Added Myrrdin voice name and Voice ID (oR4uRy4fHDUGGISL0Rev) to §3.2 — previously referenced elsewhere but not in this document. Module count updated 12→~54. No creature name changes needed (document uses generic creature references). |

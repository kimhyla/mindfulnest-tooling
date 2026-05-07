# M4 Phase B — Cue Point Map

**Module:** M4 (Ember / Heart-Sending Spell)
**Domain:** heart (kindness)
**Voice stem file:** `M4_phase_b_voice_stem.mp3` (pending Kim generation)

---

## CUE-MARKED SCRIPT

Cue markers show where sounds fire in the mix. Markers are stripped before TTS — they exist only for the pipeline.

```
{{BELL_CUE}}
[WELCOME]
Ahh... you've come to send your Kindness magic. Good.

[CONNECTION]
You saw the kind words travel as glowing bubbles — how both you and the Sweetrose got brighter. Now it's your turn to feel that warmth inside.

[SETUP]
Let everything go still for a moment. Feel yourself right here.

Now, if you want to, put your hand right on your heart. You can feel it beating there. Think of who you want to send your warmth to — the Sweetrose, or someone from your life you care about.

Here's what I want you to do.

[INSTRUCTION — Cycle 1]
{{INHALE_CUE}}
Breathe in slowly... and think of something good for them. Something that would make them really happy.

{{EXHALE_CUE}}
Now breathe out... and send it to them. Feel the warmth that goes with it.

[INSTRUCTION — Cycle 2]
{{INHALE_CUE}}
Let's do it again. Same good thing. Breathe in... hold it in your heart...

{{EXHALE_CUE}}
...and breathe out... send it again.

[INSTRUCTION — Cycle 3]
{{INHALE_CUE}}
One more time. In... feel it...

{{EXHALE_CUE}}
...and out... send it with all your warmth.

[DEEPENING — Cycle 4]
{{INHALE_CUE}}
Keep sending that same good thing. In... hold it...

{{EXHALE_CUE}}
...and out... send it.

[DEEPENING — Discovery]
{{NOTICING_CUE}}
Here's the secret. That good thing you keep sending... check inside for a second. Are you feeling a little warmer and nicer too?

[DEEPENING — Cycle 5]
{{INHALE_CUE}}
Keep going. In... feel it...

{{EXHALE_CUE}}
...and out... send it... and feel that warmth inside you at the same time.

[DEEPENING — Naming]
That's the double-up. Your kind thoughts go out to the other person... and they also make you feel nicer and warmer too. That's the Kindness magic working.

[LANDING]
{{LANDING_CUE}}
That warm feeling right there... inside you... that's your Kindness magic.

[EXIT]
{{EXIT_CUE}}
Stay right there. Just keep sending.
```

---

## CUE TYPE SUMMARY

| Cue | Type | Sound | Count | Notes |
|-----|------|-------|-------|-------|
| `{{BELL_CUE}}` | transition bell | `transition_bell.mp3` | 1 | Fires 3s before voice starts |
| `{{INHALE_CUE}}` | breath cycle start | `inhale sound.mp3` | 5 | Triggers inhale wind sound |
| `{{EXHALE_CUE}}` | breath cycle exhale | `exhale sound.mp3` | 5 | Placed by rhythm offset, NOT at narrator's "out" |
| `{{NOTICING_CUE}}` | noticing tone | `noticing tone.mp3` | 1 | Double-up discovery moment |
| `{{LANDING_CUE}}` | landing shimmer | `landing shimmer.mp3` | 1 | "That's your Kindness magic" |
| `{{EXIT_CUE}}` | ambient fade trigger | (no sound — triggers bed fade-out) | 1 | Starts 8s ambient bed fade |

---

## BREATH CYCLE DESIGN

M4 uses breath cycles, but they serve warmth-sending rather than breathing technique. The breath is the VEHICLE, not the lesson. This means:

- **Rhythm:** Same as standard Instruction/Deepening rhythms (4s in, 2s hold, 5s out for Instruction; 3s in, 1s hold, 4s out for Deepening)
- **Volume:** Breath sounds should be QUIETER than M1/M2 — the breath is background, the warmth is foreground. Suggest inhale at 0.20 (vs M1's 0.30), exhale at 0.40 (vs M1's 0.55)
- **No exhale shimmers:** The escalating exhale shimmer pattern (subtle → medium → full) doesn't fit M4. Warmth doesn't "build" per-exhale the way calm does. The single landing shimmer at the end is sufficient.
- **Noticing tone placement:** Fires at "Here's the secret" — the pivot from outward sending to inward discovery. This is M4's unique moment.

---

## AMBIENT BED

**Domain:** heart (kindness)
**Character:** Warmer and more emotional than the calm-domain bed. Should feel like golden afternoon light, not just stillness.
**Existing candidates to audition:** `ambient bed pretty option.mp3` through `ambient bed pretty option6.mp3` — these were generated for earlier modules but the "pretty" aesthetic may fit the heart domain.
**If none work:** Generate new candidates using heart-domain prompts (see below).

### Heart-Domain Ambient Bed Prompt (if needed)

```
Warm golden ambient drone, gentle sustained pad with slow harmonic
breathing, no melody, no rhythm, no percussion. Feels like warmth
radiating from inside — soft analog synthesizer with a tender,
emotional quality. Comforting and safe, like being wrapped in sunlight.
Very quiet and subtle. Major key warmth. Children's meditation background.
```

---

## VOLUME ARCHITECTURE (M4-specific)

| Layer | Gain | Rationale |
|-------|------|-----------|
| Voice stem | 1.00 | Always loudest |
| Ambient bed | 0.08 | Same as M1 proven default |
| Transition bell | 0.50 | Standard |
| Inhale wind | 0.20 | Quieter than M1 — breath is background in this module |
| Exhale wind | 0.40 | Quieter than M1 — same reason |
| Noticing tone | 0.15 | Gentle awareness marker at double-up discovery |
| Landing shimmer | 0.25 | Slightly louder than M1 — the warmth landing is M4's peak moment |

---

## PIPELINE STEPS (after voice stem exists)

1. **Vosk extraction:** Run STT on voice stem → word-level timestamps
2. **Cue matching:** Match cue markers to word occurrences using disambiguation (5 inhale cues, 5 exhale cues — count occurrences of "breathe"/"in" and "out"/"send")
3. **Rhythm assignment:** Apply Instruction rhythm (cycles 1-3) and Deepening rhythm (cycles 4-5)
4. **Overlap check:** Verify no cycle bleeds into the next
5. **Mix:** Voice + bell + ambient bed + 5 breath cycles + noticing tone + landing shimmer → `M4_phase_b_complete_mix.mp3`
6. **Kim listen-through:** Approve or adjust

---

*v1.0 — April 2, 2026. Derived from approved Phase B script v1.2 + Audio Assembly Guide v1.4 + Audio Pipeline Master Plan v1.*

# M4 Phase B — ElevenLabs TTS Generation Script

**Voice:** Myrrhin (Voice ID: `oR4uRy4fHDUGGISL0Rev`)
**Settings:** Stability 65-75% · Clarity 75-85% · Style Exaggeration 15-25%
**Generate:** 3 takes, pick best for pacing and warmth
**Export:** MP3, save as `M4_phase_b_voice_stem.mp3`

---

## WHAT TO PASTE INTO ELEVENLABS

Copy everything between the `---` lines below. Nothing else.

---

[warmly] Ahh... you've come to send your Kindness magic. Good.

You saw the kind words travel as glowing bubbles... how both you and the Sweetrose got brighter. Now it's your turn to feel that warmth inside.

[gently] Let everything go still for a moment... Feel yourself right here.

Now, if you want to... put your hand right on your heart. You can feel it beating there... Think of who you want to send your warmth to... the Sweetrose... or someone from your life you care about.

Here's what I want you to do.

[gently] Breathe in slowly... and think of something good for them. Something that would make them really happy.

Now breathe out...... and send it to them. Feel the warmth that goes with it.

Let's do it again. Same good thing. Breathe in...... hold it in your heart......

......and breathe out...... send it again.

One more time. In...... feel it......

......and out...... send it with all your warmth.

Keep sending that same good thing. In...... hold it......

......and out...... send it.

[warmly] Here's the secret. That good thing you keep sending...... check inside for a second. Are you feeling a little warmer and nicer too?

Keep going. In...... feel it......

......and out...... send it...... and feel that warmth inside you at the same time.

That's the double-up. Your kind thoughts go out to the other person...... and they also make you feel nicer and warmer too. That's the Kindness magic working.

[softly] That warm feeling right there...... inside you...... that's your Kindness magic.

[softly] Stay right there. Just keep sending.

---

## PACING NOTES

- **Overall energy:** Warmer and more tender than M1. The "Ahh..." is a pleased exhale, not just a greeting. "Good." is quiet satisfaction.
- **Breath pacing:** The breath cycles here are NOT counted (unlike M2). They're slow and natural — ~4s in, ~2s pause, ~5s out. The child is sending warmth, not counting.
- **Double-up discovery:** "Here's the secret" should have a touch of conspiratorial warmth — sharing something wonderful. "Are you feeling a little warmer and nicer too?" is genuine curiosity, not a leading question.
- **Landing:** "That warm feeling right there... inside you..." — soft, almost a whisper. Specific. The quietest, most intimate moment.
- **Exit:** "Stay right there. Just keep sending." — trails off gently. Does NOT conclude. Leaves the child in the sending state.
- **Extra ellipses** (`......`) are intentional — they create longer pauses for breathing space. If Myrrhin still rushes through them, try adding `<break time="3s"/>` tags at those points.

## PVC CAVEAT

Myrrhin is a Professional Voice Clone. The `[gently]`, `[warmly]`, `[softly]` audio tags may behave differently than with standard voices. **Test on the first paragraph first.** If tags are ignored or produce odd results, remove them and rely on the ellipsis pacing alone — the script reads warmly without them.

## DURATION TARGET

Script is ~170 words. Expected voice stem duration: **100-120 seconds** (with grounding + warmth-generation pauses). If the stem comes in under 90s, the pauses are too rushed — regenerate. If over 140s, it's dragging — also regenerate.

## AFTER GENERATING

1. Pick the best of 3 takes
2. Save as `M4_phase_b_voice_stem.mp3` in the project folder
3. Tell Claude "voice stem is ready" — Claude handles everything from there (cue points, mixing, final MP3)

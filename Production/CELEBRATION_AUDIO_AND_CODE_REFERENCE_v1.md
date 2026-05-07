# MindfulNest Celebration Layer — Audio & Code Reference

**Version:** 1.0
**Date:** March 30, 2026
**Purpose:** Technical specifications and code examples for celebration moment implementation
**Companion Document:** PROGRESS_ROAD_CELEBRATION_LAYER_DESIGN_v1.md

---

## PART 1: CELEBRATION CHIME SPECIFICATION

### 1.1 Musical Notes & Frequency

**Three-Note Ascending Progression (Major Chord)**

| Note | Frequency (Hz) | Duration | Gap After |
|------|---|---|---|
| C4 (Middle C) | 261.63 Hz | 0.4s | 0.15s |
| E4 (Major Third) | 329.63 Hz | 0.4s | 0.15s |
| G4 (Perfect Fifth) | 392.00 Hz | 0.4s | — |

**Total Duration:** 0.4 + 0.15 + 0.4 + 0.15 + 0.4 = 1.5 seconds

**Rationale:**
- Major chord progression conveys completion and warmth
- C-E-G is the most "complete" sounding triad (I-III-V)
- Middle register (C4-G4) is warm but not overly deep
- Ascending progression feels uplifting (psychological association)
- 1.5 seconds is long enough to be noticed, short enough to not interrupt

### 1.2 Instrumentation: Bell/Vibraphone Synthesis

The celebration chime should sound like a warm bell or vibraphone, not a harsh synth.

**Characteristics:**
- Attack: Very fast (< 20ms) — immediate onset
- Sustain: Gradual decay over 0.35 seconds per note
- Timbre: Warm, slightly mellow (not bright/harsh)
- Resonance: Slight harmonic richness (not pure sine wave)
- Reverb: 0.2 seconds of subtle room reverb (optional, adds warmth)

**Bad Examples:**
- ✗ Harsh metallic bell (like a telephone ring)
- ✗ Thin sine-wave tones (too digital)
- ✗ Deep bass notes (too heavy, not celebratory)
- ✗ Super bright ding (juvenile, like a game alarm)

**Good Examples:**
- ✓ Apple Watch ring-complete chime (reference: warm vibraphone)
- ✓ Headspace meditation timer (reference: soft bell)
- ✓ Piano D4-F#4-A4 progression (reference: warm major chord)

### 1.3 Audio Generation Options

#### Option A: Pre-Recorded Audio File (Recommended for MVP)

**Steps:**
1. Generate notes using a DAW (Digital Audio Workstation):
   - Logic Pro, Ableton, or free tool (GarageBand on Mac, Audacity on all platforms)
   - Select vibraphone instrument
   - Create MIDI notes: C4 (1 beat), gap, E4 (1 beat), gap, G4 (1 beat)
   - Tempo: 120 BPM gives appropriate timing
   - Export as MP3 (128 kbps, mono) or WAV (44.1 kHz, 16-bit, mono)

2. **File specs:**
   - Format: MP3 (for app bundle) or WAV (for web)
   - Bit rate: 128 kbps (MP3) or 16-bit 44.1 kHz (WAV)
   - File size: ~40-50 KB (negligible for app download)
   - Sample: "celebration_chime_C4_E4_G4_1500ms.mp3"

3. **Asset management:**
   - Store in app bundle under `/assets/audio/celebration/`
   - Preload on app startup (negligible latency)
   - Provide fallback haptic pattern if audio unavailable

#### Option B: Web Audio API / Tone.js (For Advanced Implementation)

If generating audio programmatically, use Tone.js (lightweight, well-supported):

```javascript
// Install: npm install tone

import * as Tone from 'tone';

// Function to play celebration chime
async function playCelebrationChime() {
  const now = Tone.now();

  // Create synth (vibraphone-like sound)
  const synth = new Tone.Synth({
    oscillator: { type: 'sine' }, // or 'triangle' for slight harmonic richness
    envelope: {
      attack: 0.01,     // 10ms attack
      decay: 0.35,      // 350ms decay
      sustain: 0,       // No sustain
      release: 0.1      // 100ms release
    }
  }).toDestination();

  // Play C4 (261.63 Hz) for 0.4 seconds
  synth.triggerAttackRelease('C4', '0.4');

  // Play E4 after 0.55s (0.4s note + 0.15s gap)
  synth.triggerAttackRelease('E4', '0.4', now + 0.55);

  // Play G4 after 1.1s
  synth.triggerAttackRelease('G4', '0.4', now + 1.1);

  // Return promise that resolves when chime completes
  return new Promise(resolve => {
    setTimeout(resolve, 1500); // Total duration
  });
}

// Trigger on button click
document.getElementById('celebrateButton').addEventListener('click', async () => {
  await Tone.start(); // Initialize Web Audio context
  await playCelebrationChime();
  triggerConfetti();
  triggerHaptic();
});
```

**Advantages:**
- No audio file to download
- Can adjust pitch/timing dynamically
- Smaller bundle size

**Disadvantages:**
- Slightly higher computational cost
- May fail on some browsers if Web Audio API not available

**Recommendation:** Use pre-recorded audio for MVP (simpler, more reliable). Upgrade to Tone.js later if needed.

### 1.4 Volume Specification

**Perceived Loudness:** -18 dB relative to app's max volume

**Why:**
- Loud enough to be heard in a moderately noisy home
- Soft enough to not startle or dominate attention
- -18 dB is equivalent to Headspace/Calm notification volumes

**Implementation:**
```javascript
// When playing audio
const audioElement = document.getElementById('celebrationAudio');
audioElement.volume = 0.15; // 0-1 scale, 0.15 ≈ -18 dB
audioElement.play();
```

**Accessibility:**
- Always respect system volume settings
- Provide mute override in settings
- Never force full-volume playback

### 1.5 Haptic Feedback Pattern

For devices with haptic motors (iPhone, Android flagship):

**Pattern:** 2 short taps + 1 longer tap (mirrors the note progression)

```javascript
// Using iOS Haptics or Android Vibration API

// iOS (via WebKit)
function triggerHapticPattern() {
  if (window.webkit?.messageHandlers?.haptic) {
    // Short-short-long pattern
    window.webkit.messageHandlers.haptic.postMessage({
      pattern: 'celebrationMilestone'
    });
  } else if (navigator.vibrate) {
    // Android Vibration API fallback
    // [vibrate, pause, vibrate, pause, vibrate]
    navigator.vibrate([50, 50, 50, 50, 100]);
  }
}

triggerHapticPattern();
```

**Android Implementation (Kotlin):**
```kotlin
// In your Activity
val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator

if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
  vibrator.vibrate(
    VibrationEffect.createWaveform(
      longArrayOf(0, 50, 50, 50, 50, 100),  // timings in ms
      -1  // repeat index (-1 = no repeat)
    )
  )
} else {
  vibrator.vibrate(longArrayOf(0, 50, 50, 50, 50, 100), -1)
}
```

---

## PART 2: ANIMATION SPECIFICATIONS

### 2.1 Glow Animation (CSS)

```css
/* Glow animation — applies to milestone card container */
@keyframes celebration-glow {
  0% {
    box-shadow: 0 0 0 0 rgba(220, 140, 80, 0.4);
  }
  50% {
    box-shadow: 0 0 25px 8px rgba(220, 140, 80, 0.2);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(220, 140, 80, 0);
  }
}

.milestone-card.celebrating {
  animation: celebration-glow 2s ease-out 1;
}

/* Color per arc (matches stone colors) */
.milestone-card.arc-1.celebrating {
  animation: celebration-glow-arc1 2s ease-out 1;
}

@keyframes celebration-glow-arc1 {
  0% { box-shadow: 0 0 0 0 rgba(220, 140, 80, 0.4); }
  50% { box-shadow: 0 0 25px 8px rgba(220, 140, 80, 0.2); }
  100% { box-shadow: 0 0 0 0 rgba(220, 140, 80, 0); }
}

.milestone-card.arc-2.celebrating {
  animation: celebration-glow-arc2 2s ease-out 1;
}

@keyframes celebration-glow-arc2 {
  0% { box-shadow: 0 0 0 0 rgba(220, 200, 80, 0.4); }
  50% { box-shadow: 0 0 25px 8px rgba(220, 200, 80, 0.2); }
  100% { box-shadow: 0 0 0 0 rgba(220, 200, 80, 0); }
}

/* Additional arcs... */
```

**Parameters:**
- **Duration:** 2000ms
- **Easing:** ease-out (slows down toward end)
- **Timing:** Starts immediately when "Celebrate Moment" clicked
- **Repeats:** Once per celebration
- **Max shadow blur:** 25px (visible from a distance, not overwhelming)

### 2.2 Confetti Animation (CSS)

```css
/* Confetti particles — soft, minimal design */
.confetti-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
}

.confetti-particle {
  position: absolute;
  opacity: 1;
  animation: confetti-fall 1s ease-in forwards;
}

@keyframes confetti-fall {
  0% {
    transform: translateY(-20px) translateX(var(--drift)) rotateZ(0deg);
    opacity: 1;
  }
  100% {
    transform: translateY(150px) translateX(var(--drift)) rotateZ(360deg);
    opacity: 0;
  }
}

/* Particle colors (soft pastels matching arc themes) */
.confetti-particle.arc-1 {
  background-color: rgba(220, 140, 80, 0.7); /* Soft orange */
}

.confetti-particle.arc-2 {
  background-color: rgba(220, 200, 80, 0.7); /* Soft yellow */
}

.confetti-particle.arc-3 {
  background-color: rgba(180, 220, 140, 0.7); /* Soft green */
}

/* etc. for other arcs */

/* Particle sizing */
.confetti-particle {
  width: 8px;
  height: 8px;
  border-radius: 50%; /* Circles, not rectangles */
}
```

**JavaScript to Trigger:**

```javascript
function triggerConfetti(arcColor = 'arc-1') {
  const container = document.querySelector('.confetti-container');
  const particleCount = 25;

  for (let i = 0; i < particleCount; i++) {
    const particle = document.createElement('div');
    particle.className = `confetti-particle ${arcColor}`;

    // Random horizontal drift (-40px to +40px)
    const drift = Math.random() * 80 - 40;
    particle.style.setProperty('--drift', `${drift}px`);

    // Random starting position across card width
    particle.style.left = Math.random() * 100 + '%';

    container.appendChild(particle);

    // Remove particle from DOM after animation completes
    setTimeout(() => particle.remove(), 1000);
  }
}

// Trigger when "Celebrate Moment" clicked
document.getElementById('celebrateButton').addEventListener('click', () => {
  triggerConfetti(milestoneArcColor);
  playCelebrationChime();
  triggerHaptic();
});
```

**Parameters:**
- **Particle count:** 25 (enough to see, not overwhelming)
- **Particle size:** 8x8px (small, subtle)
- **Particle shape:** Circles (soft, not sharp)
- **Duration:** 1000ms (falls while sound plays)
- **Drift range:** ±40px (horizontal variation)
- **Opacity:** Fades from 1 to 0 (not abrupt disappearance)
- **Rotation:** 360deg (gentle spin effect)

### 2.3 Combined Celebration Sequence

```javascript
async function celebrateMilestone(milestoneCard, arcColor) {
  const button = milestoneCard.querySelector('[data-celebrate]');

  button.addEventListener('click', async () => {
    // Disable button to prevent rapid re-triggering
    button.disabled = true;

    // Start glow animation immediately
    milestoneCard.classList.add('celebrating');

    // Start confetti (non-blocking)
    triggerConfetti(arcColor);

    // Start audio (2 second blocking operation)
    await playCelebrationChime();

    // Remove celebration class after glow completes
    setTimeout(() => {
      milestoneCard.classList.remove('celebrating');
    }, 2000);

    // Re-enable button (allow parent to celebrate again if desired)
    button.disabled = false;
  });
}
```

**Timeline:**
- T=0ms: Glow starts, confetti generated, button disabled
- T=0ms: Audio starts (chime plays for 1500ms)
- T=1000ms: Confetti particles all faded out
- T=1500ms: Audio ends, haptic pattern completes
- T=2000ms: Glow animation ends, button re-enabled

---

## PART 3: REACT COMPONENT EXAMPLE

### 3.1 MilestoneCard Component

```jsx
import React, { useState, useRef } from 'react';
import './MilestoneCard.css';

const MilestoneCard = ({ milestone, arcColor }) => {
  const [isCelebrating, setIsCelebrating] = useState(false);
  const cardRef = useRef(null);
  const containerRef = useRef(null);

  const arcColors = {
    'arc-1': 'rgba(220, 140, 80, 0.4)',
    'arc-2': 'rgba(220, 200, 80, 0.4)',
    'arc-3': 'rgba(180, 220, 140, 0.4)',
    // ... more arcs
  };

  const playCelebrationSound = async () => {
    try {
      const audio = new Audio('/assets/audio/celebration_chime.mp3');
      audio.volume = 0.15; // -18dB equivalent
      audio.play();

      // Return promise that resolves when audio ends
      return new Promise((resolve) => {
        audio.addEventListener('ended', resolve, { once: true });
      });
    } catch (error) {
      console.error('Failed to play celebration sound:', error);
    }
  };

  const triggerHaptic = () => {
    if (navigator.vibrate) {
      // Android Vibration API
      navigator.vibrate([50, 50, 50, 50, 100]);
    } else if (window.webkit?.messageHandlers?.haptic) {
      // iOS haptic
      window.webkit.messageHandlers.haptic.postMessage({
        pattern: 'celebrationMilestone'
      });
    }
  };

  const generateConfetti = () => {
    const container = containerRef.current;
    if (!container) return;

    const particleCount = 25;
    const arcColorMap = {
      'arc-1': 'rgba(220, 140, 80, 0.7)',
      'arc-2': 'rgba(220, 200, 80, 0.7)',
      'arc-3': 'rgba(180, 220, 140, 0.7)',
      // ... more
    };

    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement('div');
      particle.className = 'confetti-particle';
      particle.style.background = arcColorMap[arcColor] || 'rgba(200, 150, 200, 0.7)';

      const drift = Math.random() * 80 - 40;
      particle.style.setProperty('--drift', `${drift}px`);
      particle.style.left = Math.random() * 100 + '%';

      container.appendChild(particle);

      // Remove after animation completes
      setTimeout(() => particle.remove(), 1000);
    }
  };

  const handleCelebrate = async () => {
    setIsCelebrating(true);
    cardRef.current?.classList.add('celebrating');

    // Trigger all celebration effects in parallel
    generateConfetti();
    triggerHaptic();
    await playCelebrationSound();

    // Remove celebration class after glow completes
    setTimeout(() => {
      cardRef.current?.classList.remove('celebrating');
      setIsCelebrating(false);
    }, 2000);
  };

  return (
    <div
      ref={containerRef}
      className={`milestone-card ${arcColor}`}
      style={{
        '--arc-glow-color': arcColors[arcColor],
      }}
    >
      <div ref={cardRef} className="milestone-card-content">
        <div className="milestone-header">
          <span className="milestone-icon">🌟</span>
          <h2>{milestone.childName} reached {milestone.type}</h2>
        </div>

        <div className="milestone-title">
          "{milestone.name}"
        </div>

        <div className="milestone-date">
          {new Date(milestone.date).toLocaleDateString()} — {milestone.duration}
        </div>

        <div className="milestone-description">
          {milestone.description}
        </div>

        <div className="milestone-actions">
          <button
            onClick={handleCelebrate}
            disabled={isCelebrating}
            className="celebrate-button"
            data-celebrate
          >
            {isCelebrating ? 'Celebrating...' : 'Celebrate Moment'}
          </button>
          <button
            onClick={() => setShowLanguage(!showLanguage)}
            className="together-button"
          >
            Celebrate Together
          </button>
        </div>

        {showLanguage && (
          <CelebrationLanguage milestone={milestone} />
        )}
      </div>
    </div>
  );
};

export default MilestoneCard;
```

### 3.2 CelebrationLanguage Component

```jsx
const CelebrationLanguage = ({ milestone }) => {
  const [showMore, setShowMore] = useState(false);

  const languageSuggestions = {
    'arc-completion': [
      `"I noticed you've finished your first arc in MindfulNest. That's 6 weeks of learning new ways to calm down and handle tough feelings. I'm really proud of you for sticking with it."`,
      `"What was your favorite creature you met in Everdale? What did they teach you?" [Listen; don't correct.]`,
      `"You've learned a lot of techniques now. Have you noticed using any of them when you're not on the app?"`,
    ],
    'mastery-level-4': [
      `"I noticed you using that breathing technique when you were worried about school. That shows real courage."`,
      `"You're getting really good at that technique. How does it feel when you use it?"`,
      `"That's a tool you can use forever. You own this now."`,
    ],
    // ... more milestone types
  };

  const suggestions = languageSuggestions[milestone.typeKey] || [];

  return (
    <div className="celebration-language">
      <h3>Celebrate This Moment Together</h3>
      <p className="intro">{milestone.languageIntro}</p>

      <div className="suggestions">
        {suggestions.slice(0, 3).map((suggestion, idx) => (
          <div key={idx} className="suggestion-card">
            <span className="icon">📌</span>
            <p>{suggestion}</p>
          </div>
        ))}
      </div>

      {!showMore && (
        <button
          onClick={() => setShowMore(true)}
          className="more-ideas-button"
        >
          More Ideas
        </button>
      )}

      {showMore && (
        <div className="more-suggestions">
          {/* Additional suggestions */}
        </div>
      )}

      <button className="skip-button">Skip</button>
    </div>
  );
};
```

### 3.3 Styling (CSS)

```css
/* Milestone card base */
.milestone-card {
  background: linear-gradient(135deg, #f0e6d3 0%, #f5e8db 100%);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 16px;
  transition: box-shadow 0.3s ease;
}

/* Celebration state */
.milestone-card.celebrating {
  animation: celebration-glow 2s ease-out 1;
}

/* Arc-specific glow colors */
.milestone-card.arc-1.celebrating {
  box-shadow: 0 0 0 0 rgba(220, 140, 80, 0.4);
  animation: celebrate-glow-arc1 2s ease-out 1;
}

@keyframes celebrate-glow-arc1 {
  0% { box-shadow: 0 0 0 0 rgba(220, 140, 80, 0.4); }
  50% { box-shadow: 0 0 25px 8px rgba(220, 140, 80, 0.2); }
  100% { box-shadow: 0 0 0 0 rgba(220, 140, 80, 0); }
}

/* Milestone header */
.milestone-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.milestone-icon {
  font-size: 24px;
}

.milestone-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

/* Buttons */
.celebrate-button,
.together-button {
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.celebrate-button {
  background: #8b7e7e;
  color: white;
  margin-right: 12px;
}

.celebrate-button:hover:not(:disabled) {
  background: #6b5e5e;
}

.celebrate-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.together-button {
  background: #f0e6d3;
  color: #333;
  border: 1px solid #ddd;
}

.together-button:hover {
  background: #e8dcc4;
}

/* Confetti container */
.confetti-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
}

.confetti-particle {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: confetti-fall 1s ease-in forwards;
}

@keyframes confetti-fall {
  0% {
    transform: translateY(-20px) translateX(var(--drift)) rotateZ(0deg);
    opacity: 1;
  }
  100% {
    transform: translateY(150px) translateX(var(--drift)) rotateZ(360deg);
    opacity: 0;
  }
}

/* Language suggestions */
.celebration-language {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #ddd;
}

.celebration-language h3 {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
}

.suggestion-card {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.suggestion-card .icon {
  flex-shrink: 0;
  font-size: 18px;
}

.suggestion-card p {
  font-size: 14px;
  line-height: 1.5;
  color: #555;
  margin: 0;
}
```

---

## PART 4: TESTING & QA CHECKLIST

### 4.1 Audio Testing

- [ ] Celebration chime plays at correct volume (-18dB)
- [ ] No clipping or distortion at normal listening level
- [ ] Sound begins and ends cleanly (no clicks)
- [ ] Duration is exactly 1.5 seconds
- [ ] Works on iOS (Safari, app webview)
- [ ] Works on Android (Chrome, app webview)
- [ ] Respects system volume settings
- [ ] Respects mute switch (iOS)
- [ ] Works with headphones
- [ ] Works with speaker

### 4.2 Animation Testing

- [ ] Glow animation is smooth and 2 seconds long
- [ ] Confetti particles animate correctly
- [ ] Confetti fades out (not abrupt)
- [ ] Animation performance is good (no jank on low-end devices)
- [ ] Animation respects `prefers-reduced-motion` setting
- [ ] Glow color matches arc color
- [ ] Button is disabled during celebration (no rapid re-triggers)
- [ ] Celebration can be retriggered after completion

### 4.3 Haptic Testing

- [ ] Haptic pattern vibrates (2 short + 1 long)
- [ ] Haptic works on iPhone (requires iOS 14+)
- [ ] Haptic works on Android (requires Vibration API support)
- [ ] Haptic respects system haptic settings
- [ ] Haptic fails gracefully if device doesn't support it

### 4.4 Accessibility Testing

- [ ] Sound plays correctly when system volume is high
- [ ] Sound plays correctly when system volume is low
- [ ] Mute override works (button still triggers haptic/visual)
- [ ] Screen reader announces milestone correctly
- [ ] Button is keyboard accessible
- [ ] Animation respects `prefers-reduced-motion` in CSS

### 4.5 Edge Cases

- [ ] Multiple milestones on same day display correctly
- [ ] Celebration works offline (audio preloaded)
- [ ] Celebration works on slow network
- [ ] Memory leak check: no dangling event listeners after celebration
- [ ] Parent can celebrate multiple times (button re-enables)
- [ ] Celebration data persists (can see old milestones)

---

## PART 5: PERFORMANCE OPTIMIZATION

### 5.1 Audio File Size

**Target:** < 50 KB per audio file

**Optimization:**
- Mono (not stereo): Halves file size
- 128 kbps MP3 bitrate: Transparent quality
- 44.1 kHz sample rate: Standard, not overkill

**Example Sizes:**
- Celebration chime (1.5s stereo WAV): ~100 KB
- Celebration chime (1.5s mono MP3 128kbps): ~35 KB
- Celebration chime (1.5s mono MP3 96kbps): ~25 KB

### 5.2 CSS Animation Performance

**Best Practices:**
- Use `transform` and `opacity` only (GPU-accelerated)
- Avoid animating `box-shadow` if possible (use `filter: drop-shadow()` instead)
- Limit simultaneous animations to 1-2 elements
- Use `will-change` sparingly (can increase memory use)

**Example Optimized Glow (using drop-shadow):**
```css
@keyframes celebration-glow-optimized {
  0% {
    filter: drop-shadow(0 0 0px rgba(220, 140, 80, 0.4));
  }
  50% {
    filter: drop-shadow(0 0 15px rgba(220, 140, 80, 0.3));
  }
  100% {
    filter: drop-shadow(0 0 0px rgba(220, 140, 80, 0));
  }
}
```

### 5.3 Memory Management (React)

**Cleanup:**
```javascript
useEffect(() => {
  const handleCelebrate = () => { /* ... */ };
  button?.addEventListener('click', handleCelebrate);

  // Cleanup on unmount
  return () => {
    button?.removeEventListener('click', handleCelebrate);
  };
}, []);
```

**Confetti Cleanup:**
- Remove DOM nodes after animation (already done in example code)
- Don't create >100 particles at once
- Cache SVG/canvas confetti if rendering many celebration cards

---

## SUMMARY

**Audio:** Warm 3-note ascending chime (C-E-G, 1.5s, vibraphone)
**Visual:** 2s glow animation + optional confetti (1s)
**Haptic:** 2 short + 1 long vibration pattern
**Implementation:** Pre-recorded MP3 file (~35 KB) + CSS/JS animations
**Total UX Duration:** ~2 seconds from click to completion

---

**Document Version:** 1.0
**Last Updated:** March 30, 2026
**Status:** Ready for Audio Engineer & Frontend Developer Review

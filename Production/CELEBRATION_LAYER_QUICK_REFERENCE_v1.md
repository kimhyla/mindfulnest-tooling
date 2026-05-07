# Progress Road Celebration Layer — Quick Reference Guide

**Version:** 1.0 (Quick Lookup)
**Full Documentation:**
- Design: `PROGRESS_ROAD_CELEBRATION_LAYER_DESIGN_v1.md`
- Audio/Code: `CELEBRATION_AUDIO_AND_CODE_REFERENCE_v1.md`
- Strategy: `PROGRESS_ROAD_CELEBRATION_EXECUTIVE_SUMMARY_v1.md`

---

## VISUAL REFERENCE

### Milestone Card Layout

```
┌─────────────────────────────────┐
│ 🌟 Child reached Arc Completion│
│                                 │
│ "Complete Arc 1: Everdale..."  │
│                                 │
│ Date — Duration                 │
│                                 │
│ [2-3 sentence clinical desc]   │
│                                 │
│ [Celebrate] [Together] buttons │
└─────────────────────────────────┘
```

### Colors by Arc

| Arc | Domain | Color | Hex |
|-----|--------|-------|-----|
| 1 | Body-Sensing | Warm Orange | #DC8C50 |
| 2 | Now-Watching | Warm Yellow | #DCC850 |
| 3 | Courage | Soft Green | #B4DC8C |
| 4 | Kindness | Soft Red | #DC8C8C |
| 5 | Calm-Breathing | Soft Blue | #8CB0DC |
| 6 | Self-Grounding | Soft Purple | #C8A0DC |

---

## AUDIO CHIME SPEC

**Notes:** C4 (261.63 Hz) → E4 (329.63 Hz) → G4 (392.00 Hz)
**Duration:** 0.4s → 0.15s gap → 0.4s → 0.15s gap → 0.4s = 1.5s total
**Volume:** -18 dB (audio element: `volume = 0.15`)
**Instrument:** Vibraphone (warm, not synth)
**File Size:** ~35 KB (MP3 128kbps mono)

**To Generate:**
- DAW: Logic Pro, Ableton, GarageBand, or Audacity
- Instrument: Vibraphone or soft bell
- Envelope: Attack 10ms, Decay 350ms, Release 100ms
- Export: MP3 (128kbps, mono) or WAV (44.1kHz, 16-bit)
- Store: `/assets/audio/celebration_chime.mp3`

---

## ANIMATION SPECS

### Glow (2 seconds)
```css
@keyframes celebration-glow {
  0% { box-shadow: 0 0 0 0 rgba(220, 140, 80, 0.4); }
  50% { box-shadow: 0 0 25px 8px rgba(220, 140, 80, 0.2); }
  100% { box-shadow: 0 0 0 0 rgba(220, 140, 80, 0); }
}
```

### Confetti (1 second, 25 particles)
- Size: 8x8px circles
- Fall distance: 150px
- Drift: ±40px horizontal
- Opacity: 1 → 0 (fade)
- Rotation: 360deg

### Haptic Pattern
- [50ms vibrate, 50ms pause, 50ms vibrate, 50ms pause, 100ms vibrate]
- Or: 2 short taps + 1 longer tap

---

## MILESTONE TYPES & TRIGGERS

### Arc Completion
- **Trigger:** All 6 events completed in arc
- **Frequency:** ~Monthly
- **Importance:** ★★★ (Highest)
- **Sound:** Full chime + loud haptic
- **Visual:** Large glow + confetti

### Mastery Level 4 (Adept)
- **Trigger:** Spell reaches Adept level
- **Frequency:** ~Weekly
- **Importance:** ★★ (Medium)
- **Sound:** Full chime (or softer variant)
- **Visual:** Medium glow + optional confetti

### Goal Achievement
- **Trigger:** Therapist-set goal reached
- **Frequency:** ~Weekly
- **Importance:** ★ (Lower)
- **Sound:** Quick chime (or silent)
- **Visual:** Subtle glow, no confetti

### Consistency Streak
- **Trigger:** 10 / 30 / 60+ consecutive days
- **Frequency:** Rare
- **Importance:** ★★ (Medium)
- **Sound:** Full chime
- **Visual:** Medium glow

---

## LANGUAGE FORMULA BY MILESTONE TYPE

### Arc Completion
**Headline:** `[Child] reached Arc Completion: "[Arc Name]"`
**Description:** "X has completed their [#] arc... This represents [duration] of consistent practice and marks [clinical significance]."
**Suggestions:** 4 options focusing on (1) effort, (2) curiosity about favorite creature, (3) real-world application, (4) sharing/family

### Mastery Level 4
**Headline:** `[Child] reached Mastery Level 4: "[Spell Name]"`
**Description:** "X can now use [Spell] even when feeling anxious... This shows the technique is becoming automatic and real-world applicable."
**Suggestions:** 3 options focusing on (1) observation of use, (2) asking how it feels, (3) ownership/competence

### Goal Achievement
**Headline:** `[Child] reached Goal: "[Goal Name]"`
**Description:** "This shows X is [clinical significance of goal]. Example: 'taking ownership of their coping skills' or 'building consistency.'"
**Suggestions:** 2-3 options, brief, observation-based

---

## TONE GUIDE (DO/DON'T)

### DO
- ✓ "Your child reached a courage milestone"
- ✓ "Shows that..."
- ✓ "What did you learn?"
- ✓ "6 weeks of practice"
- ✓ "Taking ownership"
- ✓ "Automatic" / "Competence"
- ✓ "You might say..."

### DON'T
- ✗ "AMAZING!!!"
- ✗ "You're the best!"
- ✗ "Time for ice cream!"
- ✗ "Won the courage spell"
- ✗ "Better than other kids"
- ✗ "You MUST celebrate"
- ✗ "So proud!" (too generic)

---

## SETTINGS & ACCESSIBILITY

### Parent Preference Toggle
```
☑ Play celebration sound
☑ Show language suggestions
☑ Display progress road
☐ Weekly digest email
```

### Accessibility Options
- **Deaf/HoH:** Haptic-only, captions on video
- **Neurodivergent:** Reduce animation duration, high contrast
- **Non-English:** Support all app languages + therapist-provided suggestions

---

## REACT COMPONENT ESSENTIALS

### Import & Setup
```javascript
import { MilestoneCard } from './components/MilestoneCard';
import './assets/audio/celebration_chime.mp3';

// Usage
<MilestoneCard
  milestone={milestoneData}
  arcColor="arc-1"
/>
```

### Key Functions
```javascript
playCelebrationSound()  // Audio playback
triggerHaptic()         // Vibration pattern
generateConfetti()      // Particle animation
triggerGlow()          // CSS animation class
```

### Event Handlers
```javascript
onClick={handleCelebrate}  // Triggers all effects
onClick={handleLanguage}   // Expands suggestions
onAnimationEnd={cleanup}   // Removes glow class
```

---

## TESTING CHECKLIST

### Audio
- [ ] Plays at -18dB volume
- [ ] No clipping/distortion
- [ ] Exactly 1.5 seconds
- [ ] Works iOS & Android
- [ ] Respects mute switch

### Animation
- [ ] 2-second glow smooth
- [ ] Confetti fades (no abrupt end)
- [ ] Good performance (no jank)
- [ ] Respects `prefers-reduced-motion`
- [ ] Button disabled during celebration

### Haptic
- [ ] Pattern: 2 short + 1 long
- [ ] Works iPhone (iOS 14+)
- [ ] Works Android
- [ ] Fails gracefully if unsupported

### UX
- [ ] All text is clear and scannable
- [ ] Language suggestions are approachable
- [ ] "Skip" button always available
- [ ] Multiple celebrations possible
- [ ] Works on slow network

---

## ROLLOUT PHASES

### Phase 1 (2 weeks)
- Milestone card visual design
- Language suggestion cards
- Progress road timeline
- No audio

### Phase 2 (2 weeks after Phase 1)
- Celebration audio + haptic
- Confetti animation
- Arc color theming

### Phase 3 (1 month)
- Real-world timing suggestions
- Setback guidance cards
- Accessibility features
- A/B testing

---

## METRICS TO TRACK

### Engagement
- % of milestones with "Celebrate Moment" clicks (target: >50% arcs)
- % clicking "Celebrate Together" (target: >40%)
- Confetti on/off preference split
- Sound on/off preference split

### Retention
- Parent app opens 7 days post-milestone vs. baseline
- Subscription retention improvement post-celebration feature

### Qualitative
- Parent satisfaction (survey post-celebration)
- Language suggestion utility (do parents use provided language?)
- Therapist feedback on parent-child alignment

---

## GOTCHAS & EDGE CASES

⚠️ **Multiple milestones same day:** Combine into single card
⚠️ **Offline mode:** Audio must be preloaded (not streamed)
⚠️ **Slow network:** Don't block card render on confetti JS
⚠️ **Rapid re-celebration:** Disable button during animation
⚠️ **Setbacks:** Never use shame language or urgency
⚠️ **Therapist integration:** Always acknowledge therapist is the clinical decision-maker

---

## QUICK LOOKUP: MILESTONE CARD TEMPLATE

```
[Icon] [Child Name] reached [Milestone Type]

"[Milestone Name]"

[Date] — [Duration/Time Context]

[1-2 sentence clinical explanation of what this milestone means]

[Button: Celebrate Moment] [Button: Celebrate Together]

[If Together clicked, expand:]
Here are some ways you might talk to [Child]:
- [Suggestion 1 — observation/question]
- [Suggestion 2 — observation/question]
- [Suggestion 3 — observation/question]
[Skip]
```

---

## BRAND VOICE FOR MILESTONE LANGUAGE

**Tone:** Warm, clinical, observational, empowering
**Audience:** Parents (adults, focused on their child's growth)
**Key Values:** Competence, resilience, real-world application, therapist integration

**Example Phrasing:**
- "Alex is building consistency..."
- "This shows Maya is taking ownership..."
- "Jordan is ready for deeper work..."
- "Shows that..." (observation, not judgment)
- "Here's what this means therapeutically..." (education)

---

## CONTACT & CLARIFICATION

**Questions about:**
- **Design & UX?** See: `PROGRESS_ROAD_CELEBRATION_LAYER_DESIGN_v1.md`
- **Audio specs?** See: `CELEBRATION_AUDIO_AND_CODE_REFERENCE_v1.md`
- **Strategy & rationale?** See: `PROGRESS_ROAD_CELEBRATION_EXECUTIVE_SUMMARY_v1.md`

---

**Version:** 1.0 (Quick Reference)
**Last Updated:** March 30, 2026
**For:** Designers, Product, Developers, QA

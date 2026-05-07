# MindfulNest Voice Roster — LOCKED v2
**Date:** April 6, 2026
**Status:** All 12 character voices locked by Kim. Updated: Guide Bird → Chipper1, all voices → eleven_v3 with emotional direction tags.

---

## v2 Changes (April 6, 2026)

1. **Guide Bird voice replaced:** Ash (`VU16byTywsWv5JpI8rbc`) → Chipper1 (`7o9pyvsN0ob5GO6LBQp6`). Ash was too slow/droll. Kim tested Chipper2 first (overplayed), then Chipper1 (approved).
2. **All voices switched to `eleven_v3` model** with emotional direction audio tags `[tag]` for voice acting control.
3. **Voice settings standardized** for v3 emotional mode: Stability 0.30, Similarity 0.80, Style 0.30 (low stability = "Creative" mode for maximum expressiveness).
4. **All 146 Arc 1 dialogue lines regenerated** with v3 emotional tags. Output: `video_pipeline/audio/arc_1_v3/`

---

## Locked Voice Profiles

| Character | ElevenLabs Voice | Voice ID | Model | Settings | Notes |
|-----------|-----------------|----------|-------|----------|-------|
| **Myrrhin** (Narrator) | Myrrdin - Wise and Magical Narrator | `oR4uRy4fHDUGGISL0Rev` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Narrates Opening Storybook + ALL Phase B meditations. |
| **Guide Bird** | Chipper1 | `7o9pyvsN0ob5GO6LBQp6` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | **NEW voice (was Ash).** Warm, energetic, slightly self-deprecating. One voice across all arcs. Kim-approved April 6. |
| **Tessa** (turtle, M1) | Jessica - Playful, Bright, Warm | `cgSgspJ2msm6clMCkdW9` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Gentle, slightly shy, warm. Young female. |
| **Luna** (owl, M2) | Miranda | `PoHUWWWMHFrA8z7Q88pu` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Bright, intellectual, excitable. Young female with academic energy. |
| **Ember** (fox, M4) | Katie | `T720RsqorTx4ZZWohrNN` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Warm, kind, curious. Young female. |
| **Bramble** (bear, M6) | Northern Terry | `wo6udizrrtpIxWGp2qJk` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Gruff, practical, brief. Deep Irish accent. |
| **Benson** (bunny, M3) | Gigi | `n7Wi4g1bhpw4Bs8HK5ph` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Small, quiet, scared-but-brave. Very young male. |
| **Bork** (firefly, M5) | Bork2 | `zzePw2Fo1hmm1iJnqh4y` | eleven_v3 | Stability 0.20, Similarity 0.80, Style 0.40 | **NEW voice (was Matthew Schmitz).** Pompous, ridiculous, self-important. Lower stability + higher style for maximum theatrical absurdity. |
| **Oliver** (deer) | Brayden | `3XOBzXhnDY98yeWQ3GdM` | eleven_v3 | Stability 0.35, Similarity 0.80, Style 0.30 | **NEW voice (was Mark Natural).** Measured, earnest, quiet authority. Slightly higher stability (0.35) to prevent voice drift on longer lines. |
| **Grizzle/Agent** (deer) | Gotham Boss | `M9UAxraM2w5tCjpOaIB0` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Neutral, businesslike, not evil. Normalize volume in mixing. |
| **Lady Willow** (deer) | Alisha - Soft and Engaging | `ftDdhfYtmfGP0tFlBYA1` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Warm, regal, wise. Adult female. Arc 2. |
| **Mountain King** | Carter | `qNkzaJoHLLdpvgh5tISm` | eleven_v3 | Stability 0.30, Similarity 0.80, Style 0.30 | Arc 2. |

---

## Emotional Direction System (eleven_v3)

All dialogue is now scripted with inline emotional direction tags. Tags are placed in square brackets before the text they affect:

```
[bursting with relief and excitement] FINALLY!! I've been looking ALL over for you!
[trying to hold back tears, embarrassed] Oh... Hi... I'm sorry. I'm Tessa.
[quiet, carrying the weight of memory] They used to shine so bright...
```

### Key principles:
- Tags describe the **emotional state**, not acting instructions
- Multiple tags can appear within a single line for emotional shifts
- `[pause]` creates natural breathing pauses (replaces SSML `<break>` tags which don't work on v3)
- Low stability (0.30 = "Creative" mode) gives the model room to interpret emotional tags expressively
- Source fidelity: dialogue text is preserved verbatim from Kim's skeleton; only tags are added

### Tag reference (used across Arc 1):
- Excitement: `[bursting with excitement]`, `[delighted]`, `[thrilled]`
- Vulnerability: `[trying to hold back tears]`, `[voice breaking]`, `[barely audible]`
- Reflection: `[quiet, carrying the weight of memory]`, `[reflective]`
- Authority: `[commanding]`, `[formal]`, `[steady, informative]`
- Humor: `[playful skepticism]`, `[sarcastic, amused]`, `[teasing]`
- Discovery: `[realization dawning]`, `[lightbulb moment]`, `[eureka]`
- Caution: `[cautious]`, `[uneasy]`, `[slightly wary]`

---

## Audio Output Structure

All v3 audio lives in `video_pipeline/audio/arc_1_v3/` organized by event:

```
arc_1_v3/
├── event_0_storybook/          (7 files — Myrrhin)
├── event_0b_guidebird_intro/   (13 files — Guide Bird)
├── event_0c_map_landing/       (1 file — Guide Bird)
├── event_1_tessa_intro/        (7 files — Guide Bird, Tessa)
├── event_1_tessa_map/          (2 files — Tessa, Guide Bird)
├── event_1_tessa_hook/         (1 file — Guide Bird)
├── event_2_luna_intro/         (13 files — Luna, Tessa, Guide Bird)
├── event_2_luna_map/           (1 file — Luna)
├── event_2_luna_hook/          (1 file — Guide Bird)
├── event_3_ember_intro/        (16 files — Ember, Luna, Tessa, Guide Bird)
├── event_3_ember_resolution/   (1 file — Guide Bird)
├── event_3_ember_map/          (3 files — Tessa, Luna, Ember)
├── event_3_ember_hook/         (1 file — Guide Bird)
├── event_3b_oliver_meet/       (10 files — Oliver, Luna, Guide Bird)
├── event_3b_oliver_map/        (4 files — Oliver, Tessa, Luna, Ember)
├── event_3b_oliver_hook/       (1 file — Guide Bird)
├── event_4_bramble_intro/      (29 files — Bramble, Oliver, Ember, Tessa, Luna, Guide Bird)
├── event_4_bramble_map/        (2 files — Bramble, Luna)
├── event_4_bramble_hook/       (1 file — Guide Bird)
├── event_5_benson_intro/       (15 files — Oliver, Benson, Bramble, Luna, Tessa, Guide Bird)
├── event_5_benson_map/         (2 files — Benson, Luna)
├── event_5_benson_hook/        (1 file — Guide Bird)
├── event_6_bork_intro/         (7 files — Bork, Luna, Guide Bird)
├── event_6_bork_map/           (2 files — Bork, Luna)
├── event_6_bork_hook/          (1 file — Guide Bird)
└── event_7_agent/              (4 files — Ember, Luna, Bramble)
```

**Filename convention:** `{speaker}_{line_number:02d}.mp3`

---

## TTS Production Rules

These rules apply to ALL TTS generation for MindfulNest. Follow them every time dialogue is scripted or regenerated.

### Pronunciation Rules

| Written Form | TTS Script Form | Reason |
|-------------|----------------|--------|
| MindfulNest | Mindful-Nest | Hyphenated — sounds like one natural proper noun while keeping "Nest" distinct from "ness". Two separate words sounded awkward. |

*Add new pronunciation rules to this table as they are discovered during production.*

### Personalization Variables

Lines containing `{childName}`, `{therapistName}`, `{chosenGuideName}`, or any other personalization variable are **NOT generated as universal audio**. They are rendered per-child at runtime after variable substitution. When generating production audio batches, **skip personalized lines** or generate them with demo values (e.g., "Alex", "Dr. Sarah", "Mom") for review purposes only.

### Dialogue Changes Log

| Date | Line | Old | New | Reason |
|------|------|-----|-----|--------|
| April 6 | Tessa intro #2 | "I'm a turtle" | "I'm from Dragonshell" | Kim direction |
| April 6 | Luna intro #4 | "...Everdale?" | "...Everdale!" | Wrong cadence; should be exclamation |
| April 6 | Oliver meet #6 | "It expanded out to all the other Kingdoms, too" | "It went out all over the Kingdom" | Kim direction |

### Pacing

- Guide Bird lines need `[pause]` tags between sentences for natural breathing room
- Short exclamations (e.g., "Oh", "Huh", "What!!") should NOT have emotional tags longer than the dialogue itself
- Use `[pause]` for natural breathing pauses (replaces SSML `<break>` which doesn't work on v3)

### Voice Casting Notes

- **Oliver**: Brayden confirmed April 6. Mark Natural and Oliver2 both rejected (unnatural). Brayden uses stability 0.35 (not 0.30) to prevent voice drift on longer lines.
- **Bork**: Bork2 confirmed April 6. Matthew Schmitz rejected (too wise, not ridiculous enough). Bork2 uses stability 0.20 / style 0.40 for maximum theatrical pomposity.
- **Guide Bird**: Chipper1 confirmed. Chipper2 was tested but overplayed emotional tags.

---

## Previous Versions

- **v1** (April 6, 2026): Original roster with mixed models. Guide Bird was Ash on eleven_multilingual_v2. All voices had higher stability settings. No emotional direction tags.
- **Old audio** in `video_pipeline/audio/arc_1/` — 191 files generated with old models + raw text. Superseded by `arc_1_v3/`.

## Production Notes

- All volumes should be normalized to a consistent level in the mixing step
- Grizzle and Willow are notably quiet — normalize in post
- `[pause]` tags in v3 replace SSML `<break time="X">` (SSML breaks do NOT work on v3)
- Personalized lines use placeholder variables — segment-level rendering handles per-child versions at runtime
- The generation script is preserved at `/sessions/vibrant-focused-clarke/generate_all_v3_tts.py` for reference/re-runs

# MindfulNest Voice Roster — LOCKED
**Date:** April 6, 2026
**Status:** All 12 character voices locked by Kim

---

## Locked Voice Profiles

| Character | ElevenLabs Voice | Voice ID | Model | Settings | Notes |
|-----------|-----------------|----------|-------|----------|-------|
| **Myrrhin** (Narrator) | Myrrdin - Wise and Magical Narrator | `oR4uRy4fHDUGGISL0Rev` | professional | Stability 0.70, Similarity 0.80, Style 0.20 | Professional voice clone. Narrates Opening Storybook + ALL Phase B meditations. |
| **Guide Bird** | Ash - Calm, Soothing, Magnetic | `VU16byTywsWv5JpI8rbc` | eleven_multilingual_v2 | Stability 0.60, Similarity 0.80, Style 0.20 | Warm, energetic, slightly self-deprecating. One voice across all arcs. |
| **Tessa** (turtle, M1) | Jessica - Playful, Bright, Warm | `cgSgspJ2msm6clMCkdW9` | premade | Stability 0.65, Similarity 0.80, Style 0.15 | Gentle, slightly shy, warm. Young female. |
| **Luna** (owl, M2) | Miranda | `PoHUWWWMHFrA8z7Q88pu` | eleven_multilingual_v2 | Stability 0.50, Similarity 0.80, Style 0.25 | Bright, intellectual, excitable. Young female with academic energy. |
| **Ember** (fox, M4) | Katie | `T720RsqorTx4ZZWohrNN` | eleven_monolingual_v1 | Stability 0.50, Similarity 0.85, Style 0.0 | Warm, kind, curious. Young female. Mono model preserves expressiveness. |
| **Bramble** (bear, M6) | Northern Terry | `wo6udizrrtpIxWGp2qJk` | eleven_turbo_v2_5 | Stability 0.40, Similarity 0.85, Style 0.35 | Gruff, practical, brief. Deep Irish accent. Turbo model preserves accent. |
| **Benson** (bunny, M3) | Gigi | `n7Wi4g1bhpw4Bs8HK5ph` | eleven_multilingual_v2 | Stability 0.60, Similarity 0.80, Style 0.15 | Small, quiet, scared-but-brave. Very young male. |
| **Bork** (firefly, M5) | Matthew Schmitz | `0SpgpJ4D3MpHCiWdyTg3` | eleven_monolingual_v1 | Stability 0.65, Similarity 0.90, Style 0.0 | Pompous, dry, formal. British. Mono model preserves British accent. |
| **Oliver** (deer) | Mark - Natural Conversations | `UgBBYS2sOqTuMpoF3BR0` | eleven_monolingual_v1 | Stability 0.60, Similarity 0.85, Style 0.0 | Measured, earnest, quiet authority. May swap for younger voice later. |
| **Grizzle/Agent** (deer) | Gotham Boss | `M9UAxraM2w5tCjpOaIB0` | eleven_multilingual_v2 | Stability 0.70, Similarity 0.80, Style 0.10 | Neutral, businesslike, not evil. Volume is quiet — normalize in mixing. |
| **Lady Willow** (deer) | Alisha - Soft and Engaging | `ftDdhfYtmfGP0tFlBYA1` | eleven_monolingual_v1 | Stability 0.55, Similarity 0.85, Style 0.0 | Warm, regal, wise. Adult female. Volume is soft — normalize in mixing. Arc 2. |
| **Mountain King** | Carter | `qNkzaJoHLLdpvgh5tISm` | eleven_multilingual_v2 | Stability 0.70, Similarity 0.80, Style 0.10 | Arc 2. |

---

## Model Selection Guide

Different voices sound best on different models. The multilingual_v2 model tends to flatten accents and reduce expressiveness. When a voice sounds monotone or loses its accent:

- **eleven_monolingual_v1** — Best for preserving British accents and expressiveness (Bork, Ember, Oliver, Willow)
- **eleven_turbo_v2_5** — Best for preserving regional accents like Irish (Bramble)
- **eleven_multilingual_v2** — Works fine for voices that don't have strong accents or that sounded good in initial tests (Guide Bird, Luna, Benson, Grizzle, King)
- **premade voices** — Use their default model (Tessa/Jessica)

## Production Notes

- All volumes will be normalized to a consistent level in the mixing step
- Ellipses (`...`) in dialogue text create natural pauses — use deliberately
- Avoid splitting natural phrases across pause markers (learned from Oliver "than I can" split)
- Test lines used actual skeleton dialogue for character accuracy
- Voice test files preserved in `video_pipeline/voice_tests/` for reference

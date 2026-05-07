# Lessons Learned: Line 11 Animation (Guide Bird) — Chinese Lip-Sync Artifact

**Date:** April 14, 2026
**Beat:** Line 11 — Guide Bird speaks to child ("OK Alex. Let's practice a real magic spell!")
**Status:** Failed generations → fresh restart needed

---

## What Happened

Multiple animation generations for Line 11 (Guide Bird close-up, speaking to child) produced **Chinese-phoneme lip-sync artifacts** — the bird's beak animated as if speaking Chinese dialogue, despite prompts explicitly requesting closed beak and silent movement.

## Root Cause

**ByteDance Seedance v1.5 Pro has a talking-head bias baked into its model weights.** This is not a prompt issue — it's a model architecture issue. The bias:
- Activates on any face/beak close-up
- Generates mouth/beak movement synchronized to phantom Chinese phonemes
- Cannot be fully suppressed by negative prompts or API parameters alone
- Is especially triggered by close-up framing (the exact framing Line 11 needs)

## What Was Tried (and Failed)

1. **Anti-lip-sync prompt language** — "Beak closed, no speech, no lip movement" → Still produced lip sync
2. **API parameter `sound: false`** → Did not prevent visual lip-sync generation
3. **Negative prompt including "Chinese"** → Reduced but did not eliminate
4. **Multiple seed variations** → All seeds produced the same lip-sync artifact

## What Works

**Switch to Kling v3.0 Pro.** Kling is a general motion model with NO talking-head bias. Same WaveSpeed API key — switching is one endpoint string change:
- Seedance: `bytedance/seedance-v1.5-pro/image-to-video`
- **Kling: `kwaivgi/kling-v3.0-pro/image-to-video`**

## Locked Rules Going Forward (CLAUDE.md Rule 8)

### Default Model: Kling v3.0 Pro
- Via WaveSpeed (`kwaivgi/kling-v3.0-pro/image-to-video`) or EvoLink (`api.evolink.ai`)
- Seedance only when Kim explicitly requests it, with mandatory Lip-Sync Review Gate

### Anti-Lip-Sync Safeguards (ALL models, ALWAYS ON)

**Banned words in ALL motion prompts:**
`speaking`, `speech`, `dialogue`, `lip sync`, `lip movement`, `mouth movement`, `beak movement`, `talking`, `singing`, `vocal`

**Required prompt constraints (bird characters):**
- `"Beak closed, no speech, no lip movement"`
- End with: `"Silent subtle idle movement only"` or `"no dialogue in video"`

**API parameters:**
```
sound: false
negative_prompt: "lip sync, speaking, talking, mouth movement, dialogue, speech, open mouth, Chinese, audio, voice, singing"
cfg_scale: 0.5
```

## Strategy for Fresh Restart (This Session)

1. **Pick a different Guide Bird source image** — slightly different pose/angle to break any cached association
2. **Use Kling v3.0 Pro exclusively** — no Seedance
3. **Craft motion prompt focused on body language, NOT face** — describe wing flutter, head tilt, weight shift — keep attention away from beak area
4. **Generate 3 options with different seeds** — pick best idle motion
5. **Review gate before delivery** — scrub frame-by-frame for any mouth/beak movement

## Cost Reference

- Kling via WaveSpeed: ~$0.10/second
- Kling via EvoLink: ~$0.375 per 5-second clip (27 credits)
- 3 options for Line 11 = ~$1.13 (EvoLink) or ~$1.50 (WaveSpeed)

---
name: beat-kling-prompt-author
description: Claude Kling O3 prompt author for MindfulNest Extract beats Phase B.
---

# Beat Kling prompt author (Phase B)

Convert approved **dialogue** beats into Event-1-quality `kling_o3_prompt` strings.

## Skip (handled by tooling)

- `beat_type: stage_still` — pre-built still-insert prompt; do not call author.
- Empty dialogue stage_direction rows.

## Required structure (dialogue beats)

1. `@Image1 ({Speaker}) {Role}. Scene from @Image2.`
2. **Camera:** static locked medium shot (verbatim lock block).
3. Micro-expression staging from `scene_notes` — face/body only, solo @Image1.
4. Voice/delivery + spoken dialogue with **emotion bracket tag** inside quotes, e.g. `"[warm, to camera] Hello..."`.
5. Storybook style tail + audio/solo-shot locks.

## Tool output (`submit_kling_prompts`)

Return for every dialogue beat_index:

- `kling_o3_prompt` — full multi-line prompt
- `emotion` — delivery tag (bracket form OK)
- `scene_notes` — simple micro-expression staging (eyes widen, rooted in place)

## Cast

- **Lorelai** (lemur) — Element registry key Lorelai
- **Arlo** — guide; Arlo to-camera beats use viewer off-screen lock
- **Tessa** — turtle

Never Luna or Chipper in prompts.

## Staging rules

Same as planner: no camera moves, no locomotion, no second character in frame.

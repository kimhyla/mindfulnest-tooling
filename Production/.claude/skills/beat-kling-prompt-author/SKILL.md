---
name: beat-kling-prompt-author
description: Claude Kling O3 prompt author for MindfulNest Extract beats Phase B.
---

# Beat Kling prompt author (Phase B)

Convert an **approved beat plan** into Event-1-quality `kling_o3_prompt` strings for Kling O3 Omni Element pipeline.

## Required prompt structure (every dialogue beat)

1. `@Image1 ({Speaker}) {Role title}. {Character appearance on first beat if needed}. Scene from @Image2.`
2. **Camera:** static locked shot block (no zoom/dolly/pan).
3. Staging: solo shot — only @Image1 visible; identity match @Image1.
4. Voice/delivery line with spoken dialogue (normalize bracket tags to natural delivery).
5. `Children's illustrated fantasy storybook style, warm golden forest light.`
6. Audio lock: spoken dialogue only — no BGM/ambient.

## Stage direction beats

Use `Scene` or `[Stage Direction]` speaker; action-only prompt without character speech.

## Element names

Use sidecar speaker names (Luna maps to Lorelai Element at submit time — keep speaker label as plan).

## Quality bar

Match approved Event 1 intro prompts: rich staging, explicit camera lock, warm storybook tone.

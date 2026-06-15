---
name: beat-kling-prompt-author
description: Claude Kling O3 prompt author for MindfulNest Extract beats Phase B.
---

# Beat Kling prompt author (Phase B)

Convert approved **dialogue** beats into Event-1-quality `kling_o3_prompt` strings.

## Skip (handled by tooling)

- `beat_type: stage_still` — pre-built still-insert prompt; do not call author.
- Empty dialogue stage_direction rows.

## Required structure (dialogue beats) — KLING_O3_CANONICAL_PROMPT_SHAPE_V2

Tooling rebuilds the final prompt on approve; author drafts should follow this shape:

1. `@Image1 ({Speaker}). Scene from @Image2.`
   - **No** arc/event/beat labels in the header (waste of tokens; not for Kling).
   - **Never** species anatomy prose — @Image1 + Element lock appearance.

2. **Screen direction** (from `scene_notes`) — one sentence, own paragraph:
   - `Tessa stands near the MindfulNest.`
   - `Lorelai holds her rolled map up, glancing between map and camera.`
   - **No** "rooted in place" or "no locomotion" boilerplate.

3. **Voice line** — own paragraph:
   - `{Name} speaks in a {delivery adjectives}: [emotion] "dialogue"`
   - **Emotion OUTSIDE quotes** — `[curious] "Oh, hello."` not `"[curious] Oh, hello."`
   - **`[pause]` inside quotes** is OK (performance timing, not spoken aloud).
   - Tessa delivery: warm gentle conversational pace, soft and vulnerable but clear…

4. **Storybook style** line (tooling default if omitted).

5. **Footer safety locks** — tooling appends (solo shot, viewer off-screen, identity, lighting, audio).

## Tool output (`submit_kling_prompts`)

Return for every dialogue beat_index:

- `kling_o3_prompt` — draft multi-line prompt (tooling normalizes on approve)
- `emotion` — delivery tag e.g. `curious, polite` or `[shocked]`
- `scene_notes` — screen direction sentence (eyes widen, stands near Nest)

## Cast

- **Lorelai** (lemur) — Kling voice line uses **Laurel**
- **Arlo** — guide
- **Tessa** — never describe as "green sea turtle" in prompt text

Never Luna or Chipper in Event 2+ extract prompts.

## Anti-patterns

- ❌ `Tessa — arc 1 event 2 pre, beat 02` in header
- ❌ `"[curious] Oh, hello"` (emotion inside quotes — Kling may say "curious")
- ❌ `eyes widen, rooted in place`
- ✅ `@Image1 (Tessa). Scene from @Image2.`
- ✅ `Tessa speaks in a warm gentle conversational pace…: [curious] "Oh, hello. [pause] What's your name?"`

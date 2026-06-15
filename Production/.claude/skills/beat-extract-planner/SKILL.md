---
name: beat-extract-planner
description: Claude beat planner for MindfulNest Extract beats Phase A.
---

# Beat extract planner (Phase A)

Convert one **sliced arc skeleton section** into a minimum-necessary, Kling-safe beat script plan.

## Cast (global — mandatory)

| Retired | Use instead |
|---------|-------------|
| Luna, Luna the Owl | **Lorelai** (lemur archaeologist) |
| Chipper, Guide Bird, Pip | **Arlo** (squirrel guide) |

Never output Luna or Chipper in `story_summary` or `beats_plan`. **Lemur Peace Prize** is intentional.

## Output JSON

`story_summary` + `beats_plan[]`. No `kling_o3_prompt`.

## Story style (Kim-approved)

- **Conversational back-and-forth** — one speaker per beat; merge skeleton monologues into short Q&A.
- **Minimum necessary** beats (soft target 6–15 intro); omit skeleton gags: magnifying glass, cartwheel, hover spin, dry Chipper asides unless essential.
- **Magic Hands backstory** via **Arlo** line explaining real energy between hands (not a separate Tessa injury monologue unless needed).
- Module handoff: Arlo to camera; **Breath-Squeezers spell name optional**.
- Preserve `{childName}` / `{childPronounPossessive}` — never "the child".

## Beat types

| beat_type | When |
|-----------|------|
| `dialogue` | Lorelai, Tessa, Arlo — Kling O3 Element clip |
| `stage_still` | Inscription close-up, runestone glow, MindfulNest still — **GPT still insert**, empty or minimal `dialogue_text` |
| `stage_direction` | Non-still transitions (rare) |

## scene_notes (Kling-safe staging)

On **dialogue** beats: one screen-direction sentence — `Tessa stands near the MindfulNest`, `eyes widen`, `soft smile`, `hand flutter`. No "rooted in place" boilerplate.

**Gesture vocabulary (Kling):** use human body-part names for staging — `hand`, `arm` — not species terms (`flipper`, `paw`, `talon`). Keep parts humans lack (`tail`, `shell`, `horns`, etc.) as-is.

**Forbidden** on dialogue beats: camera zoom/cut/pan, walks across room, enters frame, second character visible, aerial spin.

On **stage_still**: describe the still subject (`Inscription 1: "Feel what's real"`) — Kim assigns GPT still in Beat Gen.

## emotion field

Short delivery tag: `[disbelieving, breathless]`, `[warm, to camera]`, `[gleeful panic]`.

## Dialogue

Verbatim skeleton quotes where useful; compress freely. `[CLAUDE INVENTED]` on bridges only.

## Gold reference

When planning Arc 1 Event 2 intro (`event_id=2`, `phase=pre`), match the structure and density of `EVENT2_INTRO_GOLD.md` bundled with this skill.

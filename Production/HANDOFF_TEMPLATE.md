# MindfulNest Session Handoff Template
**Purpose:** Copy this template, fill in the bracketed fields, and paste into a new thread to ensure zero-context-loss session transitions.

**When to use:** At the END of every session, before context runs out. Also use when Kim says "handoff," "new thread," "wrap up," or "continue in next session."

---

## HANDOFF PROMPT (copy everything below this line)

---

You are continuing a MindfulNest production session. Read CLAUDE.md and `.auto-memory/MEMORY.md` FIRST — they are the system of record.

### Session Context
**Date:** [TODAY'S DATE]
**What we were working on:** [1-2 sentence summary of the session's main task]
**Where we left off:** [Specific point — e.g., "M1 audio: voice stem v5 generated, Kim hasn't auditioned yet"]

### Completed This Session
[Bullet list of what was accomplished — be specific with filenames and version numbers]
- [e.g., "Built storyboard_v11.html via JS-only patch (preserved all 14 base64 images from v10)"]
- [e.g., "Updated CLAUDE.md Rule 6 — now Two-Path Protocol with 7 validated fixes from 10-agent audit"]
- [e.g., "Created root principle memory: principle_preserve_authored_state.md"]

### Pending / Next Steps
[What the next session should do FIRST — be specific]
- [e.g., "Kim needs to test Export Locked Sequence button in storyboard_v11"]
- [e.g., "Next production step: Kim auditions voice stem v5 and 5 gong candidates"]

### Critical State (prevents re-work)
[Key decisions, locked choices, or state that must NOT be re-done]
- [e.g., "Storyboard v11 images are Kim's hand-selected choices — do NOT rebuild from disk files"]
- [e.g., "Dashboard storyboard fields are live: M1 = current, v11, js_patch mode"]
- [e.g., "10 locked audio decisions in prod_audio_locked_decisions — query before any audio work"]

### Files Changed This Session
[Every project file created or modified — full filenames. Do NOT include .auto-memory files here.]
- [e.g., "CLAUDE.md — Rule 6 rewritten (Two-Path Protocol)"]
- [e.g., "Production/Event_1/storyboard_v11.html — JS-patched from v10"]
- [e.g., "Production/tools/build_storyboard.py — export panel updated"]

### Memory Files Changed
[Every .auto-memory file created or modified — separate from project files for quick scanning]
- [e.g., ".auto-memory/principle_preserve_authored_state.md — NEW (root principle)"]
- [e.g., ".auto-memory/feedback_never_surgical_html_injection.md — Updated (Path B cross-reference)"]
- [e.g., ".auto-memory/reference_storyboard_tool.md — Updated"]

### Active Warnings
[Any known issues, gotchas, or things to watch out for]
- [e.g., "storyboard-producer skill is installed but hasn't been test-fired in a live session yet"]
- [e.g., "Export Locked Sequence format not yet documented in PIPELINE_BRAIN"]

### Dashboard State
[Current Directus state for the module(s) being worked on — include even if unchanged, to confirm the session queried the dashboard]
- [e.g., "M1: stage=audio, status=in_progress, storyboard_status=current, storyboard_version=11"]
- [e.g., "prod_visual_assets: IDs 12-21 (TTS audio), ID 22 (audition player)"]

### Voice Roster (include for audio/video sessions)
[ElevenLabs voice IDs and settings for characters used this session — prevents re-selection and drift]
| Character | Voice ID | Voice Name | Stability | Similarity | Style |
|-----------|----------|------------|-----------|------------|-------|
| [e.g., Guide Bird] | [e.g., `7o9pyvsN0ob5GO6LBQp6`] | [e.g., Chipper1] | [e.g., 0.30] | [e.g., 0.80] | [e.g., 0.30] |

### Reference Docs Registry Changes This Session
- **New files registered:** [list or "none"]
- **Files deleted/moved:** [list or "none"]
- **Registry updates (renames, path corrections):** [list or "none"]
- **Unresolved sync issues:** [list or "none"]

### Mandatory First Actions for Next Session
1. Run registry sync check (CLAUDE.md Rule 15 — structural sync of prod_reference_docs vs. disk)
2. Run 4-step sanity check (CLAUDE.md Session Start protocol — read handoff notes, query Directus for module state + storyboard freshness, smoke-test if visual work planned, report briefly)
3. Run `build_storyboard.py --smoke-test` if visual work is planned
4. Execute 7-query session start protocol (PIPELINE_BRAIN Part 1B) if production work is planned
5. [Any session-specific first action, e.g., "Ask Kim if she tested the export button"]

---

## TEMPLATE NOTES (do not include in handoff)
- Fill ALL bracketed fields. Empty brackets = context loss.
- Be specific with filenames and version numbers — "the storyboard" is ambiguous, "storyboard_v11.html" is not.
- Include the Dashboard State section even if nothing changed — it confirms the session queried the dashboard.
- The "Critical State" section prevents the #1 failure mode: the next session re-doing work Kim already approved.
- Keep the handoff under 1 page. If it needs more, the session probably should have been split.

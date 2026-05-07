# Session Handoff — April 13, 2026 (Session 2 — Supersedes HANDOFF_20260413.md)

Copy everything below and paste as the first message in a new thread.

---

You are continuing a MindfulNest production session. Read CLAUDE.md and `.auto-memory/MEMORY.md` FIRST — they are the system of record.

### Session Context
**Date:** April 13, 2026 (combined handoff covering both Session 1 and Session 2)
**What we were working on:** Session 1 fixed 5 storyboard production failures and hardened CLAUDE.md Rule 6. Session 2 produced all M1 Event 1 Story Scene TTS audio (10 lines), built permanent TTS audition workstation with Save to Disk, registered everything in Directus, wrote VIDEO_PRODUCTION_LESSONS_LEARNED_v6, and cascaded all decisions to PIPELINE_BRAIN, skills, and memory files.
**Where we left off:** All production tooling is verified and persistent. Kim's next production step is storyboard work — fire the storyboard-producer skill.

### Completed This Session (Session 1 — Storyboard Hardening)
- Fixed 5 storyboard production failures (drag-drop loss, base64 truncation, registry not wired, image scrambling from disk path guessing, export button not scrolling)
- Built `storyboard_v11.html` via JS-only patch from v10 — all base64 images preserved byte-identical
- Rewrote CLAUDE.md Rule 6 as **Two-Path Protocol** (Path A: builder for structural/image changes, Path B: JS patches for behavior fixes)
- Ran 10-agent adversarial audit — validated 8 real gaps, rejected 12 theoretical ones
- Created `principle_preserve_authored_state.md` root principle memory
- Created and installed `storyboard-producer` skill (fire-it-all-up pipeline: smoke test → registry → audit → build → verify → open)
- Added 4 storyboard tracking fields to Directus `prod_modules`
- Added Step 8 (storyboard freshness check) to CLAUDE.md staleness scan
- Created permanent handoff template at `Production/HANDOFF_TEMPLATE.md`

### Completed This Session (Session 2 — TTS Audio + Lessons Cascade)
- Produced 10 Story Scene TTS lines for M1 Event 1 (Tessa + Guide Bird) — all approved by Kim
  - Voice IDs: Guide Bird = `7o9pyvsN0ob5GO6LBQp6` (Chipper1), Tessa = `cgSgspJ2msm6clMCkdW9` (Jessica)
  - Settings: stability 0.30, similarity 0.80, style 0.30, model eleven_v3
  - Output: `Production/Event_1/story_scene_tts_v2/` (10 MP3 files)
  - Directus: registered as prod_visual_assets IDs 12-21
- Re-rendered 3 lines (3, 8, 10) that were lost when browser tab navigated away
- Built permanent TTS Audition Workstation:
  - Script: `Production/tools/build_tts_review.py` (upgraded from v1 to v3)
  - Config: `Production/Event_1/tts_audition_config.json` (Directus ID 23)
  - Player: `Production/Event_1/tts_audition_player_v3.html` (Directus ID 22)
  - Features: click-to-play, editable text, ElevenLabs regen, Save to Disk (pulsing green), Approve/Redo, Export Verdicts, Save All Approved
- Wrote VIDEO_PRODUCTION_LESSONS_LEARNED_v6.md — 7 new sections (25-31)
- Cascaded ALL decisions to:
  - `PIPELINE_BRAIN_v1.md` — TTS audition section, build_tts_review.py tool section, Tool Persistence Checklist (Part 4B-2), present_files file delivery method
  - `video-producer` skill — Step 2b (TTS Audition), fixed script name, added present_files delivery note
  - `audio-producer` skill — Story Scene note, present_files delivery for non-audio files
  - `storyboard-producer` skill — fixed `details` field to use JSON object (not string) for prod_activity_log
  - `.auto-memory/reference_tts_audition_tool.md` — NEW
  - `.auto-memory/reference_tool_persistence_checklist.md` — NEW
  - `.auto-memory/project_directus_schema_quirks.md` — added prod_activity_log schema (action/details)
  - `.auto-memory/feedback_open_files_for_kim.md` — rewritten to prioritize present_files
  - `.auto-memory/MEMORY.md` — updated index entries
- Ran 10-agent adversarial verification on tool persistence (5 verifiers + 5 counter-agents)
- Ran 5-point consistency verification — all PASS

### Pending / Next Steps
1. **Fire the storyboard-producer skill for M1 Event 1** — Kim wants to test the full pipeline end-to-end
2. Kim needs to test Export Locked Sequence button in storyboard_v11.html (scroll + flash + Copy + Download JSON)
3. Kim needs to confirm all images in v11 are her correct selections
4. Next audio step: M1 Phase B voice stem v5 audition + gong candidates (see `project_m1_audio_handoff.md`)
5. Export Locked Sequence format should be documented in PIPELINE_BRAIN (currently undocumented)

### Critical State (prevents re-work)
- **Storyboard v11 images are Kim's hand-selected choices** — do NOT rebuild from disk files. Use JS-only patches for behavior changes. If a full rebuild is needed, extract images FROM the current HTML.
- **10 Story Scene TTS lines are approved** — Directus IDs 12-21. Do NOT re-render unless Kim requests specific changes.
- **CLAUDE.md Rule 6 is Two-Path Protocol** — NOT "Builder-Only." Path A = builder for structural changes. Path B = JS patches for behavior fixes.
- **Dashboard storyboard fields are live:** M1 = current, v11, js_patch mode
- **10 locked audio decisions** in `prod_audio_locked_decisions` — query before any audio work
- **Audio delivery to Kim:** QuickTime Player via Finder (right-click → Open With). NEVER computer:// links.
- **All other file delivery:** `present_files` MCP tool ONLY. computer:// links, Finder navigation, Chrome file://, raw paths all FAIL in Cowork.
- **Directus prod_activity_log schema:** `action` (required text) + `details` (jsonb object). NOT `description`/`status`.
- **Root principle:** `principle_preserve_authored_state.md` — any rebuild of ANY file must preserve ALL authored state
- **Tool persistence checklist:** 7 locations for any new production tool (see `.auto-memory/reference_tool_persistence_checklist.md`)
- **ElevenLabs pause tags:** `[pause]` works. SSML `<break>` does NOT work. `[state]` tags for emotional rendering.
- **TTS audition config-driven:** To rebuild audition player, just `cd Production/Event_1 && python3 ../tools/build_tts_review.py --config tts_audition_config.json --output audition_player.html`. The cd is required — relative audio paths only resolve from Event_1 dir.

### Files Changed This Session (Both Sessions Combined)
- `CLAUDE.md` — Rule 6 rewritten (Two-Path Protocol), Step 8 added to staleness scan
- `Production/Event_1/storyboard_v10.html`, `storyboard_v11.html` — storyboard versions
- `Production/Event_1/story_scene_tts_v2/` — 10 approved TTS MP3 files
- `Production/Event_1/tts_audition_config.json` — NEW (permanent config for audition player)
- `Production/Event_1/tts_audition_player_v3.html` — NEW (audition workstation with regen + save)
- `Production/tools/build_storyboard.py` — export panel updated
- `Production/tools/build_tts_review.py` — upgraded v1→v3 (regen, save to disk, verdicts)
- `Production/PIPELINE_BRAIN_v1.md` — TTS audition section, build_tts_review.py tool section, Tool Persistence Checklist (Part 4B-2), present_files delivery method
- `Production/VIDEO_PRODUCTION_LESSONS_LEARNED_v6.md` — NEW (7 new sections: 25-31)
- `Production/HANDOFF_TEMPLATE.md` — NEW (permanent template for all future handoffs)
- `.claude/skills/video-producer/SKILL.md` — Step 2b TTS Audition, fixed script name, present_files
- `.claude/skills/audio-producer/SKILL.md` — Story Scene note, present_files for non-audio
- `.claude/skills/storyboard-producer/SKILL.md` — fixed details field to JSON object

### Memory Files Changed
- `.auto-memory/principle_preserve_authored_state.md` — NEW (root principle)
- `.auto-memory/reference_tts_audition_tool.md` — NEW (build_tts_review.py reference)
- `.auto-memory/reference_tool_persistence_checklist.md` — NEW (7-point checklist)
- `.auto-memory/reference_handoff_template.md` — NEW
- `.auto-memory/project_storyboard_dashboard_tracking.md` — NEW
- `.auto-memory/project_directus_schema_quirks.md` — Updated (activity_log schema)
- `.auto-memory/feedback_open_files_for_kim.md` — Rewritten (present_files primary)
- `.auto-memory/feedback_never_surgical_html_injection.md` — Updated (Path B cross-reference)
- `.auto-memory/feedback_preserve_kim_storyboard_edits.md` — Rewritten
- `.auto-memory/reference_storyboard_tool.md` — Updated
- `.auto-memory/reference_storyboard_builder_modes.md` — Updated
- `.auto-memory/MEMORY.md` — Updated index (TTS Audition Tool, Tool Persistence Checklist entries)

### Active Warnings
- **storyboard-producer skill has NOT been test-fired end-to-end** in a live production session yet — Session 2 was TTS/cascade work, not storyboard production. The next session should fire it.
- Export Locked Sequence output format not yet documented in PIPELINE_BRAIN
- v10 storyboard still on disk — keep as rollback target until Kim approves v11
- PIPELINE_BRAIN has 3 versions on disk (v1, v2, v3) — **v1 is current** per CLAUDE.md. v2 and v3 are stale drafts from prior sessions. Do not edit v2 or v3.
- `build_tts_review.py` MUST be run from the Event directory (`cd Production/Event_1`) for relative audio paths to resolve. Running from elsewhere produces a skeleton HTML with 0 audio blocks and no error.
- **Directus NULL module_id:** `prod_visual_assets` records created this session had NULL module_id initially — were PATCHed to module_id=1. Check if any NEW assets registered in future sessions also need module_id set explicitly.
- **Storyboard-producer pipeline sub-steps** (in execution order): smoke test → registry image query → audit previous version → build via Python builder → feature regression check → post-build verification → deliver to Kim via present_files. Do NOT skip or reorder steps.

### Dashboard State
- M1: stage=audio, status=in_progress, storyboard_status=current, storyboard_version=11, storyboard_build_mode=js_patch
- M2-M6: storyboard_status=not_started (expected — only M1 is in production)
- prod_visual_assets: IDs 12-21 (TTS audio), ID 22 (audition player), ID 23 (audition config)
- Directus smoke test: PASS (auth, query, schema all green as of this session)

### Voice Roster (M1 Event 1 — Locked)
| Character | Voice ID | Voice Name | Stability | Similarity | Style |
|-----------|----------|------------|-----------|------------|-------|
| Guide Bird | `7o9pyvsN0ob5GO6LBQp6` | Chipper1 | 0.30 | 0.80 | 0.30 |
| Tessa | `cgSgspJ2msm6clMCkdW9` | Jessica | 0.30 | 0.80 | 0.30 |
| Myrrhin (Phase B) | `oR4uRy4fHDUGGISL0Rev` | — | 0.70 | 0.80 | 0.20 |

### Mandatory First Actions for Next Session
1. Read CLAUDE.md and `.auto-memory/MEMORY.md`
2. Run staleness scan (CLAUDE.md Session Start protocol — includes Step 8 storyboard freshness)
3. Run `build_storyboard.py --smoke-test` for storyboard work
4. Execute 7-query session start protocol (PIPELINE_BRAIN Part 1B) for any production work
5. Ask Kim: "Did you test the Export Locked Sequence button in v11? Are all images correct?"
6. **Fire the storyboard-producer skill for M1 Event 1** when Kim is ready

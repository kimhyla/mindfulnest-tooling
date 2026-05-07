You are continuing a MindfulNest production session. Read CLAUDE.md and `.auto-memory/MEMORY.md` FIRST — they are the system of record.

### Session Context
**Date:** April 14, 2026
**What we were working on:** Speed optimization decisions → QA validator suite (full build, calibration, pipeline integration) → Production Architecture Master update → planning next pipeline container.
**Where we left off:** Validator suite v1.0 deployed. Architecture Master updated to v2 (Two-Write Rule + QA validators in testing protocol). Kim requested we build a unified reference image selector + cropper container.

---

## TASK 1: Build Reference Image Selector + Cropper Container ← PRIMARY TASK

**The Architecture Master has already been updated** (`PRODUCTION_ARCHITECTURE_MASTER_v2.md`). Read it FIRST — especially Part 6 (prescriptive checklist for new tools). Then build this:

Kim wants a **single unified HTML container** that handles the full image-selection-to-crop pipeline on one screen:

**What it should do:**
- Select reference images (master source images) for a module/event — similar to how the storyboard tool handles image assignment per dialogue line
- Crop selected masters into 4:3 close-ups (the existing cropper functionality from `build_cropper.py`)
- All on one screen — not two separate tools
- Integrated with Directus registry (`prod_visual_assets`) — reads available images from registry, writes crops back to registry
- Follow ALL architecture requirements from Part 6.2 of `PRODUCTION_ARCHITECTURE_MASTER_v2.md` (base64 embedding, localStorage, export JSON, Two-Write Rule for Directus registration, `--smoke-test`, `--audit`, `--audit-previous`, dark theme, etc.)
- Run QA validators on the built HTML output (Part 6.6 step 7)

**Existing tools to reference/merge:**
- `Production/tools/build_cropper.py` (797 lines) — the current standalone cropper
- `Production/Event_1/cropper_tool.html` — example output
- `Cropper/` folder — contains previous cropper outputs (tessa_initial_recrop.html, guidebird_sideview_cropper.html, etc.)
- The storyboard builder's image-selection UX — for reference on how to present image choices from Directus

**Key constraints:**
- CLAUDE.md Rule 6: minimum 600px shortest side on all crops
- CLAUDE.md Rule 7: Two-Path Protocol applies — build via Python builder, never edit HTML directly
- `.auto-memory/feedback_single_master_crop.md` — crop from ONE master for consistency; never generate per-character stills
- `.auto-memory/project_crop_aspect_ratio.md` — all crops must be 4:3 (iPad-optimized)
- Follow the 7-location persistence checklist (`.auto-memory/reference_tool_persistence_checklist.md`)

**Build approach:**
- Use agents/counteragents for architecture design before writing code
- Follow Part 6 prescriptive checklist from `PRODUCTION_ARCHITECTURE_MASTER_v2.md`
- Run QA validators on the built HTML output
- Open finished tool in Finder for Kim

---

## TASK 1b: Review Part 7 Priority Order (Optional)

Part 7 of the architecture doc lists "What To Build Next" in priority order. The **speed optimization batching strategy** (SPEED-* decisions, now in Directus) changes the production approach from module-by-module to arc-level batching by work type. Check if Part 7's priorities need reordering and update in v2 if so. This is lower priority than the container build.

---

## WHAT WAS ALREADY DONE (Architecture Master Update)

The Production Architecture Master was updated from v1 → v2 this session. Two changes:

1. **Part 6.2** — The auto-registration checkbox was expanded to name the **Two-Write Rule**: every asset output must write to BOTH `prod_visual_assets`/`prod_audio_assets` AND `prod_activity_log`. This was previously implicit; now it's an explicit named rule. (Originated from the "Mindfulness App Development Strategy Review" session which added 13 registration blocks to video-producer and audio-producer skills.)

2. **Part 6.6** — New step 7 added to Testing Protocol: run QA validators on output via `pipeline.py --validate`, with `--skip-validators` kill switch reference.

Both changes were verified by a counteragent (5/5 checks passed, no unintended modifications to other sections).

---

## PREVIOUS SESSION: Completed Work

### Completed This Session
- Uploaded all 18 SPEED-* decisions to Directus `prod_session_decisions` collection
- Built `Production/validators/` — 9 Python files + schemas directory (full QA validator suite)
- Wired validators into `Production/tools/pipeline.py` (validate_output(), --skip-validators, --validate)
- Calibrated against 322 production artifacts: 0 Tier 1 blockers, 47 Tier 2 warnings
- Counteragent reviewed validators: added truncation detection, channel count check, auto-fix backup
- Created `MINDFULNEST_SPEED_OPTIMIZATION_v2_April2026.html` interactive report
- Updated `PRODUCTION_ARCHITECTURE_MASTER_v1.md` → v2 (Two-Write Rule + QA validators)
- Reviewed "Troubleshoot purchase limit issue" and "Mindfulness App Development Strategy Review" conversations for architecture conflicts — found none; only the Two-Write Rule needed explicit naming
- Logged VALIDATOR-DEPLOY decision to Directus

### Critical State (prevents re-work)
- QA validators are LIVE in pipeline.py — they run silently. Do not rebuild them.
- Kill switch: `pipeline.py --skip-validators` if validators block production unexpectedly
- Validator thresholds calibrated against real artifacts. Don't change without re-running calibration.
- Auto-fix scope: ONLY unicode ellipsis → ASCII. Do not expand per Source Fidelity Protocol.
- All 18 SPEED-* decisions are in Directus and LOCKED (except SPEED-D → update to LOCKED, SPEED-F → BACKBURNER)
- `PRODUCTION_ARCHITECTURE_MASTER_v2.md` is now current. v1 is preserved but superseded.
- M1 Tessa is at pipeline stage `audio` / `in_progress` — voice stem v5 and gong candidates await Kim's audition

### Files Changed This Session
- `Production/validators/` — 9 NEW files + schemas/ directory (full validator suite)
- `Production/tools/pipeline.py` — MODIFIED (validator integration)
- `Production/PRODUCTION_ARCHITECTURE_MASTER_v2.md` — NEW (versioned-up from v1, Two-Write Rule + QA validators)
- `CLAUDE.md` — MODIFIED (speed optimization section)
- `MINDFULNEST_SPEED_OPTIMIZATION_v2_April2026.html` — NEW
- `Production/SESSION_HANDOFF_20260414_final.md` — NEW (this file)

### Memory Files Changed
- `.auto-memory/project_speed_optimization_plan.md` — NEW
- `.auto-memory/project_validator_suite.md` — NEW
- `.auto-memory/MEMORY.md` — UPDATED (speed optimization + validator entries)

### Active Warnings
- `_step_tts` in pipeline.py is still a stub — requires audio-producer skill until implemented
- SPEED-D status in Directus still shows PENDING — update to LOCKED
- Counteragent noted Tier 1 checks may be slightly loose — monitor in production

### Dashboard State
- M1: stage=audio, status=in_progress (unchanged — session was infrastructure)
- prod_session_decisions: 18 SPEED-* entries + 1 VALIDATOR-DEPLOY entry

### Mandatory First Actions for Next Session
1. Run staleness scan (CLAUDE.md Session Start protocol)
2. Read `Production/PRODUCTION_ARCHITECTURE_MASTER_v2.md` — especially Parts 1, 6, and 7
3. Begin reference image selector + cropper container design (agents/counteragents first, code second)
4. Follow Part 6 checklist and 7-location persistence checklist throughout the build

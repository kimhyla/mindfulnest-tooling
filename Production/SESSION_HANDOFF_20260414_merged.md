You are continuing a MindfulNest production session. Read CLAUDE.md and `.auto-memory/MEMORY.md` FIRST — they are the system of record.

### Session Context
**Date:** April 14, 2026
**What we were working on:** Speed optimization decisions → QA validator suite (full build, calibration, pipeline integration) → planning next pipeline container.
**Where we left off:** Validator suite v1.0 fully deployed and verified. Kim then requested we build a new pipeline container for **reference image selection + cropping** (merged into one screen), integrated with Directus registry. Before building, Kim wants us to review and update the Production Architecture Master document.

---

## TASK 1: Review & Update Production Architecture Master

Kim has a "how to build new pipeline components" document: `Production/PRODUCTION_ARCHITECTURE_MASTER_v1.md`. It contains 9 parts including Part 6 ("Building Future Tools — Prescriptive Checklist") and Part 7 ("What To Build Next"). Before building the new container, Kim wants:

1. **Read the full document** — especially Parts 6 and 7.
2. **Check if anything from the previous session needs to be added.** Specifically:
   - The **QA validator suite** is a new piece of infrastructure that doesn't appear in the architecture doc yet. It should be documented: what it validates, how it's wired into pipeline.py, the `--skip-validators` kill switch, the tiered check system. Add it to the tool ecosystem description (Part 1) and reference it in the future-tool checklist (Part 6 — new tools should run validators after builds).
   - The **speed optimization batching strategy** (SPEED-* decisions) may affect Part 7's priority ordering — production now batches by work type across all modules, not module-by-module.
   - The **Tool Persistence Checklist** (`.auto-memory/reference_tool_persistence_checklist.md`) references 7 locations. The validator suite adds a potential 8th: "runs QA validation against the tool's outputs." Consider whether to add this.
3. **Version-up the document** (v1 → v2) per CLAUDE.md Rule 2. Never overwrite.

## TASK 2: Build Reference Image Selector + Cropper Container

Kim wants a **single unified HTML container** that handles the full image-selection-to-crop pipeline on one screen:

**What it should do:**
- Select reference images (master source images) for a module/event — similar to how the storyboard tool handles image assignment per dialogue line
- Crop selected masters into 4:3 close-ups (the existing cropper functionality from `build_cropper.py`)
- All on one screen — not two separate tools
- Integrated with Directus registry (`prod_visual_assets`) — reads available images from registry, writes crops back to registry
- Follow ALL architecture requirements from Part 6 of the Production Architecture Master (base64 embedding, localStorage, export JSON, auto-register in Directus, `--smoke-test`, `--audit`, `--audit-previous`, dark theme, etc.)

**Existing tools to reference/merge:**
- `Production/tools/build_cropper.py` (797 lines) — the current standalone cropper
- `Production/Event_1/cropper_tool.html` — example output
- `Cropper/` folder — contains previous cropper outputs (tessa_initial_recrop.html, guidebird_sideview_cropper.html, etc.)
- The storyboard builder's image-selection UX — for reference on how to present image choices

**Key constraints:**
- CLAUDE.md Rule 6: minimum 600px shortest side on all crops
- CLAUDE.md Rule 7: Two-Path Protocol applies — build via Python builder, never edit HTML directly
- `.auto-memory/feedback_single_master_crop.md` — crop from ONE master for consistency; never generate per-character stills
- `.auto-memory/project_crop_aspect_ratio.md` — all crops must be 4:3 (iPad-optimized)
- Follow the 7-location persistence checklist (`.auto-memory/reference_tool_persistence_checklist.md`)

**Build approach:**
- Use agents/counteragents for architecture design before writing code
- Follow Part 6 prescriptive checklist from the Production Architecture Master
- Run QA validators on the built HTML output

---

## PREVIOUS SESSION: Completed Work

Everything below was completed in the session ending April 14, 2026.

### Completed This Session
- Uploaded all 18 SPEED-* decisions to Directus `prod_session_decisions` collection
- Built `Production/validators/` — 9 Python files + schemas directory:
  - `__init__.py` — Core data structures (Tier enum, ArtifactType enum, ValidationCheck, ValidationResult)
  - `config.py` — Thresholds for all 5 artifact types
  - `schemas/allowed_variables.json` — 10 personalization vars, 8 cue markers, 6 creatures
  - `phase_b.py` — Phase B script validator (encoding, variables, cue markers, truncation detection)
  - `audio.py` — MP3 validator via ffprobe (container, duration, sample rate, bitrate, channel count)
  - `storyboard.py` — HTML validator (structure, base64 integrity, export functions, drag-drop)
  - `video.py` — MP4 validator via ffprobe (container, streams, resolution, codec, fps)
  - `json_config.py` — JSON validator (syntax, structure, context-aware key requirements)
  - `runner.py` — Orchestrator with CLI, Tier 1 retry loop, calibration report generator
- Wired validators into `Production/tools/pipeline.py`:
  - `validate_output()` function runs after each substep
  - `--skip-validators` kill switch (logs bypass to Directus)
  - `--validate /path/to/file` standalone command
- Calibrated against 322 production artifacts: 0 Tier 1 blockers, 47 Tier 2 warnings
- Fixed 6 false positives during calibration
- Counteragent reviewed: added truncation detection, channel count check, auto-fix file backup
- Created `MINDFULNEST_SPEED_OPTIMIZATION_v2_April2026.html` interactive report
- Persisted speed plan to `.auto-memory/project_speed_optimization_plan.md`
- Added speed optimization section to CLAUDE.md under Production Pipeline
- Logged VALIDATOR-DEPLOY decision to Directus

### Critical State (prevents re-work)
- QA validators are LIVE in pipeline.py — they run silently. Do not rebuild them.
- Kill switch: `pipeline.py --skip-validators` if validators block production unexpectedly
- Validator thresholds in `Production/validators/config.py` were calibrated against real artifacts. Don't change without re-running calibration.
- Auto-fix scope is intentionally minimal (only unicode ellipsis → ASCII). Do not expand per Source Fidelity Protocol.
- All 18 SPEED-* decisions are in Directus and LOCKED (except SPEED-D → needs status update to LOCKED, and SPEED-F → BACKBURNER)
- M1 Tessa is at pipeline stage `audio` / `in_progress` — voice stem v5 and gong candidates await Kim's audition (read `.auto-memory/project_m1_audio_handoff.md` for context)

### Files Changed This Session
- `Production/validators/__init__.py` — NEW
- `Production/validators/config.py` — NEW
- `Production/validators/schemas/allowed_variables.json` — NEW
- `Production/validators/phase_b.py` — NEW
- `Production/validators/audio.py` — NEW
- `Production/validators/storyboard.py` — NEW
- `Production/validators/video.py` — NEW
- `Production/validators/json_config.py` — NEW
- `Production/validators/runner.py` — NEW
- `Production/tools/pipeline.py` — MODIFIED (validator integration)
- `CLAUDE.md` — MODIFIED (speed optimization section)
- `MINDFULNEST_SPEED_OPTIMIZATION_v2_April2026.html` — NEW
- `Production/SESSION_HANDOFF_20260414_merged.md` — NEW (this file)

### Memory Files Changed
- `.auto-memory/project_speed_optimization_plan.md` — NEW
- `.auto-memory/project_validator_suite.md` — NEW
- `.auto-memory/MEMORY.md` — UPDATED (speed optimization + validator entries)

### Active Warnings
- `_step_tts` in pipeline.py is still a stub — requires audio-producer skill until implemented
- SPEED-D status in Directus still shows PENDING — update to LOCKED
- Validator activity log write returned 400 (module_id=0 schema mismatch) — minor
- Counteragent noted Tier 1 checks may be slightly loose — monitor in production

### Dashboard State
- M1: stage=audio, status=in_progress (unchanged — session was infrastructure, not module production)
- prod_session_decisions: 18 SPEED-* entries + 1 VALIDATOR-DEPLOY entry

### Mandatory First Actions for Next Session
1. Run staleness scan (CLAUDE.md Session Start protocol)
2. Read `Production/PRODUCTION_ARCHITECTURE_MASTER_v1.md` in full — especially Parts 1, 6, and 7
3. Identify updates needed from the validator suite + speed optimization work
4. Version-up to v2 with updates
5. THEN begin the reference image selector + cropper container design (agents/counteragents first, code second)

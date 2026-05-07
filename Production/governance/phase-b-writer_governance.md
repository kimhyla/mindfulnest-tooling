# Phase B Writer — Governance Gate

**Skill:** phase-b-writer
**Created:** 2026-04-17 (Wave A WA-C10, spec v2 §C10, Kim's §12 Q1 = YES for phase-b-writer)
**Severity:** HIGH — script fidelity + therapeutic timing + TTS compatibility are locked decisions

## Governing Documents (Read Before Proceeding)

1. `Production/PIPELINE_BRAIN_v1.md` — Phase B section (7-section template, cue markers, pause annotation)
2. `TTS_PERSONALIZATION_PIPELINE_v1.md` — voice/personalization architecture
3. `CLAUDE.md` Rule 11 — Source Fidelity Protocol (Kim's dialogue preserved VERBATIM)
4. `CLAUDE.md` Rule 8 — lip-sync prevention (if output feeds LipSync)
5. `STAGE3_ARCHITECTURE_INVENTORY_v1.md` — APP-14 TTS pipeline, APP-23 scene composer
6. `PHASE_B_ARCHITECTURE_ZOOMOUT_REVIEW.md` v2 — Option C Directus-Admin-as-UI prototype pending (LD-214, LD-215)

## Startup Validation Checklist

Before ANY Phase B script writing, verify ALL of the following:

### 1. Dashboard Queries Completed
- [ ] 7-query session start protocol completed (dashboard-gate)
- [ ] `prod_locked_decisions` queried for `decision_key` LIKE `%PHASE_B%` — all active Phase B LDs loaded
- [ ] `prod_voice_profiles` queried — Myrrhin settings confirmed (LD-148 `ELEVENLABS_V3_FOR_ALL_CHARACTERS`)
- [ ] `prod_activity_log` checked — Kim's recent Phase B verdicts reviewed
- [ ] `prod_script_pauses` checked IF exists (per LD-188 `FIRESTORE_SCHEMA_LOCKFILE_COVERS_12_COLLECTIONS`)

### 2. Structural Check — 7-Section Template (LD-78 `phase_b_seven_section_template`)
The canonical Phase B script has exactly 7 sections. Verify target output will contain:
- [ ] Section 1: Arrival / Settling
- [ ] Section 2: Body-Sensing / Orientation
- [ ] Section 3: The Technique Itself (main practice)
- [ ] Section 4: Deepening / Extension
- [ ] Section 5: Noticing / Reflection
- [ ] Section 6: Integration / Anchoring
- [ ] Section 7: Return / Closing

### 3. Voice + Cue-Marker Check
- [ ] Narrator: Myrrhin (LD-143 `MYRRHIN_VISUAL_DESIGN_LOCKED`, ElevenLabs library voice)
- [ ] LD-79 `phase_b_sensation_language_only` — sensation-language-only (no cognitive/interpretive framing)
- [ ] LD-80 `phase_b_cue_markers_placement` — cue markers BEFORE the narration line they control
- [ ] Required cue markers: `{{INHALE_CUE}}`, `{{EXHALE_CUE}}`, `{{BELL_CUE}}`, `{{PAUSE:Xs}}`
- [ ] Pause durations at therapeutic precision (0.5s / 1.0s / 1.5s / 2.0s / etc.); no rounded "maybe a few seconds"

### 4. Source Fidelity Check (CLAUDE.md Rule 11)
- [ ] Kim-authored dialogue preserved VERBATIM if reusing/adapting prior text
- [ ] No retyping through Claude's text generation
- [ ] Character-specific voice conventions honored (see `CLAUDE_Everdale_World_Design_Bible_v13_10.md` for Myrrhin voice)

### 5. TTS Compatibility Check (feeds audio-producer + LipSync)
- [ ] "MindfulNest" hyphenated as "Mindful-Nest" (ElevenLabs pronunciation fix)
- [ ] Emotional direction tags on every line
- [ ] No `[pause 1s]` inline in text — use `{{PAUSE:1s}}` cue marker (structured)
- [ ] If output will be LipSync'd (Rule 8.2 §8.2): pauses ≤ 1.0s; long pauses get silence-compression pre-processing per §8.4

### 6. Pipeline Discipline Check
- [ ] One module's Phase B per session only
- [ ] Script saved to `prod_scripts` in Directus (authoritative) + `.md` file for Kim's review
- [ ] `prod_modules.stage_status` moves `phase_b_writing → phase_b_kim_review` on completion
- [ ] NEVER commit a Phase B script without Kim's explicit approval (Rule 94 hard gate)

### 7. Zero-Error-QA Phase 0 Trigger
Per LD-124 `PREFLIGHT_PROTOCOL_STEP_0` — if this Phase B script:
- Introduces a new technique type not in `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md` → architectural (4+4)
- Modifies an existing Phase B that shipped → routine (1+1)
- Writes a new Phase B within established patterns → trivial (skip agents, still write preflight row)

### 8. Integration with Phase B Producer Tool (per LD-215)
If Storyboard Option C prototype succeeded (LD-214 GO), Phase B authoring happens in Directus Admin:
- [ ] Script edit in `prod_scripts.content` via Directus Admin text field
- [ ] Pause annotation via `prod_script_pauses` collection + custom interface
- [ ] Flow triggers ElevenLabs render on save
- [ ] No separate localhost:5112 tool

If Option C prototype failed → fall back to Storyboard Option E pattern (extract POC v8 scripts into `Production/lib/phase_b/`, narrow pause-annotation route on existing localhost:5111).

## Hard Failure Gates (STOP + escalate)

- Phase B script bypasses the 7-section template → STOP, re-read LD-78
- Kim-authored dialogue retyped through model generation → STOP, Rule 11 violation
- Pause durations vague ("a few seconds") → STOP, structured markers required
- Phase B script committed without Kim approval → STOP, Rule 94 violation
- TTS output broke on "MindfulNest" pronunciation → STOP, apply "Mindful-Nest" hyphenation

## Related LDs (current)

- LD-78 phase_b_seven_section_template
- LD-79 phase_b_sensation_language_only
- LD-80 phase_b_cue_markers_placement
- LD-143 MYRRHIN_VISUAL_DESIGN_LOCKED
- LD-146 M1_PHASE_B_AUDIO_LOCKED
- LD-147 ARC_SKELETON_IS_CANONICAL_DIALOGUE_SOURCE
- LD-148 ELEVENLABS_V3_FOR_ALL_CHARACTERS
- LD-150 SKELETON_IS_OUTLINE_NOT_SHIP_SOURCE
- LD-151 DIALOGUE_EDITS_MUST_PERSIST
- LD-195 PHASE_B_M1_PAUSE_STRUCTURE_v9_LOCKED
- LD-196 PHASE_B_AUDIO_STITCH_RECIPE_v1
- LD-214 STORYBOARD_OPTION_C_DIRECTUS_ADMIN_UI (pending prototype)
- LD-215 PHASE_B_TOOL_COLLAPSES_INTO_OPTION_C (conditional on LD-214 GO)

## Update Protocol

When any of these LDs change, update the Related LDs section. When new Phase B-related LDs are locked, add them to Section 1 Governing Documents if they warrant doc-level citation, else to the Related LDs list.

## Locked Architecture Constraints (added 2026-04-18, task_id: size-budget-arch-cascade-1caa1e0b)

Before producing ANY deliverable, verify:

- [ ] **Single-MP4 atomic (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1):** Output is ONE MP4 file per module/event with all audio + video + animations baked in. No separate audio track. No separate overlay file. No multi-file deliverable.
- [ ] **No runtime TTS (NO_RUNTIME_TTS_PERSONALIZATION_V1):** Rendered audio contains NO personalization variables (`{childName}`, `{therapistName}`, `{parentTitle}`, `{parentName}`, `{chosenGuideName}`, pronouns). All spoken content is universal phrasing. ElevenLabs runs ONCE per module in the production pipeline; never at runtime from the app.
- [ ] **Arc-aware sizing (CATALOG_DELIVERY_ARC_AT_A_TIME_V1):** Per-module target ≤ 60 MB with 100 MB hard ceiling. If exceeded, either compress before registering or file a `SHORTCUT_SIZE_OVERRIDE_*` escape-hatch decision with Kim's approval.
- [ ] **Transparent MP4 loops (if used for characters/breathing circle):** BAKED INTO the atomic module MP4 at production time. Not layered at runtime. Reference: LD-128 2026-04-18 appendix.
- [ ] **Tool-layer enforcement (per Rule 19 addendum):** ffmpeg/cwebp/ElevenLabs command flags in this governance file are the enforcement point — hardcode bitrate and format ceilings here. Phase 0 prose gate is a reminder, not enforcement.

If ANY box cannot be checked, STOP. Either adjust the plan to comply OR file a `SHORTCUT_*` Directus decision with Kim's explicit approval.

Reference: `APP_ARCHITECTURE_MASTER_v1.md`, `SIZE_BUDGET_AUDIT_20260418.md`, preflight id=84.

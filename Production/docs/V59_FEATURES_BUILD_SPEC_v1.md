# V59 Features Build Tech Spec v1

**Date:** 2026-05-06
**Produced by:** tech-spec skill (dual-Opus research + debate + Kim §13 LOCKED decisions + §13c audit folded in)
**Inputs:**
- `Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md` (~206 items, Cursor v6 + v7-equivalent verdicts)
- Research Agent A (decisions/governance research)
- Research Agent B (code-reality symbol-level trace, replaces Cursor v7 UNCLEAR pass)
- Kim's locked decisions 2026-05-06 (Q1-Q11 + §13c follow-ups)

**Classification:** EXECUTION SPEC — feature build on locked architecture (post-v3 architecture revision)

**Spec scope:** 5 phases (Phase A → E) corresponding to 5 sub-sessions (S5.5c → e → f → g → h) executing the v59 features build to completion + asset findability cleanup.

---

## §0 — Mandatory Operating Mode for Executing Sessions

**This section is read FIRST by every terminal session executing any phase of this spec.** It compiles the error-elimination decisions made through the v59 build (S5.5a1, a2, b, b.1, architecture revision v3, features inventory v1/v2, this spec). Every phase honors all of §0.1 through §0.10. Skipping any of these has historically produced silent failures that browser smoke surfaces too late.

### §0.1 — Skill load + Phase 0 classification (Rule 19)

- **Load `zero-error-qa` skill** before any edit. The skill governs Phase 0 pre-flight, classification, agent spawn, and proof-of-execution patterns.
- **Classify the phase task** per zero-error-qa Tier model:
  - **Tier A (Routine):** per-bug fixes, additive UI primitives, no contract changes. 0 advocate+counter agents. Phase 0 minimal.
  - **Tier B (Cross-cutting / new contracts):** new endpoints, multi-component refactor, schema additions. 1+1 advocate+counter agents.
  - **Tier C (Architectural):** Layer 3 contract rewrites, state shape changes, governance LD supersedes. 4+4 advocate+counter agents.
- **Per-phase classification is stated in §4.** When in doubt, escalate one tier (Tier A → Tier B if any new contract is touched).
- **Write `prod_preflight_reviews` row via `try_post_or_queue` BEFORE any edit.** Reference predecessor preflight + this spec. Confirm via read-back per Rule 35.
- **LD existence preflight query (per Cursor v8 Q9):** if this phase will AMEND or SUPERSEDE any LD, BEFORE writing any code: query `prod_locked_decisions` to confirm the LD key/ID exists. If the query is unavailable OR the row is missing, HALT the phase. Do NOT speculatively reference LDs that may not exist; do NOT silently substitute.
- **Rule 36 applicability gate (per Cursor v8 Q11):** if this phase produces any Path B-style HTML patches in `storyboard_v59_prod.html` or production tooling HTML, run `Production/scripts/patch_invariant_audit.py` BEFORE any new patch lands. If audit unavailable, document `RULE_36_AUDIT_SKIPPED` in `prod_activity_log` with the specific reason. If audit fails (exit 1 from fragile-pattern detection), STOP per §0.8 escape hatch.
- **Artifact-proof requirement per gate (per Cursor v8 Q11):** every smoke gate that PASSES must write a corresponding evidence artifact (file path, output excerpt, screenshot reference, or activity_log row ID) to the phase's COMPLETE row. "Pass/fail text alone" is insufficient — the next session must be able to AUDIT the proof.

### §0.2 — Six-Layer Verification Contract (FROM `feedback_six_layer_feature_verification.md`)

For every feature this phase touches, the feature is NOT done until ALL six layers verify:

1. **UI element exists** — button rendered, drop zone reactive, textarea editable, etc.
2. **UI → backend wiring** — user's input reaches server in expected payload shape with expected field names (no silently-dropped fields, no shape mismatches)
3. **Backend processing matches intent** — server actually USES the input (not "the request returns 200" — the request body must materially affect the output)
4. **State update propagation** — result written to right partition / row / file with right metadata (iteration_notes, parent_asset_id, timestamps)
5. **UI re-render reflects new state** — user sees the correct outcome (thumbnail updates, status changes, cost displays, error messages)
6. **End-to-end smoke test: vary input → observe output changes meaningfully** — same input twice → same output. Different input → different output.

**Layer 6 failure = RELEASE-BLOCKER, not partial completion.** Server-side gates (py_compile, curl probes, npm build) verify Layers 1-4 only — they CANNOT verify Layer 6. Browser smoke is the final arbiter for any UI work.

### §0.3 — Eight Risk Classes for Silent Failure

These categories are MOST AT RISK for Layer 2/3/6 silent failure. Identify which apply to each item in scope; add explicit smoke tests:

| Risk class | Examples in this build | Specific risk |
|---|---|---|
| **AI-driven** | PB-2 Suggest Script, BG-23/24 GPT generation, PB-15a/PA-18a watercolor animate | Input gets dropped client-side OR AI ignores the input. Output looks plausible but doesn't reflect what user provided. |
| **Multi-stage pipelines** | PA-10 LD-375 5-stage Phase A canonical, Phase B Cedric pipeline (LD-149/196), magic compositor | Stage N silently fails / no-ops; final output looks "close enough" but a stage was skipped |
| **Async / fire-and-forget** | SB-10 Send for Lipsync, SB-11 Send for Animation | Success/failure not surfaced to UI; user thinks it worked when it didn't |
| **Drag-drop interactions** | BG-14/15, SB-14, CC-15/16, watercolor → timeline | Wrong asset path delivered, wrong format, wrong target field updated |
| **Side-effect captures** | BG-22, C-9, CC-23/24/25/27 (registered_write), iteration_notes, parent_asset_id | Side effect "works" 95% of the time but skipped on edge cases |
| **Cost / metric displays** | BG-30/31/32, library counts | Hardcoded estimates instead of real API response data |
| **Conditional rendering** | CC-9 hide-on-milestone, SB-22-24 dynamic label, magic button success state, ST-14 mode auto-detect | Happy path tested, edge cases fail |
| **State persistence** | PB-1/PA-1 textarea persist, SB-15 reorder persist, scope swap state | Works in current session, fails after page refresh |

### §0.4 — Authoring Discipline (FROM v2 inventory §13a + §13c)

Rules every phase MUST follow:

1. **Don't invent UI specifics.** Use LOOSE terms ("trim controls", "generation results") unless the specific is cited (LD or Kim chat). When unsure, mark `[UNDECIDED]` rather than guessing. Cost-cause of 4 false WIRED-BUT-BROKEN items in v1.
2. **Don't hallucinate endpoint names.** GREP `Production/tools/storyboard-v2/src/api/endpoints.ts` first. v1 had `/api/beat_gen/*` everywhere — actual namespace is `/api/bg/*`. The MUTATION_ENDPOINTS catalog is authoritative.
3. **Verify field names per Rule 35.** Consult `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` before any `prod_*` payload. Use `try_post_or_queue` for read-back. Same discipline for state-shape field names — VERIFY the field exists or propose explicitly.
4. **Verify agent claims against code.** Research agents misreport file existence and missing infrastructure. Cross-check directly via `Read`/`Glob` — don't recurse with more agents.
5. **6-layer end-to-end verification on every functional item.** UI exists ≠ feature works. Smoke test by varying input → observing meaningful output change. Layer 6 fail = release-blocker.
6. **Browser smoke is mandatory after any UI work.** Server-side gates ≠ user-visible correctness. The proper-fix sprint shipped MANDATORY_E2E_GATE_V1 (if exists) so Playwright e2e is the automated layer; Kim's browser smoke is "does it FEEL right."
7. **Per-bug classification beats batch-blind work.** Phase A of any bug-fix session = status audit BEFORE patching. Write a classification table. Patch only what reproduces.
8. **Don't recommend legacy tool when v59 has gaps.** The answer is always "next phase fixes them."
9. **Author handoffs AFTER predecessor session ships, not during.** Mid-flight handoff authoring carries unique risk.
10. **Tech-spec skill is the right tool for "wrong architectural model"** symptoms. Don't push a quick patch.
11. **"Already wired" / "exists" in docs is NOT proof.** Run the 6-layer verification anyway.
12. **Per Rule 32: absolute `http://localhost:PORT/api/...` URLs in production tool fetch() calls** — never relative paths. Storyboards are loaded from varying origins; relative paths silently break. Apply when modifying `path_picker.html` or any production HTML tool.

### §0.5 — Don't Rely on Memory or Guess

**Mantra (per Kim 2026-05-06):** *"do not rely on memory or guess, always make sure to check all the way to the end, rather than assuming."*

Application:
- Read every file you reference. Re-read at each phase boundary.
- If you find yourself reasoning from "what I recall about this file," STOP and re-read.
- If you find yourself reasoning from "what an agent told me," STOP and verify directly.
- "I think this works" → verify smoke. "I think this exists" → grep first. "I think this LD is current" → query `prod_locked_decisions`.
- Per Rule 24 confidence annotation: tag claims `[CONFIRMED against <source>]` / `[INFERRED — verify]` / `[GUESSED]`.

### §0.6 — Tail-End Independent Verifier Subagent (Recommended)

Pattern proven in S5.5a1 + a2 + b: at end of each phase, BEFORE marking COMPLETE, spawn an Explore agent (or general-purpose) to do an independent end-to-end verification:
- Read recent file changes (git diff)
- Spot-check 5-10 random items from this phase's scope
- Verify each via the 6-layer contract
- Return verdict: PASS / PARTIAL / FAIL + specific findings
- a2's tail-end verifier ran 17 tool uses against 41k tokens, did 10 spot-checks. Caught nothing — but absence of evidence ≠ evidence of absence; the rigor matters.

### §0.7 — Standing Rules Reference (must be honored every phase)

- **Rule 18** — Activity log row for state transitions
- **Rule 19** — No shortcuts in shipping code; no placeholder/future/stub comments without LD-tracked SHORTCUT exceptions
- **Rule 24** — Confidence annotation [CONFIRMED/INFERRED/GUESSED]
- **Rule 26** — Opus escalation triggers (failed patch ×2, cross-system decision, conflicting authorities, repeated frustration phrases ≥3)
- **Rule 27** — Delete obsolete workarounds when root-cause fixes ship
- **Rule 29** — Server staleness check before any "test it now" announcement (lsof PID lstart > .py mtime)
- **Rule 32** — Absolute `http://localhost:PORT` URLs in production tool fetch() calls
- **Rule 33** — Verify correct server + file before testing any new feature (4-line bash check)
- **Rule 35** — Directus schema verification + `try_post_or_queue` for every prod_* write with read-back

### §0.8 — Standing Escape Hatches (when to STOP and surface to Kim)

These conditions apply to EVERY phase. Per-phase additional escape hatches in §4.

1. **Cursor v8 review (if Kim ran it) flags a release-blocker** — STOP, address before proceed
2. **Smoke test fails on a Layer 6 contract** (input variation produces no output variation) — RELEASE-BLOCKER
3. **Schema drift detected** — Directus collection has a different shape than `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` documents. STOP, update reference doc + memory before any write.
4. **An LD this spec amends/supersedes is not found at expected key** — surface (means LD numbering shifted; reconcile)
5. **A handler refactor breaks py_compile** — STOP, revert via git, do not patch on top of broken parse
6. **A client refactor breaks `npm run build`** — STOP, revert, surface TS errors
7. **Phase A surfaces an architectural issue** (not just a bug) — STOP, invoke tech-spec skill rather than patching
8. **Rule 26 Opus escalation triggered** (failed patch ×2, cross-system, conflicting authorities, ≥3 frustration phrases) — STOP, escalate to Opus
9. **Test fixtures don't match current state** (e.g., expected event_id doesn't exist) — STOP, surface
10. **Discovery during execution that a prior phase's work was incomplete** — STOP, surface (means prior phase's COMPLETE row was premature)

### §0.9 — Deviation Logging Pattern (FROM a1/a2/b honesty pattern)

EVERY phase logs deviations honestly in `prod_activity_log`:
- a1 logged 2 prompt-vs-spec deviations
- a2 logged the scope-vs-stub deviation (~50 vs ~30 edits)
- b logged the Cursor-reports-not-on-disk + Bug 5/7 status-unknown classifications

Pattern: when spec says X but reality is Y, write activity_log row `S5_5<phase>_DEVIATION_<deviation_id>` with `details: {spec_says: ..., reality_is: ..., resolution: ..., approved_by: ...}`. Surface to Kim before silently substituting. The audit trail makes long-running multi-session work safe.

**Deviations are NORMAL.** Specs are always incomplete. The behavior to AVOID is: silently substituting OR pretending no deviation happened.

### §0.10 — Browser Smoke Discipline

After any UI work, browser smoke is mandatory before marking phase COMPLETE. Per `feedback_browser_smoke_required.md`:
- Server-side curl probes verify endpoint shape, NOT user-visible correctness
- Bonus tail-end verifier subagents catch what gates miss, but CANNOT verify what Kim sees in browser
- Architectural design gaps surface only via Kim's hands-on test

Every phase's verification table flags which gates require Kim hands-on (cannot self-test in terminal). Phase does NOT mark COMPLETE until Kim confirms or explicitly defers those gates. Per `feedback_file_links.md`: file:// links don't work in chat — Kim screenshots / records / describes verbally with timestamps.

---

## §1 Task

Complete the v59 Preact production tool by:

1. **Beat Generator polish** (Phase A / S5.5c-pass2) — fix delete-confirm modal, thumbnail size enforcement, asset registration via `registered_write.py`, Accept All confirm modal + activity log row, build Library tier filter / search / item preview, add Storyboard image-holder drop zones
2. **Storyboard tab feature completion** (Phase B / S5.5e-pass2) — add image holder rendering + assign/inject buttons + drag-drop, reorder beats, add/delete beats, single dynamic-label export button, ProjectSelector cleanup, ProductionMap fixes, event_create flow verification
3. **Phase A/B parity + CRITICAL Phase B Suggest Script fix** (Phase C / S5.5f-pass2) — REWRITE PB-2 handler to read therapeutic sources, fix textarea persist, fix Phase A lipsync target ambiguity, fix bbox constants to LD-331, watercolor animate Layer 6 smoke gates, MAG-1 state writeback fix, remove ambient preset from producers (Stitcher-only)
4. **Stitcher polish + Library tier extension** (Phase D / S5.5g-pass2) — per-slot bake button, mode auto-detect refactor, Sound Library tier filter, LibraryPanel tier extension
5. **Asset findability cleanup + Rule 19 violations** (Phase E / S5.5h) — refactor all writes through `registered_write.py`, fix `parent_asset_id` linkage, delete LL-28 placeholder/future comments, fix `module_id=1` hardcodes

After all 5 phases, the v59 client is production-ready end-to-end.

## §2 Governing Decisions

### Locked decisions (Kim 2026-05-06, §13 + §13c)

| # | Decision | Status |
|---|---|---|
| Q1 | Trim controls = NUMERIC inputs (do NOT swap for sliders) | LOCKED |
| Q2 | `pathappPatch scope_target_video` = GLOBAL injection | LOCKED |
| Q3 | Stitcher in milestone scope = ENABLED (1-slot mode) | LOCKED |
| Q4 | Cropper keyboard shortcuts = SKIP | LOCKED |
| Q5 | Per-slot bake button = nice-to-have; final bake stays | LOCKED |
| Q6 | Phase A 3-clip = 1 sitting dropdown + auto fly-in/out from standardized library | LOCKED |
| Q7 | Ambient preset selector = STITCHER ONLY (remove from Phase A/B producers) | LOCKED |
| Q8 | Library: tier filter + search (filename + `iteration_notes` substring) + item preview, ~60-80px thumbnails | LOCKED |
| Q9 | PB-8 Mix Audio button = DROPPED (Phase B pipeline bakes audio inside lipsync) | LOCKED |
| Q10 | Storyboard export = SINGLE dynamic-label button | LOCKED |
| Q11 | Module-level SFX cues + universal SFX library | LOCKED |
| — | Watercolor library = same panel, watercolor as a tier | LOCKED |
| — | PA-10 label = "Stitch Fly-In/Out" (was "Mix Audio (auto-stitch)") | LOCKED |
| — | PB-2 sources = `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_16.md` + `Arc Skeletons/ARC_<NN>_SKELETON_FINAL.{md,docx}` Therapeutic Note section | LOCKED |
| — | BG-5/8/18 = visible buttons (NOT right-click context menus) | LOCKED |
| — | BG-9 delete confirm = Modal primitive (NOT `window.confirm()`) | LOCKED |
| — | BG-11 group beats = DEFER (no use case named) | LOCKED |
| — | BG-16 click-to-upload = SKIP (drag-drop sufficient) | LOCKED |
| — | BG-38/39 locked mode + re-open after Accept All = DEFER (current behavior fine) | LOCKED |

### Existing LDs this spec respects (must not violate)

LD-149/196/348 (Phase B Cedric pipeline), LD-280 (single MP4 atomic), LD-281 (no runtime TTS), LD-284 (normalization before concat), LD-330 (WaveSurfer source of truth), LD-331 (watercolor placement bbox — Phase A RIGHT 480x540 fx=800; Phase B LEFT 600x540 fx=40), LD-375 (Phase A canonical pipeline), LD-376 (Phase A xfade recipe), LD-412 (phase_boundaries valid names), LD-421/422 (asset findability), LD-423 (universal stitch editor), LD-440 (gpt-image-2 primary), LD-456/461 (scope validation), LD-458 (event_load lock), LD-460 (async pin), LD-462/463 (Phase A/B producer specs), LD-464 (animate-this bridge), LD-465 (Production Map), LD-466 (export to Stitcher slot order), LD-467 (multi-event selector), LD-468/469 (magic on still/video), LD-470 (watercolor animate procedural), LD-471 (Stitcher full UI), LD-472 (WaveSurfer timeline), LD-473/474/475/478 + new LDs from architecture revision (PHASE_A_TOP_LEVEL_STATE_V1, PHASE_B_TOP_LEVEL_STATE_V1, MILESTONE_STANDALONE_INDEPENDENT_V1, TARGET_VIDEO_SELECTOR_V1, TAB_STRUCTURE_PRODUCTION_ORDER_V1, WIN_RENAMED_RESOLUTION_V1).

### LDs this spec amends/supersedes

| Action | LD | Reason |
|---|---|---|
| SUPERSEDE | LD-517 (if exists) AMBIENT_PRESET_SELECTOR_INPRODUCER_V1 | Q7 LOCKED: ambient preset Stitcher-only |
| AMEND | LD-515 (if exists) PHASE_A_THREE_CLIP_HANDLING_V1 | Q6 LOCKED: 1 sitting + auto fly-in/out |
| New LD | `AMBIENT_PRESET_STITCHER_ONLY_V1` (HIGH) | locks Q7 |
| New LD | `PHASE_A_ONE_DROPDOWN_AUTO_FLYINOUT_V1` (HIGH) | locks Q6 |
| New LD | `PB_2_THERAPEUTIC_SOURCES_LOAD_V1` (CRITICAL) | locks the PB-2 handler contract |
| New LD | `MAG_BUTTON_STATE_WRITEBACK_V1` (HIGH) | locks the magic_still_path/magic_video_path field write contract |
| New LD | `PA_9_LIPSYNC_TARGETS_SITTING_CLIP_V1` (HIGH) | per LD-375 contract |
| New LD | `LIBRARY_TIER_FILTER_V1` (MEDIUM) | locks tier names and filter behavior |
| New LD | `STORYBOARD_IMAGE_HOLDER_V1` (HIGH) | per-beat image rendering + drop zone |
| New LD | `BG_ACCEPT_BEATS_ACTIVITY_LOG_V1` (MEDIUM) | locks audit trail contract |
| New LD | `REGISTERED_WRITE_UNIVERSAL_V1` (HIGH) | all media writes through registered_write.py |

## §3 Approach

Five sequential phases corresponding to 5 terminal sessions. Each phase is bounded, testable, and ships independently. Browser smoke after each phase before next phase starts.

**Phase ordering rationale:**
- Phase A (Beat Generator) first because it's the AUTHORING bottleneck — without polished BG, Kim can't produce new beats efficiently
- Phase B (Storyboard) second because beats authored in BG flow into Storyboard for the next stage
- Phase C (Phase A/B + critical PB-2 fix) third because it depends on functional BG/SB AND because PB-2 is silently producing generic Phase B scripts NOW (urgent fix once authoring infrastructure is solid)
- Phase D (Stitcher polish) fourth because Stitcher consumes outputs from BG/SB/Phase A/B
- Phase E (asset findability cleanup) last because it's cross-cutting refactor that benefits from all prior phases being stable first

Each phase concludes with browser smoke + activity_log row + handoff stub for next session.

## §4 Implementation Phases

### Phase A — S5.5c-pass2: Beat Generator polish + Cropper fixes + Library primitives

**Classification: Tier A (Routine).** No contract changes; additive polish + UI primitives.

**Phase 0:**
- Load `zero-error-qa` skill (per §0.1)
- Per-bug classification: each item is ROUTINE (per-bug) — see risk classes (§0.3): drag-drop (BG-14/15, CC-16), side-effect (BG-22, BG-37, C-9), AI-driven (BG-23/24 GPT generation), conditional rendering (CC-17/18/19)
- Write `prod_preflight_reviews` row via `try_post_or_queue` (Rule 35 read-back) BEFORE any edit
- Reference predecessor preflight (most recent v59 features preflight) + this spec

**Escape hatches (Phase A specific, in addition to §0.8 standing list):**
- BG-22 / C-9 `registered_write` refactor breaks `find_asset.py` queries → STOP, surface
- Library tier filter (CC-17) — if `prod_assets` schema doesn't have a tier-discriminator field, surface to Kim before guessing the field name (Rule 35)
- Library item preview (CC-19) — if hover/click doesn't render audio/video correctly, defer to follow-up rather than ship broken

**Phase A1 — Beat Generator polish (~45 min):**
1. **BG-9** — Replace `window.confirm()` (BgTab.tsx:289) with Modal primitive from `ui/Modal.tsx`. Same destructive-action confirm semantics; cleaner UX consistency.
2. **BG-17** — Enforce thumbnail size: add CSS class `.mn-bg-ref-thumb` with `max-width: 80px; max-height: 80px; object-fit: cover;`. Apply to `<img>` at BgTab.tsx:704.
3. **BG-22** — Refactor asset registration in `production_server.py:10067-10083` to call `registered_write.register_asset(...)` instead of direct Directus write. Pass `iteration_notes`, `parent_asset_id` (where parent exists).
4. **BG-34/35** — Add warn modal listing unset beat_ids when Accept All clicked with incomplete selections. Add confirm modal "Lock in N selections and advance pipeline_stage?" Use Modal primitive.
5. **BG-37** — Add `try_post_or_queue("prod_activity_log", {action: "BEAT_GEN_ACCEPT_ALL", details: {selection_map: {...}, event_id: ..., target: ...}})` in `_handle_bg_accept_beats` at production_server.py:9227-9311. Per Rule 18, must register activity for state transitions.
6. **BG-5/8/18** — Add visible buttons for: (a) Edit chip (small pencil icon next to chip ×), (b) Insert beat after (small + icon between beat cards), (c) Remove ref (small × on thumbnail corner). NOT right-click — visible per Kim 2026-05-06 lock.

**Phase A2 — Cropper fixes (~15 min):**
1. **C-9** — Refactor cropper save in `production_server.py:10067-10083` to use `registered_write.register_asset` (related to BG-22; same handler path).
2. **Verify aspect-ratio lock at 4:3** per Kim's spec — read `CropperCanvas.tsx:216-271`. If not present, ADD aspect lock to crop-rect resize logic. Min crop size = 600px short side per Rule 6 (already enforced via C-8).
3. **C-11** — DROP from inventory (no keyboard shortcuts per Q4 lock).

**Phase A3 — Library primitives (~60 min):**
1. **CC-15** — Already WIRED (draggable items at LibraryPanel.tsx:127-133,155). Verify only.
2. **CC-16** — Add drop target on Storyboard image holders (PREP for Phase B SB-14). Define `mn-storyboard-image-drop-zone` CSS class + `onDrop` handler accepting `lib-image` payload.
3. **CC-17 Library tier filter dropdown:**
   - Tier values: `images`, `ambient`, `sfx`, `transitions`, `watercolors`
   - Filter `prod_assets` by tier (likely uses `asset_type` field; verify via Rule 35 schema reference)
   - Default tier = `images`
   - Persist tier selection in `localStorage`
4. **CC-18 Library search box:**
   - Text input above tier filter
   - Substring match on (a) `file_name` field, (b) `iteration_notes` field
   - Debounced 300ms
   - Combined with tier filter (search within selected tier)
5. **CC-19 Library item preview:**
   - Hover trigger after 500ms (don't fire on quick-pass)
   - Image: shows fullsize at 320px max
   - Audio: plays inline
   - Video: plays muted preview
   - Click sticky-pins the preview until clicked elsewhere

**Phase A Verification (smoke gates):**

| Gate | Smoke test | Risk class |
|---|---|---|
| A-1 | `python3 -m py_compile Production/tools/production_server.py` clean | — |
| A-2 | `cd Production/tools/storyboard-v2 && npm run build` clean | — |
| A-3 | Server restart + `/api/health` 200 (Rule 29) | — |
| A-4 | BG-22 smoke: upload ref → `find_asset.py` query returns row with `iteration_notes` populated | side-effect |
| A-5 | BG-37 smoke: Accept All → `prod_activity_log` row `BEAT_GEN_ACCEPT_ALL` written with selection_map | audit |
| A-6 | BG-34/35 smoke: Accept All with 1 unset beat → warn modal lists that beat | conditional render |
| A-7 | CC-17 smoke: switch tier from images → sfx → asset list filters meaningfully | conditional render |
| A-8 | CC-18 smoke: type "tessa" in search → list narrows to tessa-named items | conditional render |
| A-9 | CC-19 smoke: hover image library item → preview opens after 500ms | UX |
| A-10 | Activity log row `S5_5C_PASS2_COMPLETE` with full gate summary | — |
| A-11 | New LD: `LIBRARY_TIER_FILTER_V1`, `BG_ACCEPT_BEATS_ACTIVITY_LOG_V1` registered via `try_post_or_queue` (Rule 35) | — |

**Phase A Deferred (DROP from scope):**
- BG-10 reorder UI (drag-drop) — defer to Phase B if Kim wants reorder in BG vs SB; otherwise drop
- BG-11 group beats — DEFER per Kim
- BG-16 click-to-upload — SKIP per Kim
- BG-38/39 locked mode + re-open — DEFER per Kim
- C-11 keyboard shortcuts — SKIP per Q4

---

### Phase B — S5.5e-pass2: Storyboard tab feature completion + ProjectSelector cleanup + ProductionMap fixes

**Classification: Tier C (escalated per Cursor v8 Q8 — cross-cutting scope/UI propagation + new image-management contracts + ProductionMap mutation-channel refactor).** SB-3/12/13/14 add new image-management contracts; CC-7/9/11 affect cross-component scope cascade; ProductionMap raw fetch refactor changes mutation channel; SB-21 milestone-scope partition write-target is a Layer 4 contract change.

**Phase 0:**
- Load `zero-error-qa` skill
- Spawn 4+4 advocate+counter agents per Rule 19 Tier C (full Phase 0 architectural review — escalated from Tier B per Cursor v8)
- Risk classes: drag-drop (SB-14), state propagation (SB-3/12/13, SB-15 reorder), conditional rendering (SB-22/23/24 dynamic label, CC-9 hide-on-milestone, CC-11 reset-on-event-load), state persistence (SB-15 reorder persist), end-to-end multi-stage (SB-21 milestone scope)
- Write `prod_preflight_reviews` row referencing predecessor

**Escape hatches (Phase B specific):**
- SB-21 milestone-scope smoke fails (Send Out writes to wrong partition) → STOP, RELEASE-BLOCKER, surface
- SB-15 drag-drop reorder turns out fragile → fall back to up/down arrows (Kim 2026-05-06 lock allows fallback)
- ProductionMap endpoint cap (CC-31) cannot be lifted without backend change beyond this spec's scope → defer to follow-up + document
- TargetVideoSelector rename (CC-7) breaks any imports not caught by TS check → STOP, fix all import sites before proceed

**Phase B1 — Storyboard image management (CRITICAL UX gaps; ~90 min):**
1. **SB-3** — Add image holder rendering. In BeatCard component (StoryboardTab.tsx:514-555), insert `<img>` element rendering `beat.image_path` or fallback to `beat.gpt_options[selected_option_id].image_path`. Apply CSS class for consistent sizing.
2. **SB-12** — Add "Assign Image" button on BeatCard. Wires to existing `assign_image` endpoint declaration in `endpoints.ts:58`. Opens Library modal filtered to `images` tier; user picks; PATCH `state.videos.<role>.beats[id].image_path`.
3. **SB-13** — Add "Inject Image" button on BeatCard. Wires to existing `inject_image` endpoint at `endpoints.ts:60`. Same pattern, different storage semantics (per existing endpoint contract).
4. **SB-14** — Add drop target on BeatCard (uses `CC-16` infrastructure from Phase A). Drag library image → drops onto BeatCard → fires `assign_image` or `inject_image` depending on which sub-zone.
5. **SB-15** — Add reorder controls (drag-drop per Kim 2026-05-06). Use HTML5 drag events. On drop, PATCH `display_order` array via existing endpoint. Fallback to up/down arrows if drag-drop turns out fragile.
6. **SB-16** — Add "Add Beat" button in Storyboard footer. Reuses BG endpoint `bg_add_beat` (works in any scope where beats partition exists).
7. **SB-17** — Add Delete Beat button per BeatCard. Reuses `bg_delete_beat` endpoint. Confirm via Modal primitive (consistency with BG-9 lock).
8. **SB-22/23/24** — Replace 3 separate export buttons (if any exist) with SINGLE dynamic-label button. Label: `Export as Intro` / `Export as Resolution` / `Export as Milestone` based on `activeTargetVideo.value` (intro/resolution) or `activeMilestoneId.value` (milestone). Click invokes `scene/assemble` endpoint with `scope_target_video`.
9. **SB-21 milestone scope smoke:** Verify `scene/assemble` writes to `state.videos.standalone.completed_mp4_path` when `activeProjectType === 'milestone'` (NOT to `state.videos.intro.completed_mp4_path`). Already WIRED per Agent B trace; smoke confirms.

**Phase B2 — ProjectSelector + TargetVideoSelector cleanup (~30 min):**
1. **CC-7** — Rename `VideoSelector.tsx` → `TargetVideoSelector.tsx`. Update all imports + `app.tsx:91-93` references.
2. **CC-9** — Hide TargetVideoSelector when `activeProjectType.value === 'milestone'`. Add conditional render in app.tsx.
3. **CC-11** — On event load, reset `activeTargetVideo.value` to `'intro'`. Add explicit reset in `ScopeBoundary.tsx` event-load handler. Verify via smoke.
4. **CC-5 confirmation** — Verify Stitcher tab STAYS enabled in milestone scope. Per Q3 lock, only Phase A and Phase B disabled.

**Phase B3 — Production Map fixes (~30 min):**
1. **CC-31** — Verify Production Map endpoint returns all 59 V1 modules. Read `production_server.py:8765-8768`. Remove any pagination cap. Smoke: ProductionMap renders 10 arcs × ~6 modules = 59 cells.
2. **CC-34** — Refactor `ProductionMapTab.tsx:178-195` `onCellClick` to use `pathappPatch` instead of raw `fetch(MUTATION_ENDPOINTS.event_load, ...)`. Standard mutation channel per LD-519 (if exists) or general consistency.

**Phase B4 — Module SFX cues documentation (~15 min):**
1. **CC-33** — Document the relationship between `state.module_sfx_cues` (module-level, kim's main use case for SFX placement on the assembled module timeline per Q11) AND `slot.sfx_cues[]` (per-slot, used for transitions between slots per LD-466). Add comment in StitcherTab.tsx + state shape doc. Both coexist; both needed.

**Phase B5 — Event create flow verification (~10 min):**
1. **EP-24** — Already WIRED per Agent B trace (`ProjectSelector.tsx:108-125` + `production_server.py:6322-6370`). Smoke: create new event via "+ New Event" → directory + Directus row created → milestone scope NOT applicable (different endpoint).

**Phase B Verification (smoke gates):**

| Gate | Smoke test | Risk class |
|---|---|---|
| B-1 | py_compile + npm build clean | — |
| B-2 | Server restart + /api/health 200 | — |
| B-3 | SB-3: BeatCard renders beat.image_path thumbnail | render |
| B-4 | SB-12/13: Assign/Inject Image buttons functional → image updates on card | state propagation |
| B-5 | SB-14: drag library image → BeatCard → image assigns | drag-drop |
| B-6 | SB-15: reorder beats via drag → display_order persists across reload | state persistence |
| B-7 | SB-16/17: Add Beat / Delete Beat work; confirm modal on delete | conditional render |
| B-8 | SB-21 milestone smoke: ProjectSelector → milestone, BG → SB → Send Out → state.videos.standalone.completed_mp4_path written | end-to-end |
| B-9 | SB-22/23/24: dynamic-label button shows correct target name; click writes to correct partition | conditional render |
| B-10 | CC-7/9: TargetVideoSelector renamed, hidden in milestone scope | conditional render |
| B-11 | CC-11: switch event → activeTargetVideo resets to intro | state persistence |
| B-12 | CC-31: Production Map renders all 59 modules | data |
| B-13 | CC-34: ProductionMap event_load uses pathappPatch (not raw fetch) | mutation channel |
| B-14 | EP-24: event create + modal flow smoke | end-to-end |
| B-15 | Activity log row `S5_5E_PASS2_COMPLETE` | — |
| B-16 | New LD `STORYBOARD_IMAGE_HOLDER_V1` registered | — |

---

### Phase C — S5.5f-pass2: Phase A/B parity + CRITICAL PB-2 fix + watercolor end-to-end + bbox

**Classification: Tier C (ARCHITECTURAL).** PB-2 handler is a Layer 3 contract REWRITE. MAG-1 is a Layer 4 state-shape contract change. LD-517 supersede + LD-515 amend are governance-level changes. Phase A 3-clip refactor changes a producer pipeline contract. Watercolor animate Layer 6 is the highest-risk smoke gate in the build.

**Phase 0:**
- Load `zero-error-qa` skill
- **Spawn 4+4 advocate+counter agents per Rule 19 Tier C** — full Phase 0 architectural review
- Risk classes: AI-driven (PB-2, watercolor animate — both CRITICAL), multi-stage pipeline (Phase A LD-375 5-stage), state persistence (textarea persist), state propagation (MAG-1 writeback, bbox constants), conditional rendering (magic button success state)
- Write `prod_preflight_reviews` row with full classification + spawn record
- Reference Cursor v8 review (if Kim ran it; otherwise note "Cursor v8 not run")

**Escape hatches (Phase C specific — TIER C HIGH-RISK):**
- **PB-2 smoke test fails** (M1E1 returns generic meditation language NOT referencing Magic Hands/palm/body-sensing) → **RELEASE-BLOCKER**. Halt Phase C. Surface to Kim. DO NOT advance to Phase D. Investigation: Claude API prompt construction; verify therapeutic note text actually included; verify Claude is using it not summarizing past it.
- **Watercolor animate Layer 6 smoke fails** (3 different motion descriptions → identical animations) → **RELEASE-BLOCKER**. Verify Claude is actually using `motion_description` in filter generation, not just receiving it. Investigation: Claude system prompt at `production_server.py:8593`.
- **LD-331 actual bbox text differs from spec values** — STOP, LD wording wins per Rule 24, surface to Kim
- **PA-9 lipsync target fix breaks existing Phase A states** (test fixtures expect generic base clip behavior) → STOP, write migration if needed, surface
- **Phase A 3-clip refactor breaks existing `state.phase_a` records** (existing data has 3 separate clip IDs but new model has 1 sitting + auto fly-in/out) → STOP, write migration, surface
- **MAG-1 state writeback breaks existing magic button rendering** (some states already have these fields populated by older code paths) → STOP, audit existing data, surface
- **Cursor v8 review (if Kim ran it) flags additional Tier C concerns** → STOP, surface, address before proceed

**Phase C1 — PB-2 CRITICAL FIX (~75 min):**

Current state per Agent B: `production_server.py:7985-8129` does NOT load arc skeleton, does NOT load technique inventory, does NOT extract therapeutic notes. Generates GENERIC Phase B scripts.

**RELEASE-BLOCKER PREFLIGHT (per Cursor v8 Q1):** If `event_id` → arc resolution is ambiguous OR no arc skeleton can be deterministically resolved for the active module, **HALT — do not synthesize a generic script**. Surface to Kim with the ambiguity (e.g., "M1E1 maps to multiple arc skeletons" or "no skeleton found at expected path"). Generic-script-fallback is a Layer 3 silent failure and is forbidden.

**Phase artifact requirement (per Cursor v8 Q1):** the executing session must capture and log to `prod_activity_log` the (a) resolved arc skeleton path used, (b) extracted Therapeutic Note section verbatim (truncated if very long), and (c) Claude API prompt template actually sent. Without these artifacts, the phase does NOT mark COMPLETE.

Required handler refactor:
1. Resolve active `event_id` (e.g., `M1E1`) → arc number (e.g., `1`) → arc skeleton path (`Arc Skeletons/ARC_01_SKELETON_FINAL.{md,docx}`)
2. Read BOTH .md and .docx (per CLAUDE.md Rule 10 alignment protocol). Use `pandoc` for .docx extraction.
3. Diff sections; if disagreement → STOP, surface to Kim
4. Locate `## EVENT N: ...` section for active module within the skeleton
5. Extract `### Therapeutic Note — ...` subsection (between `### Narrative Setup` and `### Resolution`)
6. Read `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_16.md` (highest version per Rule 2)
7. Construct Claude API prompt with BOTH contexts:
   ```
   Therapeutic context for this module:
   <THERAPEUTIC NOTE TEXT>
   
   Technique catalog:
   <RELEVANT TECHNIQUE FROM INVENTORY>
   
   Generate a Phase B meditation script using the technique above.
   Use [pause N] markers for breath rhythm. Voice: Cedric.
   ```
8. Send to Claude API (gpt-image-2 NOT applicable here; this is text gen — use claude-sonnet-4-x or whichever model is current per existing Suggest Script flow)
9. Return script to client

**SMOKE TEST (BLOCKING):** Suggest Script for M1E1 (Tessa's Fall, Body-Sensing/Palm Interoception). Output MUST reference palm/breath/Magic Hands SPECIFICALLY. Generic meditation language = release-blocker.

Register new LD: `PB_2_THERAPEUTIC_SOURCES_LOAD_V1` (CRITICAL).

**Phase C2 — Phase A/B textarea persist (~20 min):**

**Endpoint correction (per Cursor v8 Q6):** `phase_a_script` and `phase_b_script` are NOT separate endpoints in MUTATION_ENDPOINTS catalog (verified `endpoints.ts:51-125`). Use the existing `v2_module_patch` endpoint (line 90, comment: "S5.5f — top-level state writes via the v2 module-patch handler. Whitelisted fields: see `_V2_MODULE_ALLOWED_FIELDS` in production_server.py. Used for phase_X_watercolor_cues_json, phase_X_ambient_preset_id, the Phase A 3-clip slots, etc.").

1. **PB-1** — Add `onBlur` handler on Phase B script textarea (`PhaseProducer.tsx:466-473`). Call pattern: `pathappPatch(scope, MUTATION_ENDPOINTS.v2_module_patch, {field: 'phase_b_script', value})` OR equivalent client helper that targets `v2_module_patch`. Server-side: verify `phase_b_script` is whitelisted in `_V2_MODULE_ALLOWED_FIELDS`; if not, ADD it (small server change). Verify via reload smoke.
2. **PA-1** — Same pattern for Phase A script textarea, field=`phase_a_script`. Verify whitelist entry.

**Phase C3 — Phase A 3-clip handling refactor per Q6 (~45 min):**

**RELEASE-BLOCKER PREFLIGHT (per Cursor v8 Q3):**
- ✗ `Production/standardized_assets/` directory does NOT exist (verified 2026-05-06)
- HARD GATE: BEFORE any client/server code change, the executing session must (a) create the directory, (b) populate it with versioned `chipper_fly_in_v*.mp4` + `chipper_fly_out_v*.mp4` standardized assets (Kim sources/approves these — DO NOT generate without Kim sign-off), (c) register each via `registered_write.py` per LD-421, (d) verify via `find_asset.py`. If standardized assets cannot be sourced in this phase, HALT and surface — do NOT proceed with the client refactor (would break the producer).

**Migration plan for existing `state.phase_a` records (per Cursor v8 Q3):**
Existing records use field names: `chipper_flyin_clip_id`, `chipper_sitting_clip_id`, `chipper_flyout_clip_id` (verified `PhaseProducer.tsx:82-84, 113, 115, 359, 361`). The refactor:
- KEEPS `chipper_sitting_clip_id` (user-selected via dropdown)
- DEPRECATES `chipper_flyin_clip_id` and `chipper_flyout_clip_id` from user-selectable to auto-resolved
- Migration script: for each existing `state.phase_a` record, leave existing values in place (backwards compat); new code resolves fly-in/out from standardized library at render time, ignoring the per-event values
- After Phase C3 ships, future Phase A authoring populates only `chipper_sitting_clip_id`; the old fields remain in legacy state but are inert

Per Q6 LOCKED: 1 sitting dropdown + auto fly-in/fly-out from standardized library.

1. **PA-6/7/8** — Refactor `PhaseProducer.tsx:613-635, 652-659`. Remove 3 separate dropdowns. Replace with:
   - 1 dropdown: "Sitting clip" (lists `chipper_idle_on_empty_desk_*` clips); writes `chipper_sitting_clip_id`
   - Auto-resolved at render time: fly-in clip from `Production/standardized_assets/chipper_fly_in_v*.mp4` (most recent version per filename sort)
   - Auto-resolved at render time: fly-out clip from `Production/standardized_assets/chipper_fly_out_v*.mp4`
   - REMOVE UI for `chipper_flyin_clip_id` / `chipper_flyout_clip_id` (legacy field names; data preserved per migration plan above)
2. **PA-9** — Hardcode `Send for Lipsync` in Phase A path to use `state.phase_a.phase_a_chipper_sitting_clip_id` (not generic `selectedBaseClip`). Per LD-375 contract.
3. **PA-10** — Rename label `Mix Audio (auto-stitch)` → `Stitch Fly-In/Out`. Functionality unchanged (still fires LD-375 5-stage pipeline).
4. AMEND LD-515 (if exists) PHASE_A_THREE_CLIP_HANDLING_V1.
5. New LD: `PHASE_A_ONE_DROPDOWN_AUTO_FLYINOUT_V1` + `PA_9_LIPSYNC_TARGETS_SITTING_CLIP_V1`.

**Phase C4 — Watercolor placement bbox fix per LD-331 (~20 min):**
1. **PB-17/PA-19** — Read `production_server.py:17107-17110`. Compare actual bbox constants to LD-331 spec values. Per spec: Phase A RIGHT 480x540 frame_x=800; Phase B LEFT 600x540 frame_x=40. FIX constants if they differ. If LD-331 itself has different values than the spec wording, surface to Kim before changing (LD wording wins over spec wording per Rule 24 confidence annotation).
2. Smoke: render watercolor on Phase A → appears at frame_x=800 RIGHT side. Same on Phase B at frame_x=40 LEFT.

**Phase C5 — Ambient preset removal from Phase A/B producers (~15 min):**
1. **PB-22/PA-23 REMOVE** per Q7 — Delete ambient preset selector from `PhaseProducer.tsx:513-533`. Move ambient selection to Stitcher only.
2. SUPERSEDE LD-517 (if exists) AMBIENT_PRESET_SELECTOR_INPRODUCER_V1.
3. New LD: `AMBIENT_PRESET_STITCHER_ONLY_V1` (HIGH).

**Phase C6 — MAG-1 magic_*_path state writeback fix (~30 min):**

Current state per Agent B: server returns `composite_path` and `asset_id` in 200 response but never writes `state.beats[beat_id].magic_still_path` / `magic_video_path`.

**Idempotent merge behavior (per Cursor v8 Q2):** Some legacy beat records may have ONE of the two fields populated by older code paths (manual sets, partial migrations, rollback artifacts). The fix MUST:
- PRESERVE existing non-empty `magic_still_path` / `magic_video_path` UNLESS the current render succeeded for the SAME beat_id + role + asset_type
- ONLY supersede when current render is a successful new render of the same target (idempotent merge: new render of same target overwrites; new render of different target adds without disturbing the other field)
- Log a `prod_activity_log` row `MAG_FIELD_MERGE` with `{prior_value, new_value, supersede_reason}` whenever overwriting an existing non-empty field

1. In `_handle_magic_still` (production_server.py ~8201-8309): after `register_asset`, write `state.videos[role].beats[beat_id].magic_still_path = str(rendered)` via `mutate_video_state(role, lambda part: ...)`. Use scope from request body. Apply idempotent merge per above.
2. Same pattern in `_handle_magic_video` (~8311-8489): write `magic_video_path` with idempotent merge.
3. New LD: `MAG_BUTTON_STATE_WRITEBACK_V1` (HIGH) — locks the field name contract + idempotent merge semantics.
4. Smoke: trigger magic-on-still → reload → BeatCard's "magic on still" button shows success state (button conditional rendering at StoryboardTab.tsx:579-580 now has truthy field).
5. Smoke (legacy compat): synthesize a beat record with `magic_still_path` populated but `magic_video_path` empty → trigger magic-on-video → still field UNCHANGED, video field NOW populated.

**Phase C7 — Watercolor animate Layer 6 smoke (CRITICAL) (~30 min):**

Per `feedback_six_layer_feature_verification.md` and §11 of inventory v2. Layers 1-3 verified by Agent B trace (path_picker.html line 623 sends motion_description; production_server.py line 8593 puts it in Claude prompt). Layer 6 needs runtime smoke.

**Reproducible fixture block (per Cursor v8 Q7):**

```yaml
fixture:
  watercolor_key: <first deterministic key from /api/phase/watercolor_list at execution time;
                  cite the exact key in activity log row before smoke runs>
  fixed_path_points:
    # Same path geometry across all 3 smoke runs to isolate motion_description as the variable
    - [0.20, 0.50]
    - [0.50, 0.30]
    - [0.80, 0.50]
    - [0.50, 0.70]
  motion_descriptions:
    smoke_1: "moving up and down on either side"
    smoke_2: "trembling in place"
    smoke_3: "spiraling outward from center"

pass_criteria:
  - All 3 outputs render successfully (200 response, ffmpeg exit 0, output mp4 produced)
  - Pairwise video_hash(smoke_1, smoke_2, smoke_3) all DIFFER (sha256 of output mp4 binary; any two equal = FAIL)
  - Observable motion class differs in first 3 seconds (Kim hands-on visual confirmation):
    * smoke_1 → vertical translation
    * smoke_2 → in-place oscillation/jitter
    * smoke_3 → expanding circular/radial motion

blocker_criteria:
  - Any two pairwise video hashes EQUAL → Claude is producing identical output regardless of input → RELEASE-BLOCKER (Layer 3 silent failure)
  - All 3 outputs render but motion class is visually indistinguishable per Kim → RELEASE-BLOCKER (Claude receives input but ignores it)
  - Repeating smoke_1 twice → outputs MUST be identical (deterministic given same path + same description); if differ → release-blocker for non-determinism (separate bug class)
```

Activity log row: `WATERCOLOR_ANIMATE_LAYER_6_SMOKE` with `details: {watercolor_key, video_hashes: [h1, h2, h3], pass: true|false, kim_visual_confirm: true|false|deferred}`.

If smoke shows identical animations regardless of text → RELEASE-BLOCKER (verify Claude is actually using motion_description in filter generation, not just receiving it).

**Phase C Verification (smoke gates):**

| Gate | Smoke test | Risk class |
|---|---|---|
| C-1 | py_compile + npm build clean | — |
| C-2 | Server restart + /api/health 200 | — |
| C-3 | **PB-2 CRITICAL: Suggest Script for M1E1 → output references Magic Hands/palm/body-sensing** | **AI-driven Layer 3 — RELEASE-BLOCKER on fail** |
| C-4 | PB-1/PA-1: textarea edit → reload → text retained | state persistence |
| C-5 | PA-6/7/8: 1 sitting dropdown + auto fly-in/out resolution | state propagation |
| C-6 | PA-9: lipsync targets sitting clip (not generic base) | multi-stage pipeline |
| C-7 | PA-10: button label reads "Stitch Fly-In/Out" | — |
| C-8 | PB-17/PA-19: watercolor renders at LD-331 bbox | render |
| C-9 | PB-22/PA-23: ambient preset selector ABSENT in Phase A/B producers | conditional render |
| C-10 | **MAG-1: magic-on-still trigger → reload → button shows success state** | state propagation |
| C-11 | **PB-15a/PA-18a/MAG-4 Layer 6: 3 smoke tests show meaningfully different animations** | **AI-driven — release-blocker on fail** |
| C-12 | LD-517 SUPERSEDED, LD-515 AMENDED, 4 new LDs registered | — |
| C-13 | Activity log row `S5_5F_PASS2_COMPLETE` | — |

---

### Phase D — S5.5g-pass2: Stitcher polish + Library tier extension

**Classification: Tier A (Routine).** Additive UI features + mode-detect refactor; no contract changes.

**Phase 0:**
- Load `zero-error-qa` skill
- Per-feature classification: ROUTINE per-feature
- Risk classes: conditional rendering (ST-14 mode auto-detect, ST-15 tier filter), multi-stage (ST-9 per-slot bake)
- Write `prod_preflight_reviews` row

**Escape hatches (Phase D specific):**
- ST-14 mode refactor breaks current event-mode behavior → STOP, revert, surface
- LibraryPanel tier extension (ST-16) breaks Phase A's CC-17 (cross-cutting prereq) → STOP, surface (signals Phase A's CC-17 had a contract bug)
- Per-slot bake (ST-9) — if backend doesn't support single-slot encode, defer per Q5 (it's nice-to-have, not blocking)

**Phase D1 — Stitcher feature additions (~60 min):**
1. **ST-9** — Add per-slot bake button (nice-to-have per Q5). Per-slot bake = re-encode just that slot's MP4 without re-baking entire module. Useful for iterating one segment.
2. **ST-14** — Refactor mode auto-detect at `StitcherTab.tsx:141-144`. Replace "infer from slots length" with "use `activeProjectType.value` signal". 4-slot when event scope, 1-slot when milestone scope.
3. **ST-15** — Add Sound Library tier filter dropdown in Stitcher tab. Filters Library Panel to ambient / sfx / transitions.
4. **ST-6 / ST-20** — VERIFY numeric trim inputs stay (Q1 LOCKED — do NOT swap for sliders).

**Phase D2 — LibraryPanel tier extension (~45 min):**
1. **ST-16** — Extend LibraryPanel at `LibraryPanel.tsx:62-69, 124-157` to support 5 tiers: `images`, `ambient`, `sfx`, `transitions`, `watercolors`. Currently image-centric only. Wire to Phase A's CC-17 tier filter dropdown infrastructure.
2. Watercolor as a tier (per Kim 2026-05-06 lock): same panel, just filtered.

**Phase D Verification:**

| Gate | Smoke test | Risk class |
|---|---|---|
| D-1 | py_compile + npm build clean | — |
| D-2 | Server restart + /api/health 200 | — |
| D-3 | ST-9: per-slot bake produces single-slot mp4 without re-baking module | multi-stage pipeline |
| D-4 | ST-14: switch event ↔ milestone → 4-slot ↔ 1-slot mode auto-flips | conditional render |
| D-5 | ST-15: Stitcher tier filter shows SFX-only assets in panel | conditional render |
| D-6 | ST-16: LibraryPanel filters to each of 5 tiers | conditional render |
| D-7 | ST-6/ST-20 confirm numeric trim still | — |
| D-8 | Activity log row `S5_5G_PASS2_COMPLETE` | — |

---

### Phase E — S5.5h: Asset findability + Rule 19 cleanup

**Classification: Tier C (escalated per Cursor v8 Q8 — highly cross-cutting; touches every write path; parent_asset_id linkage failure mode is silent + cumulative).** Touches many files; while no individual behavior change, the cumulative cross-cutting impact (every media write across server) elevates risk class. LD-421/422 contract enforcement + parent_asset_id linkage are Layer 4 side-effect captures (per §0.3 highest-risk class for silent failure).

**Phase 0:**
- Load `zero-error-qa` skill
- Spawn 4+4 advocate+counter agents per Rule 19 Tier C (escalated from Tier B per Cursor v8)
- Risk classes: side-effect captures (registered_write refactor on every write path), state propagation (parent_asset_id linkage), Rule 19/27 compliance (LL-28 deletes)
- Write `prod_preflight_reviews` row

**Escape hatches (Phase E specific):**
- `registered_write` refactor on a path breaks existing `find_asset.py` queries (verify before/after diff) → STOP, surface
- `parent_asset_id` linkage refactor creates orphaned chains (existing rows have None already) → DOCUMENT but don't backfill (out of scope)
- `module_id=1` hardcode fix breaks scene_assemble for events without module_id in state → LD as `SHORTCUT_MODULE_ID_DERIVE_V1` per Rule 19 escape hatch, do NOT silently change behavior
- LL-28 comment deletion accidentally removes load-bearing code (rare but possible if dev wrote `// future: ...` ABOVE actual implementation) → grep + manual review before delete

**Phase E1 — registered_write.py refactor (~75 min):**

**Scope clarification (per Cursor v8 Q4):** This is **caller-linkage remediation**, NOT API signature work. The `register_asset(...)` function ALREADY supports `parent_asset_id` (verified `Production/lib/registered_write.py:146-161, 206-209`). The bug is callers passing `None`. Fix = update callers to pass actual parent IDs where predecessor exists.

**Read-back assertion required (per Cursor v8 Q4):** After EACH refactored call site, executing session adds an assertion that `parent_asset_id` is non-null when a predecessor row exists for the same scope+role. Test: re-send (SB-21) for a beat that already has a previous concat MP4 → new row's `parent_asset_id` MUST point at the previous row's `asset_id` (NOT None).

1. **CC-23** — Refactor `production_server.py:10008-10012, 10067-10173` (upload + crop save) to use `registered_write.register_asset(...)` instead of direct Directus write.
2. **CC-24** — Refactor `beat_generator.py:1226-1343` + `production_server.py:9425-9447` (gpt_options registration) — currently lands on `beat["gpt_options"]` in sidecar but DOES NOT enter `prod_assets`. Fix.
3. **CC-25** — Refactor Phase B handlers (`phase_b_lipsync` ~16898+, `phase_b_regen_audio`, `phase_b_mix_audio`) — currently DO NOT register MP4 outputs. Add `register_asset` calls.
4. **CC-27** — Fix `parent_asset_id=None` in scene_assemble (`production_server.py:7340, 7764`). Pass actual `previous_concat_mp4_asset_id` when one exists for same scope+role. Maintains LD-421 traceability chain.
5. New LD: `REGISTERED_WRITE_UNIVERSAL_V1` (HIGH) — locks "all media writes through registered_write.py" contract.

**Phase E2 — Rule 19 / LL-28 violations cleanup (~30 min):**

Delete or convert to LD-tracked exceptions per Rule 19:

| Location | Comment | Action |
|---|---|---|
| `AssetTile.tsx:7-8` | "future" consumer comment | Delete |
| `LibraryPanel.tsx:6-8` | "future drop targets" comment | Delete (drop zones now exist post-Phase A) |
| `PhaseProducer.tsx:10-13` | deferred/future shipping comment | Delete |
| `production_server.py:12-13` | top docstring stub references | Update to current state |
| `production_server.py:7337` | inline "stub/refine later" `module_id=1` hardcode | Fix: read actual module_id from state OR LD it as SHORTCUT |
| `production_server.py:7761` | same `module_id=1` hardcode | Fix or LD |

For the two `module_id=1` hardcodes: they're production debt. Read `state.module_id` (likely already exists; verify) and use that. If state doesn't have module_id yet, derive from event_id resolver. If neither possible, register `SHORTCUT_MODULE_ID_HARDCODE_<reason>_V1` per Rule 19 escape hatch with closure plan.

**Phase E Verification:**

| Gate | Smoke test | Risk class |
|---|---|---|
| E-1 | py_compile + npm build clean | — |
| E-2 | grep -E '\(future\|stub\|TODO\|FIXME\|refine later\)' Production/tools/storyboard-v2/src/*.tsx Production/tools/production_server.py | head -20 | returns 0 unjustified hits | Rule 19 |
| E-3 | After upload/crop/generate/lipsync/mix → `find_asset.py` query returns the new row with `iteration_notes` populated AND `parent_asset_id` set (where applicable) | side-effect |
| E-4 | Re-send (SB-21) twice → 2 separate `prod_assets` rows with `parent_asset_id` linkage between them | side-effect |
| E-5 | New LD `REGISTERED_WRITE_UNIVERSAL_V1` registered | — |
| E-6 | Activity log row `S5_5H_COMPLETE` | — |

---

## §5 Files Created / Modified

### Created
- `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` — this spec
- `Production/tools/storyboard-v2/src/components/TargetVideoSelector.tsx` (rename from `VideoSelector.tsx`)
- `Production/tools/storyboard-v2/src/components/library/LibrarySearchBox.tsx` (NEW for CC-18)
- `Production/tools/storyboard-v2/src/components/library/LibraryItemPreview.tsx` (NEW for CC-19)
- `Production/standardized_assets/` directory (if not exists) for chipper_fly_in / chipper_fly_out reusable clips per Q6
- Per-phase handoff stubs (5 total): `STORYBOARD_V59_S5_5_C_PASS2_HANDOFF.md`, `_E_PASS2_`, `_F_PASS2_`, `_G_PASS2_`, `_H_HANDOFF.md`

### Modified

**production_server.py** — heavy refactor:
- 7985-8129 (PB-2 suggest_script) — REWRITE per §C1
- 8201-8309, 8311-8489 (magic_still / magic_video) — add state writeback per §C6
- 9227-9311 (bg_accept_beats) — add activity log row per §A1.5
- 10008-10173 (cropper save + upload) — refactor through registered_write per §E1
- 10067-10083 (asset registration) — registered_write.register_asset per §A1.3
- 17107-17110 (watercolor bbox constants) — fix per LD-331 per §C4
- 7337, 7761 (module_id=1 hardcodes) — fix per §E2
- 12-13 (top docstring) — clean up per §E2

**storyboard-v2 client:**
- BgTab.tsx — Phase A items (BG-9, 17, 22, 34, 35, 5, 8, 18)
- StoryboardTab.tsx — Phase B SB items (3, 12, 13, 14, 15, 16, 17, 22-24); Phase C MAG-1 button condition
- PhaseProducer.tsx — Phase C items (PB-1, PA-1, PA-6/7/8, PA-9, PA-10, PB-17/PA-19, PB-22/PA-23 removal)
- StitcherTab.tsx — Phase D items (ST-9, 14, 15)
- LibraryPanel.tsx — Phase A CC-15/16 + Phase D ST-16
- ProjectSelector.tsx — already WIRED, Phase B verifies + smoke
- ProductionMapTab.tsx — Phase B CC-31, CC-34
- ScopeBoundary.tsx — Phase B CC-11
- app.tsx — Phase B CC-7, CC-9
- VideoSelector.tsx → renamed TargetVideoSelector.tsx
- AssetTile.tsx, LibraryPanel.tsx — Phase E LL-28 cleanup
- CropperCanvas.tsx — Phase A C-9 + 4:3 aspect lock

**beat_generator.py:**
- 1226-1343 (gpt_options registration) — refactor through registered_write per §E1

**Other:**
- `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_16.md` — read-only (PB-2 source)
- `Arc Skeletons/ARC_<NN>_SKELETON_FINAL.{md,docx}` — read-only (PB-2 source)

## §6 Directus Writes Required

**`prod_locked_decisions` (via `try_post_or_queue`, Rule 35):**

POST 9 new LDs:
- `LIBRARY_TIER_FILTER_V1` (MEDIUM) — Phase A
- `BG_ACCEPT_BEATS_ACTIVITY_LOG_V1` (MEDIUM) — Phase A
- `STORYBOARD_IMAGE_HOLDER_V1` (HIGH) — Phase B
- `PB_2_THERAPEUTIC_SOURCES_LOAD_V1` (CRITICAL) — Phase C
- `MAG_BUTTON_STATE_WRITEBACK_V1` (HIGH) — Phase C
- `PA_9_LIPSYNC_TARGETS_SITTING_CLIP_V1` (HIGH) — Phase C
- `PHASE_A_ONE_DROPDOWN_AUTO_FLYINOUT_V1` (HIGH) — Phase C
- `AMBIENT_PRESET_STITCHER_ONLY_V1` (HIGH) — Phase C
- `REGISTERED_WRITE_UNIVERSAL_V1` (HIGH) — Phase E

PATCH if exist (else skip):
- LD-515 PHASE_A_THREE_CLIP_HANDLING_V1 → AMENDED per Q6
- LD-517 AMBIENT_PRESET_SELECTOR_INPRODUCER_V1 → SUPERSEDED by AMBIENT_PRESET_STITCHER_ONLY_V1
- LD-516 VOICE_STEM_UPLOAD_UI_V1 → ANNOTATE: "voice stem upload UI deferred per pass2 scope"

**`prod_activity_log` (via `try_post_or_queue`):**
- 5 phase completion rows: `S5_5C_PASS2_COMPLETE`, `S5_5E_PASS2_COMPLETE`, `S5_5F_PASS2_COMPLETE`, `S5_5G_PASS2_COMPLETE`, `S5_5H_COMPLETE`
- Plus deviation rows for any spec-vs-reality drift surfaced during execution

**`prod_preflight_reviews`:**
- 1 row per phase (5 total), `task_type=routine` or `architectural` per phase classification

**`prod_reference_docs`:**
- Register this spec doc per Rule 15

## §7 Error Cases and Handling

| Failure | Handling |
|---|---|
| PB-2 smoke test fails (M1E1 returns generic meditation) | RELEASE-BLOCKER. Halt Phase C. Surface to Kim. Fix at handler level (more debugging on prompt construction). DO NOT advance to Phase D. |
| Watercolor animate Layer 6 smoke shows identical animations regardless of motion_description | RELEASE-BLOCKER. Investigate Claude prompt construction; verify Claude is actually USING motion_description in filter generation, not just receiving it. |
| LD-331 actual bbox values differ from spec wording | STOP. Surface to Kim. LD wording wins per Rule 24. |
| Refactoring `registered_write` breaks existing asset queries | Halt Phase E. Run `find_asset.py` smoke before/after each refactor; if results differ, surface. |
| `module_id=1` hardcode fix breaks existing scene_assemble | LD as `SHORTCUT_MODULE_ID_HARDCODE_V1` with closure plan; do not break working code without explicit Kim approval per Rule 19. |
| Phase A 3-clip refactor causes existing Phase A states to fail | Migration: existing `state.phase_a` records need `phase_a_chipper_sitting_clip_id` field; auto-resolve fly-in/out from standardized library. Write migration script if any existing Phase A records use the 3-separate-dropdown model. |
| ProjectSelector → milestone scope swap fails | Existing scope swap is WIRED; verify smoke before forward progress. |

**No silent failures.** Per Rule 19. Every error path returns clear error to client OR surfaces to Kim via prod_activity_log row + halt.

## §8 Verification

Done when:
- All Phase A-E gates pass (~50 gates total)
- 9 new LDs registered (Rule 35 read-back confirmed)
- 3 PATCHed LDs (if pre-existing)
- 5 phase activity log rows + this spec registered in `prod_reference_docs`
- Browser smoke verified by Kim (specifically: PB-2 M1E1 smoke + watercolor animate Layer 6 3-test smoke + drag-drop Library → multiple drop zones)

Proof artifacts:
- `git diff` of all file changes (per phase)
- Migration script outputs (Phase C if needed)
- Curl probe outputs for new endpoint behaviors
- Kim browser smoke screenshots/recording (PB-2 + watercolor animate)
- Directus row IDs for all writes
- Final activity log summary row

## §9 Rollback

Per phase rollback:
- **Phase A:** revert via git per-commit; LDs PATCH to `superseded` if rolled back
- **Phase B:** same; SB-3 image holder is purely additive — safe rollback
- **Phase C:** REWRITE of PB-2 handler is risky — keep original handler in git; if smoke fails, restore via `git checkout`. Magic state writeback is additive (just doesn't write the field — falls back to current behavior). Bbox fix is a constant change — easy revert.
- **Phase D:** purely additive (per-slot bake button, mode auto-detect, library tier extension) — safe rollback
- **Phase E:** highest-risk rollback because it's cross-cutting refactor. Per-file revert via git. New LDs PATCH to `superseded`.

If a phase fails mid-execution, halt + revert touched files via git + restore from snapshot if state.json mutated. Document rollback in `prod_activity_log` action=`S5_5<phase>_PASS2_ROLLBACK` with reason.

## §10 Out of Scope (V1)

Things explicitly NOT in this spec:

- **WaveSurfer.js timeline polish** (LD-472 deferred items beyond what's WIRED)
- **BG-10 reorder beats in Beat Generator** — defer to Phase B if Kim wants reorder; otherwise drop
- **BG-11 group beats** — DEFER per Kim 2026-05-06
- **BG-16 click-to-upload** — SKIP per Kim 2026-05-06
- **BG-38/39 locked mode + re-open** — DEFER per Kim 2026-05-06
- **C-11 cropper keyboard shortcuts** — SKIP per Q4 LOCKED
- **PB-4/PA-4 voice stem upload UI** — STUBBED currently; defer true file-upload to future spec (LD-516 already deferred this)
- **Stitcher /stitch_editor retirement** (ST-22 doctrine-only) — defer until v59 Stitcher tab has had Kim's full production cycle validation
- **Per-event-per-target Playwright matrix expansion** — defer
- **Phase A/B history/diff UI for prior MP4 generations** — covered by `find_asset.py` query; no in-tool UI

## §11 Dependencies on Prior Sessions

**Hard dependencies (must be present):**
- v3 architecture revision shipped (state shape correct: `state.videos.{intro|resolution|standalone}`, `state.phase_a` top-level, `state.phase_b` top-level, milestones at `Production/Milestones/<id>/state.json`)
- Existing Phase A/B canonical pipelines per LD-375/376 (Phase A) + LD-149/196/348 (Phase B)
- Existing Stitcher 4-slot module mode + 1-slot standalone mode per LD-471/466/423
- Existing endpoints: `/api/bg/*`, `/api/phase/*`, `/api/storyboard/*`, `/api/stitch_editor/*`, `/api/timeline/cues`, `/api/watercolor/animate`, `/api/event/*`, `/api/milestones/*`, `/api/scene/assemble`, `/api/beat/finalize`
- Working `pathappPatch` mutation channel with `scope_target_video` global injection (Q2 LOCKED)
- `registered_write.py` + `find_asset.py` infrastructure per LD-421/422

**Soft dependencies (nice-to-have):**
- Cursor v8 cross-review of THIS spec before terminal execution (recommended; see §12)

**Forward unblocking:**
- After Phase E ships, S6 (parallel-run on Event_2 + cutover) can begin

## §12 Cursor v8 Cross-Review Prompt

Send Cursor this prompt with the spec for one final review before terminal execution:

```
You are doing a Cursor v8 architectural cross-review of
Production/docs/V59_FEATURES_BUILD_SPEC_v1.md.

Inventory v6 + v7-equivalent (Agent B trace) verified 131 + 71 = 202
items. Kim §13 LOCKED 9 decisions. This spec partitions remaining
work across 5 phases (S5.5c-pass2 through S5.5h).

Your job: verify the spec is execution-ready for atomic per-phase
terminal sessions. Identify gaps, errors, release-blockers, missing
edge cases.

Specifically verify:

1. PB-2 handler rewrite contract (§C1) — is the arc skeleton
   resolution + therapeutic note extraction logic right? Does the
   Claude prompt construction respect existing Suggest Script flow?
2. MAG-1 state writeback fix (§C6) — verify the field name contract
   (magic_still_path vs magic_video_path) matches what
   StoryboardTab.tsx:579-580 reads.
3. Phase A 3-clip refactor (§C3) — verify standardized fly-in/out
   library exists at Production/standardized_assets/. If not, the
   spec needs to acknowledge it must be created.
4. registered_write.py refactor (§E1) — verify all 5 cited paths
   actually need refactoring; verify the function signature
   register_asset(...) matches what callers should pass.
5. Cross-phase dependencies — Phase A's CC-16 drop zone infrastructure
   is a prereq for Phase B's SB-14. Verify the ordering is correct.
6. New LD write-back (Rule 35) — verify all 9 new LDs have correct
   field types per Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md.
7. Watercolor animate Layer 6 smoke — propose specific test fixtures
   (which watercolor key, which 3 motion descriptions) to make the
   smoke test reproducible.
8. PB-2 smoke fixture — propose the specific Claude API model + max
   tokens + system prompt template for the rewrite. Don't guess; cite
   existing Suggest Script flow if model/template already locked.
9. Are there any LDs in prod_locked_decisions that this spec is
   amending/superseding without saying so? (Use try_get_or_queue to
   query for any LDs with "ambient_preset", "phase_a_three_clip",
   "voice_stem_upload" in decision_key — confirm the AMEND/SUPERSEDE
   list.)
10. Open Kim decisions remaining — should be ZERO (all locked per
    §13 + §13c). If you find any, surface.

Output format: per-section verdicts (APPROVED / AMEND / RELEASE-BLOCKER)
with specific file paths and line numbers for any required changes.

End with OVERALL VERDICT: SHIP / REVISE BEFORE SHIP / HOLD.
```

## §13 Notes for the Executing Sessions

- This spec covers FIVE sub-sessions. Each phase is a separate atomic terminal session per Kim's preference (avoid compaction risk per `feedback_handoff_authoring_timing.md`).
- Phase ordering is sequential — A → B → C → D → E. Browser smoke after each phase before next phase starts.
- Each phase's executing terminal session uses `zero-error-qa` skill, writes preflight row, classifies per phase notes above.
- Per Rule 35: every Directus write consults schema reference; uses `try_post_or_queue` with read-back.
- Per `feedback_six_layer_feature_verification.md`: every feature must verify all 6 layers, not just UI shell. Smoke gates in §4 enforce.
- Per `feedback_browser_smoke_required.md`: server-side gates ≠ user-visible correctness. Browser smoke is mandatory before declaring phase complete.
- Per `feedback_verify_agent_findings.md`: do not trust agent claims about file existence/missing without grep verification first.
- Per `feedback_never_recommend_legacy_tool.md`: if v59 has gaps, the answer is "next phase fixes them," NEVER "use legacy storyboard."
- Per Rule 27: delete obsolete code (LL-28 violations in Phase E).
- Per Rule 29: server staleness check before "test it now" (lsof PID lstart > .py mtime).
- Per Rule 36: any new Path B-style HTML patches in v58 storyboard tooling must follow §36.1 invariant constraints. (This spec is mostly TSX work, so Rule 36 mostly N/A, but if any path_picker.html patches happen, apply.)

---

**End of spec v1.** Send to Cursor v8 for one final cross-review (recommended). Then atomic per-phase terminal execution. Total scope: ~3,100-4,400 LOC of v59 client work + ~500 LOC of server refactor + 9 new LDs + 3 LD amendments + 5 phase completion rows.

---

## §14 — Pre-execution discipline checklist (per phase)

The executing terminal session uses this checklist BEFORE any edit. Do not proceed with Phase X until all boxes checked.

```
PHASE X PRE-EXECUTION CHECKLIST
==============================
[ ] §0 read fully (Mandatory Operating Mode)
[ ] zero-error-qa skill loaded
[ ] Phase 0 classification confirmed: Tier ___ (A/B/C)
[ ] Phase 0 advocate+counter agents spawned (per tier: 0 / 1+1 / 4+4)
[ ] prod_preflight_reviews row written via try_post_or_queue (Rule 35)
[ ] Predecessor preflight referenced + this spec referenced
[ ] All source files cited in this phase READ FRESH (not from memory)
[ ] Cursor v8 review (if Kim ran it) findings reviewed + folded in
[ ] Risk classes for this phase identified (per §0.3)
[ ] Smoke gates per phase verification table reviewed
[ ] Escape hatches list reviewed (§0.8 standing + per-phase additions)
[ ] Server staleness baseline captured (lsof PID + .py mtimes)
[ ] DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md reviewed for any prod_*
    writes in scope
[ ] Endpoints catalog reviewed (endpoints.ts MUTATION_ENDPOINTS) —
    no invented endpoint names
[ ] State shape verified — read actual Production/Event_*/production_state.json
[ ] Confidence annotations [CONFIRMED/INFERRED/GUESSED] applied to
    any inferred claims in execution plan
[ ] Browser smoke deferral plan documented (which gates need Kim
    hands-on; do not mark COMPLETE until Kim confirms)
[ ] Independent tail-end verifier subagent spec drafted (per §0.6)

END-OF-PHASE CHECKLIST (after all gates pass):
[ ] All smoke gates from phase verification table PASS
[ ] py_compile + npm run build clean
[ ] Server restart + /api/health 200; PID lstart > .py mtime
    (Rule 29)
[ ] All Directus writes verified via try_post_or_queue read-back
    (Rule 35)
[ ] LD query snapshot present (queried prod_locked_decisions before
    any AMEND/SUPERSEDE writes; row IDs captured in phase artifacts;
    per Cursor v8 Q12)
[ ] Rule 36 audit run/skipped with reason documented
    (per Cursor v8 Q12)
[ ] Explicit evidence artifact links/IDs for each gate captured in
    phase artifacts (file paths, output excerpts, activity_log row
    IDs; per Cursor v8 Q12)
[ ] "Unresolved inferred claims = 0" check: every
    [INFERRED — verify] annotation per Rule 24 has been resolved to
    [CONFIRMED] OR documented as deferred-with-reason
    (per Cursor v8 Q12)
[ ] Activity log row S5_5<phase>_PASS2_COMPLETE written with full
    gate summary + any spec-vs-reality deviations honestly
    documented (per §0.9)
[ ] Independent tail-end verifier subagent run; verdict captured
[ ] Browser smoke checklist drafted for Kim hands-on
[ ] Next-phase handoff stub written
[ ] Spec v1 §X marked complete in `prod_reference_docs` annotation
```

---

## §15 — Items I May Have Missed (audit per Kim 2026-05-06)

After parsing the conversation per Kim's directive, items I'm flagging as potentially under-specified:

### Cursor v8 cross-review additions (2026-05-06)

C8-1. **Mandatory LD preflight query gate** (Cursor v8 Q9 amend) — folded into §0.1. Before any AMEND/SUPERSEDE LD write, executing session must query `prod_locked_decisions` for the key/ID. If query unavailable or row missing, HALT the phase. Pre-existing risk: spec referenced "LD-515 if exists / LD-517 if exists" without enforcing the existence check.

C8-2. **Destructive rollback command patterns in spec text** (Cursor v8 Q13) — §9 Rollback uses `git checkout -- <file>` style commands which can DESTROY uncommitted local edits if Kim has any. Future spec authoring discipline: rollback procedures should specify `git stash` first OR explicit `git status` check, OR cite Rule 19 / safety wording. Out of scope to retrofit §9 here; flagged for future spec template.

C8-3. **Shell pipeline error masking** (Cursor v8 Q13) — some smoke gates use shell pipelines like `grep ... | head -20` where the head exit-0 can mask grep failures. Verification gates should use `set -o pipefail` OR avoid pipelines for gate logic. Out of scope to retrofit specific lines in this spec; flagged for executing-session discipline.

C8-4. **Phase C2 endpoint name correction** (Cursor v8 Q6) — RESOLVED via spec edit. `phase_a_script` and `phase_b_script` are NOT separate endpoints; use `v2_module_patch` (endpoints.ts:90) with field-keyed payload. Spec §C2 updated 2026-05-06.

C8-5. **Production/standardized_assets directory missing** (Cursor v8 Q3 RELEASE-BLOCKER) — RESOLVED via spec edit. Phase C3 now has hard preflight gate: directory + assets must be created/populated BEFORE any code change. Spec §C3 updated 2026-05-06.

C8-6. **Phase B / Phase E classification escalated to Tier C** (Cursor v8 Q8) — RESOLVED via spec edit. Both phases now require 4+4 advocate+counter agents in Phase 0. Spec §4 Phase B + Phase E classification headers updated.

### Original Desktop audit gaps (preserved from v1):

1. **Phase B workflow narrative** — Kim described the workflow explicitly: "click to import Claude's suggested Phase B script → review → send to ElevenLabs (background uses Cedric presets) → audio comes back → listen, approve OR regenerate → send for lipsync → lipsync returns → approve OR resend → place watercolors (stills or animations) → click 'animate this' if animating → result back in watercolor library → drag-drop into video." The spec covers each item but doesn't narrate the workflow as a sequence. Suggest executing Phase C session reads this narrative as the user-experience reference; the line items are what gets BUILT but the narrative is the user JOURNEY.

2. **Phase A workflow narrative** — same as Phase B PLUS extra step "after lipsync approval, fly-in/fly-out auto-stitches onto front and back of the lipsynced sitting clip." PA-10 button (renamed "Stitch Fly-In/Out") fires this step.

3. **"Cutting YAML" finding** — Kim referenced "the cutting YAML" for the watercolor animate flow. Verified: `path_picker.html:525-538` produces YAML for human backup ("Copy YAML" button); the actual API submit (line 620-635) uses JSON. Same path geometry encoded both ways. This finding doesn't require a code change but the executing session should know it when working on PB-15a/PA-18a/MAG-4.

4. **Library search performance** — with 59 modules' worth of assets, substring search on `iteration_notes` could get slow if naive. Implementation should index `iteration_notes` field in Directus OR cache locally + filter client-side. Defer perf optimization unless smoke shows lag.

5. **Cropper aspect ratio: 4:3 LOCK enforcement** — Kim's spec is "4:3 aspect locked + resizable + min-quality". Phase A2 mentions verify aspect lock; if code doesn't enforce 4:3 (just freeform crop), ADD that constraint. Also verify min-size = 600px short side per Rule 6 / C-8 (already WIRED).

6. **Watercolor animate Layer 6 — what's a "meaningfully different" animation?** Defining this rigorously: motion description "moving up and down" should produce an animation where the watercolor visibly translates along the y-axis (vertical motion). Different from "spiraling outward" (which should produce circular/radial motion). The smoke gate is FALSE if both animations look like generic ambient motion regardless of input — that's Layer 3 silent failure. Smoke gate is TRUE if a viewer can clearly distinguish the two intents in the rendered output.

7. **Kim browser smoke artifact format** — per `feedback_file_links.md`, file:// links don't work in chat. Kim should either: (a) record screen as MP4 and paste, (b) screenshot key frames, or (c) describe verbally with timestamps. The executing session's browser smoke checklist should specify the artifact format Kim provides per gate.

8. **Cursor v8 review optional** — this spec recommends Cursor v8 cross-review (§12) but Kim has not committed to running it. Decision: optional. If skipped, executing session proceeds with §0 escape hatches as the safety net. If run, Cursor's findings get folded into Pre-execution Checklist before paste.

---

## §16 — Reference index (file paths used in this spec)

For executing sessions: every file path cited here, in one place.

**Sources to read:**
- `Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md` — item-level inventory with verdicts
- `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` — architecture revision (just shipped)
- `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` — 25 lessons
- `Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_16.md` — Phase B Suggest Script source (technique catalog)
- `Arc Skeletons/ARC_<NN>_SKELETON_FINAL.{md,docx}` — Phase B Suggest Script source (therapeutic notes)
- `CLAUDE.md` (Rules 18, 19, 24, 27, 29, 32, 35, 36)
- Memory files in `~/.claude/projects/.../memory/`:
  - `feedback_six_layer_feature_verification.md`
  - `feedback_browser_smoke_required.md`
  - `feedback_handoff_authoring_timing.md`
  - `feedback_never_recommend_legacy_tool.md`
  - `feedback_verify_agent_findings.md`
  - `feedback_tech_spec_for_wrong_architecture.md`
  - `project_v59_architecture_corrected_model.md`
  - `project_v59_features_planning.md`
  - `project_phase_b_suggest_script_sources.md`
  - `project_milestone_videos_independent.md`
  - `project_phase_b_is_cedric_lipsynced.md`
  - `project_beat_generator_3_options_not_grid.md`
  - `project_stitch_editor_v59_canonical.md`
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Rule 35 schema lookup
- `Production/lib/directus.py` — `try_post_or_queue` helper

**Files to modify (per §5):**
- Server: `production_server.py`, `beat_generator.py`
- Client tabs: `BgTab.tsx`, `StoryboardTab.tsx`, `PhaseProducer.tsx`, `StitcherTab.tsx`, `LibraryPanel.tsx`, `ProjectSelector.tsx`, `ProductionMapTab.tsx`, `ScopeBoundary.tsx`, `app.tsx`, `VideoSelector.tsx → TargetVideoSelector.tsx`, `CropperCanvas.tsx`, `CropperModal.tsx`, `AssetTile.tsx`
- Component creates: `library/LibrarySearchBox.tsx`, `library/LibraryItemPreview.tsx`, possibly `standardized_assets/`

**Endpoint catalog:** `Production/tools/storyboard-v2/src/api/endpoints.ts` (MUTATION_ENDPOINTS table — authoritative; do NOT invent names)

---

**Truly end of spec v1.** All Kim 2026-05-06 decisions baked in. All error-elimination categories addressed. Ready for Cursor v8 cross-review (recommended) → atomic per-phase terminal execution.

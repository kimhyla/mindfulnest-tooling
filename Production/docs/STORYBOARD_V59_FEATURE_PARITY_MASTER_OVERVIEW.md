# Storyboard v59 — Feature Parity Master Overview (post-v3 architecture)

**Date:** 2026-05-03
**Status:** Master overview pointing at 4 sub-session specs
**Classification:** Multi-session feature build on stable v3 architecture (NOT another architectural revision)
**Parent context:** v3 architecture revision shipped 2026-05-03 (37/37 gates green; 12 new LDs; 2 supersedes)
**Locked decisions baked in:**
- Beat Generator = 3 options per beat (NOT 3×3 matrix, NOT 9 stills, NOT FLUX) — `project_beat_generator_3_options_not_grid.md`
- Phase B IS Cedric lipsynced video (memory entry corrected) — `project_phase_b_is_cedric_lipsynced.md`
- Production Map data sources from `GAMEPLAY_SCOPE_v3.md` (FROZEN V1 scope; LD-357)
- v59 Stitcher tab is canonical; port FROM `/stitch_editor` INTO it; retire after parity validated
- Magic compositor cross-platform = OUT of scope (separate tooling); SFX cue placement UI = IN scope (S5.5g)

---

## §1 Why this exists

v3 architecture revision succeeded at making the v59 Preact client architecturally correct (state shape, partitions, milestone scope, export pipeline, drain protocol). Browser smoke 2026-05-03 surfaced ~3,100-4,400 LOC of feature gaps — buttons + UIs that exist as backend endpoints (and/or in legacy server-rendered HTML) but were never ported to the Preact rewrite.

These gaps are NOT another architectural issue. v3 unblocked all of them. They are sequential UI/feature work, split across 4 bounded sessions in production-workflow dependency order.

## §2 Why split, not atomic

Total scope ~3,100-4,400 LOC of net-new TypeScript/TSX. v3 was ~600 LOC of code change + a state migration + ~1100 lines of spec. The feature parity work is ~5× v3's code-change volume.

Atomic landing risks the same mid-session compaction halt that S5.5d hit at Phase B partial. Per LL-11 (lessons-learned 2026-05-03): "atomic single-session pattern works for BOUNDED architectural change" — this exceeds bounded. Split + sequential gives:

1. Each session is shippable independently (~3-4 hr each)
2. Browser smoke gates between sessions catch issues at the layer they were introduced
3. Compaction risk per session is manageable
4. Kim can use partial functionality between sessions

## §3 The 4 sub-sessions — production-workflow dependency order

```
S5.5c  →  S5.5e  →  S5.5f  →  S5.5g
  ↓         ↓         ↓         ↓
 Beat    Storyboard  Phase    Stitcher
 Gen     buttons +   A/B      SFX +
  +      Selectors   parity   trims +
Cropper  + Map data           Map
 + UI                         verify
primitives
```

| Session | Spec | Scope (one-line) | Gates | Status |
|---|---|---|---|---|
| **S5.5c** | `STORYBOARD_V59_S5_5_C_SPEC_v2.md` (revises v1 for v3 readiness) | Beat Generator full UI + Cropper canvas + drag-drop primitives + Modal/Toast/Spinner shared UI components | 17 gates (12 + 5 Phase B0) | **COMPLETE 2026-05-03** — commit `bc12a4d`; LDs 496-499; 17/17 gates green; browser smoke deferred to Kim |
| **S5.5e** | `STORYBOARD_V59_S5_5_E_SPEC_v1.md` (NEW) | Storyboard tab beat-level buttons (regen_audio, use_as_final, send_for_lipsync, preview_beat) + EventSelector → ProjectSelector with milestones + Production Map data populate from GAMEPLAY_SCOPE_v3.md | 14 gates | **COMPLETE 2026-05-03** — commit `bc12a4d` (combined with S5.5c); LDs 500-504; 14/14 gates green; 53 new prod_modules rows (M7..M59); browser smoke deferred to Kim |
| **S5.5c+e PROPER FIX** | `STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` | TDD-ordered combined bugfix (R1 scope deps, R2 drag-drop drop targets, R3 option_key gate, R4 TBD placeholder, R5 library tile sizing) + +NewEvent server endpoint + 3 process structural changes (mandatory e2e standard, CI Playwright workflow, lessons-learned LL-26). Working tree migrated to `kimhyla/mindfulnest-tooling` per LD-505. | 20 gates | **COMPLETE 2026-05-03 (in tooling tree)** — branch `claude/s5_5ce-proper-fix`; LDs 506-510; 17 PASS / 3 DEFERRED (G3 existing scaffold needs Event_1 not in tree; G17/G18 S5.5f/g coverage audit time-box deferred to follow-up PR) / 0 FAIL; CI green run [25301815131](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25301815131); RED proof [25301870632](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25301870632); restore [25301926100](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25301926100). 13/13 e2e tests passing on every commit going forward. |
| **RETROACTIVE COVERAGE v1** | `STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md` | Tests-only sprint — adds Playwright e2e for 6 retroactively-untested surfaces (S1 beat lifecycle / S2 pathappPatch persistence / S3 StoryboardTab refresh / S4 magic compositor / S5 library rendering / S6 ProjectSelector+ScopeBoundary). 41 new tests. NO production code modified. Bugs surfaced: F-S2-001 StitcherTab raw-fetch mutations, F-S2-002 VideoSelector raw-fetch mutations, F-CI-001 missing PyYAML, F-SVR-001 sidecar TypeError — all logged + deferred per Rule 3. Spec drift documented (S5.5e bg_finalize/unlock endpoint names superseded by S5.5d v3; S4 magic UI is in StoryboardTab not BgTab). | 8 gates (G1-G8) | **COMPLETE 2026-05-04** — branch `claude/retroactive-coverage-sprint`; preflight #202 (predecessor #201, activity_log #1494); LD `RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE` (SOFT); 8/8 gates PASS / 0 FAIL; CI green run [25319006667](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25319006667) — 54/54 e2e tests passing (13 R-tests + 41 retroactive); RED-then-GREEN iteration documented via run [25318767660](https://github.com/kimhyla/mindfulnest-tooling/actions/runs/25318767660). Results doc: `Production/docs/RETROACTIVE_COVERAGE_RESULTS_V1.md`. |
| **S5.5f** | `STORYBOARD_V59_S5_5_F_SPEC_v1.md` (incl §19 amendment) | Phase A/B feature parity: WaveSurfer.js v7 timeline + watercolor drag-drop cue authoring + CuePopover (3-value live animation enum per §19.10) + Phase A 3-clip handling (fly-in / sitting / fly-out) + Generate-stem-from-script button + ambient preset selector + new server endpoint `/api/phase_b/ambient_preset_list` + workflow extension | 18 gates (F1-F18) | **COMPLETE 2026-05-04** — branch `claude/s5_5f`; preflight #203 + activity_log #1497 (PHASE_A_PREFLIGHT) + #1499 (CHECKPOINT_AT_PHASE_A_DONE) + #1500 (S5_5F_COMPLETE); LDs 512 WAVESURFER_TIMELINE_INTEGRATION_V1 / 513 WATERCOLOR_DRAG_DROP_TIMELINE_V1 / 514 CUE_POPOVER_INSPECTOR_V1 / 515 PHASE_A_THREE_CLIP_HANDLING_V1 (all HARD) + 516 VOICE_STEM_UPLOAD_UI_V1 / 517 AMBIENT_PRESET_SELECTOR_INPRODUCER_V1 (SOFT); 18/18 F-gates PASS; F17 grep ZERO hits; CI green via Playwright workflow (proper-fix 13 + s5_5f 18 = 31 tests on every push); commits 3f105c0 (Phase A) → 43ca045 (handoff) → 5215125 (Phase B) → ef554c7 (Phase C) → 64bdc50 (Phase D) → 39c46a3 (Phase E) → a7f223a (Phase F). |
| **WAVE 1 ARCHITECTURAL FIX** | `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` (incl §14-§16 Cursor v11 + Wave-1 framing) | Wave 1 of comprehensive retroactive coverage program. Fixes 4 prod_blockers from retroactive v1 (#46-49 → resolved): F-S2-001 StitcherTab 3 raw fetches → pathappPatch; F-S2-002 VideoSelector 2 raw fetches → pathappPatch; F-SVR-001 sidecar TypeError root-cause guard at `production_server.py:3885`; F-CI-001 `Production/tools/requirements.txt` extracts inline pip. Adds mandatory `MUTATION_CHANNEL_INVARIANT_V1` grep gate (G13) — blocking step + strict warning step (Kim's two-step Option 2 design). | 13 gates (G1-G13) | **COMPLETE 2026-05-04** — branch `claude/architectural-fix-mutation-channel`; PR #4 merged squash `1b40d1b`; preflight #204 + activity_log #1502; LDs 519 MUTATION_CHANNEL_INVARIANT_V1 / 520 SERVER_SILENT_FAILURE_FAIL_LOUD_V1 (both HARD) / 521 PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1 (SOFT); 81/81 CI tests green; RED→GREEN proof commits ed89fa5 → c1c9499. **4 NEW prod_blockers logged for Wave 3** (#50-53 — incidentally-found event_load raw-fetch violations in ProjectSelector × 2, EventSelector, ProductionMapTab; per scope guard + Cursor R6, NOT fixed in Wave 1). |
| **S5.5g** | `STORYBOARD_V59_S5_5_G_SPEC_v1.md` (incl §14 + §19 + §20 + §21 R1-R5 fold) | Stitcher SFX cue placement + per-boundary transitions (incl dissolve with audio_xfade_ms per Q1) + per-slot trims via stitch_save_job extension + Production Map multi-event mapping fix + Phase F verification only per §19.10 | 16 gates | **COMPLETE 2026-05-04** — branch `claude/s5_5g`; preflight #205 + activity_log #1507 (S5_5G_COMPLETE) + #1508 (STORYBOARD_V59_FEATURE_PARITY_COMPLETE); LDs 523 STITCHER_SFX_CUE_UI_V1 / 524 STITCHER_TRANSITIONS_V1 / 525 STITCHER_PER_SLOT_TRIMS_V1 / 526 STITCHER_RAW_FETCH_MIGRATED_V1 (all HARD) / 527 PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 (SOFT) / 528 V59_CLIENT_FEATURE_COMPLETE_V1 (HARD closure); 16/16 gates green; G14 Wave 1 grep gate verification PASS (0 StitcherTab raw-fetch hits). CI green via Playwright workflow (proper-fix 13 + retroactive 41 + s5_5f 18 + architectural-fix 9 + s5_5g 9 = 90 tests); commits fd9ebfd (Phase A) → 7d7f701 (B RED) → 66db518 (B GREEN) → bf59c66 (B CSS fix) → 980c683 (C RED) → 12f117a (C GREEN) → de7f93b (D RED) → 2d500ee (D GREEN) → dac4707 (E RED) → 57bc15f (E GREEN) → handoff/closeout. **v59 client = FEATURE-COMPLETE**; /stitch_editor retirement clock starts on merge per §19.11.1 (N=14 days; deprecation day 15; deletion day 45). Closeout handoff: `Production/docs/STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md`. |
| **SPRINT E (Wave 4) — server audit** | spec TBD per `STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md` §3 | RECOMMENDED NEAR-TERM per Cursor 2026-05-04 second-opinion review. Audit silent-failure pattern beyond F-SVR-001; pathappPatch envelope acceptance on all server mutation handlers; pre-write state snapshot consistency; concurrency / drain protocol coverage. ~4 hours. | TBD | PENDING |
| **SPRINT B/C/D/F (deferred waves)** | per `STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md` | Opportunistic — promote to "run now" per backlog §6 trigger conditions. Wave 3 (in Sprint D) inherits #50-53 event_load violations from Wave 1's incidental findings. | TBD | DEFERRED |
| **APP ARCHITECTURE FOUNDATION** | `Production/docs/MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` (Cursor APPROVED 2026-05-04 R1-R4 folded) | NOT a storyboard sub-session — separate program. 5 load-bearing discipline pieces (CI from commit 1; test-with-feature spec template; structural enforcement; schema contracts; observability + silent-failure detection) that MUST be in place before feature 1 ships in any app-side repo (iOS, Therapist Dashboard, Parent Dashboard, Functions). LD-518 MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1 (HARD). Master tech spec §14.13 + v6.2 changelog already point to this spec. Activates whenever app-side work begins. | per spec §9 | LOCKED — ready to drive app foundation work |

**Total verification gates across 4 sessions:** ~56 gates (vs v3's 37)

## §4 Why this specific ordering

**Production workflow:** Beat Generator → Storyboard processing → Phase A/B production → Stitcher final assembly.

Each session unblocks the next layer of Kim's actual workflow:
- **S5.5c first:** Without Beat Generator, Kim can't AUTHOR new beats. This is the bottleneck.
- **S5.5e second:** Without per-beat buttons, beats can't be PROCESSED into ready-for-stitching MP4s (TTS regen, animation, lipsync).
- **S5.5f third:** Phase A/B videos are already creatable via existing UI; this session adds production polish (waveform, drag-drop, etc.).
- **S5.5g last:** Final assembly. Consumes everything from prior sessions.

## §5 Things that already exist (DO NOT rebuild in any session)

Verified by direct code inspection 2026-05-03 (Agent B's report had errors; cross-checked):

- `src/components/tabs/PhaseATab.tsx` + `PhaseBTab.tsx` — exist + registered in TabBar
- `src/components/TabBar.tsx` — production order tabs with `eventOnly: true` for Phase A/B
- `src/state/scope.ts` — `activeScope`, `activeTargetVideo`, `activeProjectType`, `activeMilestoneId` signals all live (lines 38, 56, 63, 64)
- `src/components/VideoSelector.tsx` — has v3 CANONICAL_ROLES update + VIDEO_ROLE_PER_REQUEST_V2 reference (line 37)
- `src/api/client.ts:170` — `pathappPatch` is the canonical mutation channel; auto-injects scope fields
- `src/components/StoryboardTab.tsx:234-300` — magic-on-still / magic-on-video buttons (LD-468/469) wired
- `src/components/StoryboardTab.tsx` — Send Out as MP4 button POSTs to `/api/scene/assemble` (v3 export pipeline) **but currently via raw fetch (~L328-347), NOT via `pathappPatch`**. Migrating this is part of S5.5e §3.5. Per Cursor v8 finding.
- `src/components/StitcherTab.tsx` — 4-slot strip + Ambient + Preview + Loudnorm + Bake (basic stitching working)
- `src/components/ProductionMapTab.tsx` — table renders correctly; just needs full data
- `src/components/LibraryPanel.tsx` — right-rail asset library renders (just no drag/drop yet)

## §6 Things that DO NOT exist yet (the gap inventory each session covers)

### Beat Generator (S5.5c)
- Extract Beats button + flow
- 3-options-per-beat display grid (UI for what backend already returns)
- Per-beat dialogue editor with stage-direction chip extraction
- Per-beat character ref + BG ref upload slots
- Add/delete beat controls
- Cost display
- Accept All wiring (currently sends empty `beats: []`)

### Cropper (S5.5c)
- Real `<canvas>` (currently ships 1×1 placeholder PNG per `CropperModal.tsx:64-65`)
- Crop selection rectangle (drag/resize handles)
- Aspect ratio constraint
- Image upload via `cr_upload`
- Library delete UI via `cr_library_delete`

### Shared UI primitives (S5.5c)
- `Modal` component (CropperModal is one-off)
- `Toast` / `Snackbar` (only ScopeBanner exists, single-purpose)
- `Spinner` / progress component
- Generic `<Select>`, `<Tabs>`, `<Tooltip>`
- Drag/drop helper (HTML5 dataTransfer)

### Storyboard beat-level buttons (S5.5e)
- Regenerate Audio (TTS) — `POST /api/beat/regenerate_audio`
- Use as Final (no-lipsync path) — `POST /api/beat/use_as_final`
- Send for Animation — `POST /api/animate` (3 Kling options/beat)
- Preview Beat (audio playback) — `GET /api/beat/audio/<beat_id>`
- Send for Lipsync (per-beat) — `POST /api/lipsync`
- Select option (which animation to keep) — `POST /api/select`
- Beat delay / trim — `POST /api/beat/delay`, `POST /api/beat/trim`
- Inject image / Assign image — `POST /api/inject-image`, `POST /api/assign-image` (already in endpoints.ts but never wired)

### ProjectSelector (S5.5e)
- Extend EventSelector to include milestone listing (`GET /api/project/list` returns events + milestones grouped)
- Group dropdown by Events / Milestones with "+ New Milestone" option
- Milestone-create modal with regex validation per v3 spec §3.4.1

### Production Map data (S5.5e)
- One-shot script: parse `GAMEPLAY_SCOPE_v3.md` → POST to `prod_modules` via `try_post_or_queue` (Rule 35) → all 10 arcs / 59 modules visible
- Verify Production Map renders all rows after load

### Phase A/B parity (S5.5f)
- WaveSurfer.js v7 waveform display (per LD-472)
- Watercolor library drag-drop onto timeline (currently opens new tab via `/magic`)
- Cue popover (animation type / duration / Delete) per LD-470 procedural watercolor
- Voice stem upload UI (no `<input type="file">` anywhere in PhaseProducer)
- Ambient preset selector inside producer (currently only in Stitcher slots)
- Phase A 3-clip handling (fly-in / sitting / fly-out — currently only handles ONE base clip)

### Stitcher SFX/transitions/trims (S5.5g)
- SFX cue placement UI on timeline (drag from LibraryPanel onto position) — backend exists at `/api/timeline/cues` POST/DELETE
- SFX library tier filter (ambient / sfx / transitions)
- Per-cue volume / fadein / fadeout sliders
- Transitions between slots (crossfade / cut / dissolve dropdown per boundary)
- Per-slot trim handles on `<video>` scrubber (in/out points)
- Audio extract per slot — `POST /api/stitch_editor/audio_extract`
- Open in QuickTime — `POST /api/timeline/open_in_quicktime`

### Production Map V1 scope verification (S5.5g)
- After S5.5e populated `prod_modules`, verify all 10 arcs × ~6 modules render
- Multi-event mapping (currently uses Event_1 as canonical for ALL modules per `_handle_production_map`:8434) — defer or fix here

## §7 Out of scope across all 4 sessions (defer to S6+)

- Long-term `pinned_video_role` enforcement in `_check_event_pin` (drain protocol fences migration window only)
- Job registry leak fix (`_GPT_JOBS`/`_MAGIC_JOBS`/`_ASSEMBLE_JOBS` accumulate terminal entries forever — documented smell)
- `_handle_bg_submit_flux` thread-ification (currently synchronous, ~30s)
- `_auto_assemble_phase_a_stitched` decorator wrap (parent handlers cover drain gate)
- Magic compositor cross-platform Mac/Windows wiring (separate tooling work, not v59 client)
- /stitch_editor standalone tool retirement (defer until S5.5g parity validated + Kim has used v59 Stitcher for full production cycle)
- Lipsync registry promotion (currently lives in `state.beats[bk].lipsync.status`, not a registry)
- Voice profile management UI (LD-462; backend exists; defer)

## §8 Cross-session conventions (apply to all 4)

1. **Mutation channel:** every state write goes via `pathappPatch(activeScope.value, endpoint, body)` from `src/api/client.ts:170`. NEVER raw fetch. (S5.5g cleanup item: 3 existing raw-fetch sites at StoryboardTab.tsx:310, StitcherTab.tsx:102/128/170, ProductionMapTab.tsx:114 should be migrated.)
2. **Scope auto-injection:** new endpoints get added to `BG_MUTATION_ENDPOINTS` set in `endpoints.ts:72-79` if they expect `scope_event_id`. `pathappPatch` auto-injects `event_id` / `scope_event_id` / `beat_id` / `scope_version`.
3. **Asset registration:** every new media write goes through `registered_write.register_asset(...)` per LD-421/422. Never raw POST to `/items/prod_assets`.
4. **TypeScript strictness:** `exactOptionalPropertyTypes: true`. New optional fields require conditional-spread pattern (see `PhaseProducer.tsx:71-81`).
5. **Test IDs:** every new interactive element gets `data-testid="<noun>-<context>"` per existing convention.
6. **Drain decorator (server-side Python ONLY):** any new heavy mutation handler in `Production/tools/production_server.py` gets `@with_pin_and_drain(handler_name, track_sync=...)` per v3 spec §3.7. There is NO TypeScript equivalent — do not search the Preact tree.
7. **HTML preview pattern:** any Kim-facing previews use `Production/_previews/preview_test_*.html` template + `osascript activate Safari`, NEVER file:// links (per `feedback_file_links.md`).
8. **Git commit:** at end of each session, terminal Claude commits the session's changes with message `S5.5x — <session label> (X gates green)`. NOT after individual phases.
9. **Mandatory e2e coverage (added 2026-05-03 per S5.5c+e proper-fix; LDs `MANDATORY_E2E_GATE_V1` CRITICAL + `CI_PLAYWRIGHT_ON_COMMIT_V1` HIGH).** Every spec's §4 Phase E (or equivalent) gates that test FUNCTIONAL behavior MUST have corresponding Playwright tests in `Production/tools/storyboard-v2/e2e/`. Server-side gate green + e2e gate green is the minimum. Either alone is insufficient. If a behavior cannot be cleanly e2e-tested, that's a redesign signal — surface to Kim before shipping. Rule 19 (no shortcuts) explicitly extends to e2e. Per-session CI inclusion: each session's spec names which `e2e/<session>.spec.ts` files run on the workflow at `kimhyla/mindfulnest-tooling/.github/workflows/playwright_e2e.yml`; expand the workflow's test target list as new sessions land. Browser smoke (Kim hands-on) becomes "does it FEEL right?" subjective UX only — "does anything actually work?" is now automated via e2e per `BROWSER_SMOKE_REDEFINED_V1` MEDIUM.

## §9 Each session's Phase 0 obligations

Every session begins with:
1. Read this master overview + the session's spec FULLY
2. Read v3 spec at `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` for architecture context
3. Read predecessor session's COMPLETE activity log row from `prod_activity_log` to confirm starting state
4. Write `prod_preflight_reviews` row for THIS session via `try_post_or_queue` referencing predecessor preflight as immediate predecessor; confirm via read-back per Rule 35
5. Verify server is fresh (Rule 29) before any UI test
6. Confirm `npm run build` clean before starting any TS edits (no inherited errors)

## §10 Each session's closing obligations

1. Run all gates from spec §8 (verification gate list)
2. Browser smoke (E19-equivalent) — DEFERRED to Kim hands-on. Document deferral in activity log.
3. Write `prod_activity_log` row `S5_5x_COMPLETE` with full gate summary
4. Write S5.5(x+1) handoff stub at `Production/docs/STORYBOARD_V59_S5_5_<next>_HANDOFF.md` (or for S5.5g: write `STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md`)
5. Update this master overview's table with the session's completed status
6. Tail-end verifier subagent (per a1/a2/b/d-cont pattern)
7. Git commit (single commit for the session per §8.8)

## §11 Cursor review checklist (master-level)

Send Cursor each session spec independently. Cross-cutting questions for Cursor across all 4:

1. Is the production-workflow dependency ordering correct? Could any session be moved earlier without breaking dependencies?
2. Is shared UI primitive extraction (in S5.5c) correctly placed first? Without it, do later sessions duplicate work?
3. Are the per-session gate counts (~12-16 each) sufficient for the scope, or should some sessions have more?
4. Are there cross-session integration risks not captured (e.g., signals introduced in S5.5c that S5.5e depends on)?
5. Does any session's "Out of scope" item conflict with another session's "In scope" item?
6. Is the multi-event Production Map fix (S5.5g) too late — should it be in S5.5e since it's a data fix, not a UI port?

## §12 Reference docs (cite, don't re-read)

- v3 spec: `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md`
- v3 handoff: `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_HANDOFF.md`
- v3 lessons learned: `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md`
- S5.5c v1 spec (legacy reference): `Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v1.md` (S5.5c v2 spec supersedes)
- Pre-v3 lessons doc: `LESSONS_LEARNED_May02_2026_Storyboard_Wrap_Chain_Reckoning.md`
- Backend reference (full feature catalog): `Production/tools/build_storyboard.py` (3,492 lines — legacy server-rendered UI; mine for feature surface when porting)
- Frontend reference: `Production/tools/storyboard-v2/src/`

---

## §11 Cursor v8 findings folded into specs (audit trail)

Cursor v8 (2026-05-03) reviewed the 5-document bundle. Per-spec findings folded into v2 of each spec. Bundle-level findings:

| Finding | Resolution |
|---|---|
| Send Out raw fetch claim in §5 was overstated | Corrected; migration in S5.5e §3.5 |
| `@with_pin_and_drain` ambiguity (server vs client) | §6 clarified server-side Python only |
| MUTATION_ENDPOINTS catalog completeness | S5.5c gets new Phase B0 to extend catalog before component wiring |
| `/api/canonical_stitch` route does NOT exist | S5.5f §3.5 corrected — Phase A stitch via `_handle_phase_b_mix_audio` (calls `_auto_assemble_phase_a_stitched` internally) + `v2_module_patch` for clip ID writes |
| `/api/phase_b/ambient_preset_list` route does NOT exist | S5.5f §3.7 corrected — implement filesystem scan endpoint OR static preset list |
| `beat.use_as_final` was wrong field name | S5.5e §3.1 + Q1 corrected — derive final state from `beat.final` block presence (`source`, `source_option`, `file`, `approved_at`) |
| Line refs to raw fetch sites (`:310`, `:102/128/170`) drifted | S5.5e + S5.5g corrected with current line anchors |
| PhaseProducer hardcodes `Production/Event_1/` in fileUrl | S5.5f adds gate to remove hardcode |
| Production Map cell-nav assertion timing | S5.5e gates assert row count + table render only; click-to-correct-event gate moves to S5.5g |
| Handoff stub filename chain consistency | All specs cross-checked; chain c→e→f→g intact |

Send to Cursor v9 only if substantive new design emerges. Otherwise execute.

**End of master overview (v2 — Cursor v8 folded).**

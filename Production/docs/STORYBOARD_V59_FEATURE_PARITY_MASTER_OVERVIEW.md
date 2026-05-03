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
| **S5.5f** | `STORYBOARD_V59_S5_5_F_SPEC_v1.md` (NEW) | Phase A/B feature parity: WaveSurfer waveform, watercolor drag-drop on timeline, cue popovers, Phase A 3-clip handling, voice stem upload, ambient preset selector inside producer | ~16 gates | PENDING — handoff stub at `STORYBOARD_V59_S5_5_F_HANDOFF.md` |
| **S5.5g** | `STORYBOARD_V59_S5_5_G_SPEC_v1.md` (NEW) | Stitcher SFX cue placement + transitions + per-slot trims (port FROM /stitch_editor INTO v59 Stitcher tab) + Production Map full V1 scope verification | ~14 gates | PENDING |

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

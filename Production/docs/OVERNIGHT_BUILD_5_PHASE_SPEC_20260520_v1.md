# Overnight 5-Phase Build Spec — V59 Storyboard

**Marker:** `OVERNIGHT_BUILD_PHASED_20260520_5D300F32ED56`
**Date:** 2026-05-20
**Branch:** `feature/overnight-build-20260518` (per Kim's directive)
**Authority:** Kim's autonomous-mode directive 2026-05-20 04:30 UTC
**Originating activity row:** prod_activity_log id=6038 `COORDINATOR_RESUMPTION_PRE_PHASE_0_V1`

## §0 — Operating Constraints

- **NO Opus agents** (cost ceiling). Cursor + Sonnet + inline only.
- Vendor cost cap: $30/phase, $75 cumulative.
- Positive evidence required for every "done" claim.
- Coordinator resumption row at PRE + POST of each phase.
- Deviation row when scope drifts from spec.
- HONEST HALT: only halt for Kim-workflow/preference/business questions or
  genuine new-tech-spec triggers.
- Default: cursor-consultation → decide → push forward.

## §1 — Phase 0: Close PR #73

**Prereqs (executed before Phase 0 actual):**
- [x] A. 3 cosmetic Rule 24 nits applied inline (paths.py:132, production_server.py:608, production_server.py:11627)
- [x] B. Zero concurrent sessions (10 latest other sessions all isRunning=false, oldest 7+ hours)
- [x] D. This spec written; marker grep verifies presence
- [ ] E. Coordinator PRE row written (id=6038, done)
- [ ] C. Branch creation (deferred to after PR #73 merge)

**Phase 0 work:**
1. Lock `SHORTCUT_CROPPER_LIBRARY_DELETE_V1` LD (Kim's verbal approval 2026-05-19 "she does not use this workflow") — unblocks AI Review on PR #73.
2. Commit + push the 3 cosmetic nits.
3. Wait for CI green on PR #73.
4. Merge PR #73 into main.
5. Create `feature/overnight-build-20260518` branch off main.
6. Write `COORDINATOR_RESUMPTION_POST_PHASE_0_V1` row.

**Exit criteria:**
- PR #73 merged on main
- New overnight branch checked out
- Pytest still ≥276 passed / 0 errors

## §2 — Phase 1: Library flow restoration

Per /tmp/v59_full_qa_audit synthesis + Agent C blockers map.

**Work (dependency-ordered):**
1. **Blocker #150** — Cropper writes WebP but doesn't register in state.
   - Create POST /api/state/register_crop server handler
   - Wire CropperModal save handler to call it
   - Verify crop appears in Library after save
2. **Blocker #59** — Drag library images into option boxes (regression from v58).
   - Port drop-zone handler from v58 storyboard to BeatImageHolder/option-slot
   - Verify drag from LibraryPanel → option box writes correct image_path
3. **Blocker #146** — Stale `{beat_id}_lipsync.mp4` not cleaned on Regen B+C.
   - Add unlink step in `_handle_regenerate_bc` before re-render
   - Verify no orphaned lipsync.mp4 after regen

**Exit criteria:**
- All 3 blockers patched on disk with verifying tests OR smoke-call verification
- prod_blockers PATCH to is_resolved=true with closure rows in prod_activity_log
- Pytest still green

## §3 — Phase 2: Background-morph fidelity + composite preview

1. **LD-730 fix** — Add `input_fidelity:high` to OpenAI end-frame call (ref_doc 231)
2. **Kim batch1 #4** — Investigate BeatCompositePreview silent ▶ / black square
   - Read BeatCompositePreview.tsx end-to-end
   - Trace videoSrc construction
   - File a fix or DEVIATION row if it requires more scope

**Exit criteria:**
- Both items either FIXED with positive evidence OR DEVIATION row written.

## §4 — Phase 3: UI parity audits + Blocker #44

**Cursor-agent driven** (per autonomy default #2 cursor-agent for multi-file work).

1. **T5a** — BG + Cropper parity to v2 Preact functionality
2. **T4** — Phase B audit vs legacy v1
3. **T5b** — Phase A + Stitcher + Production Map parity to v1 legacy (LDs 471/515/523/524/525)
4. **Blocker #44** — Beat Gen tab library panel
5. **5 creature reference masters** — Luna/Benson/Ember/Bork/Bramble (Flux Kontext gen; ~$3)

**Exit criteria:**
- All 4 UI surfaces audited with findings filed as blockers OR fixed inline
- 5 masters registered in prod_assets (`role='master_still'`)

## §5 — Phase 4: Hardening + cleanup

Long list of small items. Each verified individually:
- T2 stale_lipsync flag (assign_image post-lipsync)
- Blocker #148 audio regen partition default
- C7-4 path_picker.html:794 absolute URL
- C7-5 production_server.py:8027 absolute URL
- C2-2 latest_preview_stitched_path stale cleanup
- C2-3 completed_mp4_path stale cleanup
- C5-2 delete PIL bypass dead code
- C4-10 migration_warnings one-time dedup
- Wave 3 raw-fetch migration (blockers #50/#51/#52/#53)
- Test coverage gaps (#156/#155/#78/#8)

**Exit criteria:** every item closed in Directus OR DEVIATION row.

## §6 — Phase 5: Long-tail / deferred

Tracked but not actioned this session:
- LD-722 TTS/Kling prompt separation (7-8h, ref_doc 224)
- CodeQL SHORTCUT closures (#168-173)
- 11 AI Review non-blocking nits (cosmetic)

**Exit criteria:** None (these are tracking items).

## §7 — Final cursor review

After all phases land, dispatch cursor-agent for an independent review pass:
- Check each phase's claimed fixes against actual code state
- Flag any deferred items that should have landed
- Iterate until cursor agrees nothing more to do

## §8 — Resumption protocol

Every phase writes `COORDINATOR_RESUMPTION_<PRE|POST>_PHASE_<N>_V1` row to prod_activity_log. A fresh session that picks up mid-build reads the latest row + git tags + this spec to resume.

If a phase halts (deviation, agent failure, vendor cap), write `HALT_PHASE_<N>_<reason>_V1` row with full context.

## §9 — Verification at every step

- After every edit: py_compile (Python) or `tsc --noEmit` (TS).
- After every commit: pytest full suite still green.
- After every phase: re-read all modified files; positive evidence captured.
- At final: cursor-agent independent review.

# S5.5c Terminal Handoff — v59 Storyboard Rewrite (Beat Generator UI)

**Authored by S5.5b (closeout) — 2026-05-03**
**Session prior:** S5.5b (combined-with-c attempt) shipped PART 1 clean; PART 2 deferred to this session per Rule 19 no-shortcuts and prompt escape-hatch. See `prod_activity_log` id=1475 (`S5_5B_COMPLETE_C_DEFERRED`) for full PART 1 gate summary.

---

## Why this is a separate session

The combined S5.5b + S5.5c session shipped PART 1 (b) clean — 5 LDs registered, all 18 verifiable gates green, 4 new endpoints LIVE, VideoSelector + pathappPatch auto-injection + EventSelector URL nav + ScopeBoundary `/api/event/current` integration shipped. **PART 2 (c) Phase A audit confirmed `0 of 6` beat_gen endpoints exist on disk** — the C_SPEC §3.3 assumption "UI port only" was wrong. PART 2 thus needs full backend build (6 endpoints incl. real GPT-image-2 integration) plus ~400-line BeatGeneratorTab.tsx — too large to honor "no shortcuts" + "all due diligence" within the combined session's remaining budget.

S5.5c gets its own focused session to do this properly.

---

## Pre-conditions verified from disk + Directus (2026-05-03 11:14-11:30 UTC)

| Artifact | Path / ID | State |
|---|---|---|
| State files | `Production/Event_*/production_state.json` | v2 partition shape unchanged from S5.5a2; Event_1 4 partitions; Event_2 2 partitions |
| Server | running (PID changes) | py_compile clean; LD-474 audit 0 violations |
| Bug audit table | `Production/docs/STORYBOARD_V59_S5_5_B_BUG_STATUS.md` | NEW — full status per bug |
| Bug 1 | RESOLVED-BY-PRIOR | S5.5a1 cache-clear + S5.5a2 nested cache (LD-475 + LD-478) |
| Bug 2 | FIXED in S5.5b | StitcherTab `/library` → `/jobs` + 12 `job_name`→`name` + 2nd fetch for slots |
| Bug 3 | FIXED in S5.5b | path_picker.html scopeVideoRole const + 3 magic POST bodies |
| Bug 4 | FIXED in S5.5b | `/api/event/current` endpoint + EventSelector URL nav + ScopeBoundary calls server |
| Bug 5 / 7 | WONTFIX_NON_EXISTENT | Renumbering artifacts |
| Bug 6 | MOSTLY_RESOLVED | stitch_editor_state.json file-backed; probe job survived restart |
| New endpoints | LIVE | GET /api/event/current, GET /api/video/list, POST /api/video/set_active, POST /api/video/create |
| VideoSelector UI | LIVE | `Production/tools/storyboard-v2/src/components/VideoSelector.tsx` ~180 lines, wired into App.tsx |
| pathappPatch auto-injection | LIVE | `client.ts` reads `activeVideoRole` signal; baseline scope_video_role in every mutating fetch |
| ScopeBoundary | UPDATED | calls `/api/event/current` first; seeds `activeVideoRole` from server's `state.active_video` |
| LDs S5.5b | 479 EVENT_CURRENT_ENDPOINT_V1, 480 VIDEO_LIST_ENDPOINT_V1, 481 VIDEO_SET_ACTIVE_ENDPOINT_V1 (HIGH), 482 VIDEO_CREATE_ENDPOINT_V1 (HIGH), 483 VIDEO_SELECTOR_UI_V1 (HIGH) | active |
| LD-474 PATCH | append | `state.active_video` is write-target of /api/video/set_active (display hint only; partition selection still body['scope_video_role'] only) |
| LD-474 audit script | bug fixed | `Production/scripts/ld474_audit_active_video.py` AST walker now handles `arguments` nodes |

---

## What S5.5c must do

### Phase 0 — Pre-flight (mandatory per Rule 19, LD-262)

1. Load `zero-error-qa` skill
2. Classify: ROUTINE Tier A for the TSX build (uses established patterns); Tier B if backend additions touch new architecture (they shouldn't — use existing scope guard / mutate_video_state / LD-460 pin patterns).
3. Spawn 1+1 advocate/counter (Tier A) or document Cursor v5 architectural-review exemption per LD-124 (same pattern S5.5a1/a2/b used).
4. Write `prod_preflight_reviews` row referencing #196 as predecessor; confirm via read-back.

### Phase A — Backend audit + extension (~45 min)

**Endpoint audit (already done in S5.5b prep — re-verify before edit):** ALL 6 endpoints from C_SPEC §3.3 are TO_ADD:

| Endpoint | Body | Purpose |
|---|---|---|
| POST /api/beat_gen/upload_ref | {scope_event_id, scope_video_role, beat_id, ref_type: "char"\|"bg", image_b64} | Save char/BG ref via registered_write.py; update `videos.<role>.beats[bid].refs.<type>` |
| POST /api/beat_gen/generate | {scope_event_id, scope_video_role, beat_id, count: 3} | Read refs + dialogue + stage_directions; build_gpt_still_prompt() (beat_generator.py:952); 3 gpt-image-2 calls (varied seed); register outputs; update `gen_options[]` |
| POST /api/beat_gen/select_option | {scope_event_id, scope_video_role, beat_id, option_id} | Update `selected_option_id`; mirror `image_path` for downstream |
| POST /api/beat_gen/add_beat | {scope_event_id, scope_video_role, after_beat_id?} | Insert empty beat; return new beat_id |
| POST /api/beat_gen/delete_beat | {scope_event_id, scope_video_role, beat_id, confirm: true} | Hard-delete from partition |
| POST /api/beat_gen/accept_all | {scope_event_id, scope_video_role} | Validate every beat selected; advance `pipeline_stage`; activity_log row |

**Pattern to follow (per S5.5a2 + S5.5b precedent):**
- Every handler: `_assert_event_scope(self._scope_body(body), allow_missing=True)` first
- Generation handler: pin via `_check_event_pin` per LD-460 (long-running async); pin tuple includes `pinned_video_role: body.get("scope_video_role", "intro")`
- Writes: `mutate_video_state(video_role, lambda partition: ...)` — NEVER raw `mutate_state` for partition-scoped data
- Asset registration: `registered_write.py` per LD-421 / LD-422; capture `iteration_notes` at production-time
- Stage-direction extraction: `extract_stage_directions(dialogue, max_n=2)` helper using `re.compile(r'\(([^)]{4,50})\)')`. Add to production_server.py near other beat-gen helpers.

**Phase A gates:**
- `python3 -m py_compile Production/tools/production_server.py` clean
- Server restart; `/api/health` returns 200
- All 6 endpoints respond with expected shapes (curl probes; on `/generate` use minimal body that 400s on missing inputs to avoid burning gpt-image-2 budget)

### Phase B — TSX tab build (~60 min)

**File:** `Production/tools/storyboard-v2/src/components/BeatGeneratorTab.tsx` (NEW, ~400-line target)

Pattern: same as existing tab files (`StoryboardTab.tsx`, `BgTab.tsx`, etc.). Reads from scope-keyed signal stores; mutates via `pathappPatch` (which now auto-injects `scope_video_role` thanks to S5.5b PART 1).

Layout per C_SPEC §3.1:
```
┌─ Beat Generator — [active video role badge] ─┐
│ Cost this session: $X.XX • This generation: $Y.YY │
├─ per beat ─────────────────────────────────┤
│ [dialogue textarea + stage-direction chips]│
│ [Char ref] [BG ref] [Generate 3 options]  │
│ [option 1] [option 2] [option 3]          │
└────────────────────────────────────────────┘
[+ Add Beat]                  [Accept All ▶]
```

**Components in build order (each commit-worthy):**
1. Beat card skeleton (dialogue textarea, header, delete)
2. Stage-direction chips (regex extraction on blur; chip × handler)
3. Per-beat ref upload slots (file picker → base64 → upload → thumbnail)
4. 3-option grid (Generate button, option thumbs, select handler)
5. Cost display (header strip + per-gen toast)
6. Add Beat / Delete Beat
7. Accept All flow (validation, confirm modal, locked-mode UI)

Wire into `app.tsx` ActivePane + `TabBar.tsx`.

### Phase C — Asset registration verification (~15 min)

Per LD-421 / LD-422:
- Every ref upload → `registered_write.py` → `prod_assets` row
- Every generated still → 3 `prod_assets` rows (one per option)
- `iteration_notes` captured at production-time
- `parent_asset_id` linking refs → generations
- Verify via `find_asset.py` query

### Phase D — Verification (8 gates per C_SPEC §4)

1. py_compile clean
2. `npm run build` (no TS errors)
3. Server restart; `/api/health` 200
4. All 6 endpoints respond with expected shape (curl probes)
5. Dev server smoke test (Kim hands-on): upload refs → type stage direction → generate 3 → select → add beat → delete → accept all
6. `find_asset.py` query returns the generated stills + refs
7. **REGRESSION GATE:** `python3 Production/scripts/ld474_audit_active_video.py` STILL PASSES (zero violations after backend additions). This is added to gate sweep per S5.5a2 closeout precedent.
8. `prod_activity_log` row `S5_5C_COMPLETE` written

### Phase E — LD registrations

- New LD `BEAT_GEN_TAB_V1` per C_SPEC §4 Phase E — locks tab contract: state shape additions (refs, gen_options, selected_option_id, stage_directions), 6 endpoint contracts, selection-and-acceptance flow.

---

## Critical constraints

1. **Use canonical prompt builder.** `build_gpt_still_prompt()` lives at `Production/tools/beat_generator.py:952`. Do NOT reimplement. (C_SPEC said L934-947; current line is L952 — drift, but same function name.)
2. **State shape additions are ADDITIVE.** 4 new sub-fields under `state.videos.<role>.beats[bid]`: `refs`, `gen_options`, `selected_option_id`, `stage_directions`. NO migration needed beyond S5.5a2's lift. Read paths must use `.get(...)` defensively (existing beats from S5.5a2 don't have these fields).
3. **Asset registration mandatory.** Every ref + generated still goes through `registered_write.py`. Direct ffmpeg/imageio/open() writes for these paths are FORBIDDEN per LD-421.
4. **LD-474 invariant unchanged.** Beat Generator handlers must NOT read `state.active_video` for partition selection; only `body['scope_video_role']` (which client auto-injects via pathappPatch as of S5.5b).
5. **Out of scope (cut per Kim 2026-05-02):**
   - GPT mode toggle
   - 9-stills-per-beat / 3×3 grid
   - FLUX Kontext path (LD-440 locks gpt-image-2 only)
   - Bulk operations
   - History/diff UI
   - Image editing within tab
   - Animation hooks ("Animate this" stays on watercolors)

---

## Verification gates (S5.5c must pass all 8)

1. `python3 -m py_compile Production/tools/production_server.py` — clean
2. `cd Production/tools/storyboard-v2 && npm run build` — no TS errors
3. Server restart; `/api/health` returns 200
4. All 6 `/api/beat_gen/*` endpoints respond with expected shape (curl probes)
5. Dev server loads BeatGeneratorTab; Kim hands-on smoke per C_SPEC §4 Phase D
6. `find_asset.py` query returns 3 generated stills + 2 refs
7. LD-474 audit script STILL PASSES (regression gate added per S5.5a2 closeout)
8. `prod_activity_log` row `S5_5C_COMPLETE` written
9. S5.5b/c COMBINED handoff to S6 prep written (`Production/docs/STORYBOARD_V59_S6_HANDOFF.md`)

---

## Reference

- **Spec:** `Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v1.md` (full executable spec)
- **Predecessor:** S5.5b activity_log id=1475 + preflight #196
- **LDs from S5.5b:** 479-483 (EVENT_CURRENT, VIDEO_LIST, VIDEO_SET_ACTIVE, VIDEO_CREATE, VIDEO_SELECTOR_UI)
- **LDs from S5.5a2:** 476-478 (STATE_MIGRATION_APPLIED, HANDLER_REFACTOR_VIDEOS_PARTITION, IMAGE_OVERRIDES_NESTED_BY_ROLE)
- **LDs from S5.5a1:** 473-475 (BG_VIDEO_PARTITION, VIDEO_ROLE_PER_REQUEST, IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD)
- **PATCHed LDs:** 456 (SCOPE_VALIDATION) + 460 (ASYNC_JOB_GENERATION_PIN) + 461 (SCOPE_BODY_HELPER) + 474 (S5.5b note about set_active write-target)
- **Audit script:** `Production/scripts/ld474_audit_active_video.py` (S5.5a2 build; S5.5b bug-fix on AST walker)
- **Bug status table:** `Production/docs/STORYBOARD_V59_S5_5_B_BUG_STATUS.md`
- **Cursor v4/v5 review reports:** UNFINDABLE on disk; B_SPEC_v1 (Desktop synthesis) is the authoritative repro source — used in S5.5b per preflight #196 deviation flag #1

---

## What S6 needs (the session AFTER c)

S6 = parallel-run module on Event_2 + cutover decision. Pre-conditions: PART 1 (S5.5b) shipped (✓) + S5.5c Beat Generator UI shipped + browser smoke tests confirm tabs work end-to-end.

After S5.5c lands cleanly, write `Production/docs/STORYBOARD_V59_S6_HANDOFF.md` per S5.5c §11 + the original combined session prompt's "End-of-session deliverables" template.

---

**End of S5.5c handoff stub.** Hand off to terminal Claude Code with: "Read this stub. Run Phase 0 preflight. Then execute Phases A–E in order. Report back when all 8 verification gates pass."

---

## 2026-05-03 update — S5.5d-cont closeout addendum

S5.5d (initial) and S5.5d-cont (continuation) shipped the v3 architecture revision per `STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` (`prod_reference_docs` id=190). Continuation preflight: id=198. Closeout activity_log: id=1480.

**Cumulative impact on this S5.5c handoff:**
- State shape advances from v2 (`videos.{intro, phase_a, phase_b, win}`) to v3 (`videos.{intro, resolution, standalone}`; `phase_a` + `phase_b` lifted to top-level).
- LDs 473 + 474 from S5.5a1 are now **superseded** by LD-487 `BG_VIDEO_PARTITION_V2` + LD-488 `VIDEO_ROLE_PER_REQUEST_V2` (S5.5d-cont).
- LDs 475 + 477 + 478 + 481 + 482 + 139 + 460 carry an **amendment note** narrowing scope to multi-beat partitions only.
- Migration script `Production/scripts/migrate_phase_partitions_to_top_level.py` was applied 2026-05-03 with snapshots at `Production/Event_<N>/.backups/state/20260503T191817Z_pre_phase_revision.json`.
- v59 client tab order is now `[Beat Generator, Cropper, Storyboard, Phase B, Phase A, Stitcher, Map]`.
- See `Production/docs/STORYBOARD_V59_S6_HANDOFF.md` for the S6 entry point + open items.

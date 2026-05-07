# Storyboard v59 — S5.5c+e Browser-Smoke Bugfix Spec v1

**Date:** 2026-05-03
**Classification:** EXECUTION SPEC — bugfix bundle for issues caught by Kim's hands-on browser smoke after S5.5c+e shipped
**Predecessor:** S5.5c+e (commits `bc12a4d` + `9efaabd`; 31/31 server-side gates green)
**Why this exists:** Server-side gates are necessary but not sufficient (LL-15 from v3 lessons-learned). Browser smoke surfaced 5 distinct integration bugs + 1 feature gap. This spec covers all of them in one bounded session.
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Task

Fix 5 root causes for 7 user-visible symptoms surfaced in browser smoke 2026-05-03 + add the missing "+ New Event" UI flow Kim called out as part of the architectural review.

NONE of these are architectural revisions. They are integration completions: features the spec said were done but were only ~70% wired.

## §2 Governing Decisions

### LDs respected

| LD | Reason |
|---|---|
| LD-456 / LD-460 / LD-461 | Standard scope + pin + body helper hygiene |
| LD-184 | Audio preview always-fresh from disk (Bug R1 must not regress this) |
| LD-421 / LD-422 | Asset registration via `registered_write.py` |
| LD-486 | Milestone independence (Bug R1 milestone-load fix must respect) |
| LD-494 | TargetVideoSelector visibility per scope |
| `BEAT_GEN_3_OPTIONS_NOT_GRID_V1` (S5.5c) | UI is 1×3 NOT 3×3 — bugfix must not change this |
| `UI_PRIMITIVES_SHARED_V1` (S5.5c) | Use Modal/Toast/Spinner/AssetTile primitives for all new UI |
| `DRAG_DROP_HELPER_V1` (S5.5c) | The dragdrop.ts payload union exists; this bugfix wires it into the components that should have used it |
| `BEAT_LIFECYCLE_STATE_MACHINE_V1` (S5.5e) | Bug R3 fix must not break the state machine |

### NEW LDs this spec writes (2)

| Key | Severity | Purpose |
|---|---|---|
| `S5_5CE_BROWSER_SMOKE_BUGFIX_V1` | MEDIUM | Records the 5 integration bugs caught by browser smoke + their fixes. Captures the lesson: "scaffolded with `// future` comments" is not the same as "shipped." |
| `NEW_EVENT_CREATION_UI_V1` | MEDIUM | "+ New Event" UI flow analogous to "+ New Milestone": modal with regex-validated `event_id`, server endpoint already exists at `_handle_event_create` (verify in Phase A). |

## §3 Approach

### Diagnosis confirmed via direct code inspection 2026-05-03

| Root cause | Evidence | Fix scope |
|---|---|---|
| **R1: Scope-change doesn't trigger UI re-fetch** | `BgTab.tsx` has 3 `useEffect` calls; dependency arrays must NOT include `activeTargetVideo` / `activeProjectType` / `activeMilestoneId` signals (or signals aren't read inside via `.value` correctly). Same pattern in `StoryboardTab.tsx` likely. Plus `+ New Milestone` Create button doesn't auto-call `/api/milestones/load` — milestone is created in Directus + on disk but UI stays in old scope. | BgTab + StoryboardTab effect dependencies; ProjectSelector post-Create flow. |
| **R2: Drag-drop never wired** | `LibraryPanel.tsx:6` literal comment: `"Tiles are also draggable so future drop"` — flagged as future, never finished. Zero `draggable` attribs in component code, zero `onDragStart` handlers. Also zero `onDrop` handlers in BgTab beat option slots / char ref / BG ref / Cropper. The `dragdrop.ts` helper exists from S5.5c but has no callers. | LibraryPanel tile attrs + drag handlers; drop targets in BgTab + CropperModal; use existing `dragdrop.ts` payload union. |
| **R3: bg_accept_option 400** | Server `_handle_bg_accept_option` expects body `{beat_id, option_key}`. Client likely sending `{beat_id, option_index}` (numeric) or omitting `option_key`. | Audit BgTab call site; fix body shape. |
| **R4: populate_prod_modules wrong fields** | Production Map shows `M7-M59 = TBD / intro` for all. Either parser regex didn't match GAMEPLAY_SCOPE_v3.md format, OR doc structure has creature_name / video_role in different fields than parser expected. | Re-read GAMEPLAY_SCOPE_v3.md actual format; fix parser; PATCH all 53 rows with correct creature_name + video_role per arc/module. |
| **R5: Library thumbnails too big** | LibraryPanel CSS sizing makes 53 tiles need scrolling to see all. | CSS sizing fix; aim ~80px thumbnails. |

### NEW: + New Event UI flow

Server-side endpoint check in Phase A. If `_handle_event_create` exists (likely, given the v3 work), wire UI same pattern as + New Milestone:
- ProjectSelector dropdown "+ New Event" entry triggers Modal
- Modal with `event_id` regex `^[A-Z][A-Za-z0-9_]{2,63}$` (events use Capital-leading by convention vs milestones lowercase)
- Display label optional
- Create → POST `/api/event/create` (or whatever endpoint name) → on success, auto-call `/api/event/load` to switch scope into the new event (this also fixes R1 pattern for events, mirroring milestone fix)

If endpoint does NOT exist: scope decision needed. Default: this session adds `_handle_event_create` (~30 lines server) + UI; surface to Kim if scope expands beyond ~30 lines server.

## §4 Implementation Phases

### Phase A — Pre-flight + diagnosis confirmation

**A1.** Read this spec + master overview + S5.5c v2 spec + S5.5e v1 spec.

**A2.** `prod_preflight_reviews` row referencing S5.5c+e preflight #199 as predecessor.

**A3.** Confirm bug reproduction: open v59 client, reproduce R1 (switch video → stale beats), R2 (drag library tile → no drop), R3 (click option radio → Lock failed 400 toast). Don't fix yet; just capture exact reproduction.

**A4.** Inspect:
- `BgTab.tsx` lines 126, 152, 477 — useEffect dependencies vs scope signals
- `LibraryPanel.tsx` — confirm zero draggable + zero onDragStart
- BgTab `bg_accept_option` call site — capture exact body shape sent vs server expectation `{beat_id, option_key}`
- `GAMEPLAY_SCOPE_v3.md` — actual structure (markdown table? YAML? regex required to extract creature_name + video_role per module)

**A5.** Verify `_handle_event_create` server endpoint existence. Grep `production_server.py` for `event/create` route and handler. If missing, document scope expansion to ~30 lines server.

### Phase B — R1 fix: scope-change re-fetch

**B1.** `BgTab.tsx` — add `activeTargetVideo.value`, `activeProjectType.value`, `activeMilestoneId.value` reads inside the relevant `useEffect` body so signals subscribe; verify dependency array includes them OR uses Preact signals `effect()` pattern.

**B2.** `StoryboardTab.tsx` — same audit + fix.

**B3.** `ProjectSelector.tsx` — after `+ New Milestone` Create succeeds: auto-call `/api/milestones/load` with the new id; await success; UI scope updates.

**B4.** Verification: switch Project to Event_2; switch Video to resolution; beats list clears (Event_2 resolution is empty per state). Switch back to Event_1 intro; beats list shows Event_1's 17 intro beats. Create new milestone; UI auto-loads it; scope chip + Video dropdown reflect milestone scope.

### Phase C — R2 fix: drag-drop wiring

**C1.** `LibraryPanel.tsx` — extract tile rendering into `<AssetTile>` (S5.5c primitive); set `draggable={true}` + `onDragStart={(e) => setDragData(e, {kind: 'lib-image', lib_key: it.key, tier: it.tier})}` per dragdrop.ts.

**C2.** `BgTab.tsx` beat option slots (3 slots per beat) — add `onDragOver={(e) => e.preventDefault()}` + `onDrop={(e) => { const payload = getDragData(e); if (payload?.kind === 'lib-image') {/* call bg_accept_lib_image */} }}`.

**C3.** `BgTab.tsx` char ref + BG ref slots — same drop handler pattern; calls bg_update_beat with `{char_ref_key}` or `{bg_ref_key}`.

**C4.** `CropperModal.tsx` — add drop target on the canvas area; on drop, set source image from library URL.

**C5.** Visual cue: drop targets get `dragover` CSS state (border highlight) when valid payload hovers.

**C6.** Verification: drag library tile → drop on beat option slot → option set with library image. Drag → drop on char ref → char ref populated. Drag → drop on Cropper canvas → image loads.

### Phase D — R3 fix: bg_accept_option 400

**D1.** Diagnose Phase A4 finding: client sends `{beat_id, option_index: <number>}`; server expects `{beat_id, option_key: <string>}`. Fix client to send option_key (the option's actual key string from `phase_1.options[i].key` or similar).

**D2.** If option_key isn't present in client option object, query GET on the beat to find the canonical option keys, OR fix client option representation to carry `key` field.

**D3.** Test: click radio on each option in a beat → POST returns 200 → option marked selected → no Lock failed toast.

### Phase E — R4 fix: populate_prod_modules re-run

**E1.** Re-read `GAMEPLAY_SCOPE_v3.md` actual structure. Document the format Phase A4 found.

**E2.** Update `populate_prod_modules_from_gameplay_scope.py` parser to extract correct fields per module:
- `m_number` (already correct)
- `colloquial_name` (creature name) — needs fixing
- `arc_id` — needs fixing
- `video_role` — current "intro" placeholder; needs real per-module value (probably most are "intro" but some are different — check the doc)
- `stone_id` — should be present per module if doc has it

**E3.** Run `--validate` against current Directus state; expected: M1-M6 unchanged (already correct); M7-M59 all have TBD names + intro role.

**E4.** Run `--apply` — script PATCHes M7-M59 with correct field values.

**E5.** Read-back verify Production Map shows real creature names (no TBD); video_role per module reflects the doc.

### Phase F — R5 fix: library thumbnail sizing

**F1.** `src/index.css` (or LibraryPanel-scoped CSS) — set asset tile width ~80px (configurable via CSS variable `--ui-library-tile-size`).

**F2.** Verify all ~50 tiles fit visible in the right rail without scroll on a 1280px-wide viewport.

### Phase G — + New Event UI

**G1.** If `_handle_event_create` exists in `production_server.py`: wire UI only.

**G2.** If missing: add `_handle_event_create` server handler (~30 lines):
- POST `/api/event/create` with body `{event_id, event_label?}`
- Validate `event_id` regex (capital-leading per convention)
- Reserved word check (cannot start with `Test_`, `_*`, `Tmp_`)
- Create `Production/Event_<id>/` directory + `production_state.json` scaffold matching v3 shape
- Wraps with `@with_pin_and_drain('event_create', track_sync=False)`
- Returns `{ok, event_id, event_dir}` or 409 on collision

**G3.** Client: `ProjectSelector.tsx` "+ New Event" entry → Modal (S5.5c primitive) with regex-validated event_id input + label input.

**G4.** On Create success: auto-call `/api/event/load` with the new event_id.

**G5.** Verify: + New Event opens modal → enter `Event_3` → Create → server creates dir + state.json → UI loads new event scope → empty intro/resolution partitions visible in Beat Generator + Storyboard.

### Phase H — Verification (12 gates)

**H1.** `npm run build` clean.
**H2.** Server `/api/health` 200; PID start time AFTER any server edits (Rule 29).
**H3.** **R1 probe:** switch Video from intro to resolution on Event_2 → beats list clears (resolution is empty). Switch back to Event_1 intro → 17 beats reappear.
**H4.** **R1 probe:** click + New Milestone → enter `valid_test_h_smoke` → Create → UI auto-loads milestone scope. Scope chip shows milestone id; Video dropdown hides; Phase A/B tabs disabled.
**H5.** **R2 probe:** drag library image tile → drop on beat option slot → POST `bg_accept_lib_image` → option set.
**H6.** **R2 probe:** drag library image tile → drop on char ref slot → ref set.
**H7.** **R2 probe:** open Cropper → drag library tile onto canvas → image loads as source.
**H8.** **R3 probe:** click radio on a beat option → POST `bg_accept_option` returns 200 → no Lock failed toast.
**H9.** **R4 probe:** Production Map renders M7-M59 with REAL creature names (NOT TBD); video_role per module reflects GAMEPLAY_SCOPE_v3.md.
**H10.** **R5 probe:** library tiles ≤ 80px wide; ~50 tiles visible without scroll on 1280px viewport.
**H11.** **+ New Event probe:** + New Event modal opens; reserved-word `Test_X` rejected; valid `Event_3` accepted; Create → server creates Event_3/ + state.json; UI loads new scope; intro + resolution partitions empty.
**H12.** Playwright smoke (NEW per Cursor v8 + recent learning): write `e2e/s5_5ce_bugfix_smoke.spec.ts` covering H3, H5, H8, H9, H11. `npx playwright test e2e/s5_5ce_bugfix_smoke.spec.ts` exits 0.

### Phase I — LD writes

**I1.** Write 2 NEW LDs: `S5_5CE_BROWSER_SMOKE_BUGFIX_V1`, `NEW_EVENT_CREATION_UI_V1`.

### Phase J — Closeout

**J1.** `prod_activity_log` row `S5_5CE_BUGFIX_COMPLETE` with full 12-gate summary + the 5 root-cause diagnosis (R1-R5).

**J2.** Update master overview status table with bugfix-shipped note.

**J3.** Tail-end verifier subagent — focused on regression check (none of the originally-passing 31 gates from S5.5c+e are now broken).

**J4.** Git commit: `S5.5c+e bugfix — scope refresh + drag-drop + accept-option + populate fields + thumbnails + New Event UI (12 gates green)`.

## §5 Files Created / Modified

### Created
- `Production/tools/storyboard-v2/e2e/s5_5ce_bugfix_smoke.spec.ts` (Playwright tests for H12)

### Modified
- `Production/tools/storyboard-v2/src/components/LibraryPanel.tsx` (drag handlers + AssetTile use)
- `Production/tools/storyboard-v2/src/components/BgTab.tsx` (effect deps + drop handlers + bg_accept_option body fix)
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` (effect deps)
- `Production/tools/storyboard-v2/src/components/CropperModal.tsx` (drop target + source from library)
- `Production/tools/storyboard-v2/src/components/ProjectSelector.tsx` (auto-load milestone after Create + + New Event entry)
- `Production/tools/storyboard-v2/src/components/ProjectSelector.tsx` OR new modal component for + New Event
- `Production/tools/storyboard-v2/src/index.css` OR LibraryPanel CSS (thumbnail size)
- `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (parser fix)
- `Production/tools/production_server.py` (only if `_handle_event_create` doesn't exist; ~30 lines new)

### Modified (Directus)
- `prod_modules`: PATCH all 53 rows (M7-M59) with correct fields

## §6 Directus Writes

- `prod_locked_decisions`: 2 NEW LDs
- `prod_modules`: 53 PATCHes
- `prod_activity_log`: phase rows + COMPLETE
- `prod_preflight_reviews`: 1 row at session start

## §7 Error Cases

| Failure | Handling |
|---|---|
| GAMEPLAY_SCOPE_v3.md still doesn't parse cleanly | Surface to Kim; defer R4 fix to a follow-up; ship R1/R2/R3/R5/+NewEvent in this session |
| `_handle_event_create` doesn't exist + server addition exceeds 50 lines | Surface to Kim before adding server work; defer + New Event to a separate session if scope balloons |
| R1 fix surfaces deeper signal-architecture issue | STOP; this would be the architectural smell I described to Kim. Surface for rethink. |
| R2 drag-drop breaks Safari (different dataTransfer behavior) | Document; require Chromium for now; add to S5.5f gate set |
| R3 fix reveals option_key isn't in client option object | Fix client option representation; surface as scope add |
| Playwright H12 can't run because dist isn't served | Use the existing scaffold's pattern (likely Playwright spins its own dev server per `playwright.config.ts`) |

## §8 Verification

12 gates green + 2 LDs + 53 prod_modules PATCHes + Playwright passing + browser smoke 7 steps green per `STORYBOARD_V59_S5_5_CE_HANDOFF.md` Notes-for-Kim list.

## §9 Rollback

- Client fixes: `git checkout -- src/components/`
- Populate script: re-run with original (broken) version OR PATCH all 53 rows back to TBD/intro
- Server endpoint (if added): `git checkout -- production_server.py`; PATCH any created Event_3/ dir to /tmp or delete
- LDs: PATCH to `status='superseded'`

## §10 Out of Scope (defer)

- Production Map multi-event mapping (deferred to S5.5g per spec)
- Voice profile UI (S6)
- Phase A/B feature parity (S5.5f)
- Stitcher SFX/transitions/trims (S5.5g)
- Drag-drop on Safari (Chromium-only this session)
- "+ New Module" UI (the architectural-question concept) — events are the granularity per V1 scope; new-event covers the use case

## §11 Dependencies

**On v3:** state shape, scope signals, pathappPatch, Modal/Toast/Spinner/AssetTile/dragdrop primitives.
**On S5.5c+e:** all of it. This is the bugfix.

## §12 Notes for the Executing Session

- **PRIORITY: R1 first.** All other bugs are easier to test once scope-refresh works. R3 in particular may LOOK fixed in a stale-scope view — re-test after R1 ships.
- **The "future drop" comment in LibraryPanel.tsx:6** is the smoking gun for R2. Spec said drag-drop was wired; comment in committed code says "future." That's the integration gap — features marked done in spec that are only scaffolded in code.
- **Don't expand scope.** Cursor v8 reviewed S5.5c+e specs for completeness; if a deeper bug surfaces beyond the 5 root causes, surface to Kim. Don't quietly add fix #6.
- **GAMEPLAY_SCOPE_v3.md** is the source of truth for V1 scope per LD-357. The parser fix is "match the format the doc has," NOT "decide what the format should be."
- **+ New Event UI** uses the same Modal primitive as + New Milestone for consistency. Different regex (capital-leading) + different reserved words.
- **Playwright at H12** is the regression coverage going forward. Even if it takes an extra hour, write it — this is the lesson from today.
- Per Rule 29: server staleness check before any "test it now" if production_server.py modified.
- Per Rule 35: every Directus write via try_post_or_queue with read-back.
- Per Rule 19: no shortcuts. Don't ship "R3 fix" without testing all 5 root cause fixes don't conflict with each other.

## §13 Cursor Review Checklist

Send Cursor this spec + the 5 root-cause table + the following questions:

1. R1 (scope-refresh): is the fix `useEffect` dependency arrays, OR Preact-signals `effect()` pattern, OR explicit signal-subscription hooks? Verify via `BgTab.tsx:126,152,477` how signals are currently consumed; identify the cleanest pattern.

2. R1 milestone-load auto-call: should this happen in ProjectSelector after Create returns, OR in the milestones_load endpoint when create+load is fused into one API call? Two options have different ergonomics.

3. R2 drag-drop on AssetTile: is the existing AssetTile component ready to accept drag handlers via props, or does it need API extension?

4. R2 drop target visual cue: should we add a `[draghover]` CSS state OR use inline JS to add a class? Strict-mode TS implications?

5. R3 option_key lookup: where does the client get the canonical option_key from? `phase_1.options[i].key`? Is that field always present, or sometimes missing?

6. R4 GAMEPLAY_SCOPE_v3.md format: please READ the actual file and report its structure (markdown tables, YAML frontmatter, regex pattern). Spec assumes per-module fields are extractable; verify before terminal execution.

7. + New Event UI: does `_handle_event_create` exist in production_server.py? If yes, what's its body shape? If no, is the ~30-line addition the right scope, or is there a cleaner path?

8. Playwright dev-server: does `playwright.config.ts` already start its own dev server, or does it expect localhost:5111 + the file:// dist? Either works; just confirm what's there.

9. Are 12 gates enough? Should we add a regression gate that the original 31 S5.5c+e gates still pass after these fixes?

10. Architectural pre-flight question: is there ANY pattern across R1-R5 that suggests a deeper architectural smell (e.g., "scaffolded with future comments, never finished" might be a culture issue, not just a bug)? If yes, what would the fix-the-pattern action be?

Append findings as §14 before terminal execution.

---

**End of S5.5c+e bugfix spec v1.**

Designed for Cursor review BEFORE terminal execution per Kim's 2026-05-03 directive to avoid feature-then-bugfix-spiral risk. Cursor v9 review is the gate before terminal handoff is written.

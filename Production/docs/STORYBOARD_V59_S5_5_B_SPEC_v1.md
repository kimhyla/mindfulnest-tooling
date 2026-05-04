# Storyboard v59 — Sub-Session S5.5b Spec v1

**Date authored:** 2026-05-03
**Author:** Desktop Claude (parallel to S5.5a2 execution)
**Classification:** EXECUTION SPEC — bug-fix sweep + 1 endpoint + 1 UI component
**NOT tech-spec-skill scope:** Cursor v5 already debated root causes; this
session is execution against known root causes, not architectural research

## §1 Task

Close the bug list from Session 5 hands-on testing + add the two missing
pieces that Cursor v5 + my Session 5 review identified as required:

**Bug fixes (Session 5 hands-on test):**
- **Bug 1** — storyboard image scrambling on event swap
- **Bug 2** — stitcher persistence/shape mismatch
- **Bug 3** — magic POST scope_video_role plumbing
- **Bug 4** — EventSelector page reload doesn't propagate to ScopeBoundary
- **Bug 6** — stitch job persistence

**New components:**
- **VideoSelector UI** — global dropdown to switch between
  `videos.{intro|phase_a|phase_b|win}` partitions (depends on S5.5a2
  partition being live)
- **GET /api/event/current** — endpoint returning currently-active event
  (Cursor v5 Bug 4 fix)

**CRITICAL FIRST STEP:** Several of these bugs may already be resolved by
S5.5a1 and/or S5.5a2. Phase A is a bug-status audit — verify each bug
against current behavior BEFORE writing any patch. Apply fixes only to
bugs still reproducing.

## §2 Architecture (already locked — citing, not deciding)

| Decision | Source | Notes |
|---|---|---|
| Single mutation channel | spec v3.1 | All writes via `pathappPatch(scope, field, value)` |
| Scope token includes `video_role` | LD-474 (S5.5a2) | All mutating handlers receive `body['scope_video_role']` |
| `_image_overrides` + `_pending_override_keys` cleared on event load | LD-475 (S5.5a1) | Bug 1 (image scrambling on event swap) likely tied to this — verify in Phase A |
| Magic POSTs carry scope_video_role | LD-468/469/470 (S5.5a2 Phase C) | Bug 3 likely resolved by a2 — verify in Phase A |
| State partition by video_role | LD-473 (S5.5a1) + a2 application | VideoSelector reads/writes partition selection |
| Per-event isolation lock | LD-465 | Holds during partition swap |
| State shape v2 | LD-473 + a2 migration | `state.videos.<role>.beats[...]` etc. |

## §3 Bug-by-Bug Detail

### Bug 1 — Storyboard image scrambling on event swap

**Symptom (Session 5 hands-on):** Switching from Event_1 → Event_2 → Event_1
left storyboard tab showing Event_2's images on Event_1's beats (or
similar cross-event contamination).

**Suspected root cause (a1 era):** `_image_overrides` cache held stale
entries from prior event after swap.

**Likely current state:** S5.5a1 added cache-clear in `_handle_event_load`
(LD-475). a2 extends this for partition-aware loads. **Verify in Phase A:**
load Event_1 → swap to Event_2 → swap back. If images still scramble,
the cache-clear is firing but something downstream is repopulating from
stale source. Investigate ScopeBoundary, signal store, and any
Preact effect that might cache image URLs across event swaps.

**Fix path (if not resolved):**
- Likely client-side: scope-keyed signal stores must be re-allocated on
  event swap, not refreshed in place
- Per spec v3.1: switching events allocates fresh stores
- Audit `Production/tools/storyboard-v2/src/state/` for any store that
  doesn't re-allocate on `event_id` change

### Bug 2 — Stitcher persistence/shape mismatch

**Symptom (Session 5):** Stitcher tab UI ships but jobs don't persist
across page reload OR Phase A/B output sent to stitcher doesn't appear.

**Cursor v5 finding:** "4-slot code IS in StitcherTab.tsx (lines 215-282) —
issue is job persistence/shape, not missing UI."

**Likely current state:** Either StitchEditorState job naming inconsistent
OR job shape on disk doesn't match what tab reads.

**Fix path:**
1. Read `StitcherTab.tsx` lines 215-282 — confirm the 4-slot code
2. Read `production_server.py` stitcher endpoints — confirm job storage
   path + shape
3. Diff: what does the tab READ vs what does the server WRITE?
4. Fix the mismatch at whichever side is wrong (preference: fix the one
   that drifted from the original spec, not the one matching the spec)
5. If both drifted, surface to Kim — don't guess which is canonical

### Bug 3 — Magic POST scope_video_role plumbing

**Symptom (Session 5):** Magic-still / magic-video / watercolor-animate
POSTs from path_picker.html return 400 "VIDEO_ROLE_INVALID" or write to
the wrong partition after event swap.

**Likely current state:** S5.5a2 Phase C extends magic POSTs (LD-468/469/470)
to carry `scope_video_role`. **Verify in Phase A:** trigger one magic
generation; confirm POST body includes `scope_video_role`; confirm
server-side validation passes; confirm output written to correct
partition.

**Fix path (if not resolved):**
- If POST missing `scope_video_role`: patch path_picker.html to include
  it (read from URL param or window.__MN_VIDEO_ROLE__)
- If server-side validation rejects: confirm `_assert_event_scope`
  changes from a2 propagated to magic handlers

### Bug 4 — EventSelector page reload doesn't propagate to ScopeBoundary

**Symptom (Session 5):** EventSelector dropdown changes event → page reloads
→ ScopeBoundary on boot reads stale event from URL param / data-attr /
window global → user sees old event's data despite the dropdown showing
new event.

**Cursor v5 root cause (verbatim from review):** EventSelector reloads
page after `/api/event/load` but ScopeBoundary on boot only reads
`?event=` URL param, `data-event-id` attr, or `__MN_EVENT_ID__` —
none of which are updated by EventSelector.

**Cursor v5 fix options:**
- (A) Add `GET /api/event/current` endpoint; ScopeBoundary calls it on
  boot; server returns currently-active event
- (B) EventSelector navigates with `?event=<id>` after load (no separate
  endpoint needed; URL param is the source of truth)

**Recommended fix: BOTH.**
- Add `GET /api/event/current` (cleaner semantics, allows other components
  to query active event without parsing URL)
- ALSO have EventSelector navigate with `?event=<id>` after load (so
  bookmarks + page refreshes work)

**Endpoint contract (`GET /api/event/current`):**
- No body
- Returns `{event_id, video_role, partition_keys: [...]}` 200
- Returns `{event_id: null}` 200 if no event loaded (rather than 404 —
  null is a valid state on first boot)

### Bug 6 — Stitch job persistence

**Symptom (Session 5):** Stitch jobs initiated in one session don't appear
in next session's stitcher tab even though the underlying file exists
on disk.

**Likely root cause:** Job metadata stored in memory, not in
`prod_activity_log` or a job tracker collection.

**Fix path:**
1. Audit how stitch jobs are tracked currently — likely in a Python
   dict on the running server
2. Add persistence: on every stitch job state change, write to
   `prod_activity_log` with action=`STITCH_JOB_<state>` and
   `details` JSON containing job_id, source_paths, output_path,
   status
3. On stitcher tab load: query `prod_activity_log` for recent
   `STITCH_JOB_*` rows for the active event; reconstruct UI state
4. Optional: add `prod_stitch_jobs` collection if Kim wants
   first-class job tracking (DEFER — overkill for V1; activity_log
   is sufficient)

## §4 New Component: VideoSelector

### §4.1 Purpose

Global UI control letting Kim choose which video role
(`intro | phase_a | phase_b | win`) the storyboard tabs operate on.
Required because S5.5a2's partition lift means each event now contains
4 distinct video assets rather than 1 flat state.

### §4.2 Placement

- **Header bar of v59 app**, immediately right of EventSelector
- Same dropdown pattern as EventSelector (consistency)
- Visible on every tab (not tab-specific)

### §4.3 Behavior

**On mount:**
- Read currently-active video role from `state.active_video` (read-only
  display hint per LD-474)
- If `state.active_video` unset, default to `intro`

**On change:**
- POST to a new endpoint `POST /api/video/set_active` with body
  `{scope, video_role}`
- Server updates `state.active_video` (display-only field)
- Client navigates with `?event=<id>&video=<role>` (URL is source of
  truth, matching EventSelector pattern)
- Page reload OR signal-driven re-render (decide based on current
  EventSelector pattern — match it)

**Tab integration:**
- Storyboard, Phase A, Phase B, Stitcher tabs all read
  `videos.<active_role>` partition
- Beat Generator tab (S5.5c) reads same
- VideoSelector emits a signal change that all tabs subscribe to
  (or page reload if matching EventSelector — pick one approach,
  document why)

**Empty partitions:**
- If user selects `videos.win` and that partition is empty, tabs show
  "no data for this video role yet — generate intro first" or similar
- Do NOT auto-create empty partitions; partitions populate when user
  takes action that writes to them

### §4.4 Backend endpoints

**New:** `POST /api/video/set_active`
- Body: `{scope: {event_id, beat_id?, version}, video_role}`
- Validates `video_role` via `state.validate_video_role()` (a1 helper)
- Updates `state.active_video` via `state.mutate_state(...)`
  (top-level field, not partition-specific)
- Returns `{ok: true, active_video: <role>}` 200
- Returns `{ok: false, error: "VIDEO_ROLE_INVALID", valid: [...]}`
  400 on bad role

**New:** `GET /api/event/current` (also serves Bug 4 fix)
- See §3 Bug 4 for contract

## §5 Implementation Phases

### Phase A — Bug-status audit (~30 min) [BLOCKING for B/C/D]

Per bug:
1. Reproduce against current (post-a2) server
2. Mark as: RESOLVED / STILL REPRODUCES / PARTIAL / CANNOT REPRODUCE
3. For STILL REPRODUCES: confirm Cursor v5 / spec root cause still
   matches; flag if not
4. For RESOLVED: log to `prod_activity_log` action=`BUG_RESOLVED_BY_PRIOR_SESSION`
5. Output: bug-status table, written to
   `Production/docs/STORYBOARD_V59_S5_5_B_BUG_STATUS.md`

**Hard gate:** do not proceed to Phase B until status table is
written and Kim's expected-failures (the 5 bugs) have been classified.

### Phase B — Bug fixes (~60 min, scoped to bugs still reproducing)

For each bug marked STILL REPRODUCES in Phase A:
1. Apply fix per §3 fix-path guidance
2. Verify symptom resolved
3. Add Playwright test (or extend existing) covering the regression
4. Commit message format: `fix(s5_5b): Bug N — <one-line summary>`

For each bug marked PARTIAL:
1. Investigate residual; same flow as STILL REPRODUCES

### Phase C — Endpoints + VideoSelector (~45 min)

1. Add `GET /api/event/current` per §3 Bug 4 contract
2. Add `POST /api/video/set_active` per §4.4
3. Build VideoSelector TSX component per §4
4. Wire into header bar
5. Verify tab integration: switch video role → all tabs reflect change

### Phase D — Verification (~15 min)

Per gate:
1. ✅ Bug status table written + reviewed
2. ✅ All STILL REPRODUCES bugs marked RESOLVED in
   `prod_activity_log`
3. ✅ `python3 -m py_compile Production/tools/production_server.py`
4. ✅ `cd Production/tools/storyboard-v2 && npm run build` clean
5. ✅ Server restart; `/api/health` 200
6. ✅ `GET /api/event/current` returns expected shape (200 with
   loaded event; 200 with `{event_id: null}` on cold boot)
7. ✅ `POST /api/video/set_active` accepts valid roles + 400s on
   invalid
8. ✅ Smoke test: load Event_1 → switch to phase_a video role →
   tabs show phase_a partition data → switch to phase_b → tabs
   update → switch event to Event_2 → state preserved per-event
9. ✅ Bug 1 specifically retested: Event_1 → Event_2 → Event_1
   storyboard images intact, no cross-event contamination
10. ✅ Bug 4 specifically retested: EventSelector change → page
    reload → ScopeBoundary picks up new event correctly
11. ✅ Stitch job persistence: initiate stitch job → restart server
    → tab on reload shows the job in correct state (Bug 6)
12. ✅ `prod_activity_log` row `S5_5B_COMPLETE` with full gate
    summary
13. ✅ S5.5c handoff stub written (or if S5.5c executes in same
    session, S6 prep handoff)

### Phase E — LD registrations

1. New LD `VIDEO_SELECTOR_V1` — locks the VideoSelector contract:
   header placement, URL param convention, server endpoint contracts
2. New LD `EVENT_CURRENT_ENDPOINT_V1` — locks `GET /api/event/current`
   contract
3. PATCH LD-474 (VIDEO_ROLE_PER_REQUEST_V1) — append note about
   `state.active_video` being write-target of `/api/video/set_active`
   (display hint, not partition selector)
4. Per-bug PATCHes if any prior LDs reference the buggy behavior

## §6 Files Created / Modified

**Created:**
- `Production/docs/STORYBOARD_V59_S5_5_B_BUG_STATUS.md` (Phase A output)
- `Production/tools/storyboard-v2/src/components/VideoSelector.tsx`

**Modified:**
- `Production/tools/production_server.py` — add `GET /api/event/current`
  + `POST /api/video/set_active`; bug fixes per Phase A audit
- `Production/tools/storyboard-v2/src/components/Header.tsx` (or
  wherever EventSelector lives) — add VideoSelector
- `Production/tools/storyboard-v2/src/state/` — fix per-event store
  re-allocation if Bug 1 still reproduces
- `Production/tools/storyboard-v2/src/tabs/StitcherTab.tsx` — fix
  per Bug 2 if still reproduces
- `Production/tools/path_picker.html` — fix scope_video_role plumbing
  per Bug 3 if still reproduces
- Any other files identified by Phase A audit

## §7 Directus Writes Required

**`prod_locked_decisions` (via `try_post_or_queue`):**
- 2 new: `VIDEO_SELECTOR_V1` + `EVENT_CURRENT_ENDPOINT_V1`
- 1+ PATCHes: LD-474 (VIDEO_ROLE_PER_REQUEST_V1) + any bug-related LDs

**`prod_activity_log` (via `try_post_or_queue`):**
- Phase A: 1 row per bug with action=`BUG_AUDIT_<RESOLVED|REPRODUCES|PARTIAL>`
- Phase B: 1 row per fix with action=`BUG_FIX_<bug_id>` + `details`
  containing root cause + fix description
- Phase D pass: `S5_5B_COMPLETE` with full gate summary

**`prod_preflight_reviews`:**
- 1 row at session start per Rule 19

## §8 Error Cases and Handling

| Failure | Handling |
|---|---|
| Bug status audit shows Cursor v5 root cause no longer applies | Surface to Kim; do NOT silently substitute another fix path |
| Bug fix breaks unrelated test | Revert; investigate; do not patch on top of patch |
| VideoSelector POST fails on every role | Likely a2's `validate_video_role` is broken — STOP, do not patch around it |
| `GET /api/event/current` returns null when event IS loaded | Server-side state inconsistency — STOP, surface to Kim |
| StateManager `mutate_state` deadlock during VideoSelector change | event_load_lock contention — investigate before patching |

**No silent failures.** Per Rule 19.

## §9 Verification

Done when all 13 gates from §5 Phase D pass + 2 new LDs + 1 PATCHed LD +
all activity_log rows written. Proof artifacts:

- Bug status table
- `git diff` of all bug fix patches
- Smoke test results (with screenshots if Kim hands-on)
- Directus row IDs for LDs + activity log

## §10 Rollback

- Bug fixes: revert via git per-commit
- VideoSelector: delete TSX file + un-register from header; v59 returns
  to single-active-video state (defaults to intro)
- New endpoints: revert per git
- `state.active_video` field: backwards compatible (handlers ignore it
  per LD-474); no rollback needed

## §11 Out of Scope (S5.5b)

- Beat Generator UI build — that's S5.5c
- Beat Generator backend endpoint additions — that's S5.5c Phase A
- WaveSurfer.js timeline (LD-472) — explicitly deferred per
  S5.5a2 handoff stub "Honest deferral to Session 6"
- Per-event-per-video Playwright matrix expansion — defer
- Stitch job retry logic — V2

## §12 Dependencies on Prior Sessions

**Hard dependency on S5.5a2:**
- `state.videos.<role>` partition exists
- `_assert_event_scope` validates `scope_video_role`
- LD-474 enforced in mutating handlers
- `state.active_video` field exists on state (write-target for
  VideoSelector POST)

**Hard dependency on S5.5a1:**
- `state.validate_video_role()` helper exists
- `_image_overrides` cache-clear on event_load (Bug 1 may already
  be resolved by this)

**Independent of:**
- S5.5c (Beat Generator) — but if combined into one session, run b
  FIRST so c can use VideoSelector

## §13 Notes for the Executing Session

- Phase A is BLOCKING — do not start Phase B fixes without bug-status
  audit complete
- Where this spec and the original Cursor v5 review disagree, the
  CURRENT BEHAVIOR (as discovered in Phase A) wins — fixes apply to
  what's actually broken now, not what was broken at v5 review time
- Per Rule 35: every Directus write consults
  `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE
  payload composition; uses `try_post_or_queue`
- Per Rule 36: any new Path B-style patches in storyboard-v2 follow
  invariant constraints
- Per Rule 19: no shortcuts. If Phase A surfaces a bug whose fix
  is more involved than expected, surface to Kim — do not stub

---

**End of S5.5b spec v1.** When combined with S5.5c into a single session,
ORDER: b first (Phases A–E), then c. Hard gate: all 13 of b's verification
gates must pass before c starts. If any b gate fails or surfaces a
surprise, STOP and write c handoff for next session.

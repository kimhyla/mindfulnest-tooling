# S5.5b Bug-Status Audit — 2026-05-03

**Authored:** Phase A of S5.5b combined-with-c session, 2026-05-03  
**Authoritative repro source:** `Production/docs/STORYBOARD_V59_S5_5_B_SPEC_v1.md` §3 (Cursor v4/v5 reports unfindable on disk; B_SPEC_v1 is comprehensive synthesis — see preflight #196 deviation flag #1).  
**Server tested against:** PID 5303, started 2026-05-03 10:42:53, fresh post-S5.5a2 (py_compile + LD-474 audit clean).  
**Method:** empirical probes (curl, file inspection) + grep + execution-risk subagent's structured-evidence audit.

---

## Status Summary

| Bug | Spec Description | Status | Evidence | Action |
|---|---|---|---|---|
| **1** | Storyboard image scrambling on event swap | **RESOLVED by S5.5a1+a2** | Cross-event swap returns 200 with cache-clear log lines (6 in log); `_image_overrides` nested by role (LD-478); signal stores re-allocate per `scopeKey` (`scope.ts:24-26`) | Mark RESOLVED-BY-PRIOR. Log to activity log. No patch. |
| **2** | Stitcher persistence/shape mismatch | **STILL REPRODUCES (likely coupled to Bug 3)** | UI in `StitcherTab.tsx:215-282` complete; tab POSTs to `/api/stitch_editor/job` + `/preview` without `scope_video_role`; couples to LD-474 strictness if/when enforced | Phase B Step 1: investigate shape vs coupling; surface to Kim if both drifted. |
| **3** | Magic POST scope_video_role plumbing | **STILL REPRODUCES** | `path_picker.html:593,601,613` carry `scope_event_id` but NOT `scope_video_role`. Server-side `_check_event_pin` extension (a2) waits for client to provide the field. Currently `allow_missing_video_role=True` tolerates it but routes to `intro` always — wrong if Kim is editing a non-intro video. | Phase B Step 3: patch `path_picker.html` to inject `scope_video_role` from URL param / window global. |
| **4** | EventSelector page reload doesn't propagate | **STILL REPRODUCES** | `/api/event/current` does not exist (grep zero hits in `production_server.py`). `EventSelector.tsx:72` calls `window.location.reload()` without updating URL. `ScopeBoundary.tsx` reads stale URL/attr/global. | Phase C: implement BOTH fixes per spec §3 Bug 4 (belt+suspenders). |
| **5** | (no detailed entry; B_HANDOFF L59 flags as renumbering artifact) | **NON-EXISTENT** | Zero detailed entries in any spec; only listed in deferred-list bullets. Cursor v4/v5 reports unfindable. Likely renumbering artifact from review revisions. | Mark NON-EXISTENT / WONTFIX. Log decision to activity log. |
| **6** | Stitch job persistence | **MOSTLY RESOLVED** | `Production/tools/stitch_editor_state.json` exists with 3 jobs persisted. `StitchEditorState` is file-backed (not in-memory only as spec claimed). The spec's prescribed fix (prod_activity_log integration) is over-engineering for V1 — file persistence already works. | Mark MOSTLY-RESOLVED. Phase B Step 6: smoke test (initiate → restart → reappear). If passes, log RESOLVED. If fails, audit gap. |
| **7** | (no detailed entry) | **NON-EXISTENT** | Same evidence as Bug 5 — referenced only in deferred-list bullets across 3 prior specs; no detailed entry anywhere. | Mark NON-EXISTENT / WONTFIX. Log decision. |

---

## Detail per Bug (with proof artifacts)

### Bug 1 — Storyboard image scrambling on event swap → **RESOLVED**

**a1 fix (LD-475):** `_handle_event_load` clears `_image_overrides` + `_pending_override_keys` inside `event_load_lock`. Confirmed at `production_server.py` cache-clear region.

**a2 extension (LD-478):** Caches now nested `dict[role, dict[bid, data_uri]]`. Same beat_id across partitions doesn't contaminate.

**Live probe (this session, 2026-05-03):**
```
swap Event_1 → Event_2: HTTP=200
swap Event_2 → Event_1: HTTP=200
[event/load] cleared image override cache (event swap to Event_2)
[event/load] cleared image override cache (event swap to Event_1)
```
6 cache-clear log lines in `/tmp/prodserver_s5_5a2.log` since server start.

**Client-side:** `Production/tools/storyboard-v2/src/state/scope.ts:24-26` builds `scopeKey` per `{event_id, beat_id, version}`; `getScopedStore` allocates fresh stores per scope-key. Event swap → new scope-key → new store. No stale image URLs survive across event swaps.

**Verdict:** RESOLVED-BY-PRIOR (S5.5a1 + S5.5a2). No code change needed.

---

### Bug 2 — Stitcher persistence/shape mismatch → **STILL REPRODUCES (mild)**

**Cursor v5 quote (via B_SPEC §3 Bug 2):** "4-slot code IS in StitcherTab.tsx (lines 215-282) — issue is job persistence/shape, not missing UI."

**Empirical:** UI is complete (StitcherTab L215-282 renders 4 slots: intro, phase_a, phase_b, resolution + ambient/preview controls). Persistence works (Bug 6 evidence). Likely residual: shape mismatch on what the tab READS vs what server WRITES on a stitch job, OR coupling to Bug 3 (no scope_video_role in stitch POSTs).

**Phase B plan:** Read StitcherTab L215-282 fully + match against `/api/stitch_editor/job` + `/preview` server handlers. If shape diverges, fix at the side that drifted from the original spec. If Bug 3 is the actual root cause, fix together.

---

### Bug 3 — Magic POST scope_video_role plumbing → **STILL REPRODUCES**

**Empirical (path_picker.html):**
```
277:  const scopeEventId = params.get('scope_event_id') || params.get('event_id') || '';
593:    scope_event_id: scopeEventId || 'Event_1',    // POST /api/storyboard/magic_path (Workflow A)
601:    scope_event_id: scopeEventId || 'Event_1',    // POST /api/storyboard/magic_video (Workflow B)
613:    scope_event_id: scopeEventId || 'Event_1',    // POST /api/storyboard/watercolor_animate (Workflow C)
```

NO `scope_video_role` in any of the 3 magic POSTs.

**Server side (post-a2):** `_assert_event_scope` validates `scope_video_role` when present; missing currently allowed via `allow_missing_video_role=True`. The 17 `_check_event_pin` sites all have `pinned_video_role: (body or {}).get("scope_video_role", "intro")` — defaulting to `intro`.

**Implication:** Kim editing `phase_a` partition who triggers a magic POST writes to `intro` partition by mistake. Symptomatically silent until Kim notices the magic clip is on the wrong video.

**Fix:** Phase B Step 3 — patch path_picker.html to inject `scope_video_role` from URL param + `window.__MN_VIDEO_ROLE__` + localStorage fallback (matching the EventSelector pattern). Add as 4th line to each of the 3 POST bodies.

---

### Bug 4 — EventSelector page reload doesn't propagate → **STILL REPRODUCES**

**Empirical:**
- `grep "event/current\|_handle_event_current" production_server.py` → zero hits. **Endpoint does not exist.**
- `grep "?event=\|history.pushState" EventSelector.tsx` → only `window.location.reload()` at L72. **No URL update.**
- ScopeBoundary.tsx (per subagent) reads URL/attr/global on boot — gets STALE values after EventSelector reload.

**Cursor v5 verbatim (B_SPEC §3 Bug 4):**
> "EventSelector reloads page after `/api/event/load` but ScopeBoundary on boot only reads `?event=` URL param, `data-event-id` attr, or `__MN_EVENT_ID__` — none of which are updated by EventSelector."

**Fix (BOTH per spec recommendation):**
- (A) Add `GET /api/event/current` endpoint — returns currently-active event from server state
- (B) EventSelector navigates `?event=<id>` after `/api/event/load` — URL becomes source of truth

Belt + suspenders. Both ship in PART 1 Phase C.

---

### Bug 5 — **NON-EXISTENT (renumbering artifact)**

**Evidence:** Searched all `Production/docs/` for "Bug 5", "Bug_5":
- Found ONLY in `B_HANDOFF.md:59` ("Note on Bug 5: missing from the deferred list — it was either renumbered in v5 review or already addressed")
- B_SPEC_v1 §3 contains entries for Bugs 1, 2, 3, 4, 6 — no §3.5
- Cursor v4/v5 review reports unfindable on disk

**Decision:** Close as NON-EXISTENT / WONTFIX. Log activity_log row `BUG_5_WONTFIX_NON_EXISTENT` with rationale.

---

### Bug 6 — Stitch job persistence → **MOSTLY RESOLVED (verify by smoke test)**

**Empirical:**
- `Production/tools/stitch_editor_state.json` exists, 584 bytes, `{version, jobs}` shape, **3 jobs persisted**
- File mtime 2026-04-26 (pre-a1, written by S5 work)
- `StitchEditorState` is file-backed, not in-memory only

**Spec said:** "Job metadata stored in memory, not in prod_activity_log." → empirically incorrect; persistence already works via JSON file.

**Smoke-test plan (Phase D gate):** initiate stitch job → kill server → restart → confirm job in library.

**Decision:** Mark MOSTLY-RESOLVED. Log as such. Skip the spec's prescribed `prod_activity_log` integration unless smoke test fails.

---

### Bug 7 — **NON-EXISTENT**

**Evidence:** Identical to Bug 5 — only referenced in deferred-list bullets across 3 prior specs (`A1_SPEC_v1:421`, `A1_SPEC_v2:632`, `A2_HANDOFF:157`). No detailed entry, no symptom, no fix path. Cursor v4/v5 reports unfindable.

**Decision:** Close as NON-EXISTENT / WONTFIX. Same activity_log pattern as Bug 5.

---

## Phase A Outcome

| Action item | Phase B work needed |
|---|---|
| Bug 1 RESOLVED | None — log only |
| Bug 2 STILL REPRODUCES | Investigate shape vs Bug 3 coupling |
| Bug 3 STILL REPRODUCES | Patch path_picker.html (3 POST bodies) |
| Bug 4 STILL REPRODUCES | Add `/api/event/current` + EventSelector URL nav (Phase C) |
| Bug 5 NON-EXISTENT | Log WONTFIX |
| Bug 6 MOSTLY RESOLVED | Smoke test only; activity_log row if test passes |
| Bug 7 NON-EXISTENT | Log WONTFIX |

**Total Phase B scope:** Bug 2 investigation + Bug 3 path_picker.html patch (3 lines × 3 sites). Plus 3 NON-FIX activity_log rows (1 RESOLVED-BY-PRIOR, 2 WONTFIX, 1 MOSTLY-RESOLVED).

**Phase C scope (separate from bug fixes):** 4 new endpoints + VideoSelector + pathappPatch auto-injection.

**Forward signal — S5.5c Phase A:** Beat-gen endpoint grep confirms 0 of 6 endpoints exist. C_SPEC Phase A will need to ADD all 6, not just port UI. Forecast logged in preflight #196 R6.

---

**End of bug-status audit. Phase B begins after this row + 3 BUG_AUDIT activity_log rows are written.**

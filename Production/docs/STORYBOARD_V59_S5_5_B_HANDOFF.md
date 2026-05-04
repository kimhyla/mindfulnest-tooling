# S5.5b Terminal Handoff — v59 Storyboard Rewrite

**Authored by S5.5a2 (closeout)** — 2026-05-03

This is the entry-point handoff for **Sub-Session S5.5b**. S5.5a2 (migration apply
+ handler refactor + scope token expansion) shipped on 2026-05-03 — production
state.json files are live in v2 partition shape, ~50 distinct edit sites refactored
across handlers/helpers/AppContext init/smoke test, server is back online.
S5.5b focuses on **bug fixes** (Cursor v4/v5 findings) + **VideoSelector UI**
(now unblocked by a2's live partition).

---

## What S5.5a2 left on disk + Directus (pre-conditions for S5.5b)

| Artifact | Path / ID | State |
|---|---|---|
| Migration | `Production/Event_*/production_state.json` | LIVE in v2 shape: `videos.{intro\|phase_a\|phase_b\|win}` |
| Snapshots | `Production/Event_<N>/.backups/state/20260503T140831Z_pre_videos_migration.json` | sha256-verified equal to pre-state |
| Handler refactor | `Production/tools/production_server.py` | 21 handlers + ~52 mutator closures + 17 `_check_event_pin` pin-init sites refactored to v2 paths; py_compile clean; smoke-test path updated |
| `_scope_body` / `_assert_event_scope` | L4593 / L4524 | extended with `scope_video_role` (validates against canonical set + `state.validate_video_role`); `allow_missing_video_role=True` default during refactor window |
| `AppContext._image_overrides` | nested `dict[role, dict[bid, data_uri]]` | hydrates from `videos[role].image_overrides` per `IMAGE_OVERRIDES_NESTED_BY_ROLE_V1` |
| LD-474 audit script | `Production/scripts/ld474_audit_active_video.py` | passes — zero `state["active_video"]` reads anywhere |
| New LDs | `prod_locked_decisions` 476 (STATE_MIGRATION_APPLIED_V1, HIGH), 477 (HANDLER_REFACTOR_VIDEOS_PARTITION_V1, HIGH), 478 (IMAGE_OVERRIDES_NESTED_BY_ROLE_V1, MEDIUM) | active |
| PATCHed LDs | LD-456 / LD-460 / LD-461 | extension notes appended |
| Preflight | `prod_preflight_reviews` id=195 | architectural; `related_activity_log_id=1465` |
| Activity log | `prod_activity_log` id=1465 | action=`S5_5A2_COMPLETE` with full gate summary + scope-vs-stub deviation transparency |
| Server | PID changed; runs `Production/Event_1/storyboard_v59_prod.html` | log: `/tmp/prodserver_s5_5a2.log`; nested `_image_overrides` hydration confirmed at startup |

---

## What S5.5b must do

### Pre-flight (mandatory per Rule 19, LD-262)

1. Load `zero-error-qa` skill
2. Classify: depends on which bug-fix bundle Kim chooses to ship in this session.
   - Bugs 1, 2, 3, 4, 6, 7 (Cursor v4/v5 findings) — **ROUTINE per-bug** unless they
     touch security/auth/schema; classify each individually.
   - VideoSelector UI in v59 client — **ROUTINE** (frontend component build);
     classify ARCHITECTURAL only if it changes the v59 client → server contract.
3. Validation Tier: A (per-bug routine) or B (if any bug touches schema/auth)
4. Write `prod_preflight_reviews` row via `try_post_or_queue` BEFORE any edit;
   confirm via read-back. Reference preflight #195 as immediate predecessor.

### Phase A — Cursor v4/v5 bug fixes

Bugs 1-4, 6, 7 from the v4/v5 reviews are deferred items. Locate the original
review reports (referenced in `STORYBOARD_V59_S5_5_A1_SPEC_v2.md` §11) and
process each:

1. **Read the bug description + repro from the review report**.
2. **Classify per bug** (per Phase 0 step above).
3. **Fix + verify** via the standard pattern: read region → edit → py_compile →
   functional probe.
4. **Activity log per bug** with `action=s5_5b_bug_<N>_fixed` and proof-of-fix
   evidence.

**Note on Bug 5**: missing from the deferred list — it was either renumbered
in v5 review or already addressed. Check Cursor v5 review notes before
assuming it doesn't exist.

### Phase B — VideoSelector UI (v59 client)

The migration is live; multi-partition state is real on disk; the v59 client
needs a `VideoSelector` component so Kim can switch between
intro/phase_a/phase_b/win partitions in the UI. Build per the v3.1 spec
architectural notes:

1. **Component:** `<VideoSelector />` rendering a dropdown of
   `state.videos.{role}` entries (queryable via the new `/api/video/list`
   endpoint — does NOT exist yet; see Step 4).
2. **Local signal:** `activeVideo` in v59 client (preact signal). Persists to
   `state.active_video` via `pathappPatch` on user select. Per
   `VIDEO_ROLE_PER_REQUEST_V1` (LD-474), this is **client-local** — server
   does NOT cache or use it for partition selection.
3. **Mutation contract:** every mutating fetch from v59 includes
   `scope_video_role` in the request body. The v59 `pathappPatch` helper
   should auto-inject the current `activeVideo` signal value.
4. **New endpoint** (server side): `GET /api/video/list` returns the result
   of `self.app.state.list_videos()` (helper already exists from S5.5a1).
   Add scope guard via `self._scope_body(body)`. Read-only — no `_check_event_pin`
   needed.
5. **`+ New video` button:** invokes `POST /api/video/create` with body
   `{scope_event_id, video_role, video_label}`. Server uses
   `self.app.state.create_video(role, label)`. Validate role via
   `_VALID_VIDEO_ROLES`; 400 on duplicate.

### Phase C — Verification (Tier A or B per classification)

1. `python3 -m py_compile Production/tools/production_server.py`
2. Per-bug: re-test the original repro to confirm fix
3. Server restart + `/api/health` 200
4. VideoSelector E2E in browser: load Event_1, select intro → see intro beats;
   select phase_a → see phase_a state; `+ New video` creates a partition that
   persists to disk; v59 client `pathappPatch` includes `scope_video_role` in
   every request body
5. LD-474 audit script still passes (zero `state["active_video"]` reads in
   mutating handlers)
6. Cross-event swap (Event_1→Event_2→Event_1) — cache-clear log line still
   appears 3×; per-event isolation holds across partitions

### Phase D — LD registrations

- Per fixed bug: register `BUG_<N>_FIXED_V1` LD or PATCH the original bug LD
  with `closure_date` + status update
- New LD: `VIDEO_SELECTOR_UI_V1` if the component is non-trivial
- New LD: `API_VIDEO_LIST_V1` and `API_VIDEO_CREATE_V1` for the new endpoints

---

## Critical constraints

1. **Migration is live; no rollback path** — any further state.json edits
   must respect v2 shape. Use `mutate_video_state(role, ...)` for partition
   writes; `mutate_state(...)` only for top-level (`event_id`, `version`,
   `_module_version`, `module_sfx_cues`, `latest_preview_stitched_path`,
   `full_module_segment_boundaries`, `fade_between_beats_ms`, `active_video`).
2. **LD-474 stays hard** — handlers MUST NOT read `state["active_video"]`;
   only `body["scope_video_role"]`. Run the audit script as a gate.
3. **No new shortcuts** — same Rule 19 discipline as a1/a2.
4. **VideoSelector is read-and-redirect, not a toggle** — switching the
   selector MUST update the client's local `activeVideo` signal AND persist
   `state.active_video` via pathappPatch. Server still picks partition from
   request body, never from state.

---

## Verification gates (S5.5b must pass all that apply)

1. ✅ `migrate_state_to_videos_partition.py --validate` exits 0 (still v2;
   no regressions)
2. ✅ `python3 -m py_compile Production/tools/production_server.py` clean
3. ✅ Server restarts; `/api/health` returns 200
4. ✅ Per-bug repro confirms fix
5. ✅ VideoSelector E2E (if Phase B in scope): partition switch → request
   body carries `scope_video_role`
6. ✅ LD-474 audit script: 0 violations
7. ✅ Cross-event swap cache-clear unchanged
8. ✅ Per-bug LDs registered (or PATCHed)
9. ✅ `prod_activity_log` row `S5_5B_COMPLETE` with full gate summary
10. ✅ S5.5c handoff stub written (Beat Generator UI Option B+)

---

## Reference

- **Pre-spec:** `Production/docs/STORYBOARD_V59_S5_5_A2_HANDOFF.md` (S5.5a2
  handoff). S5.5b does not yet have a separate spec; this handoff is the
  working spec until one is authored.
- **Architecture doc:** `Production/docs/STORYBOARD_V59_SPEC_v3_1.md`
  (canonical, sessions 1.5-5 lineage)
- **Rules:** CLAUDE.md Rules 19, 27, 29, 35, 36
- **LDs from S5.5a1:** 473 (BG_VIDEO_PARTITION_V1), 474 (VIDEO_ROLE_PER_REQUEST_V1),
  475 (IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1)
- **LDs from S5.5a2:** 476 (STATE_MIGRATION_APPLIED_V1),
  477 (HANDLER_REFACTOR_VIDEOS_PARTITION_V1), 478 (IMAGE_OVERRIDES_NESTED_BY_ROLE_V1)
- **PATCHed LDs:** 456 (SCOPE_VALIDATION_V1), 460 (ASYNC_JOB_GENERATION_PIN_V1),
  461 (SCOPE_BODY_HELPER_V1)
- **Preflight predecessor:** id=195 (S5.5a2), related_activity_log_id=1465
- **Audit script:** `Production/scripts/ld474_audit_active_video.py`
- **Cursor v4/v5 reviews:** referenced in S5.5a1 + S5.5a2 preflights as
  architectural-review exemption per LD-124. v4/v5 also list Bugs 1-4, 6, 7
  for S5.5b — locate the review reports for repro details.

---

## What S5.5c expects (forward dep)

S5.5c is "Beat Generator UI build (Option B+)" per the original spec v2 §10
out-of-scope list. It depends on:
- VideoSelector UI being live (S5.5b Phase B)
- Per-partition beat editing being a real flow Kim can use

If S5.5b ships only bug fixes and defers VideoSelector to S5.5c, then S5.5c
becomes "VideoSelector + Beat Generator UI" together. Kim's call.

---

**End of S5.5b handoff stub.** Hand off to terminal Claude Code with:
"Read this stub. Run Phase 0 preflight per the procedure above. Then
execute Phases A–D in the order/scope you decide. Report back when
verification gates pass."

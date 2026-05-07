# S5.5a2 Terminal Handoff — v59 Storyboard Rewrite

**Authored by S5.5a1 (closeout)** — 2026-05-03

This is the entry-point handoff for **Sub-Session S5.5a2**. S5.5a1 (foundation
tools) is complete. S5.5a2 applies the migration ATOMICALLY with a handler
refactor — the migration cannot be applied in isolation because ~30 handlers
still read `state.beats` rather than `state.videos.<role>.beats`; applying
without refactoring would crash the server on next event load (Cursor v5 Q1
release-blocker).

---

## What S5.5a1 left on disk (pre-conditions for S5.5a2)

All in `Production/`:

| Artifact | Path | State |
|---|---|---|
| Migration script | `scripts/migrate_state_to_videos_partition.py` | exists, dry-run tested both events; `--apply` mode coded but NEVER invoked |
| StateManager helpers | `tools/production_server.py` L1056-1164 | 5 helpers added: `get_beats`, `mutate_video_state`, `list_videos`, `create_video`, `validate_video_role`; class const `_VALID_VIDEO_ROLES` |
| Cache fix | `tools/production_server.py` L5788-5808 | `_handle_event_load` clears `_image_overrides` + `_pending_override_keys` (DICT) inside `event_load_lock` |
| TECH_SPEC banner | `tools/GPT_STILLS_TECH_SPEC_v1.md` | SUPERSEDED banner at top |
| LDs PATCHed | Directus `prod_locked_decisions` | LD-426, LD-431, LD-428, LD-429 → `superseded_by_id` set, `status='superseded'`, `is_current=false`, `date_superseded='2026-05-03'`, notes appended |
| LDs new | Directus `prod_locked_decisions` | LD-473 BG_VIDEO_PARTITION_V1 (HIGH), LD-474 VIDEO_ROLE_PER_REQUEST_V1 (HIGH), LD-475 IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1 (MEDIUM) |
| Preflight row | Directus `prod_preflight_reviews` id=194 | `task_type=architectural`, `approved_to_proceed=true`, `related_activity_log_id=1463` |
| Activity log | Directus `prod_activity_log` id=1463 | action=`S5_5A1_COMPLETE` with full verification gate summary |

State files unchanged:

- `Production/Event_1/production_state.json` — version=v1, 30 top-level keys, mtime 2026-05-03 00:06:24Z (pre-session)
- `Production/Event_2/production_state.json` — version=v1, 6 top-level keys, mtime 2026-04-26 03:05:10Z (pre-session)

---

## What S5.5a2 must do (atomic — these MUST land in the same session)

The migration apply + the handler refactor MUST ship together. There is no
intermediate state where one is correct and the other is not — see
`STORYBOARD_V59_S5_5_A1_SPEC_v2.md` §1 + §11 for the full rationale.

### Pre-flight (mandatory per Rule 19, LD-262)

1. Load `zero-error-qa` skill
2. Classify: ARCHITECTURAL — schema migration applied to live state files +
   ~30 handler call-site changes touching cross-event read paths
3. Validation Tier: B (architectural, server boundary changes — but no app/RN
   diff, so not C)
4. Spawn 4+4 advocate/counter (UNLESS a v6-style design review or Cursor
   cycle has already served as the architectural review per LD-124, in
   which case follow that LD pattern and document the exemption — same as
   S5.5a1 did)
5. Write `prod_preflight_reviews` row via `try_post_or_queue` BEFORE any
   edit; confirm via read-back

### Phase A — Migration apply (SHORT, but irreversible without snapshot)

1. **Stop the server** — `pkill -f production_server.py`
2. **Confirm Dropbox sync paused** (or warn Kim; the migration writes
   per-event state.json files which are Dropbox-synced)
3. **Run** `python3 Production/scripts/migrate_state_to_videos_partition.py
   --apply` — script prints user warning + 5s confirm prompt; type
   `apply migration` to proceed
4. Per-event: snapshot to `Event_<N>/.backups/state/<TS>_pre_videos_migration.json`,
   atomic write of v2-shape state.json, read-back verify `is_already_migrated()`
5. **Validate via** `--validate` mode — exit 0 expected on all event state files
6. **Inspect** `Event_1/.backups/state/` — confirm snapshot exists + matches
   pre-migration content

### Phase B — Handler refactor (~30 handlers, mechanical but high-volume)

The handlers that read or write `state.beats` need to read/write
`state.videos[video_role].beats` instead. Identify them with:

```bash
grep -nE 'state\["beats"\]|state\.beats|state\.get\("beats"' Production/tools/production_server.py
```

For each:

1. **Read paths** — replace with `self.app.state.get_beats(video_role)`
   (where `video_role` comes from `body.get("scope_video_role", "intro")` —
   default 'intro' for backwards compatibility during the refactor window
   only; remove default after all clients pass `scope_video_role` explicitly)
2. **Write paths** — wrap in `self.app.state.mutate_video_state(video_role,
   lambda partition: ...)` instead of `self.app.state.mutate_state(lambda
   state: ...)`. The mutator now receives the **partition** dict, not the
   full state.
3. **CRITICAL CONSTRAINT (LD-474 VIDEO_ROLE_PER_REQUEST_V1):** handlers
   MUST NOT read `state["active_video"]` to choose a partition. Only
   `body["scope_video_role"]` drives partition selection in mutating
   handlers. Add a lint/audit script to catch violations: grep for
   `state\["active_video"\]` in mutating handler functions and fail if
   any usage is in a non-read-only context.

### Phase C — Scope token expansion (LD-456 + LD-461 extension)

`_assert_event_scope` and `_scope_body` need to validate `scope_video_role`
on every mutating request — same pattern as `scope_event_id`:

1. Extend `_scope_body(body, ...)` to surface `scope_video_role` (default
   'intro' during refactor window; required after)
2. Extend `_assert_event_scope` to call `state.validate_video_role(role)`
   and 400 with `{"code": "VIDEO_ROLE_INVALID", "valid": [...]}` on
   unknown role
3. Extend LD-460 async pin tuple to include `video_role` (so async jobs
   can't write to a different partition than they pinned at start)
4. Extend magic POSTs (LD-468/469/470) to carry `scope_video_role`

### Phase D — Verification (Tier B mandatory)

1. `python3 -m py_compile Production/tools/production_server.py`
2. Restart server; `/api/health` returns 200
3. `/api/event/load` for Event_1 returns 200; state v2-shape; cache-clear
   log line still appears
4. Functional probes for refactored endpoints: pick 5 representative
   handlers (1 phase_a write, 1 phase_b write, 1 intro read, 1 image
   override write, 1 cross-event swap), run each via curl, assert
   correct partition mutated
5. v59 client smoke test — load Event_1, verify Phase A and Phase B
   panels still show their data after migration (state was lifted into
   `videos.phase_a` and `videos.phase_b`)

### Phase E — LD registrations

Register or PATCH:

- New LD: `STATE_MIGRATION_APPLIED_V1` — locks the moment of migration
  apply with timestamp + per-event snapshot paths
- New LD: `HANDLER_REFACTOR_VIDEOS_PARTITION_V1` — locks the new handler
  contract (read via `get_beats`, write via `mutate_video_state`,
  partition selection via `body['scope_video_role']` only)
- PATCH LD-456 (SCOPE_VALIDATION_V1) — append note about `scope_video_role`
  extension
- PATCH LD-460 (ASYNC_JOB_GENERATION_PIN_V1) — append note about
  `video_role` in pin tuple
- PATCH LD-461 (SCOPE_BODY_HELPER_V1) — append note about
  `scope_video_role` extraction

---

## Critical constraints

1. **Server MUST be stopped before `--apply`.** The migration writes to
   files the server holds open; concurrent writes will corrupt state.
2. **No partial application.** If any state file fails validation, the
   script halts and exits non-zero; restore ALL files from snapshots
   before retrying. Do NOT proceed with handler refactor on a partially-
   migrated set.
3. **Handler refactor + migration must land in same commit.** A commit
   that has only one is a broken state for anyone who pulls it.
4. **No new shortcuts.** S5.5a1 explicitly avoided shortcuts (deferral
   to S5.5a2 was justified by atomic-dependency, not convenience).
   S5.5a2 must apply the same discipline — no "we'll fix that handler
   later" allowed.
5. **Out of scope for S5.5a2:**
   - Bug fixes from Cursor v4 (Bug 1-4, Bug 6, Bug 7) — those are S5.5b
   - Beat Generator UI build (Option B+) — that's S5.5c

---

## Verification gates (S5.5a2 must pass all)

1. ✅ `migrate_state_to_videos_partition.py --validate` exits 0 (all
   files at v2)
2. ✅ `python3 -m py_compile Production/tools/production_server.py`
   clean after handler refactor
3. ✅ Server restarts; `/api/health` returns 200
4. ✅ `/api/event/load` for Event_1 returns 200 with `version=v2` state
5. ✅ Functional probe: write to `phase_a` partition via existing handler
   succeeds; partition gets the expected field; v59 client renders the
   value
6. ✅ Functional probe: write to `phase_b` partition; same as above
7. ✅ Cross-event swap (Event_1 → Event_2 → Event_1) — cache-clear log
   line appears each time; per-event state isolation holds
8. ✅ Lint/audit script — zero violations of LD-474 (`state["active_video"]`
   reads in mutating handlers)
9. ✅ Snapshots present at `Event_<N>/.backups/state/<TS>_pre_videos_migration.json`
10. ✅ LDs registered: STATE_MIGRATION_APPLIED_V1 +
    HANDLER_REFACTOR_VIDEOS_PARTITION_V1
11. ✅ LDs PATCHed: 456, 460, 461 with extension notes
12. ✅ `prod_activity_log` row `S5_5A2_COMPLETE` with full gate summary
13. ✅ S5.5b handoff stub written

---

## Reference

- **Spec:** `Production/docs/STORYBOARD_V59_S5_5_A1_SPEC_v2.md` (S5.5a1
  spec — comprehensive context). S5.5a2 does not yet have a separate
  spec; this handoff is the working spec until one is authored.
- **Architecture doc:** `Production/docs/STORYBOARD_V59_SPEC_v3_1.md`
  (canonical, sessions 1.5-5 lineage)
- **Rules:** CLAUDE.md Rules 19, 27, 29, 35, 36
- **LD-124** (PHASE_0_STEP_0) — preflight protocol
- **LD-262** (CLASSIFICATION_INSIDE_PHASE_0_STEP_1) — classification
  sentence requirement
- **LD-456 / LD-460 / LD-461** — scope guard contracts to extend
- **LD-473 / LD-474 / LD-475** — new locks from S5.5a1
- **Cursor v4 + v5 reviews** — design + execution-spec validation
  (referenced in S5.5a1 preflight 194 as architectural-review
  exemption from in-session 4+4 spawn per LD-124 pattern)

---

**End of S5.5a2 handoff stub.** Hand off to terminal Claude Code with:
"Read this stub. Run Phase 0 preflight per the procedure above. Then
execute Phases A–E in order. Report back when all 13 verification gates
pass."

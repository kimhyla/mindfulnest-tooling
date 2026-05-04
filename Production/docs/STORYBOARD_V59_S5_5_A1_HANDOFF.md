# S5.5a1 Terminal Handoff — v59 Storyboard Rewrite

**Paste the entire prompt below into your existing terminal Claude Code session.**

---

## PROMPT START

You are continuing the v59 storyboard rewrite. This is **Sub-Session S5.5a1** of the v59 build (Sessions 1, 1.5, 2, 3, 4, 5 already shipped to disk).

### Read these FIRST, in order:

1. **`Production/docs/STORYBOARD_V59_S5_5_A1_SPEC_v2.md`** — your executable spec for THIS session. Read fully. This is the source of truth.
2. **`Production/docs/STORYBOARD_V59_SPEC_v3_1.md`** — canonical architecture doc (Sessions 1.5–5 lineage)
3. **`CLAUDE.md`** Rules 19, 27, 35, 36 — no-shortcuts, delete obsolete workarounds, Directus schema verification, patch invariant persistence
4. **Phase 0 pre-flight is mandatory** — this task classifies as **ARCHITECTURAL but LOW-RISK execution** per spec v2 §Classification. Spawn 4+4 advocate+counter agents per Rule 19 Phase 0, write `prod_preflight_reviews` row BEFORE any edit, then proceed.

### Scope of THIS session (S5.5a1)

Per spec v2 §1 (re-scoped via Option C):

**IN SCOPE:**
- 5 helper methods on `StateManager` in `Production/tools/production_server.py` (`get_beats`, `mutate_video_state`, `list_videos`, `create_video`, `validate_video_role`)
- 1 cache fix in `_handle_event_load` (~L5775): clear `_image_overrides = {}` AND `_pending_override_keys = {}` (dict, not set)
- Migration script `Production/scripts/migrate_state_to_videos_partition.py` — **WRITE + DRY-RUN ONLY, DO NOT APPLY**
- 2 LD registrations: `STATE_VIDEOS_PARTITION_V1` + `S5_5A1_HELPERS_V1` (Phase F — LAST)
- Verification gates per spec v2 §6

**OUT OF SCOPE (deferred to S5.5a2):**
- Migration application to any `Production/Event_*/production_state.json` file
- Handler refactor (~30 handlers) to use new partition
- Scope token expansion to include `video_role`
- Anything that touches read-paths in handlers

### Critical constraints (don't violate)

1. **DO NOT apply the migration to any state.json file.** Script is dry-run only. Application happens in S5.5a2 atomically with handler refactor — applying here without handler updates = server crash on next event load.
2. **`_pending_override_keys` is a dict[str, str], NOT a set.** Spec v2 §3.3 corrected this from v1.
3. **`active_video` is a read-only display hint.** Helper write-paths must NOT use it for partition selection. Spec v2 §3.4.
4. **Rule-based lift via regex** — `^phase_a_` → `videos.phase_a.{key}`; `^phase_b_` → `videos.phase_b.{key}`. Spec v2 §3.1 enumerates the keep-at-top-level set + module-level homes.
5. **LD writes use Rule 35 protocol** — consult `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` BEFORE composing payload; use `try_post_or_queue` from `Production/lib/directus.py`. `prod_locked_decisions.severity` is UPPERCASE.
6. **Server staleness check before any "test it"** — Rule 29. Verify `lsof -ti:5111` PID start time is AFTER your last `production_server.py` edit.

### Verification before declaring done

Per spec v2 §6, ALL of these must pass:

1. ✅ `python3 -c "from production_server import StateManager; sm = StateManager(); assert hasattr(sm, 'get_beats') and hasattr(sm, 'mutate_video_state') and hasattr(sm, 'list_videos') and hasattr(sm, 'create_video') and hasattr(sm, 'validate_video_role')"` — all 5 helpers present
2. ✅ `_handle_event_load` clears BOTH `_image_overrides` and `_pending_override_keys`
3. ✅ Migration script runs in dry-run mode against Event_1 state.json without errors and reports the proposed partition
4. ✅ Migration script idempotency check returns "already migrated" on a v2-shape state.json (synthesize a fake one to test)
5. ✅ Migration script fail-closes on partial migration (synthesize a half-migrated state.json to test)
6. ✅ Server restart succeeds; `/api/event/load` for Event_1 returns 200 with v1-shape state intact (no migration applied = no behavior change)
7. ✅ `python3 Production/scripts/migrate_state_to_videos_partition.py --dry-run --event Event_1` runs from `Production/tools/` cwd (sys.path correct)
8. ✅ Both LDs registered in `prod_locked_decisions` with `try_post_or_queue` read-back confirming write

### What success looks like at end of session

- Server restarted with new helpers + cache fix on disk
- v1-shape state.json files unchanged (migration NOT applied)
- Migration script tested in dry-run, ready for S5.5a2 to call with `--apply`
- 2 LDs registered
- `prod_activity_log` entry: `S5_5A1_COMPLETE` with verification gate results
- Handoff stub for S5.5a2 written to `Production/docs/STORYBOARD_V59_S5_5_A2_HANDOFF.md`

### If anything is ambiguous

Read spec v2 §3 (Implementation Detail), §4 (Phases A–F), and §11 (S5.5a2 Dependencies). The spec is comprehensive — Cursor v5 reviewed it and approved the rescoped version. Don't reinvent; execute.

If you find a genuine spec gap (not just unclear-to-you), STOP and surface to Kim before editing. Do not silently improvise.

### Context about prior sessions (so you know the lineage)

- **Session 1** (commit 23812d9): Vite+Preact+TS scaffold + 4 read-only tabs
- **Session 1.5** (commit b78da31): server scope guards on 13 handlers, `/api/state/snapshot`, `/api/event/load`, state file isolation lock
- **Session 2** (commit dcb0535): Touchpoint A flows + universal `pathappPatch` + storyboard export buttons
- **Session 2.5** (commit 024634f): Shared phase infrastructure + voice resolver + dynamic dropdowns
- **Session 2.7/2.9** (commit f496e92): Phase A + Phase B producer panels
- **Session 3 + 3.5 + 4 + 5** (commit 4f12421): Animate-this bridge + stitcher loudnorm + Production Map + StateManager isolation testing (which discovered the partition need)

S5.5 (a1, a2, b, c) are the closing bug-fix + architectural-cleanup sub-sessions before S6 (parallel-run on Event_2 + cutover).

### Begin

Run Phase 0 pre-flight now. Then execute spec v2 §4 Phases A–F in order. Report back when verification gates pass.

## PROMPT END

---

**Note to Kim:** This handoff is ~1100 words. The spec it references (v2) is the comprehensive doc. Terminal Claude doesn't need to re-derive context — just execute the spec.

When the terminal session reports back done, the next handoff will be S5.5a2 (migration application + handler refactor + scope token expansion). I'll write that one when you're ready.

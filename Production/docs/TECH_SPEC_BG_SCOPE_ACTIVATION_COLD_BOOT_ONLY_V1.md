# TECH_SPEC — Beat Gen Scope Activation Cold-Boot Only V1

**Status:** Implemented  
**Branch:** `fix/beatgen-category-fix-arc-v1`  
**Extends:** `TECH_SPEC_BEATGEN_JSON_MIRROR_UNION_BOOTSTRAP_V1.md`, `TECH_SPEC_BEATGEN_PER_EVENT_SQLITE_V1.md`, `test_bg_session_fast_get.py`

---

## 1. Category-unlocker

- **Bug category:** Read/write split violation — HTTP GET scope activation re-ran cold-boot sidecar reconcile under `_sidecar_lock`, convoying all `ThreadingHTTPServer` workers and freezing `/api/bg/session-state`.
- **Category fix:** Scope activation is **idempotent** — cold boot (SQLite bootstrap + JSON mirror union + Dropbox lock cleanup) runs **once per bound scope key**, not on every `assert_production_scope` → `activate_bg_for_scope` → `init_bg_paths`.
- **Fix type:** CATEGORY

---

## 2. Bottom-most root cause (5-level chain)

| Level | Why |
|-------|-----|
| 1 | Beat Gen stuck on "Loading beat state…" every refresh |
| 2 | `/api/bg/session-state` timed out; all worker threads blocked on `rlock_acquire` |
| 3 | Every BG GET called `init_bg_paths` → `reconcile_sqlite_segment_beats_from_json_mirror` → `mutate_sidecar_locked` |
| 4 | Prior fixes removed **other** writers from session GET (terminal reconcile, milestone repair) but not init reconcile |
| 5 | **Missing invariant:** cold-boot reconcile is for **startup / event swap / scope change** only — HTTP read handlers must not trigger sidecar writes |

JSON mirror union (I5) remains correct on **cold** paths. Warm GETs use already-bound SQLite authority.

---

## 3. Fix invariants (I8–I9)

### I8 — Scope key idempotency

Track `_BG_ACTIVE_SCOPE_KEY` after first cold bind:

- `milestone:{mdir}|lib:{library}` for milestone scope
- `event:{resolved_event_dir}` for dedicated event scope

When `init_bg_paths` is called with the **same** key and `cold_boot=False` (default): **skip** cold boot block (bootstrap, legacy import, mirror union, lock cleanup log spam). Path globals and creature refs already match.

When key **changes** (event/load, milestone enter/exit, first startup): run full cold boot.

Optional `cold_boot=True` forces re-union (restore scripts only).

### I9 — Session GET remains read-only for sidecar persistence

Unchanged contracts from prior specs:

- `handle_bg_session_state`: `repair_sidecar=False`
- `_enrich_beats_job_busy(..., session_read_only=True)`
- No `mutate_sidecar_locked` on warm `init_bg_paths`

---

## 4. Files

| File | Change |
|------|--------|
| `Production/tools/beat_generator.py` | Scope key, warm skip, `_run_bg_paths_cold_boot`, test reset helper |
| `Production/tools/tests/test_bg_scope_activation_cold_boot_only.py` | Behavior + contract tests |
| `Production/scripts/verify_bg_scope_activation_cold_boot_durability.sh` | CI/deploy grep gate |
| `Production/scripts/verify_storyboard_session_durability.sh` | Wire sub-guard |

---

## 5. Acceptance / proof

- [ ] Warm second `init_bg_paths` does not call `reconcile_sqlite_segment_beats_from_json_mirror`
- [ ] Scope change (Event_2 → Event_3) still runs cold boot
- [ ] Startup + event/load still union mirror beats (existing per-event sqlite tests green)
- [ ] Event_3 `:5113` session-state < 2s under 10 parallel GETs
- [ ] pytest + verify sub-guard green; commit on feature branch

---

## 6. Residual risks

| Risk | Mitigation |
|------|------------|
| Mirror edited on disk while server hot | Requires restart (cold boot) — same as before |
| Long writer still holds lock (O3 patch, char ref) | Separate from this class; session GET no longer adds reconcile writer |
| Test pollution across init calls | `reset_bg_paths_activation_for_tests()` |

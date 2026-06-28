# TECH_SPEC — Beat Gen JSON Mirror Union Bootstrap V1

**Status:** Implemented  
**Branch:** `fix/beatgen-per-event-sqlite-v1`  
**Extends:** `TECH_SPEC_BEATGEN_PER_EVENT_SQLITE_V1.md`, `BEATGEN_SIDECAR_SQLITE_AUTHORITY_SPEC_v1.md`

---

## 1. Category-unlocker

- **Bug category:** Monotonic beat-list durability — cold boot / event reload must never shrink segment beat count below the durable JSON mirror export.
- **Category fix:** JSON mirror union on init + event/load reconcile — SQLite wins for existing `beat_id`s; mirror fills missing draft rows only.
- **Fix type:** CATEGORY

---

## 2. Bottom-most root cause (5-level chain)

| Level | Why |
|-------|-----|
| 1 | Kim saw 6 beats after reload instead of 12 |
| 2 | Per-event SQLite had only 6 rows (O3 rehydrate subset) |
| 3 | `bootstrap_sqlite_sidecar_from_json()` skips import when `beat_count() > 0` |
| 4 | O3 rehydrate only runs on **empty** segments and only finds beats with disk clips |
| 5 | **Missing invariant:** beat list cardinality must be **monotonic** w.r.t. durable JSON mirror on every cold path **and on mirror export write** — partial SQLite is not authoritative |

Per-event SQLite (I1 from prior spec) fixed cross-event purge. This spec fixes **intra-event shrink** when bootstrap/rehydrate treat partial disk state as complete.

---

## 3. Fix invariants (I5–I6)

### I5 — JSON mirror union (never shrink)

On `init_bg_paths` (event scope) and `reconcile_event_sidecar_after_milestone_exit`:

1. Read durable JSON mirror at `BG_SIDECAR_PATH` (Dropbox export target).
2. For each segment matching loaded `Event_N`, union any `beat_id` present in mirror but missing from SQLite.
3. Preserve SQLite row for overlapping `beat_id` (live O3 state wins).
4. Copy segment meta from mirror (`beat_plan_draft`, `name`, …) when absent in SQLite segment.

### I6 — O3 rehydrate is enrichment-only for list cardinality

`rehydrate_segment_beats_from_o3_artifacts` remains for **empty** segments. Mirror union runs **before** rehydrate so draft rows exist; rehydrate then enriches disk options on existing rows via separate reconcile paths.

### I7 — Monotonic mirror export (never shrink on write)

`_merge_event_scoped_mirror` unions segment beats on export — SQLite wins overlapping `beat_id`; existing mirror rows are retained. Prevents partial SQLite from overwriting a fuller durable mirror during background export.

---

## 4. Files

| File | Change |
|------|--------|
| `Production/tools/beat_generator.py` | `merge_missing_segment_beats_from_json_mirror`, `reconcile_sqlite_segment_beats_from_json_mirror`; call on init + event/load |
| `Production/tools/tests/test_beatgen_per_event_sqlite.py` | Union + no-overwrite tests |
| `Production/scripts/verify_beatgen_per_event_sqlite_durability.sh` | Event_3 intro beats ≥ mirror count |

---

## 5. Acceptance / proof

- [ ] pytest union tests green
- [ ] Reproduce: partial DB (6 beats) + mirror (12) → cold restart → session-state = 12 **before manual heal**
- [ ] Browser hard refresh Event_3 intro shows 12 beats
- [ ] Milestone init still never calls bootstrap (`test_milestone_init_never_bootstraps_sqlite`)

---

## 6. Sibling categories still open

- Snapshot fallback when mirror is also stale (mirror empty but archive has beats)
- Automatic snapshot-on-write into per-event DB path from restore script migration
- UI warning when beat count drops vs last session (client-side)

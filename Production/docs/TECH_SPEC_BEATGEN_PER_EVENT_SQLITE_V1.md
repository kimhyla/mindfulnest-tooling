# TECH_SPEC — Beat Gen Per-Event SQLite V1

**Status:** Implemented  
**Branch:** `fix/beatgen-per-event-sqlite-v1`  
**Extends:** `BEATGEN_SIDECAR_SQLITE_AUTHORITY_SPEC_v1.md`, `TECH_SPEC_STITCH_SCOPE_PARTITION_V1.md`, `EVENT_LOAD_SIDECAR_RECONCILE_V1`

---

## 1. Category-unlocker

- **Bug category:** Storage scope collision — Beat Gen SQLite authority was **global** (one `beatgen.db` for all `Event_N`) while production topology is **event-dedicated servers** (`Event_2`→`:5112`, `Event_3`→`:5113`, …) plus milestone JSON sidecars. Reconcile on `event/load` **purged** other events' segment keys from the shared store.
- **Category fix:** Per-event SQLite files (`beatgen_eventN.db`) + purge **milestone pollution only** (non-numeric segment ids like `event_3b_full`) + merge export to global JSON mirror + O3 artifact rehydrate when segments are empty but clips/intents exist on disk.
- **Fix type:** CATEGORY

---

## 2. Greater root problem (why shared DB + cross-event purge existed)

Two independent decisions collided without a single storage/topology invariant:

| Decision | When / where | Intent |
|----------|----------------|--------|
| **W7 Global SQLite** | `BEATGEN_SIDECAR_SQLITE_AUTHORITY_SPEC_v1.md` §2 | Match legacy single-file JSON shape; one import; one mirror; fastest Dropbox-lock fix |
| **Dedicated event servers** | `TECH_SPEC_STITCH_SCOPE_PARTITION_V1.md`, launchd `:5110+N` | Isolate stitch scope, pin `Event_N` on port, reject cross-event `event/load` |
| **EVENT_LOAD_SIDECAR_RECONCILE_V1** | `event_video.handle_event_load`, Jun 2026 | After milestone work leaked `event_3b_full` rows into **event** SQLite, purge non-current-event segments on load |

Reconcile was written for **milestone pollution** (`event_3b_full`), but `purge_sidecar_segments_not_for_event` deleted **any** segment whose numeric id ≠ loaded event — including valid `event_3_pre` rows belonging to another production event.

**Compounding gaps:**

1. **Snapshots never captured Event_3** — `.production_snapshots` always showed `event_3_pre: 0`; restore path could not recover Event_3.
2. **No `_preserved` manifest for Event_3** — preserve runs on video-role switch within an event, not on dedicated-server refresh.
3. **`replace_full` guard** allows losing entire events if remaining beat count ≥ 60% of total (multi-event DB).

**Terminal cause:** Missing invariant — *storage partition key must match server partition key* (event-dedicated port ⇒ event-scoped beat store).

---

## 3. Fix invariants (I1–I4)

### I1 — Per-event SQLite authority

LaunchAgent env per dedicated server:

```text
MN_BEATGEN_DB_PATH=~/.mindfulnest/state/beatgen_event{N}.db
```

Bootstrap: empty per-event DB imports **only** matching segments from global JSON mirror; if still empty, copy rows from legacy `beatgen.db` for that event.

### I2 — Purge milestone pollution only

`purge_sidecar_segments_not_for_event` removes segments where event part is **non-numeric** (e.g. `3b` in `event_3b_full`). Numeric `event_3_pre` survives when Event_2 loads.

### I3 — Merge mirror export

Per-event DB export **merges** into global `Production/beat_generator_state.json` — updates only segments for that event; never wipes sibling events.

### I4 — O3 artifact rehydrate

When segment beats are empty, rebuild from `Event_N/arlo_o3_jobs/*_{intent,terminal}.json` + still-insert clips. Prefer **done** terminals with delivery over failed/newer intents. Runs on **`event/load` reconcile** and **server startup** (`run_server` after `init_bg_paths`).

### I5 — Strict `replace_full` guard (V1.1)

Any net beat loss on `replace_full` is **blocked** when the DB already has beats (`incoming_count < existing`). Override only via `MN_SIDECAR_ALLOW_FULL_REPLACE=1` (restore scripts).

### I6 — Deploy + CI gates (V1.1)

- `verify_beatgen_per_event_sqlite_durability.sh` wired into `verify_storyboard_session_durability.sh` (deploy path)
- `verify_production_server_launchagent_durability.sh` requires `MN_BEATGEN_DB_PATH` in install script
- GitHub CI: `beatgen-per-event-sqlite` pytest job (no live servers)

---

## 4. Files

| File | Change |
|------|--------|
| `Production/tools/beat_generator.py` | Per-event bootstrap filter, merge mirror, rehydrate, purge fix, legacy import, strict replace_full |
| `Production/tools/production_server.py` | Startup sidecar reconcile |
| `Production/scripts/install_production_server_launchagent.sh` | `MN_BEATGEN_DB_PATH` per event |
| `Production/scripts/verify_storyboard_session_durability.sh` | Calls beatgen per-event gate |
| `Production/scripts/verify_production_server_launchagent_durability.sh` | MN_BEATGEN_DB_PATH marker |
| `Production/tools/tests/test_event_load_sidecar_reconcile.py` | Cross-event purge regression |
| `Production/tools/tests/test_beatgen_per_event_sqlite.py` | Bootstrap, merge, rehydrate, replace_full, startup marker |
| `Production/scripts/verify_beatgen_per_event_sqlite_durability.sh` | Multipass gate |

---

## 5. Acceptance / proof

- [x] `pytest` reconcile + per-event tests green
- [x] Event_2 `:5112` session-state intro beats ≥ 1; DB = `beatgen_event2.db`
- [x] Event_3 `:5113` session-state intro beats = 6; DB = `beatgen_event3.db`
- [x] Event_4 `:5114` server up; DB path scoped
- [x] Global JSON mirror contains **both** `event_2_pre` and `event_3_pre` after Event_3 export
- [x] Hard refresh Beat Gen on Event_3 — beats remain (no empty state)
- [x] Startup reconcile runs before first GET (marker in `production_server.py`)
- [x] `replace_full` blocks any net beat drop
- [x] All six Event_N launchagents set `MN_BEATGEN_DB_PATH`

---

## 6. Residual risks (honest)

| Risk | Mitigation |
|------|------------|
| Operator explicit delete / extract replace | By design — not a persistence bug |
| Milestone scope on wrong server channel | Dedicated servers strip milestone scope (STITCH_SCOPE_PARTITION_V1) |
| Legacy `beatgen.db` on disk | Deprecated; live servers use `beatgen_eventN.db`; WARN if env unset |
| Segment empty with no disk artifacts | Rehydrate cannot invent beats — operator must extract/insert |

---

## 7. Operational notes

- **Restore Event_3 (2026-06-27):** Rehydrated 6 beats from disk artifacts into `beatgen_event3.db`.
- **Event_2 still+TTS / trims:** Preserved in Event_2 DB after legacy import; verify beat 15/19 on `:5112`.
- Reinstall launchagents after deploy: `bash Production/scripts/install_production_server_launchagent.sh Event_N`

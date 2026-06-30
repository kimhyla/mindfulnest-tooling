# TECH_SPEC_PARALLEL_EVENT_ISOLATION_V1

## Problem

Multiple dedicated storyboard servers (Event_11 on :5121, Event_13 on :5123, …) may run **simultaneously** while Kim works across tabs during Kling ordering waits. SQLite authority isolates hot Beat Gen writes per event, but **shared Dropbox `beat_generator_state.json` mirror export** and **all-events O3 startup reconcile** still contend on macOS CloudStorage → `Errno 11` crash loops and UI stalls (e.g. Stitcher “Loading stitch jobs…” for up to 120s).

## Goals

1. **Parallel tabs OK** — three+ events editing independently without cross-event sidecar fights.
2. **No fleet-wide cold-boot storm** — one event’s restart must not require reconciling every other event.
3. **Startup must retry transient Dropbox errno** — never fail-hard on first `Errno 11`.
4. **Backward compatible** — global Dropbox JSON remains bootstrap source; optional admin merge later.

## Design (PARALLEL_EVENT_ISOLATION_V1)

### A. Per-event local mirror (export target)

| Layer | Path | Role |
|-------|------|------|
| Authority | `~/.mindfulnest/state/beatgen_eventN.db` | Hot read/write (unchanged) |
| Bootstrap read | `Production/beat_generator_state.json` (Dropbox) | One-time SQLite import when DB empty |
| **Mirror export** | `~/.mindfulnest/mirror/beatgen_eventN.json` | Debounced export from SQLite — **not Dropbox** |

Set via launchagent env `MN_SIDECAR_MIRROR_PATH` (auto-derived from event slug when unset).

**Skip global merge on export** when isolated mirror is active — removes read-modify-write on shared Dropbox file during parallel work.

### B. Event-scoped startup reconcile

`run_blocking_o3_startup` calls `_run_o3_admin_reconcile(..., force=False)` so intent-lock heal runs for **this event only**, not every Event_N on disk.

Admin reconcile uses the same 12-attempt transient retry as `update_beat_locked`.

### C. Operator workflow

- **Normal:** keep launchagents running for every event tab you have open — parallel editing is supported.
- **Avoid:** `POST /api/server/restart` on all ports at once; deploy events sequentially; don’t boot Event_4–6 unless needed.
- **Hard-refresh all tabs at once** is tolerable after this spec (no shared mirror write), but sequential refresh is still gentler on CPU at cold boot.

## Verification

- `Production/scripts/verify_parallel_event_isolation_durability.sh`
- `pytest tests/test_parallel_event_isolation_v1.py`
- Meta gate pass 3 includes new durability script

## Non-goals (v1)

- Rebuilding global Dropbox JSON from per-event mirrors automatically (admin/export tool later).
- Removing global sidecar bootstrap path.

# BG session-state fast GET — spec v1

**Problem:** `GET /api/bg/session-state` takes 25–45s on Event_2 intro because each load synchronously scans Dropbox `kling_o3_clips/` for all 25 beats (`glob` + per-option `is_file`).

**Goal:** Session GET is SQLite-read + in-memory enrich only (<2s for 25 beats). Disk scans run in gallery repair / O3 finalize / explicit reconcile — not on every Beat Gen open.

## Category fix (not patch)

| Layer | Before | After |
|-------|--------|-------|
| **Persist** | Disk counts/exists only in API response (ephemeral) | `materialize_o3_disk_enrich_fields` writes counts + `*_exists` onto beat in SQLite during repair/select |
| **Session GET** | Full `enrich_beat_kling_o3_pinned` (disk) × N beats | `session_read=True` — copy persisted fields, no `glob`/`is_file` |
| **Job busy GET** | `observe_and_close_stale_o3_attempt` could `update_beat_locked` during GET | Read-only `beat_job_busy` annotation; heal on poll/repair only |

## Persisted beat fields (`BG_SESSION_DISK_ENRICH_V1`)

- `kling_o3_disk_delivery_count`, `kling_o3_orphan_delivery_count`
- `kling_o3_clips_dir`, `kling_o3_pinned_preserve`
- `kling_o3_video_path_exists`, `magic_video_path_exists`, `magic_still_path_exists`, `audio_file_exists`
- per-option `video_path_exists` on `kling_o3_options`
- `kling_o3_disk_enrich_at` (ISO timestamp)

**Writers:** `reconcile_o3_disk_deliveries_for_beat`, `_apply_o3_video_selection`, startup gallery repair (via reconcile).

## Agent debate 3×3 (pre-implementation)

### Round 1 — Correctness

| Pro fast GET | Con / risk | Resolution |
|--------------|------------|------------|
| SQLite is authority (P4) | Stale counts if repair never ran | Startup `schedule_o3_gallery_repair_at_startup` + persist on select; UI tolerates missing counts |
| Repair already scans disk outside lock | Orphan clips invisible until repair | Same as today; repair imports orphans — unchanged contract |
| `video_path_exists` on options from persist | User deletes file on disk manually | Select-o3 and poll still verify; missing badge when `=== false` only |

### Round 2 — Conflicts

| Area | Conflict | Resolution |
|------|----------|------------|
| `test_session_get_enriches_job_busy` | Must keep job_busy on GET | Keep `_enrich_beats_job_busy` but read-only (no `observe` persist) |
| `enrich_beat_kling_o3_pinned` used in poll/select | Poll needs fresh exists | Poll/select paths keep `session_read=False` (default) |
| `force_reconcile_o3=1` on GET | Still triggers disk reconcile thread | Unchanged; not default idle GET |

### Round 3 — Durability

| Check | Evidence required |
|-------|-----------------|
| Unit | `session_read` does not call `list_o3_element_delivery_paths_on_disk` |
| Unit | `materialize_o3_disk_enrich_fields` sets counts after reconcile |
| Integration | `session-state` wall time <5s after repair (curl) |
| UI | Beat Gen loads beats; beat 4 shows g7; disk banner when counts present |

## Out of scope (follow-up)

- Lazy per-beat disk endpoint for Finder path refresh (optional; repair + select sufficient for v1)
- Moving `production_state.read_state()` off session hot path (separate if still slow)

## Implementation note (post-debate)

Session GET must also skip `refresh_o3_ui_slot_layout` — it calls `migrate_o3_options_edge_cut_to_trim`, which runs `_ffprobe_duration` per gallery option (was ~0.7s/beat on Dropbox). Labels are persisted during gallery repair / select-o3.

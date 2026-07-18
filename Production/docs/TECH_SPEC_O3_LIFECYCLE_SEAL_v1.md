# O3 Lifecycle Seal — Tech Spec v1

**Status:** Implementing  
**Owner:** mindfulnest-tooling  
**Supersedes/amends:** `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` §6.1 (session GET), `TECH_SPEC_BG_SESSION_READ_PATH_COMPLETION_v1.md` I-GET-2  
**Incident class:** Beat 2 g3 — Kling ok, delivery encode failed, manual recovery reverted by session GET

## 3×3 debate synthesis

| Agent | Lane | Vote |
|-------|------|------|
| A — Lifecycle | Atomic close + pointer-only job id | `close_o3_attempt` sole closer; kill log-path lifecycle binding |
| B — Session GET | Read-only gallery | Remove `compose_session_terminal_view` from hot GET; wire `_apply_o3_session_terminal_reconcile` at startup |
| C — Write path | Master-or-orphan-before-failed | L1 staging done; seal recovery before terminal `failed` when master exists |

## Problem class (P0)

**Symptom:** Paid clip appears, play works briefly, then gallery reverts + failure toast on refresh.

**Root chain:**
1. ffmpeg delivery encode fails on Dropbox (L1 staging now prevents new cases)
2. Terminal `failed` written with `sidecar_persist_ok: false` — pointers not cleared atomically
3. Sidecar retains `o3_current_job_id` + `kling_o3_voice_fix_job_log_path`
4. Session GET resolves job from log path → re-runs `restore_last_good` → downgrades gallery
5. Client toasts stale `failed` terminal on every refresh

## Five structural fixes

### F1 — Write path (prevention)
- **Done:** `video_delivery.encode_delivery_video` stages locally (`local_staging_temp_path` → `commit_local_file_to_dest`)
- **New:** `seal_o3_recovery_before_terminal()` — delivery on disk → orphan recover; master only → `done_with_warning`; else `failed`
- **New:** Pipeline `main()` uses `close_o3_attempt` not raw `write_intent_terminal` on failure

### F2 — Atomic job close
- `_clear_o3_job_metadata` clears full `O3_JOB_CACHE_FIELDS` via `clear_o3_job_cache_fields`
- All closed terminal writes route through `close_o3_attempt(persist_beat=True)`

### F3 — Single lifecycle authority
- `resolve_o3_job_id_for_lifecycle`: `o3_current_job_id` → optional `kling_o3_voice_fix_ui_job_id` (spawn only)
- **Removed from lifecycle:** log-path regex (`job_id_from_beat` retained as `job_id_from_beat_legacy_reconcile` for admin only)

### F4 — Session GET read-only gallery
- Default GET: sidecar gallery + derived `job_busy` only
- `o3_terminal_outcomes: []` on default GET
- Terminal/disk heal persists at **startup** via `_apply_o3_session_terminal_reconcile`

### F5 — Recovery seals lifecycle
- Startup/admin/poll write paths persist gallery before clearing busy
- Client toasts gated on `persisted: true` in outcome rows

## Acceptance criteria

| ID | Criterion | Proof |
|----|-----------|-------|
| AC-1 | Log-path-only beat does not bind failed terminal on session GET | Unit: `test_lifecycle_ignores_log_path_only` |
| AC-2 | Default session GET does not call `compose_session_terminal_view` | Grep gate + unit |
| AC-3 | Startup runs terminal reconcile persist | Log `[startup:o3-terminal-reconcile]` + unit |
| AC-4 | Beat 2 g3 fixture: failed terminal + stale pointers + recovered delivery → GET stable | Integration fixture |
| AC-5 | `encode_delivery_video` never writes under CloudStorage | Existing `test_ffmpeg_io_cloud_staging.py` |
| AC-6 | Client ignores non-persisted session outcomes | TS unit |
| AC-7 | `restore_last_good` does not call `refresh_o3_ui_slot_layout` | Grep gate |

## Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| In-flight poll | Low — poll uses explicit job_id | Unchanged |
| Admin reconcile | Uses legacy log matcher | `job_id_from_beat_legacy_reconcile` |
| Tab-sleep orphan | Medium — GET won't project disk | Startup `_apply` + poll persist |
| Milestone library clips | Existing event dir candidates | Startup reconcile uses same candidates |
| Stitch export | Master-only never approved | Seal contract |

## Implementation phases

1. P1: `o3_job_status_contract` pointer-only + gate failed heal  
2. P2: Session GET read-only + startup terminal reconcile wire  
3. P3: `o3_recovery_seal` + pipeline `close_o3_attempt` on failure  
4. P4: Client toast gate + outcome `persisted` field  
5. P5: Contract tests + durability scripts + live proof on Event_6 beat 2

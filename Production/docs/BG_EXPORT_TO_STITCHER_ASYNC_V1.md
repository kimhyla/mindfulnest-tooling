# BG_EXPORT_TO_STITCHER_ASYNC_V1 — async Send to Stitcher job truth

**Status:** Implemented (post 3×3 agent debate, 2026-06-22)  
**Scope:** Beat Gen `Send Beat Gen to Stitcher` → `/api/bg/export-to-stitcher`  
**Proof target:** Event_2 intro (`http://127.0.0.1:5112/?event=Event_2`)

## Problem class

Sync POST held the HTTP connection open for 3–5+ minutes (materialize + concat + stitch upsert). Server restart, port-guard, or deploy dropped the connection → client toast `TypeError: Failed to fetch` even when export logic was fine. Prior fixes (ffmpeg Dropbox staging, trim durability) addressed **server-side ffmpeg** failures, not **connection lifetime**.

## Category fix

Mirror **STITCH_BAKE_JOB_TRUTH_V1**:

| Layer | Deliverable |
|-------|-------------|
| Job store | `bg_export_stitcher_job_store.py` — `{event_dir}/bg_export_stitcher_jobs/{job_id}.json` |
| Lock | `{event_dir}/bg_export_stitcher_jobs/export.lock` (flock; one export per event) |
| POST | Validate + trim seed sync → **202** `{ job_id, submitted }` or **200** `{ reattach }` |
| Worker | Daemon thread: materialize → concat → `stitch_upsert_event_slot` → Directus |
| Poll | **GET** `/api/bg/poll-export-to-stitcher?job_id=` → progress + terminal result |
| Client | `bgExportToStitcherJobTruth.ts` + BgTab poll loop + sessionStorage latch |

## Scope key (dedupe / reattach)

`{arc_number}|{bg_event_id}|{phase}|{slot_key}` — includes BG segment `event_id`, not only `scope_event_id`.

## Pin contract (LD-460)

- POST: `_check_event_pin` pre-work → 423 `EVENT_CHANGED_PRE_WORK`
- Worker terminal: `_check_event_pin` before `stitch_upsert_event_slot` + sidecar mutate → failed job `EVENT_CHANGED_MID_JOB`

## Progress

- `beat_index` / `beat_total` during materialize (optional callback in `resolve_segment_stitch_export_clip_paths`)
- Phases: `queued` → `materialize` → `concat` → `upsert` → `directus` → `done`

## 3×3 debate outcomes (integrated)

1. **Scope key** must include BG segment `event_id` — adopted.
2. **Beat snapshot** via `beat_ids[]` on job record — adopted.
3. **Trim seed/migrate** stays sync in POST before 202 — adopted.
4. **409 EXPORT_ALREADY_IN_PROGRESS** when lock held and no reattach job — adopted.
5. **Poll endpoint** in READ catalog only — adopted.
6. **Client success** on poll terminal `done`, not POST body — adopted.

## Verification

- `pytest tests/test_bg_export_stitcher_job_truth.py tests/test_intro_export_api_contract.py -v`
- `node --experimental-strip-types --test src/utils/__tests__/bgExportToStitcherJobTruth.test.ts`
- POST 202 + poll until done; intro MP4 on disk + stitch slot updated
- Browser: Beat Gen button shows progress; no Failed to fetch on restart during poll

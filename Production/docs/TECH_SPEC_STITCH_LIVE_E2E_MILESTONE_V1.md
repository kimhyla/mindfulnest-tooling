# TECH_SPEC_STITCH_LIVE_E2E_MILESTONE_V1

**Extends:** `TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1.md`, `STITCH_LOAD_JOB_PLAYBACK_BAKE_V1`  
**Scope:** Post-deploy Playwright gate `stitch_sfx_playback_truth_live.spec.ts` only — not app runtime.

## Problem

Deploy step `(g.4)` fails intermittently after Event_2 `load_job` auto-bake ships:

1. **Server contention** — milestone `GET /job/milestone_*_stitch` blocks behind Event_2 `load_job` (~2 min first heal).
2. **Wrong assertion surface** — E2E required `saved_video_path` on every `POST /job`, including sfx-only merges (server contract: merge preserves prior `video_path`; response field is standalone convenience, not merge echo).
3. **Wrong mux truth surface** — test inferred mux readiness from `<video src>` only; job API `mux_preview_hash` is the durable source of truth (`handle_stitch_preview` persist).
4. **Fixture drift** — failed runs left milestone `standalone` with no `video_path`; cleanup cascaded into more failures.

## 3×3 debate (architecture-simplifying verdict)

| Option | Verdict |
|--------|---------|
| **A — Server: auto-bake mux on milestone save** | Rejected — duplicates client preview queue; violates single-owner (preview builds mux). |
| **B — Server: load_job hydrate for milestone** | Already shipped (`63d1fed`); not an E2E-only fix. |
| **C — Split deploy gate to separate job** | Rejected — adds process/orchestration; doesn't fix test contract. |
| **D — E2E: tiered save asserts + job-API mux poll** | **Accepted** — test matches existing server contract; no new endpoints. |
| **E — E2E: one fixture helper (`ensureMilestoneStandaloneVideo`)** | **Accepted** — single bootstrap owner; beforeAll/afterEach reuse. |
| **F — Deploy script: warm Event_2 load_job before Playwright** | **Accepted** — one serialized curl drains bake queue; simpler than test retries. |

**Principle:** Live E2E asserts **durable job state** (same store as production UI refresh), not incidental POST response fields or DOM-only signals.

## Contract (E2E)

### `postStandaloneSlots`

| Payload intent | Assert |
|----------------|--------|
| Always | HTTP 200, `job_persisted === true` |
| Includes `video_path` | `saved_video_path` non-empty |
| SFX / cue-only merge | Read-back `GET job` → `standalone.video_path` non-empty (lineage preserved) |

### Mux after SFX drop

Poll `GET job` → `standalone.mux_preview_hash` (≥8 hex chars, ≠ prior hash) with 180s budget — same field Stitcher refresh uses.

### Fixture

`ensureMilestoneStandaloneVideo(request)` — idempotent POST bootstrap from `Milestones/milestone1_arc1/assembled/standalone_*.mp4`. Used in `beforeAll` (then `ensureMuxPreviewReady`) and `afterEach` restore.

### Deploy warmup (`verify_stitch_sfx_playback_truth_live_e2e.sh`)

Before Playwright: `GET /api/stitch_editor/job/Event_2_stitch` with 300s max — drains auto-bake so milestone job GET is not blocked.

## Proof

- `npx playwright test e2e/stitch_sfx_playback_truth_live.spec.ts --config playwright.live.config.ts`
- Full deploy `(g.4)` green on `:5112`

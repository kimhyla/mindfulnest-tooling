# TECH_SPEC_STITCH_SLOT_EDIT_DISPATCH_V1

**Status:** LOCKED (Layer 4 — tiered save dispatch)  
**Token:** `STITCH_SLOT_EDIT_DISPATCH_V1`  
**Supersedes:** implicit “every save rebuilds all ambient tiers” behavior only; does **not** remove client guards from Layers 1–3.

---

## 1. Problem (Layer 4)

`stitch_save_job` persisted editorial JSON **and** synchronously rebuilt derived artifacts for unrelated tiers. SFX-only edits triggered full ambient ffmpeg (~94s slot) before HTTP 200, then client queued mux ffmpeg — two pipelines, one endpoint.

**Missing invariant:** geometry change invalidates only artifact tiers that depend on that geometry.

---

## 2. Goals

| Edit | Persist JSON | Ambient rebuild | Mux rebuild |
|------|--------------|-----------------|-------------|
| SFX drop/drag | ✓ sync | skip if ambient sig fresh | client async `stitch_preview` |
| Ambient dropdown | ✓ sync | ✓ sync (drift or missing artifact) | client async if SFX |
| Beat Gen export | ✓ via `stitch_upsert_event_slot` | on next ambient save | client if SFX |
| Trim / metadata | ✓ sync | skip unless ambient drift | client if SFX |

---

## 3. Non-goals

- Removing client instant-UI markers (`STITCH_SFX_DROP_INSTANT_V1`, `STITCH_SFX_RANGE_INSTANT_V1`, waveform stable, stale-while-revalidate).
- Async ambient bake in background thread (future); v1 still sync ffmpeg but **only on ambient drift**.
- Mux on save (remains `stitch_preview` only).

---

## 4. Architecture

### 4.1 Server (`stitch_slot_edit_dispatch.py`)

- `ambient_tier_drifted` — video path, ambient bed, volume, ambient sig
- `sfx_tier_drifted` — sorted cue geometry
- `slot_needs_ambient_rebuild` — drift OR missing/stale `se_slot_{hash}.mp4`
- `plan_stitch_save_dispatch` — returns `ambient_rebuild_keys`, `ambient_skip_keys`, `mux_rebuild_hint_keys`

### 4.2 `handle_stitch_save_job`

1. Snapshot `prev_slots` before mutate  
2. Persist JSON via existing upsert  
3. Read `next_slots` after mutate  
4. `dispatch = plan_stitch_save_dispatch(...)`  
5. `rebuild_stitch_ambient_mixes_for_job(h, name, slot_keys=dispatch["ambient_rebuild_keys"])` — **explicit list**; empty list skips all ambient ffmpeg  
6. Response adds `edit_dispatch` block  

### 4.3 Client

- `inferStitchEditKind(prev, next)` → sends `edit_kind` hint on save (telemetry + tests)
- Existing mux queue on geometry change unchanged
- Layers 1–3 markers remain

---

## 5. 3×3 debate (summary)

| Agent | Position | Verdict |
|-------|----------|---------|
| A1 Server | Authoritative drift from prev/next slots, not client hint alone | **Accepted** |
| A2 Server | Empty `slot_keys=[]` must skip ambient loop (not “all slots”) | **Accepted** |
| A3 Client | Keep instant UI + refresh local cues; dispatch is server-side | **Accepted** |
| B1 QA | E2E must bootstrap milestone video via explicit POST (single-owner) | **Accepted** |
| B2 QA | Deploy gate fails on empty job — fix E2E bootstrap, not load_job hydrate | **Accepted** |
| B3 UX | Mux still async; operator hears SFX after preview completes | **Accepted** |
| C1 Tests | pytest dispatch plan + empty slot_keys + client infer kind | **Accepted** |
| C2 Durability | grep markers + verify script pre-deploy | **Accepted** |
| C3 Regression | Do not remove STITCH_AMBIENT_BAKE_SKIP_UNCHANGED inner guard | **Accepted** (belt+suspenders) |

---

## 6. Proof

- `test_stitch_slot_edit_dispatch.py`
- `stitchSlotEditDispatch.test.ts`
- `verify_stitch_slot_edit_dispatch_durability.sh`
- Live E2E bootstrap when `video_path` missing but `assembled/standalone_*.mp4` exists

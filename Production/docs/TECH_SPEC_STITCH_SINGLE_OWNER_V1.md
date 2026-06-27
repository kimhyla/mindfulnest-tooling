# TECH_SPEC — Stitch Single Owner V1

**Status:** Implementing  
**Branch:** `fix/build-sha-drift-banner`  
**Supersedes:** load-time disk hydrate as write path (A6 in `TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1`)  
**Extends:** `TECH_SPEC_STITCH_TRUTH_CONTRACT_V2.md`, `TECH_SPEC_MILESTONE_BEATGEN_INTEGRATION_v1.md`

---

## 1. Purpose

End the split between **pipeline disk** (`assembled/*.mp4`), **editorial JSON** (`stitch_state.json`), and **client playback cache**. After Beat Gen / Phase export, **Stitcher owns the slot** — one record, one store, one load path.

---

## 2. Causeless cause

> **Stitcher had multiple writers for the same slot.**  
> Beat Gen export, `load_job` disk hydrate, client `previewUrls`, and preview persist each could mutate overlapping fields without a single ownership rule.

---

## 3. Invariant (STITCH_SINGLE_OWNER_V1)

| Layer | Role after export |
|-------|-------------------|
| **`stitch_state.json` → job slot** | **Sole authority** for `video_path`, `sfx_cues`, ambient, artifact pointers |
| **`assembled/*.mp4`** | **Input file only** — written by Beat Gen; read by **`stitch_upsert_event_slot`** (Send to Stitcher), never by `load_job` persist |
| **Mux MP4 on disk** | **Derived cache** — built from slot geometry; pointers in JSON |
| **Client `previewUrls` / session** | **Performance cache only** — must not outrank server job on reload |

### 3.1 load_job contract (read-mostly)

- **`GET /api/stitch_editor/job/<name>`** returns persisted job from the correct store (`stitch_state_store_for_job`).
- **MUST NOT** `mutate_state` to bootstrap from `assembled/` or event export folders.
- **Milestone, job missing:** return **ephemeral** empty `{ slots: { standalone: {} } }` in the response — **do not persist** until `stitch_save_job` or export upsert.
- **Event, job missing:** `404` (unchanged).

### 3.2 Write paths (only these persist video + editorial)

| Path | When |
|------|------|
| `stitch_upsert_event_slot` | Beat Gen Send to Stitcher, Phase A/B export, operator export |
| `stitch_save_job` | Operator SFX / ambient / trim edits |
| `handle_stitch_preview` | Geometry persist + mux artifact pins (must not wipe non-empty `sfx_cues` with empty preview payload) |
| `load_job` heal | **Only** for slots **already persisted**: timeline dur, artifact validation, canonical audio defaults |

### 3.3 Disk hydrate functions (retained, demoted)

`hydrate_milestone_standalone_from_disk` and `hydrate_stitch_canonical_slots_from_disk` remain for:

- Unit tests / migration scripts
- **Not** called from `handle_stitch_load_job` with `mutate_state`

---

## 4. Blast radius

| Change | Impact | Mitigation |
|--------|--------|------------|
| No milestone hydrate on load | Cold open without prior export shows empty standalone until Send to Stitcher | Product intent; export is the handoff |
| No event hydrate on load | Partial event jobs no longer auto-fill empty intro/phase from disk on GET | Slots fill via Phase export / Beat Gen (already canonical) |
| Ephemeral milestone job | First GET before save returns empty slot without creating `created_at` row | Save or export creates row |
| Operators with wiped `stitch_state` | No silent recovery from `assembled/` on refresh | Re-send to Stitcher or restore backup |

**Out of scope:** Web Audio real-time SFX; removing client preview cache entirely (Phase 2 — server job remains authority).

---

## 5. Implementation map

| File | Change |
|------|--------|
| `server_handlers/stitch_editor.py` | `STITCH_SINGLE_OWNER_V1`; remove load_job hydrate/bootstrap persist; gate load heal persist on `job_persisted` |
| `StitcherTab.tsx` | `data-stitch-single-owner` marker; load uses server job only (existing merge + stale-while-revalidate) |
| `test_stitch_single_owner.py` | load_job does not persist hydrate; export upsert still writes |
| `verify_stitch_single_owner_durability.sh` | deploy gate source guards |
| `check_storyboard_critical_features.sh` | grep marker |

---

## 6. Multipass proof plan

| Pass | Proof |
|------|-------|
| **Repro** | Delete milestone job row → `load_job` → disk regains hydrate row with 0 cues (pre-fix) |
| **Unit** | pytest `test_stitch_single_owner.py` |
| **API post-fix** | Delete job row → `load_job` → disk **unchanged**; response ephemeral empty or existing |
| **Export** | `stitch_upsert_event_slot` still sets `video_path` on milestone store |
| **Deploy** | `deploy_storyboard_v59.sh --event Event_2` exit 0; `build-sha` = git HEAD |
| **Browser** | Hard refresh milestone Stitcher; SFX cues survive reload; resize keeps video (stale-while-revalidate) |
| **Dedicated port** | `:5112` `event/load` wrong event → 409 |

---

## 7. 3×3 debate summary

| Agent | Position | Resolution |
|-------|----------|--------------|
| A1 Server | load_job read-only for pipeline disk | **Adopt** |
| A2 Server | Keep hydrate for migration only | **Adopt** |
| A3 UX | Empty slot until export is honest | **Adopt** — Kim confirmed ownership model |
| B1 Client | Thin cache over server job | **Partial** — merge on load shipped; full previewUrls removal deferred |
| B2 QA | Repro test with disk before/after | **Adopt** |
| B3 Deploy | Gate + live milestone E2E | **Adopt** |
| C1 | Risk: broken cold-start | Export path documented; no silent hydrate |
| C2 | Risk: list-slot wipe recurrence | Separate guard (`_coerce_stitch_save_slots_to_dict`) |
| C3 | Risk: split-brain video/cues | Stale-while-revalidate + single owner load |

**Verdict:** Server load read-only + export-only video ingest + existing client merge/stale-while-revalidate.

---

## 8. Sibling categories

| Category | Status |
|----------|--------|
| List-shaped slots wipe | Closed (`normalize_milestone_stitch_job` coerce) |
| Client previewUrls stale-while-revalidate | Closed (same branch) |
| Preview persist empty sfx wipe | Closed (`_persist_stitch_preview_slot_geometry` guard) |
| Client previewUrls as sole authority | **Open** (Phase 2) |
| Milestone SQLite on init | Unrelated — do not touch in this spec |

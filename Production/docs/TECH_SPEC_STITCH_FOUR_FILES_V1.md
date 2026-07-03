# TECH_SPEC — Stitch Four Files v1 (STITCH_FOUR_FILES_V1)

**Status:** Draft v1.1 — 4-agent debate complete; pending Kim approval before Full QA implementation  
**Reviews:** Adversary [b636c2c7](b636c2c7-c8ca-4540-90c2-a6bba9603110) · Advocate [5d3b5fe1](5d3b5fe1-0a38-4547-b748-5b2c005d09ca) · Durability [f85a99e0](f85a99e0-5f7f-4be0-b63f-c9e10e9eacb2) · Blast radius [b43d2674](b43d2674-c311-49b9-801b-652707cefdb1) — all **APPROVE WITH CONDITIONS** (incorporated below)  
**Marker:** `STITCH_FOUR_FILES_V1`  
**Branch (implementation):** `feat/stitch-four-files-v1` (from current tooling HEAD)  
**Parent registry:** `STORYBOARD_AUTHORITY_REGISTRY_v1.md`  
**Supersedes (partial):** `TECH_SPEC_STITCH_AMBIENT_BAKE_V1` artifact ladder (§4.1 dry → se_slot → mux); `STITCH_MUX_INTERIM_DRY_VIDEO_V1`; load-job playback auto-bake as operator hot path  
**Extends:** `FAST_AND_FLAWLESS_DONE_v1.md` (adds **FF-036** — not FF-028; FF-028 is O3 failed-redo heal)  
**Trigger:** Event_4 resolution — lipsync drift perception, missing beat boundaries, triple playback artifacts (dry / ambient_mix / mux_preview), operator demand for “four MP4s, play instantly, persistent after first export.”

**Goal:** One playback authority per stitch slot. **Send to Stitcher** and **slot rebake** produce a single baked MP4 (`video_path`) containing speech + ambient bed + canonical SFX (+ operator SFX). Stitcher review serves that file directly. **Bake Final** concatenates the four slot `video_path` files only. No parallel preview cache graph for event slots.

---

## 0. Operator contract (Kim — non-negotiable)

| Rule | Detail |
|------|--------|
| Four containers | intro, phase_a, phase_b, resolution — unchanged |
| Beat Gen export | N beats → **one** flattened concat MP4 per slot (already true) |
| Playback | Composer plays **`slot.video_path`** — same bytes as Bake Final input |
| Ambient | Auto-applied from per-slot defaults on first export; editable via dropdown → **one slot rebake** |
| SFX | Canonical defaults auto-applied; operator may add → **one slot rebake** |
| Empty slot | No export yet → container empty; no ffmpeg, no fallback URL |
| Review | No remux on load, tab switch, or hard refresh |
| Bake Final | Fades + concat four slot `video_path` → canonical module MP4 |

> **`video_path` is playback is bake input** — or the operation fails closed.

---

## 1. Category-unlocker

| Item | Value |
|------|-------|
| **Bug category** | Split playback authority — dry export, `se_slot_*`, `stitch_preview_*`, hash resolver, load_job heal |
| **Category fix** | Single `stitch_slot_playback_mp4` concept; one bake on write; direct file serve |
| **Fix type** | CATEGORY — all events, all ports :5111–5116+, milestone jobs scoped separately |
| **Blast radius** | Event stitch jobs, BG Send to Stitcher, Phase A/B export upsert, stitch_save_job, composer URL resolver, module bake pipeline, cache sweep rules, ~40 tests referencing ambient_mix/mux_preview |

---

## 2. Architecture (target)

### 2.1 Pipeline

```
[Beat Gen / Phase export]
  per-beat flatten → concat → dry slot MP4 (scratch, optional retain for debug)
       ↓
  bake_slot_playback_mp4(dry, ambient, sfx) → slot_playback MP4
       ↓
  atomic upsert: slot.video_path = playback MP4, video_dur_ms, beat_boundaries

[Stitcher review]
  GET /files/…/video_path  (byte-range) — no cache tier selection

[Operator edit ambient or SFX]
  stitch_save_job → rebake_slot_playback_mp4 → update video_path (new file, atomic mutate)

[Bake Final]
  concat(slot.video_path × 4) + transitions → M{n}_event_{n}_final.mp4
```

### 2.2 Retired for event slots

| Retired | Replacement |
|---------|-------------|
| Composer dry / ambient_mix / mux URL resolver | Always `video_path` |
| `ensure_stitch_slot_playback_artifacts` on **load_job** | Read-only load; no bake |
| `POST stitch_preview` for event slot review | Only if legacy client during migration window |
| `ambient_mix_hash`, `mux_preview_hash` as playback authority | Optional legacy fields cleared on migrate; not read for playback |
| `se_slot_{hash}.mp4` hot path | Orphan after sweep; no new writes |
| `stitch_preview_{hash}.mp4` hot path | Same |

**Milestone standalone jobs:** May keep simplified single-file path; event four-slot jobs are primary scope.

---

## 3. New authority concept — FF-036 `stitch_slot_playback_mp4`

| | |
|--|--|
| **Question** | Which file does Stitcher play and Bake Final read for this slot? |
| **Shape** | disk |
| **Invariant** | `slot.video_path` ffprobe-playable; duration = `slot.video_dur_ms`; contains speech + configured ambient + all `sfx_cues` |
| **Read gate** | `resolve_slot_playback_path(slot) -> Path` → `video_path` only |
| **Write gate** | `bake_and_persist_slot_playback_mp4(h, job_name, slot_key)` — sole writer after export/save |

**Module:** `Production/tools/server_handlers/stitch_slot_playback.py` (new)

**Behaviors:**

1. **`bake_slot_playback_mp4(h, slot, *, dry_video_path: Path, dest: Path) -> float`**
   - **Input MUST be dry concat** (speech-only export) — never an already-mixed `video_path` (prevents double ambient/SFX)
   - Mix: reuse `_stitch_mix_slot_audio(dry, slot, …)` — `-map 0:v -c:v copy` + amix speech + bed + SFX
   - If slot has **no** ambient and **no** SFX: atomic copy dry → dest (no ffmpeg mix)
   - Post: `ensure_mp4_playback_timestamps`, `av_duration_drift_s` ≤ `STITCH_EXPORT_AV_MAX_DRIFT_S`
   - Returns duration seconds

2. **`bake_and_persist_slot_playback_mp4(h, job_name, slot_key, *, dry_video_rel, slot_patch, beat_boundaries, stitch_store)`**
   - Writes `Production/{Event}/assembled/{slot_key}_playback_{utc}.mp4`
   - **Single `mutate_state` only** (G7): `video_path`, `video_dur_ms`, `beat_boundaries`, `playback_recipe_version`, ambient/SFX fields, clear legacy artifact fields — **no second mutate** for artifacts
   - Fail closed: if bake fails, **prior slot unchanged**
   - Optional retain: `dry_export_path` on slot (debug/audit only; never used for rebake input)

3. **`resolve_slot_playback_path(slot) -> str`**
   - Returns `slot["video_path"]` or raises `StitchPlaybackMissingError`

4. **Deprecation shims (one release):**
   - `attach_stitch_slot_derived_media_urls` sets `_playback_url` from `video_path` only
   - Old hash fields ignored with logged `STITCH_FOUR_FILES_MIGRATE_V1` once per slot

---

## 4. Wire points (mandatory)

| Call site | Change |
|-----------|--------|
| `kling_o3.py` `_run_bg_export_stitcher` | After concat: `bake_and_persist` with dry path; upsert uses **baked** path as `video_path` |
| `stitch_upsert_event_slot` | Remove `ensure_stitch_slot_playback_artifacts_on_export` sidecar bake; caller passes already-baked path OR upsert invokes bake inline before persist |
| `handle_stitch_save_job` | On ambient/SFX geometry change: rebake → new `video_path` |
| `handle_stitch_load_job` | **No** `ensure_stitch_slot_playback_artifacts`; validate `video_path` exists + playable only |
| `production_server._stitch_mix_slot_audio` | Unchanged filter graph; called from `bake_slot_playback_mp4` |
| `stitchJobMediaHydrate.resolveSlotPlaybackPreviewUrl` | Return `resolveDrySlotSourceVideoUrl(slot.video_path)` when path set; never mux hash URLs for event slots |
| `stitchSlotRequiresMuxedPreview` / `stitchSlotRequiresAmbientMix` | Event slots: **always false** for composer blocking |
| `handle_stitch_bake` / `_stitch_build_pipeline` | **Passthrough mode** when `playback_recipe_version === STITCH_FOUR_FILES_V1`: skip normalize, loudnorm, `_stitch_mix_slot_audio`; concat + transitions only |
| `stitch_artifact_build.py` + `rebuild_stitch_ambient_mixes_for_job` | Route save-triggered rebuilds to `bake_and_persist` (dry from `dry_export_path` or re-export required) — not `se_slot_*` / `mux_preview_*` writers |
| `stitchSlotTimelineDurMs` (client) | Use `video_dur_ms` only; stop preferring `mux_preview_duration_ms` |
| `stitchArtifactBuildPoll.ts` | Completion = `playback_recipe_version` + playable `video_path`; not `mux_preview_hash` poll |
| `stitch_sfx_playback_truth_live.spec.ts` | Rewrite: truth = `/files/…video_path` HTTP 200, not mux hash URL |
| `authority_registry.py` | Add FF-036 row |
| `FAST_AND_FLAWLESS_DONE_v1.md` | Add FF-036 checklist |

---

## 5. Slot state shape (after migrate)

```json
{
  "video_path": "Production/Event_4/assembled/resolution_playback_20260701T180000Z.mp4",
  "video_dur_ms": 47397,
  "playback_recipe_version": "STITCH_FOUR_FILES_V1",
  "ambient_bed_path": "Production/Event_4/ambien bed pretty option4.mp3",
  "ambient_volume": 0.15,
  "sfx_cues": [],
  "beat_boundaries": [{"beat_id": "…", "start_ms": 0, "end_ms": 6333, "duration_ms": 6333}]
}
```

**Removed from write path (legacy read ignored):** `ambient_mix_hash`, `ambient_mix_video_path`, `mux_preview_hash`, `mux_video_path`, `mix_sig`, `ambient_mix_sig`.

---

## 6. Fail-closed gates

| Gate | When | Threshold / action |
|------|------|-------------------|
| G1 Export concat | BG Send to Stitcher | `assert_stitch_export_assembled_av_drift` ≤ 50ms |
| G2 Playback bake | After ambient+SFX mix | `av_duration_drift_s` ≤ 250ms |
| G3 Upsert atomicity | `mutate_state` | No partial slot if G2 fails |
| G4 Load job | `load_job` | Missing `video_path` → slot marked empty, warning — no dry fallback |
| G5 Composer | Client | No URL unless `video_path` set and file 200 from `/files` |
| G6 Bake Final | Pre-concat | All four slots have playable `video_path` or fail with slot list |
| G7 Boundaries | Export upsert | `beat_boundaries` written in **same** mutate as `video_path` |
| G8 Rebake input | save/export rebake | ffmpeg input = `dry_export_path` or fresh concat — **never** current mixed `video_path` |
| G9 Module bake | Bake Final | Slots with `playback_recipe_version` skip normalize/loudnorm/mix (passthrough) |
| G10 Bake Final slots | Pre-bake | **Filled** slots only must have playable `video_path`; empty slots allowed |

---

## 7. Multipass verification (every stage)

### Stage A — Unit (pytest)

| Test file | Contract |
|-----------|----------|
| `test_stitch_four_files_playback_authority.py` | bake → video_path; drift gate; atomic upsert |
| `test_stitch_four_files_load_job_readonly.py` | load_job does not call bake |
| `test_stitch_four_files_save_rebake.py` | SFX add → new video_path, old hash fields absent |
| `test_stitch_four_files_client_resolver.py` | resolveSlotPlaybackPreviewUrl = files URL only |
| `test_stitch_four_files_module_bake.py` | module bake does not double-mix ambient |
| `test_stitch_four_files_migrate_legacy.py` | slot with ambient_mix_hash → load clears legacy, playback = video_path |

Extend existing: `test_stitch_export_timeline_authority_v1`, `test_stitch_module_bake_av_parity`.

### Stage B — Script multipass

New: `Production/scripts/verify_stitch_four_files_durability.sh`

1. Sig grep: no event-slot read of `ambient_mix_hash` in resolver (allow legacy module comments)
2. pytest subset above
3. Server build-sha parity (Dropbox + served bundle)
4. Golden curl: mock slot bake → load_job → `video_path` unchanged, no bake log line

### Stage C — Live operator path (agent-run, Kim does not)

Per event port **5114 (Event_4)** after deploy:

1. Send resolution to Stitcher (or use existing export)
2. `curl load_job` → resolution `video_path` ends with `_playback_` or post-bake name; `beat_boundaries.length >= 1`
3. `ffprobe` slot file: audio stream present; drift ≤ 250ms
4. Hard refresh Stitcher → same URL, no “building mux” spinner
5. Bake Final → module MP4 duration ≈ sum(slots) ± transition budget

### Stage D — Blast-radius matrix

| Surface | Must still work | Proof |
|---------|-----------------|-------|
| Event_1–6 stitch jobs | Four-slot review + bake | Spot Event_1 + Event_4 |
| Phase A/B direct export | Upsert bakes playback | pytest + one curl |
| Milestone standalone | Unchanged or explicit shim | `test_milestone_stitch_job_isolation` |
| Intro canonical tail | Concat + bake | existing intro tests green |
| SFX waveform drops | Rebake updates video_path | `verify_stitch_sfx_playback_truth` adapted |
| Cache sweep | Does not delete `*_playback_*.mp4` referenced by state | sweep test |

---

## 8. Migration

1. **One-release shim (removed in same PR as P4):** legacy slots without `playback_recipe_version`:
   - Ambient-only: if cache `se_slot_{hash}` playable → copy bytes to new `_playback_` file, set `video_path`
   - SFX slots: if `mux_preview_{hash}` playable → same
   - Else: slot flagged `playback_migration_required`; Bake Final fail-closed until Re Send to Stitcher or Save rebake
2. Operator action: **Re Send to Stitcher** per slot OR **Save** stitch job — no manual Dropbox surgery.
3. Sweep unreferenced `se_slot_*` / `stitch_preview_*` after migration window (referenced + `*_playback_*` in state **never** deleted).
4. **`stitch_peaks_*`:** extract from **`video_path`** (mixed) for waveform display; SFX drop clock = `video_dur_ms` only.

---

## 9. Rollback

Revert commit; legacy resolver + ambient bake V1 returns. Re-export slots recommended after rollback.

---

## 10. Implementation phases

| Phase | Scope | Exit criteria |
|-------|--------|---------------|
| P0 | Spec + debate + registry | Kim approval |
| P1 | `stitch_slot_playback.py` + upsert/export bake | Stage A bake tests green |
| P2 | load_job read-only + client resolver | Stage A load/client tests green |
| P3 | save_job rebake + module bake skip double-mix | Stage B script green |
| P4 | Legacy migrate + sweep + docs | Stage C Event_4 proof |
| P5 | Full QA commit + deploy all ports | Stage D matrix |

---

## 11. Out of scope

- Changing Beat Gen per-beat flatten/concat semantics
- Client-side Web Audio ambient preview
- Kid app (`MindfulNest`) — consumes final module MP4 only
- Re-picking ambient bed files per event (content choice)

---

## 12. Review log (4-agent debate — incorporated in v1.1)

| Agent | Verdict | Key conditions incorporated |
|-------|---------|----------------------------|
| Adversary | APPROVE WITH CONDITIONS | G8 dry-only rebake; G9 module passthrough; single mutate G7; migration must cover SFX slots |
| Advocate | APPROVE WITH CONDITIONS | FF-036 renumber; module loudnorm skip; delete dead builders in P4; grep gate on read path |
| Durability | REJECT → fixed in v1.1 | Runtime pytest + verify script; no grep-only proof; port fanout in Stage C |
| Blast radius | APPROVE WITH CONDITIONS | artifact_build chain; timeline dur; e2e rewrite; poll completion signal |

---

## 13. Acceptance (Kim)

- [ ] Resolution slot: play after export, hard refresh, no spinner, lipsync stable through beat 6+
- [ ] Ambient bed audible, single soft loop per period
- [ ] Add one SFX → one rebake → hear SFX at drop time
- [ ] Bake Final matches four-slot review
- [ ] Empty phase slot stays empty until export

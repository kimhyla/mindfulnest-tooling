# TECH_SPEC_STITCH_AMBIENT_BAKE_V1

**Status:** LOCKED (post 3×3 review 2026-06-22)  
**Authority:** Kim product direction — ambient via dropdown only; waveform is SFX-only; composer must play without mux wait when no SFX.  
**Token:** `STITCH_AMBIENT_BAKE_ON_SAVE_V1`

---

## 1. Problem

Stitcher treats **ambient bed** like a live preview layer:

1. `stitchSlotRequiresMuxedPreview` is true when ambient OR SFX → composer blocks on server mux build.
2. Waveform `audio_extract` remixes ambient into MP3 peaks → extra ffmpeg + cache surface.
3. `stitch_preview` runs full normalize → ambient mix → copy pipeline on every ambient/SFX geometry change.
4. Playability gates + redundant `se_norm_*_pv` re-encodes created poison-cache risk unrelated to operator intent.

**Operator intent:** Pick ambient bed from dropdown (reset/change). Hear result in composer. Place SFX on speech waveform. No ambient editing on waveform.

---

## 2. Goals

| Goal | Metric |
|------|--------|
| Ambient dropdown → audible preview | ≤1 server bake (no mux) for slots without SFX |
| No redundant reload | Job load hydrates persisted ambient artifact; no mux queue when SFX empty |
| Waveform = SFX only | `audio_extract` speech-only peaks; no ambient in extract path |
| Mux only with SFX | `stitch_preview` mux when `sfx_cues` non-empty |
| Durable artifacts | Lineage pins + mix sig; purge poison; sweep orphans |
| Bake unchanged | Full pipeline still builds final module MP4 with ambient + SFX |

---

## 3. Non-goals

- Per-waveform ambient volume editing (volume fixed `0.15`).
- Baking ambient at Phase export (dropdown remains Stitcher authority).
- Client Web Audio preview (deferred; server bake on save is sufficient).
- Removing loudnorm / trim / transitions.

---

## 4. Architecture

### 4.1 Artifact layers

```
[Phase export] → dry slot MP4 (speech, LD-284)
       ↓
[Dropdown save] → se_slot_{ambient_hash}.mp4  (speech + ambient, no SFX)
       ↓
[SFX on slot]   → stitch_preview_{mux_hash}.mp4 (speech + ambient + SFX)
       ↓
[Bake]          → module final MP4
```

| Artifact | File pattern | When built | Composer uses when |
|----------|--------------|------------|---------------------|
| Dry slot | Event path | Phase/BG export | No ambient, no SFX |
| **Ambient mix** | `se_slot_{hash}.mp4` | `stitch_save_job` if ambient set | Ambient set, **no SFX** |
| Mux preview | `stitch_preview_{hash}.mp4` | `stitch_preview` if SFX | SFX cues present |
| Speech peaks | `stitch_peaks_{hash}.json` | `audio_extract` speech-only | Waveform display |
| Normalize cache | `se_norm_*` | Bake / trim only | Not preview hot path |

### 4.2 Persisted slot fields (additions)

```json
{
  "ambient_mix_hash": "12-char stem matching se_slot_{hash}",
  "ambient_mix_duration_ms": 22750,
  "ambient_mix_video_path": "Production/Event_2/...mp4",
  "ambient_mix_video_mtime_ms": 1782134777526,
  "ambient_mix_sig": "16-char SHA256 (video + ambient, no SFX)"
}
```

Ephemeral on load (not in JSON on disk):

- `_ambient_mix_url` → `/api/stitch_editor/slot_mix_file/{ambient_mix_hash}`

Existing mux fields unchanged; only populated when SFX exist.

### 4.3 Signatures (dual-layer invalidation)

| Field | Inputs | Clears on drift |
|-------|--------|-----------------|
| `ambient_mix_sig` | video path + mtime + ambient + volume + loop token; **no SFX** | `ambient_mix_*` fields |
| `mix_sig` (full) | above + sorted SFX cue geometry | `mux_preview_*` (+ peaks only if extract included SFX — not after V1) |

**File identity:** `ambient_mix_hash` = 12-char stem from `_stitch_mix_slot_audio` output `se_slot_{hash}.mp4` (MD5 of norm mtime + ambient path + volume + loop token). **Not** derivable from `ambient_mix_sig` alone — validation uses lineage pins + playability probe on `se_slot_{ambient_mix_hash}.mp4`.

**Normalize tier:** ambient bake uses `preview_only=True` (`stitch_preview_can_use_source_directly` skip when LD-284).

Client `stitchSlotRequiresMuxedPreview(slot)` → **SFX only**.

Client `stitchSlotLiveAmbientSig(slot)` → video + ambient (no SFX) for ambient-mix session cache.

**Migration:** load validates ambient-only slots with legacy `mux_preview_hash` → clear mux fields; composer uses ambient mix only.

### 4.4 Server flows

#### A. `POST stitch_save_job` (ambient dropdown)

1. Merge slot; clear `ambient_bed_path`; normalize volume; invalidate artifacts on geometry drift.
2. Persist job state.
3. For each merged slot with `video_path` + `ambient_bed`:
   - `_stitch_build_slot_ambient_mix(slot)` → normalize (or skip) + `_stitch_mix_slot_audio(sfx=[])`.
   - Persist `ambient_mix_*` fields + `ambient_mix_sig`.
4. If ambient cleared: pop ambient_mix fields.
5. Build **before** persisting `ambient_mix_hash` (playable gate passes).
6. Response **required:** `built_slots: { slot_key: { ok, ambient_mix_hash?, _ambient_mix_url?, error? } }`.
7. Job JSON saved even if one slot bake fails; per-slot error in `built_slots`.

#### B. `GET stitch_load_job`

1. `validate_stitch_slot_media_artifacts` — validate ambient mix file + lineage pins.
2. `attach_stitch_slot_derived_media_urls` — attach `_ambient_mix_url`.
3. If ambient expected but artifact missing: warning + client may call rebuild endpoint.

#### C. `POST stitch_preview` (slot preview / SFX geometry change)

- Only required when `sfx_cues` non-empty.
- Client skips POST when no SFX.

#### D. `POST stitch_audio_extract`

- **Speech-only** extract from slot video (ignore `ambient_bed` in body for mix; deprecate ambient params).
- Peaks hash from raw extract stem only.

#### E. `GET stitch_editor/slot_mix_file/{hash}`

- Serves `Production/stitch_editor_cache/se_slot_{hash}.mp4` with byte-range + playability gate.

### 4.5 Client flows

#### Composer video URL

```typescript
if (hasSfx) use mux preview URL (build if missing)
elif (hasAmbient) use ambient mix URL from slot._ambient_mix_url or previewUrls
else use dry video_path
```

#### Waveform

- Do not pass `ambientBed` to `audio_extract`.
- Peaks show speech; label indicates SFX timeline.

#### Job load hydrate

- `previewUrls[slot] = ambient mix URL` when ambient + no SFX + valid artifact.
- `slotsNeedingMux` only when SFX + missing mux.
- `slotsNeedingAmbientMix` when ambient + missing artifact → optional quiet rebuild via save or dedicated endpoint.

---

## 5. Cleanup policy (STITCH_CACHE_SWEEP_V1)

### DELETE (safe)

| Pattern | Condition |
|---------|-----------|
| `*.tmp.*.mp4` | Orphan temps in `stitch_editor_cache` |
| `*.browser_norm.*.mp4` | Failed in-place heal leftovers |
| `se_norm_*_pv.mp4` | Unreferenced by any job artifact AND age > 1h |
| `stitch_preview_*.mp4` | Unreferenced stem AND not in `mux_preview_hash` |
| `stitch_audio_{12}.mp3` | Mixed waveform MP3 (12-char hash) unreferenced |
| `se_slot_*.mp4` | Unreferenced AND not `ambient_mix_hash` |

### NEVER DELETE

| Pattern | Reason |
|---------|--------|
| Referenced `mux_preview_hash` | Active mux preview |
| Referenced `ambient_mix_hash` | Active ambient mix |
| Referenced `waveform_peaks_hash` | Active peaks |
| Event slot `video_path` files | Canonical exports |
| `stitch_bake.lock` while bake running | Active job |

### Implementation

- `sweep_stitch_cache_unreferenced(h)` — reads `stitch_editor_state.json`, collects referenced stems, deletes orphans.
- Run once at server startup + after deploy mirror.

---

## 6. Migration

1. Deploy code; load job → stale mux for ambient-only slots cleared by validation.
2. First ambient dropdown save or `stitch_save_job` rebuilds ambient mix.
3. Sweep orphans after migration.

No manual Dropbox edits required.

---

## 7. Tests (real durability)

| Test | Contract |
|------|----------|
| `test_stitch_ambient_bake_on_save` | save_job with ambient → `se_slot_*.mp4` exists + playable + `ambient_mix_hash` persisted |
| `test_stitch_mux_only_when_sfx` | `stitchSlotRequiresMuxedPreview` false with ambient only |
| `test_audio_extract_speech_only` | ambient in body does not change peaks hash |
| `test_ambient_mix_lineage_stale` | video_path change clears ambient_mix fields |
| `test_cache_sweep_preserves_referenced` | referenced stems survive sweep |
| Static grep | `stitchSlotRequiresMuxedPreview` uses SFX-only gate |

---

## 8. Deploy / QA proof

1. `pytest` relevant tests pass.
2. `deploy_storyboard_v59.sh` or mirror + restart on port 5112.
3. `curl` save_job → response includes `built_slots.phase_a.ambient_mix_hash`.
4. `curl` slot_mix_file → HTTP 200 + ffprobe duration matches slot.
5. Browser: Event_2 Stitcher → Phase A → change ambient dropdown → composer plays without "Muxed preview unavailable"; hard refresh → still plays from persisted artifact.

---

## 9. Rollback

Revert commit; old mux-on-ambient behavior returns. Orphan `se_slot_*` files harmless.

# TECH_SPEC — Stitch Intro Export Truth v2 (FF-038)

**Status:** In progress (2026-07-01)  
**Supersedes:** FF-037 partial fix — join fade 80ms shipped but still-insert path inference dead + ambient aloop clicks remain  
**Scope:** All BG `pre`/`post`/`phase_*` exports + four-files playback bake (intro first on Event_4)

## 3×3 agent debate (consensus)

### Agent A — Export concat

| Position | Detail |
|----------|--------|
| A1 | `_kling_export_clip_path_is_still_insert()` checks `_still_insert_` in filename — clips are renamed to `{beat_id}_norm_concat.mp4` before concat → **150ms exit fade never fires** |
| A2 | `beat_is_still_insert(beat)` must be captured in `resolve_segment_stitch_export_clip_paths` and passed as parallel `list[bool]` |
| A3 | Lipsync cliff at ~33.9s is **hard video cut** (still-insert TTS → Kling) while only audio got micro-fade; need symmetric **video** `fade=t=out` at still-insert exits (`KLING_EXPORT_STILL_INSERT_EXIT_FADE_MS`) |

**Marker:** `STITCH_EXPORT_TRUTH_STILL_INSERT_VIDEO_FADE_V1`

### Agent B — Ambient bed loop

| Position | Detail |
|----------|--------|
| B1 | `STITCH_AMBIENT_FULL_PERIOD_TILE_V2` builds correct one-period tile, then `[tile]aloop=loop=-1` hard-restarts at ~32.808s — audible in **playback** at user-reported 33s/66s |
| B2 | Replace post-tile `aloop` with explicit `asplit` + `concat` tile repeat (`STITCH_AMBIENT_TILE_CONCAT_LOOP_V1`) then `atrim` to slot duration |
| B3 | Short beds (`content_s < STITCH_AMBIENT_LOOP_MIN_BED_S`) may keep `aloop` — not intro symptom path |

**Marker:** `STITCH_AMBIENT_TILE_CONCAT_LOOP_V1`

### Agent C — Stitcher / waveform

| Position | Detail |
|----------|--------|
| C1 | `waveform_peaks_hash` survives re-export when dry/playback paths change — composer can show stale peaks misaligned with lip motion |
| C2 | `bake_and_persist_slot_playback_mp4` upsert must `pop("waveform_peaks_hash")` on every successful export bake |
| C3 | FF-037 dry-path peaks routing stays; v2 adds **write-time invalidation** only |

**Marker:** `STITCH_EXPORT_TRUTH_WAVEFORM_INVALIDATE_ON_EXPORT_V1`

### Unanimous rejections (do not repeat)

- LEGACY_PURGE / mux artifact tiers — authority layer, not concat quality
- Raising join fade beyond 80ms globally without still-insert metadata — insufficient alone (measured dry steps unchanged post FF-037)
- Filename-based still-insert detection after norm_concat rename

## Root cause (post FF-037 measurement)

| Symptom | Layer | Cause |
|---------|-------|-------|
| Click ~33.9s dry | Concat | Still-insert exit fade dead code; hard A/V join beat_05→beat_15 |
| Click ~32.8s playback-only | Ambient mux | `aloop` period restart at bed tile length |
| Lipsync off after 33s | Composer + video | Hard video cut + optional stale peaks hash |

**Baselines (Event_4 pre-FF-038):**

- Dry: `intro_kling_o3_20260701T230840Z.mp4` — max_step ~0.21 at 33.9s, ~0.20 at 65.6s
- Playback: `intro_playback_20260701T231028Z.mp4` — max_step ~0.19 at 32.8s (ambient period)

## Non-negotiable invariants (FF-038)

### Export concat

| Rule | Detail |
|------|--------|
| Metadata | `resolve_segment_stitch_export_clip_paths` → `(clip_paths, still_insert_flags, scratch_dir)` |
| Audio exit | `still_insert_flags[i]` → `KLING_EXPORT_STILL_INSERT_EXIT_FADE_MS` on outgoing join |
| Video exit | Same flag → `fade=t=out` on video lane before concat |
| Pair-fade intro | Expand `still_insert_flags` for black-pause parts (`False` on inserted black clips) |

### Ambient loop

| Rule | Detail |
|------|--------|
| Full-period path | `build_ambient_explicit_tile_concat_loop` replaces `[tile]aloop` |
| Sig token | `ambient_loop_sig_token()` includes `STITCH_AMBIENT_TILE_CONCAT_LOOP_V1` |

### Waveform invalidation

| Rule | Detail |
|------|--------|
| On export bake | `slot.pop("waveform_peaks_hash", None)` in `bake_and_persist_slot_playback_mp4` upsert |
| Peaks source | Unchanged FF-037: four-files peaks from `dry_export_path` |

## Blast radius

| File | Change |
|------|--------|
| `beat_generator.py` | still_insert flags; video fade; pair-fade flag expansion |
| `stitch_ambient_loop.py` | tile concat loop |
| `stitch_slot_playback.py` | peaks hash purge |
| `kling_o3.py` | unpack 3-tuple from resolve |
| `authority_registry.py` + registry doc | FF-038 row |
| Tests + `verify_stitch_export_truth_v2_durability.sh` | new gates |

## Verification gates

### Pre-deploy

1. `pytest tests/test_stitch_export_truth_v2_durability.py -v`
2. `pytest tests/test_stitch_ambient_loop_seam_budget.py -v`
3. `pytest tests/test_stitch_export_truth_durability.py -v`
4. `bash Production/scripts/verify_stitch_export_truth_v2_durability.sh`
5. `bash Production/scripts/verify_authority_registry_durability.sh`

### Post-deploy proof (D1–D8)

| Step | Check | Pass |
|------|-------|------|
| D1 | Fleet build-sha `:5111`–`:5116` == HEAD | all match |
| D2–D3 | `verify_multipass_deploy_proof.sh` 1 & 2 | exit 0 |
| D4 | `verify_stitch_export_truth_v2_durability.sh` | exit 0 |
| D5 | Send to Stitcher (intro) on `:5114` | new `intro_kling_o3_*` + `intro_playback_*` |
| D6 | Seam probe dry at 33.9s / 65.6s vs 230840Z baseline | max_step −30% |
| D7 | Seam probe playback at 32.8s vs 231028Z baseline | max_step −30% |
| D8 | Browser Stitcher composer — waveform + lip at beat 5 | visual OK |

### Poisoned state

Existing intro MP4s remain broken until **Send to Stitcher (intro)** after deploy.

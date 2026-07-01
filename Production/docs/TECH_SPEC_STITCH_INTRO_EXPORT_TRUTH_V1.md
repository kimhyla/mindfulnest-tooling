# TECH_SPEC — Stitch Intro Export Truth v1 (FF-037)

**Status:** In progress (2026-07-01)  
**Scope:** Event_4 intro first; all BG `pre`/`post`/`phase_*` exports via same pipeline  
**Agents:** 4×4 debate consensus — LEGACY_PURGE was wrong layer for intro symptoms

## Problem class

Intro Stitcher symptoms after `STITCH_FOUR_FILES_LEGACY_PURGE_V1`:

1. **Audio jumps ~33s / ~66s** — measured in **dry** `intro_kling_o3_*` (speech-only) and baked playback; not introduced by ambient mux alone.
2. **Lipsync “way off” in composer** — video uses `-c:v copy` from dry concat; drift is pre-bake or **UI waveform misalignment** (peaks from ambient-mixed MP4).
3. **Wrong prior fix** — LEGACY_PURGE stops split-authority regression; does not rebake MP4s or fix concat joins.

## Root cause (consensus)

| Layer | Cause | Evidence |
|-------|--------|----------|
| Dry concat | 25ms beat-join fade insufficient; still-insert→Kling timbre cliff at ~33.9s | RMS steps in dry file at beat boundaries |
| Waveform UI | Peaks extracted from `video_path` (playback w/ ambient) while video is speech timeline | `StitcherTab` passes `video_path` to `StitcherSlotWaveform` |
| Browser playback | Missing `+faststart` on `se_slot_*` mix cache; edit-list atoms may survive `-c:v copy` | `production_server._stitch_mix_slot_audio` |

Ambient loop period (32.808s) is a **timing coincidence** — pure V2 ambient render has inaudible seams; dry file has no ambient.

## Non-negotiable invariants (FF-037)

### Export concat (all BG slots)

| Rule | Detail |
|------|--------|
| Marker | `STITCH_EXPORT_TRUTH_JOIN_FADE_V1` |
| Join fade | `KLING_EXPORT_AUDIO_JOIN_FADE_MS` ≥ 80ms at all non-terminal beat joins |
| Still-insert exit | `KLING_EXPORT_STILL_INSERT_EXIT_FADE_MS` = 150ms on clips whose path contains `_still_insert_` |
| Pipeline | trim → loudnorm → AV assert → `concat_kling_o3_approved_beats` → dry MP4 |

### Four-files playback bake

| Rule | Detail |
|------|--------|
| Marker | `STITCH_EXPORT_TRUTH_PLAYBACK_REMUX_V1` |
| Post-bake | `ensure_mp4_playback_timestamps` + `_remux_mp4_copy_safe` (+faststart) |
| Mix output | `_stitch_mix_slot_audio` MUST include `-movflags +faststart` |
| Drift gate | `STITCH_EXPORT_AV_MAX_DRIFT_S` unchanged |

### Waveform / composer parity

| Rule | Detail |
|------|--------|
| Marker | `STITCH_EXPORT_TRUTH_WAVEFORM_SPEECH_V1` |
| Peaks source | Four-files slots: extract peaks from `dry_export_path`, not baked `video_path` |
| Client | `StitcherTab` passes `dry_export_path` to waveform when four-files |
| Playback video | Composer video URL unchanged (`video_path` baked playback) |

## Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| All Kling exports | Longer join fades change concat audio | Golden pytest + re-export smoke |
| Intro / phase_b four-files | Peaks cache invalidation | New peaks hash from dry path |
| Legacy resolution mux | Unchanged in v1 | Follow-up: migrate to four-files |
| Milestone jobs | Still legacy ladder | Out of scope v1 |
| Deploy | build-sha drift | Commit before deploy; fleet parity |

## Verification gates (multipass)

### Pre-deploy (local)

1. `pytest tests/test_stitch_export_truth_durability.py -v`
2. `pytest tests/test_kling_o3_concat_export.py -v`
3. `bash Production/scripts/verify_stitch_export_truth_durability.sh`
4. `bash Production/scripts/verify_stitch_four_files_durability.sh`
5. `bash Production/scripts/verify_authority_registry_durability.sh`
6. `npm run build` in `storyboard-v2/`

### Deploy (Event_4 primary)

```bash
MN_SKIP_DROPBOX_EDIT_GATE=1 bash Production/scripts/deploy_storyboard_v59.sh --event Event_4
```

**Success:** log contains `[deploy] complete`; no `FATAL` after pre-A.

### Post-deploy proof (each step logged)

| Step | Command / check | Pass |
|------|-----------------|------|
| D1 | Fleet build-sha `:5111`–`:5116` == `git HEAD` | all match |
| D2 | `verify_multipass_deploy_proof.sh 1` | exit 0 |
| D3 | `verify_multipass_deploy_proof.sh 2` | exit 0 |
| D4 | `verify_stitch_export_truth_durability.sh` | exit 0 |
| D5 | Intro re-export (Send to Stitcher pre) on `:5114` | new `intro_kling_o3_*` + `intro_playback_*` |
| D6 | Python seam probe on new dry file at 33.876s / 64.826s | max_step ≤ prior baseline − 30% |
| D7 | `load_job` intro slot: peaks hash bound; no legacy mux fields | grep API |
| D8 | Hard refresh Stitcher — waveform aligns with lip motion at beat 5 | operator |

### Poisoned state

Existing intro MP4s on disk **remain broken** until **Send to Stitcher (intro)** after deploy. No automatic rebake on deploy.

## Implementation map

| File | Change |
|------|--------|
| `beat_generator.py` | Join fade 80ms; still-insert exit 150ms |
| `stitch_slot_playback.py` | Post-bake remux marker |
| `production_server.py` | `+faststart` on mix |
| `stitch_editor.py` | Peaks from dry on four-files |
| `StitcherTab.tsx` | Waveform `dry_export_path` for four-files |
| `authority_registry.py` + registry doc | FF-037 row |

## Out of scope (v1)

- Resolution legacy → four-files migration
- Ambient `aloop` → explicit concat tile repeat
- Milestone job four-files promotion

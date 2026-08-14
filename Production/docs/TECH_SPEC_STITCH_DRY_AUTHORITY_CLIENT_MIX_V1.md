# TECH_SPEC — Stitch Dry Authority + Client Mix v1 (STITCH_DRY_AUTHORITY_CLIENT_MIX_V1)

**Status:** v1.0 — 2×2 agent debate consensus; approved for Full QA implementation  
**Marker:** `STITCH_DRY_AUTHORITY_CLIENT_MIX_V1`  
**FF registry:** **FF-042** (supersedes FF-036 preview authority; FF-041 remains legacy bake containment)  
**Supersedes (preview path):** `TECH_SPEC_STITCH_FOUR_FILES_V1.md` §0–§3 operator playback contract  
**Parent registry:** `STORYBOARD_AUTHORITY_REGISTRY_v1.md`  
**Branch:** `feat/cross-pipeline-g1-g8-closure`

---

## 0. Operator contract (Kim — non-negotiable)

| Rule | Detail |
|------|--------|
| Flattened export | Send to Stitcher writes **one dry concat MP4** per slot — same bytes Beat Gen exported |
| `video_path` | **IS** the dry concat — not `*_playback_*`, not a copy, not a rebake |
| Stitcher speech | `<video src=dry>` — speech **audio bytes** from that file via `MediaElementSource` |
| Stitcher ambient + SFX | Layered at playback (client Web Audio) — hear bed + drops while scrubbing |
| SFX cue bytes | **Prefetch on attach** (`STITCH_SFX_HOT_SERVE_PREFETCH_V1`) via `/files` with 503 retry — never first-load on the play critical path |
| Dry composer video | Bind only after APFS `playback_resolve` (`STITCH_DRY_HOT_SERVE_PLAYBACK_V1`) — never cold Dropbox `/files` for dry/four-files slots |
| Ambient loop seams | Server-rendered slot-length ambient asset (FF-039 graph parity) — client plays file, does not synthesize loop |
| Save ambient/SFX | Geometry persist only — **no** server ffmpeg rebake on save |
| Bake Final | Server ffmpeg mixes dry slots + ambient + SFX → kid module MP4 |
| Four containers | intro / phase_a / phase_b / resolution — unchanged |

> **Composer truth = dry MP4 bytes. Kid truth = server Bake Final mix.**

---

## 1. 2×2 debate consensus

| Agent | Verdict | Key incorporation |
|-------|---------|-----------------|
| **Advocate** | APPROVE WITH CONDITIONS | Dry `video_path`; `StitchSlotAudioMixEngine`; W9 ambient loop API; module bake re-mix |
| **Adversary** | REJECT → **APPROVE WITH CONDITIONS** after synthesis | W9 blocks client FF-039 port; `MediaElementSource` (not mute+replace); migration gate; no double-audio; seek sync ≤50ms |
| **Durability** | APPROVE WITH CONDITIONS | `verify_stitch_dry_authority_client_mix_durability.sh`; ffprobe P1–P7; registry rows |
| **Blast radius** | APPROVE WITH CONDITIONS | ~35 files; load_job migration from `dry_export_path`; module bake invert passthrough |

**Resolved adversary blockers:**

| Blocker | Resolution |
|---------|------------|
| FF-039 client ambient | **W9** `GET /api/stitch_editor/slot_ambient_loop` — server ffmpeg, same `build_ambient_bed_filter_lane_for_file` |
| `video_path` baked for bake | **Rejected** — Kim requires dry IS the file; module bake mixes at Bake Final |
| Double-audio | Single graph: `MediaElementSource(video)` → speech bus; ambient/SFX additive only |
| Split authority | `video_path` = dry = waveform source = composer video src |

---

## 2. Architecture

```
[Beat Gen Send to Stitcher]
  per beat: resolve approved MP4 (same path as BG preview — delivery or trim bake)
  concat → one dry slot MP4 (intro_kling_o3_*.mp4)
  upsert: video_path = dry, playback_recipe_version = STITCH_DRY_AUTHORITY_CLIENT_MIX_V1
  NO per-beat loudnorm · NO per-beat normalize · NO ambient · NO bake_slot_playback_mp4

[Stitcher review]
  <video src="/api/media/playback/…">   ← dry bytes after playback_resolve (APFS)
  StitchSlotAudioMixEngine + W9 ambient loop:
    speech from <video> element (MediaElementSource)
    ambient bed @ 0.15 via slot_ambient_loop (preview only — not baked into video_path)
    SFX cues: prefetch on attach → Web Audio schedule on play (preview only)
  stitch_save_job: persist geometry only — NO server ffmpeg rebake

[Bake Final]  ← normalize · loudnorm · ambient · SFX · transitions happen HERE
  per slot: normalize → loudnorm → _stitch_mix_slot_audio(dry) → concat + transitions
  → kid module MP4
```

### 2.1 Client-mix media durability (forever lock)

| Layer | Marker | Rule |
|-------|--------|------|
| Dry / four-files video | `STITCH_DRY_HOT_SERVE_PLAYBACK_V1` | Composer `<video>` binds only `/api/media/playback/…` after `playback_resolve`. Cold `/files` for those slots is forbidden (Dropbox File Provider gray / Format Error). |
| Default start/finish SFX | `STITCH_SFX_HOT_SERVE_PREFETCH_V1` | `prefetchAllSfx` on attach; `/files` fetch retries 503/429; audit `SFX_PREFETCH` / `SFX_LOAD_FAILED` / `SFX_SCHEDULE`. Play must schedule from warm cache (`sfx_scheduled` matches remaining cues). |

**Forbidden regressions**

- Loading SFX buffers only inside `scheduleSfxFromCurrentTime` with no attach prefetch
- Swallowing SFX fetch failures without `SFX_LOAD_FAILED` audit
- Binding dry-slot composer video to `/files?path=` when hot-serve resolve fails
- Re-introducing timeupdate drift-resync that stops/reschedules SFX every ~250ms

**Gates:** `verify_stitch_sfx_playback_truth_durability.sh` · `verify_stitch_dry_authority_client_mix_durability.sh` · session durability aggregate

---

## 3. Wire points

| ID | Site | Change |
|----|------|--------|
| W1 | `stitch_upsert_event_slot` | `persist_dry_authority_slot_export` replaces four-files bake |
| W2 | `handle_stitch_load_job` | `migrate_four_files_slot_to_dry_authority` |
| W3 | `_stitch_build_pipeline` | Passthrough **only** `STITCH_FOUR_FILES_V1`; dry authority → full mix |
| W4 | `GET /api/stitch_editor/slot_ambient_loop` | Slot-length ambient audio (FF-039 graph) |
| W5 | `resolveSlotPlaybackPreviewUrl` + `stitchDryHotServePlayback` | Dry path authority; composer bind only after `playback_resolve` |
| W6 | `resolveSlotWaveformVideoPath` | `video_path` (dry) — drop `dry_export_path` branch |
| W7 | `StitcherTab` + `StitchSlotAudioMixEngine.ts` | Client mix lifecycle + `STITCH_SFX_HOT_SERVE_PREFETCH_V1` |
| W8 | `stitch_save_job` | No rebake for dry-authority event slots |
| W9 | `authority_registry.py` + doc | FF-042 rows |
| W10 | `stitchSfxFetch.ts` | `/files` 503/429 retry for cue bytes |
| W11 | `verify_stitch_*` durability scripts | Prefetch + dry hot-serve markers fail deploy |

---

## 4. Migration (load_job)

For `playback_recipe_version === STITCH_FOUR_FILES_V1` or `video_path` matches `*_playback_*`:

1. If `dry_export_path` exists and file on disk → `video_path = dry_export_path`
2. Else glob assembled dry candidate for slot → newest
3. Else `playback_migration_required = true` (fail-closed until Re Send to Stitcher)
4. Set `playback_recipe_version = STITCH_DRY_AUTHORITY_CLIENT_MIX_V1`
5. Clear legacy mux/ambient artifact fields; invalidate peaks hash if path changed
6. Do not delete `*_playback_*` on disk (orphan sweep later)

---

## 5. Acceptance (measurable)

| ID | Gate | Threshold |
|----|------|-----------|
| P1 | `video_path` basename | `*_kling_o3_*` or phase stitch — **not** `*_playback_*` |
| P2 | `video_dur_ms` vs ffprobe | ≤50ms |
| P3 | Dry A/V drift | ≤250ms |
| P4 | New `*_playback_*` after SFX save | 0 files |
| B1 | `data-stitch-client-mix` marker | present when ambient or SFX |
| B2 | SFX marker position | ±2% of `offset_ms / video_dur_ms` |
| B3 | Mix clock vs `video.currentTime` @30s | ≤50ms |
| B4 | `SFX_PREFETCH` after attach | `sfx_loaded` == cue count with paths; `sfx_failed` == 0 when `/files` healthy |
| B5 | `SFX_RESYNC` after play @ t≈0 | `sfx_scheduled` ≥ start+finish cues still in window (resolution: 2) |
| B6 | Dry composer `src` | `/api/media/playback/` only for dry/four-files slots |
| M1 | Module bake output | ambient + SFX present; duration ≈ Σ slots |

---

## 6. Milestone jobs

**Frozen:** milestone `standalone` keeps legacy server mux ladder until explicit follow-up. Event four-slot jobs are primary scope.

---

## 7. Review log

All four agents **APPROVE WITH CONDITIONS** after §1 synthesis. Implementation blocked until W9 + module bake invert + migration land in same PR as client engine.

**2026-08-14 enshrine:** `STITCH_SFX_HOT_SERVE_PREFETCH_V1` + `STITCH_DRY_HOT_SERVE_PLAYBACK_V1` locked into this spec, authority registry, cursor rule, and deploy durability gates after Event_6 audit proved play-critical `/files` SFX loads left `sfx_scheduled: 0`.

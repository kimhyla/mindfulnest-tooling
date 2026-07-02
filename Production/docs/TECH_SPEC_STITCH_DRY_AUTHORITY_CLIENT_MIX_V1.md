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
  concat → dry MP4
  upsert: video_path = dry, playback_recipe_version = STITCH_DRY_AUTHORITY_CLIENT_MIX_V1
  NO bake_slot_playback_mp4

[Stitcher review]
  <video src="/files?path={video_path}">   ← dry bytes (video + speech)
  StitchSlotAudioMixEngine:
    MediaElementSource(video) → speech → destination
    fetch W9 ambient loop → BufferSource(loop) → gain(ambient_volume) → destination
    per sfx_cue: fetch source → BufferSource @ offset_ms → destination
  sync: play / pause / seeked → reschedule

[stitch_save_job]
  persist sfx_cues / ambient_bed / volume only
  client engine rebuild — NO server slot mux

[Bake Final]
  per slot: normalize → loudnorm → _stitch_mix_slot_audio(dry) → concat + transitions
```

---

## 3. Wire points

| ID | Site | Change |
|----|------|--------|
| W1 | `stitch_upsert_event_slot` | `persist_dry_authority_slot_export` replaces four-files bake |
| W2 | `handle_stitch_load_job` | `migrate_four_files_slot_to_dry_authority` |
| W3 | `_stitch_build_pipeline` | Passthrough **only** `STITCH_FOUR_FILES_V1`; dry authority → full mix |
| W4 | `GET /api/stitch_editor/slot_ambient_loop` | Slot-length ambient audio (FF-039 graph) |
| W5 | `resolveSlotPlaybackPreviewUrl` | Dry `/files?path=video_path` for dry-authority slots |
| W6 | `resolveSlotWaveformVideoPath` | `video_path` (dry) — drop `dry_export_path` branch |
| W7 | `StitcherTab` + `StitchSlotAudioMixEngine.ts` | Client mix lifecycle |
| W8 | `stitch_save_job` | No rebake for dry-authority event slots |
| W9 | `authority_registry.py` + doc | FF-042 rows |

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
| M1 | Module bake output | ambient + SFX present; duration ≈ Σ slots |

---

## 6. Milestone jobs

**Frozen:** milestone `standalone` keeps legacy server mux ladder until explicit follow-up. Event four-slot jobs are primary scope.

---

## 7. Review log

All four agents **APPROVE WITH CONDITIONS** after §1 synthesis. Implementation blocked until W9 + module bake invert + migration land in same PR as client engine.

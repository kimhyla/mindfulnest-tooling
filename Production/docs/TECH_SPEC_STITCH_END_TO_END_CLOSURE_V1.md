# TECH_SPEC — Stitch End-to-End Closure v1

**Status:** Shipped (2026-07-01)  
**Agents:** FF-026 Ambient Authority + FF-036 Playback Authority + CI/Durability (3×3 debate consensus)

## Problem class

Split authority and bundled regressions:

1. **FF-026:** `1dd2401` replaced operator-verified V2 ambient tile with V3; audible click at every `bed_period` (intro ~33s, resolution ~27s).
2. **FF-036:** Four-files bake wrote flat MP4 but Stitcher client could still play stale mux/ambient URLs from `previewUrls`, session, or localStorage.
3. **Invalidation:** `bg_o3_stitch_invalidation` cleared `video_path` but left `playback_recipe_version`, breaking recovery.

## Non-negotiable invariants

### FF-026 — Ambient loop (ONE algorithm marker)

| Rule | Detail |
|------|--------|
| Active marker | `STITCH_AMBIENT_FULL_PERIOD_TILE_V2` |
| Algorithm | `pre` + `wrap` crossfade + `concat` → full-period tile → `aloop` |
| Forbidden | V3 offset duplicate + `atrim=0:{content_s}` after acrossfade (`STITCH_AMBIENT_PERIOD_OFFSET_XFADE_V3`) |
| Golden beds | Resolution `ambien bed pretty option4.mp3` (~27s); Intro `Intro video ambient bed.mp3` (~32.8s) |
| CI | Filter graph MUST contain `concat=n=2:v=0:a=1[{p}tile]`; MUST NOT contain `[{p}p1]` V3 labels |
| Bundling | Ambient loop changes MUST NOT ship in same commit as playback pipeline changes |

### FF-036 — Four-files playback (ONE file, ONE URL)

| Rule | Detail |
|------|--------|
| Bake | `stitch_upsert_event_slot` → `bake_and_persist_slot_playback_mp4` for all event slots |
| Authority | `slot.video_path` = `*_playback_*.mp4` = Stitcher playback = Bake Final input |
| Client read gate | `stitchSlotUsesFourFilesPlayback` → return `/files?path=` for `video_path` **before** cache |
| Client write gate | `buildSlotPreview` MUST NOT call `stitch_preview` for four-files slots |
| Server preview | `handle_stitch_preview` MUST passthrough `/files?path=` for four-files (no ffmpeg) |
| Cache | localStorage MUST store `playback_recipe_version`; reject stale recipe |
| Invalidation | Clearing `video_path` MUST also clear `playback_recipe_version` + `dry_export_path` |

## Verification gates

- `verify_stitch_ambient_durability.sh` — V2 marker + concat grep + pytest
- `verify_stitch_four_files_durability.sh` — client read gate + server passthrough + pytest
- Both wired into `verify_fast_and_flawless_done.sh` pass 3

## Operator invariant

After Send to Stitcher: exactly one MP4 per slot; Stitcher plays that file only.

# TECH_SPEC_VIDEO_QUALITY_V1

**Status:** implemented 2026-06-22  
**Scope:** Storyboard operator preview + stitch bake pipeline (all events)

## Problem classes

| ID | Class | Symptom | Category fix |
|----|--------|---------|--------------|
| VQ-P1 | Dual decode + seek loops | Horizontal banding / pleats on Phase A/B lipsync preview | Single `HTMLVideoElement` drives WaveSurfer via `media` option (one clock) |
| VQ-P2 | Throttled display-only sync | Choppy lip motion in preview after pleat fix | Same as VQ-P1 — no seek-driven frame updates during play |
| VQ-P3 | Inconsistent H.264 recipes | Soft exports, blocky previews | `VIDEO_QUALITY_V1` constants: CRF 18 everywhere |
| VQ-P4 | Bitrate cap vs quality | Bake normalize capped at 1500k | CRF 18 + slow preset (similar size, better gradients) |
| VQ-P5 | Gradient banding in encode | Fireplace/smoke macro-blocks | `gradfun` in normalization VF chain |
| VQ-P6 | Missing preview CSS | Banding on small BG magic previews | `PLAYBACK_VIDEO_ANTI_BANDING_CLASS` on all preview `<video>` |
| VQ-A1 | Avatar still sub-HD | Soft Avatar Pro output when operator PNG is ~1672×941 (passes 600px min gate only) | `ensure_avatar_still_dimensions()` in `submit_avatar_pro()` → 1920×1080 before data URI (Beat Gen + Phase A + Phase B) |

## Single sources of truth

- **Encode:** `credentials_lib/video_encode_policy.py` + `credentials_lib/ffmpeg_stitch.py` (imports policy)
- **Preview playback:** `playbackVideoPolicy.ts` + `WaveformTimeline.tsx` (`effectiveLinkedVideoMatchAudio` → shared media)
- **Durability:** `verify_phase_producer_durability.sh` PLAY-8/VQ-1 guards + pytest

## Recipe bump

`NORMALIZATION_RECIPE_VERSION` → **v7** invalidates cached `*_normalized.mp4` (intentional).

## Bake button (`Bake final MP4`)

`_run_stitch_bake_core` → `_stitch_build_pipeline` (normalize v7 CRF18+gradfun) → `encode_module_final_lean` (MODULE_FINAL_LEAN_DELIVERY_V3: 1050k/1200k + stronger lean gradfun, ≤60 MB target).

Clicking **Bake** applies the full quality stack — no separate regen step required.

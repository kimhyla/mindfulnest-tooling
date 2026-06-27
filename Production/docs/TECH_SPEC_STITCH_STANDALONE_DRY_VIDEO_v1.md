# TECH_SPEC — STITCH_STANDALONE_DRY_VIDEO_v1

**Classification:** CATEGORY fix — milestone Stitcher must not inherit event-mode mux-gated video playback.

## Problem

Milestone Stitcher showed waveform + slot metadata after Send to Stitcher, but **no video player** until the operator clicked Review. Event-mode hides the slot composer and gates standalone preview on `previewUrls[activePreviewSlot]` (mux/Review pipeline). Waveform uses `video_path` directly; video did not.

## 3×3 debate (summary)

| Agent | Position |
|-------|----------|
| A1 | Auto-click Review on load — reuses mux path |
| A2 | Bind dry `/files?path=` from `video_path` on load (LD-827 parity) |
| A3 | Re-enable full slot composer in standalone mode |
| B1 | A2 — minimal diff, no fake user clicks |
| B2 | A3 — too much event UI in milestone scope |
| B3 | A1 — still hides video when mux build fails |
| C1 | **A2 wins** — one resolver, one `<video>`, Review upgrades to ambient mix |
| C2 | Contract marker `STITCH_STANDALONE_DRY_VIDEO_V1` + unit test |
| C3 | Sibling: enable quiet ambient mux for standalone in follow-up if needed |

## Category fix

- **Resolver:** `resolveStandaloneStitchSlotVideoUrl()` → `resolveSlotPlaybackPreviewUrl(..., 'standalone', ...)`.
- **UI:** Standalone preview `<video src={standaloneVideoSrc}>` when `video_path` present; not gated on Review.
- **Review:** Still builds ambient/SFX mix; replaces src when mux URL available.

## Gates

- Unit: `STITCH_STANDALONE_DRY_VIDEO_V1` in `stitchPersistedPlaybackArtifacts.test.ts`.
- Browser: `data-testid="stitcher-video-player"` visible with `src` containing `/files?path=` after export.

## Out of scope (siblings)

- Auto ambient mux rebuild on standalone load (event mode has mux queue; standalone skips `standaloneMode` in mux effect).
- Footer bake preview before Bake (unchanged).

# Lessons Learned — Phase B Waveform Cue UI + Preview + Export (2026-05-28)

**Date:** 2026-05-28  
**Status:** RESOLVED  
**Locked decisions:** `WAVEFORM_CUE_DUAL_HANDLE_V1`, `WAVEFORM_CUE_DRAG_COMMIT_ON_POINTERUP_V1`, `PREVIEW_OVERLAY_FAST_ENCODER_V1`, `EXPORT_TO_STITCHER_PAYLOAD_V1`  
**Canonical UI:** `Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx`  
**Canonical export:** `PhaseProducer.tsx` → `stitch_save_job` with `{ name, slots: { phase_b: { video_path } } }`

---

## LL-WCU-1 — Right-edge-only resize was not “hard to drag left” — there was no left handle

**What happened:** Kim could expand cue duration forward (right edge) but could not expand the cue **start time** backward.

**Root cause:** `WaveformTimeline` only rendered one `.mn-waveform-cue-block-handle` on the **right** edge.

**Permanent rule:** Red cue blocks MUST expose **two** handles:
- `--left` → adjust `offset_ms` with fixed end time
- `--right` → adjust `duration_ms` with fixed start time

---

## LL-WCU-2 — Persisting cues on every pointermove caused `HTTP 0: Failed to fetch`

**What happened:** Dragging cue edges spammed `v2_module_patch` + `state_snapshot` on every pixel. While ffmpeg preview compositing ran, patch requests failed → `cue patch HTTP 0`.

**Permanent rule:** During drag, update **local draft state only** (`dragDraft` in `WaveformTimeline`). Call `onCueRangeChange` / `persistCues` **once on pointerup**.

---

## LL-WCU-3 — Preview compositing felt “stuck” on first run

**What happened:** `POST /api/phase_b/preview` re-encodes the **full** lipsync clip (132s for Event_1). Cache miss used `-preset slow` → many minutes.

**Permanent rule:** Preview path uses `PREVIEW_OVERLAY_ENCODER_ARGS` (`-preset veryfast`). Final stitch/bake keeps LD-284 `-preset slow`. Fresh preview ≈ 10s on 132s clip; cached ≈ instant.

---

## LL-WCU-4 — “Export to Stitcher” appeared dead

**What happened:** Client sent `{ job_name, slot, video_path }` but server requires `{ name, slots, transitions }`. Server returned `MISSING_JOB_NAME` (400); UI showed stale cue-patch error instead.

**Permanent rule:** Export MUST POST:
```json
{
  "name": "phase_b_Event_1",
  "slots": { "phase_b": { "video_path": "Production/Event_1/phase_b_lipsync_….mp4" } },
  "transitions": []
}
```
Server validates dict-keyed slots (same shape as `scene_assemble` auto-populate).

---

## Regression checklist

- [ ] Red cue block has left + right handles (`data-testid="cue-handle-left-*"`)
- [ ] Dragging handle does NOT POST until mouse release (Network tab: one patch)
- [ ] Preview first miss completes in <60s for 132s lipsync
- [ ] Export shows `✓ Exported to Stitcher → phase_b slot`
- [ ] Stitcher tab shows video on phase_b slot after export

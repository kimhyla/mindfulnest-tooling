# LESSONS LEARNED — Waveform drag-seek regression (2026-06-12)

## LD tag

`WAVEFORM_DRAG_SEEK_V1` (extends 2026-05-25 `0ff0be0`)

## Symptom

Red playhead on Phase A/B waveform snaps back to 0:00 on drag release — on amber cut
region, cue blocks, and open waveform areas.

## Root cause chain

1. **2026-05-25 (`0ff0be0`)** — WaveSurfer v7 `dragToSeek:true` fires `click` with
   drag-start `relativeX` on mouseup → seek to 0. Fix: `interact:false` + custom
   pointer handlers on the WaveSurfer canvas.

2. **2026-05-28 (`8604e4c`)** — Cue overlay added above canvas (`z-index: 5`).
   Canvas handlers no longer receive hits in overlay-covered areas.

3. **2026-06-10 (`c3ab386`)** — Seek handlers moved to `seekLayerRef` inside the
   **same** `useEffect` as `WaveSurfer.create`. Effect ran before `seekLayerRef`
   was populated → `if (!seekLayer) return` exited **without** attaching handlers
   and **without** WS cleanup. Result: zero seek handlers; playhead stuck / snap.

## Durable fix (2026-06-12)

- **Two effects:** (1) mount/destroy WaveSurfer on `audioSrc`; (2) bind seek on
  `wrapperRef` when `isReady === true`.
- **Never** early-return from the WS effect without cleanup.
- **Bind target:** `wrapperRef` (full timeline), not canvas or seek-layer ref.
- **Skip targets:** `.mn-waveform-cue-block`, cue handles, stem-cut handles only.
- **Coords:** track insets `left/right 8px`, `top 28px` match overlay alignment.
- **Regression guard:** `data-current-time-ms` on timeline + marker
  `waveform-seek-layer` in `check_storyboard_critical_features.sh`.

## Do not regress

- Do not re-merge seek bind into WS mount effect.
- Do not bind seek only to canvas (overlay blocks it).
- Do not use `seekLayerRef` without `isReady` in effect deps.

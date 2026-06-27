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
- **Skip targets:** cue handles, stem-cut handles, ▶ Play label only (not cue bodies).
- **Coords:** track insets `left/right 8px`, `top 28px` match overlay alignment.
- **`applySeek`:** always `wsRef.current`, never a closed-over `ws` from effect setup.
- **Seek effect deps:** mirror WS remount deps (`syncPlayUi`, `waveformHeight`,
  `linkedVideoScrubOnly`) so handlers rebind when WaveSurfer recycles.
- **Regression guard:** `data-current-time-ms` on timeline + marker
  `waveform-seek-layer` in `check_storyboard_critical_features.sh`.

## Regression (2026-06-19) — stale `ws` closure + `getDuration()` zero

- **Symptom:** click/drag seek no-op or snaps to ~0.0s; ▶ Play still works.
- **Cause A:** `STITCH_UNIFIED_PLAYBACK_V1` WS remount deps; seek handlers used
  closed-over destroyed `ws` (`wsRef.current` fix).
- **Cause B:** `applySeek` used `ws.getDuration()` which can be `0` while
  `data-loaded-duration-ms` is already set — `setCurrentMs(rel * 0)`.
- **Cause C:** `onSeeking` ran after `seekTo()` with `getCurrentTime()===0` and
  overwrote applySeek (`t * 1000 === 0` when duration was decoded).
- **Fix:** `applySeek` reads `wsRef.current` + `timelineDurationMsRef`; seek
  effect deps mirror WS remount keys; `msFromWsClock` returns `null` when `t<=0`.

## Regression (2026-06-19) — Phase A stitched MP4 on waveform

- **Symptom:** Phase A drag flashes 0.0s → brief position → 0.0s on release.
- **Cause:** `priorityAudioFileForPhase` forced `phase_a_stitched_*.mp4` onto the
  waveform while the preview `<video>` synced the same file via `linkedVideo`.
  `onSeeking` + `ws.getCurrentTime()` stale clock fought `applySeek`.
- **Fix (SEEK-5/6):** Waveform uses `priorityAudioFile` only (stem when
  `lipsync_requires_regen`); stitched stays on preview video. `isDraggingSeekRef`,
  capture-phase handlers, `linkedVideoTimeS()` from `lastScrubMsRef`.

## Regression (2026-06-19) — watercolor cue blocks swallow drag-seek

- **Symptom:** play → pause → drag snaps back to pause position or 0.0s on Event_1
  (5111) with watercolor cues; click-to-seek at uncued positions still works.
- **Cause:** `.mn-waveform-cue-block { pointer-events: auto }` covered most of
  the waveform on Event_1; `shouldSkipSeek` returned early when `e.target` was a
  cue block → `isDragging` never set → drag was a no-op.
- **Fix (SEEK-4):** cue block body `pointer-events: none` (stem-trim pattern);
  handles + `.mn-waveform-cue-popover-hit` stay `auto`; remove cue-block from
  `shouldSkipSeek` skip list (handles still skipped).

**Paired rule (WAVEFORM_CUE_HANDLE_V1):** Any commit that sets
`.mn-waveform-cue-block { pointer-events: none }` **must** also set
`.mn-waveform-cue-block-handle { pointer-events: auto }` in the **same**
change. Partial stem-trim copy regresses cue resize (Jun 19 `374d4ef`).
Guarded by `CUE-RESIZE-*` Playwright tests + `verify_phase_waveform_play_durability.sh`.

## Regression (2026-06-19) — stale WS clock + Phase A stitched fight

- **Symptom:** drag release flashes 0.0s then maybe correct position; play→pause→drag worst.
- **Cause A:** `onSeeking` overwrote `applySeek` with `ws.getCurrentTime()` still at 0 on lipsync/mp4.
- **Cause B:** `applySeek` used `ws.getDuration()` which can be 0 while `data-loaded-duration-ms` is set.
- **Cause C:** Phase A waveform loaded stitched MP4 while linked preview video synced same file — dual seek fight.
- **Cause D:** cue overlay bodies had `pointer-events:auto` — drag over cues was a no-op on Phase B.
- **Fix:** `timelineDurationMsRef` + `lastScrubMsRef` + `isDraggingSeekRef`; capture-phase handlers on `wrapperRef`; cue bodies `pointer-events:none`; waveform audio uses `priorityAudioFile` only (stitched stays on preview `<video>`).

- Do not re-merge seek bind into WS mount effect.
- Do not bind seek only to canvas (overlay blocks it).
- Do not use `seekLayerRef` without `isReady` in effect deps.
- Do not close over `ws` in drag-seek handlers — use `wsRef.current`.
- Do not set `pointer-events: auto` on full-width cue block bodies.

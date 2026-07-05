/**
 * WAVEFORM_SEEK_CONTROLLER_V1 — pointer drag-seek isolated from WaveSurfer mount.
 * Must never live in the same useEffect as WaveSurfer.create (WAVEFORM_DRAG_SEEK_V1).
 */
import type WaveSurfer from 'wavesurfer.js';
import { timelineRelXFromClientX, type WaveformTimeAuthority } from './waveformTimeAuthority.ts';

export const WAVEFORM_SEEK_CONTROLLER_V1 = 'WAVEFORM_SEEK_CONTROLLER_V1';
export const WAVEFORM_DRAG_SEEK_BOUND = 'WAVEFORM_DRAG_SEEK_V2';

const SEEK_SKIP_SELECTOR =
  '.mn-waveform-source-label, .mn-waveform-cue-drag-body, .mn-waveform-cue-block-handle, .mn-waveform-cue-popover-hit, .mn-waveform-stem-trim-handle';

export type WaveformSeekControllerBindings = {
  wrapper: HTMLElement;
  wsRef: { current: WaveSurfer | null };
  timeAuthority: WaveformTimeAuthority;
  isDraggingSeekRef: { current: boolean };
  lastScrubMsRef: { current: number | null };
  linkedVideoRef: { current: { current: HTMLVideoElement | null } | null | undefined };
  useSharedLinkedMediaRef: { current: boolean };
  onWaveformClickRef: { current: ((timeMs: number) => void) | undefined };
  withLinkedVideoSuppress: (fn: () => void) => void;
  publishPlayheadMs: (ms: number) => void;
  resolveDurationMs: () => number;
  displayOnly: boolean;
  onMasterSeek?: ((ms: number) => void) | undefined;
};

export function shouldSkipWaveformSeek(target: EventTarget | null): boolean {
  if (!target || typeof HTMLElement === 'undefined') return false;
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest(SEEK_SKIP_SELECTOR));
}

/** Bind capture-phase drag-seek on wrapper; returns cleanup. */
export function bindWaveformSeekController(
  bindings: WaveformSeekControllerBindings,
): () => void {
  const {
    wrapper,
    wsRef,
    timeAuthority,
    isDraggingSeekRef,
    lastScrubMsRef,
    linkedVideoRef,
    useSharedLinkedMediaRef,
    onWaveformClickRef,
    withLinkedVideoSuppress,
    publishPlayheadMs,
    resolveDurationMs,
    displayOnly,
    onMasterSeek,
  } = bindings;

  let seekPointerId: number | null = null;

  const applySeekAtMs = (ms: number, durMs: number) => {
    const live = wsRef.current;
    if (!live || durMs <= 0) return;
    const rel = Math.max(0, Math.min(1, ms / durMs));
    lastScrubMsRef.current = ms;
    timeAuthority.scrubToMs(ms);
    publishPlayheadMs(ms);
    live.seekTo(rel);
    if (displayOnly) {
      onMasterSeek?.(ms);
      return;
    }
    const lv = linkedVideoRef.current?.current;
    if (lv && useSharedLinkedMediaRef.current) {
      withLinkedVideoSuppress(() => {
        lv.muted = false;
        try {
          lv.currentTime = ms / 1000;
        } catch {
          // ignore seek on unloaded media
        }
      });
    } else if (lv && !useSharedLinkedMediaRef.current) {
      withLinkedVideoSuppress(() => {
        lv.muted = true;
        try {
          lv.currentTime = ms / 1000;
        } catch {
          // ignore seek on unloaded media
        }
      });
    }
  };

  const applySeek = (rel: number, durOverrideMs?: number) => {
    const durMs = durOverrideMs ?? resolveDurationMs();
    if (durMs <= 0) return;
    applySeekAtMs(rel * durMs, durMs);
  };

  const getRelX = (e: PointerEvent): number => {
    const box = wrapper.getBoundingClientRect();
    return timelineRelXFromClientX(box, e.clientX);
  };

  const onPointerDown = (e: PointerEvent) => {
    if (shouldSkipWaveformSeek(e.target)) return;
    const live = wsRef.current;
    const durMs = resolveDurationMs();
    if (!live || durMs <= 0) return;
    isDraggingSeekRef.current = true;
    timeAuthority.beginDragSeek();
    seekPointerId = e.pointerId;
    wrapper.setPointerCapture(e.pointerId);
    applySeek(getRelX(e));
  };

  const onPointerMove = (e: PointerEvent) => {
    if (!isDraggingSeekRef.current || e.pointerId !== seekPointerId) return;
    applySeek(getRelX(e));
  };

  const endDragSeek = (rel: number) => {
    let durMs = resolveDurationMs();
    // WTA-12: resolveDurationMs() can briefly read 0 on release while move scrub succeeded —
    // endDragSeek(0) was zeroing authority and snapping the label to 0.0s.
    let ms =
      durMs > 0
        ? rel * durMs
        : (lastScrubMsRef.current ?? timeAuthority.getPlayheadMs());
    if (ms <= 0) {
      seekPointerId = null;
      isDraggingSeekRef.current = false;
      timeAuthority.setDraggingSeek(false);
      return;
    }
    if (durMs <= 0) {
      durMs = timeAuthority.getDurationMs() || ms;
      rel = durMs > 0 ? ms / durMs : rel;
    }
    applySeekAtMs(ms, durMs);
    onWaveformClickRef.current?.(ms);
    // Defer authority release until after WS internal seeking/click handlers (WTA-12).
    requestAnimationFrame(() => {
      applySeekAtMs(ms, durMs);
      timeAuthority.endDragSeek(ms);
      requestAnimationFrame(() => {
        applySeekAtMs(ms, durMs);
        isDraggingSeekRef.current = false;
        timeAuthority.setDraggingSeek(false);
      });
    });
  };

  const onPointerUp = (e: PointerEvent) => {
    if (!isDraggingSeekRef.current || e.pointerId !== seekPointerId) return;
    seekPointerId = null;
    endDragSeek(getRelX(e));
  };

  const onPointerCancel = (e: PointerEvent) => {
    if (seekPointerId !== null && e.pointerId !== seekPointerId) return;
    seekPointerId = null;
    isDraggingSeekRef.current = false;
    timeAuthority.setDraggingSeek(false);
  };

  wrapper.addEventListener('pointerdown', onPointerDown, true);
  wrapper.addEventListener('pointermove', onPointerMove, true);
  wrapper.addEventListener('pointerup', onPointerUp, true);
  wrapper.addEventListener('pointercancel', onPointerCancel, true);
  wrapper.setAttribute('data-drag-seek-bound', WAVEFORM_DRAG_SEEK_BOUND);

  return () => {
    wrapper.removeAttribute('data-drag-seek-bound');
    wrapper.removeEventListener('pointerdown', onPointerDown, true);
    wrapper.removeEventListener('pointermove', onPointerMove, true);
    wrapper.removeEventListener('pointerup', onPointerUp, true);
    wrapper.removeEventListener('pointercancel', onPointerCancel, true);
  };
}

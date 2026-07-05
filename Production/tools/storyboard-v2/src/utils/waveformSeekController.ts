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

  const applySeek = (rel: number) => {
    const live = wsRef.current;
    const durMs = resolveDurationMs();
    if (!live || durMs <= 0) return;
    const ms = rel * durMs;
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
    const durMs = resolveDurationMs();
    const ms = rel * durMs;
    applySeek(rel);
    timeAuthority.endDragSeek(ms);
    onWaveformClickRef.current?.(ms);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
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

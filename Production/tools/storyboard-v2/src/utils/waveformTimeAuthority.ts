/**
 * WAVEFORM_TIME_AUTHORITY_V1 — single playhead/duration authority for WaveformTimeline.
 * E3 track: closes WTA-017 remount reset class + paused drag snap-to-0 (WTA-001).
 */
export const WAVEFORM_TIME_AUTHORITY_V1 = 'WAVEFORM_TIME_AUTHORITY_V1';
/** Ignore stale WS/video clocks at 0 for this long after drag release (ms). */
export const PAUSED_SCRUB_HOLD_MS = 750;
/** Must match WaveformTimeline track insets (cue overlay alignment). */
export const WAVEFORM_TRACK_INSET_PX = 8;

/** Single X→rel mapping for seek, drop, and cue-handle drag (WTA-5). */
export function timelineRelXFromClientX(
  box: Pick<DOMRect, 'left' | 'width'>,
  clientX: number,
): number {
  const trackLeft = box.left + WAVEFORM_TRACK_INSET_PX;
  const trackWidth = box.width - WAVEFORM_TRACK_INSET_PX * 2;
  if (trackWidth <= 0) return 0;
  return Math.max(0, Math.min(1, (clientX - trackLeft) / trackWidth));
}

export interface WaveformTimeAuthority {
  getPlayheadMs(): number;
  getDurationMs(): number;
  setDurationMs(ms: number): void;
  scrubToMs(ms: number): void;
  preserveAcrossRemount(): number;
  restoreAfterRemount(): number;
  onPlaybackStart(): void;
  isDraggingSeek(): boolean;
  setDraggingSeek(v: boolean): void;
  beginDragSeek(): void;
  endDragSeek(ms: number): void;
  /** WTA-1 — while paused, prefer authority over stale media clocks reporting 0. */
  resolvePausedPlayheadMs(mediaTimeMs: number, legacyScrubMs?: number | null): number;
}

export function createWaveformTimeAuthority(
  initialPlayheadMs = 0,
  initialDurationMs = 0,
  now: () => number = () => Date.now(),
): WaveformTimeAuthority {
  let playheadMs = initialPlayheadMs;
  let durationMs = initialDurationMs;
  let preservedMs = 0;
  let userSeekedToZero = false;
  let draggingSeek = false;
  let pausedScrubHoldUntil = 0;

  const clampPlayhead = (ms: number): number => {
    if (durationMs > 0) return Math.max(0, Math.min(durationMs, ms));
    return Math.max(0, ms);
  };

  return {
    getPlayheadMs: () => playheadMs,
    getDurationMs: () => durationMs,
    setDurationMs(ms: number) {
      durationMs = ms;
    },
    scrubToMs(ms: number) {
      const clamped = clampPlayhead(ms);
      playheadMs = clamped;
      if (clamped <= 0) userSeekedToZero = true;
    },
    preserveAcrossRemount() {
      preservedMs = userSeekedToZero ? 0 : playheadMs;
      return preservedMs;
    },
    restoreAfterRemount() {
      if (preservedMs > 0 && !userSeekedToZero) {
        playheadMs = preservedMs;
      }
      return playheadMs;
    },
    onPlaybackStart() {
      userSeekedToZero = false;
      pausedScrubHoldUntil = 0;
    },
    isDraggingSeek: () => draggingSeek,
    setDraggingSeek(v: boolean) {
      draggingSeek = v;
    },
    beginDragSeek() {
      draggingSeek = true;
    },
    endDragSeek(ms: number) {
      draggingSeek = false;
      const clamped = clampPlayhead(ms);
      playheadMs = clamped;
      if (clamped <= 0) userSeekedToZero = true;
      pausedScrubHoldUntil = now() + PAUSED_SCRUB_HOLD_MS;
    },
    resolvePausedPlayheadMs(mediaTimeMs: number, legacyScrubMs?: number | null): number {
      if (draggingSeek) return playheadMs;
      const legacy = legacyScrubMs ?? null;
      if (legacy != null && legacy > 0) return legacy;
      if (playheadMs > 0 && mediaTimeMs < 50) return playheadMs;
      if (now() < pausedScrubHoldUntil && playheadMs > 0) return playheadMs;
      if (mediaTimeMs > 0) return mediaTimeMs;
      return playheadMs;
    },
  };
}

/**
 * WAVEFORM_TIME_AUTHORITY_V1 — single playhead/duration authority for WaveformTimeline.
 * E3 track: closes WTA-017 remount reset class.
 */
export const WAVEFORM_TIME_AUTHORITY_V1 = 'WAVEFORM_TIME_AUTHORITY_V1';
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
}

export function createWaveformTimeAuthority(
  initialPlayheadMs = 0,
  initialDurationMs = 0,
): WaveformTimeAuthority {
  let playheadMs = initialPlayheadMs;
  let durationMs = initialDurationMs;
  let preservedMs = 0;
  let userSeekedToZero = false;
  let draggingSeek = false;

  return {
    getPlayheadMs: () => playheadMs,
    getDurationMs: () => durationMs,
    setDurationMs(ms: number) {
      durationMs = ms;
    },
    scrubToMs(ms: number) {
      const clamped = durationMs > 0
        ? Math.max(0, Math.min(durationMs, ms))
        : Math.max(0, ms);
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
      // Paused scrub authority cleared when playback starts (PLAY path).
      userSeekedToZero = false;
    },
    isDraggingSeek: () => draggingSeek,
    setDraggingSeek(v: boolean) {
      draggingSeek = v;
    },
  };
}

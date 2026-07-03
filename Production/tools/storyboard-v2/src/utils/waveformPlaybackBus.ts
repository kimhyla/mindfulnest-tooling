import { stopAllStitchClientMix } from '../audio/StitchSlotAudioMixEngine';

/** Coordinates Phase A/B waveform players (only one should play at a time).
 *  PHASE_WAVEFORM_PLAY + PHASE_PRODUCER_AB — keep-alive mounts both panes. */
export type PlaybackControl = {
  readonly busId: symbol;
  pause: () => void;
};

const controls = new Map<symbol, PlaybackControl>();

export function registerWaveformPlaybackControl(c: PlaybackControl): () => void {
  controls.set(c.busId, c);
  return () => {
    controls.delete(c.busId);
  };
}

export function pauseOtherWaveformPlayback(except: PlaybackControl): void {
  for (const c of controls.values()) {
    if (c.busId !== except.busId) c.pause();
  }
}

/** Pause every mounted Phase A/B waveform (hidden keep-alive panes included). */
export function pauseAllWaveformPlayback(): void {
  for (const c of controls.values()) c.pause();
}

/** Pause waveforms + linked preview media without resetting playhead (▶/⏸ toggle). */
export function pauseAllPhasePlayback(): void {
  pauseAllWaveformPlayback();
  pauseAppMediaElements(false);
}

/** WaveSurfer + preview media app-wide; resets playhead (tab / Stop audio). */
export function stopAllPhasePlayback(): void {
  pauseAllWaveformPlayback();
  stopAllStitchClientMix();
  pauseAppMediaElements(true);
  composerPoolRefPauseAll?.();
}

/** Optional hook — Stitcher registers pool pause on mount. */
let composerPoolRefPauseAll: (() => void) | null = null;

export function registerStitchComposerPoolPause(fn: (() => void) | null): void {
  composerPoolRefPauseAll = fn;
}

function pauseAppMediaElements(resetTime: boolean): void {
  if (typeof document === 'undefined') return;
  document
    .querySelectorAll(
      '.mn-tab-pane-keepalive video, .mn-tab-pane-keepalive audio, ' +
        '.mn-stitcher-pane video, .mn-stitcher-pane audio, ' +
        '.mn-stitcher-ambient-bed-audio, ' +
        '.mn-library-preview-audio',
    )
    .forEach((el) => {
      if (!(el instanceof HTMLMediaElement)) return;
      el.pause();
      if (!resetTime) return;
      try {
        el.currentTime = 0;
      } catch {
        // ignore seek errors on unloaded media
      }
    });
}

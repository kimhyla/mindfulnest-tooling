/** Coordinates Phase A/B waveform players (only one should play at a time). */
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
  if (typeof document === 'undefined') return;
  document.querySelectorAll('.mn-tab-pane-keepalive video, .mn-tab-pane-keepalive audio').forEach((el) => {
    if (el instanceof HTMLMediaElement) el.pause();
  });
}

/** WaveSurfer + linked preview videos in hidden keep-alive panes; resets playhead (tab / Stop audio). */
export function stopAllPhasePlayback(): void {
  pauseAllWaveformPlayback();
  if (typeof document === 'undefined') return;
  document.querySelectorAll('.mn-tab-pane-keepalive video, .mn-tab-pane-keepalive audio').forEach((el) => {
    if (el instanceof HTMLMediaElement) {
      el.pause();
      try {
        el.currentTime = 0;
      } catch {
        // ignore seek errors on unloaded media
      }
    }
  });
}

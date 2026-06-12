/** Coordinates Phase A/B waveform players (only one should play at a time). */
type PlaybackControl = { pause: () => void };

const controls = new Set<PlaybackControl>();

export function registerWaveformPlaybackControl(c: PlaybackControl): () => void {
  controls.add(c);
  return () => {
    controls.delete(c);
  };
}

export function pauseOtherWaveformPlayback(except: PlaybackControl): void {
  for (const c of controls) {
    if (c !== except) c.pause();
  }
}

/** Stop every mounted Phase A/B waveform (hidden keep-alive panes included). */
export function pauseAllWaveformPlayback(): void {
  for (const c of controls) c.pause();
}

/** WaveSurfer + linked preview videos in hidden keep-alive panes. */
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

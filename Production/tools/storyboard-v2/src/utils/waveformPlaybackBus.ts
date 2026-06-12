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

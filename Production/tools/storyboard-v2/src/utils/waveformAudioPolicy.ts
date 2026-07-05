/**
 * WAVEFORM_AUDIO_POLICY_V1 — separate waveform decode from preview video (SEEK-5/6).
 * Waveform must never share a video element clock with the preview player when filenames
 * differ; stitched MP4 stays on preview <video> for LD-829 single-player UX.
 */
export const WAVEFORM_AUDIO_POLICY_V1 = 'WAVEFORM_AUDIO_POLICY_V1';

export type WaveformAudioSource = {
  name: string;
  label: 'lipsync' | 'mixed' | 'stem' | 'stitched';
};

export type PhaseStateSliceLike = {
  voice_stem_file?: string;
  voice_stem_mtime?: number;
  lipsync_file?: string;
  lipsync_requires_regen?: boolean;
  lipsync_status?: string;
  lipsync_mtime?: number;
  mixed_audio_file?: string;
  stitched_file?: string;
  stitched_mtime?: number;
};

function lipsyncStale(slice: PhaseStateSliceLike): boolean {
  const stemMtime = slice.voice_stem_mtime ?? 0;
  const lipsyncMtime = slice.lipsync_mtime ?? 0;
  return (
    Boolean(slice.lipsync_requires_regen) ||
    (slice.lipsync_status?.startsWith('error:') ?? false) ||
    slice.lipsync_status === 'qa_failed' ||
    (stemMtime > 0 && lipsyncMtime > 0 && stemMtime > lipsyncMtime)
  );
}

/** Stem/lipsync/mixed priority — never prefers stitched (SEEK-5). */
export function waveformAudioFromSlice(
  slice: PhaseStateSliceLike,
): WaveformAudioSource | null {
  if (slice.voice_stem_file && lipsyncStale(slice)) {
    return { name: slice.voice_stem_file, label: 'stem' };
  }
  if (slice.lipsync_file && !lipsyncStale(slice)) {
    return { name: slice.lipsync_file, label: 'lipsync' };
  }
  if (slice.mixed_audio_file) {
    return { name: slice.mixed_audio_file, label: 'mixed' };
  }
  if (slice.voice_stem_file) {
    return { name: slice.voice_stem_file, label: 'stem' };
  }
  if (slice.lipsync_file) {
    return { name: slice.lipsync_file, label: 'lipsync' };
  }
  return null;
}

/**
 * Waveform decode source for Phase A/B producers.
 * SEEK-5: never stitched — LD-829 stitched stays on preview <video> only.
 */
export function waveformAudioForPhase(
  slice: PhaseStateSliceLike,
  _phase: 'a' | 'b',
): WaveformAudioSource | null {
  return waveformAudioFromSlice(slice);
}

/** True when waveform and linked preview decode the same file (shared media path). */
export function linkedMediaMatchesWaveform(
  waveformFilename: string | null | undefined,
  previewFilename: string | null | undefined,
  sameFilename: (a: string, b: string) => boolean,
): boolean {
  if (!waveformFilename || !previewFilename) return false;
  return sameFilename(waveformFilename, previewFilename);
}

/**
 * WAVEFORM_INTERACTION_POLICY_V1 — loud-failure guards for drop/seek/cue (WTA-5 / WTA-INV-6).
 * Centralizes readiness checks so WaveformTimeline does not silently return on durMs <= 0.
 */
export const WAVEFORM_INTERACTION_POLICY_V1 = 'WAVEFORM_INTERACTION_POLICY_V1';

export type WaveformInteractionRejectReason =
  | 'waveform_loading'
  | 'no_duration'
  | 'no_surface';

export type WaveformInteractionReadyInput = {
  isReady: boolean;
  durationMs: number;
  hasAudioSrc: boolean;
  displayOnly?: boolean;
  hasDisplayPeaks?: boolean;
  /** Stitcher SFX strip — fallbackDurationMs only, no WaveSurfer decode (S5.5g G3). */
  dropOnlyWithDuration?: boolean;
};

export type WaveformInteractionAssessment =
  | { ok: true; durationMs: number }
  | { ok: false; reason: WaveformInteractionRejectReason; userMessage: string };

export function assessWaveformInteractionReady(
  input: WaveformInteractionReadyInput,
): WaveformInteractionAssessment {
  const dropOnlyReady = input.dropOnlyWithDuration === true && input.durationMs > 0;
  const hasSurface =
    input.hasAudioSrc
    || (input.displayOnly === true && input.hasDisplayPeaks === true)
    || dropOnlyReady;
  if (!hasSurface) {
    return {
      ok: false,
      reason: 'no_surface',
      userMessage: 'No audio on the waveform yet — generate a stem or load lipsync first.',
    };
  }
  if (!input.isReady && !dropOnlyReady) {
    return {
      ok: false,
      reason: 'waveform_loading',
      userMessage: 'Waveform is still loading — wait a moment, then drop again.',
    };
  }
  if (input.durationMs <= 0) {
    return {
      ok: false,
      reason: 'no_duration',
      userMessage: 'Timeline duration not ready — wait for the waveform to finish loading.',
    };
  }
  return { ok: true, durationMs: input.durationMs };
}

/** Operator-facing copy for toast when HTML5 drop is rejected (WTA-5). */
export function waveformDropRejectMessage(reason: WaveformInteractionRejectReason): string {
  switch (reason) {
    case 'waveform_loading':
      return 'Drop skipped — waveform still loading. Try again in a second.';
    case 'no_duration':
      return 'Drop skipped — timeline length not ready yet (often right after Generate stem).';
    case 'no_surface':
      return 'Drop skipped — no audio on this timeline yet.';
    default:
      return 'Drop skipped — waveform not ready.';
  }
}

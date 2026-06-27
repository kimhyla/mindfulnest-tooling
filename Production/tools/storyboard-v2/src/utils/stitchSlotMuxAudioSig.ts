/** Fingerprint slot ambient + SFX geometry for mux invalidation (STITCH_SLOT_MEDIA_ARTIFACTS_V1). */
import { STITCH_AMBIENT_LOOP_SIG_V1 } from './stitchConstants';

export const STITCH_SLOT_MUX_AUDIO_SIG_V1 = 'STITCH_SLOT_MUX_AUDIO_SIG_V1';
export const STITCH_SLOT_MEDIA_ARTIFACTS_V1 = 'STITCH_SLOT_MEDIA_ARTIFACTS_V1';
/** STITCH_SLOT_LIVE_GEOMETRY_SIG_V1 — always derived from cues/ambient; never prefer stale mix_sig. */
export const STITCH_SLOT_LIVE_GEOMETRY_SIG_V1 = 'STITCH_SLOT_LIVE_GEOMETRY_SIG_V1';

/** STITCH_AMBIENT_BAKE_ON_SAVE_V1 — ambient baked on save; mux preview only when SFX present. */
export const STITCH_AMBIENT_BAKE_ON_SAVE_V1 = 'STITCH_AMBIENT_BAKE_ON_SAVE_V1';

export interface StitchSlotMuxSigInput {
  video_path?: string;
  mix_sig?: string;
  ambient_mix_sig?: string;
  ambient_mix_hash?: string;
  ambient_bed?: string;
  ambient_bed_path?: string;
  ambient_volume?: number;
  sfx_cues?: ReadonlyArray<{
    id?: string;
    offset_ms?: number;
    duration_ms?: number;
    volume?: number;
    fadein_ms?: number;
    fadeout_ms?: number;
    source_path?: string;
    name?: string;
  }>;
}

function sfxCueGeometryParts(
  cues: StitchSlotMuxSigInput['sfx_cues'],
): string {
  return (cues ?? [])
    .filter((c): c is NonNullable<typeof c> => Boolean(c && typeof c === 'object'))
    .map((c) => [
      c.id ?? '',
      c.offset_ms ?? 0,
      c.duration_ms ?? '',
      c.volume ?? '',
      c.fadein_ms ?? '',
      c.fadeout_ms ?? '',
      c.source_path ?? '',
      c.name ?? '',
    ].join(':'))
    .sort()
    .join('|');
}

export function stitchSlotLiveAmbientSig(
  slot: StitchSlotMuxSigInput | null | undefined,
): string {
  if (!slot) return '';
  const ambient = (slot.ambient_bed_path || slot.ambient_bed || '').trim();
  const vol = slot.ambient_volume ?? '';
  const videoPath = (slot.video_path ?? '').trim();
  return `${STITCH_AMBIENT_LOOP_SIG_V1}#${videoPath}#${ambient}@${vol}`;
}

/**
 * Live mix geometry fingerprint — ambient + sfx_cues (+ video path).
 * Used for session invalidation and remux triggers; ignores persisted mix_sig.
 */
export function stitchSlotLiveGeometrySig(
  slot: StitchSlotMuxSigInput | null | undefined,
): string {
  if (!slot) return '';
  const ambient = (slot.ambient_bed_path || slot.ambient_bed || '').trim();
  const vol = slot.ambient_volume ?? '';
  const videoPath = (slot.video_path ?? '').trim();
  return `${STITCH_AMBIENT_LOOP_SIG_V1}#${videoPath}#${ambient}@${vol}#${sfxCueGeometryParts(slot.sfx_cues)}`;
}

/** @deprecated Prefer stitchSlotLiveGeometrySig — kept for call-site compatibility. */
export function stitchSlotMuxAudioSig(
  slot: StitchSlotMuxSigInput | null | undefined,
): string {
  return stitchSlotLiveGeometrySig(slot);
}

/** True when slot has SFX cues requiring mux preview (speech + ambient + SFX). */
export function stitchSlotRequiresMuxedPreview(
  slot: StitchSlotMuxSigInput | null | undefined,
): boolean {
  if (!slot) return false;
  return (slot.sfx_cues ?? []).some((c) => Boolean(c && typeof c === 'object'));
}

/** True when slot has ambient bed but no SFX — uses baked ambient mix, not mux. */
export function stitchSlotRequiresAmbientMix(
  slot: StitchSlotMuxSigInput | null | undefined,
): boolean {
  if (!slot) return false;
  const hasAmbient = Boolean((slot.ambient_bed_path || slot.ambient_bed || '').trim());
  return hasAmbient && !stitchSlotRequiresMuxedPreview(slot);
}

/** Speech-only waveform identity (video path only — no ambient/SFX). */
export function stitchSlotSpeechPeaksSig(
  videoPath: string | undefined,
): string {
  return (videoPath ?? '').trim();
}

/** Drop persisted server artifact fields after geometry edit (client mirror of server clear). */
export function stripStaleStitchSlotArtifacts<T extends StitchSlotMuxSigInput>(
  slot: T,
): T {
  const next = { ...slot } as T & Record<string, unknown>;
  delete next.mix_sig;
  delete next['ambient_mix_sig'];
  delete next['ambient_mix_hash'];
  delete next['ambient_mix_duration_ms'];
  delete next['ambient_mix_video_path'];
  delete next['ambient_mix_video_mtime_ms'];
  delete next['mux_preview_hash'];
  delete next['mux_preview_duration_ms'];
  delete next['mux_video_path'];
  delete next['mux_video_mtime_ms'];
  delete next['waveform_peaks_hash'];
  delete next['waveform_peaks_duration_s'];
  delete next['media_artifacts_built_at'];
  delete next['_mux_preview_url'];
  delete next['_waveform_peaks_url'];
  delete next['_ambient_mix_url'];
  return next as T;
}

export function stitchSlotGeometryChanged(
  prev: StitchSlotMuxSigInput | null | undefined,
  next: StitchSlotMuxSigInput | null | undefined,
): boolean {
  return stitchSlotLiveGeometrySig(prev) !== stitchSlotLiveGeometrySig(next);
}

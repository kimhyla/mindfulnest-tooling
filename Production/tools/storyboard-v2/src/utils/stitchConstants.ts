/** STITCH_AMBIENT_BED_VOLUME — canonical 0.15 under-speech bed (all stitch slots). */
export const STITCH_AMBIENT_BED_VOLUME = 0.15 as const;

/** STITCH_SFX_CUE_DEFAULT_VOLUME — canonical delivery SFX level (all stitch slots). */
export const STITCH_SFX_CUE_DEFAULT_VOLUME = 0.45 as const;
export const STITCH_SFX_CUE_DEFAULT_FADEIN_MS = 300 as const;
export const STITCH_SFX_CUE_DEFAULT_FADEOUT_MS = 1200 as const;

/** STITCH_SLOT_AUDIO_MIX_V1 — server-side normalize_slot_audio_mix_levels for all four slots. */
export const STITCH_SLOT_AUDIO_MIX_V1 = 'STITCH_SLOT_AUDIO_MIX_V1' as const;

/** STITCH_DEFAULT_AMBIENT_BEDS_V1 — canonical preset_id per stitch slot (auto-applied on export/load). */
export const STITCH_DEFAULT_AMBIENT_BEDS_V1 = 'STITCH_DEFAULT_AMBIENT_BEDS_V1' as const;

export type StitchSlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution';

/** Canonical ambient bed preset_id per slot — mirrors stitch_editor.py STITCH_DEFAULT_AMBIENT_BEDS. */
export const STITCH_DEFAULT_AMBIENT_BEDS: Record<StitchSlotKey, string> = {
  intro: 'Intro video ambient bed',
  phase_a: 'ambient bed pretty option2',
  phase_b: 'ambient bed pretty option',
  resolution: 'ambien bed pretty option4',
};

export function defaultAmbientBedForSlot(slotKey: StitchSlotKey): string {
  return STITCH_DEFAULT_AMBIENT_BEDS[slotKey];
}

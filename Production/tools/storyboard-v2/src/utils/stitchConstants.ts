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

/** STITCH_AMBIENT_VOLUME_PERSIST_V1 — client mirrors server 0.15 clamp on every slot with a bed. */
export const STITCH_AMBIENT_VOLUME_PERSIST_V1 = 'STITCH_AMBIENT_VOLUME_PERSIST_V1' as const;

/** STITCH_SLOT_CANONICAL_DEFAULTS_V1 — ambient beds + tail SFX auto-materialized on load/export. */
export const STITCH_SLOT_CANONICAL_DEFAULTS_V1 = 'STITCH_SLOT_CANONICAL_DEFAULTS_V1' as const;

/** STITCH_CANONICAL_DEFAULTS_PERSIST_V1 — client persists when server or client backfills defaults. */
export const STITCH_CANONICAL_DEFAULTS_PERSIST_V1 = 'STITCH_CANONICAL_DEFAULTS_PERSIST_V1' as const;

/** STITCH_AMBIENT_SELECT_HYDRATE_V1 — select options include saved beds before catalog fetch completes. */
export const STITCH_AMBIENT_SELECT_HYDRATE_V1 = 'STITCH_AMBIENT_SELECT_HYDRATE_V1' as const;

/** Mirrors server ambient_loop_sig_token() — busts client session cache when loop bake changes. */
export const STITCH_AMBIENT_LOOP_SIG_V1 =
  'STITCH_AMBIENT_LOOP_TRIM_V2:STITCH_AMBIENT_LOOP_XFADE_V1:STITCH_AMBIENT_BED_MIX_FADE_IN_V1:STITCH_AMBIENT_BED_SLOT_FADE_OUT_V1:2.500:0.500:0.750:no_hard_aloop_v1' as const;

export type StitchSlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution' | 'standalone';

/** Canonical ambient bed preset_id per slot — mirrors stitch_editor.py STITCH_DEFAULT_AMBIENT_BEDS. */
export const STITCH_DEFAULT_AMBIENT_BEDS: Record<StitchSlotKey, string> = {
  intro: 'Intro video ambient bed',
  standalone: 'Intro video ambient bed',
  phase_a: 'ambient bed pretty option2',
  phase_b: 'ambient bed pretty option',
  resolution: 'ambien bed pretty option4',
};

export function defaultAmbientBedForSlot(slotKey: StitchSlotKey): string {
  return STITCH_DEFAULT_AMBIENT_BEDS[slotKey];
}

/** STITCH_COMPOSER_PLAYBACK_OWNER_V1 — muxed <video> owns audio; bus/keep-alive must not pause it. */
export const STITCH_COMPOSER_PLAYBACK_OWNER_V1 = 'STITCH_COMPOSER_PLAYBACK_OWNER_V1' as const;

export function isStitchComposerPlaybackOwner(el: Element): boolean {
  if (!(el instanceof HTMLMediaElement)) return false;
  return (
    el.getAttribute('data-testid') === 'stitcher-composer-video'
    || el.getAttribute('data-stitch-composer-playback-owner') === STITCH_COMPOSER_PLAYBACK_OWNER_V1
  );
}

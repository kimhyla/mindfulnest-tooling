/** STITCH_SLOT_EDIT_DISPATCH_V1 — client edit_kind hint for stitch_save_job. */

import {
  stitchSlotLiveAmbientSig,
  stitchSlotLiveGeometrySig,
  type StitchSlotMuxSigInput,
} from './stitchSlotMuxAudioSig';

export const STITCH_SLOT_EDIT_DISPATCH_V1 = 'STITCH_SLOT_EDIT_DISPATCH_V1';

export const EDIT_KIND_SFX_GEOMETRY = 'sfx_geometry';
export const EDIT_KIND_AMBIENT_GEOMETRY = 'ambient_geometry';
export const EDIT_KIND_MIXED_GEOMETRY = 'mixed_geometry';
export const EDIT_KIND_VIDEO_LINEAGE = 'video_lineage';
export const EDIT_KIND_METADATA = 'metadata';

export type StitchEditKind =
  | typeof EDIT_KIND_SFX_GEOMETRY
  | typeof EDIT_KIND_AMBIENT_GEOMETRY
  | typeof EDIT_KIND_MIXED_GEOMETRY
  | typeof EDIT_KIND_VIDEO_LINEAGE
  | typeof EDIT_KIND_METADATA;

function sfxOnlySig(slot: StitchSlotMuxSigInput | null | undefined): string {
  if (!slot) return '';
  return (slot.sfx_cues ?? [])
    .filter((c): c is NonNullable<typeof c> => Boolean(c && typeof c === 'object'))
    .map((c) => [
      c.id ?? '',
      c.offset_ms ?? 0,
      c.duration_ms ?? '',
      c.volume ?? '',
      c.fadein_ms ?? '',
      c.fadeout_ms ?? '',
      c.source_path ?? '',
    ].join(':'))
    .sort()
    .join('|');
}

/** Infer edit_kind from prev/next slot snapshots (hint for server dispatch telemetry). */
export function inferStitchEditKind(
  prevSlots: Record<string, StitchSlotMuxSigInput | undefined>,
  nextSlots: Record<string, StitchSlotMuxSigInput>,
): StitchEditKind {
  let ambient = false;
  let sfx = false;
  let video = false;

  for (const [key, nxt] of Object.entries(nextSlots)) {
    const prev = prevSlots[key];
    if ((prev?.video_path ?? '').trim() !== (nxt.video_path ?? '').trim()) {
      video = true;
    }
    if (stitchSlotLiveAmbientSig(prev) !== stitchSlotLiveAmbientSig(nxt)) {
      ambient = true;
    }
    if (sfxOnlySig(prev) !== sfxOnlySig(nxt)) {
      sfx = true;
    }
  }

  if (video) return EDIT_KIND_VIDEO_LINEAGE;
  if (ambient && sfx) return EDIT_KIND_MIXED_GEOMETRY;
  if (ambient) return EDIT_KIND_AMBIENT_GEOMETRY;
  if (sfx) return EDIT_KIND_SFX_GEOMETRY;
  return EDIT_KIND_METADATA;
}

/** True when full mix geometry (SFX + ambient) changed — client mux queue trigger. */
export function stitchSlotMixGeometryChanged(
  prev: StitchSlotMuxSigInput | null | undefined,
  next: StitchSlotMuxSigInput | null | undefined,
): boolean {
  return stitchSlotLiveGeometrySig(prev) !== stitchSlotLiveGeometrySig(next);
}

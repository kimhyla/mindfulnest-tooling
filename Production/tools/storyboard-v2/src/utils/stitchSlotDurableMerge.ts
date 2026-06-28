/** STITCH_SAVE_SLOT_DURABLE_MERGE_V1 — client partial slot patches must not drop server fields. */

export const STITCH_SAVE_SLOT_DURABLE_MERGE_V1 = 'STITCH_SAVE_SLOT_DURABLE_MERGE_V1';

/** Fields the server merge preserves — client setJob must not clobber after save. */
export const STITCH_SLOT_DURABLE_FIELDS = [
  'video_path',
  'video_dur_ms',
  'ambient_bed',
  'ambient_bed_path',
  'ambient_volume',
  'loudnorm_already_applied',
  'beat_boundaries',
] as const;

export type StitchSlotDurableFields = {
  video_path?: string;
  video_dur_ms?: number;
  ambient_bed?: string;
  ambient_bed_path?: string;
  ambient_volume?: number;
  loudnorm_already_applied?: boolean;
  beat_boundaries?: unknown[];
  sfx_cues?: unknown[];
};

/** Merge incoming client patch over prev; restore durable fields when patch omitted them. */
export function mergeStitchSlotClientPatch<T extends StitchSlotDurableFields>(
  prev: T | null | undefined,
  incoming: T,
): T {
  const out = { ...incoming } as T & Record<string, unknown>;
  if (!prev) return out as T;
  const prevCues = Array.isArray(prev.sfx_cues) ? prev.sfx_cues : [];
  if (
    prevCues.length > 0
    && !Object.prototype.hasOwnProperty.call(incoming, 'sfx_cues')
  ) {
    (out as Record<string, unknown>)['sfx_cues'] = prevCues;
  }
  for (const key of STITCH_SLOT_DURABLE_FIELDS) {
    const prevVal = prev[key as keyof T];
    const nextVal = out[key as keyof T];
    if (
      prevVal != null
      && prevVal !== ''
      && (nextVal == null || nextVal === '')
    ) {
      (out as Record<string, unknown>)[key] = prevVal;
    }
  }
  return out as T;
}

export function mergeStitchJobSlotsClientPatch<
  T extends StitchSlotDurableFields,
>(
  prevSlots: Record<string, T | undefined> | undefined,
  incomingSlots: Record<string, T>,
): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [key, slot] of Object.entries(incomingSlots)) {
    out[key] = mergeStitchSlotClientPatch(prevSlots?.[key], slot);
  }
  return out;
}

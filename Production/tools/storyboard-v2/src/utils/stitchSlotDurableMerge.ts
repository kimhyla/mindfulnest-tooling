/** STITCH_SAVE_SLOT_DURABLE_MERGE_V1 — client partial slot patches must not drop server fields. */

import { mergeOperatorFieldOnHydrate } from './operatorEditMerge.ts';

export const STITCH_SAVE_SLOT_DURABLE_MERGE_V1 = 'STITCH_SAVE_SLOT_DURABLE_MERGE_V1';
export const STITCH_AMBIENT_BED_MERGE_V1 = 'STITCH_AMBIENT_BED_MERGE_V1';

const ambientPatchInFlight = new Map<string, number>();

export function stitchAmbientSessionKey(eventId: string, slotKey: string): string {
  return `${eventId}|${slotKey}`;
}

export function beginStitchAmbientPatch(eventId: string, slotKey: string): void {
  const key = stitchAmbientSessionKey(eventId, slotKey);
  ambientPatchInFlight.set(key, (ambientPatchInFlight.get(key) ?? 0) + 1);
}

export function endStitchAmbientPatch(eventId: string, slotKey: string): void {
  const key = stitchAmbientSessionKey(eventId, slotKey);
  const next = (ambientPatchInFlight.get(key) ?? 1) - 1;
  if (next <= 0) ambientPatchInFlight.delete(key);
  else ambientPatchInFlight.set(key, next);
}

export function isStitchAmbientPatchInFlight(eventId: string, slotKey: string): boolean {
  return (ambientPatchInFlight.get(stitchAmbientSessionKey(eventId, slotKey)) ?? 0) > 0;
}

/** Hydrate ambient_bed from server without clobbering in-flight operator selection. */
export function mergeStitchAmbientBedOnHydrate(
  localBed: string | undefined,
  serverBed: string | undefined,
  opts: { patchInFlight: boolean },
): string | undefined {
  return mergeOperatorFieldOnHydrate(localBed, serverBed, opts);
}

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
  opts?: { ambientPatchInFlight?: boolean },
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
    if (key === 'ambient_bed') continue;
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
  const mergedBed = mergeStitchAmbientBedOnHydrate(
    prev.ambient_bed,
    incoming.ambient_bed,
    { patchInFlight: opts?.ambientPatchInFlight ?? false },
  );
  if (mergedBed !== undefined) {
    (out as Record<string, unknown>)['ambient_bed'] = mergedBed;
  } else if (
    prev.ambient_bed != null
    && prev.ambient_bed !== ''
    && (out.ambient_bed == null || out.ambient_bed === '')
  ) {
    (out as Record<string, unknown>)['ambient_bed'] = prev.ambient_bed;
  }
  return out as T;
}

export function mergeStitchJobSlotsClientPatch<
  T extends StitchSlotDurableFields,
>(
  prevSlots: Record<string, T | undefined> | undefined,
  incomingSlots: Record<string, T>,
  opts?: { eventId?: string },
): Record<string, T> {
  const out: Record<string, T> = {};
  for (const [key, slot] of Object.entries(incomingSlots)) {
    const ambientInFlight = opts?.eventId
      ? isStitchAmbientPatchInFlight(opts.eventId, key)
      : false;
    out[key] = mergeStitchSlotClientPatch(prevSlots?.[key], slot, {
      ambientPatchInFlight: ambientInFlight,
    });
  }
  return out;
}

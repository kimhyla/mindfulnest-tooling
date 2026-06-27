/** STITCH_SLOT_VIDEO_LINEAGE_V1 — job video_path vs playback cache must stay in sync. */
import {
  clearCachedStitcherPreviewLs,
  invalidateStitchSlotSessionSlot,
  type StitchSessionSlotKey,
} from './stitchSlotSessionCache';
import { STITCH_MUX_VIDEO_LINEAGE_V1 } from './stitchMuxVideoLineage';

export const STITCH_SLOT_VIDEO_LINEAGE_V1 = 'STITCH_SLOT_VIDEO_LINEAGE_V1';
export { STITCH_MUX_VIDEO_LINEAGE_V1 };

const SLOT_KEYS: StitchSessionSlotKey[] = ['intro', 'phase_a', 'phase_b', 'resolution'];

export function stitchSlotVideoPathChanged(
  prevPath: string | undefined,
  nextPath: string | undefined,
): boolean {
  const prev = (prevPath ?? '').trim();
  const next = (nextPath ?? '').trim();
  return Boolean(prev && next && prev !== next);
}

export function slotsWithVideoPathChanges(
  prevSlots: Partial<Record<StitchSessionSlotKey, { video_path?: string } | undefined>> | undefined,
  nextSlots: Partial<Record<StitchSessionSlotKey, { video_path?: string } | undefined>> | undefined,
): StitchSessionSlotKey[] {
  const changed: StitchSessionSlotKey[] = [];
  for (const slotKey of SLOT_KEYS) {
    const prevPath = prevSlots?.[slotKey]?.video_path;
    const nextPath = nextSlots?.[slotKey]?.video_path;
    if (stitchSlotVideoPathChanged(prevPath, nextPath)) {
      changed.push(slotKey);
    }
  }
  return changed;
}

/** Drop session mux + localStorage preview when canonical slot video_path changes. */
export function invalidateStitchSlotPlaybackCaches(
  eventId: string,
  slotKeys: readonly StitchSessionSlotKey[],
): void {
  for (const slotKey of slotKeys) {
    invalidateStitchSlotSessionSlot(eventId, slotKey);
    clearCachedStitcherPreviewLs(eventId, slotKey);
  }
}

/** Operator export succeeded — invalidate playback caches before Stitcher refetch. */
export function notifyStitchSlotExportApplied(
  eventId: string,
  slotKey: StitchSessionSlotKey,
): void {
  invalidateStitchSlotPlaybackCaches(eventId, [slotKey]);
}

/** Never preserve stale previewUrls for slots whose video lineage changed. */
export function mergeHydratedPreviewUrlsAfterLineage(
  prev: Partial<Record<StitchSessionSlotKey, string>>,
  hydrated: Partial<Record<StitchSessionSlotKey, string>>,
  lineageChanged: readonly StitchSessionSlotKey[],
): Partial<Record<StitchSessionSlotKey, string>> {
  const next: Partial<Record<StitchSessionSlotKey, string>> = { ...prev };
  for (const slotKey of lineageChanged) {
    delete next[slotKey];
  }
  return { ...next, ...hydrated };
}

export function stitchExportKeptExistingWarning(warnings: readonly string[] | undefined): boolean {
  return (warnings ?? []).some((w) => /kept existing export/i.test(w));
}

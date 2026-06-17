/** STITCH_TRACK_FOCUS_V1 — composer follows populated slots after export / load. */

export type StitchTrackSlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution';

export const STITCH_TRACK_SLOT_KEYS: StitchTrackSlotKey[] = [
  'intro',
  'phase_a',
  'phase_b',
  'resolution',
];

const STITCHER_TRACK_SLOT_LS_PREFIX = 'storyboard_v2_stitcher_track_slot';

export function isStitchTrackSlotKey(value: string): value is StitchTrackSlotKey {
  return (STITCH_TRACK_SLOT_KEYS as string[]).includes(value);
}

export function readPersistedTrackSlot(eventId: string): StitchTrackSlotKey | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(`${STITCHER_TRACK_SLOT_LS_PREFIX}:${eventId}`);
    return raw && isStitchTrackSlotKey(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function writePersistedTrackSlot(eventId: string, slot: StitchTrackSlotKey | null): void {
  if (typeof window === 'undefined') return;
  try {
    const key = `${STITCHER_TRACK_SLOT_LS_PREFIX}:${eventId}`;
    if (slot) {
      window.localStorage.setItem(key, slot);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // localStorage may be unavailable in some test contexts.
  }
}

/** Pick the slot the composer should review — never stay on an empty persisted slot. */
export function pickTrackSlotForJob(
  slots: Record<string, { video_path?: string | null } | undefined> | undefined,
  eventId: string,
  preferredSlot?: string | null,
): StitchTrackSlotKey {
  if (
    preferredSlot
    && isStitchTrackSlotKey(preferredSlot)
    && slots?.[preferredSlot]?.video_path
  ) {
    return preferredSlot;
  }

  const persisted = readPersistedTrackSlot(eventId);
  if (persisted && slots?.[persisted]?.video_path) {
    return persisted;
  }

  for (let i = STITCH_TRACK_SLOT_KEYS.length - 1; i >= 0; i--) {
    const key = STITCH_TRACK_SLOT_KEYS[i];
    if (slots?.[key]?.video_path) return key;
  }

  if (persisted) return persisted;
  if (preferredSlot && isStitchTrackSlotKey(preferredSlot)) return preferredSlot;
  return STITCH_TRACK_SLOT_KEYS[0];
}

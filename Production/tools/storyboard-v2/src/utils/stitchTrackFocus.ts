/** STITCH_TRACK_FOCUS_V1 — composer follows populated slots after export / load.
 * STITCH_VIEWER_SLOT_LAYOUT_V1 — viewer slot must belong to current job layout keys. */

export type StitchTrackSlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution';

export type StitchUiSlotKey = StitchTrackSlotKey | 'standalone';

export const STITCH_TRACK_SLOT_KEYS: StitchTrackSlotKey[] = [
  'intro',
  'phase_a',
  'phase_b',
  'resolution',
];

export const STITCH_VIEWER_SLOT_LAYOUT_V1 = 'STITCH_VIEWER_SLOT_LAYOUT_V1';

/** Timeline width for slots without video — avoids fake 30s gray bars. */
export const STITCH_EMPTY_SEGMENT_MS = 2500;

const STITCHER_TRACK_SLOT_LS_PREFIX = 'storyboard_v2_stitcher_track_slot';

export function isStitchTrackSlotKey(value: string): value is StitchTrackSlotKey {
  return (STITCH_TRACK_SLOT_KEYS as string[]).includes(value);
}

export function isStitchUiSlotKey(value: string): value is StitchUiSlotKey {
  return isStitchTrackSlotKey(value) || value === 'standalone';
}

export function stitchTrackFocusStorageKey(stitchSessionKey: string): string {
  return `${STITCHER_TRACK_SLOT_LS_PREFIX}:${stitchSessionKey}`;
}

export function slotHasStitchVideo(
  slots: Record<string, { video_path?: string | null } | undefined> | undefined,
  slot: StitchUiSlotKey,
): boolean {
  return Boolean((slots?.[slot]?.video_path ?? '').trim());
}

export function readPersistedTrackSlot(stitchSessionKey: string): StitchUiSlotKey | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(stitchTrackFocusStorageKey(stitchSessionKey));
    return raw && isStitchUiSlotKey(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function writePersistedTrackSlot(
  stitchSessionKey: string,
  slot: StitchUiSlotKey | null,
): void {
  if (typeof window === 'undefined') return;
  try {
    const key = stitchTrackFocusStorageKey(stitchSessionKey);
    if (slot) {
      window.localStorage.setItem(key, slot);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // localStorage may be unavailable in some test contexts.
  }
}

/** Pre-layout-validation formula (a5891e2) — documents the bug class for regression tests. */
export function legacyResolveStitchViewerSlot(
  trackFocusedSlot: StitchUiSlotKey | null,
  multiPhaseFirstKey: StitchUiSlotKey | null,
  standaloneMode: boolean,
): StitchUiSlotKey {
  return (
    trackFocusedSlot
    ?? multiPhaseFirstKey
    ?? (standaloneMode ? 'standalone' : STITCH_TRACK_SLOT_KEYS[0])
  );
}

/**
 * STITCH_VIEWER_SLOT_LAYOUT_V1 — navigation memory is valid only inside current layout.
 */
export function resolveStitchViewerSlot(opts: {
  layoutSlotKeys: readonly StitchUiSlotKey[];
  trackFocusedSlot: StitchUiSlotKey | null;
}): StitchUiSlotKey {
  const first = opts.layoutSlotKeys[0] ?? STITCH_TRACK_SLOT_KEYS[0];
  if (
    opts.trackFocusedSlot
    && opts.layoutSlotKeys.includes(opts.trackFocusedSlot)
  ) {
    return opts.trackFocusedSlot;
  }
  return first;
}

/** Pick track focus for any stitch layout (event 4-slot or milestone standalone). */
export function pickTrackSlotForLayout(
  slots: Record<string, { video_path?: string | null } | undefined> | undefined,
  layoutKeys: readonly StitchUiSlotKey[],
  stitchSessionKey: string,
  preferredSlot?: string | null,
): StitchUiSlotKey {
  const first = layoutKeys[0] ?? STITCH_TRACK_SLOT_KEYS[0];
  const persisted = readPersistedTrackSlot(stitchSessionKey);

  // Operator track click memory wins over passive scope/video-role hint on restore.
  if (
    persisted
    && layoutKeys.includes(persisted)
    && slotHasStitchVideo(slots, persisted)
  ) {
    return persisted;
  }

  if (
    preferredSlot
    && isStitchUiSlotKey(preferredSlot)
    && layoutKeys.includes(preferredSlot)
    && slotHasStitchVideo(slots, preferredSlot)
  ) {
    return preferredSlot;
  }

  for (let i = layoutKeys.length - 1; i >= 0; i--) {
    const key = layoutKeys[i];
    if (slotHasStitchVideo(slots, key)) return key;
  }

  if (persisted && layoutKeys.includes(persisted)) return persisted;
  if (
    preferredSlot
    && isStitchUiSlotKey(preferredSlot)
    && layoutKeys.includes(preferredSlot)
  ) {
    return preferredSlot;
  }
  return first;
}

/** Event 4-slot layout — backward-compatible wrapper. */
export function pickTrackSlotForJob(
  slots: Record<string, { video_path?: string | null } | undefined> | undefined,
  stitchSessionKey: string,
  preferredSlot?: string | null,
): StitchTrackSlotKey {
  const picked = pickTrackSlotForLayout(
    slots,
    STITCH_TRACK_SLOT_KEYS,
    stitchSessionKey,
    preferredSlot,
  );
  return isStitchTrackSlotKey(picked) ? picked : STITCH_TRACK_SLOT_KEYS[0];
}

/** User clicked a track segment — redirect empty clicks to the best populated slot. */
export function resolveTrackSlotForInteraction(
  slots: Record<string, { video_path?: string | null } | undefined> | undefined,
  stitchSessionKey: string,
  clicked: StitchTrackSlotKey,
  preferredSlot?: string | null,
): StitchTrackSlotKey {
  if (slotHasStitchVideo(slots, clicked)) return clicked;
  return pickTrackSlotForJob(slots, stitchSessionKey, preferredSlot);
}

import type { Transition } from '../components/StitcherTransitionSelector';

export type SlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution';

export const STITCH_SLOT_ORDER: SlotKey[] = ['intro', 'phase_a', 'phase_b', 'resolution'];

/** Match intro canonical final_pair_fade_ms default (prolonged fade-through-black). */
export const DEFAULT_PHASE_TRANSITION_FADE_MS = 2800;

export function defaultStitchTransitions(): Transition[] {
  return [0, 1, 2].map((after_slot) => ({
    after_slot,
    kind: 'dissolve',
    fade_ms: DEFAULT_PHASE_TRANSITION_FADE_MS,
    audio_xfade_ms: 0,
  }));
}

export function resolveStitchTransitions(_existing?: Transition[] | null): Transition[] {
  // STITCH_CANONICAL_TRANSITIONS_V1 — pipeline always uses these; UI mirrors canonical.
  return defaultStitchTransitions();
}

export interface StitchSlotLike {
  video_path?: string;
  ambient_bed?: string;
}

export function orderedStitchSlots(
  slots: Record<string, StitchSlotLike> | undefined,
): StitchSlotLike[] {
  if (!slots) return [];
  return STITCH_SLOT_ORDER.map((key) => slots[key]).filter(
    (s): s is StitchSlotLike => !!s?.video_path,
  );
}

export function allStitchSlotsReady(
  slots: Record<string, StitchSlotLike> | undefined,
): boolean {
  return STITCH_SLOT_ORDER.every((key) => !!slots?.[key]?.video_path);
}

export function cumulativeSlotOffsetsMs(slotDurationsMs: number[]): number[] {
  const offsets = [0];
  let acc = 0;
  for (const dur of slotDurationsMs) {
    acc += dur;
    offsets.push(acc);
  }
  return offsets;
}

/** Seek target for a slot inside the module preview timeline (prefers server black-pause offsets). */
export function modulePreviewSeekOffsetMs(
  slotKey: SlotKey,
  slotStartOffsetsMs: number[],
  slotDurationsMs: number[],
): number {
  const idx = slotIndexForKey(slotKey);
  if (idx >= 0 && idx < slotStartOffsetsMs.length) {
    return slotStartOffsetsMs[idx] ?? 0;
  }
  const legacy = cumulativeSlotOffsetsMs(slotDurationsMs);
  return legacy[idx] ?? 0;
}

export function slotIndexForKey(key: SlotKey): number {
  return STITCH_SLOT_ORDER.indexOf(key);
}

const MODULE_PREVIEW_LS_PREFIX = 'storyboard_v2_stitcher_module_preview';

export interface CachedModulePreview {
  cache_key: string;
  preview_url: string;
  slot_durations: number[];
  slot_start_offsets_ms?: number[];
}

export function modulePreviewCacheKey(
  slots: Record<string, StitchSlotLike> | undefined,
  transitions: Transition[],
): string {
  const slotPaths = STITCH_SLOT_ORDER.map((key) => slots?.[key]?.video_path ?? '');
  const ambientBeds = STITCH_SLOT_ORDER.map((key) => slots?.[key]?.ambient_bed ?? '');
  return JSON.stringify({ slotPaths, ambientBeds, transitions });
}

export function readCachedModulePreview(
  eventId: string,
): CachedModulePreview | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(`${MODULE_PREVIEW_LS_PREFIX}:${eventId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedModulePreview;
    if (parsed?.cache_key && parsed?.preview_url) return parsed;
  } catch {
    // ignore
  }
  return null;
}

export function writeCachedModulePreview(
  eventId: string,
  cache: CachedModulePreview,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      `${MODULE_PREVIEW_LS_PREFIX}:${eventId}`,
      JSON.stringify(cache),
    );
  } catch {
    // ignore
  }
}

/** LD-827 — multi-phase viewer must never be blank while module preview bakes. */
export function resolveModuleViewerVideoUrl(opts: {
  standaloneMode: boolean;
  modulePreviewUrl?: string | undefined;
  viewerProcessedUrl?: string | undefined;
  viewerSourceUrl?: string | undefined;
}): string | undefined {
  if (opts.standaloneMode) {
    return opts.viewerProcessedUrl ?? opts.viewerSourceUrl;
  }
  return opts.modulePreviewUrl ?? opts.viewerSourceUrl;
}

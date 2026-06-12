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
    audio_xfade_ms: DEFAULT_PHASE_TRANSITION_FADE_MS,
  }));
}

export function resolveStitchTransitions(existing?: Transition[] | null): Transition[] {
  const defaults = defaultStitchTransitions();
  if (!existing?.length) return defaults;
  return defaults.map(
    (d) => existing.find((t) => t.after_slot === d.after_slot) ?? d,
  );
}

export interface StitchSlotLike {
  video_path?: string;
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

export function slotIndexForKey(key: SlotKey): number {
  return STITCH_SLOT_ORDER.indexOf(key);
}

const MODULE_PREVIEW_LS_PREFIX = 'storyboard_v2_stitcher_module_preview';

export interface CachedModulePreview {
  cache_key: string;
  preview_url: string;
  slot_durations: number[];
}

export function modulePreviewCacheKey(
  slotPaths: string[],
  transitions: Transition[],
): string {
  return JSON.stringify({ slotPaths, transitions });
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

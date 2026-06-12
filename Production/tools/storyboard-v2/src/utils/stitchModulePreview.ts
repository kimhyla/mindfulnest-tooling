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

export function resolveStitchTransitions(existing?: Transition[] | null): Transition[] {
  const defaults = defaultStitchTransitions();
  if (!existing?.length) return defaults;
  return defaults.map((d) => {
    const found = existing.find((t) => t.after_slot === d.after_slot);
    if (!found) return d;
    return {
      ...found,
      kind: found.kind ?? d.kind,
      fade_ms: found.fade_ms ?? d.fade_ms,
      // Dissolve boundaries use fade-through-black; never duck dialogue at tail.
      audio_xfade_ms: 0,
    };
  });
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

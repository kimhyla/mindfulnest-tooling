/**
 * Compact keep-window overlay on Beat Gen O3 video thumbnails.
 * Amber regions = head/tail TO REMOVE; middle = kept for export.
 * Maps to per-option trim_start_s + trim_back_s (start crop + end crop together).
 */
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { shouldPreserveBgO3CutDraft } from '../../utils/bgO3CutSession.ts';

const MIN_KEEP_S = 0.25;

/** ffprobe ∪ video element — used for export/persist gates (never shorter than operator view). */
export function resolveO3PlaybackDurationS(
  sourceDurationS: number | null | undefined,
  loadedDurationS: number | null | undefined,
): number {
  const src = sourceDurationS != null && sourceDurationS > 0 ? sourceDurationS : 0;
  const loaded = loadedDurationS != null && loadedDurationS > 0 ? loadedDurationS : 0;
  return Math.max(src, loaded);
}

/** Overlay drag timeline: prefer loaded video metadata (what the operator sees). */
export function resolveO3OverlayDurationS(
  sourceDurationS: number | null | undefined,
  loadedDurationS: number | null | undefined,
): number {
  const loaded = loadedDurationS != null && loadedDurationS > 0 ? loadedDurationS : 0;
  if (loaded > 0) return loaded;
  const src = sourceDurationS != null && sourceDurationS > 0 ? sourceDurationS : 0;
  return src;
}

/** Export/persist timeline: server ffprobe, never shorter than what the operator sees. */
export function resolveO3ExportDurationS(
  sourceDurationS: number | null | undefined,
  playbackDurationS: number,
): number {
  const src = sourceDurationS != null && sourceDurationS > 0 ? sourceDurationS : 0;
  const playback = playbackDurationS > 0 ? playbackDurationS : 0;
  return Math.max(src, playback);
}

/**
 * Duration for trim_start + trim_back math — must match server `_o3_trim_authority_path`.
 * Prefer the loaded overlay timeline (handle drags); fall back to export ffprobe.
 */
export function resolveO3TrimAuthorityDurationS(
  overlayTimelineDurationS: number,
  exportDurationS: number,
  playbackDurationS: number,
): number {
  if (overlayTimelineDurationS > 0) return overlayTimelineDurationS;
  if (exportDurationS > 0) return exportDurationS;
  return playbackDurationS > 0 ? playbackDurationS : 0;
}

/** Clamp keep handles into [0, duration] with ≥ minKeepS kept (fixes stale keepEnd > duration). */
export function normalizeO3KeepWindow(
  durationS: number,
  keepStartS: number,
  keepEndS: number,
  minKeepS = MIN_KEEP_S,
): { startS: number; endS: number } {
  if (durationS <= 0) {
    return {
      startS: Math.max(0, keepStartS),
      endS: Math.max(keepStartS, keepEndS),
    };
  }
  const endHint = keepEndS > keepStartS + 0.001 ? keepEndS : durationS;
  const endCap = Math.min(endHint, durationS);
  const startS = Math.max(0, Math.min(keepStartS, endCap - minKeepS));
  const endS = Math.max(startS + minKeepS, Math.min(endCap, durationS));
  const startRounded = Math.round(startS * 100) / 100;
  const endRounded = Math.round(endS * 100) / 100;
  // Post-round clamp: centisecond round must not push end past ffprobe duration (e.g. 8.125 → 8.13).
  const endClamped = Math.min(endRounded, durationS);
  const startClamped = Math.max(0, Math.min(startRounded, endClamped - minKeepS));
  return {
    startS: startClamped,
    endS: endClamped,
  };
}

/** Keep window must leave ≥ MIN_KEEP_S and fit inside the clip. */
export function isValidO3KeepWindow(
  durationS: number,
  keepStartS: number,
  keepEndS: number,
  minKeepS = MIN_KEEP_S,
): boolean {
  if (durationS <= minKeepS * 2 - 0.001) return false;
  const kept = keepEndS - keepStartS;
  return (
    keepStartS >= -0.001
    && keepEndS <= durationS + 0.001
    && kept >= minKeepS - 0.001
  );
}

/** Back-compat alias used by BgTab validation helper name. */
export function isValidO3CutWindow(
  durationS: number,
  keepStartS: number,
  keepEndS: number,
  minKeepS = MIN_KEEP_S,
): boolean {
  return isValidO3KeepWindow(durationS, keepStartS, keepEndS, minKeepS);
}

export interface BgO3CutOverlayProps {
  beatIndex: number;
  optionIndex: number;
  beatId: string;
  durationS: number;
  /** Absolute time where kept region begins (trim_start). */
  keepStartS: number;
  /** Absolute time where kept region ends (duration - trim_back). */
  keepEndS: number;
  editable: boolean;
  onDragStart?: () => void;
  onDragEnd?: () => void;
  onKeepDraftChange: (keepStartS: number, keepEndS: number) => void;
  onKeepRejected?: (reason: string) => void;
}

function relXFromPointer(container: HTMLElement, evt: PointerEvent): number {
  const box = container.getBoundingClientRect();
  if (box.width <= 0) return 0;
  return Math.max(0, Math.min(1, (evt.clientX - box.left) / box.width));
}

export function BgO3CutOverlay({
  beatIndex,
  optionIndex,
  beatId,
  durationS,
  keepStartS,
  keepEndS,
  editable,
  onDragStart,
  onDragEnd,
  onKeepDraftChange,
  onKeepRejected,
}: BgO3CutOverlayProps) {
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState<{ startS: number; endS: number } | null>(null);
  const timelineRef = useRef({ durationS, keepStartS, keepEndS, draft: null as { startS: number; endS: number } | null });
  timelineRef.current = { durationS, keepStartS, keepEndS, draft };

  useEffect(() => {
    if (shouldPreserveBgO3CutDraft(beatId, optionIndex, draft !== null)) return;
    setDraft(null);
  }, [beatId, optionIndex, draft, keepStartS, keepEndS, durationS]);

  const normalizedKeep = normalizeO3KeepWindow(durationS, keepStartS, keepEndS);
  const display = draft ?? normalizedKeep;

  const resolveKeepAtCommit = () => {
    const live = timelineRef.current;
    const liveDraft = live.draft;
    const liveNorm = normalizeO3KeepWindow(live.durationS, live.keepStartS, live.keepEndS);
    return liveDraft ?? liveNorm;
  };
  const hasKeep = display.endS > display.startS + MIN_KEEP_S - 0.001 && durationS > 0;
  const pct = (s: number) => (durationS > 0 ? (s / durationS) * 100 : 0);
  const keepLeft = pct(display.startS);
  const keepRight = pct(display.endS);
  const headWidth = hasKeep ? keepLeft : 0;
  const tailWidth = hasKeep ? Math.max(0, 100 - keepRight) : 0;

  const commitDraft = useCallback((startS: number, endS: number) => {
    const dur = timelineRef.current.durationS;
    if (dur <= MIN_KEEP_S * 2) {
      onKeepRejected?.(
        dur <= 0
          ? 'Loading clip duration — try again in a moment'
          : `Clip is only ${dur.toFixed(1)}s — too short to trim`,
      );
      return;
    }
    const { startS: roundedStart, endS: roundedEnd } = normalizeO3KeepWindow(dur, startS, endS);
    setDraft(null);
    onKeepDraftChange(roundedStart, roundedEnd);
  }, [onKeepDraftChange, onKeepRejected]);

  const onLeftHandlePointerDown = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!editable || durationS <= 0) return;
    onDragStart?.();
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const container = overlayRef.current;
    if (!container) return;
    const endS = display.endS > display.startS + 0.001 ? display.endS : durationS;

    const applyPreview = (evt: PointerEvent) => {
      const newStart = relXFromPointer(container, evt) * durationS;
      setDraft({
        startS: Math.max(0, Math.min(endS - MIN_KEEP_S, newStart)),
        endS,
      });
    };

    const onUp = (upEvt: PointerEvent) => {
      const live = timelineRef.current;
      const atCommit = resolveKeepAtCommit();
      const endSAtCommit = atCommit.endS > atCommit.startS + 0.001 ? atCommit.endS : live.durationS;
      const newStart = relXFromPointer(container, upEvt) * live.durationS;
      commitDraft(
        Math.max(0, Math.min(endSAtCommit - MIN_KEEP_S, newStart)),
        endSAtCommit,
      );
      onDragEnd?.();
      handle.removeEventListener('pointermove', applyPreview);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', applyPreview);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  };

  const onRightHandlePointerDown = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!editable || durationS <= 0) return;
    onDragStart?.();
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const container = overlayRef.current;
    if (!container) return;
    const startS = display.startS;

    const applyPreview = (evt: PointerEvent) => {
      const newEnd = relXFromPointer(container, evt) * durationS;
      setDraft({
        startS,
        endS: Math.max(startS + MIN_KEEP_S, Math.min(durationS, newEnd)),
      });
    };

    const onUp = (upEvt: PointerEvent) => {
      const live = timelineRef.current;
      const atCommit = resolveKeepAtCommit();
      const startSAtCommit = atCommit.startS;
      const newEnd = relXFromPointer(container, upEvt) * live.durationS;
      commitDraft(
        startSAtCommit,
        Math.max(startSAtCommit + MIN_KEEP_S, Math.min(live.durationS, newEnd)),
      );
      onDragEnd?.();
      handle.removeEventListener('pointermove', applyPreview);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', applyPreview);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  };

  if (durationS <= 0) {
    return null;
  }

  return (
    <div
      ref={overlayRef}
      class={`mn-bg-o3-cut-overlay${editable ? '' : ' mn-bg-o3-cut-overlay--busy'}`}
      data-testid={`bg-o3-cut-overlay-${beatIndex}-${optionIndex}`}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {headWidth > 0.1 ? (
        <div
          class="mn-bg-o3-cut-block"
          data-testid={`bg-o3-cut-head-${beatIndex}-${optionIndex}`}
          style={{ left: '0%', width: `${headWidth}%` }}
          title={`Remove head: 0s → ${display.startS.toFixed(2)}s`}
        />
      ) : null}
      {tailWidth > 0.1 ? (
        <div
          class="mn-bg-o3-cut-block"
          data-testid={`bg-o3-cut-tail-${beatIndex}-${optionIndex}`}
          style={{ left: `${keepRight}%`, width: `${tailWidth}%` }}
          title={`Remove tail: ${display.endS.toFixed(2)}s → ${durationS.toFixed(2)}s`}
        />
      ) : null}
      <div
        class="mn-bg-o3-cut-handle mn-bg-o3-cut-handle--left"
        data-testid={`bg-o3-cut-handle-left-${beatIndex}-${optionIndex}`}
        style={{ left: `${keepLeft}%` }}
        title="Drag to trim start (head crop)"
        onPointerDown={onLeftHandlePointerDown}
      />
      <div
        class="mn-bg-o3-cut-handle mn-bg-o3-cut-handle--right"
        data-testid={`bg-o3-cut-handle-right-${beatIndex}-${optionIndex}`}
        style={{ left: `${Math.min(99.5, keepRight)}%` }}
        title="Drag to trim end (tail crop)"
        onPointerDown={onRightHandlePointerDown}
      />
    </div>
  );
}

/** @deprecated use onKeepDraftChange */
export type BgO3CutOverlayLegacyProps = BgO3CutOverlayProps & {
  cutStartS: number;
  cutEndS: number;
  onCutDraftChange: (cutStartS: number, cutEndS: number) => void;
  onCutRejected?: (reason: string) => void;
};

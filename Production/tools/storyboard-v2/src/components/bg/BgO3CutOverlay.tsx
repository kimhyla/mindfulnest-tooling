/**
 * Compact keep-window overlay on Beat Gen O3 video thumbnails.
 * Amber regions = head/tail TO REMOVE; middle = kept for export.
 * Maps to per-option trim_start_s + trim_back_s (start crop + end crop together).
 */
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';

const MIN_KEEP_S = 0.25;

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
  durationS: number;
  /** Absolute time where kept region begins (trim_start). */
  keepStartS: number;
  /** Absolute time where kept region ends (duration - trim_back). */
  keepEndS: number;
  editable: boolean;
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
  durationS,
  keepStartS,
  keepEndS,
  editable,
  onKeepDraftChange,
  onKeepRejected,
}: BgO3CutOverlayProps) {
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState<{ startS: number; endS: number } | null>(null);

  useEffect(() => {
    setDraft(null);
  }, [keepStartS, keepEndS, durationS]);

  const display = draft ?? {
    startS: keepStartS,
    endS: keepEndS > keepStartS + 0.001 ? keepEndS : durationS,
  };
  const hasKeep = display.endS > display.startS + MIN_KEEP_S - 0.001 && durationS > 0;
  const pct = (s: number) => (durationS > 0 ? (s / durationS) * 100 : 0);
  const keepLeft = pct(display.startS);
  const keepRight = pct(display.endS);
  const headWidth = hasKeep ? keepLeft : 0;
  const tailWidth = hasKeep ? Math.max(0, 100 - keepRight) : 0;

  const commitDraft = useCallback((startS: number, endS: number) => {
    if (durationS <= 0) return;
    const clampedStart = Math.max(0, Math.min(durationS - MIN_KEEP_S, startS));
    const clampedEnd = Math.max(clampedStart + MIN_KEEP_S, Math.min(durationS, endS));
    const roundedStart = Math.round(clampedStart * 100) / 100;
    const roundedEnd = Math.round(clampedEnd * 100) / 100;
    if (!isValidO3KeepWindow(durationS, roundedStart, roundedEnd)) {
      setDraft(null);
      onKeepRejected?.(
        durationS <= MIN_KEEP_S * 2
          ? `Clip is only ${durationS.toFixed(1)}s — too short to trim`
          : 'Trim window too small — drag handles farther apart (need ≥0.25s kept)',
      );
      return;
    }
    setDraft(null);
    onKeepDraftChange(roundedStart, roundedEnd);
  }, [durationS, onKeepDraftChange, onKeepRejected]);

  const onLeftHandlePointerDown = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!editable || durationS <= 0) return;
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
      const newStart = relXFromPointer(container, upEvt) * durationS;
      commitDraft(Math.max(0, Math.min(endS - MIN_KEEP_S, newStart)), endS);
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
      const newEnd = relXFromPointer(container, upEvt) * durationS;
      commitDraft(startS, Math.max(startS + MIN_KEEP_S, Math.min(durationS, newEnd)));
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

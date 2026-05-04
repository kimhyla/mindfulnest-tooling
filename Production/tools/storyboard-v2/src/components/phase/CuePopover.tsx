// CuePopover — animation / duration / volume / delete inspector for a single
// watercolor cue. Per LD CUE_POPOVER_INSPECTOR_V1 (S5.5f spec §3.4).
// Reusable surface — S5.5g Stitcher will mount the same component.
//
// Animation enum is the live server set (production_server.py:3704
// _V2_CUE_ANIMATIONS = {"fade_in", "slide_in", "gentle_pan"} per spec
// §19.10 #1). Earlier draft listed five values; those would have been
// rejected by the validator. Do not extend without changing the server set.
//
// Delete: Modal-confirm by default; Shift+click on Delete skips the
// confirmation (Cursor v8 Q8 power-user path).

import { useState } from 'preact/hooks';
import { Modal } from '../ui/Modal';
import type { WatercolorCue } from './WaveformTimeline';

export const CUE_ANIMATION_TYPES = ['fade_in', 'slide_in', 'gentle_pan'] as const;
export type CueAnimationType = typeof CUE_ANIMATION_TYPES[number];

export interface CuePopoverProps {
  cue: WatercolorCue;
  /** Anchor coordinates in viewport space; popover positions itself near them. */
  anchor: { x: number; y: number };
  onPatch: (updated: WatercolorCue) => void;
  onDelete: () => void;
  onClose: () => void;
}

export function CuePopover({ cue, anchor, onPatch, onDelete, onClose }: CuePopoverProps) {
  const [animationType, setAnimationType] = useState<string>(
    cue.animation_type ?? 'fade_in',
  );
  const [durationMs, setDurationMs] = useState<number>(cue.duration_ms ?? 3000);
  const [volume, setVolume] = useState<number>(cue.volume ?? 1.0);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const commit = (next: Partial<WatercolorCue>) => {
    onPatch({ ...cue, ...next });
  };

  const onAnimChange = (e: Event) => {
    const v = (e.target as HTMLSelectElement).value;
    setAnimationType(v);
    commit({ animation_type: v });
  };

  const onDurationBlur = () => {
    commit({ duration_ms: durationMs });
  };

  const onVolumeChange = (e: Event) => {
    const v = Number((e.target as HTMLInputElement).value);
    setVolume(v);
    commit({ volume: v });
  };

  const onDeleteClick = (e: MouseEvent) => {
    if (e.shiftKey) {
      // Power-user skip-confirm path (Cursor v8 Q8).
      onDelete();
      return;
    }
    setConfirmingDelete(true);
  };

  // Cursor v8 Q2 — `position: fixed` so the popover detaches from any scroll
  // ancestor; offset 12px below + right of the anchor; clamped to the
  // viewport so a marker near the right edge doesn't push the popover off-screen.
  const popoverStyle = {
    position: 'fixed' as const,
    left: `${Math.min(anchor.x + 12, window.innerWidth - 280)}px`,
    top: `${Math.min(anchor.y + 12, window.innerHeight - 220)}px`,
    zIndex: 50,
  };

  return (
    <>
      <div
        class="mn-cue-popover"
        data-testid="cue-popover"
        data-cue-id={cue.id}
        style={popoverStyle}
      >
        <div class="mn-cue-popover-header">
          <strong>Watercolor cue</strong>
          <button
            type="button"
            class="mn-cue-popover-close"
            data-testid="cue-popover-close"
            aria-label="Close"
            onClick={onClose}
          >
            &times;
          </button>
        </div>
        <label class="mn-cue-popover-row">
          <span>Animation</span>
          <select
            data-testid="cue-popover-animation"
            value={animationType}
            onChange={onAnimChange}
          >
            {CUE_ANIMATION_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label class="mn-cue-popover-row">
          <span>Duration (ms)</span>
          <input
            type="number"
            data-testid="cue-popover-duration"
            min={100}
            max={30_000}
            step={100}
            value={durationMs}
            onInput={(e: Event) =>
              setDurationMs(Number((e.target as HTMLInputElement).value))
            }
            onBlur={onDurationBlur}
          />
        </label>
        <label class="mn-cue-popover-row">
          <span>Volume</span>
          <input
            type="range"
            data-testid="cue-popover-volume"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onInput={onVolumeChange}
          />
          <span class="mn-dim">{volume.toFixed(2)}</span>
        </label>
        <div class="mn-cue-popover-footer">
          <button
            type="button"
            class="mn-btn mn-btn-danger"
            data-testid="cue-popover-delete"
            onClick={onDeleteClick}
            title="Click to confirm; Shift+click to skip confirm"
          >
            Delete
          </button>
          <button
            type="button"
            class="mn-btn"
            data-testid="cue-popover-done"
            onClick={onClose}
          >
            Done
          </button>
        </div>
      </div>
      <Modal
        id="cue-delete"
        title="Delete cue?"
        open={confirmingDelete}
        onClose={() => setConfirmingDelete(false)}
        footer={
          <>
            <button
              type="button"
              class="mn-btn"
              data-testid="cue-delete-cancel"
              onClick={() => setConfirmingDelete(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              class="mn-btn mn-btn-danger"
              data-testid="cue-delete-confirm"
              onClick={() => {
                setConfirmingDelete(false);
                onDelete();
              }}
            >
              Delete
            </button>
          </>
        }
      >
        <p>
          Remove watercolor cue at{' '}
          <strong>{((cue.offset_ms ?? 0) / 1000).toFixed(1)}s</strong>?
          Shift+click Delete in the future to skip this confirm.
        </p>
      </Modal>
    </>
  );
}

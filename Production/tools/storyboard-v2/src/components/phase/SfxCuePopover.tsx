// SfxCuePopover — volume / fadein / fadeout / Delete inspector for a single
// SFX cue. Per spec §3.2 + §4 Phase B G4-G5. STITCHER_SFX_CUE_UI_V1 (HARD).
//
// Distinct from CuePopover (which edits watercolor cues — animation_type +
// duration_ms). SFX cues have a different field set (volume / fadein_ms /
// fadeout_ms / source_path) so the two popovers stay separated to avoid a
// discriminated-union prop drilling that obscures contracts.
//
// Contract:
//   - onPatch(updated): caller persists the change. The popover does not
//     POST directly — it returns the updated cue and the caller decides
//     where to write (per-slot → stitch_save_job; module-level →
//     /api/timeline/cues).
//   - onDelete(): caller removes the cue and persists.
//   - Volume control fires onPatch on each input event so the test (G4) can
//     observe the live mutation. Fadein/Fadeout fire onPatch on blur.

import { useState } from 'preact/hooks';

export interface SfxCue {
  id: string;
  source_path: string;
  name?: string;
  offset_ms: number;
  /** Playback window on the slot timeline (ms). Default 3000 at drop time. */
  duration_ms?: number;
  volume: number;
  fadein_ms: number;
  fadeout_ms: number;
}

export interface SfxCuePopoverProps {
  cue: SfxCue;
  /** Anchor coordinates in viewport space; popover positions itself near them. */
  anchor: { x: number; y: number };
  onPatch: (updated: SfxCue) => void;
  onDelete: () => void;
  onClose: () => void;
}

export function SfxCuePopover({ cue, anchor, onPatch, onDelete, onClose }: SfxCuePopoverProps) {
  const [volume, setVolume] = useState<number>(cue.volume);
  const [fadeinMs, setFadeinMs] = useState<number>(cue.fadein_ms);
  const [fadeoutMs, setFadeoutMs] = useState<number>(cue.fadeout_ms);

  const commit = (next: Partial<SfxCue>) => {
    onPatch({ ...cue, ...next });
  };

  const onVolumeChange = (e: Event) => {
    const v = Number((e.target as HTMLInputElement).value);
    setVolume(v);
    commit({ volume: v });
  };

  const onFadeinBlur = () => {
    commit({ fadein_ms: fadeinMs });
  };

  const onFadeoutBlur = () => {
    commit({ fadeout_ms: fadeoutMs });
  };

  const popoverStyle = {
    position: 'fixed' as const,
    left: `${Math.min(anchor.x + 12, window.innerWidth - 280)}px`,
    top: `${Math.min(anchor.y + 12, window.innerHeight - 240)}px`,
    zIndex: 50,
  };

  const displayName = cue.name ?? cue.source_path.split('/').pop() ?? cue.id;

  return (
    <div
      class="mn-cue-popover mn-sfx-cue-popover"
      data-testid="sfx-cue-popover"
      data-cue-id={cue.id}
      style={popoverStyle}
    >
      <div class="mn-cue-popover-header">
        <strong>SFX cue · {displayName}</strong>
        <button
          type="button"
          class="mn-cue-popover-close"
          data-testid="sfx-cue-popover-close"
          aria-label="Close"
          onClick={onClose}
        >
          &times;
        </button>
      </div>
      <label class="mn-cue-popover-row">
        <span>Volume</span>
        <input
          type="range"
          data-testid="sfx-cue-popover-volume"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onInput={onVolumeChange}
        />
        <span class="mn-dim">{volume.toFixed(2)}</span>
      </label>
      <label class="mn-cue-popover-row">
        <span>Fade in (ms)</span>
        <input
          type="number"
          data-testid="sfx-cue-popover-fadein"
          min={0}
          max={10_000}
          step={50}
          value={fadeinMs}
          onInput={(e: Event) =>
            setFadeinMs(Number((e.target as HTMLInputElement).value))
          }
          onBlur={onFadeinBlur}
        />
      </label>
      <label class="mn-cue-popover-row">
        <span>Fade out (ms)</span>
        <input
          type="number"
          data-testid="sfx-cue-popover-fadeout"
          min={0}
          max={10_000}
          step={50}
          value={fadeoutMs}
          onInput={(e: Event) =>
            setFadeoutMs(Number((e.target as HTMLInputElement).value))
          }
          onBlur={onFadeoutBlur}
        />
      </label>
      <div class="mn-cue-popover-row mn-dim">
        <span>Offset</span>
        <span>{(cue.offset_ms / 1000).toFixed(2)}s</span>
      </div>
      {cue.duration_ms != null && cue.duration_ms > 0 ? (
        <div class="mn-cue-popover-row mn-dim">
          <span>Duration</span>
          <span>{(cue.duration_ms / 1000).toFixed(2)}s</span>
        </div>
      ) : null}
      <div class="mn-cue-popover-footer">
        <button
          type="button"
          class="mn-btn mn-btn-danger"
          data-testid="sfx-cue-popover-delete"
          onClick={onDelete}
        >
          Delete
        </button>
        <button
          type="button"
          class="mn-btn"
          data-testid="sfx-cue-popover-done"
          onClick={onClose}
        >
          Done
        </button>
      </div>
    </div>
  );
}

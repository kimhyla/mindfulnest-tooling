// StitcherSlotWaveform — per-slot SFX strip drop target (Q1 Option C: sfx-strip → lib-sfx).

import { useRef } from 'preact/hooks';
import { acceptDragForTarget, makeDropTarget, type DragPayload } from '../utils/dragdrop';
import type { SfxCue } from './phase/SfxCuePopover';

export interface StitcherSlotWaveformProps {
  slotKey: string;
  videoDurMs: number;
  cues: ReadonlyArray<SfxCue>;
  onSfxDrop: (lib_key: string, source_path: string, offset_ms: number) => void;
  onCueClick: (cue_id: string, anchor: { x: number; y: number }) => void;
}

export function StitcherSlotWaveform({
  slotKey,
  videoDurMs,
  cues,
  onSfxDrop,
  onCueClick,
}: StitcherSlotWaveformProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  const dropHandlers = makeDropTarget(
    (payload: DragPayload, e: DragEvent) => {
      if (payload.kind !== 'lib-sfx') return;
      if (videoDurMs <= 0) return;
      const wrapper = wrapperRef.current;
      if (!wrapper) return;
      const box = wrapper.getBoundingClientRect();
      if (box.width <= 0) return;
      const relativeX = (e.clientX - box.left) / box.width;
      const clamped = Math.max(0, Math.min(1, relativeX));
      const offsetMs = Math.round(clamped * videoDurMs);
      onSfxDrop(payload.lib_key, payload.source_path, offsetMs);
    },
    acceptDragForTarget('sfx-strip'),
    'sfx-strip',
  );

  const cuePctLeft = (cue: SfxCue): number => {
    if (videoDurMs <= 0) return 0;
    return Math.max(0, Math.min(100, (cue.offset_ms / videoDurMs) * 100));
  };

  return (
    // CI fix #4: consolidated to single div (Q1's outer-wrapper pattern
    // broke G3 — drops on outer never reached inner-element drop handlers).
    // Restores the original pre-Q1 DOM shape where slot-waveform testid +
    // drop handlers + data-drop-target-kind are all on the SAME element.
    /* eslint-disable-next-line jsx-a11y/no-static-element-interactions */
    <div
      ref={wrapperRef}
      class="mn-stitcher-slot-waveform mn-drop-target"
      data-testid={`stitcher-slot-waveform-${slotKey}`}
      data-drop-target-kind="sfx-strip"
      data-slot-key={slotKey}
      data-video-dur-ms={videoDurMs}
      data-cue-count={cues.length}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
    >
      <div class="mn-stitcher-slot-waveform-canvas" />
      <div class="mn-stitcher-slot-waveform-cue-overlay">
        {cues.map((cue) => (
          <div
            key={cue.id}
            data-testid={`stitcher-sfx-cue-marker-${slotKey}-${cue.id}`}
            data-offset-ms={cue.offset_ms}
            class="mn-stitcher-sfx-cue-marker"
            style={{ left: `${cuePctLeft(cue)}%` }}
            onClick={(e: MouseEvent) =>
              onCueClick(cue.id, { x: e.clientX, y: e.clientY })
            }
            title={`${cue.name ?? cue.source_path.split('/').pop() ?? cue.id} @ ${(cue.offset_ms / 1000).toFixed(1)}s`}
          />
        ))}
      </div>
    </div>
  );
}

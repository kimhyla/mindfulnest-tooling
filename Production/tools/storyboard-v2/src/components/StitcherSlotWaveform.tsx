// StitcherSlotWaveform — per-slot drop target with cue markers for SFX cue
// authoring. Per S5.5g spec §3.2 + STITCHER_SFX_CUE_UI_V1 (HARD).
//
// Why a separate component (not WaveformTimeline reuse):
//   - WaveformTimeline (S5.5f) is wired tightly to watercolor cues with
//     `cue.animation_type` + `lib-watercolor` drop kind. Extending it to a
//     discriminated-union of cue kinds would invade the Phase A/B test
//     surface. A sibling component for SFX semantics keeps each surface
//     self-contained and Phase B's risk bounded.
//   - Stitcher slots are short (intro/resolution ~30s, phase_a/b ~30-60s)
//     and don't require WaveSurfer's full audio decode + zoom UI; a static
//     drop-target rectangle with positioned cue markers is sufficient and
//     stays well under the slot's UI budget.
//
// Contract:
//   - Drop target accepts `lib-sfx` payloads only (filter dropped on other kinds)
//   - onSfxDrop receives (lib_key, source_path, offset_ms) where offset_ms
//     is computed from drop_x / wrapper_width × video_dur_ms
//   - onCueClick fires when a marker is clicked; the parent opens the popover

import { useRef } from 'preact/hooks';
import { makeDropTarget, type DragPayload } from '../utils/dragdrop';
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
    (payload) => payload.kind === 'lib-sfx',
  );

  const cuePctLeft = (cue: SfxCue): number => {
    if (videoDurMs <= 0) return 0;
    return Math.max(0, Math.min(100, (cue.offset_ms / videoDurMs) * 100));
  };

  return (
    <div
      ref={wrapperRef}
      class="mn-stitcher-slot-waveform mn-drop-target"
      data-testid={`stitcher-slot-waveform-${slotKey}`}
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

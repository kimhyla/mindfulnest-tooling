// StitcherTransitionSelector — kind dropdown + audio_xfade_ms input for one
// per-boundary transition. Per spec §3.3 + Q1 LOCKED 2026-05-04 +
// STITCHER_TRANSITIONS_V1 (HARD).
//
// Transition shape (handoff §3.3):
//   { after_slot, kind: 'crossfade'|'cut'|'dissolve', fade_ms,
//     audio_xfade_ms, source_path? }
//
// kind semantics:
//   'cut'       — pipeline skips transition synthesis; audio_xfade_ms ignored
//   'crossfade' — existing trans_<after_slot> SFX cue synthesis; audio_xfade_ms
//                 controls SFX fadein/fadeout duration
//   'dissolve'  — visual fadeblack at boundary; audio_xfade_ms=0 → hard audio
//                 cut; audio_xfade_ms>0 → also crossfade audio across boundary
//
// Server default if kind absent: 'crossfade' (backward compat for legacy jobs).
// Server default if audio_xfade_ms absent: fade_ms (audio matches visual).

import { useState } from 'preact/hooks';
import { DEFAULT_PHASE_TRANSITION_FADE_MS } from '../utils/stitchModulePreview';

export type TransitionKind = 'crossfade' | 'cut' | 'dissolve';

export interface Transition {
  after_slot: number;
  kind: TransitionKind;
  fade_ms: number;
  audio_xfade_ms: number;
  source_path?: string;
  audio_name?: string;
}

export interface StitcherTransitionSelectorProps {
  afterSlot: number;
  /** Existing transition entry for this boundary, or null if none yet. */
  transition: Transition | null;
  onChange: (next: Transition) => void;
}

const KIND_CHOICES: Array<{ value: TransitionKind; label: string }> = [
  { value: 'crossfade', label: 'Crossfade' },
  { value: 'cut', label: 'Cut' },
  { value: 'dissolve', label: 'Dissolve' },
];

const DEFAULT_FADE_MS = DEFAULT_PHASE_TRANSITION_FADE_MS;

export function StitcherTransitionSelector({
  afterSlot,
  transition,
  onChange,
}: StitcherTransitionSelectorProps) {
  const initial: Transition = transition ?? {
    after_slot: afterSlot,
    kind: 'dissolve',
    fade_ms: DEFAULT_FADE_MS,
    audio_xfade_ms: 0,
    source_path: '',
  };
  const [kind, setKind] = useState<TransitionKind>(initial.kind);
  const [audioXfadeMs, setAudioXfadeMs] = useState<number>(
    initial.audio_xfade_ms,
  );

  const commit = (patch: Partial<Transition>) => {
    onChange({
      ...initial,
      kind,
      audio_xfade_ms: audioXfadeMs,
      ...patch,
    });
  };

  const onKindChange = (e: Event) => {
    const v = (e.target as HTMLSelectElement).value as TransitionKind;
    setKind(v);
    commit({ kind: v });
  };

  const onAudioXfadeBlur = () => {
    commit({ audio_xfade_ms: audioXfadeMs });
  };

  // audio_xfade_ms control is meaningful for crossfade + dissolve; for cut it
  // is ignored server-side. Hide the input when kind='cut' to avoid implying
  // it has effect.
  const showAudioXfade = kind !== 'cut';

  return (
    <div
      class="mn-stitcher-transition"
      data-testid={`stitcher-transition-after-${afterSlot}`}
      data-after-slot={afterSlot}
      data-kind={kind}
    >
      <label class="mn-dim mn-stitcher-transition-label">trans:</label>
      <select
        class="mn-stitcher-transition-kind"
        data-testid={`stitcher-transition-kind-after-${afterSlot}`}
        value={kind}
        onChange={onKindChange}
      >
        {KIND_CHOICES.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
      {showAudioXfade ? (
        <label class="mn-stitcher-transition-audio">
          <span class="mn-dim">audio xfade (ms)</span>
          <input
            type="number"
            data-testid={`stitcher-transition-audio-xfade-after-${afterSlot}`}
            min={0}
            max={5000}
            step={50}
            value={audioXfadeMs}
            onInput={(e: Event) =>
              setAudioXfadeMs(Number((e.target as HTMLInputElement).value))
            }
            onBlur={onAudioXfadeBlur}
          />
        </label>
      ) : null}
    </div>
  );
}

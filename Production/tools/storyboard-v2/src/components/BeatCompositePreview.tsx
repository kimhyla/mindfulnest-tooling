// BeatCompositePreview — pre-lipsync synchronized animation + TTS preview.
// F-BEAT-PREVIEW-001 / blocker #127: dial in audio_delay before lipsync submit.
// Browser-side only — no new server endpoints.

import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { SERVER_BASE } from '../api/endpoints';

export interface BeatCompositePreviewBeat {
  _version?: number;
  audio_file?: string;
  phase_1?: {
    options?: Array<{ file?: string; status?: string }>;
    selected_option?: number;
  };
}

export interface BeatCompositePreviewProps {
  index: number;
  beatId: string;
  eventId: string;
  beat: BeatCompositePreviewBeat;
  /** Current delay (slider or persisted) in seconds — audio starts N s after video. */
  audioDelay: string | number;
}

function parseDelaySec(raw: string | number): number {
  const n = typeof raw === 'number' ? raw : parseFloat(raw);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

export function BeatCompositePreview({
  index,
  beatId,
  eventId,
  beat,
  audioDelay,
}: BeatCompositePreviewProps) {
  const optionCount = beat.phase_1?.options?.length ?? 0;
  const defaultOpt = (() => {
    const sel = beat.phase_1?.selected_option;
    if (typeof sel === 'number' && sel >= 1 && sel <= optionCount) return sel;
    // Default to option 1. The component is gated on
    // beat.phase_1?.selected_option != null at the parent, so optionCount >= 1
    // is invariant when we render. (Defensive fallback to 1 if invariant broken.)
    return 1;
  })();

  const [previewOpt, setPreviewOpt] = useState(defaultOpt);
  // Session-close review F-127 / BeatCompositePreview: resync local preview
  // option when parent beat refreshes after onSelectOption or poll — without
  // this, previewOpt stays on the pre-mutation selection.
  useEffect(() => {
    const sel = beat.phase_1?.selected_option;
    if (typeof sel === 'number' && sel >= 1 && sel <= optionCount) {
      setPreviewOpt(sel);
    }
  }, [beat.phase_1?.selected_option, optionCount]);
  const [isPlaying, setIsPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const delayTimerRef = useRef<number | null>(null);

  const audioDelaySec = parseDelaySec(audioDelay);
  const version = beat._version ?? 0;

  const optFile = beat.phase_1?.options?.[previewOpt - 1]?.file;
  const videoSrc = optFile
    ? `${SERVER_BASE}/asset/${optFile}?v=${version}`
    : null;
  const audioSrc = beat.audio_file
    ? `${SERVER_BASE}/api/beat/audio/${encodeURIComponent(beatId)}?event_id=${encodeURIComponent(eventId)}&v=${version}`
    : null;

  const clearDelayTimer = useCallback(() => {
    if (delayTimerRef.current !== null) {
      window.clearTimeout(delayTimerRef.current);
      delayTimerRef.current = null;
    }
  }, []);

  const stopPlayback = useCallback(() => {
    clearDelayTimer();
    try { videoRef.current?.pause(); } catch { /* defensive */ }
    try { audioRef.current?.pause(); } catch { /* defensive */ }
    setIsPlaying(false);
  }, [clearDelayTimer]);

  const scheduleAudioAfterDelay = useCallback(() => {
    const aud = audioRef.current;
    if (!aud) return;
    aud.currentTime = 0;
    clearDelayTimer();
    const ms = Math.round(audioDelaySec * 1000);
    if (ms > 0) {
      delayTimerRef.current = window.setTimeout(() => {
        delayTimerRef.current = null;
        void aud.play().catch(() => {});
      }, ms);
    } else {
      void aud.play().catch(() => {});
    }
  }, [audioDelaySec, clearDelayTimer]);

  const startPlayback = useCallback(async () => {
    const vid = videoRef.current;
    const aud = audioRef.current;
    if (!vid || !aud || !videoSrc || !audioSrc) return;
    clearDelayTimer();
    vid.currentTime = 0;
    aud.currentTime = 0;
    try {
      await vid.play();
    } catch {
      setIsPlaying(false);
      return;
    }
    scheduleAudioAfterDelay();
    setIsPlaying(true);
  }, [videoSrc, audioSrc, clearDelayTimer, scheduleAudioAfterDelay]);

  const onTogglePlay = () => {
    if (isPlaying) {
      stopPlayback();
      return;
    }
    void startPlayback();
  };

  useEffect(() => {
    // When the previewed option or audio_delay changes, stop any in-flight
    // playback so the next play() reuses a clean state. We intentionally
    // re-run on previewOpt/audioDelaySec changes only — isPlaying is read at
    // effect-fire time but adding it to deps would re-fire on every
    // play/pause toggle (loop). stopPlayback is wrapped in useCallback with
    // stable deps, so its identity doesn't drift.
    if (isPlaying) stopPlayback();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewOpt, audioDelaySec]);

  useEffect(() => () => {
    clearDelayTimer();
    try { videoRef.current?.pause(); } catch { /* defensive */ }
    try { audioRef.current?.pause(); } catch { /* defensive */ }
  }, [clearDelayTimer]);

  const onVideoEnded = () => {
    stopPlayback();
  };

  if (!videoSrc || !audioSrc) return null;

  return (
    <div
      class="mn-beat-composite-preview"
      data-testid={`beat-${index}-composite-preview`}
    >
      <span class="mn-beat-button-group-label">Sync preview:</span>
      {optionCount > 1 ? (
        <select
          class="mn-beat-composite-preview-opt"
          data-testid={`beat-${index}-composite-preview-option`}
          value={String(previewOpt)}
          onChange={(e) => {
            setPreviewOpt(Number((e.target as HTMLSelectElement).value));
          }}
          disabled={isPlaying}
          aria-label="Animation option for sync preview"
        >
          {Array.from({ length: optionCount }).map((_, i) => {
            const oi = i + 1;
            const opt = beat.phase_1?.options?.[i];
            const ready = !!(opt?.file && opt?.status !== 'pending' && opt?.status !== 'failed');
            return (
              <option key={oi} value={String(oi)} disabled={!ready}>
                opt {oi}{!ready ? ' (pending)' : ''}
              </option>
            );
          })}
        </select>
      ) : null}
      <button
        type="button"
        class="mn-btn mn-btn-small"
        data-testid={`beat-${index}-composite-preview-play`}
        onClick={onTogglePlay}
        title="Play animation + TTS with audio_delay offset (pre-lipsync)"
      >
        {isPlaying ? '⏸' : '▶'} composite
      </button>
      <video
        ref={videoRef}
        src={videoSrc}
        class="mn-storyboard-preview-video mn-beat-composite-preview-video"
        playsInline
        preload="auto"
        muted
        onEnded={onVideoEnded}
        data-testid={`beat-${index}-composite-preview-video`}
      />
      <audio
        ref={audioRef}
        src={audioSrc}
        preload="auto"
        style={{ display: 'none' }}
        data-testid={`beat-${index}-composite-preview-audio`}
      />
    </div>
  );
}


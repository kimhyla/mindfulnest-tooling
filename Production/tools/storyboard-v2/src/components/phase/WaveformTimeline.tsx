// WaveformTimeline — WaveSurfer.js v7 audio timeline for Phase A/B producers.
// Per LD WAVESURFER_TIMELINE_INTEGRATION_V1 + LD-330 + LD-472.
//
// Responsibilities (Phase B scope):
//  - Mount WaveSurfer over a container, load the audio source priority winner
//    (lipsync > mixed > stem; resolved by PhaseProducer)
//  - Expose duration via the ready event so cue markers can be positioned
//  - Click-to-seek on the waveform
//  - Render absolute-positioned cue markers from `phase_X_watercolor_cues_json`
//
// Phase C will extend this with: drag-drop watercolor → cue create, cue
// drag-to-reposition, popover on marker click.
//
// Cursor v8 Q1: WaveSurfer.create / destroy cycle leaves no WebAudio leaks —
// every effect that creates an instance returns a cleanup that calls .destroy().

import { useEffect, useRef, useState } from 'preact/hooks';
import WaveSurfer from 'wavesurfer.js';
import { makeDropTarget, type DragPayload } from '../../utils/dragdrop';

export interface WatercolorCue {
  id: string;
  watercolor_key: string;
  offset_ms: number;
  duration_ms?: number;
  animation_type?: string;
  volume?: number;
}

export interface WaveformTimelineProps {
  audioSrc: string | null;
  sourceLabel: 'lipsync' | 'mixed' | 'stem' | null;
  sourceFilename?: string | null;
  cues: ReadonlyArray<WatercolorCue>;
  onCueClick?: (cueId: string, anchor: { x: number; y: number }) => void;
  onWaveformClick?: (timeMs: number) => void;
  onReady?: (durationMs: number) => void;
  /** Phase C — drop watercolor tile to create a cue at offset_ms = dropX/width × duration. */
  onWatercolorDrop?: (lib_key: string, offset_ms: number) => void;
}

export function WaveformTimeline(props: WaveformTimelineProps) {
  const {
    audioSrc,
    sourceLabel,
    sourceFilename,
    cues,
    onCueClick,
    onWaveformClick,
    onReady,
    onWatercolorDrop,
  } = props;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [currentMs, setCurrentMs] = useState<number>(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  // (re)mount WaveSurfer whenever audioSrc changes.
  useEffect(() => {
    if (!audioSrc || !containerRef.current) return;
    setLoadError(null);
    setDurationMs(null);
    setCurrentMs(0);

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#7d6b5d',
      progressColor: '#3a2e26',
      cursorColor: '#c33',
      height: 80,
      normalize: true,
      barWidth: 2,
      barGap: 1,
    });
    wsRef.current = ws;

    const onReadyHandler = () => {
      const d = ws.getDuration() * 1000;
      setDurationMs(d);
      onReady?.(d);
    };
    const onAudioProcess = () => {
      setCurrentMs(ws.getCurrentTime() * 1000);
    };
    // 'click' fires with relativeX 0..1 (WaveSurfer v7).
    const onWsClick = (relativeX: number) => {
      if (!Number.isFinite(relativeX)) return;
      ws.seekTo(relativeX);
      const total = ws.getDuration() * 1000;
      const t = relativeX * total;
      setCurrentMs(t);
      onWaveformClick?.(t);
    };

    ws.on('ready', onReadyHandler);
    ws.on('audioprocess', onAudioProcess);
    ws.on('seeking', onAudioProcess);
    ws.on('click', onWsClick);

    ws.load(audioSrc).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
    });

    return () => {
      try {
        ws.destroy();
      } catch {
        // destroy() throws if AbortError is in flight — non-fatal at unmount
      }
      if (wsRef.current === ws) wsRef.current = null;
    };
    // onReady / onWaveformClick are intentionally captured at mount time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioSrc]);

  // Cue marker horizontal position (% of timeline width).
  const cuePctLeft = (cue: WatercolorCue): number => {
    if (!durationMs || durationMs <= 0) return 0;
    return Math.max(0, Math.min(100, (cue.offset_ms / durationMs) * 100));
  };

  // Drop target — `kind: 'lib-watercolor'` payloads land here and become cues.
  // The drop X position relative to the wrapper element determines offset_ms.
  const dropHandlers = makeDropTarget(
    (payload: DragPayload, e: DragEvent) => {
      if (payload.kind !== 'lib-watercolor') return;
      if (!durationMs || durationMs <= 0) return;
      const wrapper = wrapperRef.current;
      if (!wrapper) return;
      const box = wrapper.getBoundingClientRect();
      const relativeX = (e.clientX - box.left) / box.width;
      const clamped = Math.max(0, Math.min(1, relativeX));
      const offsetMs = Math.round(clamped * durationMs);
      onWatercolorDrop?.(payload.lib_key, offsetMs);
    },
    (payload) => payload.kind === 'lib-watercolor',
  );

  if (!audioSrc) {
    return (
      <div
        class="mn-waveform-timeline mn-waveform-empty"
        data-testid="waveform-timeline-empty"
      >
        <span class="mn-dim">
          No audio yet — generate a stem from the script or send for lipsync.
        </span>
      </div>
    );
  }

  return (
    <div
      ref={wrapperRef}
      class="mn-waveform-timeline mn-drop-target"
      data-testid="waveform-timeline"
      data-audio-src={audioSrc}
      data-source-label={sourceLabel ?? ''}
      data-loaded-duration-ms={durationMs ?? ''}
      data-current-time-ms={Math.round(currentMs)}
      data-cue-count={cues.length}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
    >
      <div class="mn-waveform-source-label">
        <strong>Audio ({sourceLabel ?? '—'}):</strong>{' '}
        <span class="mn-dim">{sourceFilename ?? ''}</span>
      </div>
      <div ref={containerRef} class="mn-waveform-canvas" />
      <div class="mn-waveform-cue-overlay">
        {cues.map((cue) => (
          <div
            key={cue.id}
            data-testid={`cue-marker-${cue.id}`}
            data-offset-ms={cue.offset_ms}
            class="mn-waveform-cue-marker"
            style={{ left: `${cuePctLeft(cue)}%` }}
            onClick={(e: MouseEvent) =>
              onCueClick?.(cue.id, { x: e.clientX, y: e.clientY })
            }
            title={`${cue.watercolor_key} @ ${(cue.offset_ms / 1000).toFixed(1)}s`}
          />
        ))}
      </div>
      {loadError ? (
        <div class="mn-waveform-error mn-dim">load error: {loadError}</div>
      ) : null}
    </div>
  );
}

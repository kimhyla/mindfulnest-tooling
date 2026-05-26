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
  /** Called on audioprocess + seeking so the parent can track playback position (ms). */
  onTimeUpdate?: (currentMs: number) => void;
  /** Called when the user drags the right edge of a cue block to resize it. */
  onCueResize?: (cueId: string, newDurationMs: number) => void;
  /**
   * Optional video element to keep in sync with waveform playback.
   * The caller should mute the <video> to avoid double audio (WaveSurfer plays audio).
   * WaveformTimeline drives the video: play/pause/seek mirror WaveSurfer state.
   */
  linkedVideo?: { current: HTMLVideoElement | null };
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
    onTimeUpdate,
    onCueResize,
    linkedVideo,
  } = props;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [currentMs, setCurrentMs] = useState<number>(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isReady, setIsReady] = useState<boolean>(false);
  // Ref mirror of isReady so pointer-event closures always see the current value
  // without needing to be in the useEffect dependency array.
  const isReadyRef = useRef<boolean>(false);

  // (re)mount WaveSurfer whenever audioSrc changes.
  useEffect(() => {
    if (!audioSrc || !containerRef.current) return;
    setLoadError(null);
    setDurationMs(null);
    setCurrentMs(0);
    setIsPlaying(false);
    setIsReady(false);

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#7d6b5d',
      progressColor: '#3a2e26',
      cursorColor: '#c33',
      height: 80,
      normalize: true,
      barWidth: 2,
      barGap: 1,
      // interact:false disables WaveSurfer's built-in click/drag-to-seek handlers.
      // We own all seek logic below via native pointer events, which lets us do
      // smooth drag-seek without WaveSurfer resetting the playhead on mouseup
      // (the dragToSeek:true bug — WaveSurfer v7 fires 'click' with the
      // drag-START relativeX on release, which is 0 when dragging from the left,
      // causing the playhead to snap back to 0:00).
      interact: false,
    });
    wsRef.current = ws;

    const onReadyHandler = () => {
      const d = ws.getDuration() * 1000;
      setDurationMs(d);
      setIsReady(true);
      isReadyRef.current = true;
      onReady?.(d);
    };
    const onAudioProcess = () => {
      const ms = ws.getCurrentTime() * 1000;
      setCurrentMs(ms);
      onTimeUpdate?.(ms);
    };
    // 'seeking' fires after every ws.seekTo() call with the real committed position.
    const onSeeking = () => {
      const ms = ws.getCurrentTime() * 1000;
      setCurrentMs(ms);
      onTimeUpdate?.(ms);
    };

    ws.on('ready', onReadyHandler);
    ws.on('audioprocess', onAudioProcess);
    ws.on('seeking', onSeeking);
    ws.on('play', () => setIsPlaying(true));
    ws.on('pause', () => setIsPlaying(false));
    ws.on('finish', () => setIsPlaying(false));

    // ── Linked video sync ────────────────────────────────────────────────────
    // When a <video> ref is passed (linkedVideo), WaveSurfer is the master clock.
    // The video is muted by the caller; WaveSurfer's WebAudio provides the audio.
    // Access linkedVideo.current inside callbacks so we always get the live element
    // (refs don't trigger re-renders, so captured-at-effect-time is safe).
    // ── lv_play helper ───────────────────────────────────────────────────────
    // Force .muted = true before EVERY play() call.
    // Root cause of the sync bug: WaveSurfer fires 'play' after its internal
    // WebAudio Promise resolves, outside the original user-gesture window.
    // Chrome's autoplay policy blocks video.play() on an unmuted element from
    // an async callback — the Promise is rejected silently because we used
    // .catch(() => {}).  Setting .muted = true imperatively bypasses the policy
    // entirely (muted elements can always autoplay regardless of gesture timing).
    // The JSX `muted` attribute on <video> is insufficient: Preact does not
    // reliably reflect it to the DOM .muted property in all Chrome versions.
    const lv_play = (lv: HTMLVideoElement) => {
      lv.muted = true;
      lv.play().catch(() => {
        // Chrome rejects play() with AbortError when:
        //   (a) lv.currentTime is set while a play() Promise is in-flight
        //   (b) "video-only background media paused to save power" power-saving policy
        // Retry once via rAF — by then the Promise chain is settled and the
        // browser has processed the muted-video policy check.
        if (lv.paused) {
          requestAnimationFrame(() => {
            lv.muted = true;
            lv.play().catch(() => {});
          });
        }
      });
    };
    // ─────────────────────────────────────────────────────────────────────────

    ws.on('play', () => {
      const lv = linkedVideo?.current;
      if (!lv) return;
      // Do NOT set lv.currentTime here. The play button already sets it
      // synchronously in the user-gesture handler before calling ws.play().
      // Setting currentTime here interrupts the in-flight lv.play() Promise
      // (Chrome AbortError: "play() request was interrupted"). The audioprocess
      // drift corrector (below) catches any minor float skew on subsequent ticks.
      lv_play(lv);
    });
    ws.on('pause', () => {
      linkedVideo?.current?.pause();
    });
    ws.on('finish', () => {
      const lv = linkedVideo?.current;
      if (!lv) return;
      lv.pause();
      lv.currentTime = 0;
    });
    ws.on('seeking', () => {
      const lv = linkedVideo?.current;
      if (!lv) return;
      lv.currentTime = ws.getCurrentTime();
      if (!ws.isPlaying()) return;
      lv_play(lv);
    });
    ws.on('audioprocess', () => {
      const lv = linkedVideo?.current;
      if (!lv) return;
      // Correct drift >0.3s to avoid fighting over tiny float jitter.
      // GUARD: only set currentTime when the video is already playing (not paused).
      // Setting currentTime while lv.play() is in-flight (lv.paused=true with a
      // pending Promise) aborts the Promise, which triggers the self-healer below,
      // which calls lv_play() again — creating a loop that keeps the video at 0.
      // When lv.paused=true the self-healer below will call lv_play(); once play()
      // resolves the next audioprocess tick sees paused=false and corrects drift then.
      const drift = Math.abs(lv.currentTime - ws.getCurrentTime());
      if (!lv.paused && drift > 0.3) lv.currentTime = ws.getCurrentTime();
      // Self-healing: if WaveSurfer is playing but video is still paused
      // (e.g. autoplay rejected on first try), restart it.
      // Guard: only self-heal if WaveSurfer is genuinely still playing.
      // Without this, 'audioprocess' fires during the pause flush ticks
      // (WebAudio buffer drain after ws.pause()), sees lv.paused===true,
      // and re-starts the video — causing the desync Kim reported.
      // ws.isPlaying() returns false synchronously after ws.pause(), so
      // this guard makes the healer a no-op during teardown.
      if (lv.paused && ws.isPlaying()) lv_play(lv);
    });
    // ─────────────────────────────────────────────────────────────────────────

    ws.load(audioSrc).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
    });

    // Custom pointer-based seek — replaces WaveSurfer's built-in dragToSeek.
    // Works on mouse, touch (pointer events unify both), and stylus.
    // setPointerCapture() keeps pointermove firing even when the cursor leaves
    // the element mid-drag, so fast drags don't lose tracking.
    const canvas = containerRef.current;
    let isDragging = false;

    const getRelX = (e: PointerEvent): number => {
      const box = canvas.getBoundingClientRect();
      return Math.max(0, Math.min(1, (e.clientX - box.left) / box.width));
    };

    const onPointerDown = (e: PointerEvent) => {
      if (!isReadyRef.current) return;
      isDragging = true;
      canvas.setPointerCapture(e.pointerId);
      ws.seekTo(getRelX(e));
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging) return;
      ws.seekTo(getRelX(e));
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      const rel = getRelX(e);
      ws.seekTo(rel);
      onWaveformClick?.(rel * ws.getDuration() * 1000);
    };
    const onPointerCancel = () => {
      isDragging = false;
    };

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerCancel);

    return () => {
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onPointerCancel);
      isReadyRef.current = false;
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

  // Cue block horizontal position (% of timeline width).
  const cuePctLeft = (cue: WatercolorCue): number => {
    if (!durationMs || durationMs <= 0) return 0;
    return Math.max(0, Math.min(100, (cue.offset_ms / durationMs) * 100));
  };

  // Cue block width (% of timeline width). Min 4px enforced via CSS min-width.
  const cuePctWidth = (cue: WatercolorCue): number => {
    if (!durationMs || durationMs <= 0) return 0;
    const durMs = cue.duration_ms ?? 3000;
    return Math.max(0, Math.min(100 - cuePctLeft(cue), (durMs / durationMs) * 100));
  };

  // Resize handle: pointer capture drag on the right edge of a cue block.
  // INVARIANTS: wrapperRef must be mounted; durationMs must be non-null and > 0.
  const onHandlePointerDown = (
    e: PointerEvent,
    cue: WatercolorCue,
  ) => {
    e.stopPropagation(); // do NOT let the waveform seek handler see this event
    if (!durationMs || durationMs <= 0) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);

    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const onMove = (moveEvt: PointerEvent) => {
      const box = wrapper.getBoundingClientRect();
      const relX = Math.max(0, Math.min(1, (moveEvt.clientX - box.left) / box.width));
      const endMs = relX * durationMs;
      const newDuration = Math.max(0, endMs - cue.offset_ms);
      onCueResize?.(cue.id, Math.round(newDuration));
    };

    const onUp = (upEvt: PointerEvent) => {
      const box = wrapper.getBoundingClientRect();
      const relX = Math.max(0, Math.min(1, (upEvt.clientX - box.left) / box.width));
      const endMs = relX * durationMs;
      const newDuration = Math.max(0, endMs - cue.offset_ms);
      onCueResize?.(cue.id, Math.round(newDuration));
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
    };

    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
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
        <button
          type="button"
          class="mn-btn mn-btn-play"
          data-testid="waveform-play-btn"
          disabled={!isReady}
          onClick={() => {
            const ws = wsRef.current;
            if (!ws) return;
            if (ws.isPlaying()) {
              // Pause: WaveSurfer drives; 'pause' event handler mirrors to video.
              ws.pause();
            } else {
              // Play: call lv.play() SYNCHRONOUSLY in the user-gesture stack
              // BEFORE ws.play() so Chrome's autoplay policy never blocks it.
              // WaveSurfer fires 'play' async (after AudioContext.resume()) —
              // by then we're outside the gesture window and Chrome may block
              // lv.play() even with lv.muted=true (browser-version quirk).
              const lv = linkedVideo?.current;
              if (lv) {
                lv.muted = true;
                lv.currentTime = ws.getCurrentTime();
                lv.play().catch(() => {});
              }
              ws.play();
            }
          }}
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? '⏸ Pause' : '▶ Play'}
        </button>
        <strong>Audio ({sourceLabel ?? '—'}):</strong>{' '}
        <span class="mn-dim">{sourceFilename ?? ''}</span>
        {durationMs ? (
          <span class="mn-dim"> · {(currentMs / 1000).toFixed(1)}s / {(durationMs / 1000).toFixed(1)}s</span>
        ) : null}
      </div>
      <div ref={containerRef} class="mn-waveform-canvas" />
      <div class="mn-waveform-cue-overlay">
        {cues.map((cue) => (
          <div
            key={cue.id}
            data-testid={`cue-marker-${cue.id}`}
            data-offset-ms={cue.offset_ms}
            data-duration-ms={cue.duration_ms ?? 3000}
            class="mn-waveform-cue-block"
            style={{
              left: `${cuePctLeft(cue)}%`,
              width: `${cuePctWidth(cue)}%`,
            }}
            onClick={(e: MouseEvent) => {
              // Only fire cueClick when clicking the block body, not the handle.
              const target = e.target as HTMLElement;
              if (target.classList.contains('mn-waveform-cue-block-handle')) return;
              onCueClick?.(cue.id, { x: e.clientX, y: e.clientY });
            }}
            title={`${cue.watercolor_key} @ ${(cue.offset_ms / 1000).toFixed(1)}s · ${((cue.duration_ms ?? 3000) / 1000).toFixed(1)}s`}
          >
            <div
              class="mn-waveform-cue-block-handle"
              onPointerDown={(e: PointerEvent) => onHandlePointerDown(e, cue)}
            />
          </div>
        ))}
      </div>
      {loadError ? (
        <div class="mn-waveform-error mn-dim">load error: {loadError}</div>
      ) : null}
    </div>
  );
}

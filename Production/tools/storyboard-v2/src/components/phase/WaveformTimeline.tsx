// WaveformTimeline — WaveSurfer.js v7 audio timeline for Phase A/B producers.
// Per LD WAVESURFER_TIMELINE_INTEGRATION_V1 + LD-330 + LD-472.
//
// ── DURABILITY RULES (PHASE_WAVEFORM_PLAY — do not regress, 2026-06-12) ─────
// Enforced by: e2e/phase_waveform_playback.spec.ts + check_storyboard_critical_features.sh
//   PLAY-1  ▶ Play lives in .mn-waveform-source-label — MUST be in shouldSkipSeek()
//           and MUST stopPropagation on pointerdown. Otherwise pointerdown seeks
//           before play(), WaveSurfer swallows AbortError, button stays ▶ Play.
//   PLAY-2  ws.play() MUST run synchronously from the click handler — no await before
//           play() (Chrome user-gesture window).
//   PLAY-3  playback bus control object is stable (one useRef shell + mutate methods);
//           pauseOtherWaveformPlayback matches on busId, never object identity churn.
//   PLAY-4  stopAllPhasePlayback only on tab change — effect() in useEffect with dispose,
//           never bare effect() during App render (app.tsx prevTabRef pattern).
//   PLAY-5  Hidden keep-alive panes pause via MutationObserver on [hidden] only.
// ─────────────────────────────────────────────────────────────────────────────
//
// Responsibilities (Phase A + Phase B — same WaveformTimeline instance per tab):
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

import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import WaveSurfer from 'wavesurfer.js';
import { makeDropTarget, type DragPayload } from '../../utils/dragdrop';
import {
  pauseOtherWaveformPlayback,
  registerWaveformPlaybackControl,
  pauseAllPhasePlayback,
} from '../../utils/waveformPlaybackBus';

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
  /** Stitcher SFX — drop lib-sfx tile; includes default duration_ms window. */
  onSfxDrop?: (
    lib_key: string,
    source_path: string,
    offset_ms: number,
    duration_ms: number,
  ) => void;
  /** When audio is not loaded yet, use this duration for drop + cue block math. */
  fallbackDurationMs?: number;
  /** Hide play controls (Stitcher per-slot strip). */
  compact?: boolean;
  /** Override empty-state copy (Stitcher: "Load video…"). */
  emptyMessage?: string;
  /** Prefix for cue block testids (Stitcher: stitcher-sfx-cue-marker-intro-). */
  cueTestIdPrefix?: string;
  /** Override root data-testid (Stitcher: stitcher-slot-waveform-intro). */
  timelineTestId?: string;
  /** Optional extra class on cue blocks (Stitcher SFX styling). */
  cueBlockClassName?: string;
  /** Called on audioprocess + seeking so the parent can track playback position (ms). */
  onTimeUpdate?: (currentMs: number) => void;
  /** Called when the user drags a cue block edge (left = move start, right = move end). */
  onCueRangeChange?: (cueId: string, offsetMs: number, durationMs: number) => void;
  /** Amber box = region TO REMOVE before lipsync / Apply Cut. */
  stemCutStartMs?: number;
  stemCutEndMs?: number;
  stemCutEditable?: boolean;
  onStemCutChange?: (cutStartMs: number, cutEndMs: number) => void;
  /** @deprecated Use stemCutStartMs — legacy prop name. */
  stemTrimStartMs?: number;
  /** @deprecated Use stemCutEndMs — legacy prop name. */
  stemTrimBackMs?: number;
  stemTrimEditable?: boolean;
  onStemTrimChange?: (trimStartMs: number, trimBackMs: number) => void;
  /** @deprecated Prefer onCueRangeChange — right-edge-only resize shim. */
  onCueResize?: (cueId: string, newDurationMs: number) => void;
  /** Called whenever WaveSurfer's play/pause state changes (authoritative source). */
  onPlayStateChange?: (playing: boolean) => void;
  /**
   * Optional video element to keep in sync with waveform playback.
   * The caller should mute the <video> to avoid double audio (WaveSurfer plays audio).
   * WaveformTimeline drives the video: play/pause/seek mirror WaveSurfer state.
   */
  linkedVideo?: { current: HTMLVideoElement | null };
  /** Parent can call play()/pause() from Preview with Overlay (same user-gesture stack). */
  playbackControl?: { current: WaveformPlaybackControl | null };
}

export interface WaveformPlaybackControl {
  readonly busId: symbol;
  play: (opts?: { fromStart?: boolean }) => boolean;
  pause: () => void;
  readonly isReady: boolean;
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
    onSfxDrop,
    fallbackDurationMs,
    compact,
    emptyMessage,
    cueTestIdPrefix,
    timelineTestId,
    cueBlockClassName,
    onTimeUpdate,
    onCueRangeChange,
    onCueResize,
    onPlayStateChange,
    linkedVideo,
    playbackControl,
    stemCutStartMs,
    stemCutEndMs,
    stemCutEditable,
    onStemCutChange,
    stemTrimStartMs,
    stemTrimBackMs,
    stemTrimEditable,
    onStemTrimChange,
  } = props;

  const cutStartMs = stemCutStartMs ?? stemTrimStartMs ?? 0;
  const cutEndMs = stemCutEndMs ?? stemTrimBackMs ?? 0;
  const cutEditable = stemCutEditable ?? stemTrimEditable ?? false;
  const onCutChange = onStemCutChange ?? onStemTrimChange;

  const MIN_CUE_DURATION_MS = 250;
  const MIN_STEM_CUT_MS = 250;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [currentMs, setCurrentMs] = useState<number>(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isReady, setIsReady] = useState<boolean>(false);
  /** Live drag preview — avoids hammering server with patch on every pointermove. */
  const [dragDraft, setDragDraft] = useState<{
    id: string;
    offset_ms: number;
    duration_ms: number;
  } | null>(null);
  const [stemCutDraft, setStemCutDraft] = useState<{
    start_ms: number;
    end_ms: number;
  } | null>(null);
  // Drop drag preview when server props change (e.g. Apply Cut clears cut keys).
  useEffect(() => {
    setStemCutDraft(null);
  }, [audioSrc, cutStartMs, cutEndMs]);
  // Ref mirror of isReady so pointer-event closures always see the current value.
  const isReadyRef = useRef<boolean>(false);
  const onWaveformClickRef = useRef(onWaveformClick);
  onWaveformClickRef.current = onWaveformClick;

  const timelineDurationMs = durationMs ?? fallbackDurationMs ?? null;

  const cuePctLeft = (cue: WatercolorCue): number => {
    if (!timelineDurationMs || timelineDurationMs <= 0) return 0;
    return Math.max(0, Math.min(100, (cue.offset_ms / timelineDurationMs) * 100));
  };

  const cuePctWidth = (cue: WatercolorCue): number => {
    if (!timelineDurationMs || timelineDurationMs <= 0) return 0;
    const durMs = cue.duration_ms ?? 3000;
    return Math.max(0, Math.min(100 - cuePctLeft(cue), (durMs / timelineDurationMs) * 100));
  };

  const hardPause = useCallback(() => {
    wsRef.current?.pause();
    linkedVideo?.current?.pause();
    setIsPlaying(false);
    const pane = wrapperRef.current?.closest('.mn-tab-pane-keepalive');
    pane?.querySelectorAll('video, audio').forEach((el) => {
      if (el instanceof HTMLMediaElement) el.pause();
    });
  }, [linkedVideo]);

  /** Keep ▶/⏸ label aligned with WaveSurfer even if a play/pause event is dropped. */
  const syncPlayUi = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    const playing = ws.isPlaying();
    setIsPlaying(playing);
    onPlayStateChange?.(playing);
  }, [onPlayStateChange]);

  // WaveSurfer mount — audioSrc changes only. Seek handlers live in a separate
  // effect below (LD WAVEFORM_DRAG_SEEK_V1).
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
      if (stopPlaybackIfHiddenPane()) return;
      const ms = ws.getCurrentTime() * 1000;
      setCurrentMs(ms);
      onTimeUpdate?.(ms);
      syncPlayUi();
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

    const stopPlaybackIfHiddenPane = (): boolean => {
      const pane = wrapperRef.current?.closest('.mn-tab-pane-keepalive') as HTMLElement | null;
      if (!pane?.hidden) return false;
      ws.pause();
      linkedVideo?.current?.pause();
      return true;
    };

    ws.on('play', () => {
      if (stopPlaybackIfHiddenPane()) return;
      setIsPlaying(true);
      onPlayStateChange?.(true);
    });
    ws.on('pause', () => {
      setIsPlaying(false);
      onPlayStateChange?.(false);
    });
    ws.on('finish', () => {
      setIsPlaying(false);
      onPlayStateChange?.(false);
    });

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
      if (stopPlaybackIfHiddenPane()) return;
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
      if (stopPlaybackIfHiddenPane()) return;
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

    return () => {
      isReadyRef.current = false;
      try {
        ws.pause();
        ws.destroy();
      } catch {
        // destroy() throws if AbortError is in flight — non-fatal at unmount
      }
      if (wsRef.current === ws) wsRef.current = null;
    };
    // onReady / onWaveformClick are intentionally captured at mount time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioSrc, syncPlayUi]);

  // Keep-alive: pause when this phase tab is hidden so background WaveSurfer
  // instances do not block playback on the visible tab (Chrome autoplay policy).
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const pane = wrapper.closest('.mn-tab-pane-keepalive') as HTMLElement | null;
    if (!pane) return;

    const pauseIfHidden = () => {
      if (!pane.hidden) return;
      hardPause();
    };

    const pauseIfHiddenAndStopMedia = () => {
      pauseIfHidden();
      // Also pause any HTML media in this pane (lipsync preview, stitched clip).
      pane.querySelectorAll('video, audio').forEach((el) => {
        if (el instanceof HTMLMediaElement) {
          el.pause();
        }
      });
    };

    pauseIfHiddenAndStopMedia();
    const obs = new MutationObserver(pauseIfHiddenAndStopMedia);
    obs.observe(pane, { attributes: true, attributeFilter: ['hidden'] });
    return () => obs.disconnect();
  }, [audioSrc, linkedVideo, hardPause]);

  // Drag-seek — separate effect so handlers bind AFTER WaveSurfer ready + wrapper
  // ref exist. Regression history:
  //   2026-05-25 (0ff0be0): interact:false + canvas pointer handlers — worked
  //   until cue overlay (8604e4c) blocked canvas hits.
  //   2026-06-10 (c3ab386): seek-layer inside WS effect — broke because
  //   seekLayerRef.current was null on first run → early return left ZERO
  //   handlers attached (playhead stuck / snap-to-0).
  // Durable rule: bind on wrapperRef; never early-return before WS cleanup;
  // skip source-label (▶ Play lives there), cue blocks, cut handles; deps include isReady.
  useEffect(() => {
    const wrapper = wrapperRef.current;
    const ws = wsRef.current;
    if (!wrapper || !ws || !isReady || !audioSrc) return;

    let isDragging = false;
    let seekPointerId: number | null = null;

    const getRelX = (e: PointerEvent): number => {
      const box = wrapper.getBoundingClientRect();
      const trackLeft = box.left + 8;
      const trackWidth = box.width - 16;
      if (trackWidth <= 0) return 0;
      return Math.max(0, Math.min(1, (e.clientX - trackLeft) / trackWidth));
    };

    const shouldSkipSeek = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) return false;
      return Boolean(
        target.closest(
          '.mn-waveform-source-label, .mn-waveform-cue-block-handle, .mn-waveform-stem-trim-handle, .mn-waveform-cue-block',
        ),
      );
    };

    const onPointerDown = (e: PointerEvent) => {
      if (!isReadyRef.current) return;
      if (shouldSkipSeek(e.target)) return;
      isDragging = true;
      seekPointerId = e.pointerId;
      wrapper.setPointerCapture(e.pointerId);
      ws.seekTo(getRelX(e));
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging || e.pointerId !== seekPointerId) return;
      ws.seekTo(getRelX(e));
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging || e.pointerId !== seekPointerId) return;
      isDragging = false;
      seekPointerId = null;
      const rel = getRelX(e);
      ws.seekTo(rel);
      onWaveformClickRef.current?.(rel * ws.getDuration() * 1000);
    };
    const onPointerCancel = (e: PointerEvent) => {
      if (seekPointerId !== null && e.pointerId !== seekPointerId) return;
      isDragging = false;
      seekPointerId = null;
    };

    wrapper.addEventListener('pointerdown', onPointerDown);
    wrapper.addEventListener('pointermove', onPointerMove);
    wrapper.addEventListener('pointerup', onPointerUp);
    wrapper.addEventListener('pointercancel', onPointerCancel);

    return () => {
      wrapper.removeEventListener('pointerdown', onPointerDown);
      wrapper.removeEventListener('pointermove', onPointerMove);
      wrapper.removeEventListener('pointerup', onPointerUp);
      wrapper.removeEventListener('pointercancel', onPointerCancel);
    };
  }, [audioSrc, isReady]);

  const emitCueRange = (cueId: string, offsetMs: number, durationMs: number) => {
    const clampedDuration = Math.max(MIN_CUE_DURATION_MS, Math.round(durationMs));
    const clampedOffset = Math.max(0, Math.round(offsetMs));
    if (onCueRangeChange) {
      onCueRangeChange(cueId, clampedOffset, clampedDuration);
      return;
    }
    onCueResize?.(cueId, clampedDuration);
  };

  const previewCueRange = (cueId: string, offsetMs: number, durationMs: number) => {
    setDragDraft({
      id: cueId,
      offset_ms: Math.max(0, Math.round(offsetMs)),
      duration_ms: Math.max(MIN_CUE_DURATION_MS, Math.round(durationMs)),
    });
  };

  const displayCues = cues.map((c) => {
    if (!dragDraft || dragDraft.id !== c.id) return c;
    return { ...c, offset_ms: dragDraft.offset_ms, duration_ms: dragDraft.duration_ms };
  });

  const relXFromPointer = (wrapper: HTMLDivElement, evt: PointerEvent): number => {
    const box = wrapper.getBoundingClientRect();
    return Math.max(0, Math.min(1, (evt.clientX - box.left) / box.width));
  };

  const displayStemCut = stemCutDraft ?? {
    start_ms: cutStartMs,
    end_ms: cutEndMs,
  };

  const stemCutPctLeft = (): number => {
    if (!durationMs || durationMs <= 0) return 0;
    return Math.max(0, Math.min(100, (displayStemCut.start_ms / durationMs) * 100));
  };

  const stemCutPctWidth = (): number => {
    if (!durationMs || durationMs <= 0) return 0;
    const cutMs = Math.max(0, displayStemCut.end_ms - displayStemCut.start_ms);
    return Math.max(0, Math.min(100 - stemCutPctLeft(), (cutMs / durationMs) * 100));
  };

  const emitStemCut = (startMs: number, endMs: number) => {
    onCutChange?.(
      Math.max(0, Math.round(startMs)),
      Math.max(0, Math.round(endMs)),
    );
  };

  const previewStemCut = (startMs: number, endMs: number) => {
    setStemCutDraft({
      start_ms: Math.max(0, Math.round(startMs)),
      end_ms: Math.max(0, Math.round(endMs)),
    });
  };

  // Right handle: drag end time forward/back — offset fixed, duration changes.
  const onRightHandlePointerDown = (e: PointerEvent, cue: WatercolorCue) => {
    e.stopPropagation();
    e.preventDefault();
    if (!timelineDurationMs || timelineDurationMs <= 0) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startOffset = cue.offset_ms;

    const applyPreview = (evt: PointerEvent) => {
      const endMs = relXFromPointer(wrapper, evt) * timelineDurationMs;
      const maxEnd = timelineDurationMs;
      const clampedEnd = Math.max(startOffset + MIN_CUE_DURATION_MS, Math.min(maxEnd, endMs));
      previewCueRange(cue.id, startOffset, clampedEnd - startOffset);
    };

    const onUp = (upEvt: PointerEvent) => {
      const endMs = relXFromPointer(wrapper, upEvt) * timelineDurationMs;
      const maxEnd = timelineDurationMs;
      const clampedEnd = Math.max(startOffset + MIN_CUE_DURATION_MS, Math.min(maxEnd, endMs));
      setDragDraft(null);
      emitCueRange(cue.id, startOffset, clampedEnd - startOffset);
      handle.removeEventListener('pointermove', applyPreview);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', applyPreview);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  };

  // Left handle: drag start time earlier/later — end time fixed, offset + duration change.
  const onLeftHandlePointerDown = (e: PointerEvent, cue: WatercolorCue) => {
    e.stopPropagation();
    e.preventDefault();
    if (!timelineDurationMs || timelineDurationMs <= 0) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startDuration = cue.duration_ms ?? 3000;
    const endMs = cue.offset_ms + startDuration;

    const applyPreview = (evt: PointerEvent) => {
      const newOffset = relXFromPointer(wrapper, evt) * timelineDurationMs;
      const clampedOffset = Math.max(
        0,
        Math.min(endMs - MIN_CUE_DURATION_MS, newOffset),
      );
      previewCueRange(cue.id, clampedOffset, endMs - clampedOffset);
    };

    const onUp = (upEvt: PointerEvent) => {
      const newOffset = relXFromPointer(wrapper, upEvt) * timelineDurationMs;
      const clampedOffset = Math.max(
        0,
        Math.min(endMs - MIN_CUE_DURATION_MS, newOffset),
      );
      setDragDraft(null);
      emitCueRange(cue.id, clampedOffset, endMs - clampedOffset);
      handle.removeEventListener('pointermove', applyPreview);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', applyPreview);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  };

  const onStemCutLeftHandlePointerDown = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!durationMs || durationMs <= 0 || !cutEditable) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const endMs = displayStemCut.end_ms > 0
      ? displayStemCut.end_ms
      : durationMs;

    const applyPreview = (evt: PointerEvent) => {
      const newStart = relXFromPointer(wrapper, evt) * durationMs;
      const clampedStart = Math.max(
        0,
        Math.min(endMs - MIN_STEM_CUT_MS, newStart),
      );
      previewStemCut(clampedStart, endMs);
    };

    const onUp = (upEvt: PointerEvent) => {
      const newStart = relXFromPointer(wrapper, upEvt) * durationMs;
      const clampedStart = Math.max(
        0,
        Math.min(endMs - MIN_STEM_CUT_MS, newStart),
      );
      setStemCutDraft(null);
      emitStemCut(clampedStart, endMs);
      handle.removeEventListener('pointermove', applyPreview);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', applyPreview);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  };

  const onStemCutRightHandlePointerDown = (e: PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!durationMs || durationMs <= 0 || !cutEditable) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startMs = displayStemCut.start_ms;

    const applyPreview = (evt: PointerEvent) => {
      const newEnd = relXFromPointer(wrapper, evt) * durationMs;
      const clampedEnd = Math.max(startMs + MIN_STEM_CUT_MS, Math.min(durationMs, newEnd));
      previewStemCut(startMs, clampedEnd);
    };

    const onUp = (upEvt: PointerEvent) => {
      const newEnd = relXFromPointer(wrapper, upEvt) * durationMs;
      const clampedEnd = Math.max(startMs + MIN_STEM_CUT_MS, Math.min(durationMs, newEnd));
      setStemCutDraft(null);
      emitStemCut(startMs, clampedEnd);
      handle.removeEventListener('pointermove', applyPreview);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', applyPreview);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  };

  // Drop target — lib-watercolor (Phase A/B) or lib-sfx (Stitcher).
  const dropHandlers = makeDropTarget(
    (payload: DragPayload, e: DragEvent) => {
      if (!timelineDurationMs || timelineDurationMs <= 0) return;
      const wrapper = wrapperRef.current;
      if (!wrapper) return;
      const box = wrapper.getBoundingClientRect();
      const relativeX = (e.clientX - box.left) / box.width;
      const clamped = Math.max(0, Math.min(1, relativeX));
      const offsetMs = Math.round(clamped * timelineDurationMs);
      if (payload.kind === 'lib-watercolor') {
        onWatercolorDrop?.(payload.lib_key, offsetMs);
        return;
      }
      if (payload.kind === 'lib-sfx' && onSfxDrop) {
        const defaultDur = Math.max(
          MIN_CUE_DURATION_MS,
          Math.min(3000, timelineDurationMs - offsetMs),
        );
        onSfxDrop(payload.lib_key, payload.source_path, offsetMs, defaultDur);
      }
    },
    (payload) => {
      if (payload.kind === 'lib-watercolor' && onWatercolorDrop) return true;
      if (payload.kind === 'lib-sfx' && onSfxDrop) return true;
      return false;
    },
  );

  const controlRef = useRef<WaveformPlaybackControl | null>(null);
  if (!controlRef.current) {
    controlRef.current = {
      busId: Symbol('mn-waveform-playback'),
      get isReady() {
        return isReadyRef.current;
      },
      play: () => false,
      pause: () => {},
    };
  }
  const playbackControlRef = controlRef.current;

  // Call ws.play() synchronously from the click handler stack — async/await
  // before play() loses Chrome's user-gesture window and WaveSurfer may swallow
  // AbortError without firing the 'play' event (button stays on ▶ Play).
  const startPlayback = useCallback(
    (fromStart = false): boolean => {
      const ws = wsRef.current;
      if (!ws || !isReadyRef.current) return false;
      const pane = wrapperRef.current?.closest('.mn-tab-pane-keepalive') as HTMLElement | null;
      if (pane?.hidden) return false;
      if (ws.isPlaying()) return true;

      pauseOtherWaveformPlayback(playbackControlRef);

      if (fromStart) ws.seekTo(0);
      const lv = linkedVideo?.current;
      if (lv) {
        lv.muted = true;
        lv.currentTime = ws.getCurrentTime();
      }

      pauseOtherWaveformPlayback(playbackControlRef);
      setLoadError(null);
      void ws.play()
        .then(() => {
          // WaveSurfer swallows AbortError — verify media actually started.
          requestAnimationFrame(() => {
            if (ws.isPlaying()) {
              setIsPlaying(true);
              onPlayStateChange?.(true);
            } else {
              setLoadError(
                'Playback failed — try ▶ Play again (do not drag the waveform at the same time).',
              );
            }
          });
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : String(err);
          setLoadError(`Playback failed: ${msg}`);
          setIsPlaying(false);
        });
      if (lv && lv.paused) {
        lv.muted = true;
        lv.play().catch(() => {});
      }
      return true;
    },
    [linkedVideo, playbackControlRef, onPlayStateChange],
  );

  const togglePlayback = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    if (ws.isPlaying() || isPlaying) {
      // Stop every keep-alive waveform — kills ghost dual-audio from hidden panes.
      pauseAllPhasePlayback();
      setIsPlaying(false);
      onPlayStateChange?.(false);
      return;
    }
    startPlayback(false);
  }, [startPlayback, isPlaying, onPlayStateChange]);

  playbackControlRef.play = (opts) => startPlayback(opts?.fromStart ?? false);
  playbackControlRef.pause = hardPause;

  useEffect(() => {
    const unregister = registerWaveformPlaybackControl(playbackControlRef);
    if (playbackControl) {
      playbackControl.current = playbackControlRef;
    }
    return () => {
      unregister();
      hardPause();
      if (playbackControl) {
        playbackControl.current = null;
      }
    };
  }, [playbackControl, hardPause]);

  const rootTestId = timelineTestId ?? 'waveform-timeline';

  if (!audioSrc) {
    if (onSfxDrop && fallbackDurationMs && fallbackDurationMs > 0) {
      return (
        /* eslint-disable-next-line jsx-a11y/no-static-element-interactions */
        <div
          ref={wrapperRef}
          class="mn-waveform-timeline mn-waveform-timeline--drop-only mn-drop-target mn-stitcher-slot-waveform"
          data-testid={rootTestId}
          data-loaded-duration-ms={fallbackDurationMs}
          data-cue-count={displayCues.length}
          onDragOver={dropHandlers.onDragOver}
          onDragLeave={dropHandlers.onDragLeave}
          onDrop={dropHandlers.onDrop}
        >
          <div class="mn-waveform-source-label mn-waveform-source-label--compact">
            <span class="mn-dim">
              {emptyMessage ?? 'Loading slot audio — drop SFX from Library onto this strip'}
            </span>
          </div>
          <div class="mn-waveform-canvas mn-waveform-canvas--placeholder" />
          <div class="mn-waveform-cue-overlay">
            {displayCues.map((cue) => (
              <div
                key={cue.id}
                data-testid={
                  cueTestIdPrefix
                    ? `${cueTestIdPrefix}${cue.id}`
                    : `cue-marker-${cue.id}`
                }
                data-offset-ms={cue.offset_ms}
                data-duration-ms={cue.duration_ms ?? 3000}
                class={`mn-waveform-cue-block${cueBlockClassName ? ` ${cueBlockClassName}` : ''}`}
                style={{
                  left: `${cuePctLeft(cue)}%`,
                  width: `${cuePctWidth(cue)}%`,
                }}
                onClick={(e: MouseEvent) => {
                  const target = e.target as HTMLElement;
                  if (target.closest('.mn-waveform-cue-block-handle')) return;
                  onCueClick?.(cue.id, { x: e.clientX, y: e.clientY });
                }}
                title={`${cue.watercolor_key} @ ${(cue.offset_ms / 1000).toFixed(1)}s · ${((cue.duration_ms ?? 3000) / 1000).toFixed(1)}s`}
              >
                <div
                  class="mn-waveform-cue-block-handle mn-waveform-cue-block-handle--left"
                  data-testid={`cue-handle-left-${cue.id}`}
                  title="Drag to adjust cue start time"
                  onPointerDown={(e: PointerEvent) => onLeftHandlePointerDown(e, cue)}
                />
                <div
                  class="mn-waveform-cue-block-handle mn-waveform-cue-block-handle--right"
                  data-testid={`cue-handle-right-${cue.id}`}
                  title="Drag to adjust cue end time"
                  onPointerDown={(e: PointerEvent) => onRightHandlePointerDown(e, cue)}
                />
              </div>
            ))}
          </div>
        </div>
      );
    }
    return (
      <div
        class="mn-waveform-timeline mn-waveform-empty"
        data-testid="waveform-timeline-empty"
      >
        <span class="mn-dim">
          {emptyMessage
            ?? 'No audio yet — generate a stem from the script or send for lipsync.'}
        </span>
      </div>
    );
  }

  return (
    <div
      ref={wrapperRef}
      class={`mn-waveform-timeline mn-drop-target${compact ? ' mn-waveform-timeline--compact' : ''}`}
      data-testid={rootTestId}
      data-audio-src={audioSrc}
      data-source-label={sourceLabel ?? ''}
      data-loaded-duration-ms={timelineDurationMs ?? ''}
      data-current-time-ms={Math.round(currentMs)}
      data-cue-count={displayCues.length}
      data-stem-cut-editable={cutEditable ? '1' : '0'}
      data-stem-cut-start-ms={Math.round(displayStemCut.start_ms)}
      data-stem-cut-end-ms={Math.round(displayStemCut.end_ms)}
      onDragOver={dropHandlers.onDragOver}
      onDragLeave={dropHandlers.onDragLeave}
      onDrop={dropHandlers.onDrop}
    >
      {compact ? (
        <div class="mn-waveform-source-label mn-waveform-source-label--compact">
          <span class="mn-dim">Drag SFX from Library onto this waveform</span>
          {timelineDurationMs ? (
            <span class="mn-dim">
              {' '}
              · {(timelineDurationMs / 1000).toFixed(1)}s
            </span>
          ) : null}
        </div>
      ) : (
        <div class="mn-waveform-source-label">
          <button
            type="button"
            class="mn-btn mn-btn-play"
            data-testid="waveform-play-btn"
            disabled={!isReady}
            onPointerDown={(e: PointerEvent) => e.stopPropagation()}
            onClick={togglePlayback}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <strong>Audio ({sourceLabel ?? '—'}):</strong>{' '}
          <span class="mn-dim">{sourceFilename ?? ''}</span>
          {durationMs ? (
            <span class="mn-dim">
              {' '}
              · {(currentMs / 1000).toFixed(1)}s / {(durationMs / 1000).toFixed(1)}s
            </span>
          ) : null}
        </div>
      )}
      <div ref={containerRef} class="mn-waveform-canvas" />
      <div
        class="mn-waveform-seek-layer"
        data-testid="waveform-seek-layer"
        aria-hidden="true"
      />
      <div class="mn-waveform-cue-overlay">
        {cutEditable && durationMs && durationMs > 0 ? (
          <>
            {displayStemCut.end_ms > displayStemCut.start_ms + MIN_STEM_CUT_MS ? (
              <div
                class="mn-waveform-stem-trim-block"
                data-testid="waveform-stem-cut-block"
                style={{
                  left: `${stemCutPctLeft()}%`,
                  width: `${stemCutPctWidth()}%`,
                }}
                title={`Remove: ${(displayStemCut.start_ms / 1000).toFixed(2)}s → ${(displayStemCut.end_ms / 1000).toFixed(2)}s`}
              />
            ) : null}
            <div
              class="mn-waveform-stem-trim-handle mn-waveform-stem-trim-handle--left"
              data-testid="waveform-stem-cut-handle-left"
              style={{ left: `${stemCutPctLeft()}%` }}
              title="Drag to set cut start"
              onPointerDown={onStemCutLeftHandlePointerDown}
            />
            <div
              class="mn-waveform-stem-trim-handle mn-waveform-stem-trim-handle--right"
              data-testid="waveform-stem-cut-handle-right"
              style={{
                left: `${
                  displayStemCut.end_ms > displayStemCut.start_ms + MIN_STEM_CUT_MS
                    ? stemCutPctLeft() + stemCutPctWidth()
                    : 100
                }%`,
              }}
              title="Drag to set cut end"
              onPointerDown={onStemCutRightHandlePointerDown}
            />
          </>
        ) : null}
        {displayCues.map((cue) => (
          <div
            key={cue.id}
            data-testid={
              cueTestIdPrefix
                ? `${cueTestIdPrefix}${cue.id}`
                : `cue-marker-${cue.id}`
            }
            data-offset-ms={cue.offset_ms}
            data-duration-ms={cue.duration_ms ?? 3000}
            class={`mn-waveform-cue-block${cueBlockClassName ? ` ${cueBlockClassName}` : ''}`}
            style={{
              left: `${cuePctLeft(cue)}%`,
              width: `${cuePctWidth(cue)}%`,
            }}
            onClick={(e: MouseEvent) => {
              // Only fire cueClick when clicking the block body, not a resize handle.
              const target = e.target as HTMLElement;
              if (target.closest('.mn-waveform-cue-block-handle')) return;
              onCueClick?.(cue.id, { x: e.clientX, y: e.clientY });
            }}
            title={`${cue.watercolor_key} @ ${(cue.offset_ms / 1000).toFixed(1)}s · ${((cue.duration_ms ?? 3000) / 1000).toFixed(1)}s`}
          >
            <div
              class="mn-waveform-cue-block-handle mn-waveform-cue-block-handle--left"
              data-testid={`cue-handle-left-${cue.id}`}
              title="Drag to adjust cue start time"
              onPointerDown={(e: PointerEvent) => onLeftHandlePointerDown(e, cue)}
            />
            <div
              class="mn-waveform-cue-block-handle mn-waveform-cue-block-handle--right"
              data-testid={`cue-handle-right-${cue.id}`}
              title="Drag to adjust cue end time"
              onPointerDown={(e: PointerEvent) => onRightHandlePointerDown(e, cue)}
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

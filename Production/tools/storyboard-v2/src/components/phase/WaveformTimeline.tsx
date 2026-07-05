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
//   PLAY-6  Linked-video audioprocess must not lv_play() after pause (Stitcher ▶/⏸).
//           togglePlayback calls hardPause() before pauseAllPhasePlayback().
//   SEEK-1  Drag-seek applySeek MUST use wsRef.current — never close over ws from
//           effect setup (WS remount deps can recycle instance while handlers linger).
//   SEEK-3  While paused, onSeeking must not overwrite applySeek when WS clock is
//           stale (lipsync mp4 — play→pause→drag repro on Event_1 / 5111).
//   SEEK-5  Phase A waveform must not decode stitched MP4 — stem/lipsync priority
//           only; stitched stays on preview <video> (drag flash to 0.0 repro).
//   SEEK-6  isDraggingSeekRef + capture-phase handlers + linkedVideoTimeS from
//           lastScrubMsRef — onSeeking must not flash stale WS clock to 0.
//   SEEK-7  Paused onSeeking must re-assert lastScrubMsRef (trim mode + lipsync mp4).
//   SEEK-8  displayOnly + masterVideo (Stitcher): syncFromVideo MUST honor
//           isDraggingSeekRef + lastScrubMsRef — video.currentTime at 0 fights drag.
//   DROP-CAPTURE-1  HTML5 drop on wrapper bubble misses WaveSurfer canvas child;
//           bindDropTargetCapture on wrapperRef (capture phase).
//   CUE-HANDLE-1  cue-block body pointer-events:none (SEEK-4); drag-body + handles
//           pointer-events:auto — drag-body in shouldSkipSeek for cue-move only.
//   WTA-1   Paused playhead: waveformTimeAuthority.resolvePausedPlayheadMs — never
//           let WS/video clocks at 0 clobber scrub authority on drag release.
//   CUE-RESIZE-1  cue handle drag math MUST read timelineDurationMsRef.current —
//           same stale-duration class as SEEK (ws.getDuration() can be 0).
// ─────────────────────────────────────────────────────────────────────────────
//
// Responsibilities (Phase A + Phase B — same WaveformTimeline instance per tab):
//  - Mount WaveSurfer over a container, load the audio source priority winner
//    (lipsync > mixed > stem; resolved by PhaseProducer)
//  - Expose duration via the ready event so cue markers can be positioned
//  - Click-to-seek on the waveform
//  - Render absolute-positioned cue markers from `phase_X_watercolor_cues_json`
//
// Phase C: drag-drop watercolor → cue create (DROP-CAPTURE-1); cue drag-to-reposition (CUE-MOVE-1).
//
// Cursor v8 Q1: WaveSurfer.create / destroy cycle leaves no WebAudio leaks —
// every effect that creates an instance returns a cleanup that calls .destroy().

import { useCallback, useEffect, useMemo, useRef, useState } from 'preact/hooks';
import WaveSurfer from 'wavesurfer.js';
import { bindDropTargetCapture, makeDropTarget, type DragPayload } from '../../utils/dragdrop';
import {
  pauseOtherWaveformPlayback,
  registerWaveformPlaybackControl,
  pauseAllPhasePlayback,
} from '../../utils/waveformPlaybackBus';
import { isStitchComposerPlaybackOwner } from '../../utils/stitchConstants';
import { linkedMediaSameFilename } from '../../utils/playbackVideoPolicy';
import {
  createWaveformTimeAuthority,
  timelineRelXFromClientX,
} from '../../utils/waveformTimeAuthority.ts';
import { bindWaveformSeekController } from '../../utils/waveformSeekController.ts';

/** Intentional ws.destroy() during audioSrc / shared-media transitions aborts in-flight load. */
function isIgnorableWaveformLoadError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  const msg = err instanceof Error ? err.message : String(err);
  return /abort/i.test(msg);
}

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
  sourceLabel: 'lipsync' | 'mixed' | 'stem' | 'stitched' | null;
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
  /** Authoritative slot timeline for SFX drop / cue markers (STITCH_SLOT_TIMELINE_CLOCK_V1). */
  slotTimelineDurMs?: number;
  /** Hide play controls (Stitcher per-slot strip). */
  compact?: boolean;
  /** Override empty-state copy (Stitcher: "Load video…"). */
  emptyMessage?: string;
  /** Prefix for cue block testids (Stitcher: stitcher-sfx-cue-marker-intro-). */
  cueTestIdPrefix?: string;
  /** Override root data-testid (Stitcher: stitcher-slot-waveform-intro). */
  timelineTestId?: string;
  /** WaveSurfer canvas height in px (Stitcher compact strips use 56). */
  waveformHeight?: number;
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
  /** Basename of linked preview file — auto-enables match-audio sync when = sourceFilename. */
  linkedVideoFilename?: string | null;
  /**
   * Seek-only linked video (Stitcher composer): WaveSurfer owns playback; the video
   * stays paused and currentTime follows the playhead. Avoids decode stalls on long
   * assembled slot MP4s where parallel play() freezes picture while audio runs.
   */
  linkedVideoScrubOnly?: boolean;
  /**
   * Preview video decodes the same MP4 as WaveSurfer audio — display-only video +
   * throttled seeks (PLAY-8). Also auto-enabled when linkedVideoFilename matches
   * sourceFilename (all events / phases without per-caller wiring).
   */
  linkedVideoMatchAudio?: boolean;
  /** Parent ignores linked-video play/seeked while waveform drives the element. */
  linkedVideoEventSuppressRef?: { current: boolean };
  /** Parent can call play()/pause() from Preview with Overlay (same user-gesture stack). */
  playbackControl?: { current: WaveformPlaybackControl | null };
  /** Drop/seek only — no playback bus, no ▶ (Stitcher compact grid strips). */
  playbackDisabled?: boolean;
  /** Display-only waveform — peaks visualization; master video owns audio (STITCH_UNIFIED_PLAYBACK_V1). */
  displayOnly?: boolean;
  displayPeaks?: number[];
  displayDurationS?: number;
  masterVideo?: { current: HTMLVideoElement | null };
  /** When this changes, re-bind master video listeners (video mounts after peaks). */
  masterVideoSrc?: string;
  onMasterSeek?: (ms: number) => void;
  /** Server ffmpeg remix in flight — block ▶ until mixed audio_src is loaded. */
  mixExtracting?: boolean;
}

export interface WaveformPlaybackControl {
  readonly busId: symbol;
  play: (opts?: { fromStart?: boolean }) => boolean;
  pause: () => void;
  seekToMs: (ms: number) => void;
  readonly isReady: boolean;
  readonly isPlaying: boolean;
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
    slotTimelineDurMs,
    compact,
    emptyMessage,
    cueTestIdPrefix,
    timelineTestId,
    waveformHeight,
    cueBlockClassName,
    onTimeUpdate,
    onCueRangeChange,
    onCueResize,
    onPlayStateChange,
    linkedVideo,
    linkedVideoFilename = null,
    linkedVideoScrubOnly = false,
    linkedVideoMatchAudio = false,
    linkedVideoEventSuppressRef,
    playbackControl,
    playbackDisabled,
    displayOnly = false,
    displayPeaks,
    displayDurationS,
    masterVideo,
    masterVideoSrc,
    onMasterSeek,
    mixExtracting = false,
    stemCutStartMs,
    stemCutEndMs,
    stemCutEditable,
    onStemCutChange,
    stemTrimStartMs,
    stemTrimBackMs,
    stemTrimEditable,
    onStemTrimChange,
  } = props;

  const effectiveLinkedVideoMatchAudio =
    linkedVideoMatchAudio ||
    Boolean(
      linkedVideo &&
        sourceFilename &&
        linkedVideoFilename &&
        linkedMediaSameFilename(linkedVideoFilename, sourceFilename),
    );
  const useSharedLinkedMedia = effectiveLinkedVideoMatchAudio;

  const cutStartMs = stemCutStartMs ?? stemTrimStartMs ?? 0;
  const cutEndMs = stemCutEndMs ?? stemTrimBackMs ?? 0;
  const cutEditable = stemCutEditable ?? stemTrimEditable ?? false;
  const onCutChange = onStemCutChange ?? onStemTrimChange;

  const MIN_CUE_DURATION_MS = 250;
  const MIN_STEM_CUT_MS = 250;

  const containerRef = useRef<HTMLDivElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const waveformLoadGenRef = useRef(0);
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
  const onTimeUpdateRef = useRef(onTimeUpdate);
  onTimeUpdateRef.current = onTimeUpdate;

  const timelineDurationMs = durationMs ?? slotTimelineDurMs ?? fallbackDurationMs ?? null;
  const timelineDurationMsRef = useRef(timelineDurationMs);
  timelineDurationMsRef.current = timelineDurationMs;

  const resolveTimelineDurationMs = (): number => {
    const fromRef = timelineDurationMsRef.current ?? 0;
    return fromRef > 0 ? fromRef : 0;
  };
  /** Authoritative scrub target while paused — WS getCurrentTime() lags on lipsync mp4. */
  const lastScrubMsRef = useRef<number | null>(null);
  const timeAuthorityRef = useRef(createWaveformTimeAuthority());
  /** Survives seek-effect rebind — local isDragging was lost mid-drag (flash to 0). */
  const isDraggingSeekRef = useRef<boolean>(false);
  const linkedVideoRef = useRef(linkedVideo);
  linkedVideoRef.current = linkedVideo;
  const useSharedLinkedMediaRef = useRef(useSharedLinkedMedia);
  useSharedLinkedMediaRef.current = useSharedLinkedMedia;

  const cuePctLeft = (cue: WatercolorCue): number => {
    if (!timelineDurationMs || timelineDurationMs <= 0) return 0;
    return Math.max(0, Math.min(100, (cue.offset_ms / timelineDurationMs) * 100));
  };

  const cuePctWidth = (cue: WatercolorCue): number => {
    if (!timelineDurationMs || timelineDurationMs <= 0) return 0;
    const durMs = cue.duration_ms ?? 3000;
    return Math.max(0, Math.min(100 - cuePctLeft(cue), (durMs / timelineDurationMs) * 100));
  };

  const resolvePausedPlayheadMs = useCallback((mediaTimeMs: number): number => {
    return timeAuthorityRef.current.resolvePausedPlayheadMs(
      mediaTimeMs,
      lastScrubMsRef.current,
    );
  }, []);

  const publishPlayheadMs = useCallback((ms: number) => {
    const rounded = Math.round(ms);
    setCurrentMs(rounded);
    onTimeUpdateRef.current?.(rounded);
  }, []);

  const withLinkedVideoSuppress = useCallback((fn: () => void) => {
    const ref = linkedVideoEventSuppressRef;
    if (ref) ref.current = true;
    try {
      fn();
    } finally {
      requestAnimationFrame(() => {
        if (ref) ref.current = false;
      });
    }
  }, [linkedVideoEventSuppressRef]);

  const hardPause = useCallback(() => {
    wsRef.current?.pause();
    withLinkedVideoSuppress(() => {
      linkedVideo?.current?.pause();
    });
    setIsPlaying(false);
    const pane = wrapperRef.current?.closest('.mn-tab-pane-keepalive');
    pane?.querySelectorAll('video, audio').forEach((el) => {
      if (isStitchComposerPlaybackOwner(el)) return;
      if (el instanceof HTMLMediaElement) el.pause();
    });
  }, [linkedVideo, withLinkedVideoSuppress]);

  /** Keep ▶/⏸ label aligned with WaveSurfer even if a play/pause event is dropped. */
  const syncPlayUi = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    const playing = ws.isPlaying();
    setIsPlaying(playing);
    onPlayStateChange?.(playing);
  }, [onPlayStateChange]);

  // WaveSurfer mount — audioSrc or displayOnly peaks.
  useEffect(() => {
    if (displayOnly) {
      if (!displayPeaks?.length || !displayDurationS || !containerRef.current) return;
      const ta = timeAuthorityRef.current;
      const activeMs = lastScrubMsRef.current ?? currentMs;
      if (activeMs > 0) ta.scrubToMs(activeMs);
      ta.preserveAcrossRemount();
      const restoredMs = ta.restoreAfterRemount();
      setLoadError(null);
      const slotClockMs = slotTimelineDurMs ?? fallbackDurationMs ?? 0;
      const authoritativeMs = slotClockMs > 0
        ? slotClockMs
        : displayDurationS * 1000;
      setDurationMs(authoritativeMs);
      setCurrentMs(restoredMs);
      if (restoredMs > 0) lastScrubMsRef.current = restoredMs;
      setIsPlaying(false);
      setIsReady(false);

      const ws = WaveSurfer.create({
        container: containerRef.current,
        waveColor: '#7d6b5d',
        progressColor: '#3a2e26',
        cursorColor: '#c33',
        height: waveformHeight ?? 80,
        normalize: true,
        barWidth: 2,
        barGap: 1,
        interact: false,
      });
      wsRef.current = ws;
      const onReadyHandler = () => {
        const slotClockMs = slotTimelineDurMs ?? fallbackDurationMs ?? 0;
        const authoritativeMs = slotClockMs > 0
          ? slotClockMs
          : (ws.getDuration() || displayDurationS) * 1000;
        setDurationMs(authoritativeMs);
        setIsReady(true);
        isReadyRef.current = true;
        const playheadMs = lastScrubMsRef.current ?? timeAuthorityRef.current.getPlayheadMs();
        if (playheadMs > 0 && authoritativeMs > 0) {
          setCurrentMs(playheadMs);
          ws.seekTo(Math.min(1, playheadMs / authoritativeMs));
        }
      };
      ws.on('ready', onReadyHandler);
      const loadGen = ++waveformLoadGenRef.current;
      void ws.load('', [displayPeaks], displayDurationS).catch((err: unknown) => {
        if (waveformLoadGenRef.current !== loadGen) return;
        if (isIgnorableWaveformLoadError(err)) return;
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      });
      return () => {
        isReadyRef.current = false;
        try {
          ws.destroy();
        } catch {
          // non-fatal
        }
        if (wsRef.current === ws) wsRef.current = null;
      };
    }

    if (playbackDisabled || !audioSrc || !containerRef.current) return;
    const ta = timeAuthorityRef.current;
    const activeMs = lastScrubMsRef.current ?? currentMs;
    if (activeMs > 0) ta.scrubToMs(activeMs);
    ta.preserveAcrossRemount();
    const restoredMs = ta.restoreAfterRemount();
    setLoadError(null);
    setDurationMs(null);
    setCurrentMs(restoredMs);
    if (restoredMs > 0) lastScrubMsRef.current = restoredMs;
    setIsPlaying(false);
    setIsReady(false);

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#7d6b5d',
      progressColor: '#3a2e26',
      cursorColor: '#c33',
      height: waveformHeight ?? 80,
      normalize: true,
      barWidth: 2,
      barGap: 1,
      ...(useSharedLinkedMedia && linkedVideo?.current
        ? { media: linkedVideo.current }
        : {}),
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
      // Never resume after decode — prevents ghost audio on tab load / refresh.
      try {
        ws.pause();
      } catch {
        // ignore
      }
      onReady?.(d);
    };
    const msFromWsClock = (wave: WaveSurfer): number | null => {
      const t = wave.getCurrentTime();
      const wsDurS = wave.getDuration();
      if (wsDurS > 0) {
        if (t <= 0) return null;
        return t * 1000;
      }
      const durMs = timelineDurationMsRef.current ?? 0;
      if (durMs <= 0) return null;
      if (t > 0 && t <= 1) return t * durMs;
      if (t > 1) return t * 1000;
      return null;
    };
    const onAudioProcess = () => {
      if (stopPlaybackIfHiddenPane()) return;
      if (!ws.isPlaying()) return;
      const ms = msFromWsClock(ws);
      if (ms == null) return;
      setCurrentMs(ms);
      onTimeUpdate?.(ms);
      syncPlayUi();
    };
    // Paused scrub: applySeek + lastScrubMsRef own the label. WS 'seeking' /
    // getCurrentTime() often reports 0 on mp4/lipsync until decode catches up —
    // accepting that clock zeros the red playhead on drag release.
    const onSeeking = () => {
      if (isDraggingSeekRef.current || timeAuthorityRef.current.isDraggingSeek()) return;
      if (!ws.isPlaying()) {
        const wsMs = msFromWsClock(ws) ?? 0;
        const ms = resolvePausedPlayheadMs(wsMs);
        lastScrubMsRef.current = ms > 0 ? ms : null;
        publishPlayheadMs(ms);
        return;
      }
      const ms = msFromWsClock(ws);
      if (ms == null) return;
      lastScrubMsRef.current = null;
      timeAuthorityRef.current.scrubToMs(ms);
      publishPlayheadMs(ms);
    };
    const linkedVideoTimeS = (): number => {
      if (!ws.isPlaying()) {
        const wsMs = (msFromWsClock(ws) ?? 0);
        return resolvePausedPlayheadMs(wsMs) / 1000;
      }
      const t = ws.getCurrentTime();
      return t > 0 ? t : 0;
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
      lastScrubMsRef.current = null;
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
    const suppressLinkedVideoEvents = (fn: () => void) => {
      const ref = linkedVideoEventSuppressRef;
      if (ref) ref.current = true;
      try {
        fn();
      } finally {
        requestAnimationFrame(() => {
          if (ref) ref.current = false;
        });
      }
    };
    const seekLinkedVideoTo = (lv: HTMLVideoElement, t: number) => {
      suppressLinkedVideoEvents(() => {
        lv.muted = true;
        if (!lv.paused) lv.pause();
        if (Math.abs(lv.currentTime - t) > 0.02) {
          lv.currentTime = t;
        }
      });
    };
    const lv_play = (lv: HTMLVideoElement) => {
      suppressLinkedVideoEvents(() => {
        lv.muted = true;
        lv.play().catch(() => {
          if (lv.paused) {
            requestAnimationFrame(() => {
              suppressLinkedVideoEvents(() => {
                lv.muted = true;
                lv.play().catch(() => {});
              });
            });
          }
        });
      });
    };

    if (!useSharedLinkedMedia) {
    if (linkedVideoScrubOnly) {
      ws.on('play', () => {
        if (stopPlaybackIfHiddenPane()) return;
        const lv = linkedVideo?.current;
        if (!lv) return;
        seekLinkedVideoTo(lv, ws.getCurrentTime());
      });
      ws.on('seeking', () => {
        const lv = linkedVideo?.current;
        if (!lv) return;
        seekLinkedVideoTo(lv, linkedVideoTimeS());
      });
      ws.on('audioprocess', () => {
        if (stopPlaybackIfHiddenPane()) return;
        const lv = linkedVideo?.current;
        if (!lv || !ws.isPlaying()) return;
        seekLinkedVideoTo(lv, ws.getCurrentTime());
      });
    } else {
      ws.on('play', () => {
        if (stopPlaybackIfHiddenPane()) return;
        const lv = linkedVideo?.current;
        if (!lv) return;
        lv_play(lv);
      });
      ws.on('seeking', () => {
        const lv = linkedVideo?.current;
        if (!lv) return;
        const t = linkedVideoTimeS();
        suppressLinkedVideoEvents(() => {
          lv.currentTime = t;
          if (!ws.isPlaying()) return;
          lv.muted = true;
          lv.play().catch(() => {});
        });
      });
      let linkedVideoStallTicks = 0;
      ws.on('audioprocess', () => {
        if (stopPlaybackIfHiddenPane()) return;
        const lv = linkedVideo?.current;
        if (!lv || !ws.isPlaying()) return;
        const t = ws.getCurrentTime();
        // Recover stalled/ended linked video while WaveSurfer still plays (PLAY-6: only
        // when ws.isPlaying() — user ⏸ Pause stops ws first, so no restart loop).
        if (lv.paused || lv.ended) {
          linkedVideoStallTicks += 1;
          if (linkedVideoStallTicks >= 6) {
            linkedVideoStallTicks = 0;
            hardPause();
            return;
          }
          suppressLinkedVideoEvents(() => {
            lv.currentTime = t;
            lv.muted = true;
            lv.play().catch(() => {});
          });
          return;
        }
        linkedVideoStallTicks = 0;
        const drift = Math.abs(lv.currentTime - t);
        if (drift > 0.3) {
          suppressLinkedVideoEvents(() => {
            lv.currentTime = t;
          });
        }
      });
    }
    }
    ws.on('pause', () => {
      if (useSharedLinkedMedia) return;
      suppressLinkedVideoEvents(() => {
        linkedVideo?.current?.pause();
      });
    });
    ws.on('finish', () => {
      if (useSharedLinkedMedia) return;
      const lv = linkedVideo?.current;
      if (!lv) return;
      suppressLinkedVideoEvents(() => {
        lv.pause();
        lv.currentTime = 0;
      });
    });

    const sharedLv = useSharedLinkedMedia ? linkedVideo?.current : null;
    if (sharedLv) sharedLv.muted = false;
    const loadGen = ++waveformLoadGenRef.current;
    if (!useSharedLinkedMedia || sharedLv) {
      void ws.load(audioSrc).catch((err: unknown) => {
        if (waveformLoadGenRef.current !== loadGen) return;
        if (isIgnorableWaveformLoadError(err)) return;
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      });
    }

    return () => {
      isReadyRef.current = false;
      waveformLoadGenRef.current += 1;
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
  }, [audioSrc, syncPlayUi, waveformHeight, linkedVideoScrubOnly, useSharedLinkedMedia, displayOnly, displayPeaks, displayDurationS, slotTimelineDurMs, fallbackDurationMs]);

  // VQ-P1: bind lipsync <video> when it mounts after WaveformTimeline (sibling DOM order).
  useEffect(() => {
    if (!useSharedLinkedMedia || !audioSrc) return;
    let cancelled = false;
    const bind = () => {
      if (cancelled) return;
      const ws = wsRef.current;
      const lv = linkedVideo?.current;
      if (!ws || !lv) {
        requestAnimationFrame(bind);
        return;
      }
      lv.muted = false;
      ws.setMediaElement(lv);
      const bindGen = waveformLoadGenRef.current;
      void ws.load(audioSrc).catch((err: unknown) => {
        if (cancelled || waveformLoadGenRef.current !== bindGen) return;
        if (isIgnorableWaveformLoadError(err)) return;
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      });
    };
    bind();
    return () => {
      cancelled = true;
    };
  }, [useSharedLinkedMedia, audioSrc, linkedVideoFilename]);

  useEffect(() => {
    if (!displayOnly) return;
    let rafId = 0;
    let boundVideo: HTMLVideoElement | null = null;

    const resolveDurMs = (): number => {
      const slotClockMs = slotTimelineDurMs ?? fallbackDurationMs ?? 0;
      return durationMs ?? (slotClockMs > 0 ? slotClockMs : (displayDurationS ? displayDurationS * 1000 : 0));
    };

    const applyPlayheadMs = (ms: number) => {
      setCurrentMs(ms);
      const ws = wsRef.current;
      const durMs = resolveDurMs();
      if (ws && durMs > 0) {
        ws.seekTo(Math.min(1, ms / durMs));
      }
      onTimeUpdate?.(ms);
    };

    // SEEK-8 — Stitcher displayOnly: master <video> must not clobber paused drag authority.
    const syncFromVideo = (video: HTMLVideoElement) => {
      if (isDraggingSeekRef.current || timeAuthorityRef.current.isDraggingSeek()) return;
      if (!video.paused && !video.ended) {
        lastScrubMsRef.current = null;
        applyPlayheadMs(Math.max(0, video.currentTime * 1000));
        setIsPlaying(true);
        return;
      }
      const mediaMs = Math.max(0, video.currentTime * 1000);
      const ms = resolvePausedPlayheadMs(mediaMs);
      if (ms > 0) lastScrubMsRef.current = ms;
      applyPlayheadMs(ms);
      setIsPlaying(false);
    };

    const tick = () => {
      const video = masterVideo?.current;
      if (!video || video.paused || video.ended) {
        rafId = 0;
        return;
      }
      syncFromVideo(video);
      rafId = requestAnimationFrame(tick);
    };

    const onVideoPlay = () => {
      const video = masterVideo?.current;
      if (!video) return;
      syncFromVideo(video);
      if (!rafId) rafId = requestAnimationFrame(tick);
    };
    const onVideoPause = () => {
      cancelAnimationFrame(rafId);
      rafId = 0;
      const video = masterVideo?.current;
      if (video) syncFromVideo(video);
    };
    const onVideoTimeUpdate = () => {
      const video = masterVideo?.current;
      if (video) syncFromVideo(video);
    };
    const onVideoSeeked = () => {
      const video = masterVideo?.current;
      if (video) syncFromVideo(video);
    };

    const detach = () => {
      cancelAnimationFrame(rafId);
      rafId = 0;
      if (!boundVideo) return;
      boundVideo.removeEventListener('play', onVideoPlay);
      boundVideo.removeEventListener('pause', onVideoPause);
      boundVideo.removeEventListener('timeupdate', onVideoTimeUpdate);
      boundVideo.removeEventListener('seeked', onVideoSeeked);
      boundVideo = null;
    };

    const video = masterVideo?.current;
    if (video) {
      boundVideo = video;
      video.addEventListener('play', onVideoPlay);
      video.addEventListener('pause', onVideoPause);
      video.addEventListener('timeupdate', onVideoTimeUpdate);
      video.addEventListener('seeked', onVideoSeeked);
      syncFromVideo(video);
      if (!video.paused && !video.ended) {
        rafId = requestAnimationFrame(tick);
      }
    }

    return detach;
  }, [displayOnly, masterVideo, displayDurationS, durationMs, slotTimelineDurMs, fallbackDurationMs, onTimeUpdate, resolvePausedPlayheadMs]);

  // Shared lipsync <video> + WaveSurfer media: drive overlay cue timing from the
  // video clock (audioprocess alone can lag when WS uses the same element).
  useEffect(() => {
    if (!useSharedLinkedMedia || displayOnly) return;
    let rafId = 0;
    let boundVideo: HTMLVideoElement | null = null;

    // SEEK-3 / WTA-1: while paused, linked lipsync <video> often reports currentTime 0
    // until decode catches up — must not clobber applySeek / lastScrubMsRef authority.
    const syncFromVideo = (video: HTMLVideoElement) => {
      if (isDraggingSeekRef.current || timeAuthorityRef.current.isDraggingSeek()) return;
      if (!video.paused && !video.ended) {
        const ms = Math.max(0, video.currentTime * 1000);
        lastScrubMsRef.current = null;
        timeAuthorityRef.current.scrubToMs(ms);
        publishPlayheadMs(ms);
        return;
      }
      const mediaMs = Math.max(0, video.currentTime * 1000);
      const ms = resolvePausedPlayheadMs(mediaMs);
      if (ms > 0) lastScrubMsRef.current = ms;
      publishPlayheadMs(ms);
    };

    const tick = () => {
      const video = linkedVideo?.current;
      if (!video || video.paused || video.ended) {
        rafId = 0;
        return;
      }
      syncFromVideo(video);
      rafId = requestAnimationFrame(tick);
    };

    const onVideoPlay = () => {
      const video = linkedVideo?.current;
      if (!video) return;
      syncFromVideo(video);
      if (!rafId) rafId = requestAnimationFrame(tick);
    };
    const onVideoPause = () => {
      cancelAnimationFrame(rafId);
      rafId = 0;
      const video = linkedVideo?.current;
      if (video) syncFromVideo(video);
    };
    const onVideoTimeUpdate = () => {
      const video = linkedVideo?.current;
      if (video) syncFromVideo(video);
    };

    const attach = () => {
      const video = linkedVideo?.current;
      if (!video) {
        requestAnimationFrame(attach);
        return;
      }
      boundVideo = video;
      video.addEventListener('play', onVideoPlay);
      video.addEventListener('pause', onVideoPause);
      video.addEventListener('timeupdate', onVideoTimeUpdate);
      syncFromVideo(video);
      if (!video.paused && !video.ended) {
        rafId = requestAnimationFrame(tick);
      }
    };
    attach();

    return () => {
      cancelAnimationFrame(rafId);
      rafId = 0;
      if (!boundVideo) return;
      boundVideo.removeEventListener('play', onVideoPlay);
      boundVideo.removeEventListener('pause', onVideoPause);
      boundVideo.removeEventListener('timeupdate', onVideoTimeUpdate);
      boundVideo = null;
    };
  }, [useSharedLinkedMedia, displayOnly, linkedVideoFilename, audioSrc, resolvePausedPlayheadMs, publishPlayheadMs]);

  // Keep-alive: pause when this phase tab is hidden so background WaveSurfer
  // instances do not block playback on the visible tab (Chrome autoplay policy).
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const pane = wrapper.closest('.mn-tab-pane-keepalive') as HTMLElement | null;
    if (!pane) return;

    const pauseIfHiddenAndStopMedia = () => {
      // STITCH_KEEPALIVE_PAUSE_WHEN_HIDDEN_V1 — never sweep pane media while tab is visible.
      // Mounting a sibling waveform (peaks ~7s) must not pause the Stitcher composer.
      if (!pane.hidden) return;
      hardPause();
      pane.querySelectorAll('video, audio').forEach((el) => {
        if (isStitchComposerPlaybackOwner(el)) return;
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
  // applySeek MUST use wsRef.current (not a closed-over ws) — WS mount effect deps
  // expanded in STITCH_UNIFIED_PLAYBACK_V1 can remount WaveSurfer while isReady stays
  // true; stale ws.seekTo() is a silent no-op while ▶ Play still works via wsRef.
  useEffect(() => {
    const wrapper = wrapperRef.current;
    const canSeek = displayOnly
      ? Boolean(displayPeaks?.length && displayDurationS)
      : Boolean(audioSrc);
    if (!wrapper || !isReady || !canSeek) return;

    return bindWaveformSeekController({
      wrapper,
      wsRef,
      timeAuthority: timeAuthorityRef.current,
      isDraggingSeekRef,
      lastScrubMsRef,
      linkedVideoRef,
      useSharedLinkedMediaRef,
      onWaveformClickRef,
      withLinkedVideoSuppress,
      publishPlayheadMs,
      resolveDurationMs: () => {
        if (displayOnly) {
          return (
            slotTimelineDurMs ??
            fallbackDurationMs ??
            (displayDurationS ?? 0) * 1000
          );
        }
        return timelineDurationMsRef.current ?? 0;
      },
      displayOnly,
      onMasterSeek,
    });
  }, [
    audioSrc,
    isReady,
    displayOnly,
    displayPeaks,
    slotTimelineDurMs,
    fallbackDurationMs,
    displayDurationS,
    onMasterSeek,
    withLinkedVideoSuppress,
    publishPlayheadMs,
  ]);

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

  const relXFromPointer = (wrapper: HTMLDivElement, evt: PointerEvent): number =>
    timelineRelXFromClientX(wrapper.getBoundingClientRect(), evt.clientX);

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
    const durMs = resolveTimelineDurationMs();
    if (durMs <= 0) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startOffset = cue.offset_ms;

    const applyPreview = (evt: PointerEvent) => {
      const endMs = relXFromPointer(wrapper, evt) * durMs;
      const clampedEnd = Math.max(startOffset + MIN_CUE_DURATION_MS, Math.min(durMs, endMs));
      previewCueRange(cue.id, startOffset, clampedEnd - startOffset);
    };

    const onUp = (upEvt: PointerEvent) => {
      const endMs = relXFromPointer(wrapper, upEvt) * durMs;
      const clampedEnd = Math.max(startOffset + MIN_CUE_DURATION_MS, Math.min(durMs, endMs));
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
    const durMs = resolveTimelineDurationMs();
    if (durMs <= 0) return;
    const handle = e.currentTarget as HTMLDivElement;
    handle.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startDuration = cue.duration_ms ?? 3000;
    const endMs = cue.offset_ms + startDuration;

    const applyPreview = (evt: PointerEvent) => {
      const newOffset = relXFromPointer(wrapper, evt) * durMs;
      const clampedOffset = Math.max(
        0,
        Math.min(endMs - MIN_CUE_DURATION_MS, newOffset),
      );
      previewCueRange(cue.id, clampedOffset, endMs - clampedOffset);
    };

    const onUp = (upEvt: PointerEvent) => {
      const newOffset = relXFromPointer(wrapper, upEvt) * durMs;
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

  // Body drag: move entire cue along timeline — offset shifts, duration fixed (CUE-MOVE-1).
  const onCueBodyPointerDown = (e: PointerEvent, cue: WatercolorCue) => {
    const target = e.target as HTMLElement;
    if (target.closest('.mn-waveform-cue-block-handle')) return;
    e.stopPropagation();
    e.preventDefault();
    const durMs = resolveTimelineDurationMs();
    if (durMs <= 0) return;
    const duration = cue.duration_ms ?? MIN_CUE_DURATION_MS;
    const block = e.currentTarget as HTMLDivElement;
    block.setPointerCapture(e.pointerId);
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startPointerX = e.clientX;
    const startOffset = cue.offset_ms;
    const boxWidth = wrapper.getBoundingClientRect().width;
    let moved = false;

    const applyPreview = (evt: PointerEvent) => {
      if (Math.abs(evt.clientX - startPointerX) > 3) moved = true;
      const deltaMs = ((evt.clientX - startPointerX) / boxWidth) * durMs;
      const newOffset = Math.max(
        0,
        Math.min(durMs - duration, Math.round(startOffset + deltaMs)),
      );
      previewCueRange(cue.id, newOffset, duration);
    };

    const onUp = (upEvt: PointerEvent) => {
      if (!moved) {
        if (target.closest('.mn-waveform-cue-popover-hit')) {
          onCueClick?.(cue.id, { x: upEvt.clientX, y: upEvt.clientY });
        }
        block.removeEventListener('pointermove', applyPreview);
        block.removeEventListener('pointerup', onUp);
        block.removeEventListener('pointercancel', onUp);
        return;
      }
      const deltaMs = ((upEvt.clientX - startPointerX) / boxWidth) * durMs;
      const newOffset = Math.max(
        0,
        Math.min(durMs - duration, Math.round(startOffset + deltaMs)),
      );
      setDragDraft(null);
      emitCueRange(cue.id, newOffset, duration);
      block.removeEventListener('pointermove', applyPreview);
      block.removeEventListener('pointerup', onUp);
      block.removeEventListener('pointercancel', onUp);
    };

    block.addEventListener('pointermove', applyPreview);
    block.addEventListener('pointerup', onUp);
    block.addEventListener('pointercancel', onUp);
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
  const onWatercolorDropRef = useRef(onWatercolorDrop);
  onWatercolorDropRef.current = onWatercolorDrop;
  const onSfxDropRef = useRef(onSfxDrop);
  onSfxDropRef.current = onSfxDrop;

  const dropHandlers = useMemo(
    () => makeDropTarget(
      (payload: DragPayload, e: DragEvent) => {
        const durMs = resolveTimelineDurationMs();
        if (durMs <= 0) return;
        const wrapper = wrapperRef.current;
        if (!wrapper) return;
        const relativeX = timelineRelXFromClientX(wrapper.getBoundingClientRect(), e.clientX);
        const offsetMs = Math.round(relativeX * durMs);
        if (payload.kind === 'lib-watercolor') {
          onWatercolorDropRef.current?.(payload.lib_key, offsetMs);
          return;
        }
        if (payload.kind === 'lib-sfx' && onSfxDropRef.current) {
          const defaultDur = Math.max(
            MIN_CUE_DURATION_MS,
            Math.min(3000, durMs - offsetMs),
          );
          onSfxDropRef.current(payload.lib_key, payload.source_path, offsetMs, defaultDur);
        }
      },
      (payload) => {
        if (payload.kind === 'lib-watercolor' && onWatercolorDropRef.current) return true;
        if (payload.kind === 'lib-sfx' && onSfxDropRef.current) return true;
        return false;
      },
    ),
    [],
  );

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    return bindDropTargetCapture(wrapper, dropHandlers);
  }, [dropHandlers, audioSrc, isReady, displayOnly, fallbackDurationMs, displayPeaks, displayDurationS]);

  const controlRef = useRef<WaveformPlaybackControl | null>(null);
  if (!controlRef.current) {
    controlRef.current = {
      busId: Symbol('mn-waveform-playback'),
      get isReady() {
        return isReadyRef.current;
      },
      get isPlaying() {
        return wsRef.current?.isPlaying() ?? false;
      },
      play: () => false,
      pause: () => {},
      seekToMs: () => {},
    };
  }
  const playbackControlRef = controlRef.current;

  // Call ws.play() synchronously from the click handler stack — async/await
  // before play() loses Chrome's user-gesture window and WaveSurfer may swallow
  // AbortError without firing the 'play' event (button stays on ▶ Play).
  const startPlayback = useCallback(
    (fromStart = false): boolean => {
      if (mixExtracting) return false;
      const ws = wsRef.current;
      if (!ws || !isReadyRef.current) return false;
      const pane = wrapperRef.current?.closest('.mn-tab-pane-keepalive') as HTMLElement | null;
      if (pane?.hidden) return false;
      if (ws.isPlaying()) return true;

      pauseOtherWaveformPlayback(playbackControlRef);

      if (fromStart) ws.seekTo(0);
      lastScrubMsRef.current = null;
      timeAuthorityRef.current.onPlaybackStart();
      const lv = linkedVideo?.current;
      if (lv && !useSharedLinkedMedia) {
        withLinkedVideoSuppress(() => {
          lv.muted = true;
          lv.currentTime = ws.getCurrentTime();
          if (linkedVideoScrubOnly && !lv.paused) lv.pause();
        });
      }

      pauseOtherWaveformPlayback(playbackControlRef);
      setLoadError(null);
      void ws.play()
        .then(() => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              if (ws.isPlaying()) {
                setIsPlaying(true);
                onPlayStateChange?.(true);
              } else if (!linkedVideoEventSuppressRef?.current) {
                setLoadError(
                  'Playback failed — try ▶ Play again (do not drag the waveform at the same time).',
                );
              }
            });
          });
        })
        .catch((err: unknown) => {
          if (isIgnorableWaveformLoadError(err)) return;
          const msg = err instanceof Error ? err.message : String(err);
          setLoadError(`Playback failed: ${msg}`);
          setIsPlaying(false);
        });
      if (lv && lv.paused && !linkedVideoScrubOnly && !useSharedLinkedMedia) {
        withLinkedVideoSuppress(() => {
          lv.muted = true;
          lv.play().catch(() => {});
        });
      }
      return true;
    },
    [linkedVideo, linkedVideoScrubOnly, useSharedLinkedMedia, linkedVideoEventSuppressRef, playbackControlRef, onPlayStateChange, withLinkedVideoSuppress, mixExtracting],
  );

  const togglePlayback = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    if (ws.isPlaying() || isPlaying) {
      // Local hardPause first — bus + linked-video sync must not restart after pause.
      hardPause();
      pauseAllPhasePlayback();
      syncPlayUi();
      return;
    }
    startPlayback(false);
  }, [startPlayback, isPlaying, hardPause, syncPlayUi]);

  playbackControlRef.play = (opts) => startPlayback(opts?.fromStart ?? false);
  playbackControlRef.pause = hardPause;
  playbackControlRef.seekToMs = (ms: number) => {
    const ws = wsRef.current;
    const durMs = durationMs ?? fallbackDurationMs;
    if (!ws || !durMs || durMs <= 0) return;
    const clamped = Math.max(0, Math.min(durMs, ms));
    lastScrubMsRef.current = clamped;
    ws.seekTo(clamped / durMs);
    setCurrentMs(clamped);
    if (displayOnly) {
      onMasterSeek?.(clamped);
      return;
    }
    const lv = linkedVideo?.current;
    if (lv && !useSharedLinkedMedia) {
      withLinkedVideoSuppress(() => {
        lv.muted = true;
        try {
          lv.currentTime = clamped / 1000;
        } catch {
          // ignore seek on unloaded media
        }
        if (ws.isPlaying()) {
          lv.play().catch(() => {});
        }
      });
    }
  };

  useEffect(() => {
    if (playbackDisabled || displayOnly) {
      return () => {
        if (!displayOnly) hardPause();
      };
    }
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
  }, [playbackControl, hardPause, playbackDisabled, displayOnly]);

  const rootTestId = timelineTestId ?? 'waveform-timeline';
  const hasDisplayWaveform = displayOnly && Boolean(displayPeaks?.length && displayDurationS);

  if (!audioSrc && !hasDisplayWaveform) {
    if (onSfxDrop && fallbackDurationMs && fallbackDurationMs > 0) {
      return (
        /* eslint-disable-next-line jsx-a11y/no-static-element-interactions */
        <div
          ref={wrapperRef}
          class="mn-waveform-timeline mn-waveform-timeline--drop-only mn-drop-target mn-stitcher-slot-waveform"
          data-testid={rootTestId}
          data-loaded-duration-ms={fallbackDurationMs}
          data-cue-count={displayCues.length}
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
                title={`${cue.watercolor_key} @ ${(cue.offset_ms / 1000).toFixed(1)}s · ${((cue.duration_ms ?? 3000) / 1000).toFixed(1)}s`}
              >
                <div
                  class="mn-waveform-cue-drag-body"
                  data-testid={`cue-drag-body-${cue.id}`}
                  title="Drag to move cue"
                  onPointerDown={(e: PointerEvent) => onCueBodyPointerDown(e, cue)}
                />
                <div
                  class="mn-waveform-cue-popover-hit"
                  data-testid={`cue-popover-hit-${cue.id}`}
                  title="Click to edit cue"
                  onClick={(e: MouseEvent) => {
                    e.stopPropagation();
                    onCueClick?.(cue.id, { x: e.clientX, y: e.clientY });
                  }}
                />
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
      data-phase-waveform-pause-v1="PHASE_WAVEFORM_PAUSE_V1"
      data-waveform-cue-handle-v1="WAVEFORM_CUE_HANDLE_V1"
      data-waveform-cue-move-v1="CUE-MOVE-1"
      data-mix-extracting={mixExtracting ? 'true' : 'false'}
      {...(displayOnly ? { 'data-display-only-waveform': 'STITCH_UNIFIED_PLAYBACK_V1' } : {})}
      {...(displayOnly && masterVideoSrc ? { 'data-stitch-composer-master-video-sync': 'STITCH_COMPOSER_MASTER_VIDEO_SYNC_V1' } : {})}
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
          {!displayOnly ? (
            <button
              type="button"
              class="mn-btn mn-btn-play"
              data-testid="waveform-play-btn"
              disabled={!isReady || mixExtracting}
              onPointerDown={(e: PointerEvent) => e.stopPropagation()}
              onClick={togglePlayback}
              title={
                mixExtracting
                  ? 'Remixing audio…'
                  : isPlaying
                    ? 'Pause'
                    : 'Play'
              }
            >
              {isPlaying ? '⏸ Pause' : '▶ Play'}
            </button>
          ) : (
            <span class="mn-dim" data-testid="waveform-display-only-label">
              Waveform (display) — video owns audio
            </span>
          )}
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
            title={`${cue.watercolor_key} @ ${(cue.offset_ms / 1000).toFixed(1)}s · ${((cue.duration_ms ?? 3000) / 1000).toFixed(1)}s`}
          >
            <div
              class="mn-waveform-cue-drag-body"
              data-testid={`cue-drag-body-${cue.id}`}
              title="Drag to move cue"
              onPointerDown={(e: PointerEvent) => onCueBodyPointerDown(e, cue)}
            />
            <div
              class="mn-waveform-cue-popover-hit"
              data-testid={`cue-popover-hit-${cue.id}`}
              title="Click to edit cue"
              onClick={(e: MouseEvent) => {
                e.stopPropagation();
                onCueClick?.(cue.id, { x: e.clientX, y: e.clientY });
              }}
            />
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

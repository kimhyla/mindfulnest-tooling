// StitcherSlotWaveform — per-slot SFX timeline (WaveformTimeline parity).
// STITCHER_SFX_TIMELINE_V1 — WaveSurfer strip + lib-sfx drop + resize handles.
// STITCH_WAVEFORM_PEAKS_STABLE_ON_SFX_V1 — displayOnly speech peaks keyed on videoPath only.

import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { activeScope, activeMilestoneId, activeProjectType } from '../state/scope';
import { stitchJobSessionKey } from '../state/producerSessionKeys';
import { pathappPatch } from '../api/client';
import { STITCH_SLOT_AUDIO_MIX_V1 } from '../utils/stitchConstants';
import { stitchSlotSpeechPeaksSig } from '../utils/stitchSlotMuxAudioSig';
import { resolveServerMediaUrl } from '../utils/stitchSlotVideo';
import {
  commitWaveformSession,
  getStitchSlotSession,
  isWaveformSessionFresh,
  type StitchSessionSlotKey,
} from '../utils/stitchSlotSessionCache';
import {
  fetchPeaksFromArtifactUrl,
  STITCH_SLOT_MEDIA_ARTIFACTS_V1,
} from '../utils/stitchJobMediaHydrate';
import {
  singleFlightAudioExtract,
  stitchMediaFlightKey,
} from '../utils/stitchMediaBuildFlight';
import {
  WaveformTimeline,
  type WatercolorCue,
  type WaveformPlaybackControl,
} from './phase/WaveformTimeline';
import type { SfxCue } from './phase/SfxCuePopover';

export interface StitcherSlotWaveformProps {
  slotKey: string;
  videoPath?: string;
  /** Preset id from ambient dropdown — mixed into composer waveform extract. */
  ambientBed?: string;
  videoDurMs: number;
  cues: ReadonlyArray<SfxCue>;
  onSfxDrop: (
    lib_key: string,
    source_path: string,
    offset_ms: number,
    duration_ms: number,
  ) => void;
  onCueRangeChange: (cue_id: string, offset_ms: number, duration_ms: number) => void;
  onCueClick: (cue_id: string, anchor: { x: number; y: number }) => void;
  /** Muted slot video — WaveSurfer owns audio; red playhead tracks video time. */
  linkedVideo?: { current: HTMLVideoElement | null };
  linkedVideoFilename?: string | null;
  /** Seek-only sync for heavy slot MP4s (Stitcher slot composer). */
  linkedVideoScrubOnly?: boolean;
  linkedVideoMatchAudio?: boolean;
  linkedVideoEventSuppressRef?: { current: boolean };
  playbackControl?: { current: WaveformPlaybackControl | null };
  /** Compact strip in slot grid; full controls in slot composer. */
  compact?: boolean;
  /** Grid strips: SFX drop/seek only — no ▶ or playback bus. */
  playbackDisabled?: boolean;
  /** Composer: peaks-only waveform; muxed video owns audio (STITCH_UNIFIED_PLAYBACK_V1). */
  displayOnly?: boolean;
  /** Server-persisted peaks URL — hydrate without audio_extract POST. */
  artifactPeaksUrl?: string;
  mixSig?: string;
  masterVideo?: { current: HTMLVideoElement | null };
  masterVideoSrc?: string;
  onMasterSeek?: (ms: number) => void;
}

function sfxToTimelineCues(cues: ReadonlyArray<SfxCue>): WatercolorCue[] {
  return cues.map((cue) => ({
    id: cue.id,
    watercolor_key: cue.name ?? cue.source_path.split('/').pop() ?? cue.id,
    offset_ms: cue.offset_ms,
    duration_ms: cue.duration_ms ?? 3000,
  }));
}

export function StitcherSlotWaveform({
  slotKey,
  videoPath,
  ambientBed,
  videoDurMs,
  cues,
  onSfxDrop,
  onCueRangeChange,
  onCueClick,
  linkedVideo,
  linkedVideoFilename = null,
  linkedVideoScrubOnly = false,
  linkedVideoMatchAudio = false,
  linkedVideoEventSuppressRef,
  playbackControl,
  compact = true,
  playbackDisabled = false,
  displayOnly = false,
  artifactPeaksUrl,
  masterVideo,
  masterVideoSrc,
  onMasterSeek,
}: StitcherSlotWaveformProps) {
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [displayPeaks, setDisplayPeaks] = useState<number[] | null>(null);
  const [displayDurationS, setDisplayDurationS] = useState<number | null>(null);
  const [extractDurMs, setExtractDurMs] = useState<number | null>(null);
  const [timelineDurMs, setTimelineDurMs] = useState<number>(videoDurMs);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [mixExtracting, setMixExtracting] = useState(false);
  const mixRequestRef = useRef(0);

  useEffect(() => {
    setTimelineDurMs(videoDurMs);
  }, [videoDurMs]);

  useEffect(() => {
    if (!videoPath) {
      setAudioSrc(null);
      setDisplayPeaks(null);
      setDisplayDurationS(null);
      setExtractDurMs(null);
      setExtractError(null);
      setMixExtracting(false);
      return;
    }
    const eventId = activeScope.value.event_id;
    const sessionKey = stitchJobSessionKey(
      eventId,
      activeProjectType.value,
      activeMilestoneId.value,
    );
    const sessionSlot = slotKey as StitchSessionSlotKey;
    const peaksSig = stitchSlotSpeechPeaksSig(videoPath);
    if (isWaveformSessionFresh(sessionKey, sessionSlot, videoPath)) {
      const wf = getStitchSlotSession(sessionKey, sessionSlot)!.waveform!;
      setDisplayPeaks(wf.peaks);
      setDisplayDurationS(wf.durationS);
      setExtractDurMs(Math.round(wf.durationS * 1000));
      setTimelineDurMs(Math.round(wf.durationS * 1000));
      setMixExtracting(false);
      setExtractError(null);
      setAudioSrc(null);
      return;
    }
    let cancelled = false;
    const requestId = ++mixRequestRef.current;
    setMixExtracting(true);
    setAudioSrc(null);
    setDisplayPeaks(null);
    setDisplayDurationS(null);
    setExtractError(null);
    (async () => {
      if (artifactPeaksUrl) {
        const cached = await fetchPeaksFromArtifactUrl(artifactPeaksUrl);
        if (cancelled || requestId !== mixRequestRef.current) return;
        if (cached?.peaks.length) {
          setDisplayPeaks(cached.peaks);
          setDisplayDurationS(cached.durationS || videoDurMs / 1000);
          setExtractDurMs(Math.round((cached.durationS || videoDurMs / 1000) * 1000));
          setTimelineDurMs(videoDurMs > 0 ? videoDurMs : Math.round((cached.durationS || videoDurMs / 1000) * 1000));
          commitWaveformSession(sessionKey, sessionSlot, {
            peaks: cached.peaks,
            durationS: cached.durationS || videoDurMs / 1000,
            mixSig: peaksSig,
          });
          setMixExtracting(false);
          return;
        }
      }

      const body: Record<string, string | number | ReadonlyArray<SfxCue>> = displayOnly
        ? { video_path: videoPath }
        : { video_path: videoPath, sfx_cues: cues };
      const flightKey = stitchMediaFlightKey(
        sessionKey,
        slotKey,
        peaksSig,
      );
      const res = await singleFlightAudioExtract(flightKey, () => pathappPatch<{
        audio_url?: string;
        peaks_url?: string;
        peaks_duration_s?: number;
        duration_ms?: number;
        video_dur_ms?: number;
        ambient_mixed?: boolean;
        sfx_mixed?: boolean;
      }>(
        activeScope.value,
        'stitch_audio_extract',
        body,
      ));
      if (cancelled || requestId !== mixRequestRef.current) return;
      if (res.ok && (res.data?.audio_url || res.data?.peaks_url)) {
        const videoDur =
          typeof res.data.video_dur_ms === 'number' && res.data.video_dur_ms > 0
            ? res.data.video_dur_ms
            : videoDurMs;
        const extractDur =
          typeof res.data.duration_ms === 'number' && res.data.duration_ms > 0
            ? res.data.duration_ms
            : videoDur;
        if (
          !displayOnly
          && videoDur > 0
          && extractDur > 0
          && (
            Math.abs(videoDur - extractDur) > 2000
            || Math.abs(videoDur - extractDur) > videoDur * 0.015
          )
        ) {
          setAudioSrc(null);
          setDisplayPeaks(null);
          setDisplayDurationS(null);
          setExtractDurMs(null);
          setExtractError(
            `audio duration ${(extractDur / 1000).toFixed(1)}s ≠ video ${(videoDur / 1000).toFixed(1)}s — refresh or re-export slot`,
          );
          setMixExtracting(false);
          return;
        }
        if (displayOnly && res.data.peaks_url) {
          try {
            const peaksRes = await fetch(resolveServerMediaUrl(res.data.peaks_url));
            if (!peaksRes.ok) throw new Error(`peaks HTTP ${peaksRes.status}`);
            const peaksJson = await peaksRes.json() as {
              data?: number[];
              duration_s?: number;
            };
            setDisplayPeaks(Array.isArray(peaksJson.data) ? peaksJson.data : []);
            const durS =
              typeof peaksJson.duration_s === 'number' && peaksJson.duration_s > 0
                ? peaksJson.duration_s
                : (typeof res.data.peaks_duration_s === 'number' ? res.data.peaks_duration_s : videoDur / 1000);
            setDisplayDurationS(durS);
            commitWaveformSession(sessionKey, sessionSlot, {
              peaks: Array.isArray(peaksJson.data) ? peaksJson.data : [],
              durationS: durS,
              mixSig: peaksSig,
            });
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setDisplayPeaks(null);
            setDisplayDurationS(null);
            setExtractError(`peaks load failed (${msg})`);
          }
        } else if (res.data.audio_url) {
          setAudioSrc(resolveServerMediaUrl(res.data.audio_url));
        }
        const dur = videoDur > 0 ? videoDur : extractDur;
        setExtractDurMs(dur);
        setTimelineDurMs(videoDurMs > 0 ? videoDurMs : dur);
        setMixExtracting(false);
      } else {
        setAudioSrc(null);
        setDisplayPeaks(null);
        setDisplayDurationS(null);
        setExtractDurMs(null);
        setExtractError(res.error ?? `audio extract HTTP ${res.status}`);
        setMixExtracting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // displayOnly: cue markers update via timelineCues — never re-extract speech peaks on SFX edit.
  }, displayOnly
    ? [playbackDisabled, videoPath, videoDurMs, activeScope.value.event_id, displayOnly, artifactPeaksUrl]
    : [playbackDisabled, videoPath, cues, videoDurMs, activeScope.value.event_id, displayOnly, artifactPeaksUrl]);

  const timelineCues = useMemo(() => sfxToTimelineCues(cues), [cues]);
  const fallbackDurationMs = extractDurMs ?? timelineDurMs;
  const cueTestIdPrefix = `stitcher-sfx-cue-marker-${slotKey}-`;
  const waveformHeight = compact ? 56 : 72;
  const sourceLabel: 'lipsync' | 'mixed' | 'stem' | null = 'lipsync';
  const sourceFilename = videoPath?.split('/').pop() ?? slotKey;

  const emptyMessage = playbackDisabled
    ? undefined
    : !videoPath
      ? '— no slot video yet — drop SFX to place cue (timing uses default duration)'
      : mixExtracting
        ? (displayOnly ? 'Building speech waveform…' : 'Extracting slot speech for waveform…')
        : extractError
          ? `Waveform unavailable (${extractError}) — drop SFX still works`
          : (displayOnly ? (displayPeaks?.length ? undefined : 'Loading waveform peaks…') : audioSrc ? undefined : 'Extracting slot audio for waveform…');

  const hasWaveform = displayOnly
    ? Boolean(displayPeaks?.length)
    : Boolean(audioSrc);

  return (
    <div
      class="mn-stitcher-slot-waveform-wrap"
      data-stitcher-sfx-timeline="STITCHER_SFX_TIMELINE_V1"
      data-slot-key={slotKey}
      data-video-dur-ms={videoDurMs}
      data-cue-count={cues.length}
      data-has-waveform={hasWaveform ? 'true' : 'false'}
      data-ambient-bed={ambientBed ?? ''}
      data-stitcher-ambient-waveform="STITCHER_AMBIENT_WAVEFORM_V1"
      data-stitch-ambient-volume-v1="STITCH_AMBIENT_BED_VOLUME_V1"
      data-stitch-slot-audio-mix={STITCH_SLOT_AUDIO_MIX_V1}
      data-stitch-slot-video-dur-v1="STITCH_SLOT_VIDEO_DUR_V1"
      data-stitch-unified-playback={displayOnly ? 'STITCH_UNIFIED_PLAYBACK_V1' : ''}
      data-stitch-waveform-peaks-stable-on-sfx={displayOnly ? 'STITCH_WAVEFORM_PEAKS_STABLE_ON_SFX_V1' : ''}
      data-stitch-slot-media-artifacts={STITCH_SLOT_MEDIA_ARTIFACTS_V1}
      data-mix-extracting={mixExtracting ? 'true' : 'false'}
    >
      <WaveformTimeline
        timelineTestId={`stitcher-slot-waveform-${slotKey}`}
        audioSrc={displayOnly ? null : audioSrc}
        sourceLabel={sourceLabel}
        sourceFilename={sourceFilename}
        cues={timelineCues}
        compact={compact}
        waveformHeight={waveformHeight}
        fallbackDurationMs={fallbackDurationMs}
        slotTimelineDurMs={videoDurMs > 0 ? videoDurMs : fallbackDurationMs}
        {...(emptyMessage !== undefined ? { emptyMessage } : {})}
        {...(displayOnly && displayPeaks?.length ? {
          displayOnly: true,
          displayPeaks,
          displayDurationS: displayDurationS ?? fallbackDurationMs / 1000,
        } : {})}
        {...(displayOnly && masterVideo ? { masterVideo } : {})}
        {...(displayOnly && masterVideoSrc ? { masterVideoSrc } : {})}
        {...(displayOnly && onMasterSeek ? { onMasterSeek } : {})}
        {...(!displayOnly && linkedVideo ? { linkedVideo } : {})}
        {...(!displayOnly && linkedVideoFilename ? { linkedVideoFilename } : {})}
        {...(!displayOnly && linkedVideoScrubOnly ? { linkedVideoScrubOnly: true } : {})}
        {...(!displayOnly && linkedVideoMatchAudio ? { linkedVideoMatchAudio: true } : {})}
        {...(!displayOnly && linkedVideoEventSuppressRef ? { linkedVideoEventSuppressRef } : {})}
        {...(!displayOnly && playbackControl ? { playbackControl } : {})}
        playbackDisabled={playbackDisabled || mixExtracting || displayOnly}
        mixExtracting={mixExtracting}
        cueTestIdPrefix={cueTestIdPrefix}
        cueBlockClassName="mn-stitcher-sfx-cue-block"
        onSfxDrop={onSfxDrop}
        onCueRangeChange={onCueRangeChange}
        onCueClick={onCueClick}
      />
    </div>
  );
}

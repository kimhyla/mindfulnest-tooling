// StitcherSlotWaveform — per-slot SFX timeline (WaveformTimeline parity).
// STITCHER_SFX_TIMELINE_V1 — WaveSurfer strip + lib-sfx drop + resize handles.

import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { activeScope } from '../state/scope';
import { pathappPatch } from '../api/client';
import { STITCH_AMBIENT_BED_VOLUME, STITCH_SLOT_AUDIO_MIX_V1 } from '../utils/stitchConstants';
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
  linkedVideoEventSuppressRef?: { current: boolean };
  playbackControl?: { current: WaveformPlaybackControl | null };
  /** Compact strip in slot grid; full controls in slot composer. */
  compact?: boolean;
  /** Grid strips: SFX drop/seek only — no ▶ or playback bus. */
  playbackDisabled?: boolean;
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
  linkedVideoEventSuppressRef,
  playbackControl,
  compact = true,
  playbackDisabled = false,
}: StitcherSlotWaveformProps) {
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [extractDurMs, setExtractDurMs] = useState<number | null>(null);
  const [timelineDurMs, setTimelineDurMs] = useState<number>(videoDurMs);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [mixExtracting, setMixExtracting] = useState(false);
  const mixRequestRef = useRef(0);

  useEffect(() => {
    setTimelineDurMs(videoDurMs);
  }, [videoDurMs]);

  useEffect(() => {
    if (playbackDisabled || !videoPath) {
      setAudioSrc(null);
      setExtractDurMs(null);
      setExtractError(null);
      setMixExtracting(false);
      return;
    }
    let cancelled = false;
    const requestId = ++mixRequestRef.current;
    setMixExtracting(true);
    setAudioSrc(null);
    setExtractError(null);
    (async () => {
      const body: Record<string, string | number | ReadonlyArray<SfxCue>> = {
        video_path: videoPath,
        ambient_volume: STITCH_AMBIENT_BED_VOLUME,
        sfx_cues: cues,
      };
      if (ambientBed) body['ambient_bed'] = ambientBed;
      const res = await pathappPatch<{
        audio_url?: string;
        duration_ms?: number;
        video_dur_ms?: number;
        ambient_mixed?: boolean;
        sfx_mixed?: boolean;
      }>(
        activeScope.value,
        'stitch_audio_extract',
        body,
      );
      if (cancelled || requestId !== mixRequestRef.current) return;
      if (res.ok && res.data?.audio_url) {
        const videoDur =
          typeof res.data.video_dur_ms === 'number' && res.data.video_dur_ms > 0
            ? res.data.video_dur_ms
            : videoDurMs;
        const extractDur =
          typeof res.data.duration_ms === 'number' && res.data.duration_ms > 0
            ? res.data.duration_ms
            : videoDur;
        if (
          videoDur > 0
          && extractDur > 0
          && Math.abs(videoDur - extractDur) > Math.max(4000, videoDur * 0.03)
        ) {
          setAudioSrc(null);
          setExtractDurMs(null);
          setExtractError(
            `audio duration ${(extractDur / 1000).toFixed(1)}s ≠ video ${(videoDur / 1000).toFixed(1)}s — refresh or re-export slot`,
          );
          setMixExtracting(false);
          return;
        }
        setAudioSrc(res.data.audio_url);
        const dur = videoDur > 0 ? videoDur : extractDur;
        setExtractDurMs(dur);
        setTimelineDurMs(dur);
        setMixExtracting(false);
      } else {
        setAudioSrc(null);
        setExtractDurMs(null);
        setExtractError(res.error ?? `audio extract HTTP ${res.status}`);
        setMixExtracting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [playbackDisabled, videoPath, ambientBed, cues, videoDurMs, activeScope.value.event_id]);

  const timelineCues = useMemo(() => sfxToTimelineCues(cues), [cues]);
  const fallbackDurationMs = extractDurMs ?? timelineDurMs;
  const cueTestIdPrefix = `stitcher-sfx-cue-marker-${slotKey}-`;
  const waveformHeight = compact ? 56 : 72;
  const sourceLabel: 'lipsync' | 'mixed' | 'stem' | null = ambientBed ? 'mixed' : null;
  const sourceFilename = ambientBed
    ? `${videoPath?.split('/').pop() ?? slotKey} + ${ambientBed}`
    : (videoPath?.split('/').pop() ?? slotKey);

  const emptyMessage = playbackDisabled
    ? undefined
    : !videoPath
      ? '— no slot video yet — drop SFX to place cue (timing uses default duration)'
      : mixExtracting
        ? 'Remixing slot audio (speech + ambient bed + SFX)…'
        : extractError
          ? `Waveform unavailable (${extractError}) — drop SFX still works`
          : audioSrc
            ? undefined
            : 'Extracting slot audio for waveform…';

  return (
    <div
      class="mn-stitcher-slot-waveform-wrap"
      data-stitcher-sfx-timeline="STITCHER_SFX_TIMELINE_V1"
      data-slot-key={slotKey}
      data-video-dur-ms={videoDurMs}
      data-cue-count={cues.length}
      data-has-waveform={audioSrc ? 'true' : 'false'}
      data-ambient-bed={ambientBed ?? ''}
      data-stitcher-ambient-waveform="STITCHER_AMBIENT_WAVEFORM_V1"
      data-stitch-ambient-volume-v1="STITCH_AMBIENT_BED_VOLUME_V1"
      data-stitch-slot-audio-mix={STITCH_SLOT_AUDIO_MIX_V1}
      data-stitch-slot-video-dur-v1="STITCH_SLOT_VIDEO_DUR_V1"
      data-mix-extracting={mixExtracting ? 'true' : 'false'}
    >
      <WaveformTimeline
        timelineTestId={`stitcher-slot-waveform-${slotKey}`}
        audioSrc={audioSrc}
        sourceLabel={sourceLabel}
        sourceFilename={sourceFilename}
        cues={timelineCues}
        compact={compact}
        waveformHeight={waveformHeight}
        fallbackDurationMs={fallbackDurationMs}
        {...(emptyMessage !== undefined ? { emptyMessage } : {})}
        {...(linkedVideo ? { linkedVideo } : {})}
        {...(linkedVideoEventSuppressRef ? { linkedVideoEventSuppressRef } : {})}
        {...(playbackControl ? { playbackControl } : {})}
        playbackDisabled={playbackDisabled || mixExtracting}
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

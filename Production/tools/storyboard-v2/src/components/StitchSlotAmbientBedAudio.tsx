/**
 * FF-042 ambient preview — synced <audio> bed (not Web Audio loop).
 * Stops with Stop audio / tab change via .mn-stitcher-pane audio pause bus.
 */

import { useEffect, useRef } from 'preact/hooks';

import { resolveServerMediaUrl } from '../utils/stitchSlotVideo';

export interface StitchSlotAmbientBedAudioProps {
  video: HTMLVideoElement | null;
  jobName: string;
  slotKey: string;
  ambientBed?: string;
  ambientVolume?: number;
}

export function StitchSlotAmbientBedAudio({
  video,
  jobName,
  slotKey,
  ambientBed,
  ambientVolume = 0.15,
}: StitchSlotAmbientBedAudioProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bed = (ambientBed ?? '').trim();

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !bed || !jobName) return;
    const url = resolveServerMediaUrl(
      `/api/stitch_editor/slot_ambient_loop?job_name=${encodeURIComponent(jobName)}&slot_key=${encodeURIComponent(slotKey)}`,
    );
    audio.src = url;
    audio.load();
    // Server slot_ambient_loop already applies STITCH_AMBIENT_BED_VOLUME (0.15) in ffmpeg.
    audio.volume = 1;
  }, [bed, jobName, slotKey, ambientVolume]);

  useEffect(() => {
    const v = video;
    const a = audioRef.current;
    if (!v || !a || !bed) return;

    const syncTime = () => {
      if (!Number.isFinite(a.duration) || a.duration <= 0) return;
      a.currentTime = v.currentTime % a.duration;
    };

    const onPlay = () => {
      syncTime();
      void a.play().catch(() => {
        /* autoplay policy — user must interact with composer controls */
      });
    };

    const onPause = () => {
      a.pause();
    };

    const onSeeked = () => {
      syncTime();
      if (!v.paused) {
        void a.play().catch(() => {});
      }
    };

    const onTimeUpdate = () => {
      if (v.paused) {
        a.pause();
        return;
      }
      syncTime();
    };

    v.addEventListener('play', onPlay);
    v.addEventListener('pause', onPause);
    v.addEventListener('seeked', onSeeked);
    v.addEventListener('timeupdate', onTimeUpdate);
    return () => {
      v.removeEventListener('play', onPlay);
      v.removeEventListener('pause', onPause);
      v.removeEventListener('seeked', onSeeked);
      v.removeEventListener('timeupdate', onTimeUpdate);
      a.pause();
    };
  }, [video, bed]);

  if (!bed || !jobName) return null;

  return (
    <audio
      ref={audioRef}
      loop
      preload="auto"
      class="mn-stitcher-ambient-bed-audio"
      data-stitch-ambient-bed="STITCH_DRY_AUTHORITY_CLIENT_MIX_V1"
      data-testid={`stitcher-ambient-bed-${slotKey}`}
    />
  );
}

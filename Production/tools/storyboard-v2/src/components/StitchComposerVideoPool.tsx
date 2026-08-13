/**
 * STITCH_COMPOSER_VIDEO_POOL_V1 — four persistent slot videos for instant phase switch.
 */

import { useEffect, useImperativeHandle, useRef } from 'preact/hooks';
import type { Ref } from 'preact';

import { PLAYBACK_VIDEO_ANTI_BANDING_CLASS } from '../utils/playbackVideoPolicy';
import { STITCH_COMPOSER_PLAYBACK_OWNER_V1 } from '../utils/stitchConstants';
import type { StitchSessionSlotKey } from '../utils/stitchSlotSessionCache';

export const STITCH_COMPOSER_VIDEO_POOL_V1 = 'STITCH_COMPOSER_VIDEO_POOL_V1';

const POOL_SLOTS: StitchSessionSlotKey[] = ['intro', 'phase_a', 'phase_b', 'resolution', 'standalone'];

export interface StitchComposerVideoPoolHandle {
  getVideo(slot: StitchSessionSlotKey): HTMLVideoElement | null;
  getActiveVideo(): HTMLVideoElement | null;
  pauseAllExcept(slot: StitchSessionSlotKey | null): void;
}

interface StitchComposerVideoPoolProps {
  activeSlot: StitchSessionSlotKey;
  slotUrls: Partial<Record<StitchSessionSlotKey, string>>;
  poolRef: Ref<StitchComposerVideoPoolHandle | null>;
  onSlotCanPlay?: (slot: StitchSessionSlotKey, url: string) => void;
  onSlotError?: (slot: StitchSessionSlotKey) => void;
}

export function StitchComposerVideoPool({
  activeSlot,
  slotUrls,
  poolRef,
  onSlotCanPlay,
  onSlotError,
}: StitchComposerVideoPoolProps) {
  const videoRefs = useRef<Partial<Record<StitchSessionSlotKey, HTMLVideoElement | null>>>({});
  const boundSrcRef = useRef<Partial<Record<StitchSessionSlotKey, string>>>({});

  useImperativeHandle(poolRef, () => ({
    getVideo: (slot) => videoRefs.current[slot] ?? null,
    getActiveVideo: () => videoRefs.current[activeSlot] ?? null,
    pauseAllExcept: (slot) => {
      for (const key of POOL_SLOTS) {
        if (key === slot) continue;
        const video = videoRefs.current[key];
        if (video) video.pause();
      }
    },
  }));

  useEffect(() => {
    for (const slot of POOL_SLOTS) {
      const url = slotUrls[slot];
      const video = videoRefs.current[slot];
      if (!video) continue;
      if (!url) {
        if (boundSrcRef.current[slot]) {
          video.pause();
          video.removeAttribute('src');
          video.load();
          delete boundSrcRef.current[slot];
        }
        continue;
      }
      if (boundSrcRef.current[slot] === url) continue;
      boundSrcRef.current[slot] = url;
      video.src = url;
      video.load();
    }
  }, [slotUrls]);

  useEffect(() => {
    for (const slot of POOL_SLOTS) {
      const video = videoRefs.current[slot];
      if (!video) continue;
      if (slot !== activeSlot) {
        video.pause();
      }
    }
  }, [activeSlot]);

  return (
    <div
      class="mn-stitcher-composer-video-pool"
      data-stitch-composer-video-pool={STITCH_COMPOSER_VIDEO_POOL_V1}
      data-testid="stitcher-composer-video-pool"
    >
      {POOL_SLOTS.map((slot) => {
        const url = slotUrls[slot];
        if (!url) return null;
        const isActive = slot === activeSlot;
        return (
          <video
            // STITCH_COMPOSER_MASTER_VIDEO_SYNC_V1 — stable element per slot.
            // key={slot:url} remounted on hot-serve URL swap and left the
            // displayOnly waveform listening to a dead <video> (Resolution-only
            // playhead lag after Send / dry hot bind).
            key={slot}
            ref={(el) => {
              videoRefs.current[slot] = el;
            }}
            preload="auto"
            controls={isActive}
            class={`mn-stitcher-composer-video ${PLAYBACK_VIDEO_ANTI_BANDING_CLASS}${
              isActive ? ' is-pool-active' : ' is-pool-hidden'
            }`}
            data-testid={isActive ? 'stitcher-composer-video' : `stitcher-composer-video-${slot}`}
            data-stitch-slot={slot}
            data-stitch-composer-playback-owner={STITCH_COMPOSER_PLAYBACK_OWNER_V1}
            aria-label={`Slot preview video (${slot})`}
            onCanPlay={() => onSlotCanPlay?.(slot, url)}
            onLoadedData={() => onSlotCanPlay?.(slot, url)}
            onError={() => onSlotError?.(slot)}
          />
        );
      })}
    </div>
  );
}

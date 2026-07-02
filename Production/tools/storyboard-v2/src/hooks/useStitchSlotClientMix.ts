import { useEffect, useRef } from 'preact/hooks';

import {
  StitchSlotAudioMixEngine,
  type StitchClientMixJobContext,
  type StitchClientMixSlotInput,
} from '../audio/StitchSlotAudioMixEngine';
import {
  stitchSlotLiveGeometrySig,
  stitchSlotRequiresClientPreviewMix,
  STITCH_DRY_AUTHORITY_CLIENT_MIX_V1,
} from '../utils/stitchSlotMuxAudioSig';

export function useStitchSlotClientMix(
  video: HTMLVideoElement | null,
  slot: StitchClientMixSlotInput | null | undefined,
  jobCtx: StitchClientMixJobContext | null,
): void {
  const engineRef = useRef<StitchSlotAudioMixEngine | null>(null);
  const sigRef = useRef('');

  useEffect(() => {
    const needsMix = stitchSlotRequiresClientPreviewMix(slot);
    if (!video || !slot || !jobCtx || !needsMix) {
      engineRef.current?.detach();
      engineRef.current = null;
      sigRef.current = '';
      return;
    }

    const sig = stitchSlotLiveGeometrySig(slot);
    if (sigRef.current === sig && engineRef.current) {
      return;
    }

    sigRef.current = sig;
    const engine = engineRef.current ?? new StitchSlotAudioMixEngine();
    engineRef.current = engine;

    let cancelled = false;
    void (async () => {
      try {
        if (engineRef.current !== engine) return;
        await engine.attach(video, slot, jobCtx);
        if (cancelled) engine.detach();
      } catch (err) {
        console.warn('[stitch-client-mix] attach failed', err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [video, slot, jobCtx, slot ? stitchSlotLiveGeometrySig(slot) : '']);

  useEffect(() => () => {
    engineRef.current?.detach();
    engineRef.current = null;
  }, []);
}

export { STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 };

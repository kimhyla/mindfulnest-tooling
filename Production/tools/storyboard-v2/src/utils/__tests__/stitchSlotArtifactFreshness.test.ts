import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { hydrateAllSlotMediaFromJob } from '../stitchJobMediaHydrate.ts';
import {
  commitMuxSession,
  getStitchSlotSession,
  isMuxSessionFresh,
  readCachedStitcherPreviewLs,
  stitchSlotServerArtifactReady,
  writeCachedStitcherPreviewLs,
} from '../stitchSlotSessionCache.ts';

describe('stitch slot artifact freshness (STITCH_SLOT_MEDIA_ARTIFACTS_V1)', () => {
  it('isMuxSessionFresh is false when ambient artifact cleared but session cache remains', () => {
    const eventId = 'Event_3';
    const slot = 'phase_b' as const;
    const slotData = {
      video_path: 'Production/Event_3/phase_b_preview.mp4',
      ambient_bed: 'pretty option2',
      ambient_volume: 0.15,
      sfx_cues: [],
    };
    const staleUrl = 'http://localhost:5113/api/stitch_editor/slot_mix_file/deadbeef';

    commitMuxSession(eventId, slot, {
      previewUrl: staleUrl,
      videoPath: slotData.video_path,
      audioSig: 'ambient#sig',
    });
    writeCachedStitcherPreviewLs(eventId, slot, {
      video_path: slotData.video_path,
      preview_url: staleUrl,
      audio_sig: 'ambient#sig',
    });

    assert.equal(stitchSlotServerArtifactReady(slotData), false);
    assert.equal(isMuxSessionFresh(eventId, slot, slotData), false);
    assert.equal(getStitchSlotSession(eventId, slot)?.muxPreviewUrl, staleUrl);
  });

  it('hydrateAllSlotMediaFromJob purges stale session when ambient mix missing', () => {
    const eventId = 'Event_3';
    const slot = 'phase_b' as const;
    const slotData = {
      video_path: 'Production/Event_3/phase_b_preview.mp4',
      ambient_bed: 'pretty option2',
      ambient_volume: 0.15,
      sfx_cues: [],
    };
    const staleUrl = 'http://localhost:5113/api/stitch_editor/slot_mix_file/cafebabe';

    commitMuxSession(eventId, slot, {
      previewUrl: staleUrl,
      videoPath: slotData.video_path,
      audioSig: 'ambient#sig',
    });
    writeCachedStitcherPreviewLs(eventId, slot, {
      video_path: slotData.video_path,
      preview_url: staleUrl,
      audio_sig: 'ambient#sig',
    });

    const hydrated = hydrateAllSlotMediaFromJob(eventId, { [slot]: slotData });

    assert.deepEqual(hydrated.slotsNeedingAmbientMix, [slot]);
    assert.equal(hydrated.previewUrls[slot], undefined);
    assert.equal(getStitchSlotSession(eventId, slot), undefined);
    assert.equal(readCachedStitcherPreviewLs(eventId, slot), null);
  });
});

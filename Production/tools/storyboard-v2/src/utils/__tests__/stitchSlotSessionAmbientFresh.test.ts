import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  commitMuxSession,
  isMuxSessionFresh,
  stitchSlotSessionExpectedSig,
} from '../stitchSlotSessionCache.ts';
import { stitchSlotLiveAmbientSig } from '../stitchSlotMuxAudioSig.ts';

describe('stitchSlotSessionCache ambient freshness', () => {
  it('isMuxSessionFresh matches ambient sig committed at hydrate', () => {
    const eventId = 'Event_2';
    const slot = 'phase_a' as const;
    const slotData = {
      video_path: 'Production/Event_2/phase_a_preview.mp4',
      ambient_bed: 'pretty option2',
      ambient_volume: 0.15,
      sfx_cues: [],
    };
    const ambientSig = stitchSlotLiveAmbientSig(slotData);
    assert.notEqual(ambientSig, stitchSlotSessionExpectedSig({
      ...slotData,
      sfx_cues: [{ id: 'x', offset_ms: 0, duration_ms: 1000 }],
    }));

    commitMuxSession(eventId, slot, {
      previewUrl: 'http://localhost:5112/api/stitch_editor/slot_mix_file/abc',
      videoPath: slotData.video_path,
      audioSig: ambientSig,
    });

    assert.equal(isMuxSessionFresh(eventId, slot, slotData), true);
  });
});

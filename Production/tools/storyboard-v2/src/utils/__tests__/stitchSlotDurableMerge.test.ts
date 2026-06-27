import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  mergeStitchJobSlotsClientPatch,
  mergeStitchSlotClientPatch,
} from '../stitchSlotDurableMerge.ts';

describe('STITCH_SAVE_SLOT_DURABLE_MERGE_V1', () => {
  it('SFX-only client patch keeps video_path from prev slot (repro class)', () => {
    const prev = {
      video_path: 'Production/Milestones/m1/assembled/x.mp4',
      video_dur_ms: 94100,
      ambient_bed: 'Intro video ambient bed',
      sfx_cues: [],
    };
    const incoming = {
      sfx_cues: [{ id: 'c1', source_path: 'sfx/a.mp3', offset_ms: 0, duration_ms: 1000 }],
    };
    const merged = mergeStitchSlotClientPatch(prev, incoming);
    assert.equal(merged.video_path, prev.video_path);
    assert.equal(merged.video_dur_ms, 94100);
    assert.equal(merged.ambient_bed, 'Intro video ambient bed');
    assert.equal(merged.sfx_cues?.length, 1);
  });

  it('mergeStitchJobSlotsClientPatch applies per slot', () => {
    const merged = mergeStitchJobSlotsClientPatch(
      {
        standalone: {
          video_path: 'Production/Milestones/m1/assembled/x.mp4',
          video_dur_ms: 94100,
        },
      },
      {
        standalone: {
          sfx_cues: [{ id: 'c1' }],
        },
      },
    );
    assert.match(merged.standalone.video_path ?? '', /x\.mp4$/);
  });

  it('post-save refresh keeps local sfx_cues over stale server offsets', () => {
    const server = {
      standalone: {
        video_path: 'Production/Milestones/m1/assembled/x.mp4',
        video_dur_ms: 94100,
        sfx_cues: [{ id: 'c1', offset_ms: 0, duration_ms: 3000 }],
      },
    };
    const local = {
      standalone: {
        sfx_cues: [{ id: 'c1', offset_ms: 81000, duration_ms: 2500 }],
      },
    };
    const merged = mergeStitchJobSlotsClientPatch(server, local);
    assert.equal(merged.standalone.sfx_cues?.[0]?.offset_ms, 81000);
    assert.equal(merged.standalone.sfx_cues?.[0]?.duration_ms, 2500);
    assert.match(merged.standalone.video_path ?? '', /x\.mp4$/);
  });

  it('server refresh omitting sfx_cues preserves prev cues', () => {
    const merged = mergeStitchSlotClientPatch(
      {
        video_path: 'Production/Milestones/m1/assembled/x.mp4',
        sfx_cues: [{ id: 'c1', offset_ms: 1000 }],
      },
      {
        video_path: 'Production/Milestones/m1/assembled/x.mp4',
        ambient_bed: 'Intro video ambient bed',
      },
    );
    assert.equal(merged.sfx_cues?.length, 1);
  });
});

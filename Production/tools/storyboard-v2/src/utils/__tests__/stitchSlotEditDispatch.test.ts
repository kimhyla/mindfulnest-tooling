import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  EDIT_KIND_SFX_GEOMETRY,
  EDIT_KIND_AMBIENT_GEOMETRY,
  inferStitchEditKind,
  STITCH_SLOT_EDIT_DISPATCH_V1,
} from '../stitchSlotEditDispatch.ts';

describe('STITCH_SLOT_EDIT_DISPATCH_V1', () => {
  it('infers sfx_geometry when only cues change', () => {
    const prev = {
      standalone: {
        video_path: 'Production/Milestones/m1/x.mp4',
        ambient_bed: 'bed',
        sfx_cues: [],
      },
    };
    const next = {
      standalone: {
        video_path: 'Production/Milestones/m1/x.mp4',
        ambient_bed: 'bed',
        sfx_cues: [{ id: 'c1', offset_ms: 0, duration_ms: 3000, source_path: '/a.mp3' }],
      },
    };
    assert.equal(inferStitchEditKind(prev, next), EDIT_KIND_SFX_GEOMETRY);
  });

  it('infers ambient_geometry when bed changes', () => {
    const prev = {
      standalone: {
        video_path: 'Production/Milestones/m1/x.mp4',
        ambient_bed: 'bed_a',
        sfx_cues: [],
      },
    };
    const next = {
      standalone: {
        video_path: 'Production/Milestones/m1/x.mp4',
        ambient_bed: 'bed_b',
        sfx_cues: [],
      },
    };
    assert.equal(inferStitchEditKind(prev, next), EDIT_KIND_AMBIENT_GEOMETRY);
  });

  it('exports dispatch token', () => {
    assert.equal(STITCH_SLOT_EDIT_DISPATCH_V1, 'STITCH_SLOT_EDIT_DISPATCH_V1');
  });
});

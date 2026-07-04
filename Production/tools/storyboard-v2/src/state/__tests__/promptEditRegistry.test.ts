import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { applyO3GalleryFieldsFromPoll } from '../promptEditRegistry.ts';

describe('applyO3GalleryFieldsFromPoll — still stitch approve', () => {
  it('merges kling_o3_still_stitch_approved so nav checkmark updates without refresh', () => {
    const local = {
      beat_id: 'bg_arc1_event5_pre_beat_06',
      pipeline: 'still_insert',
      kling_o3_video_path: '/clips/0402_trimmed.mp4',
      kling_o3_status: 'still_rendered',
      kling_o3_still_stitch_approved: false,
    };
    const patch = {
      beat_id: 'bg_arc1_event5_pre_beat_06',
      pipeline: 'still_insert',
      kling_o3_video_path: '/clips/0402_trimmed.mp4',
      kling_o3_status: 'still_rendered',
      kling_o3_still_stitch_approved: true,
      kling_o3_still_stitch_approved_at: '2026-07-04T03:05:43Z',
    };
    const merged = applyO3GalleryFieldsFromPoll(local, patch);
    assert.equal(merged.kling_o3_still_stitch_approved, true);
    assert.equal(merged.kling_o3_still_stitch_approved_at, '2026-07-04T03:05:43Z');
  });
});

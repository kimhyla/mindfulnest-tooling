import { describe, expect, it } from 'vitest';
import { klingBeatNeedsClipApprove } from '../bgKlingClipApprove';

describe('bgKlingClipApprove', () => {
  it('flags O3 beat with clip and draft status', () => {
    expect(klingBeatNeedsClipApprove({
      pipeline: 'kling_o3_omni',
      kling_o3_video_path: '/tmp/clip.mp4',
      kling_o3_status: 'draft',
    })).toBe(true);
  });

  it('clears when approved', () => {
    expect(klingBeatNeedsClipApprove({
      kling_o3_video_path: '/tmp/clip.mp4',
      kling_o3_status: 'approved',
    })).toBe(false);
  });

  it('skips still-insert beats', () => {
    expect(klingBeatNeedsClipApprove({
      pipeline: 'still_insert',
      kling_o3_video_path: '/tmp/clip.mp4',
      kling_o3_status: 'still_rendered',
    }, { stillInsert: true })).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';
import { beatPatchFromO3PollTerminal } from '../bgPollHelpers';

describe('beatPatchFromO3PollTerminal', () => {
  it('uses still_rendered for still-insert fallback patch', () => {
    const patch = beatPatchFromO3PollTerminal(
      'bg_test_beat_06',
      { status: 'done', result: { video: '/tmp/clip.mp4' } },
      { pipeline: 'still_insert', beat_render_mode: 'still_insert' },
    );
    expect(patch?.kling_o3_status).toBe('still_rendered');
    expect(patch?.status).toBe('draft');
    expect(patch?.kling_o3_still_stitch_approved).toBeUndefined();
  });

  it('uses approved for O3 fallback patch', () => {
    const patch = beatPatchFromO3PollTerminal(
      'bg_test_beat_01',
      { status: 'done', result: { video: '/tmp/clip.mp4' } },
      { pipeline: 'kling_o3_omni' },
    );
    expect(patch?.kling_o3_status).toBe('approved');
    expect(patch?.status).toBe('approved');
  });
});

import { describe, expect, it } from 'vitest';
import {
  KLING_STITCH_READINESS_V1,
  beatKlingStitchExportReady,
  stillBeatNeedsStitchApprove,
} from '../klingStitchReadiness';
import { beatIsStitchApproved } from '../bgBeatNavStatus';

describe('KLING_STITCH_READINESS_V1', () => {
  it('exports contract marker', () => {
    expect(KLING_STITCH_READINESS_V1).toBe('KLING_STITCH_READINESS_V1');
  });

  it('O3 delivery clip ready without approved enum', () => {
    expect(beatKlingStitchExportReady({
      kling_o3_status: 'draft',
      kling_o3_video_path: '/clips/beat_g1_delivery.mp4',
      kling_o3_video_path_exists: true,
    })).toBe(true);
  });

  it('still insert needs explicit approve', () => {
    const beat = {
      pipeline: 'still_insert',
      kling_o3_status: 'still_rendered',
      kling_o3_video_path: '/clips/still.mp4',
    };
    expect(beatKlingStitchExportReady(beat)).toBe(false);
    expect(stillBeatNeedsStitchApprove(beat)).toBe(true);
  });

  it('blocks export while job busy', () => {
    expect(beatKlingStitchExportReady({
      kling_o3_video_path: '/clips/beat.mp4',
      job_busy: true,
    })).toBe(false);
  });

  it('nav checkmark uses stitch readiness not raw enum', () => {
    const clipBeat = {
      kling_o3_status: 'draft',
      kling_o3_video_path: '/clips/beat.mp4',
      kling_o3_video_path_exists: true,
    };
    expect(beatIsStitchApproved(clipBeat)).toBe(true);
    expect(beatIsStitchApproved({ kling_o3_status: 'approved' })).toBe(false);
  });
});

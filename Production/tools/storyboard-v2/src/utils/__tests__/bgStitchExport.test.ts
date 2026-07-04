import { describe, expect, it } from 'vitest';
import {
  beatStitchExportReadyFromBeat,
  stitchExportPreflightErrorMessage,
} from '../bgStitchExport';

describe('bgStitchExport', () => {
  it('prefers _derived.stitch_export_ready over client recompute', () => {
    const beat = {
      beat_id: 'bg_test_beat_06',
      pipeline: 'still_insert',
      kling_o3_video_path: '/tmp/clip.mp4',
      kling_o3_status: 'still_rendered',
      _derived: { stitch_export_ready: true },
    };
    expect(beatStitchExportReadyFromBeat(beat)).toBe(true);
  });

  it('falls back to client gate when _derived missing', () => {
    const beat = {
      beat_id: 'bg_test',
      pipeline: 'still_insert',
      kling_o3_video_path: '/tmp/clip.mp4',
      kling_o3_status: 'still_rendered',
    };
    expect(beatStitchExportReadyFromBeat(beat)).toBe(false);
  });

  it('builds preflight error toast from fix_instruction rows', () => {
    const msg = stitchExportPreflightErrorMessage({
      ready: false,
      beats: [
        {
          beat_label: 'beat 6',
          ready: false,
          fix_instruction: 'Open beat 6, click Approve still for stitch.',
        },
      ],
    });
    expect(msg).toContain('Approve still for stitch');
  });
});

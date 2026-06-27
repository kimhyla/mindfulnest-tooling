import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  STITCH_MUX_VIDEO_LINEAGE_V1,
  stitchSlotMuxPreviewLineageMatches,
} from '../stitchMuxVideoLineage.ts';

describe('stitchMuxVideoLineage', () => {
  it('exports contract marker', () => {
    assert.equal(STITCH_MUX_VIDEO_LINEAGE_V1, 'STITCH_MUX_VIDEO_LINEAGE_V1');
  });

  it('matches when mux pins current video_path', () => {
    assert.equal(
      stitchSlotMuxPreviewLineageMatches({
        video_path: 'Production/Event_2/phase_a_stitched_new.mp4',
        mux_video_path: 'Production/Event_2/phase_a_stitched_new.mp4',
        mux_preview_hash: 'abc123def456',
      }),
      true,
    );
  });

  it('rejects unpinned mux (no mux_video_path)', () => {
    assert.equal(
      stitchSlotMuxPreviewLineageMatches({
        video_path: 'Production/Event_2/phase_a_stitched_new.mp4',
        mux_preview_hash: 'abc123def456',
      }),
      false,
    );
  });

  it('rejects mux pinned to different video_path', () => {
    assert.equal(
      stitchSlotMuxPreviewLineageMatches({
        video_path: 'Production/Event_2/phase_a_stitched_new.mp4',
        mux_video_path: 'Production/Event_2/phase_a_stitched_old.mp4',
        mux_preview_hash: 'abc123def456',
      }),
      false,
    );
  });
});

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  o3TrimApplyArtifactPath,
  o3TrimApplyIsBaked,
  o3TrimApplyPreviewUrl,
} from '../o3TrimApplyContract.ts';

describe('O3 trim apply contract — export_baked + trim_baked parity', () => {
  it('treats export_baked as baked (element O3 path)', () => {
    assert.equal(
      o3TrimApplyIsBaked({ export_baked: true, trim_baked: false }),
      true,
    );
  });

  it('prefers baked_path over video_path for artifact', () => {
    const artifact = o3TrimApplyArtifactPath({
      export_baked: true,
      baked_path: '/event/assembled/_kling_o3_trim_scratch/beat_baked.mp4',
      video_path: '/event/clips/beat_g6_delivery.mp4',
    });
    assert.match(artifact ?? '', /beat_baked\.mp4$/);
  });

  it('resolves relative preview_video_url against server base', () => {
    const url = o3TrimApplyPreviewUrl(
      { preview_video_url: '/files?path=Production/Event_5/foo.mp4&v=1' },
      'http://localhost:5115',
    );
    assert.equal(url, 'http://localhost:5115/files?path=Production/Event_5/foo.mp4&v=1');
  });
});

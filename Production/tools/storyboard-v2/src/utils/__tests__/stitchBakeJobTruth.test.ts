import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  isStitchBakeStatusActive,
  isStitchBakeStatusTerminal,
  shouldToastStitchBakeRefreshFailure,
  stitchBakeStatusMessage,
  stitchBakeSuccessPaths,
} from '../stitchBakeJobTruth.ts';

describe('stitchBakeJobTruth', () => {
  it('detects terminal bake statuses', () => {
    assert.equal(isStitchBakeStatusTerminal('done'), true);
    assert.equal(isStitchBakeStatusTerminal('running'), false);
    assert.equal(isStitchBakeStatusActive('queued'), true);
    assert.equal(isStitchBakeStatusActive('done'), false);
  });

  it('toasts refresh failure only when latch set and load missing bake_job', () => {
    assert.equal(shouldToastStitchBakeRefreshFailure(false, true, true), false);
    assert.equal(shouldToastStitchBakeRefreshFailure(true, true, true), false);
    assert.equal(shouldToastStitchBakeRefreshFailure(true, false, false), true);
    assert.equal(shouldToastStitchBakeRefreshFailure(true, true, false), true);
  });

  it('maps poll payload to status message and success paths', () => {
    assert.match(stitchBakeStatusMessage({ phase: 'encode' }), /Encoding/i);
    const paths = stitchBakeSuccessPaths({
      status: 'done',
      result: { canonical_path: '/a/b/final.mp4', asset_id: 42 },
    });
    assert.equal(paths.canonical, '/a/b/final.mp4');
    assert.equal(paths.assetId, 42);
  });
});

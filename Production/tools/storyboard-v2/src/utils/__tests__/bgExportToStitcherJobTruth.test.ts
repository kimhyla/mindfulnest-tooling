// Run: cd storyboard-v2 && node --experimental-strip-types --test src/utils/__tests__/bgExportToStitcherJobTruth.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  bgExportScopeKey,
  bgExportStatusMessage,
  isBgExportStatusTerminal,
  isBgExportStatusActive,
} from '../bgExportToStitcherJobTruth.ts';

describe('bgExportToStitcherJobTruth', () => {
  it('builds scope key with arc, segment event, phase, slot', () => {
    assert.equal(bgExportScopeKey(1, '2', 'pre', 'intro'), '1|2|pre|intro');
  });

  it('detects terminal statuses', () => {
    assert.equal(isBgExportStatusTerminal('done'), true);
    assert.equal(isBgExportStatusTerminal('running'), false);
  });

  it('detects active statuses', () => {
    assert.equal(isBgExportStatusActive('queued'), true);
    assert.equal(isBgExportStatusActive('done'), false);
  });

  it('formats progress message with beat counts', () => {
    assert.equal(
      bgExportStatusMessage({ beat_index: 3, beat_total: 25, phase: 'materialize' }),
      'Sending to Stitcher… (3/25)',
    );
  });
});

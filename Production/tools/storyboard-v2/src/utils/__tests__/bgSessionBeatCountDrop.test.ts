// Run: cd storyboard-v2 && node --experimental-strip-types --test src/utils/__tests__/bgSessionBeatCountDrop.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  beatCountDropMessage,
  shouldWarnBeatCountDrop,
} from '../bgSessionBeatCountDrop.ts';

describe('shouldWarnBeatCountDrop', () => {
  it('warns when count shrinks with beats on both sides', () => {
    assert.equal(shouldWarnBeatCountDrop(12, 6), true);
  });

  it('no warn on first load (prev zero)', () => {
    assert.equal(shouldWarnBeatCountDrop(0, 6), false);
  });

  it('no warn when server returns empty (load failure path)', () => {
    assert.equal(shouldWarnBeatCountDrop(12, 0), false);
  });

  it('no warn when count grows', () => {
    assert.equal(shouldWarnBeatCountDrop(6, 12), false);
  });

  it('message includes counts', () => {
    assert.match(beatCountDropMessage(12, 6), /12.*6/);
  });
});

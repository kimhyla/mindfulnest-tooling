import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  clearBgO3CutDragActive,
  isBgO3CutDragActive,
  markBgO3CutDragActive,
  shouldPreserveBgO3CutDraft,
} from '../bgO3CutSession.ts';

describe('bgO3CutSession', () => {
  it('preserves draft while drag active', () => {
    markBgO3CutDragActive('beat1', 0);
    assert.equal(isBgO3CutDragActive('beat1', 0), true);
    assert.equal(shouldPreserveBgO3CutDraft('beat1', 0, false), true);
    clearBgO3CutDragActive('beat1', 0);
    assert.equal(shouldPreserveBgO3CutDraft('beat1', 0, false), false);
  });

  it('preserves draft when local draft exists', () => {
    assert.equal(shouldPreserveBgO3CutDraft('beat2', 1, true), true);
  });
});

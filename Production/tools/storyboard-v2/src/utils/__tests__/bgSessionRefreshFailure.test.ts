import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { shouldToastBgSessionRefreshFailure } from '../bgSessionRefreshFailure.ts';

describe('shouldToastBgSessionRefreshFailure', () => {
  it('no toast when refresh ok and no busy latch', () => {
    assert.equal(shouldToastBgSessionRefreshFailure(false, true, true), false);
  });

  it('no toast when refresh ok with busy latch cleared by success', () => {
    assert.equal(shouldToastBgSessionRefreshFailure(true, true, true), false);
  });

  it('toast when busy latch and fetch failed', () => {
    assert.equal(shouldToastBgSessionRefreshFailure(true, false, false), true);
  });

  it('toast when busy latch and empty body', () => {
    assert.equal(shouldToastBgSessionRefreshFailure(true, true, false), true);
  });
});

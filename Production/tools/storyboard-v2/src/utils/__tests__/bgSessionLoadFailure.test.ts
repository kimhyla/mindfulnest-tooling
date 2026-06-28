// Run: cd storyboard-v2 && node --experimental-strip-types --test src/utils/__tests__/bgSessionLoadFailure.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { shouldToastBgSessionLoadFailure } from '../bgSessionLoadFailure.ts';

describe('shouldToastBgSessionLoadFailure', () => {
  it('no toast while retries still running', () => {
    assert.equal(
      shouldToastBgSessionLoadFailure({
        message: 'TypeError: Failed to fetch',
        hadCachedBeats: false,
        retriesExhausted: false,
      }),
      false,
    );
  });

  it('toast on first-load failure after retries', () => {
    assert.equal(
      shouldToastBgSessionLoadFailure({
        message: 'TypeError: Failed to fetch',
        hadCachedBeats: false,
        retriesExhausted: true,
      }),
      true,
    );
  });

  it('no toast on restart blip when cached beats remain', () => {
    assert.equal(
      shouldToastBgSessionLoadFailure({
        message: 'TypeError: Failed to fetch',
        hadCachedBeats: true,
        retriesExhausted: true,
      }),
      false,
    );
  });

  it('toast on non-transient failure even with cache', () => {
    assert.equal(
      shouldToastBgSessionLoadFailure({
        message: 'beat g7 not found',
        hadCachedBeats: true,
        retriesExhausted: true,
      }),
      true,
    );
  });
});

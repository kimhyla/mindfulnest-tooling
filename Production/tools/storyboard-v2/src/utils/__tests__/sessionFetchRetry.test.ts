// Run: cd storyboard-v2 && node --experimental-strip-types --test src/utils/__tests__/sessionFetchRetry.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  isTransientSessionFetchError,
  BG_SESSION_RESTART_RETRY_DELAYS_MS,
} from '../sessionFetchRetry.ts';

describe('sessionFetchRetry', () => {
  it('uses dedicated-port restart backoff schedule', () => {
    assert.deepEqual(BG_SESSION_RESTART_RETRY_DELAYS_MS, [500, 1000, 2000, 3000, 3500]);
  });

  it('detects Failed to fetch as transient', () => {
    assert.equal(isTransientSessionFetchError('TypeError: Failed to fetch'), true);
  });

  it('detects scope-not-ready as transient', () => {
    assert.equal(
      isTransientSessionFetchError('Scope reconcile in progress — wait for server scope to verify.'),
      true,
    );
  });

  it('does not treat scope mismatch as transient', () => {
    assert.equal(isTransientSessionFetchError('scope_mismatch'), false);
    assert.equal(isTransientSessionFetchError('HTTP 409'), false);
  });
});

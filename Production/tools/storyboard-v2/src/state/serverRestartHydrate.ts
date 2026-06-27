// BG_SESSION_RESTART_HYDRATE_V1 — stable probe gate before scoped session rehydrate.

import { probeProductionServer } from './serverRehydrate';
import {
  BG_SESSION_RESTART_RETRY_DELAYS_MS,
  delayBeforeBgSessionRetry,
} from '../utils/sessionFetchRetry';

export {
  BG_SESSION_RESTART_RETRY_DELAYS_MS,
  delayBeforeBgSessionRetry,
  isTransientSessionFetchError,
} from '../utils/sessionFetchRetry';

/**
 * Require consecutive successful event/current probes before hydrating Beat Gen /
 * Stitcher / map sessions after restart.
 */
export async function waitForStableProductionServer(
  opts: { requiredSuccesses?: number; maxAttempts?: number } = {},
): Promise<boolean> {
  const requiredSuccesses = opts.requiredSuccesses ?? 2;
  const maxAttempts = opts.maxAttempts ?? BG_SESSION_RESTART_RETRY_DELAYS_MS.length + requiredSuccesses + 2;
  let streak = 0;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) {
      await delayBeforeBgSessionRetry(attempt);
    }
    const probe = await probeProductionServer();
    if (probe.ok) {
      streak += 1;
      if (streak >= requiredSuccesses) return true;
      continue;
    }
    streak = 0;
  }
  return false;
}

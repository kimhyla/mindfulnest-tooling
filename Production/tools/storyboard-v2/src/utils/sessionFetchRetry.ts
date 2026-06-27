// BG_SESSION_RESTART_HYDRATE_V1 — pure retry helpers (no fetch / probe imports for unit tests).

/** Keep in sync with scopeEventCurrent.EVENT_CURRENT_RETRY_DELAYS_MS (~10s total). */
export const BG_SESSION_RESTART_RETRY_DELAYS_MS = [500, 1000, 2000, 3000, 3500] as const;

const TRANSIENT_FETCH_RE =
  /failed to fetch|networkerror|load failed|fetch failed|connection refused|connection reset|empty reply|scope reconcile in progress|scope_not_ready|scope not ready|network request failed/i;

/** True for network blips and scope-not-ready responses that should backoff-retry. */
export function isTransientSessionFetchError(message: string): boolean {
  const m = (message ?? '').trim().toLowerCase();
  if (!m) return true;
  if (TRANSIENT_FETCH_RE.test(m)) return true;
  if (m === 'http 503' || m.includes('503')) return true;
  return false;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export async function delayBeforeBgSessionRetry(attempt: number): Promise<void> {
  if (attempt <= 0) return;
  const idx = Math.min(attempt - 1, BG_SESSION_RESTART_RETRY_DELAYS_MS.length - 1);
  await sleep(BG_SESSION_RESTART_RETRY_DELAYS_MS[idx] ?? 2000);
}

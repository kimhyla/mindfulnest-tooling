// Shared GET /api/event/current with dedicated-port retry (SCOPE_RESTART_RECONCILE_V1).

import { READ_ENDPOINTS } from '../api/endpoints';

/** Backoff schedule for dedicated-port event/current after restart (~10s total). */
export const EVENT_CURRENT_RETRY_DELAYS_MS = [500, 1000, 2000, 3000, 3500] as const;

export interface EventCurrentResponse {
  ok?: boolean;
  event_id?: string | null;
  event_generation?: number;
  active_video?: string | null;
  partition_keys?: string[];
  scope_type?: string;
  active_milestone_id?: string | null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => { setTimeout(resolve, ms); });
}

/** Single fetch — 503 / network → null (caller may retry). */
export async function fetchEventCurrentOnce(): Promise<EventCurrentResponse | null> {
  try {
    const res = await fetch(READ_ENDPOINTS.event_current, { cache: 'no-store' });
    if (res.status === 503) return null;
    if (!res.ok) return null;
    return (await res.json()) as EventCurrentResponse;
  } catch {
    return null;
  }
}

/**
 * Dedicated-port heal waits for pinned server to answer after restart — no event/load.
 * Shared port uses a single attempt unless maxAttempts is raised.
 */
export async function fetchEventCurrentWithRetry(
  opts: { forDedicatedPort?: boolean; maxAttempts?: number } = {},
): Promise<EventCurrentResponse | null> {
  const dedicated = opts.forDedicatedPort === true;
  const maxAttempts = opts.maxAttempts ?? (dedicated ? EVENT_CURRENT_RETRY_DELAYS_MS.length + 1 : 1);
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) {
      const delay = EVENT_CURRENT_RETRY_DELAYS_MS[attempt - 1] ?? 2000;
      await sleep(delay);
    }
    const current = await fetchEventCurrentOnce();
    if (current !== null) return current;
  }
  return null;
}

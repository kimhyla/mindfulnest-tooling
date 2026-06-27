/**
 * PSL core — keyed session slices with in-flight dedupe and staleness windows.
 */

export type SessionStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface SessionSliceMeta {
  status: SessionStatus;
  error: string | null;
  fetchedAt: number;
  inflight: Promise<void> | null;
}

export function isSessionFresh(fetchedAt: number, staleMs: number): boolean {
  if (!fetchedAt) return false;
  return Date.now() - fetchedAt < staleMs;
}

export function sessionHasReadyCache(
  status: SessionStatus,
  hasPayload: boolean,
): boolean {
  return status === 'ready' && hasPayload;
}

export async function runSessionFetch<T>(
  meta: SessionSliceMeta,
  opts: {
    force?: boolean;
    staleMs: number;
    hasPayload: () => boolean;
    showLoading: (on: boolean) => void;
    fetcher: () => Promise<T>;
    onSuccess: (data: T) => void;
    onError: (message: string) => void;
  },
): Promise<void> {
  const cached = sessionHasReadyCache(meta.status, opts.hasPayload());
  if (cached && !opts.force && isSessionFresh(meta.fetchedAt, opts.staleMs)) {
    return;
  }

  if (meta.inflight) {
    await meta.inflight;
    return;
  }

  if (!cached) {
    opts.showLoading(true);
    meta.status = 'loading';
  }

  const task = (async () => {
    try {
      const data = await opts.fetcher();
      opts.onSuccess(data);
      meta.status = 'ready';
      meta.error = null;
      meta.fetchedAt = Date.now();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      meta.status = 'error';
      meta.error = msg;
      opts.onError(msg);
    } finally {
      meta.inflight = null;
      opts.showLoading(false);
    }
  })();

  meta.inflight = task;
  await task;
}

/** Test-only reset */
export function resetSessionMeta(meta: SessionSliceMeta): void {
  meta.status = 'idle';
  meta.error = null;
  meta.fetchedAt = 0;
  meta.inflight = null;
}

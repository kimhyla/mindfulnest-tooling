/**
 * STITCH_SFX_HOT_SERVE_PREFETCH_V1 — client-mix SFX bytes via /files with 503 retry.
 * Same Dropbox File Provider class as gray video; never give up on first busy response.
 */

export const STITCH_SFX_FETCH_MAX_ATTEMPTS = 4;

export function stitchSfxFetchRetryDelayMs(attemptIndex: number): number {
  return 200 * (attemptIndex + 1);
}

export function stitchSfxFetchIsRetryableStatus(status: number): boolean {
  return status === 503 || status === 429;
}

/** Fetch SFX bytes; retry transient hot-serve materialize failures. */
export async function fetchStitchSfxArrayBuffer(
  url: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ArrayBuffer> {
  let lastErr: Error | null = null;
  for (let attempt = 0; attempt < STITCH_SFX_FETCH_MAX_ATTEMPTS; attempt += 1) {
    const res = await fetchImpl(url);
    if (res.ok) {
      return res.arrayBuffer();
    }
    lastErr = new Error(`SFX fetch failed: HTTP ${res.status}`);
    if (
      !stitchSfxFetchIsRetryableStatus(res.status)
      || attempt === STITCH_SFX_FETCH_MAX_ATTEMPTS - 1
    ) {
      throw lastErr;
    }
    await new Promise((r) => setTimeout(r, stitchSfxFetchRetryDelayMs(attempt)));
  }
  throw lastErr ?? new Error('SFX fetch failed');
}

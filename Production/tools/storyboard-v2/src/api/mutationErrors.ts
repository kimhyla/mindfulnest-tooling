import type { ApiResult } from './client';

/** User-facing text for failed pathappPatch / mutation helpers. */
export function formatMutationError(
  result: Pick<ApiResult, 'ok' | 'error' | 'error_code' | 'status'>,
  actionLabel: string,
): string {
  if (result.ok) return '';
  if (result.error_code === 'SCOPE_MISMATCH') {
    return (
      `${actionLabel}: server is pinned to a different event than this tab. `
      + 'Pick the event again from Project or hard-refresh with ?event= in the URL.'
    );
  }
  if (result.error_code === 'SIDECAR_IO_TRANSIENT') {
    return (
      `${actionLabel}: Dropbox is busy syncing the beat sidecar — wait a few seconds and retry.`
    );
  }
  if (result.status === 0 && /failed to fetch|networkerror|load failed/i.test(result.error ?? '')) {
    return (
      `${actionLabel}: could not reach the storyboard server `
      + '(often during event switch or restart). Wait a moment and try again.'
    );
  }
  const detail = result.error ?? (result.status ? `HTTP ${result.status}` : 'unknown error');
  return `${actionLabel}: ${detail}`;
}

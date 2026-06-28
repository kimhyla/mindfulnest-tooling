import type { ApiResult } from './client';
import { isScopeMismatchRecentlySurfaced } from './errorBoundary';
import { isClientBundleStaleError } from '../state/buildShaDrift';

/** User-facing text for failed pathappPatch / mutation helpers. */
export function formatMutationError(
  result: Pick<ApiResult, 'ok' | 'error' | 'error_code' | 'error_message' | 'status' | 'hint'>,
  actionLabel: string,
): string {
  if (result.ok) return '';
  if (isClientBundleStaleError(result)) {
    // BuildShaDriftBanner is the single persistent surface — no per-action toast text.
    return '';
  }
  if (result.error_code === 'SCOPE_MISMATCH') {
    if (isScopeMismatchRecentlySurfaced({
      error_code: 'SCOPE_MISMATCH',
      error_message: result.error_message ?? result.error ?? 'scope_mismatch',
      hint: result.hint ?? null,
    })) {
      return '';
    }
    return (
      `${actionLabel}: server is pinned to a different event than this tab. `
      + 'Pick the event again from Project or hard-refresh with ?event= in the URL.'
    );
  }
  if (result.error_code === 'MILESTONE_SCOPE_REQUIRED') {
    return (
      `${actionLabel}: Milestone scope not loaded on server — retry in a moment or reload.`
    );
  }
  if (result.error_code === 'SCOPE_NOT_READY') {
    return (
      `${actionLabel}: server scope is still verifying after restart — wait a moment and retry.`
    );
  }
  if (result.error_code === 'SIDECAR_IO_TRANSIENT') {
    return (
      `${actionLabel}: Dropbox is busy syncing the beat sidecar — wait a few seconds and retry.`
    );
  }
  if (result.error_code === 'SIDECAR_LOCK_TIMEOUT') {
    return (
      `${actionLabel}: server is busy saving another beat — wait a few seconds and retry. `
      + 'Cut preview may still work; use Preview cut if the trimmed clip did not appear.'
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

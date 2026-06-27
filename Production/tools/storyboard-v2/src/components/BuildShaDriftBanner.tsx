// BUILD_SHA_DRIFT_V1 — persistent banner when deploy replaced HTML but tab runs stale JS.
// Mutations are blocked in pathappPatch; banner replaces per-action error toasts.

import { CLIENT_BUNDLE_STALE_MESSAGE, buildShaDriftPair, clientBundleStale, reloadForFreshBundle } from '../state/buildShaDrift';

export function BuildShaDriftBanner() {
  if (!clientBundleStale.value) return null;

  const pair = buildShaDriftPair.value;
  const detail = pair ? ` (this tab: ${pair.split(' → ')[0]}, server: ${pair.split(' → ')[1]})` : '';

  return (
    <div
      class="mn-scope-banner mn-scope-banner-error"
      data-testid="build-sha-drift-banner"
      role="alert"
    >
      <span class="mn-scope-banner-text">
        {CLIENT_BUNDLE_STALE_MESSAGE}
        {detail}
        {' '}
        Your prompt text is still in the box — reload, then edits will save again.
      </span>
      <button
        type="button"
        class="mn-scope-banner-action"
        data-testid="build-sha-drift-reload"
        onClick={() => reloadForFreshBundle()}
      >
        Reload page
      </button>
    </div>
  );
}

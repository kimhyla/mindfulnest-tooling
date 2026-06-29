// BUILD_SHA_DRIFT_V1 — block mutations when deploy replaced HTML but tab runs stale JS.

import { signal } from '@preact/signals';
import { setScopeReady } from './scopeReady';
import { parseBuildShaFromHtml, readBuildShaMetaContent, buildShaDriftDetected } from './buildShaMeta';
import { pushToast } from '../components/ui/Toast';

export const CLIENT_BUNDLE_STALE_MESSAGE =
  'Storyboard updated — reload this page to continue editing.';

/** Shown in persistent banner: ``3416ffe → 91a04bb`` */
export const buildShaDriftPair = signal<string | null>(null);

export const clientBundleStale = signal(false);

let bundledBuildSha = '';

function readMetaBuildShaFromDocument(doc: Document): string {
  return readBuildShaMetaContent(doc);
}

/** Called once at app boot — captures sha embedded in this JS bundle's HTML. */
export function initBundledBuildSha(): string {
  if (typeof document !== 'undefined') {
    bundledBuildSha = readMetaBuildShaFromDocument(document);
  }
  return bundledBuildSha;
}

export function readBundledBuildSha(): string {
  if (!bundledBuildSha && typeof document !== 'undefined') {
    bundledBuildSha = readMetaBuildShaFromDocument(document);
  }
  return bundledBuildSha;
}

/** Fetch live served HTML and parse build-sha meta (no-store). */
export async function fetchLiveBuildSha(): Promise<string | null> {
  if (typeof window === 'undefined') return null;
  try {
    const res = await fetch(window.location.href.split('#')[0] ?? '/', { cache: 'no-store' });
    if (!res.ok) return null;
    const html = await res.text();
    return parseBuildShaFromHtml(html);
  } catch {
    return null;
  }
}

/**
 * Compare bundled vs live sha. On drift: mark stale, block scopeReady, return true.
 * Persistent UI: BuildShaDriftBanner (no toast spam per mutation).
 */
export async function checkBuildShaDrift(): Promise<boolean> {
  const bundled = readBundledBuildSha();
  const live = await fetchLiveBuildSha();
  if (!live || !buildShaDriftDetected(bundled, live)) {
    if (clientBundleStale.value && bundled && live && bundled === live) {
      clientBundleStale.value = false;
      buildShaDriftPair.value = null;
      if (typeof document !== 'undefined') {
        document.body.removeAttribute('data-build-sha-drift');
      }
      setScopeReady(true, 'build-sha-recovered');
    }
    return false;
  }
  clientBundleStale.value = true;
  buildShaDriftPair.value = `${bundled} → ${live}`;
  setScopeReady(false, 'build-sha-drift');
  if (typeof document !== 'undefined') {
    document.body.setAttribute('data-build-sha-drift', `${bundled}->${live}`);
  }
  return true;
}

/** Hard reload preserving query string — required after deploy before any save. */
export function reloadForFreshBundle(): void {
  window.location.reload();
}

const AUTO_RELOAD_SESSION_KEY = 'mn:build-sha-auto-reload-pair';

/** Playwright / automated tests must not hard-reload mid-spec. */
export function shouldAutoReloadOnBuildShaDrift(): boolean {
  if (typeof navigator !== 'undefined' && navigator.webdriver) return false;
  try {
    if (sessionStorage.getItem('mn:disable-build-sha-auto-reload') === '1') return false;
  } catch {
    // ignore
  }
  return true;
}

/**
 * On drift: auto-reload once per bundled→live pair (zero-touch after deploy).
 * Returns true when drift detected (reload may have started).
 */
export async function checkBuildShaDriftAndAutoReload(reason: string): Promise<boolean> {
  const drift = await checkBuildShaDrift();
  if (!drift) return false;
  if (!shouldAutoReloadOnBuildShaDrift()) return true;

  const pair = buildShaDriftPair.value;
  if (pair) {
    try {
      if (sessionStorage.getItem(AUTO_RELOAD_SESSION_KEY) === pair) {
        return true;
      }
      sessionStorage.setItem(AUTO_RELOAD_SESSION_KEY, pair);
    } catch {
      // proceed with reload
    }
  }

  if (typeof window !== 'undefined') {
    pushToast({
      kind: 'info',
      message: `Storyboard updated (${reason}) — reloading…`,
      source: 'build-sha-auto-reload',
      ttlMs: 4000,
    });
    window.setTimeout(() => reloadForFreshBundle(), 120);
  }
  return true;
}

export function isClientBundleStale(): boolean {
  return clientBundleStale.value;
}

export function isClientBundleStaleError(
  result: Pick<{ ok?: boolean; error_code?: string }, 'ok' | 'error_code'>,
): boolean {
  return !result.ok && result.error_code === 'CLIENT_BUNDLE_STALE';
}

/** Test hook — reset drift state. */
export function _resetBuildShaDriftForTesting(): void {
  clientBundleStale.value = false;
  buildShaDriftPair.value = null;
  bundledBuildSha = '';
}

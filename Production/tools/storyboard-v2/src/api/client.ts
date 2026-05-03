// Single mutation channel. Path C architectural commitment per LDs
// PATH_C_REWRITE_V1 (455), SCOPE_VALIDATION_V1 (456), EVENT_LOAD_GENERATION_LOCK_V1 (458),
// UNIVERSAL_AUTOSAVE_V1 (459), ASYNC_JOB_GENERATION_PIN_V1 (460), SCOPE_BODY_HELPER_V1 (461).
//
// Every state change in the app goes through pathappPatch(scope, endpoint, body).
// Components MUST NOT call fetch() directly for mutations. The function:
//   1. Calls /api/state/snapshot first (M1) — every mutation is preceded by
//      a state.json copy in Production/Event_<N>/.backups/state/.
//   2. Injects scope.event_id under the correct key (`scope_event_id` for BG
//      endpoints, `event_id` for non-BG) per LD-461.
//   3. POSTs the request as JSON.
//   4. Handles HTTP 409 (scope_mismatch) by emitting a window event for the
//      app to surface a red banner + reload prompt; returns ok=false.
//   5. Handles HTTP 423 (event_changed_mid_job, async-pin reject) by
//      re-fetching event-state to refresh local generation, then retrying
//      the mutation ONCE. If retry also fails, surface red banner.
//   6. Returns ApiResult so callers can branch on ok/error.

import type { Scope } from '../state/scope';
import { activeScope } from '../state/scope';
import {
  READ_ENDPOINTS,
  MUTATION_ENDPOINTS,
  scopeKeyFor,
  type ReadEndpoint,
  type MutationEndpoint,
} from './endpoints';

export interface ApiResult<T = unknown> {
  ok: boolean;
  status: number;
  data?: T;
  error?: string;
}

// ============================================================================
// Surfacing scope events to the app UI
// ============================================================================

/**
 * Custom event names dispatched on `window` by pathappPatch when the server
 * rejects a mutation. The App's ScopeBoundary (or a toast/banner component)
 * listens and surfaces the appropriate UI.
 *
 *   mn:scope-mismatch  — HTTP 409 (LD-456). Body: {endpoint, expected, got}.
 *                        UI: red banner + "Reload page" CTA.
 *   mn:event-changed   — HTTP 423 (LD-458/460). Body: {endpoint, retried}.
 *                        UI: subtle toast "Event changed; re-syncing…".
 */
export const SCOPE_EVENT_MISMATCH = 'mn:scope-mismatch';
export const SCOPE_EVENT_CHANGED = 'mn:event-changed';

function emitScopeMismatch(detail: Record<string, unknown>): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SCOPE_EVENT_MISMATCH, { detail }));
  }
}
function emitEventChanged(detail: Record<string, unknown>): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SCOPE_EVENT_CHANGED, { detail }));
  }
}

// ============================================================================
// READ — apiGet
// ============================================================================

export async function apiGet<T = unknown>(
  endpoint: ReadEndpoint,
  query: Record<string, string> = {},
): Promise<ApiResult<T>> {
  // Substitute {placeholder} tokens in the URL template with values from
  // the query dict. Substituted keys are CONSUMED so they don't ALSO end
  // up in the query string. (Some endpoints, like v2_event_state, expect
  // event_id in the path, not the query.)
  let urlStr: string = READ_ENDPOINTS[endpoint];
  const remaining: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    const token = `{${k}}`;
    if (urlStr.includes(token)) {
      urlStr = urlStr.split(token).join(encodeURIComponent(v));
    } else {
      remaining[k] = v;
    }
  }
  const url = new URL(urlStr);
  for (const [k, v] of Object.entries(remaining)) url.searchParams.set(k, v);

  try {
    const res = await fetch(url.toString());
    let data: T | undefined;
    try {
      data = (await res.json()) as T;
    } catch {
      // non-JSON or empty body
    }
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        error: `${res.status} ${res.statusText}`,
        ...(data === undefined ? {} : { data }),
      };
    }
    return {
      ok: true,
      status: res.status,
      ...(data === undefined ? {} : { data }),
    };
  } catch (e) {
    return { ok: false, status: 0, error: String(e) };
  }
}

// ============================================================================
// loadEvent — atomic event swap
// ============================================================================

export interface EventLoadResponse {
  ok: boolean;
  event_id: string;
  event_dir: string;
  storyboard: string;
  event_generation: number;
  previous_generation: number;
  previous_event_id: string;
}

/**
 * POST /api/event/load — atomically swap the server's pinned event.
 * Returns the new generation number; the v59 client should treat the
 * generation as opaque but bump activeScope's version to match.
 */
export async function loadEvent(
  newEventId: string,
  storyboard?: string,
): Promise<ApiResult<EventLoadResponse>> {
  const body: Record<string, unknown> = { event_id: newEventId };
  if (storyboard) body['storyboard'] = storyboard;
  return apiPostRaw<EventLoadResponse>(
    MUTATION_ENDPOINTS.event_load,
    body,
    'POST',
  );
}

// ============================================================================
// MUTATE — pathappPatch (single mutation channel)
// ============================================================================

export interface PatchOptions {
  /** Skip the M1 pre-write snapshot. Default false. Used internally by the
   *  snapshot endpoint itself to avoid recursion. */
  skipSnapshot?: boolean;
  /** Override fetch method (default POST). */
  method?: 'POST' | 'PATCH';
  /** Internal — set during 423-retry to suppress further retries. */
  _isRetry?: boolean;
}

/**
 * The ONLY mutation entry point. See file header for full contract.
 *
 * Status code policy:
 *   - 200/2xx — success.
 *   - 409 — scope_mismatch (LD-456). Emit mn:scope-mismatch event; ok=false.
 *   - 423 — event_changed_mid_job (LD-458/460). Re-hydrate scope + retry once.
 *   - 4xx/5xx other — propagate as ok=false with error message.
 */
export async function pathappPatch<T = unknown>(
  scope: Scope,
  endpoint: MutationEndpoint,
  body: Record<string, unknown> = {},
  opts: PatchOptions = {},
): Promise<ApiResult<T>> {
  const method = opts.method ?? 'POST';

  // M1 — state snapshot before every v59 write.
  if (!opts.skipSnapshot && endpoint !== 'state_snapshot' && endpoint !== 'event_load') {
    // Fire-and-forget snapshot with explicit scope. Failure is logged but
    // does NOT block the mutation (the snapshot is a safety net, not a gate).
    const snap = await apiPostRaw(
      MUTATION_ENDPOINTS.state_snapshot,
      { event_id: scope.event_id },
      'POST',
    );
    if (!snap.ok) {
      // Visible in console for debugging; does NOT abort the mutation.
      // (Per spec §3.5: snapshot is "every mutation is rollback-able" — if
      // the snapshot endpoint is down, we still want the mutation to land
      // and we surface the snapshot failure separately.)
      // eslint-disable-next-line no-console
      console.warn('[pathappPatch] snapshot failed (non-fatal):', snap.error);
    }
  }

  // LD-461 — pick the right scope key per handler convention.
  const scopeKey = scopeKeyFor(endpoint);
  const payload: Record<string, unknown> = {
    ...body,
    [scopeKey]: scope.event_id,
    beat_id: scope.beat_id,
    scope_version: scope.version,
  };

  const result = await apiPostRaw<T>(MUTATION_ENDPOINTS[endpoint], payload, method);

  // LD-456 — HTTP 409 scope mismatch. Surface, do not retry.
  if (result.status === 409) {
    emitScopeMismatch({
      endpoint,
      status: 409,
      data: result.data,
      hint: 'reload tab to re-resolve scope',
    });
    return result;
  }

  // LD-458/460 — HTTP 423 event_changed_mid_job. Re-hydrate + retry once.
  if (result.status === 423 && !opts._isRetry) {
    emitEventChanged({ endpoint, status: 423, phase: 'before-retry' });
    // Re-fetch v2 event-state so any cached client-side state refreshes.
    await apiGet('v2_event_state', { event_id: scope.event_id });
    // Retry with _isRetry=true so a second 423 surfaces as a final error.
    const retried = await pathappPatch<T>(scope, endpoint, body, {
      ...opts,
      _isRetry: true,
    });
    emitEventChanged({
      endpoint,
      status: retried.status,
      phase: 'after-retry',
      retried_ok: retried.ok,
    });
    return retried;
  }

  return result;
}

/**
 * Internal — raw POST/PATCH used by pathappPatch. NOT exported to components;
 * components MUST go through pathappPatch which guarantees scope injection +
 * snapshot + 409/423 handling.
 */
async function apiPostRaw<T = unknown>(
  url: string,
  payload: Record<string, unknown>,
  method: 'POST' | 'PATCH' = 'POST',
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    let data: T | undefined;
    try {
      data = (await res.json()) as T;
    } catch {
      // non-JSON body (e.g., 204 No Content)
    }
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        error: `${res.status} ${res.statusText}`,
        ...(data === undefined ? {} : { data }),
      };
    }
    return {
      ok: true,
      status: res.status,
      ...(data === undefined ? {} : { data }),
    };
  } catch (e) {
    return { ok: false, status: 0, error: String(e) };
  }
}

// Used by tests / dev tooling to inspect activeScope without coupling to
// the signal import directly.
export function _currentScopeForTesting(): Scope {
  return activeScope.value;
}

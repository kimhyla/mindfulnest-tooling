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
//   4. Handles HTTP 409 (scope_mismatch) by auto-healing server pin via
//      POST /api/event/load when client/server drift (SCOPE_MISMATCH_AUTO_HEAL_V1),
//      then retrying once; only surfaces the red banner if heal+retry fails.
//   5. Handles HTTP 423 (event_changed_mid_job, async-pin reject) by
//      re-fetching event-state to refresh local generation, then retrying
//      the mutation ONCE. If retry also fails, surface red banner.
//   6. Returns ApiResult so callers can branch on ok/error.

import type { Scope } from '../state/scope';
import {
  activeScope,
  activeTargetVideo,
  activeProjectType,
  activeMilestoneId,
  makeScope,
} from '../state/scope';
import { clientMayPinServerTo, noteClientPinnedEvent } from '../state/scopeAuthority';
import {
  READ_ENDPOINTS,
  MUTATION_ENDPOINTS,
  scopeKeyFor,
  type ReadEndpoint,
  type MutationEndpoint,
} from './endpoints';
import { dispatchV59Error, type V59Error } from './errorBoundary';

export interface ApiResult<T = unknown> {
  ok: boolean;
  status: number;
  data?: T;
  error?: string;
  /** V59 Phase 7 canonical error fields (when server returns ok:false + error_code). */
  error_code?: string;
  error_message?: string;
  retry_safe?: boolean;
  hint?: string | null;
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

function emitEventChanged(detail: Record<string, unknown>): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SCOPE_EVENT_CHANGED, { detail }));
  }
}

/** True when body is V59 Phase 7 canonical error shape (ok:false + error_code). */
function isV59ErrorBody(d: Record<string, unknown>): boolean {
  return d['ok'] === false && typeof d['error_code'] === 'string';
}

function v59ErrorFromBody(d: Record<string, unknown>): V59Error {
  return {
    ...d,
    error_code: String(d['error_code']),
    error_message: String(d['error_message'] ?? ''),
    retry_safe: d['retry_safe'] !== false,
    hint: d['hint'] == null ? null : String(d['hint']),
  };
}

interface RawPostOptions {
  /** When true, SCOPE_MISMATCH does not emit mn:scope-mismatch (caller may heal+retry). */
  suppressScopeDispatch?: boolean;
  /** Internal — one retry after server restart blip (NETWORK_RESTART_RETRY_V1). */
  _networkRetry?: boolean;
}

interface ApiGetOptions {
  /** Internal — set during READ scope-mismatch auto-heal retry (READ_SCOPE_HEAL_V1). */
  _scopeHealRetry?: boolean;
  /** Internal — cap heal loops so transient restart blips do not stick the red banner. */
  _scopeHealAttempt?: number;
  /** Internal — one retry after server restart blip (NETWORK_RESTART_RETRY_V1). */
  _networkRetry?: boolean;
}

export const SCOPE_HEALED_EVENT = 'mn:scope-healed';

export function emitScopeHealed(detail: Record<string, unknown> = {}): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SCOPE_HEALED_EVENT, { detail }));
  }
}

/** Parse non-OK JSON: V59 canonical shape first, then legacy {error} / {error_code}. */
function parseApiError<T>(
  status: number,
  data: T | undefined,
  statusText = '',
  opts: RawPostOptions = {},
): ApiResult<T> {
  const d = data as Record<string, unknown> | undefined;
  if (d && isV59ErrorBody(d)) {
    const v59 = v59ErrorFromBody(d);
    const suppressScope =
      opts.suppressScopeDispatch === true && v59.error_code === 'SCOPE_MISMATCH';
    if (typeof window !== 'undefined' && !suppressScope) {
      dispatchV59Error(v59);
    }
    return {
      ok: false,
      status,
      error: v59.error_message,
      error_code: v59.error_code,
      error_message: v59.error_message,
      retry_safe: v59.retry_safe,
      hint: v59.hint,
      ...(data === undefined ? {} : { data }),
    };
  }
  const serverMsg = d?.['error'] ?? d?.['message'] ?? d?.['error_code'];
  return {
    ok: false,
    status,
    error: serverMsg
      ? String(serverMsg)
      : statusText
        ? `${status} ${statusText}`
        : `${status}`,
    ...(data === undefined ? {} : { data }),
  };
}

/** Cross-tab scope switch (D1 tie-all-tabs). Tabs listen and/or react via activeScope deps. */
export function emitScopeEventChanged(detail: Record<string, unknown> = {}): void {
  emitEventChanged(detail);
}

// ============================================================================
// READ — apiGet
// ============================================================================

export async function apiGet<T = unknown>(
  endpoint: ReadEndpoint,
  query: Record<string, string> = {},
  opts: ApiGetOptions = {},
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
      const isScope409 = res.status === 409
        && typeof (data as Record<string, unknown> | undefined)?.['error_code'] === 'string'
        && (data as Record<string, unknown>)['error_code'] === 'SCOPE_MISMATCH';
      const attempt = opts._scopeHealAttempt ?? 0;
      const result = parseApiError(res.status, data, res.statusText, {
        // Never flash the persistent banner while READ auto-heal is still retrying.
        suppressScopeDispatch: isScope409 && attempt < 2,
      });
      if (isScopeMismatchResult(result) && attempt < 2) {
        if (await healServerScopeIfNeeded(activeScope.value)) {
          emitScopeHealed({ event_id: activeScope.value.event_id, source: 'apiGet-heal' });
          return apiGet(endpoint, query, {
            _scopeHealRetry: true,
            _scopeHealAttempt: attempt + 1,
          });
        }
      }
      if (isScopeMismatchResult(result) && attempt >= 2 && typeof window !== 'undefined') {
        dispatchV59Error({
          error_code: result.error_code ?? 'SCOPE_MISMATCH',
          error_message: result.error_message ?? result.error ?? 'scope_mismatch',
          retry_safe: result.retry_safe !== false,
          hint: result.hint ?? null,
        });
      }
      return result;
    }
    return {
      ok: true,
      status: res.status,
      ...(data === undefined ? {} : { data }),
    };
  } catch (e) {
    const err = String(e);
    if (!opts._networkRetry && /failed to fetch|networkerror|load failed/i.test(err)) {
      await new Promise((resolve) => { setTimeout(resolve, 2000); });
      return apiGet(endpoint, query, { ...opts, _networkRetry: true });
    }
    return { ok: false, status: 0, error: err };
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

/**
 * SCOPE_MISMATCH_AUTO_HEAL_V1 — when server pin drifts (restart, QA script),
 * re-pin to the client's activeScope.event_id before surfacing 409 — but only
 * when this tab has pin authority (URL ?event= or explicit Project/ScopeBoundary pin).
 * Background polls adopt server pin instead (SCOPE_POLL_ADOPT_V1).
 */
async function healServerScopeIfNeeded(scope: Scope): Promise<boolean> {
  try {
    const res = await fetch(READ_ENDPOINTS.event_current);
    if (res.ok) {
      const data = (await res.json()) as { event_id?: string };
      if (data?.event_id === scope.event_id) return true;
    }
  } catch {
    // Fall through to explicit load when authorized.
  }
  if (!clientMayPinServerTo(scope.event_id)) {
    return false;
  }
  const load = await loadEvent(scope.event_id);
  if (!load.ok || !load.data?.event_id) return false;
  noteClientPinnedEvent(load.data.event_id);
  activeScope.value = makeScope(
    load.data.event_id,
    scope.beat_id,
    load.data.event_generation,
  );
  emitScopeEventChanged({
    event_id: load.data.event_id,
    event_generation: load.data.event_generation,
    scope_key: `${load.data.event_id}:${scope.beat_id ?? 'global'}:v${load.data.event_generation}`,
    source: 'scope-mismatch-auto-heal',
  });
  emitScopeHealed({ event_id: load.data.event_id, source: 'scope-mismatch-auto-heal' });
  return true;
}

export { noteClientPinnedEvent } from '../state/scopeAuthority';

/** Ensure server process pin matches eventId before tabs fetch scoped READ endpoints. */
export async function ensureServerPinnedTo(eventId: string): Promise<boolean> {
  const scope = makeScope(eventId, activeScope.value.beat_id, activeScope.value.version);
  return healServerScopeIfNeeded(scope);
}

function isScopeMismatchResult<T>(result: ApiResult<T>): boolean {
  return !result.ok && result.error_code === 'SCOPE_MISMATCH';
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
  /** Internal — set during 409 scope-mismatch auto-heal retry. */
  _scopeHealRetry?: boolean;
}

/**
 * The ONLY mutation entry point. See file header for full contract.
 *
 * Status code policy:
 *   - 200/2xx — success.
 *   - 409 — scope_mismatch (LD-456). Auto-heal server pin + retry once;
 *           emit mn:scope-mismatch only if heal+retry still fails.
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
    //
    // F-STORYBOARD-001 fix (prod_blockers id=120, 2026-05-10):
    // Server's /api/state/snapshot handler requires scope_video_role per LD-474
    // (VIDEO_ROLE_INVALID error). Inline smoke captured 6/7 snapshot calls
    // returning 400 [CONFIRMED against prod_activity_log id=2706 closure summary
    // + direct probe POST /api/state/snapshot with {event_id, scope} returning
    // {"error":"video_role_required","code":"VIDEO_ROLE_INVALID","hint":"scope_video_role
    // required on this endpoint (LD-474)"}]. Including scope_video_role +
    // scope_event_id in the body matches the pattern used for the main mutation
    // payload below.
    const snap = await apiPostRaw(
      MUTATION_ENDPOINTS.state_snapshot,
      {
        event_id: scope.event_id,
        scope_event_id: scope.event_id,
        scope_video_role: activeTargetVideo.value,
        scope_version: scope.version,
      },
      'POST',
      { suppressScopeDispatch: !opts._scopeHealRetry },
    );
    if (isScopeMismatchResult(snap) && !opts._scopeHealRetry) {
      if (await healServerScopeIfNeeded(scope)) {
        return pathappPatch(activeScope.value, endpoint, body, { ...opts, _scopeHealRetry: true });
      }
      if (typeof window !== 'undefined' && snap.error_code) {
        dispatchV59Error({
          error_code: snap.error_code,
          error_message: snap.error_message ?? snap.error ?? 'scope_mismatch',
          retry_safe: snap.retry_safe !== false,
          hint: snap.hint ?? null,
        });
      }
    }
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
  // S5.5b: also auto-inject scope_video_role from activeVideoRole signal so
  // every mutating request carries the partition selector per LD-474. Caller
  // can override by passing scope_video_role explicitly in `body`.
  // S5.5d (v3): also auto-inject scope_target_video (canonical name, same
  // value as scope_video_role) + scope_milestone_id when active. The
  // dual-key emit lets server handlers transition incrementally.
  const scopeKey = scopeKeyFor(endpoint);
  const payload: Record<string, unknown> = {
    // baseline — body can override.
    // S5.5c+e proper-fix R2: beat_id MOVED before ...body so drop handlers
    // can pass the dropped-on beat_id explicitly without scope.beat_id
    // (typically null) overwriting it. Scope-key + scope_version stay AFTER
    // body since those identify the request scope and must not be overridden.
    scope_video_role: activeTargetVideo.value,
    scope_target_video: activeTargetVideo.value,
    beat_id: scope.beat_id,
    ...body,
    [scopeKey]: scope.event_id,
    scope_version: scope.version,
  };
  // Milestone-scope injection per MILESTONE_STANDALONE_INDEPENDENT_V1.
  if (activeProjectType.value === 'milestone' && activeMilestoneId.value) {
    payload['scope_milestone_id'] = activeMilestoneId.value;
  } else {
    payload['scope_event_id'] = scope.event_id;
  }

  const result = await apiPostRaw<T>(
    MUTATION_ENDPOINTS[endpoint],
    payload,
    method,
    { suppressScopeDispatch: !opts._scopeHealRetry },
  );

  // LD-456 — SCOPE_MISMATCH auto-heal (SCOPE_MISMATCH_AUTO_HEAL_V1).
  if (isScopeMismatchResult(result) && !opts._scopeHealRetry) {
    if (await healServerScopeIfNeeded(scope)) {
      return pathappPatch(activeScope.value, endpoint, body, { ...opts, _scopeHealRetry: true });
    }
    if (typeof window !== 'undefined' && result.error_code) {
      dispatchV59Error({
        error_code: result.error_code,
        error_message: result.error_message ?? result.error ?? 'scope_mismatch',
        retry_safe: result.retry_safe !== false,
        hint: result.hint ?? null,
      });
    }
    return result;
  }

  // LD-456 — other HTTP 409 responses must NOT emit mn:scope-mismatch.

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
  opts: RawPostOptions = {},
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
      return parseApiError(res.status, data, res.statusText, opts);
    }
    return {
      ok: true,
      status: res.status,
      ...(data === undefined ? {} : { data }),
    };
  } catch (e) {
    const err = String(e);
    if (!opts._networkRetry && /failed to fetch|networkerror|load failed/i.test(err)) {
      await new Promise((resolve) => { setTimeout(resolve, 2000); });
      return apiPostRaw(url, payload, method, { ...opts, _networkRetry: true });
    }
    return { ok: false, status: 0, error: err };
  }
}

// Used by tests / dev tooling to inspect activeScope without coupling to
// the signal import directly.
export function _currentScopeForTesting(): Scope {
  return activeScope.value;
}

// ============================================================================
// LD-778 — expectField 4-gate response body validator for runMutation callers.
// The IMPLEMENTATION lives in `./expectFieldGate.ts` (zero-dep module so the
// unit test can `node --experimental-strip-types` it without dragging in the
// rest of the storyboard-v2 module tree, which uses bundler-style
// extensionless imports incompatible with Node's strict ESM resolver).
// client.ts re-exports here so existing callers (StoryboardTab.tsx's
// runMutation) keep importing from '../api/client'.
// ============================================================================

export { expectField } from './expectFieldGate.ts';
export type { ExpectFieldSpec } from './expectFieldGate.ts';

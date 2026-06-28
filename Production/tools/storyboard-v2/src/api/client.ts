// Single mutation channel. Path C architectural commitment per LDs
// PATH_C_REWRITE_V1 (455), SCOPE_VALIDATION_V1 (456), EVENT_LOAD_GENERATION_LOCK_V1 (458),
// UNIVERSAL_AUTOSAVE_V1 (459), ASYNC_JOB_GENERATION_PIN_V1 (460), SCOPE_BODY_HELPER_V1 (461).
//
// Every state change in the app goes through pathappPatch(scope, endpoint, body).
// Components MUST NOT call fetch() directly for mutations. The function:
//   1. Calls /api/state/snapshot first (M1) — every mutation is preceded by
//      a state.json copy in Production/Event_<N>/.backups/state/.
//   2. Injects scope pin as `scope_event_id` only (LD-461 category fix —
//      never auto-inject top-level event_id; body.event_id is caller-owned).
//   3. POSTs the request as JSON.
//   4. Handles HTTP 409 (scope_mismatch) by auto-healing server pin via
//      POST /api/event/load when client/server drift (SCOPE_MISMATCH_AUTO_HEAL_V1),
//      or dedicated-port scope sync (SCOPE_CLIENT_AUTHORITY_V1), then retrying once.
//   5. Handles HTTP 423 (event_changed_mid_job, async-pin reject) by
//      re-fetching event-state to refresh local generation, then retrying
//      the mutation ONCE. If retry also fails, surface red banner.
//   6. Returns ApiResult so callers can branch on ok/error.

import type { Scope } from '../state/scope';
import {
  activeScope,
  effectiveScopeVideoRole,
  activeMilestoneId,
  makeScope,
  readUrlMilestoneId,
  shouldInjectMilestoneScope,
} from '../state/scope';
import { confirmServerMilestoneScope } from '../state/milestoneScopeGate';
import { clientMayPinServerTo, isDedicatedPortForEvent, noteClientPinnedEvent, readUrlEventId, readDedicatedPortEventId } from '../state/scopeAuthority';
import { syncAuthoritativeClientScope, readAuthoritativeEventId } from '../state/resolveAuthoritativeClientScope';
import { isClientBundleStale, CLIENT_BUNDLE_STALE_MESSAGE } from '../state/buildShaDrift';
import { scopeReady } from '../state/scopeReady';
import {
  fetchEventCurrentOnce,
  fetchEventCurrentWithRetry,
} from '../state/scopeEventCurrent';
import {
  READ_ENDPOINTS,
  MUTATION_ENDPOINTS,
  type ReadEndpoint,
  type MutationEndpoint,
} from './endpoints';
import { buildPathappMutationPayload } from './pathappPayload';
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
  /** Claude author pass on extract-beats/approve can run several minutes. */
  fetchTimeoutMs?: number;
}

interface ApiGetOptions {
  /** Internal — set during READ scope-mismatch auto-heal retry (READ_SCOPE_HEAL_V1). */
  _scopeHealRetry?: boolean;
  /** Internal — cap heal loops so transient restart blips do not stick the red banner. */
  _scopeHealAttempt?: number;
  /** Internal — one retry after server restart blip (NETWORK_RESTART_RETRY_V1). */
  _networkRetry?: boolean;
  /** Optional fetch timeout (e.g. bg_session_state under sidecar lock contention). */
  fetchTimeoutMs?: number;
  /** Internal — one retry after AbortSignal.timeout (SESSION_LOAD_TIMEOUT_RETRY_V1). */
  _timeoutRetry?: boolean;
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
    const fetchInit: RequestInit = {};
    if (opts.fetchTimeoutMs != null && opts.fetchTimeoutMs > 0 && typeof AbortSignal !== 'undefined') {
      fetchInit.signal = AbortSignal.timeout(opts.fetchTimeoutMs);
    }
    const res = await fetch(url.toString(), fetchInit);
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
      const isScope503 = res.status === 503
        && typeof (data as Record<string, unknown> | undefined)?.['error_code'] === 'string'
        && (data as Record<string, unknown>)['error_code'] === 'SCOPE_NOT_READY';
      const attempt = opts._scopeHealAttempt ?? 0;
      if (isScope503 && attempt < 3) {
        await new Promise((resolve) => { setTimeout(resolve, 1000); });
        return apiGet(endpoint, query, {
          ...opts,
          _scopeHealAttempt: attempt + 1,
        });
      }
      const result = parseApiError(res.status, data, res.statusText, {
        // Never flash the persistent banner while READ auto-heal is still retrying.
        suppressScopeDispatch: isScope409 && attempt < 2,
      });
      if (isScopeMismatchResult(result) && attempt < 2) {
        await syncAuthoritativeClientScope(activeScope.value, 'apiGet-pre');
        if (await healServerScopeIfAuthorized(activeScope.value)) {
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
    const timedOut = /timeout|aborted|abort/i.test(err)
      || (e instanceof DOMException && e.name === 'TimeoutError');
    if (!opts._timeoutRetry && timedOut) {
      await new Promise((resolve) => { setTimeout(resolve, 2000); });
      return apiGet(endpoint, query, { ...opts, _timeoutRetry: true });
    }
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
 * Background polls adopt server pin only when URL/explicit pin does not override
 * (SCOPE_POLL_ADOPT_V1 + clientScopeOverridesServerPin).
 */
/** Re-pin server to scope when this tab has URL/explicit pin authority. Exported for poll heal. */
export async function healServerScopeIfAuthorized(scope: Scope): Promise<boolean> {
  const authoritative = readAuthoritativeEventId(scope);

  // SCOPE_CLIENT_AUTHORITY_V1 — dedicated port: URL/port event is truth; sync without event/load.
  if (authoritative && isDedicatedPortForEvent(authoritative)) {
    const portEvent = readDedicatedPortEventId();
    if (portEvent !== authoritative) {
      return false;
    }
    if (await syncAuthoritativeClientScope(scope, 'dedicated-port-heal')) {
      return true;
    }
    return false;
  }

  const urlEvent = readUrlEventId();
  const dedicated = isDedicatedPortForEvent(scope.event_id);
  const useRetry = dedicated || urlEvent === scope.event_id;
  try {
    const current = useRetry
      ? await fetchEventCurrentWithRetry({ forDedicatedPort: dedicated })
      : await fetchEventCurrentOnce();
    if (current?.event_id === scope.event_id) {
      if (typeof current.event_generation === 'number'
        && current.event_generation !== scope.version) {
        activeScope.value = makeScope(
          scope.event_id,
          scope.beat_id,
          current.event_generation,
        );
      }
      return true;
    }
  } catch {
    // Fall through to explicit load when authorized.
  }
  // Dedicated port servers are CLI-pinned — never POST /api/event/load (ping-pong).
  if (isDedicatedPortForEvent(scope.event_id)) {
    return false;
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
  return healServerScopeIfAuthorized(scope);
}

function isScopeMismatchResult<T>(result: ApiResult<T>): boolean {
  return !result.ok && result.error_code === 'SCOPE_MISMATCH';
}

/** Milestone Beat Gen must pin server scope before mutating (MILESTONE_SCOPE_GATE_V1). */
async function ensureServerMilestoneScopeLoaded(scope: Scope): Promise<boolean> {
  const result = await confirmServerMilestoneScope(scope);
  return result.ok;
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
  /** Long Claude/server work (e.g. extract-beats/approve). Default browser idle. */
  fetchTimeoutMs?: number;
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

  // BUILD_SHA_DRIFT_V1 — stale JS after deploy cannot mutate safely.
  if (
    isClientBundleStale()
    && !opts._scopeHealRetry
    && endpoint !== 'event_load'
    && endpoint !== 'state_snapshot'
  ) {
    return {
      ok: false,
      status: 0,
      error: CLIENT_BUNDLE_STALE_MESSAGE,
      error_code: 'CLIENT_BUNDLE_STALE',
      error_message: 'client_bundle_stale',
      retry_safe: true,
      hint: 'Hard refresh the browser tab after a deploy.',
    };
  }

  // SCOPE_CLIENT_AUTHORITY_V1 — align activeScope to URL/dedicated port before snapshot.
  if (
    !opts._scopeHealRetry
    && endpoint !== 'event_load'
    && endpoint !== 'state_snapshot'
  ) {
    await syncAuthoritativeClientScope(scope, 'pathappPatch-pre');
  }
  scope = activeScope.value;

  if (
    !scopeReady.value
    && !opts._scopeHealRetry
    && endpoint !== 'event_load'
    && endpoint !== 'state_snapshot'
  ) {
    return {
      ok: false,
      status: 0,
      error: 'Scope reconcile in progress — wait for server scope to verify.',
      error_code: 'SCOPE_NOT_READY',
      error_message: 'scope_not_ready',
      retry_safe: true,
      hint: 'Wait for scope to finish resolving or reload the page.',
    };
  }

  if (
    shouldInjectMilestoneScope()
    && endpoint !== 'milestone_load'
    && endpoint !== 'event_load'
    && endpoint !== 'state_snapshot'
    && !opts._scopeHealRetry
  ) {
    const milestoneReady = await ensureServerMilestoneScopeLoaded(scope);
    if (!milestoneReady) {
      return {
        ok: false,
        status: 0,
        error: 'Milestone scope not loaded on server — retry in a moment or reload.',
        error_code: 'MILESTONE_SCOPE_REQUIRED',
        error_message: 'milestone_scope_required',
        retry_safe: true,
        hint: 'Server restarted; milestone project is reloading.',
      };
    }
    scope = activeScope.value;
  }

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
    const snapBody: Record<string, unknown> = {
        scope_video_role: effectiveScopeVideoRole(),
        scope_version: scope.version,
    };
    snapBody['event_id'] = scope.event_id;
    snapBody['scope_event_id'] = scope.event_id;
    if (shouldInjectMilestoneScope()) {
      snapBody['scope_milestone_id'] = activeMilestoneId.value || readUrlMilestoneId();
    }
    const snap = await apiPostRaw(
      MUTATION_ENDPOINTS.state_snapshot,
      snapBody,
      'POST',
      { suppressScopeDispatch: !opts._scopeHealRetry },
    );
    if (isScopeMismatchResult(snap)) {
      if (!opts._scopeHealRetry && await healServerScopeIfAuthorized(scope)) {
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
      // SCOPE_SNAPSHOT_FAIL_CLOSED_V1 — never mutate when pre-write snapshot scope fails.
      return {
        ok: false,
        status: snap.status,
        error: snap.error_message ?? snap.error ?? 'scope_mismatch',
        error_code: 'SCOPE_MISMATCH',
        error_message: snap.error_message ?? snap.error ?? 'scope_mismatch',
        retry_safe: snap.retry_safe !== false,
        hint: snap.hint ?? null,
        ...(snap.data === undefined ? {} : { data: snap.data }),
      } as ApiResult<T>;
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

  // LD-461 — scope pin via scope_event_id only (TECH_SPEC_PATHAPP_SCOPE_EVENT_ID_ONLY_V1).
  const scopeVideoRole = effectiveScopeVideoRole();
  const payload = buildPathappMutationPayload(scope, endpoint, body, {
    scopeVideoRole,
    injectMilestoneScope: shouldInjectMilestoneScope(),
    milestoneId: activeMilestoneId.value || readUrlMilestoneId(),
  });

  const rawOpts: RawPostOptions = { suppressScopeDispatch: !opts._scopeHealRetry };
  if (opts.fetchTimeoutMs != null && opts.fetchTimeoutMs > 0) {
    rawOpts.fetchTimeoutMs = opts.fetchTimeoutMs;
  }
  const result = await apiPostRaw<T>(
    MUTATION_ENDPOINTS[endpoint],
    payload,
    method,
    rawOpts,
  );

  // LD-456 — SCOPE_MISMATCH auto-heal (SCOPE_MISMATCH_AUTO_HEAL_V1).
  if (isScopeMismatchResult(result) && !opts._scopeHealRetry) {
    if (await healServerScopeIfAuthorized(scope)) {
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
    const fetchInit: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    };
    if (opts.fetchTimeoutMs && opts.fetchTimeoutMs > 0 && typeof AbortSignal !== 'undefined') {
      fetchInit.signal = AbortSignal.timeout(opts.fetchTimeoutMs);
    }
    const res = await fetch(url, fetchInit);
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

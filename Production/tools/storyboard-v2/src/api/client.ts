// Single mutation channel. Path C architectural commitment per LD
// PATH_C_REWRITE_V1: every state change in the app goes through
// pathappPatch(scope, endpoint, body). Components MUST NOT call fetch()
// directly for mutations.
//
// Why a single channel:
//   1. SCOPE_VALIDATION_V1 — server-side scope guard relies on every
//      mutation request body containing event_id. This client guarantees it.
//   2. M1 — state snapshot before every v59 write (Session 1.5+).
//   3. Audit trail — central place to log mutations (Rule 19 "no error paths").
//   4. Testability — Playwright + scope tests can wrap one function.
//
// Session 1 status: this file SHIPS but pathappPatch has ZERO callers. Read
// helpers (apiGet) are wired up so the LibraryPanel can render Event_1 real
// data. Mutations land in Session 1.5 after the server scope guards.

import type { Scope } from '../state/scope';
import {
  READ_ENDPOINTS,
  MUTATION_ENDPOINTS,
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
// READ — apiGet
// ============================================================================

/**
 * GET helper. Returns ApiResult so callers can check ok/error without
 * try/catch. Used by LibraryPanel + storyboard hydration in Session 1.
 *
 * Read paths do NOT carry a scope token — the server-pinned event_dir
 * already determines the read scope. (Note: LD SCOPE_VALIDATION_V1's notes
 * call out _handle_v2_event_state as accepting event_id in URL but ignoring
 * it; that's a server-side cleanup landed in Session 1.5.)
 */
export async function apiGet<T = unknown>(
  endpoint: ReadEndpoint,
  query: Record<string, string> = {},
): Promise<ApiResult<T>> {
  const url = new URL(READ_ENDPOINTS[endpoint]);
  for (const [k, v] of Object.entries(query)) url.searchParams.set(k, v);

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
// MUTATE — pathappPatch (single mutation channel)
// ============================================================================

export interface PatchOptions {
  /** Skip the M1 pre-write snapshot. Default false (snapshot is always taken). */
  skipSnapshot?: boolean;
  /** Override fetch method (default POST). PATCH used for partial updates. */
  method?: 'POST' | 'PATCH';
}

/**
 * The ONLY mutation entry point. Every component that wants to write state
 * goes through this. The function:
 *
 *   1. Injects scope.{event_id, beat_id, version} into the request body.
 *   2. (Session 1.5+) Calls /api/state/snapshot first per mitigation M1.
 *   3. POSTs the request as JSON to the named endpoint.
 *   4. Returns ApiResult. HTTP 409 on scope mismatch surfaces as ok=false.
 *
 * The server's scope guard (LD SCOPE_VALIDATION_V1) compares
 * body.event_id with self.app.event_dir.name and rejects with HTTP 409 if
 * they disagree. The client will get ok=false with status=409 so the UI
 * can show "scope mismatch — refresh tab and retry" rather than silently
 * corrupting state.
 */
export async function pathappPatch<T = unknown>(
  scope: Scope,
  endpoint: MutationEndpoint,
  body: Record<string, unknown> = {},
  opts: PatchOptions = {},
): Promise<ApiResult<T>> {
  const method = opts.method ?? 'POST';

  // M1 — state snapshot before every v59 write. Session 1.5+ wires the
  // server endpoint; Session 1 short-circuits because mutations don't ship.
  if (!opts.skipSnapshot && endpoint !== 'state_snapshot') {
    // Currently a no-op — uncomment once /api/state/snapshot lands in S1.5:
    //   await apiPostRaw(MUTATION_ENDPOINTS.state_snapshot, { event_id: scope.event_id });
  }

  const payload: Record<string, unknown> = {
    ...body,
    event_id: scope.event_id,
    beat_id: scope.beat_id,
    scope_version: scope.version,
  };

  return apiPostRaw<T>(MUTATION_ENDPOINTS[endpoint], payload, method);
}

/**
 * Internal — raw POST/PATCH used by pathappPatch. NOT exported. Components
 * must NOT call this directly; they go through pathappPatch which guarantees
 * scope injection.
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

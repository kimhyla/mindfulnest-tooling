// Scope token — {event_id, beat_id, version}.
// Path C architectural commitment per LD PATH_C_REWRITE_V1: every state
// mutation carries an explicit scope token. Cross-event mutation is
// structurally impossible because the server enforces SCOPE_VALIDATION_V1
// (HTTP 409 on mismatch).

import { signal, computed } from '@preact/signals';

export interface Scope {
  readonly event_id: string;
  readonly beat_id: string | null;  // null at the event-level; non-null at beat-level
  readonly version: number;          // monotonic; bumped by server on accepted mutations
}

export function makeScope(
  event_id: string,
  beat_id: string | null = null,
  version = 1,
): Scope {
  if (!event_id) throw new Error('Scope: event_id is required');
  return Object.freeze({ event_id, beat_id, version });
}

export function scopeKey(s: Scope): string {
  return `${s.event_id}:${s.beat_id ?? 'global'}:v${s.version}`;
}

export function withBeat(s: Scope, beat_id: string): Scope {
  return makeScope(s.event_id, beat_id, s.version);
}

export function bumpVersion(s: Scope): Scope {
  return makeScope(s.event_id, s.beat_id, s.version + 1);
}

// Active scope — the single source of truth for "what is the current event".
// Initialized to Event_1 at boot; can be reset by ScopeBoundary on mount.
export const activeScope = signal<Scope>(makeScope('Event_1', null, 1));

export const activeEventId = computed(() => activeScope.value.event_id);
export const activeScopeKey = computed(() => scopeKey(activeScope.value));

// Per-scope-keyed signal stores. Each unique scope key gets its own Map of
// signals so signals from Event 1 cannot leak into Event 2 even if a stale
// component reference survives a scope change.
const _scopeStores = new Map<string, Map<string, unknown>>();

export function getScopedStore(s: Scope): Map<string, unknown> {
  const key = scopeKey(s);
  let store = _scopeStores.get(key);
  if (!store) {
    store = new Map();
    _scopeStores.set(key, store);
  }
  return store;
}

export function clearScopedStore(s: Scope): void {
  _scopeStores.delete(scopeKey(s));
}

// Used by tests + ScopeBoundary on hot reload to start clean.
export function _resetAllScopedStoresForTesting(): void {
  _scopeStores.clear();
}

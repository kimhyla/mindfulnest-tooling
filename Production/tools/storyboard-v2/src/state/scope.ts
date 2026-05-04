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

// S5.5b VideoSelector — active video role (UX persistence, NOT partition selector).
// Per LD-474 VIDEO_ROLE_PER_REQUEST_V1: this signal is read by client UI for
// display + by pathappPatch for auto-injecting `scope_video_role` into mutating
// request bodies. Server handlers MUST NOT read state.active_video for partition
// selection — they read body['scope_video_role'] (which pathappPatch sources
// from this signal). Default 'intro' matches the migration destination of v1
// beats per LD-473 BG_VIDEO_PARTITION_V1.
//
// S5.5d (v3 architecture revision, 2026-05-03): RENAMED to `activeTargetVideo`
// per TARGET_VIDEO_SELECTOR_V1 (V3 architecture). Per VIDEO_ROLE_PER_REQUEST_V2
// the canonical roles narrow to {intro, resolution, standalone}; phase_a +
// phase_b are top-level and addressed via dedicated tabs, not video roles.
// `activeVideoRole` retained as alias for transitional compatibility.
export const activeTargetVideo = signal<string>('intro');
export const activeVideoRole = activeTargetVideo;  // alias — same signal

// S5.5d v3 architecture: project-type signal — distinguishes event scope
// (multi-beat with intro+resolution+phase_a+phase_b) from milestone scope
// (standalone single video). Drives ProjectSelector + StitcherTab mode +
// TabBar Phase A/B disable per MILESTONE_STANDALONE_INDEPENDENT_V1.
export const activeProjectType = signal<'event' | 'milestone'>('event');
export const activeMilestoneId = signal<string | null>(null);

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

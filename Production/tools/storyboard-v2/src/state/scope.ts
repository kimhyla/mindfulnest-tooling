// Scope token — {event_id, beat_id, version}.
// Path C architectural commitment per LD PATH_C_REWRITE_V1: every state
// mutation carries an explicit scope token. Cross-event mutation is
// structurally impossible because the server enforces SCOPE_VALIDATION_V1
// (HTTP 409 on mismatch).

import { signal, computed } from '@preact/signals';
import { milestonePartitionDeepLinkAuthorized } from './resolveMilestonePartition.ts';

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

/** Human-readable Beat Gen authority badge (Truth Stack P8). */
export function beatGenAuthorityBadgeLabel(
  eventId: string,
  videoRole: string,
  milestoneId: string | null,
): string {
  const role = videoRole || 'intro';
  if (milestoneId) {
    return `${milestoneId} · ${role} · JSON sidecar`;
  }
  const slug = eventId.replace(/^Event_/i, '').split('_').join('').toLowerCase();
  return `${eventId} · ${role} · SQLite beatgen_${slug}.db`;
}

/** Human-readable scope chip — includes milestone + standalone when in milestone project mode. */
export function producerScopeChipLabel(): string {
  const base = scopeKey(activeScope.value);
  if (activeProjectType.value === 'milestone' && activeMilestoneId.value) {
    return `${base} · milestone:${activeMilestoneId.value} · standalone`;
  }
  return base;
}

/** Normalize URL when entering milestone project mode (drop stale event video=intro). */
export function syncMilestoneUrlParams(milestoneId: string): void {
  if (typeof window === 'undefined') return;
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete('event');
    url.searchParams.set('milestone', milestoneId);
    url.searchParams.set('video', 'standalone');
    window.history.replaceState({}, '', url.toString());
  } catch {
    // headless / restricted contexts
  }
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

const MUTATION_SCOPE_VIDEO_ROLES = new Set(['intro', 'resolution', 'standalone']);

/**
 * Milestones are single-slot standalone — never send event partition roles.
 * Phase A/B tabs use ?video=phase_a|phase_b for navigation only; mutations must
 * not send those as scope_video_role (LD-474 rejects them).
 */
export function effectiveScopeVideoRole(): string {
  if (activeProjectType.value === 'milestone' && activeMilestoneId.value) {
    return 'standalone';
  }
  const role = activeTargetVideo.value;
  if (MUTATION_SCOPE_VIDEO_ROLES.has(role)) {
    return role;
  }
  return 'intro';
}

/** Milestone id from ?milestone= deep link (before milestone_load completes). */
export function readUrlMilestoneId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return new URLSearchParams(window.location.search).get('milestone');
  } catch {
    return null;
  }
}

/**
 * Milestone scope keys belong on mutations/GETs when the tab is in milestone
 * project mode, OR on Event_N dedicated ports with an intentional ?milestone=
 * deep link (stitch partition APIs — no server milestone_load).
 * MILESTONE_PARTITION_RESOLVER_V1 — uses milestonePartitionDeepLinkAuthorized,
 * NOT readAuthoritativeEventId / port-inference alone.
 */
export function isDedicatedPortMilestoneDeepLink(): boolean {
  if (typeof window === 'undefined') return false;
  const port = parseInt(window.location.port || '0', 10);
  const urlEventId = new URLSearchParams(window.location.search).get('event');
  return milestonePartitionDeepLinkAuthorized({
    milestoneId: readUrlMilestoneId(),
    urlEventId,
    activeScopeEventId: activeScope.value.event_id,
    port,
  });
}

export const DEDICATED_PORT_MILESTONE_LAYOUT_V1 = 'DEDICATED_PORT_MILESTONE_LAYOUT_V1';

/** Client milestone layout on Event_N dedicated port — no server milestone_load. */
export function adoptDedicatedPortMilestoneLayout(milestoneId: string): void {
  activeProjectType.value = 'milestone';
  activeMilestoneId.value = milestoneId;
  persistActiveMilestoneId(milestoneId);
  activeVideoRole.value = 'standalone';
  activeTargetVideo.value = 'standalone';
  if (typeof document !== 'undefined') {
    document.body.setAttribute('data-active-project-type', 'milestone');
    document.body.setAttribute('data-dedicated-port-milestone-layout', DEDICATED_PORT_MILESTONE_LAYOUT_V1);
  }
}

export function shouldInjectMilestoneScope(): boolean {
  const mid = activeMilestoneId.value || readUrlMilestoneId();
  if (!mid) return false;
  if (activeProjectType.value === 'milestone') return true;
  return isDedicatedPortMilestoneDeepLink();
}

/** Remove stale ?milestone= when this tab is pinned to a dedicated event port. */
export function stripStaleMilestoneUrlForDedicatedEvent(eventId: string): void {
  if (typeof window === 'undefined') return;
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('milestone')) return;
    url.searchParams.delete('milestone');
    url.searchParams.set('event', eventId);
    window.history.replaceState({}, '', url.toString());
  } catch {
    // headless / restricted contexts
  }
}

/** sessionStorage key — survives server restart so milestone project can reload. */
export const ACTIVE_MILESTONE_STORAGE_KEY = 'mn_active_milestone_id';

export function persistActiveMilestoneId(milestoneId: string | null): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    if (milestoneId) sessionStorage.setItem(ACTIVE_MILESTONE_STORAGE_KEY, milestoneId);
    else sessionStorage.removeItem(ACTIVE_MILESTONE_STORAGE_KEY);
  } catch {
    // private mode / headless
  }
}

export function readPersistedMilestoneId(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(ACTIVE_MILESTONE_STORAGE_KEY);
    return raw?.trim() ? raw.trim() : null;
  } catch {
    return null;
  }
}

/** Query params every scoped GET should carry (library event + optional milestone). */
export function activeScopeQueryParams(): Record<string, string> {
  const videoRole = effectiveScopeVideoRole();
  const out: Record<string, string> = {
    scope_video_role: videoRole,
    scope_target_video: videoRole,
    scope_event_id: activeScope.value.event_id,
  };
  if (shouldInjectMilestoneScope()) {
    out['scope_milestone_id'] = activeMilestoneId.value || readUrlMilestoneId() || '';
  }
  return out;
}

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

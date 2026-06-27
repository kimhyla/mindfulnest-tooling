// SCOPE_CLIENT_AUTHORITY_V1 — single resolver before mutations (see SCOPE_CLIENT_AUTHORITY_SPEC_v1.md).

import type { Scope } from './scope';
import { activeScope, makeScope } from './scope';
import {
  isDedicatedPortForEvent,
  noteClientPinnedEvent,
  readDedicatedPortEventId,
  readUrlEventId,
} from './scopeAuthority';
import { resolveAuthoritativeEventIdFromParts } from './scopeAuthorityResolve';
import { fetchEventCurrentWithRetry } from './scopeEventCurrent';

export const SCOPE_HEALED_EVENT = 'mn:scope-healed';

function emitScopeHealedLocal(detail: Record<string, unknown>): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(SCOPE_HEALED_EVENT, { detail }));
  }
}

/** URL ?event= wins; else dedicated port Event_N; else activeScope. */
export function readAuthoritativeEventId(fallbackScope?: Scope): string {
  return resolveAuthoritativeEventIdFromParts(
    readUrlEventId(),
    readDedicatedPortEventId(),
    fallbackScope?.event_id ?? activeScope.value.event_id,
  );
}

/**
 * On dedicated port, sync activeScope to URL/port authoritative event when server agrees.
 * Does not call event/load (ping-pong safe). Returns true when scope is aligned for mutate.
 */
export async function syncAuthoritativeClientScope(
  hint?: Scope,
  source = 'scope-authority-sync',
): Promise<boolean> {
  const authoritative = readAuthoritativeEventId(hint);
  if (!authoritative || !isDedicatedPortForEvent(authoritative)) {
    return activeScope.value.event_id === (hint?.event_id ?? activeScope.value.event_id);
  }

  const current = await fetchEventCurrentWithRetry({ forDedicatedPort: true });
  if (!current?.event_id || current.event_id !== authoritative) {
    return false;
  }

  const generation = typeof current.event_generation === 'number'
    ? current.event_generation
    : (hint?.version ?? activeScope.value.version);
  const beatId = hint?.beat_id ?? activeScope.value.beat_id;

  if (
    activeScope.value.event_id !== authoritative
    || activeScope.value.version !== generation
  ) {
    activeScope.value = makeScope(authoritative, beatId, generation);
    noteClientPinnedEvent(authoritative);
    emitScopeHealedLocal({ event_id: authoritative, source });
  }
  return true;
}

/** Scope for mutations — always activeScope after optional dedicated-port sync. */
export function mutationScopeFromActive(hint?: Scope): Scope {
  if (hint && hint.event_id === activeScope.value.event_id) {
    return activeScope.value;
  }
  return activeScope.value.event_id ? activeScope.value : hint ?? activeScope.value;
}

// SCOPE_RESTART_RECONCILE_V1 — shared boot + post-restart scope pin/verify.
// ScopeBoundary and ServerRehydrateWatcher both call reconcileClientScope so
// server down→up re-runs the same authority as first page load.

import {
  loadEvent,
  emitScopeEventChanged,
  emitScopeHealed,
  ensureServerPinnedTo,
  noteClientPinnedEvent,
} from '../api/client';
import { resetScopeMismatchDedupe } from '../api/errorBoundary';
import {
  isDedicatedPortForEvent,
  dedicatedPortBookmarkUrl,
  readUrlEventId,
  readDedicatedPortEventId,
} from './scopeAuthority';
import { readAuthoritativeEventId } from './resolveAuthoritativeClientScope';
import {
  activeScope,
  activeVideoRole,
  activeTargetVideo,
  activeProjectType,
  activeMilestoneId,
  makeScope,
  persistActiveMilestoneId,
  readPersistedMilestoneId,
  readUrlMilestoneId,
  scopeKey,
  syncMilestoneUrlParams,
  adoptDedicatedPortMilestoneLayout,
  isDedicatedPortMilestoneDeepLink,
} from './scope';
import { confirmServerMilestoneScope } from './milestoneScopeGate';
import { setScopeReady } from './scopeReady';
import {
  fetchEventCurrentOnce,
  fetchEventCurrentWithRetry,
} from './scopeEventCurrent';

export type { EventCurrentResponse } from './scopeEventCurrent';
export { EVENT_CURRENT_RETRY_DELAYS_MS, fetchEventCurrentOnce, fetchEventCurrentWithRetry } from './scopeEventCurrent';

function resolveLocalFallbackWithoutUrl(): string {
  const fromBody = document.body.getAttribute('data-event-id');
  if (fromBody) return fromBody;
  if (typeof window !== 'undefined' && window.__MN_EVENT_ID__) {
    return window.__MN_EVENT_ID__;
  }
  return 'Event_1';
}

export interface ReconcileResult {
  ok: boolean;
  pinError?: string;
  targetEventId?: string | undefined;
}

export interface ReconcileOptions {
  source: string;
  /** Test hook — skip URL/dedicated-port wrong-port guard. */
  forceEventId?: string;
}

/**
 * Pin + verify server scope (URL authority, dedicated port, or event/load).
 * Sets activeScope signals on success; does not set scopeReady (caller owns gate).
 */
export async function reconcileClientScope(
  opts: ReconcileOptions,
): Promise<ReconcileResult> {
  const urlEventId = opts.forceEventId ? null : readUrlEventId();
  const forcedId = opts.forceEventId ?? null;

  if (urlEventId && !forcedId) {
    const bookmark = dedicatedPortBookmarkUrl(urlEventId);
    if (bookmark) {
      document.body.setAttribute('data-scope-pin-failed', urlEventId);
      document.body.setAttribute('data-scope-correct-url', bookmark);
      return {
        ok: false,
        pinError: `Wrong port — use ${bookmark} for this event (then close this tab).`,
        targetEventId: urlEventId,
      };
    }
  }

  const useDedicatedRetry = Boolean(
    urlEventId && isDedicatedPortForEvent(urlEventId),
  );
  const current = await fetchEventCurrentWithRetry({ forDedicatedPort: useDedicatedRetry });
  if (current === null && useDedicatedRetry) {
    return {
      ok: false,
      pinError: `Server not ready for ${urlEventId ?? 'event'} — wait a moment and reload.`,
      targetEventId: urlEventId ?? undefined,
    };
  }

  let serverEventId = (
    current && typeof current.event_id === 'string' && current.event_id
  ) ? current.event_id : null;
  let resolvedGeneration = (
    typeof current?.event_generation === 'number'
  ) ? current.event_generation : 1;
  let serverActiveVideo = current?.active_video ?? null;
  let serverScopeType = current?.scope_type;
  let serverMilestoneId = current?.active_milestone_id;

  const dedicatedPortEventId = readDedicatedPortEventId();
  const fallbackScope = makeScope(
    serverEventId ?? resolveLocalFallbackWithoutUrl(),
    null,
    resolvedGeneration,
  );
  let targetEventId = forcedId ?? readAuthoritativeEventId(fallbackScope);

  // DEDICATED_PORT vs server truth — port 5111 implies Event_1, but Playwright
  // and mis-pinned dev tabs may serve Event_e2e_fixture (or another event) on
  // that port. When ?event= is absent, /api/event/current wins over port math.
  if (
    !forcedId
    && !urlEventId
    && dedicatedPortEventId
    && serverEventId
    && serverEventId !== dedicatedPortEventId
  ) {
    targetEventId = serverEventId;
  }

  const syncDedicatedPortPin = async (eventId: string): Promise<boolean> => {
    if (serverEventId === eventId) {
      noteClientPinnedEvent(eventId);
      return true;
    }
    const retryCurrent = await fetchEventCurrentWithRetry({ forDedicatedPort: true });
    if (retryCurrent?.event_id === eventId) {
      serverEventId = retryCurrent.event_id;
      if (typeof retryCurrent.event_generation === 'number') {
        resolvedGeneration = retryCurrent.event_generation;
      }
      serverActiveVideo = retryCurrent.active_video ?? null;
      serverScopeType = retryCurrent.scope_type;
      serverMilestoneId = retryCurrent.active_milestone_id;
      noteClientPinnedEvent(eventId);
      return true;
    }
    return false;
  };

  const pinTarget = async (eventId: string): Promise<boolean> => {
    // DEDICATED_PORT_SCOPE_TRUTH_V1 — never POST /api/event/load on 5110+N tabs
    // unless ?event= explicitly selects a non-port event (e2e fixture, etc.).
    if (dedicatedPortEventId && !urlEventId) {
      if (eventId === dedicatedPortEventId) {
        return syncDedicatedPortPin(dedicatedPortEventId);
      }
      if (serverEventId === eventId) {
        noteClientPinnedEvent(eventId);
        return true;
      }
      return false;
    }
    if (urlEventId && isDedicatedPortForEvent(urlEventId)) {
      if (eventId !== urlEventId) {
        return false;
      }
      return syncDedicatedPortPin(urlEventId);
    }
    if (serverEventId === eventId) {
      return ensureServerPinnedTo(eventId);
    }
    const loadRes = urlEventId
      ? await loadEvent(urlEventId)
      : await loadEvent(eventId);
    if (!loadRes.ok || !loadRes.data?.event_id) {
      return false;
    }
    serverEventId = loadRes.data.event_id;
    resolvedGeneration = loadRes.data.event_generation;
    noteClientPinnedEvent(loadRes.data.event_id);
    emitScopeEventChanged({
      event_id: loadRes.data.event_id,
      event_generation: loadRes.data.event_generation,
      scope_key: scopeKey(makeScope(loadRes.data.event_id, null, loadRes.data.event_generation)),
      source: urlEventId ? 'scope-boundary-url-bootstrap' : 'scope-reconcile-pin',
    });
    const refreshed = await fetchEventCurrentOnce();
    if (refreshed) {
      serverActiveVideo = refreshed.active_video ?? null;
      serverScopeType = refreshed.scope_type;
      serverMilestoneId = refreshed.active_milestone_id;
      if (typeof refreshed.event_generation === 'number') {
        resolvedGeneration = refreshed.event_generation;
      }
    }
    return ensureServerPinnedTo(eventId);
  };

  let pinOk = await pinTarget(targetEventId);
  if (!pinOk && urlEventId) {
    pinOk = await pinTarget(urlEventId);
    targetEventId = urlEventId;
  }

  if (!pinOk && !urlEventId && serverEventId && !dedicatedPortEventId) {
    targetEventId = serverEventId;
    pinOk = await ensureServerPinnedTo(targetEventId);
  }

  if (!pinOk) {
    const msg = urlEventId
      ? `Could not pin server to ${urlEventId}. Hard-refresh or pick the event again from the Project menu.`
      : dedicatedPortEventId
        ? `Could not confirm ${dedicatedPortEventId} on port ${window.location.port || '5110+N'}. Restart the dedicated server and reload.`
        : `Could not confirm server scope for ${targetEventId}. Hard-refresh and try again.`;
    if (urlEventId) {
      document.body.setAttribute('data-scope-pin-failed', urlEventId);
    }
    return { ok: false, pinError: msg, targetEventId };
  }

  activeScope.value = makeScope(targetEventId, null, resolvedGeneration);

  const urlMilestoneId = readUrlMilestoneId();
  if (pinOk && urlMilestoneId) {
    const confirmed = await confirmServerMilestoneScope(
      makeScope(targetEventId, null, resolvedGeneration),
      { forDedicatedPort: isDedicatedPortForEvent(targetEventId) },
    );
    if (confirmed.ok) {
      const refreshed = await fetchEventCurrentOnce();
      if (refreshed) {
        serverScopeType = refreshed.scope_type;
        serverMilestoneId = refreshed.active_milestone_id ?? null;
        serverActiveVideo = refreshed.active_video ?? null;
        if (typeof refreshed.event_generation === 'number') {
          resolvedGeneration = refreshed.event_generation;
          activeScope.value = makeScope(targetEventId, null, resolvedGeneration);
        }
      }
    }
  }

  const isMilestoneScope = serverScopeType === 'milestone'
    && typeof serverMilestoneId === 'string'
    && Boolean(serverMilestoneId);
  // MILESTONE_PARTITION_RESOLVER_V1 — not readAuthoritativeEventId + isDedicatedPortForEvent
  const dedicatedMilestoneLayout = isDedicatedPortMilestoneDeepLink();

  if (isMilestoneScope) {
    activeProjectType.value = 'milestone';
    activeMilestoneId.value = serverMilestoneId as string;
    persistActiveMilestoneId(serverMilestoneId as string);
    document.body.setAttribute('data-active-project-type', 'milestone');
    activeVideoRole.value = 'standalone';
    activeTargetVideo.value = 'standalone';
    syncMilestoneUrlParams(serverMilestoneId as string);
  } else if (dedicatedMilestoneLayout && urlMilestoneId) {
    adoptDedicatedPortMilestoneLayout(urlMilestoneId);
  } else {
    activeProjectType.value = 'event';
    activeMilestoneId.value = null;
    persistActiveMilestoneId(null);
    document.body.setAttribute('data-active-project-type', 'event');
    if (serverActiveVideo && typeof serverActiveVideo === 'string') {
      activeVideoRole.value = serverActiveVideo;
    }
  }
  document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
  document.body.removeAttribute('data-scope-pin-failed');
  noteClientPinnedEvent(targetEventId);
  emitScopeHealed({ event_id: targetEventId, source: opts.source });
  return { ok: true, targetEventId };
}

async function restoreMilestoneScopeAfterRestart(priorMilestoneId: string | null): Promise<boolean> {
  if (!priorMilestoneId) return true;
  activeMilestoneId.value = priorMilestoneId;
  activeProjectType.value = 'milestone';
  const confirmed = await confirmServerMilestoneScope(activeScope.value);
  if (!confirmed.ok) {
    // eslint-disable-next-line no-console
    console.warn(
      '[scope-reconcile] milestone reload after restart failed:',
      confirmed.lastError,
    );
    return false;
  }
  try {
    syncMilestoneUrlParams(priorMilestoneId);
  } catch {
    // headless
  }
  return true;
}

/** Server down→up: block mutations, re-pin, clear deduped scope errors. */
export async function reconcileScopeAfterRestart(reason: string): Promise<boolean> {
  const priorMilestoneId = (
    activeProjectType.value === 'milestone'
      ? (activeMilestoneId.value || readUrlMilestoneId() || readPersistedMilestoneId())
      : readPersistedMilestoneId()
  );
  setScopeReady(false, `reconcile-start:${reason}`);
  const result = await reconcileClientScope({ source: `server-rehydrate:${reason}` });
  if (result.ok) {
    if (priorMilestoneId) {
      const restored = await restoreMilestoneScopeAfterRestart(priorMilestoneId);
      if (!restored) {
        setScopeReady(false, `reconcile-milestone-fail:${reason}`);
        return false;
      }
    }
    resetScopeMismatchDedupe();
    setScopeReady(true, `reconcile-ok:${reason}`);
    emitScopeHealed({ event_id: activeScope.value.event_id, source: reason });
    return true;
  }
  setScopeReady(false, `reconcile-fail:${reason}`);
  return false;
}

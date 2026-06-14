// Server rehydrate — after production_server restart/deploy, tabs re-fetch state.
// Polls /api/event/current; on unreachable→OK transition bumps serverRehydrateTick
// so Phase A/B, Stitcher, Storyboard, LibraryPanel refresh without a manual reload.

import { READ_ENDPOINTS } from '../api/endpoints';
import { emitScopeEventChanged, loadEvent } from '../api/client';
import { activeScope, makeScope } from './scope';
import { serverRehydrateTick, stitcherRefreshTick } from './refreshSignals';

export const SERVER_REHYDRATE_EVENT = 'mn:server-rehydrate';

export interface ServerProbeResult {
  ok: boolean;
  status: number;
  eventId?: string;
  eventGeneration?: number;
}

/** Lightweight health probe — does not mutate. */
export async function probeProductionServer(): Promise<ServerProbeResult> {
  try {
    const res = await fetch(READ_ENDPOINTS.event_current, { cache: 'no-store' });
    if (!res.ok) {
      return { ok: false, status: res.status };
    }
    const data = (await res.json()) as {
      event_id?: string;
      event_generation?: number;
    };
    const result: ServerProbeResult = { ok: true, status: res.status };
    if (typeof data.event_id === 'string') {
      result.eventId = data.event_id;
    }
    if (typeof data.event_generation === 'number') {
      result.eventGeneration = data.event_generation;
    }
    return result;
  } catch {
    return { ok: false, status: 0 };
  }
}

/** Bump cross-tab refresh signals after server comes back or deploy completes. */
export function triggerServerRehydrate(reason: string): void {
  serverRehydrateTick.value += 1;
  stitcherRefreshTick.value += 1;
  emitScopeEventChanged({ phase: 'server-rehydrate', reason });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(SERVER_REHYDRATE_EVENT, { detail: { reason } }),
    );
  }
}

/** Sync activeScope version from server when event_id matches; re-pin server after restart drift. */
export async function syncScopeFromProbe(probe: ServerProbeResult): Promise<void> {
  if (!probe.ok || !probe.eventId) return;
  const cur = activeScope.value;
  if (probe.eventId !== cur.event_id) {
    // Server restart / deploy defaults to Event_1 while tab stays on Event_2.
    // Re-pin to the client's active event (same policy as pathappPatch heal).
    const load = await loadEvent(cur.event_id);
    if (load.ok && load.data?.event_id) {
      activeScope.value = makeScope(
        load.data.event_id,
        cur.beat_id,
        load.data.event_generation,
      );
      emitScopeEventChanged({
        event_id: load.data.event_id,
        event_generation: load.data.event_generation,
        source: 'server-rehydrate-scope-heal',
      });
    }
    return;
  }
  const gen = probe.eventGeneration ?? cur.version;
  if (gen !== cur.version) {
    activeScope.value = makeScope(probe.eventId, cur.beat_id, gen);
  }
}

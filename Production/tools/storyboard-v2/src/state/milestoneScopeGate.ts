// MILESTONE_SCOPE_GATE_V1 — server milestone pin before milestone mutations.
// Category: client assumed milestone project mode while /api/event/current was
// transient (503) or app.scope_type drifted after restart — prompt autosave failed
// before Generate with MILESTONE_SCOPE_REQUIRED.

import { MUTATION_ENDPOINTS } from '../api/endpoints';
import type { Scope } from './scope';
import {
  activeMilestoneId,
  activeProjectType,
  activeScope,
  activeTargetVideo,
  activeVideoRole,
  makeScope,
  persistActiveMilestoneId,
  readPersistedMilestoneId,
  readUrlMilestoneId,
  shouldInjectMilestoneScope,
  syncMilestoneUrlParams,
  isDedicatedPortMilestoneDeepLink,
  adoptDedicatedPortMilestoneLayout,
} from './scope';
import {
  delayBeforeBgSessionRetry,
  isTransientSessionFetchError,
} from '../utils/sessionFetchRetry';
import {
  fetchEventCurrentOnce,
  fetchEventCurrentWithRetry,
  type EventCurrentResponse,
} from './scopeEventCurrent';
import { isDedicatedPortForEvent } from './scopeAuthority';

export const MILESTONE_SCOPE_GATE_V1 = 'MILESTONE_SCOPE_GATE_V1';

/** Max attempts for milestone_load after event/current miss (~10s with backoff). */
export const MILESTONE_SCOPE_CONFIRM_MAX_ATTEMPTS =
  6 satisfies number;

export interface MilestoneScopeConfirmResult {
  ok: boolean;
  milestoneId: string | null;
  lastError: string;
}

function resolveMilestoneId(): string | null {
  return activeMilestoneId.value || readUrlMilestoneId() || readPersistedMilestoneId();
}

function serverHasMilestone(current: EventCurrentResponse | null, mid: string): boolean {
  return (
    current?.scope_type === 'milestone'
    && String(current.active_milestone_id ?? '') === mid
  );
}

async function postMilestoneLoad(
  scope: Scope,
  mid: string,
): Promise<{ ok: boolean; eventGeneration?: number; error?: string }> {
  try {
    const res = await fetch(MUTATION_ENDPOINTS.milestone_load, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        milestone_id: mid,
        scope_event_id: scope.event_id,
        scope_video_role: 'standalone',
        scope_target_video: 'standalone',
      }),
    });
    let data: { ok?: boolean; event_generation?: number; error_message?: string; error?: string } | undefined;
    try {
      data = (await res.json()) as typeof data;
    } catch {
      // empty body
    }
    if (!res.ok) {
      const msg = data?.error_message ?? data?.error ?? `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    if (!data?.ok) {
      return { ok: false, error: data?.error_message ?? data?.error ?? 'milestone_load not ok' };
    }
    return {
      ok: true,
      ...(typeof data.event_generation === 'number'
        ? { eventGeneration: data.event_generation }
        : {}),
    };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

function applyMilestoneClientSignals(mid: string, eventGeneration?: number, scope?: Scope): void {
  activeProjectType.value = 'milestone';
  activeMilestoneId.value = mid;
  persistActiveMilestoneId(mid);
  activeVideoRole.value = 'standalone';
  activeTargetVideo.value = 'standalone';
  if (typeof document !== 'undefined') {
    document.body.setAttribute('data-active-project-type', 'milestone');
  }
  syncMilestoneUrlParams(mid);
  if (typeof eventGeneration === 'number' && scope) {
    activeScope.value = makeScope(scope.event_id, null, eventGeneration);
  }
}

/** Apply server milestone pin signals on the client after successful load. */
export function adoptMilestoneScopeClientState(
  mid: string,
  scope: Scope,
  eventGeneration?: number,
): void {
  applyMilestoneClientSignals(mid, eventGeneration, scope);
}

/**
 * Confirm app.scope_type=milestone + active_milestone_id on server before
 * milestone Beat Gen mutations (prompt autosave, Generate, etc.).
 */
export async function confirmServerMilestoneScope(
  scope: Scope,
  opts: { forDedicatedPort?: boolean; maxAttempts?: number } = {},
): Promise<MilestoneScopeConfirmResult> {
  const mid = resolveMilestoneId();
  if (!mid) {
    return { ok: false, milestoneId: null, lastError: 'milestone_id missing on client' };
  }

  const dedicated = opts.forDedicatedPort ?? isDedicatedPortForEvent(scope.event_id);

  // DEDICATED_PORT_MILESTONE_LAYOUT_V1 — stitch/milestone UI on Event_N servers;
  // never POST milestone/load (activates BG sidecar isolation on pinned event).
  if (dedicated && (isDedicatedPortMilestoneDeepLink() || shouldInjectMilestoneScope())) {
    adoptDedicatedPortMilestoneLayout(mid);
    return { ok: true, milestoneId: mid, lastError: '' };
  }

  if (!shouldInjectMilestoneScope()) {
    return { ok: true, milestoneId: null, lastError: '' };
  }

  const maxAttempts = opts.maxAttempts ?? MILESTONE_SCOPE_CONFIRM_MAX_ATTEMPTS;
  let lastError = 'milestone scope not confirmed';

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) {
      await delayBeforeBgSessionRetry(attempt);
    }

    const current = dedicated
      ? await fetchEventCurrentWithRetry({ forDedicatedPort: true })
      : await fetchEventCurrentOnce();

    if (serverHasMilestone(current, mid)) {
      adoptMilestoneScopeClientState(mid, scope, current?.event_generation);
      return { ok: true, milestoneId: mid, lastError: '' };
    }

    const load = await postMilestoneLoad(scope, mid);
    if (load.ok) {
      adoptMilestoneScopeClientState(mid, scope, load.eventGeneration);
      return { ok: true, milestoneId: mid, lastError: '' };
    }

    lastError = load.error ?? lastError;
    if (!isTransientSessionFetchError(lastError) && !/503|scope_not_ready|drain_in_progress/i.test(lastError)) {
      break;
    }
  }

  return { ok: false, milestoneId: mid, lastError };
}

// Milestone scope pin — raw POST in src/api/ (not pathappPatch) to break the
// confirmServerMilestoneScope ↔ pathappPatch recursion (milestone_load is
// excluded from pathappPatch's pre-gate but still routes through ensureServerMilestoneScopeLoaded).

import { MUTATION_ENDPOINTS } from './endpoints';
import type { Scope } from '../state/scope';

export interface MilestoneLoadResult {
  ok: boolean;
  eventGeneration?: number;
  error?: string;
}

/** POST /api/milestones/load — server milestone pin without pathappPatch snapshot/gate. */
export async function loadMilestone(
  scope: Scope,
  milestoneId: string,
): Promise<MilestoneLoadResult> {
  try {
    const res = await fetch(MUTATION_ENDPOINTS.milestone_load, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        milestone_id: milestoneId,
        scope_event_id: scope.event_id,
        scope_video_role: 'standalone',
        scope_target_video: 'standalone',
        scope_version: scope.version,
        beat_id: scope.beat_id,
      }),
    });
    let data: {
      ok?: boolean;
      event_generation?: number;
      error_message?: string;
      error?: string;
    } | undefined;
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

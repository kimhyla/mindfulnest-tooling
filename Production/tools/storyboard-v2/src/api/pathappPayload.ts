// LD-461 category fix — pathappPatch scope injection contract.
// Scope pin is ALWAYS scope_event_id. body.event_id is caller-owned domain data.

import type { MutationEndpoint } from './endpoints';
import type { Scope } from '../state/scope';

export interface PathappPayloadOptions {
  scopeVideoRole: string;
  milestoneId?: string | null;
  injectMilestoneScope: boolean;
}

/**
 * Build the wire JSON for pathappPatch mutations (excluding snapshot-only fields).
 * Never auto-injects top-level event_id — prevents clobbering create/provision/BG segment keys.
 */
export function buildPathappMutationPayload(
  scope: Scope,
  _endpoint: MutationEndpoint,
  body: Record<string, unknown>,
  opts: PathappPayloadOptions,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    scope_video_role: opts.scopeVideoRole,
    scope_target_video: opts.scopeVideoRole,
    beat_id: scope.beat_id,
    ...body,
    scope_version: scope.version,
    scope_event_id: scope.event_id,
  };
  if (opts.injectMilestoneScope && opts.milestoneId) {
    payload['scope_milestone_id'] = opts.milestoneId;
  }
  return payload;
}

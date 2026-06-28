// MILESTONE_PARTITION_RESOLVER_V1 — milestone stitch partition gate (NOT event authority).
// See Production/docs/TECH_SPEC_MILESTONE_PARTITION_RESOLVER_V1.md
//
// Zero-dep pure module for Node unit tests (no scope signals, no scopeAuthority imports).

export const MILESTONE_PARTITION_RESOLVER_V1 = 'MILESTONE_PARTITION_RESOLVER_V1';

export interface MilestonePartitionDeepLinkInput {
  milestoneId: string | null;
  urlEventId: string | null;
  activeScopeEventId: string;
  port: number;
}

/** Matches Production/scripts/event_server_port.sh event_id_to_port. */
export function eventIdMatchesDedicatedPort(eventId: string, port: number): boolean {
  const m = /^Event_(\d+)$/.exec(eventId.trim());
  if (!m) return false;
  const expectedPort = 5110 + parseInt(m[1]!, 10);
  return port === expectedPort;
}

/**
 * Authorize client milestone partition deep link (scope_milestone_id injection,
 * DEDICATED_PORT_MILESTONE_LAYOUT_V1). Precedence differs from readAuthoritativeEventId:
 * never use port-inferred Event_N alone — require URL ?event= or activeScope match.
 */
export function milestonePartitionDeepLinkAuthorized(
  input: MilestonePartitionDeepLinkInput,
): boolean {
  const mid = input.milestoneId?.trim();
  if (!mid) return false;

  const { urlEventId, activeScopeEventId, port } = input;

  if (urlEventId && eventIdMatchesDedicatedPort(urlEventId, port)) {
    return true;
  }

  if (
    activeScopeEventId
    && eventIdMatchesDedicatedPort(activeScopeEventId, port)
    && (!urlEventId || urlEventId === activeScopeEventId)
  ) {
    return true;
  }

  return false;
}

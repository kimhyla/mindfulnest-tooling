// SCOPE_CLIENT_AUTHORITY_V1 — zero-dep pure helpers for resolver + Node unit tests.
// See expectFieldGate.ts for the same pattern (no state/DOM imports).

/** Matches Production/scripts/event_server_port.sh port_to_event_id. */
export function dedicatedPortEventIdFromPort(port: number): string | null {
  if (!Number.isFinite(port) || port < 5111) return null;
  const n = port - 5110;
  if (n < 1) return null;
  return `Event_${n}`;
}

/** URL ?event= wins; else dedicated port Event_N; else fallback activeScope event. */
export function resolveAuthoritativeEventIdFromParts(
  urlEvent: string | null,
  portEvent: string | null,
  fallbackEventId: string,
): string {
  if (urlEvent) return urlEvent;
  if (portEvent) return portEvent;
  return fallbackEventId;
}

/** EVENT_DEDICATED_PORT_V1 — Event_N → 5110+N. Zero-dep twin of scopeAuthority.eventIdToDedicatedPort. */
export function eventIdToDedicatedPortNumber(eventId: string): number | null {
  const m = /^Event_(\d+)$/.exec(eventId.trim());
  if (!m) return null;
  return 5110 + parseInt(m[1]!, 10);
}

export interface DedicatedPortEventUrlParams {
  eventId: string;
  tab?: string | null;
  video?: string | null;
  milestone?: string | null;
}

/**
 * PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1 — bookmark URL for Event_N on localhost:(5110+N).
 * Returns null when eventId is not Event_<digits>.
 */
export function buildDedicatedPortEventUrl(params: DedicatedPortEventUrlParams): string | null {
  const port = eventIdToDedicatedPortNumber(params.eventId);
  if (port == null) return null;
  const url = new URL(`http://localhost:${port}/`);
  url.searchParams.set('event', params.eventId);
  if (params.tab) url.searchParams.set('tab', params.tab);
  if (params.video) url.searchParams.set('video', params.video);
  if (params.milestone) url.searchParams.set('milestone', params.milestone);
  return url.toString();
}

export type EventSwitchMode = 'load' | 'navigate';

/**
 * Dedicated-port event switch: cross-port → navigate (never event/load).
 * Same port or non-Event_N → load via POST /api/event/load.
 */
export function resolveEventSwitchMode(
  targetEventId: string,
  currentPort: number,
): EventSwitchMode {
  const targetPort = eventIdToDedicatedPortNumber(targetEventId);
  if (targetPort == null || currentPort < 5111) return 'load';
  if (currentPort !== targetPort) return 'navigate';
  return 'load';
}

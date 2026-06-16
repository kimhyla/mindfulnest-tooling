// SCOPE_PIN_AUTHORITY_V1 — which client contexts may POST /api/event/load to
// re-pin the server. Background polls must NOT fight other tabs; only URL-deep-
// link or explicit user pin (ScopeBoundary / Project selector) may heal on 409.

/** Last event_id this tab intentionally pinned via ScopeBoundary or Project menu. */
let explicitClientEventId: string | null = null;

export function readUrlEventId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return new URLSearchParams(window.location.search).get('event');
  } catch {
    return null;
  }
}

/** Record that this tab owns server pin for eventId (after successful event/load). */
export function noteClientPinnedEvent(eventId: string): void {
  explicitClientEventId = eventId;
}

/** True when this tab may call loadEvent(eventId) to heal scope on 409 mutations. */
export function clientMayPinServerTo(eventId: string): boolean {
  const urlEvent = readUrlEventId();
  if (urlEvent) return urlEvent === eventId;
  return explicitClientEventId === eventId;
}

/**
 * True when background scope poll must NOT adopt the server's event pin.
 * URL ?event= and explicit ScopeBoundary pins beat stale server defaults (Event_1).
 */
export function clientScopeOverridesServerPin(serverEventId: string): boolean {
  const urlEvent = readUrlEventId();
  if (urlEvent) return urlEvent !== serverEventId;
  if (explicitClientEventId) return explicitClientEventId !== serverEventId;
  return false;
}

/** EVENT_DEDICATED_PORT_V1 — Event_N → localhost:(5110+N). Always on (2026-06). */
export function eventIdToDedicatedPort(eventId: string): number | null {
  const m = /^Event_(\d+)$/.exec(eventId.trim());
  if (!m) return null;
  return 5110 + parseInt(m[1]!, 10);
}

/** True when this tab's origin port is the dedicated port for eventId. */
export function isDedicatedPortForEvent(eventId: string): boolean {
  if (typeof window === 'undefined') return false;
  const expected = eventIdToDedicatedPort(eventId);
  if (expected == null) return false;
  const port = parseInt(window.location.port || '80', 10);
  return port === expected;
}

/** When ?event= is on the wrong port, return the bookmark URL the tab should use. */
export function dedicatedPortBookmarkUrl(eventId: string): string | null {
  if (typeof window === 'undefined') return null;
  const expected = eventIdToDedicatedPort(eventId);
  if (expected == null) return null;
  const port = parseInt(window.location.port || '80', 10);
  if (port === expected) return null;
  return `http://localhost:${expected}/?event=${encodeURIComponent(eventId)}`;
}

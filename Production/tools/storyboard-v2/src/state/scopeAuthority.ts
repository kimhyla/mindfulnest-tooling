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

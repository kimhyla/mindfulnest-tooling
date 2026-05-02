// ScopeBoundary — top-level component that establishes the active event scope
// and renders children. Companion to LD SCOPE_VALIDATION_V1: this is the
// CLIENT-SIDE half of the scope guard. The server-side half (HTTP 409 on
// mismatched event_id) lands in Session 1.5.
//
// Resolution order for event_id (highest priority first):
//   1. ?event=Event_1 URL query param
//   2. <body data-event-id="Event_1"> attribute
//   3. window.__MN_EVENT_ID__ global (set by production_server.py at render time)
//   4. Hardcoded fallback "Event_1"
//
// On mount, ScopeBoundary writes the resolved event_id into activeScope.

import { useEffect, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import { activeScope, makeScope, scopeKey } from '../state/scope';

export interface ScopeBoundaryProps {
  children: ComponentChildren;
  /** Override the resolved event_id (used by tests). */
  forceEventId?: string;
}

declare global {
  interface Window {
    __MN_EVENT_ID__?: string;
  }
}

function resolveEventId(forceEventId?: string): string {
  if (forceEventId) return forceEventId;
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get('event');
  if (fromQuery) return fromQuery;
  const fromBody = document.body.getAttribute('data-event-id');
  if (fromBody) return fromBody;
  if (window.__MN_EVENT_ID__) return window.__MN_EVENT_ID__;
  return 'Event_1';
}

export function ScopeBoundary({ children, forceEventId }: ScopeBoundaryProps) {
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    const eventId = resolveEventId(forceEventId);
    activeScope.value = makeScope(eventId, null, 1);
    setResolved(true);
    // Surface scope to the DOM for debugging + Playwright assertions.
    document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
  }, [forceEventId]);

  if (!resolved) {
    return (
      <div
        class="scope-boundary-loading"
        data-testid="scope-boundary-loading"
      >
        Resolving scope&hellip;
      </div>
    );
  }
  return <>{children}</>;
}

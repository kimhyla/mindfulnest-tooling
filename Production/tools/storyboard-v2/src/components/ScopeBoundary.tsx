// ScopeBoundary — top-level component that establishes the active event scope
// and renders children. Companion to LD SCOPE_VALIDATION_V1: this is the
// CLIENT-SIDE half of the scope guard. The server-side half (HTTP 409 on
// mismatched event_id) lands in Session 1.5.
//
// S5.5b Bug 4 fix A: query GET /api/event/current FIRST as the authoritative
// source. Server-provided event_id wins over URL/attr/global fallbacks — this
// closes the bug where EventSelector triggered window.location.reload() and
// ScopeBoundary read a STALE URL/attr/global on the next mount. Bug 4 fix B
// (EventSelector updating URL with ?event=<id>) keeps URL accurate for
// shareable links + Playwright assertions; A is the safety net.
//
// Resolution order for event_id (highest priority first):
//   1. forceEventId prop (test override)
//   2. GET /api/event/current — server's truth
//   3. ?event=Event_1 URL query param
//   4. <body data-event-id="Event_1"> attribute
//   5. window.__MN_EVENT_ID__ global (set by production_server.py at render time)
//   6. Hardcoded fallback "Event_1"
//
// On mount, ScopeBoundary writes the resolved event_id into activeScope and
// also seeds activeVideoRole from server's state.active_video (display hint
// only per LD-474).

import { useEffect, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import { activeScope, activeVideoRole, makeScope, scopeKey } from '../state/scope';
import { READ_ENDPOINTS } from '../api/endpoints';

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

function resolveLocalFallback(): string {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get('event');
  if (fromQuery) return fromQuery;
  const fromBody = document.body.getAttribute('data-event-id');
  if (fromBody) return fromBody;
  if (window.__MN_EVENT_ID__) return window.__MN_EVENT_ID__;
  return 'Event_1';
}

interface EventCurrentResponse {
  ok?: boolean;
  event_id?: string | null;
  event_generation?: number;
  active_video?: string | null;
  partition_keys?: string[];
}

export function ScopeBoundary({ children, forceEventId }: ScopeBoundaryProps) {
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 1. Test override wins.
      if (forceEventId) {
        if (!cancelled) {
          activeScope.value = makeScope(forceEventId, null, 1);
          document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
          setResolved(true);
        }
        return;
      }
      // 2. Ask the server (S5.5b Bug 4 fix A).
      let serverEventId: string | null = null;
      let serverGeneration = 1;
      let serverActiveVideo: string | null = null;
      try {
        const res = await fetch(READ_ENDPOINTS.event_current);
        if (res.ok) {
          const data = (await res.json()) as EventCurrentResponse;
          if (data && typeof data.event_id === 'string' && data.event_id) {
            serverEventId = data.event_id;
            if (typeof data.event_generation === 'number') {
              serverGeneration = data.event_generation;
            }
            serverActiveVideo = data.active_video ?? null;
          }
        }
      } catch {
        // Network unreachable — fall through to local fallback.
      }
      if (cancelled) return;
      const eventId = serverEventId ?? resolveLocalFallback();
      activeScope.value = makeScope(eventId, null, serverGeneration);
      // S5.5b: seed activeVideoRole from server's state.active_video.
      // LD-474: this is a DISPLAY HINT only; never use it for partition selection.
      if (serverActiveVideo && typeof serverActiveVideo === 'string') {
        activeVideoRole.value = serverActiveVideo;
      }
      // Surface scope to the DOM for debugging + Playwright assertions.
      document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
      setResolved(true);
    })();
    return () => { cancelled = true; };
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

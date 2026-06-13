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
//   2. GET /api/event/current — server's truth (when no ?event= deep link)
//   3. ?event=Event_1 URL query param — when present AND mismatched with the
//      server pin, POST /api/event/load to honor shareable deep links
//      (SCOPE_DEEP_LINK_DURABILITY_V1 — avoids scope_mismatch 409 on v2 state)
//   4. <body data-event-id="Event_1"> attribute
//   5. window.__MN_EVENT_ID__ global (set by production_server.py at render time)
//   6. Hardcoded fallback "Event_1"
//
// When ?event= is absent, server truth wins (S5.5b Bug 4 fix A — stale URL
// after EventSelector cannot override the live server pin).
//
// On mount, ScopeBoundary writes the resolved event_id into activeScope and
// also seeds activeVideoRole from server's state.active_video (display hint
// only per LD-474).

import { useEffect, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import {
  activeScope,
  activeVideoRole,
  activeProjectType,
  activeMilestoneId,
  makeScope,
  scopeKey,
} from '../state/scope';
import { READ_ENDPOINTS } from '../api/endpoints';
import { pathappPatch, loadEvent, emitScopeEventChanged } from '../api/client';

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
  scope_type?: string;
  active_milestone_id?: string | null;
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
          activeProjectType.value = 'event';
          activeMilestoneId.value = null;
          document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
          document.body.setAttribute('data-active-project-type', 'event');
          setResolved(true);
        }
        return;
      }
      // 2. Ask the server (S5.5b Bug 4 fix A).
      let serverEventId: string | null = null;
      let serverGeneration = 1;
      let serverActiveVideo: string | null = null;
      let serverScopeType: string | undefined;
      let serverMilestoneId: string | null | undefined;
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
            serverScopeType = data.scope_type;
            serverMilestoneId = data.active_milestone_id;
          }
        }
      } catch {
        // Network unreachable — fall through to local fallback.
      }
      if (cancelled) return;

      const urlEventId = (() => {
        try {
          return new URLSearchParams(window.location.search).get('event');
        } catch {
          return null;
        }
      })();

      let eventId = serverEventId ?? resolveLocalFallback();
      let resolvedGeneration = serverGeneration;

      // Deep-link bootstrap: ?event= requests a specific event. When it
      // differs from the process startup pin, swap server scope before any
      // tab fetches /api/v2/event/<id>/state (avoids scope_mismatch 409).
      if (urlEventId && urlEventId !== serverEventId) {
        try {
          const loadRes = await loadEvent(urlEventId);
          if (loadRes.ok && loadRes.data?.event_id) {
            eventId = loadRes.data.event_id;
            resolvedGeneration = loadRes.data.event_generation;
            try {
              const res2 = await fetch(READ_ENDPOINTS.event_current);
              if (res2.ok) {
                const data2 = (await res2.json()) as EventCurrentResponse;
                serverActiveVideo = data2.active_video ?? null;
                serverScopeType = data2.scope_type;
                serverMilestoneId = data2.active_milestone_id;
              }
            } catch {
              // Non-fatal — activeScope still matches the loaded event.
            }
            emitScopeEventChanged({
              event_id: eventId,
              event_generation: resolvedGeneration,
              scope_key: scopeKey(makeScope(eventId, null, resolvedGeneration)),
              source: 'scope-boundary-url-bootstrap',
            });
          } else if (serverEventId) {
            // Target missing or load failed — keep server pin (Bug 4 safety).
            eventId = serverEventId;
          }
        } catch {
          if (serverEventId) eventId = serverEventId;
        }
      } else if (!serverEventId && urlEventId) {
        // Cold boot with ?event= but no server pin yet.
        try {
          const loadRes = await loadEvent(urlEventId);
          if (loadRes.ok && loadRes.data?.event_id) {
            eventId = loadRes.data.event_id;
            resolvedGeneration = loadRes.data.event_generation;
          } else {
            eventId = urlEventId;
          }
        } catch {
          eventId = urlEventId;
        }
      }

      activeScope.value = makeScope(eventId, null, resolvedGeneration);
      // F-PROJECT-001: milestone scope survives reload — hydrate from server
      // (GET /api/event/current) and/or ?milestone= when server is still on event.
      let milestoneId: string | null = null;
      if (serverScopeType === 'milestone' && typeof serverMilestoneId === 'string' && serverMilestoneId) {
        milestoneId = serverMilestoneId;
      } else {
        try {
          const urlMs = new URLSearchParams(window.location.search).get('milestone');
          if (urlMs) {
            const loadRes = await pathappPatch<{ ok?: boolean }>(
              activeScope.value,
              'milestone_load',
              { milestone_id: urlMs },
            );
            if (loadRes.ok && loadRes.data?.ok) {
              milestoneId = urlMs;
              if (typeof loadRes.data === 'object' && loadRes.data !== null) {
                const eg = (loadRes.data as { event_generation?: number }).event_generation;
                if (typeof eg === 'number') {
                  activeScope.value = makeScope(eventId, null, eg);
                }
              }
            }
          }
        } catch (err) {
          // F-PROJECT-001 milestone URL bootstrap — Rule 19 escape hatch.
          // SHORTCUT: SHORTCUT_F_PROJECT_001_MILESTONE_BOOTSTRAP_BEST_EFFORT_V1
          // (prod_locked_decisions id=679) documents this deferral + closure plan.
          // Canonical milestone-scope entry is the Project dropdown onChange handler
          // (ProjectSelector.tsx:414); URL-bootstrap is a secondary deep-link convenience
          // and fallback to event scope is the safe default.
          // Observability: console.warn below + mn:milestone-bootstrap-failed CustomEvent.
          // eslint-disable-next-line no-console
          console.warn('[ScopeBoundary] milestone URL bootstrap failed (event scope fallback):', err);
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('mn:milestone-bootstrap-failed', {
                detail: {
                  url_milestone_id: new URLSearchParams(window.location.search).get('milestone'),
                  error: String(err),
                },
              }),
            );
          }
        }
      }
      if (milestoneId) {
        activeProjectType.value = 'milestone';
        activeMilestoneId.value = milestoneId;
        document.body.setAttribute('data-active-project-type', 'milestone');
      } else {
        activeProjectType.value = 'event';
        activeMilestoneId.value = null;
        document.body.setAttribute('data-active-project-type', 'event');
      }
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

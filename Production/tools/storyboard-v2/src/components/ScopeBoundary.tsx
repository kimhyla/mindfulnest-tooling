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
import {
  activeScope,
  activeVideoRole,
  activeProjectType,
  activeMilestoneId,
  makeScope,
  scopeKey,
} from '../state/scope';
import { READ_ENDPOINTS, MUTATION_ENDPOINTS } from '../api/endpoints';
import { pathappPatch } from '../api/client';

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
      const eventId = serverEventId ?? resolveLocalFallback();
      let effectiveGen = serverGeneration;
      let effectiveScopeType = serverScopeType;
      let effectiveMilestoneId = serverMilestoneId;
      const urlMs = new URLSearchParams(window.location.search).get('milestone');

      // Shared production_server process: an earlier session can leave
      // scope_type='milestone' while this navigation has no ?milestone= (e.g.
      // Playwright order). Re-pin to event scope so event-only tabs work; deep
      // links still pass ?milestone= (handled below).
      if (
        effectiveScopeType === 'milestone'
        && typeof effectiveMilestoneId === 'string'
        && effectiveMilestoneId
        && !urlMs
      ) {
        try {
          const el = await fetch(MUTATION_ENDPOINTS.event_load, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: eventId }),
          });
          if (el.ok) {
            const d = (await el.json()) as { event_generation?: number };
            if (typeof d.event_generation === 'number') {
              effectiveGen = d.event_generation;
            }
            effectiveScopeType = 'event';
            effectiveMilestoneId = null;
          }
        } catch {
          // non-fatal — fall through with server-reported scope
        }
      }

      activeScope.value = makeScope(eventId, null, effectiveGen);

      // F-PROJECT-001: milestone scope survives reload — ?milestone= bootstrap
      // or hydrate when URL and server already agree.
      let milestoneId: string | null = null;
      if (urlMs) {
        try {
          const loadRes = await pathappPatch<{ ok?: boolean; event_generation?: number }>(
            activeScope.value,
            'milestone_load',
            { milestone_id: urlMs },
          );
          if (loadRes.ok && loadRes.data?.ok) {
            milestoneId = urlMs;
            const eg = loadRes.data.event_generation;
            if (typeof eg === 'number') {
              activeScope.value = makeScope(eventId, null, eg);
            }
          }
        } catch (err) {
          // F-PROJECT-001 milestone URL bootstrap is BEST-EFFORT, NOT a critical write path.
          // Rule 19 justification: this code only runs when the user navigates with `?milestone=<id>`
          // (deep-link / shared URL flow). If milestone_load fails, the safe fallback is event scope —
          // the user can still switch via the Project dropdown's canonical onChange handler
          // (ProjectSelector.tsx:414). So the failure is non-fatal: we surface to console for
          // observability + emit a `mn:milestone-bootstrap-failed` window event for UI listeners.
          // No SHORTCUT_* LD needed because this is documented best-effort degradation, not a
          // deferred fix on a broken write path.
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
      } else if (
        effectiveScopeType === 'milestone'
        && typeof effectiveMilestoneId === 'string'
        && effectiveMilestoneId
      ) {
        milestoneId = effectiveMilestoneId;
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

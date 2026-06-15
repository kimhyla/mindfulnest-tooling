// ScopeBoundary — top-level component that establishes the active event scope
// and renders children. Companion to LD SCOPE_VALIDATION_V1: this is the
// CLIENT-SIDE half of the scope guard. The server-side half (HTTP 409 on
// mismatched event_id) lands in Session 1.5.
//
// EVENT_PIN_DURABILITY_V1 + SCOPE_URL_AUTHORITY_V1 + SCOPE_DEEP_LINK_DURABILITY_V1 (2026-06):
//   - When ?event=<id> is present, the URL is authoritative — never silently
//     fall back to Event_1 or the server's stale startup pin.
//   - Tabs do not mount until POST /api/event/load confirms the server pin
//     matches the resolved target event_id.
//   - Server persists last-loaded event in Production/server_event_pin.json so
//     restarts reopen the same event without drift.

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
import { pathappPatch, loadEvent, emitScopeEventChanged, ensureServerPinnedTo } from '../api/client';

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

function readUrlEventId(): string | null {
  try {
    return new URLSearchParams(window.location.search).get('event');
  } catch {
    return null;
  }
}

function resolveLocalFallbackWithoutUrl(): string {
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

async function fetchEventCurrent(): Promise<EventCurrentResponse | null> {
  try {
    const res = await fetch(READ_ENDPOINTS.event_current);
    if (!res.ok) return null;
    return (await res.json()) as EventCurrentResponse;
  } catch {
    return null;
  }
}

export function ScopeBoundary({ children, forceEventId }: ScopeBoundaryProps) {
  const [resolved, setResolved] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPinError(null);

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

      const urlEventId = readUrlEventId();
      const current = await fetchEventCurrent();
      if (cancelled) return;

      let serverEventId = (
        current && typeof current.event_id === 'string' && current.event_id
      ) ? current.event_id : null;
      let resolvedGeneration = (
        typeof current?.event_generation === 'number'
      ) ? current.event_generation : 1;
      let serverActiveVideo = current?.active_video ?? null;
      let serverScopeType = current?.scope_type;
      let serverMilestoneId = current?.active_milestone_id;

      // Target: URL wins when present (SCOPE_URL_AUTHORITY_V1).
      let targetEventId = urlEventId ?? serverEventId ?? resolveLocalFallbackWithoutUrl();

      const pinTarget = async (eventId: string): Promise<boolean> => {
        if (serverEventId === eventId) {
          return ensureServerPinnedTo(eventId);
        }
        const loadRes = await loadEvent(eventId);
        if (!loadRes.ok || !loadRes.data?.event_id) {
          return false;
        }
        serverEventId = loadRes.data.event_id;
        resolvedGeneration = loadRes.data.event_generation;
        emitScopeEventChanged({
          event_id: loadRes.data.event_id,
          event_generation: loadRes.data.event_generation,
          scope_key: scopeKey(makeScope(loadRes.data.event_id, null, loadRes.data.event_generation)),
          source: urlEventId ? 'scope-boundary-url-authority' : 'scope-boundary-pin',
        });
        const refreshed = await fetchEventCurrent();
        if (refreshed) {
          serverActiveVideo = refreshed.active_video ?? null;
          serverScopeType = refreshed.scope_type;
          serverMilestoneId = refreshed.active_milestone_id;
          if (typeof refreshed.event_generation === 'number') {
            resolvedGeneration = refreshed.event_generation;
          }
        }
        return ensureServerPinnedTo(eventId);
      };

      let pinOk = await pinTarget(targetEventId);
      if (!pinOk && urlEventId) {
        // One retry — server may have been mid-restart.
        pinOk = await pinTarget(urlEventId);
        targetEventId = urlEventId;
      }

      if (!pinOk) {
        if (urlEventId) {
          if (!cancelled) {
            setPinError(
              `Could not pin server to ${urlEventId}. `
              + 'Hard-refresh or pick the event again from the Project menu.',
            );
            document.body.setAttribute('data-scope-pin-failed', urlEventId);
          }
          return;
        }
        if (serverEventId) {
          targetEventId = serverEventId;
          pinOk = await ensureServerPinnedTo(targetEventId);
        }
      }

      if (!pinOk) {
        if (!cancelled) {
          setPinError(
            `Could not confirm server scope for ${targetEventId}. `
            + 'Hard-refresh and try again.',
          );
        }
        return;
      }

      if (cancelled) return;

      activeScope.value = makeScope(targetEventId, null, resolvedGeneration);

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
                  activeScope.value = makeScope(targetEventId, null, eg);
                }
              }
            }
          }
        } catch (err) {
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

      if (serverActiveVideo && typeof serverActiveVideo === 'string') {
        activeVideoRole.value = serverActiveVideo;
      }
      document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
      document.body.removeAttribute('data-scope-pin-failed');
      setResolved(true);
    })();
    return () => { cancelled = true; };
  }, [forceEventId]);

  if (pinError) {
    return (
      <div
        class="scope-boundary-error"
        data-testid="scope-boundary-error"
        data-scope-pin-error={pinError}
      >
        {pinError}
      </div>
    );
  }

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

// ScopeBoundary — top-level component that establishes the active event scope
// and renders children. Companion to LD SCOPE_VALIDATION_V1: this is the
// CLIENT-SIDE half of the scope guard. The server-side half (HTTP 409 on
// mismatched event_id) lands in Session 1.5.
//
// SCOPE_DEEP_LINK_DURABILITY_V1 + SCOPE_RESTART_RECONCILE_V1: boot pin delegates
// to reconcileClientScope (shared with ServerRehydrateWatcher) — POST event/load
// before tabs fetch scoped state; avoids scope_mismatch 409 on URL ?event= drift.

import { useEffect, useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';
import {
  activeScope,
  activeProjectType,
  activeMilestoneId,
  makeScope,
  readUrlMilestoneId,
  scopeKey,
} from '../state/scope';
import { noteClientPinnedEvent } from '../api/client';
import { reconcileClientScope } from '../state/scopeReconcile';
import { confirmServerMilestoneScope } from '../state/milestoneScopeGate';
import { setScopeReady } from '../state/scopeReady';

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

export function ScopeBoundary({ children, forceEventId }: ScopeBoundaryProps) {
  const [resolved, setResolved] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPinError(null);
      setScopeReady(false, 'scope-boundary-boot');

      if (forceEventId) {
        if (!cancelled) {
          activeScope.value = makeScope(forceEventId, null, 1);
          activeProjectType.value = 'event';
          activeMilestoneId.value = null;
          document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
          document.body.setAttribute('data-active-project-type', 'event');
          noteClientPinnedEvent(forceEventId);
          setScopeReady(true, 'scope-boundary-force');
          setResolved(true);
        }
        return;
      }

      const result = await reconcileClientScope({ source: 'scope-boundary-boot' });
      if (cancelled) return;

      if (!result.ok) {
        if (result.pinError) {
          setPinError(result.pinError);
        }
        setScopeReady(false, 'scope-boundary-pin-fail');
        return;
      }

      const needsMilestoneConfirm =
        activeProjectType.value === 'milestone'
        || Boolean(readUrlMilestoneId());
      if (needsMilestoneConfirm) {
        const confirmed = await confirmServerMilestoneScope(activeScope.value);
        if (cancelled) return;
        if (!confirmed.ok) {
          setPinError(
            'Milestone scope not loaded on server — wait a moment and reload, '
            + 'or pick the milestone again from Project.',
          );
          setScopeReady(false, 'scope-boundary-milestone-fail');
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('mn:milestone-bootstrap-failed', {
                detail: {
                  url_milestone_id: readUrlMilestoneId(),
                  error: confirmed.lastError,
                },
              }),
            );
          }
          return;
        }
      }

      if (cancelled) return;

      setScopeReady(true, 'scope-boundary-pin-ok');
      document.body.setAttribute('data-resolved-scope', scopeKey(activeScope.value));
      setResolved(true);
    })();
    return () => { cancelled = true; };
  }, [forceEventId]);

  if (pinError) {
    const correctUrl = document.body.getAttribute('data-scope-correct-url');
    return (
      <div
        class="scope-boundary-error"
        data-testid="scope-boundary-error"
        data-scope-pin-error={pinError}
      >
        {pinError}
        {correctUrl ? (
          <p style={{ marginTop: '0.75rem' }}>
            <a href={correctUrl} class="mn-scope-boundary-open-correct-url">
              Open {correctUrl}
            </a>
          </p>
        ) : null}
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

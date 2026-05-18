// ScopeBanner — listens for scope-mismatch (HTTP 409) and event-changed
// (HTTP 423) events from the mutation channel.
//
// LD-456 (409) → red persistent banner + "Reload page" CTA.
//   Persistent intentional — Kim must see it until she reloads. Toast would
//   auto-fade and risk silent corruption per Rule 19.
// LD-458 / LD-460 (423) → Toast (info: "Re-syncing…", success: "Re-sync
//   complete", error: red banner if retry fails). Migrated to the new Toast
//   primitive per S5.5c Phase B7 (LD UI_PRIMITIVES_SHARED_V1).

import { useEffect } from 'preact/hooks';
import { signal } from '@preact/signals';
import { SCOPE_EVENT_MISMATCH, SCOPE_EVENT_CHANGED } from '../api/client';
import { pushToast } from './ui/Toast';

interface BannerState {
  kind: 'mismatch' | null;
  message: string;
  detail?: Record<string, unknown>;
}

const banner = signal<BannerState>({ kind: null, message: '' });

export function ScopeBanner() {
  useEffect(() => {
    const onMismatch = (e: Event) => {
      const detail = (e as CustomEvent).detail ?? {};
      const detailMap = detail as Record<string, unknown>;
      // Wave 5 R3: prefer V59 canonical error shape (Phase 7) when present;
      // fall back to legacy detail.data shape used by LD-456 pre-V59 emitters.
      const v59Message = detailMap['error_message'];
      const v59Code = detailMap['error_code'];
      const v59Hint = detailMap['hint'];
      if (typeof v59Message === 'string' && v59Code === 'SCOPE_MISMATCH') {
        const hintText = typeof v59Hint === 'string' && v59Hint ? ` ${v59Hint}` : ' Reload the tab to re-resolve.';
        banner.value = {
          kind: 'mismatch',
          message: `Scope mismatch: ${v59Message}.${hintText}`,
          detail: detailMap,
        };
        return;
      }
      // Legacy shape: detail.data.{expected_event_id, got_event_id}
      const got = detailMap['data'];
      const expected = (got && typeof got === 'object' ? (got as Record<string, unknown>)['expected_event_id'] : undefined) ?? '?';
      const actual = (got && typeof got === 'object' ? (got as Record<string, unknown>)['got_event_id'] : undefined) ?? '?';
      banner.value = {
        kind: 'mismatch',
        message: `Scope mismatch: server is on ${String(expected)} but client sent ${String(actual)}. Reload the tab to re-resolve.`,
        detail: detailMap,
      };
    };
    const onChanged = (e: Event) => {
      const detail = ((e as CustomEvent).detail ?? {}) as Record<string, unknown>;
      const phase = String(detail['phase'] ?? '?');
      if (phase === 'before-retry') {
        pushToast({
          kind: 'info',
          message: 'Event changed mid-mutation. Re-syncing and retrying…',
          source: 'scope-banner-423-before',
        });
      } else if (phase === 'after-retry') {
        const ok = Boolean(detail['retried_ok']);
        if (ok) {
          pushToast({
            kind: 'success',
            message: 'Re-sync complete; mutation applied.',
            source: 'scope-banner-423-success',
          });
        } else {
          // Failed retry collapses into the persistent red banner so Kim
          // sees it after the toast queue drains.
          banner.value = {
            kind: 'mismatch',
            message: 'Re-sync retry failed. Reload the tab and try again.',
            detail,
          };
        }
      }
    };
    window.addEventListener(SCOPE_EVENT_MISMATCH, onMismatch);
    window.addEventListener(SCOPE_EVENT_CHANGED, onChanged);
    return () => {
      window.removeEventListener(SCOPE_EVENT_MISMATCH, onMismatch);
      window.removeEventListener(SCOPE_EVENT_CHANGED, onChanged);
    };
  }, []);

  if (banner.value.kind === null) return null;

  return (
    <div
      class="mn-scope-banner mn-scope-banner-error"
      data-testid="scope-banner-mismatch"
      role="alert"
    >
      <span class="mn-scope-banner-text">{banner.value.message}</span>
      <button
        type="button"
        class="mn-scope-banner-action"
        data-testid="scope-banner-reload"
        onClick={() => {
          window.location.reload();
        }}
      >
        Reload page
      </button>
      <button
        type="button"
        class="mn-scope-banner-dismiss"
        data-testid="scope-banner-dismiss"
        onClick={() => {
          banner.value = { kind: null, message: '' };
        }}
        aria-label="Dismiss banner"
      >
        &times;
      </button>
    </div>
  );
}

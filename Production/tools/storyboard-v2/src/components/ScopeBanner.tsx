// ScopeBanner — listens for scope-mismatch (HTTP 409) and event-changed
// (HTTP 423) events from the mutation channel and renders a fixed-top
// banner so Kim sees a clear failure mode rather than silent corruption.
//
// LD-456 (409) → red banner + "Reload page" CTA.
// LD-458 / LD-460 (423) → amber toast that auto-clears after the retry path
// finishes ("Event changed; re-syncing…" → success or red banner on retry fail).

import { useEffect } from 'preact/hooks';
import { signal } from '@preact/signals';
import { SCOPE_EVENT_MISMATCH, SCOPE_EVENT_CHANGED } from '../api/client';

interface BannerState {
  kind: 'mismatch' | 'changed' | null;
  message: string;
  detail?: Record<string, unknown>;
}

const banner = signal<BannerState>({ kind: null, message: '' });

export function ScopeBanner() {
  useEffect(() => {
    const onMismatch = (e: Event) => {
      const detail = (e as CustomEvent).detail ?? {};
      const got = (detail as Record<string, unknown>)['data'];
      const expected = (got && typeof got === 'object' ? (got as Record<string, unknown>)['expected_event_id'] : undefined) ?? '?';
      const actual = (got && typeof got === 'object' ? (got as Record<string, unknown>)['got_event_id'] : undefined) ?? '?';
      banner.value = {
        kind: 'mismatch',
        message: `Scope mismatch: server is on ${String(expected)} but client sent ${String(actual)}. Reload the tab to re-resolve.`,
        detail: detail as Record<string, unknown>,
      };
    };
    const onChanged = (e: Event) => {
      const detail = ((e as CustomEvent).detail ?? {}) as Record<string, unknown>;
      const phase = String(detail['phase'] ?? '?');
      if (phase === 'before-retry') {
        banner.value = {
          kind: 'changed',
          message: 'Event changed mid-mutation. Re-syncing and retrying…',
          detail,
        };
      } else if (phase === 'after-retry') {
        const ok = Boolean(detail['retried_ok']);
        if (ok) {
          // Auto-clear the toast after a brief delay.
          banner.value = {
            kind: 'changed',
            message: 'Re-sync complete; mutation applied.',
            detail,
          };
          setTimeout(() => {
            if (banner.value.kind === 'changed') {
              banner.value = { kind: null, message: '' };
            }
          }, 2000);
        } else {
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

  const isMismatch = banner.value.kind === 'mismatch';
  return (
    <div
      class={`mn-scope-banner ${isMismatch ? 'mn-scope-banner-error' : 'mn-scope-banner-info'}`}
      data-testid={isMismatch ? 'scope-banner-mismatch' : 'scope-banner-changed'}
      role={isMismatch ? 'alert' : 'status'}
    >
      <span class="mn-scope-banner-text">{banner.value.message}</span>
      {isMismatch ? (
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
      ) : null}
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

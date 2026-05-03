// BgTab — Beat Generator pane (Session 2 v3.1 — scope-aware Accept All wired).
// Full extract / 3x3 options grid / per-beat dialogue editor are Session 3 polish.
// This pass ships the Accept All control with explicit `scope_event_id` so
// the cross-event leak class is exercisable end-to-end via Playwright.

import { useState } from 'preact/hooks';
import { activeScope, scopeKey } from '../state/scope';
import { pathappPatch } from '../api/client';

export function BgTab() {
  const [acceptStatus, setAcceptStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [acceptDetail, setAcceptDetail] = useState<string | null>(null);

  const onAcceptAll = async () => {
    setAcceptStatus('sending');
    setAcceptDetail(null);
    // Empty beats array — this is the structural smoke; S3 wires real
    // BG state -> beats payload. The point here is to exercise the
    // scope_event_id round-trip end-to-end through pathappPatch.
    const result = await pathappPatch(activeScope.value, 'bg_accept_beats', {
      beats: [],
      segment: 0,
    });
    if (result.ok) {
      setAcceptStatus('ok');
      setAcceptDetail(`scope=${activeScope.value.event_id} (server accepted)`);
    } else {
      setAcceptStatus('error');
      setAcceptDetail(`HTTP ${result.status}: ${result.error}`);
    }
    setTimeout(() => {
      setAcceptStatus((s) => (s === 'ok' ? 'idle' : s));
    }, 3000);
  };

  return (
    <section class="mn-tab-pane mn-bg-pane" data-testid="pane-bg">
      <header class="mn-pane-header">
        <h2>Beat Generator</h2>
        <span class="mn-scope-chip" data-testid="bg-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>
      <div class="mn-bg-grid">
        <div class="mn-bg-col" data-testid="bg-col-extract">
          <h3>Extract beats</h3>
          <p class="mn-dim">Source script &rarr; structured beats (S3 polish).</p>
        </div>
        <div class="mn-bg-col" data-testid="bg-col-options">
          <h3>Options</h3>
          <p class="mn-dim">3 character refs &times; 3 BG refs grid (S3 polish).</p>
        </div>
        <div class="mn-bg-col" data-testid="bg-col-dialogue">
          <h3>Dialogue</h3>
          <p class="mn-dim">Per-beat speaker + text (S3 polish).</p>
        </div>
      </div>
      <div class="mn-bg-actions">
        <button
          type="button"
          class="mn-btn mn-btn-primary"
          data-testid="bg-accept-all-btn"
          onClick={onAcceptAll}
          disabled={acceptStatus === 'sending'}
        >
          {acceptStatus === 'sending' ? 'Sending…' : 'Accept All to Storyboard'}
        </button>
        <span
          class={`mn-bg-accept-status mn-bg-accept-${acceptStatus}`}
          data-testid="bg-accept-status"
          data-accept-status={acceptStatus}
        >
          {acceptStatus === 'idle'
            ? 'idle'
            : acceptStatus === 'sending'
              ? 'sending…'
              : acceptStatus === 'ok'
                ? `✓ ${acceptDetail}`
                : `✗ ${acceptDetail}`}
        </span>
      </div>
      <footer class="mn-pane-footer">
        <p class="mn-warn" data-testid="bg-cross-event-banner">
          Cross-event leak structurally eliminated: this Accept All POST sends
          `scope_event_id={activeScope.value.event_id}`; server returns HTTP 409
          on mismatch (LD-456 + LD-461 helper, server-side scope guard active).
        </p>
      </footer>
    </section>
  );
}

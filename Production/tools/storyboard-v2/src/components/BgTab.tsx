// BgTab — Beat Generator pane. Session 1 placeholder.
// Real BG state hydration lands in Session 1.5+ via /api/bg/state plus the
// scope-guarded /api/bg/* mutation handlers (LD SCOPE_VALIDATION_V1).

import { activeScope, scopeKey } from '../state/scope';

export function BgTab() {
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
          <p class="mn-dim">Source script &rarr; structured beats (placeholder).</p>
        </div>
        <div class="mn-bg-col" data-testid="bg-col-options">
          <h3>Options</h3>
          <p class="mn-dim">3 character refs &times; 3 BG refs (placeholder).</p>
        </div>
        <div class="mn-bg-col" data-testid="bg-col-dialogue">
          <h3>Dialogue</h3>
          <p class="mn-dim">Per-beat speaker + text (placeholder).</p>
        </div>
      </div>
      <footer class="mn-pane-footer">
        <p class="mn-warn" data-testid="bg-cross-event-banner">
          Cross-event Accept-All bug eliminated structurally:
          every Accept All POST will carry scope.event_id; server returns HTTP 409
          on mismatch (LD SCOPE_VALIDATION_V1, lands Session 1.5).
        </p>
      </footer>
    </section>
  );
}

// StitcherTab — final MP4 assembly placeholder. Session 1 read-only preview.
// Real ffmpeg concat + LD-284 NORMALIZATION_BEFORE_CONCAT_V1 enforcement
// lives server-side; this pane will visualize the queue + per-beat normalized
// asset state in later sessions.

import { activeScope, scopeKey } from '../state/scope';

export function StitcherTab() {
  return (
    <section class="mn-tab-pane mn-stitcher-pane" data-testid="pane-stitcher">
      <header class="mn-pane-header">
        <h2>Stitcher</h2>
        <span class="mn-scope-chip" data-testid="stitcher-scope-chip">
          scope: {scopeKey(activeScope.value)}
        </span>
      </header>
      <div class="mn-stitcher-empty">
        <p>Final MP4 assembly &mdash; placeholder.</p>
        <p class="mn-dim">
          Session 1 read-only preview. Per-beat normalized asset state and
          ffmpeg concat queue render in later sessions. Reference:
          LD-280 RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1, LD-284
          NORMALIZATION_BEFORE_CONCAT_V1.
        </p>
      </div>
    </section>
  );
}

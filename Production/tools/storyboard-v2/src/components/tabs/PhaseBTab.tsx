// PhaseBTab — S5.5d (v3 architecture revision, 2026-05-03).
// Top-level tab dedicated to Phase B (eyes-closed guided meditation).
// Reads top-level state.phase_b.* per PHASE_B_TOP_LEVEL_STATE_V1
// (no longer nested inside videos.phase_b partition).
//
// Implementation: thin wrapper that hosts the existing PhaseProducer
// component for phase="b" — which already reads state.phase_b.* fields.
// Disabled when activeProjectType === 'milestone'.

import { activeProjectType, scopeKey, activeScope } from '../../state/scope';
import { PhaseProducer } from '../phase/PhaseProducer';

export function PhaseBTab() {
  if (activeProjectType.value === 'milestone') {
    return (
      <section class="mn-tab-pane mn-phase-b-pane" data-testid="pane-phase-b">
        <header class="mn-pane-header">
          <h2>Phase B</h2>
          <span class="mn-scope-chip">scope: {scopeKey(activeScope.value)}</span>
        </header>
        <p class="mn-dim">
          Phase B is event-only. Switch to an Event scope to edit Phase B.
        </p>
      </section>
    );
  }
  return (
    <section class="mn-tab-pane mn-phase-b-pane" data-testid="pane-phase-b">
      <header class="mn-pane-header">
        <h2>Phase B</h2>
        <span class="mn-scope-chip">scope: {scopeKey(activeScope.value)}</span>
      </header>
      <PhaseProducer phase="b" />
    </section>
  );
}

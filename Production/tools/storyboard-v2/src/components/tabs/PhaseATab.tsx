// PhaseATab — S5.5d (v3 architecture revision, 2026-05-03).
// Top-level tab dedicated to Phase A (instructional demo). Mirror of
// PhaseBTab. Reads top-level state.phase_a.* per PHASE_A_TOP_LEVEL_STATE_V1
// (no longer nested inside videos.phase_a partition).
//
// Implementation: thin wrapper that hosts the existing PhaseProducer
// component for phase="a" — which already reads state.phase_a.* fields.
// Disabled when activeProjectType === 'milestone'.

import { activeProjectType, scopeKey, activeScope } from '../../state/scope';
import { PhaseProducer } from '../phase/PhaseProducer';

export function PhaseATab() {
  if (activeProjectType.value === 'milestone') {
    return (
      <section class="mn-tab-pane mn-phase-a-pane" data-testid="phase-a-tab-root">
        <header class="mn-pane-header" data-testid="phase-a-pane-header">
          <h2>Phase A</h2>
          <span class="mn-scope-chip" data-testid="phase-a-scope-chip">scope: {scopeKey(activeScope.value)}</span>
        </header>
        <p class="mn-dim" data-testid="phase-a-milestone-hint">
          Phase A is event-only. Switch to an Event scope to edit Phase A.
        </p>
      </section>
    );
  }
  return (
    <section class="mn-tab-pane mn-phase-a-pane" data-testid="phase-a-tab-root">
      <header class="mn-pane-header" data-testid="phase-a-pane-header">
        <h2>Phase A</h2>
        <span class="mn-scope-chip" data-testid="phase-a-scope-chip">scope: {scopeKey(activeScope.value)}</span>
      </header>
      <div data-testid="phase-a-producer-panel">
        <PhaseProducer phase="a" />
      </div>
    </section>
  );
}

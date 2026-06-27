import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  activeMilestoneId,
  activeProjectType,
  activeScope,
  activeScopeQueryParams,
  makeScope,
  producerScopeChipLabel,
  readUrlMilestoneId,
  shouldInjectMilestoneScope,
  adoptDedicatedPortMilestoneLayout,
  isDedicatedPortMilestoneDeepLink,
} from '../scope.ts';

describe('shouldInjectMilestoneScope', () => {
  beforeEach(() => {
    activeScope.value = makeScope('Event_2', null, 1);
    activeProjectType.value = 'event';
    activeMilestoneId.value = null;
  });

  it('does not inject milestone scope on hub port when project type is event', () => {
    const g = globalThis as typeof globalThis & {
      window?: { location: { search: string; href: string; port: string } };
    };
    const prev = g.window;
    g.window = {
      location: {
        search: '?milestone=milestone1_arc1',
        href: 'http://localhost:5111/?milestone=milestone1_arc1',
        port: '5111',
      },
    };
    try {
      assert.equal(readUrlMilestoneId(), 'milestone1_arc1');
      assert.equal(shouldInjectMilestoneScope(), false);
      const params = activeScopeQueryParams();
      assert.equal(params.scope_event_id, 'Event_2');
      assert.equal(params.scope_milestone_id, undefined);
    } finally {
      g.window = prev;
    }
  });

  it('injects milestone scope on dedicated port ?milestone= deep link (DEDICATED_PORT_MILESTONE_LAYOUT_V1)', () => {
    const g = globalThis as typeof globalThis & {
      window?: { location: { search: string; href: string; port: string } };
    };
    const prev = g.window;
    g.window = {
      location: {
        search: '?event=Event_2&milestone=milestone1_arc1&video=standalone',
        href: 'http://localhost:5112/?event=Event_2&milestone=milestone1_arc1',
        port: '5112',
      },
    };
    try {
      assert.equal(isDedicatedPortMilestoneDeepLink(), true);
      assert.equal(shouldInjectMilestoneScope(), true);
      adoptDedicatedPortMilestoneLayout('milestone1_arc1');
      const params = activeScopeQueryParams();
      assert.equal(params.scope_milestone_id, 'milestone1_arc1');
    } finally {
      g.window = prev;
    }
  });

  it('injects milestone scope only in milestone project mode', () => {
    activeProjectType.value = 'milestone';
    activeMilestoneId.value = 'milestone1_arc1';
    assert.equal(shouldInjectMilestoneScope(), true);
    const params = activeScopeQueryParams();
    assert.equal(params.scope_milestone_id, 'milestone1_arc1');
    assert.equal(params.scope_event_id, 'Event_2');
  });

  it('producerScopeChipLabel includes milestone and standalone in milestone mode', () => {
    activeProjectType.value = 'milestone';
    activeMilestoneId.value = 'milestone1_arc1';
    const label = producerScopeChipLabel();
    assert.match(label, /Event_2:global:v1/);
    assert.match(label, /milestone:milestone1_arc1/);
    assert.match(label, /standalone/);
  });
});

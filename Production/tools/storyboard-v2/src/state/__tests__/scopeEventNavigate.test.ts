// PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1 — zero-dep URL + switch-mode unit tests.
// Run: cd storyboard-v2 && node --experimental-strip-types --test src/state/__tests__/scopeEventNavigate.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildDedicatedPortEventUrl,
  eventIdToDedicatedPortNumber,
  resolveEventSwitchMode,
} from '../scopeAuthorityResolve.ts';

describe('eventIdToDedicatedPortNumber', () => {
  it('maps Event_1 → 5111', () => {
    assert.equal(eventIdToDedicatedPortNumber('Event_1'), 5111);
  });

  it('maps Event_2 → 5112', () => {
    assert.equal(eventIdToDedicatedPortNumber('Event_2'), 5112);
  });

  it('returns null for non-Event_N ids', () => {
    assert.equal(eventIdToDedicatedPortNumber('Event_e2e_fixture'), null);
  });
});

describe('buildDedicatedPortEventUrl', () => {
  it('builds bookmark with event param', () => {
    assert.equal(
      buildDedicatedPortEventUrl({ eventId: 'Event_1' }),
      'http://localhost:5111/?event=Event_1',
    );
  });

  it('preserves tab and video for cross-port handoff', () => {
    assert.equal(
      buildDedicatedPortEventUrl({
        eventId: 'Event_1',
        tab: 'phase_b',
        video: 'phase_b',
      }),
      'http://localhost:5111/?event=Event_1&tab=phase_b&video=phase_b',
    );
  });
});

describe('resolveEventSwitchMode', () => {
  it('navigate when dedicated ports differ', () => {
    assert.equal(resolveEventSwitchMode('Event_1', 5112), 'navigate');
    assert.equal(resolveEventSwitchMode('Event_2', 5111), 'navigate');
  });

  it('load on same dedicated port', () => {
    assert.equal(resolveEventSwitchMode('Event_2', 5112), 'load');
  });

  it('load for non-Event_N on dedicated port', () => {
    assert.equal(resolveEventSwitchMode('Event_e2e_fixture', 5112), 'load');
  });

  it('load below dedicated port range', () => {
    assert.equal(resolveEventSwitchMode('Event_1', 5110), 'load');
  });
});

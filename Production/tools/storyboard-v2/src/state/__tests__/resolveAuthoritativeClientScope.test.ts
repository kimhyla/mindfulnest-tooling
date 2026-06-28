// SCOPE_CLIENT_AUTHORITY_V1 — zero-dep resolver unit tests.
// Run: cd storyboard-v2 && node --experimental-strip-types --test src/state/__tests__/resolveAuthoritativeClientScope.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  dedicatedPortEventIdFromPort,
  resolveAuthoritativeEventIdFromParts,
} from '../scopeAuthorityResolve.ts';

describe('dedicatedPortEventIdFromPort', () => {
  it('maps 5112 → Event_2', () => {
    assert.equal(dedicatedPortEventIdFromPort(5112), 'Event_2');
  });

  it('maps 5111 → Event_1', () => {
    assert.equal(dedicatedPortEventIdFromPort(5111), 'Event_1');
  });

  it('returns null below 5111', () => {
    assert.equal(dedicatedPortEventIdFromPort(5110), null);
  });
});

describe('resolveAuthoritativeEventIdFromParts', () => {
  it('URL ?event= wins over port and fallback', () => {
    assert.equal(
      resolveAuthoritativeEventIdFromParts('Event_2', 'Event_1', 'Event_99'),
      'Event_2',
    );
  });

  it('dedicated port wins when URL absent', () => {
    assert.equal(
      resolveAuthoritativeEventIdFromParts(null, 'Event_2', 'Event_1'),
      'Event_2',
    );
  });

  it('falls back to activeScope event when no URL or port', () => {
    assert.equal(
      resolveAuthoritativeEventIdFromParts(null, null, 'Event_e2e_fixture'),
      'Event_e2e_fixture',
    );
  });
});

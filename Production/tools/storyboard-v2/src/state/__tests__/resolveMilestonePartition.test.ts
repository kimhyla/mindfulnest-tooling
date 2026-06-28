// MILESTONE_PARTITION_RESOLVER_V1 — matrix tests (Node-safe, zero DOM).
// Run: node --experimental-strip-types --test src/state/__tests__/resolveMilestonePartition.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  eventIdMatchesDedicatedPort,
  milestonePartitionDeepLinkAuthorized,
} from '../resolveMilestonePartition.ts';
import { resolveAuthoritativeEventIdFromParts } from '../scopeAuthorityResolve.ts';

function partitionGate(input: {
  milestoneId: string | null;
  urlEventId: string | null;
  activeScopeEventId: string;
  port: number;
}): boolean {
  return milestonePartitionDeepLinkAuthorized(input);
}

/** Reproduces the banned event-authority chain misapplied to milestone gates. */
function legacyPortInferenceMilestoneGate(input: {
  milestoneId: string | null;
  urlEventId: string | null;
  activeScopeEventId: string;
  port: number;
}): boolean {
  if (!input.milestoneId?.trim()) return false;
  const portEvent = input.port >= 5111 ? `Event_${input.port - 5110}` : null;
  const eventId = resolveAuthoritativeEventIdFromParts(
    input.urlEventId,
    portEvent,
    input.activeScopeEventId,
  );
  return eventIdMatchesDedicatedPort(eventId, input.port);
}

describe('milestonePartitionDeepLinkAuthorized', () => {
  it('repro: legacy port-inference gate wrongly authorizes :5111 + activeScope Event_2', () => {
    const input = {
      milestoneId: 'milestone1_arc1',
      urlEventId: null,
      activeScopeEventId: 'Event_2',
      port: 5111,
    };
    assert.equal(legacyPortInferenceMilestoneGate(input), true, 'legacy gate bug repro');
    assert.equal(partitionGate(input), false, 'partition resolver must reject');
  });

  it('repro: legacy port-inference gate wrongly authorizes :5112 + activeScope Event_3', () => {
    const input = {
      milestoneId: 'milestone1_arc1',
      urlEventId: null,
      activeScopeEventId: 'Event_3',
      port: 5112,
    };
    assert.equal(legacyPortInferenceMilestoneGate(input), true, 'legacy gate bug repro');
    assert.equal(partitionGate(input), false, 'partition resolver must reject');
  });

  it('authorizes :5112 + ?event=Event_2 + milestone', () => {
    assert.equal(
      partitionGate({
        milestoneId: 'milestone1_arc1',
        urlEventId: 'Event_2',
        activeScopeEventId: 'Event_2',
        port: 5112,
      }),
      true,
    );
  });

  it('authorizes :5112 + activeScope Event_2 + ?milestone= only', () => {
    assert.equal(
      partitionGate({
        milestoneId: 'milestone1_arc1',
        urlEventId: null,
        activeScopeEventId: 'Event_2',
        port: 5112,
      }),
      true,
    );
  });

  it('rejects :5112 + ?event=Event_3 + milestone (URL contradicts port)', () => {
    assert.equal(
      partitionGate({
        milestoneId: 'milestone1_arc1',
        urlEventId: 'Event_3',
        activeScopeEventId: 'Event_2',
        port: 5112,
      }),
      false,
    );
  });

  it('rejects missing milestone id', () => {
    assert.equal(
      partitionGate({
        milestoneId: null,
        urlEventId: 'Event_2',
        activeScopeEventId: 'Event_2',
        port: 5112,
      }),
      false,
    );
  });

  it('eventIdMatchesDedicatedPort maps Event_2 ↔ 5112', () => {
    assert.equal(eventIdMatchesDedicatedPort('Event_2', 5112), true);
    assert.equal(eventIdMatchesDedicatedPort('Event_2', 5111), false);
  });
});

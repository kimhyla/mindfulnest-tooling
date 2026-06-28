import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  isSessionFresh,
  sessionHasReadyCache,
  resetSessionMeta,
  type SessionSliceMeta,
} from '../sessionCacheCore.ts';
import { bgSessionKey, mapSessionKey, storyboardSessionKey } from '../producerSessionKeys.ts';

describe('producerSessionKeys', () => {
  it('bgSessionKey joins event and video role', () => {
    assert.equal(bgSessionKey('Event_2', 'intro'), 'Event_2|intro');
  });

  it('mapSessionKey is event id', () => {
    assert.equal(mapSessionKey('Event_2'), 'Event_2');
  });

  it('storyboardSessionKey includes project type', () => {
    assert.equal(
      storyboardSessionKey('Event_2', 'event', null),
      'Event_2|event|',
    );
  });
});

describe('sessionCacheCore', () => {
  it('sessionHasReadyCache requires ready status and payload', () => {
    assert.equal(sessionHasReadyCache('ready', true), true);
    assert.equal(sessionHasReadyCache('loading', true), false);
    assert.equal(sessionHasReadyCache('ready', false), false);
  });

  it('isSessionFresh respects window', () => {
    const now = Date.now();
    assert.equal(isSessionFresh(now - 1000, 5000), true);
    assert.equal(isSessionFresh(now - 10000, 5000), false);
  });

  it('resetSessionMeta clears slice', () => {
    const meta: SessionSliceMeta = {
      status: 'ready',
      error: 'x',
      fetchedAt: Date.now(),
      inflight: null,
    };
    resetSessionMeta(meta);
    assert.equal(meta.status, 'idle');
    assert.equal(meta.error, null);
    assert.equal(meta.fetchedAt, 0);
  });
});

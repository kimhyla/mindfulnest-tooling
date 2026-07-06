import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  pausedPlayheadHoldMs,
  resolvePlaybackAuthorityMs,
  shouldClearPlaybackAnchor,
  shouldReassertPlayheadFromAuthority,
} from '../waveformPlaybackAnchor.ts';

describe('WTA32_PLAYBACK_ANCHOR_V1', () => {
  it('resolvePlaybackAuthorityMs prefers anchor during early play', () => {
    assert.equal(resolvePlaybackAuthorityMs(115_100, 1166), 115_100);
    assert.equal(resolvePlaybackAuthorityMs(null, 1166), 1166);
  });

  it('shouldReassertPlayheadFromAuthority — Event_3 stem repro', () => {
    assert.equal(shouldReassertPlayheadFromAuthority(115_100, 1166), true);
    assert.equal(shouldReassertPlayheadFromAuthority(115_100, 20_000), false);
    assert.equal(shouldReassertPlayheadFromAuthority(400, 0), false);
  });

  it('shouldClearPlaybackAnchor when WS caught up', () => {
    assert.equal(shouldClearPlaybackAnchor(100_000, 90_000), true);
    assert.equal(shouldClearPlaybackAnchor(100_000, 10_000), false);
    assert.equal(shouldClearPlaybackAnchor(null, 50_000), false);
  });

  it('pausedPlayheadHoldMs never drops positive hold (ac59914 bounce class)', () => {
    assert.equal(pausedPlayheadHoldMs(0, 115_100, 115_100), 115_100);
    assert.equal(pausedPlayheadHoldMs(0, 0, 115_100), 115_100);
    assert.equal(pausedPlayheadHoldMs(80_000, 115_100, null), 115_100);
    assert.equal(pausedPlayheadHoldMs(0, 0, null), 0);
  });

  it('matrix — legacy scrub must not block reassert after media advances', () => {
    const anchor = 115_100;
    const wsEarly = 1166;
    const auth = resolvePlaybackAuthorityMs(anchor, wsEarly);
    assert.equal(shouldReassertPlayheadFromAuthority(auth, wsEarly), true);
    assert.equal(shouldClearPlaybackAnchor(anchor, wsEarly), false);
    const wsLate = 100_000;
    assert.equal(shouldReassertPlayheadFromAuthority(auth, wsLate), false);
    assert.equal(shouldClearPlaybackAnchor(anchor, wsLate), true);
  });
});

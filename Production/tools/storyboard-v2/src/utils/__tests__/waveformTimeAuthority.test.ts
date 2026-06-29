import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createWaveformTimeAuthority } from '../waveformTimeAuthority.ts';

describe('waveformTimeAuthority', () => {
  it('preserveAcrossRemount keeps scrubbed playhead', () => {
    const ta = createWaveformTimeAuthority();
    ta.setDurationMs(30_000);
    ta.scrubToMs(12_500);
    ta.preserveAcrossRemount();
    assert.equal(ta.restoreAfterRemount(), 12_500);
  });

  it('user seek to zero clears preserve on remount', () => {
    const ta = createWaveformTimeAuthority();
    ta.setDurationMs(30_000);
    ta.scrubToMs(12_500);
    ta.scrubToMs(0);
    ta.preserveAcrossRemount();
    assert.equal(ta.restoreAfterRemount(), 0);
  });

  it('onPlaybackStart clears paused scrub authority', () => {
    const ta = createWaveformTimeAuthority();
    ta.setDurationMs(30_000);
    ta.scrubToMs(0);
    ta.onPlaybackStart();
    ta.scrubToMs(8000);
    ta.preserveAcrossRemount();
    assert.equal(ta.restoreAfterRemount(), 8000);
  });
});

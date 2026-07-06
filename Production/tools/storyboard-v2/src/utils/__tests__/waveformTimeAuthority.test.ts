import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createWaveformTimeAuthority, timelineRelXFromClientX } from '../waveformTimeAuthority.ts';

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

  it('resolvePausedPlayheadMs ignores stale media clock at 0 after scrub', () => {
    let t = 1000;
    const ta = createWaveformTimeAuthority(0, 30_000, () => t);
    ta.scrubToMs(12_500);
    assert.equal(ta.resolvePausedPlayheadMs(0), 12_500);
    t += 800;
    assert.equal(ta.resolvePausedPlayheadMs(0), 12_500);
    t += 100;
    assert.equal(ta.resolvePausedPlayheadMs(0), 12_500);
  });

  it('endDragSeek extends paused authority through hold window', () => {
    let t = 5000;
    const ta = createWaveformTimeAuthority(0, 30_000, () => t);
    ta.beginDragSeek();
    ta.endDragSeek(15_000);
    t += 100;
    assert.equal(ta.resolvePausedPlayheadMs(0), 15_000);
    t += 700;
    assert.equal(ta.resolvePausedPlayheadMs(0), 15_000);
  });

  it('resolvePausedPlayheadMs keeps scrub when legacy scrub ref cleared but playheadMs set', () => {
    const ta = createWaveformTimeAuthority(0, 30_000);
    ta.endDragSeek(12_000);
    assert.equal(ta.resolvePausedPlayheadMs(0, null), 12_000);
  });

  it('resolvePausedPlayheadMs prefers playhead at stale zero; legacy only while media ~0 (WTA-32)', () => {
    const ta = createWaveformTimeAuthority(0, 163_550);
    ta.scrubToMs(115_100);
    assert.equal(ta.resolvePausedPlayheadMs(0, null), 115_100);
    assert.equal(ta.resolvePausedPlayheadMs(0, 115_100), 115_100);
    assert.equal(ta.resolvePausedPlayheadMs(5000, null), 5000);
    assert.equal(ta.resolvePausedPlayheadMs(8000, 115_100), 8000);
    assert.equal(ta.resolvePausedPlayheadMs(40, 115_100), 115_100);
  });

  it('timelineRelXFromClientX respects track insets', () => {
    const box = { left: 100, width: 200 };
    assert.equal(timelineRelXFromClientX(box, 100), 0);
    assert.equal(timelineRelXFromClientX(box, 300), 1);
    assert.ok(Math.abs(timelineRelXFromClientX(box, 200) - 0.5) < 0.01);
  });
});

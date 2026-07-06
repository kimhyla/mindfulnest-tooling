import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  assessWaveformInteractionReady,
  waveformDropRejectMessage,
} from '../waveformInteractionPolicy.ts';

describe('waveformInteractionPolicy', () => {
  it('rejects drop when not ready (WTA-5)', () => {
    const out = assessWaveformInteractionReady({
      isReady: false,
      durationMs: 120_000,
      hasAudioSrc: true,
    });
    assert.equal(out.ok, false);
    if (!out.ok) {
      assert.equal(out.reason, 'waveform_loading');
      assert.match(out.userMessage, /loading/i);
    }
  });

  it('rejects drop when duration zero after remount (WTA-13 class)', () => {
    const out = assessWaveformInteractionReady({
      isReady: true,
      durationMs: 0,
      hasAudioSrc: true,
    });
    assert.equal(out.ok, false);
    if (!out.ok) assert.equal(out.reason, 'no_duration');
  });

  it('accepts when ready with duration', () => {
    const out = assessWaveformInteractionReady({
      isReady: true,
      durationMs: 170_000,
      hasAudioSrc: true,
    });
    assert.equal(out.ok, true);
    if (out.ok) assert.equal(out.durationMs, 170_000);
  });

  it('waveformDropRejectMessage covers all reasons', () => {
    assert.match(waveformDropRejectMessage('waveform_loading'), /loading/i);
    assert.match(waveformDropRejectMessage('no_duration'), /timeline length/i);
    assert.match(waveformDropRejectMessage('no_surface'), /audio/i);
  });
});

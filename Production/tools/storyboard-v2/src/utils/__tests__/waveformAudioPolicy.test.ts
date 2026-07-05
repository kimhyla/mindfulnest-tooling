import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { waveformAudioFromSlice, waveformAudioForPhase } from '../waveformAudioPolicy.ts';

describe('waveformAudioPolicy', () => {
  it('prefers fresh stem over stale lipsync (SEEK-5 stem review)', () => {
    const src = waveformAudioFromSlice({
      voice_stem_file: 'phase_b_voice_stem.mp3',
      lipsync_file: 'phase_b_lipsync.mp4',
      lipsync_requires_regen: true,
      voice_stem_mtime: 2000,
      lipsync_mtime: 1000,
    });
    assert.deepEqual(src, { name: 'phase_b_voice_stem.mp3', label: 'stem' });
  });

  it('never returns stitched from waveformAudioFromSlice', () => {
    const src = waveformAudioFromSlice({
      stitched_file: 'phase_a_stitched.mp4',
      voice_stem_file: 'phase_a_stem.mp3',
    });
    assert.equal(src?.label, 'stem');
    assert.notEqual(src?.name, 'phase_a_stitched.mp4');
  });

  it('waveformAudioForPhase never returns stitched on Phase A (SEEK-5)', () => {
    const src = waveformAudioForPhase(
      {
        stitched_file: 'phase_a_stitched.mp4',
        lipsync_file: 'phase_a_lipsync.mp4',
        lipsync_mtime: 1000,
        stitched_mtime: 2000,
      },
      'a',
    );
    assert.equal(src?.label, 'lipsync');
    assert.notEqual(src?.name, 'phase_a_stitched.mp4');
  });
});

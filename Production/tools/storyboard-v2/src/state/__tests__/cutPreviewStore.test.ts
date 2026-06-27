import { describe, expect, it } from 'vitest';
import {
  _resetCutPreviewStoreForTesting,
  forgetCutPreviewsForBeat,
  recallCutPreviewUrl,
  rememberCutPreviewUrl,
} from '../state/cutPreviewStore';

describe('cutPreviewStore', () => {
  it('remembers and recalls preview URLs across keys', () => {
    _resetCutPreviewStoreForTesting();
    rememberCutPreviewUrl('beat_a', 0, '/clips/a.mp4', 1.0, 2.5, 'http://localhost/preview.mp4');
    expect(recallCutPreviewUrl('beat_a', 0, '/clips/a.mp4', 1.0, 2.5)).toBe('http://localhost/preview.mp4');
    expect(recallCutPreviewUrl('beat_a', 0, '/clips/a.mp4', 0.0, 2.5)).toBeNull();
  });

  it('forgets all previews for a beat', () => {
    _resetCutPreviewStoreForTesting();
    rememberCutPreviewUrl('beat_a', 0, '/clips/a.mp4', 1.0, 2.5, 'http://localhost/a.mp4');
    rememberCutPreviewUrl('beat_a', 1, '/clips/b.mp4', 0.5, 1.0, 'http://localhost/b.mp4');
    forgetCutPreviewsForBeat('beat_a');
    expect(recallCutPreviewUrl('beat_a', 0, '/clips/a.mp4', 1.0, 2.5)).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';
import {
  _resetCutPreviewStoreForTesting,
  enqueueAutoCutPreview,
  forgetCutPreviewsForBeat,
  recallCutPreviewUrl,
  rememberCutPreviewUrl,
} from '../cutPreviewStore';

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

  it('serializes auto-preview jobs (TRIM_PREVIEW_SERIAL_V1)', async () => {
    _resetCutPreviewStoreForTesting();
    const order: number[] = [];
    const slow = (n: number, ms: number) =>
      enqueueAutoCutPreview(
        () =>
          new Promise<void>((resolve) => {
            setTimeout(() => {
              order.push(n);
              resolve();
            }, ms);
          }),
      );
    await Promise.all([slow(1, 40), slow(2, 5), slow(3, 5)]);
    expect(order).toEqual([1, 2, 3]);
  });
});

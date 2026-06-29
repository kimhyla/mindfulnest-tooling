import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergeBeatsOnSessionHydrate } from '../bgSessionBeatMerge.ts';

describe('BG-SESSION-TERMINAL-1 — mergeBeatsOnSessionHydrate', () => {
  it('preserves locked ref boxes on session refresh', () => {
    const local = [{
      beat_id: 'b1',
      reference_image_locked: true,
      reference_image: { abs_path: '/local/char.png' },
    }];
    const server = [{
      beat_id: 'b1',
      reference_image_locked: true,
      reference_image: { abs_path: '/server/stale.png' },
    }];
    const merged = mergeBeatsOnSessionHydrate(local, server);
    assert.equal(merged[0]?.reference_image?.abs_path, '/local/char.png');
  });
});

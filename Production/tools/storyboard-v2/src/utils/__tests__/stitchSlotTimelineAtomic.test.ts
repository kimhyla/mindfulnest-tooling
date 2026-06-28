import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const tabPath = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../components/StitcherTab.tsx',
);
const hydratePath = join(
  dirname(fileURLToPath(import.meta.url)),
  '../stitchJobMediaHydrate.ts',
);

describe('STITCH_SLOT_TIMELINE_ATOMIC_V1 client rail', () => {
  it('StitcherTab uses stitchSlotTimelineDurMs for multiphase rail (not raw video_dur_ms ?? 30s)', () => {
    const src = readFileSync(tabPath, 'utf8');
    assert.match(src, /STITCH_SLOT_TIMELINE_ATOMIC_V1/);
    assert.match(src, /stitchSlotTimelineDurMs\(slot, DEFAULT_SLOT_DUR_MS\)/);
    assert.doesNotMatch(src, /slot\?\.video_dur_ms \?\? DEFAULT_SLOT_DUR_MS/);
  });

  it('stitchJobMediaHydrate defines stitchSlotTimelineDurMs mux-first contract', () => {
    const src = readFileSync(hydratePath, 'utf8');
    assert.match(src, /export function stitchSlotTimelineDurMs/);
    assert.match(src, /mux_preview_duration_ms/);
    assert.match(src, /STITCH_SFX_PLAYBACK_TRUTH_V1/);
  });
});

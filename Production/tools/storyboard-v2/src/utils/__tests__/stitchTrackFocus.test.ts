import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  legacyResolveStitchViewerSlot,
  pickTrackSlotForLayout,
  readPersistedTrackSlot,
  resolveStitchViewerSlot,
  stitchTrackFocusStorageKey,
  writePersistedTrackSlot,
} from '../stitchTrackFocus.ts';

describe('STITCH_VIEWER_SLOT_LAYOUT_V1 — repro', () => {
  it('legacy formula returns intro when stale focus bleeds into milestone layout (bug class)', () => {
    const bug = legacyResolveStitchViewerSlot('intro', 'standalone', true);
    assert.equal(bug, 'intro');
  });

  it('layout-validated resolve ignores intro when layout is standalone only', () => {
    const slot = resolveStitchViewerSlot({
      layoutSlotKeys: ['standalone'],
      trackFocusedSlot: 'intro',
    });
    assert.equal(slot, 'standalone');
  });

  it('layout-validated resolve keeps focus when slot is in layout', () => {
    assert.equal(
      resolveStitchViewerSlot({
        layoutSlotKeys: ['intro', 'phase_a', 'phase_b', 'resolution'],
        trackFocusedSlot: 'phase_b',
      }),
      'phase_b',
    );
  });

  it('invalid focus falls back to first layout slot', () => {
    assert.equal(
      resolveStitchViewerSlot({
        layoutSlotKeys: ['intro', 'phase_a'],
        trackFocusedSlot: 'resolution',
      }),
      'intro',
    );
  });
});

describe('stitchTrackFocusStorageKey', () => {
  it('namespaces milestone separately from event on same Event_2', () => {
    assert.notEqual(
      stitchTrackFocusStorageKey('Event_2'),
      stitchTrackFocusStorageKey('milestone:milestone1_arc1'),
    );
  });
});

describe('pickTrackSlotForLayout', () => {
  it('milestone layout prefers standalone with video', () => {
    const slots = {
      standalone: { video_path: 'Production/Milestones/m1/assembled/x.mp4' },
    };
    const picked = pickTrackSlotForLayout(
      slots,
      ['standalone'],
      'milestone:m1',
      'intro',
    );
    assert.equal(picked, 'standalone');
  });
});

describe('readPersistedTrackSlot round-trip', () => {
  it('stores under stitchSessionKey not bare eventId', () => {
    if (typeof globalThis.localStorage === 'undefined') {
      // node test env without localStorage — skip
      return;
    }
    writePersistedTrackSlot('milestone:test_m', 'standalone');
    assert.equal(readPersistedTrackSlot('milestone:test_m'), 'standalone');
    assert.equal(readPersistedTrackSlot('Event_2'), null);
    writePersistedTrackSlot('milestone:test_m', null);
  });
});

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  bindWaveformSeekController,
  WAVEFORM_DRAG_SEEK_BOUND,
} from '../waveformSeekController.ts';
import { createWaveformTimeAuthority } from '../waveformTimeAuthority.ts';

describe('waveformSeekController', () => {
  it('bindWaveformSeekController sets data-drag-seek-bound marker', () => {
    const attrs: Record<string, string | null> = {};
    const wrapper = {
      addEventListener: () => {},
      removeEventListener: () => {},
      setAttribute: (key: string, value: string) => {
        attrs[key] = value;
      },
      removeAttribute: (key: string) => {
        delete attrs[key];
      },
      getAttribute: (key: string) => attrs[key] ?? null,
      getBoundingClientRect: () => ({ left: 0, width: 100, top: 0, height: 40 }),
      setPointerCapture: () => {},
    } as unknown as HTMLElement;

    const ta = createWaveformTimeAuthority();
    ta.setDurationMs(10_000);
    const cleanup = bindWaveformSeekController({
      wrapper,
      wsRef: { current: null },
      timeAuthority: ta,
      isDraggingSeekRef: { current: false },
      lastScrubMsRef: { current: null },
      linkedVideoRef: { current: null },
      useSharedLinkedMediaRef: { current: false },
      onWaveformClickRef: { current: undefined },
      withLinkedVideoSuppress: (fn) => fn(),
      publishPlayheadMs: () => {},
      resolveDurationMs: () => 10_000,
      displayOnly: false,
    });
    assert.equal(wrapper.getAttribute('data-drag-seek-bound'), WAVEFORM_DRAG_SEEK_BOUND);
    cleanup();
    assert.equal(wrapper.getAttribute('data-drag-seek-bound'), null);
  });
});

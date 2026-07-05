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

  it('WTA-12 endDragSeek keeps scrub position when resolveDurationMs flickers to 0 on release', () => {
    const prevRaf = globalThis.requestAnimationFrame;
    globalThis.requestAnimationFrame = (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    };
    try {
    const handlers: Record<string, EventListener> = {};
    const wrapper = {
      addEventListener: (type: string, fn: EventListener) => {
        handlers[type] = fn;
      },
      removeEventListener: () => {},
      setAttribute: () => {},
      removeAttribute: () => {},
      getAttribute: () => null,
      getBoundingClientRect: () => ({ left: 0, width: 100, top: 0, height: 40 }),
      setPointerCapture: () => {},
    } as unknown as HTMLElement;

    const seekCalls: number[] = [];
    const published: number[] = [];
    const ws = {
      seekTo: (rel: number) => seekCalls.push(rel),
    };
    const ta = createWaveformTimeAuthority();
    ta.setDurationMs(100_000);
    let resolveDur = 100_000;
    const lastScrubMsRef = { current: null as number | null };
    const isDraggingSeekRef = { current: false };

    bindWaveformSeekController({
      wrapper,
      wsRef: { current: ws as never },
      timeAuthority: ta,
      isDraggingSeekRef,
      lastScrubMsRef,
      linkedVideoRef: { current: null },
      useSharedLinkedMediaRef: { current: false },
      onWaveformClickRef: { current: undefined },
      withLinkedVideoSuppress: (fn) => fn(),
      publishPlayheadMs: (ms) => published.push(ms),
      resolveDurationMs: () => resolveDur,
      displayOnly: false,
    });

    const down = handlers.pointerdown as (e: PointerEvent) => void;
    const move = handlers.pointermove as (e: PointerEvent) => void;
    const up = handlers.pointerup as (e: PointerEvent) => void;
    const mk = (type: string, x: number, id = 1): PointerEvent =>
      ({
        type,
        clientX: x + 8,
        pointerId: id,
        target: { closest: () => null },
      }) as PointerEvent;

    down(mk('pointerdown', 50, 7));
    move(mk('pointermove', 70, 7));
    resolveDur = 0;
    up(mk('pointerup', 70, 7));

    assert.ok(lastScrubMsRef.current != null && lastScrubMsRef.current > 50_000);
    assert.ok(ta.getPlayheadMs() > 50_000);
    assert.ok(published.some((ms) => ms > 50_000));
    assert.ok(seekCalls.some((rel) => rel > 0.5));
    } finally {
      globalThis.requestAnimationFrame = prevRaf;
    }
  });
});

/**
 * INTERACTION_PLATFORM_V1 — capture-phase HTML5 drop on composite surfaces.
 * WaveSurfer canvases and nested children receive dragover before bubble handlers;
 * bindDropTargetCapture on the wrapper fixes silent drop rejection (DROP-CAPTURE-1).
 */
import { useEffect } from 'preact/hooks';
import type { RefObject } from 'preact';
import { bindDropTargetCapture, type DropTargetHandlers } from '../utils/dragdrop';

export function useDropTargetCapture(
  ref: RefObject<HTMLElement | null>,
  handlers: DropTargetHandlers,
  deps: unknown[],
): void {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    return bindDropTargetCapture(el, handlers);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies explicit deps
  }, [ref, handlers, ...deps]);
}

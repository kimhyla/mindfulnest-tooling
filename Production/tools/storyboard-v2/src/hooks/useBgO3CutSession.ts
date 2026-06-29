/**
 * useBgO3CutSession — OPERATOR_EDIT_AUTHORITY_V1 pending keep-window on BgOptionTile.
 */
import { useCallback, useRef, useState } from 'preact/hooks';
import {
  clearBgO3CutDragActive,
  markBgO3CutDragActive,
} from '../utils/bgO3CutSession.ts';

export const BG_O3_CUT_SESSION_V1 = 'BG_O3_CUT_SESSION_V1';

export interface BgO3CutSessionController {
  pendingCut: { startS: number; endS: number } | null;
  setPendingCut: (cut: { startS: number; endS: number } | null) => void;
  onOverlayDragStart: () => void;
  onOverlayDragEnd: () => void;
  clearPendingCut: () => void;
}

export function useBgO3CutSession(
  beatId: string,
  optionIndex: number,
): BgO3CutSessionController {
  const [pendingCut, setPendingCutState] = useState<{ startS: number; endS: number } | null>(null);
  const dragDepthRef = useRef(0);

  const onOverlayDragStart = useCallback(() => {
    dragDepthRef.current += 1;
    markBgO3CutDragActive(beatId, optionIndex);
  }, [beatId, optionIndex]);

  const onOverlayDragEnd = useCallback(() => {
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      clearBgO3CutDragActive(beatId, optionIndex);
    }
  }, [beatId, optionIndex]);

  const setPendingCut = useCallback((cut: { startS: number; endS: number } | null) => {
    setPendingCutState(cut);
  }, []);

  const clearPendingCut = useCallback(() => {
    setPendingCutState(null);
    dragDepthRef.current = 0;
    clearBgO3CutDragActive(beatId, optionIndex);
  }, [beatId, optionIndex]);

  return {
    pendingCut,
    setPendingCut,
    onOverlayDragStart,
    onOverlayDragEnd,
    clearPendingCut,
  };
}

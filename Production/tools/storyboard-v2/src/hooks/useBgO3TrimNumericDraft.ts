/**
 * useBgO3TrimNumericDraft — OPERATOR_EDIT_AUTHORITY_V1 numeric trim drafts on BgOptionTile.
 * Poll/session refresh must not clobber in-progress trim inputs.
 */
import { useCallback, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { mergeOperatorFieldOnHydrate } from '../utils/operatorEditMerge.ts';

export const BG_O3_TRIM_NUMERIC_DRAFT_V1 = 'BG_O3_TRIM_NUMERIC_DRAFT_V1';

export interface BgO3TrimNumericDraftController {
  trimStartDraft: string;
  trimBackDraft: string;
  trimDraftDirty: boolean;
  setTrimStartDraft: (value: string) => void;
  setTrimBackDraft: (value: string) => void;
  onTrimStartFocus: () => void;
  onTrimStartBlur: () => void;
  onTrimBackFocus: () => void;
  onTrimBackBlur: () => void;
  clearDirtyAfterSave: () => void;
}

function draftDirty(
  startDraft: string,
  backDraft: string,
  savedStart: number,
  savedBack: number,
): boolean {
  return startDraft !== String(savedStart) || backDraft !== String(savedBack ?? 0);
}

export function useBgO3TrimNumericDraft(
  beatId: string,
  optionIndex: number,
  savedTrimStart: number,
  savedTrimBack: number | null | undefined,
): BgO3TrimNumericDraftController {
  const savedStart = savedTrimStart || 0;
  const savedBack = savedTrimBack ?? 0;
  const startFocusedRef = useRef(false);
  const backFocusedRef = useRef(false);
  const startDirtyRef = useRef(false);
  const backDirtyRef = useRef(false);
  const applyInFlightRef = useRef(false);
  const [trimStartDraft, setTrimStartDraftState] = useState(String(savedStart));
  const [trimBackDraft, setTrimBackDraftState] = useState(String(savedBack));

  const isEditingStart = useCallback(
    () => startFocusedRef.current || startDirtyRef.current || applyInFlightRef.current,
    [],
  );
  const isEditingBack = useCallback(
    () => backFocusedRef.current || backDirtyRef.current || applyInFlightRef.current,
    [],
  );

  useLayoutEffect(() => {
    const merged = mergeOperatorFieldOnHydrate(
      trimStartDraft,
      String(savedStart),
      { patchInFlight: isEditingStart() },
    );
    if (merged !== trimStartDraft) {
      setTrimStartDraftState(merged ?? String(savedStart));
      if (!isEditingStart()) startDirtyRef.current = false;
    }
  }, [savedStart, beatId, optionIndex]);

  useLayoutEffect(() => {
    const merged = mergeOperatorFieldOnHydrate(
      trimBackDraft,
      String(savedBack),
      { patchInFlight: isEditingBack() },
    );
    if (merged !== trimBackDraft) {
      setTrimBackDraftState(merged ?? String(savedBack));
      if (!isEditingBack()) backDirtyRef.current = false;
    }
  }, [savedBack, beatId, optionIndex]);

  const setTrimStartDraft = useCallback((value: string) => {
    startDirtyRef.current = true;
    setTrimStartDraftState(value);
  }, []);

  const setTrimBackDraft = useCallback((value: string) => {
    backDirtyRef.current = true;
    setTrimBackDraftState(value);
  }, []);

  const onTrimStartFocus = useCallback(() => {
    startFocusedRef.current = true;
  }, []);

  const onTrimStartBlur = useCallback(() => {
    startFocusedRef.current = false;
  }, []);

  const onTrimBackFocus = useCallback(() => {
    backFocusedRef.current = true;
  }, []);

  const onTrimBackBlur = useCallback(() => {
    backFocusedRef.current = false;
  }, []);

  const clearDirtyAfterSave = useCallback(() => {
    applyInFlightRef.current = false;
    startDirtyRef.current = false;
    backDirtyRef.current = false;
    setTrimStartDraftState(String(savedStart));
    setTrimBackDraftState(String(savedBack));
  }, [savedBack, savedStart]);

  return {
    trimStartDraft,
    trimBackDraft,
    trimDraftDirty: draftDirty(trimStartDraft, trimBackDraft, savedStart, savedBack),
    setTrimStartDraft,
    setTrimBackDraft,
    onTrimStartFocus,
    onTrimStartBlur,
    onTrimBackFocus,
    onTrimBackBlur,
    clearDirtyAfterSave,
  };
}

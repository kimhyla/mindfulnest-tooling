/**
 * useStoryboardTrimFields — OPERATOR_EDIT_AUTHORITY_V1 LD-756 trim + delay inputs.
 */
import { useCallback, useLayoutEffect, useRef, useState } from 'preact/hooks';
import { mergeOperatorFieldOnHydrate } from '../utils/operatorEditMerge.ts';

export const STORYBOARD_TRIM_FIELDS_V1 = 'STORYBOARD_TRIM_FIELDS_V1';

export interface StoryboardTrimBeatSource {
  phase_1?: {
    trim_start?: number | null;
    trim_back?: number | null;
    trim_end?: number | null;
    audio_delay?: number | string | null;
  } | null;
  trim_in?: number | null;
  trim_out?: number | null | string;
  audio_delay?: number | string | null;
  delay_seconds?: number | string | null;
  audio_duration_s?: number | null;
}

function readDelaySec(beat: StoryboardTrimBeatSource): string {
  return String(
    beat.phase_1?.audio_delay
      ?? beat.audio_delay
      ?? beat.delay_seconds
      ?? '0.0',
  );
}

function readTrimFrontSec(beat: StoryboardTrimBeatSource): string {
  const start = beat.phase_1?.trim_start ?? beat.trim_in;
  return start === null || start === undefined ? '0.0' : String(start);
}

function readTrimBackSec(beat: StoryboardTrimBeatSource): string {
  const trimBack = beat.phase_1?.trim_back;
  if (typeof trimBack === 'number' && Number.isFinite(trimBack) && trimBack > 0) {
    return trimBack.toFixed(2);
  }
  const trimEnd = beat.phase_1?.trim_end ?? beat.trim_out;
  if (trimEnd === null || trimEnd === undefined || trimEnd === 'full') {
    return '0.0';
  }
  const dur = beat.audio_duration_s;
  if (typeof dur === 'number' && Number.isFinite(dur)) {
    return Math.max(0, dur - Number(trimEnd)).toFixed(2);
  }
  return '0.0';
}

export interface StoryboardTrimFieldsController {
  trimFrontSec: string;
  trimBackSec: string;
  delaySec: string;
  setTrimFrontSec: (v: string) => void;
  setTrimBackSec: (v: string) => void;
  setDelaySec: (v: string) => void;
  onTrimFrontFocus: () => void;
  onTrimFrontBlur: () => void;
  onTrimBackFocus: () => void;
  onTrimBackBlur: () => void;
  onDelayFocus: () => void;
  onDelayBlur: () => void;
}

export function useStoryboardTrimFields(
  beatId: string,
  beat: StoryboardTrimBeatSource,
): StoryboardTrimFieldsController {
  const serverFront = readTrimFrontSec(beat);
  const serverBack = readTrimBackSec(beat);
  const serverDelay = readDelaySec(beat);

  const frontFocusedRef = useRef(false);
  const backFocusedRef = useRef(false);
  const delayFocusedRef = useRef(false);
  const frontDirtyRef = useRef(false);
  const backDirtyRef = useRef(false);
  const delayDirtyRef = useRef(false);

  const [trimFrontSec, setTrimFrontSecState] = useState(serverFront);
  const [trimBackSec, setTrimBackSecState] = useState(serverBack);
  const [delaySec, setDelaySecState] = useState(serverDelay);

  const isEditingFront = useCallback(
    () => frontFocusedRef.current || frontDirtyRef.current,
    [],
  );
  const isEditingBack = useCallback(
    () => backFocusedRef.current || backDirtyRef.current,
    [],
  );
  const isEditingDelay = useCallback(
    () => delayFocusedRef.current || delayDirtyRef.current,
    [],
  );

  useLayoutEffect(() => {
    const merged = mergeOperatorFieldOnHydrate(
      trimFrontSec,
      serverFront,
      { patchInFlight: isEditingFront() },
    );
    if (merged !== trimFrontSec) {
      setTrimFrontSecState(merged ?? serverFront);
      if (!isEditingFront()) frontDirtyRef.current = false;
    }
  }, [serverFront, beatId, beat.phase_1?.trim_start, beat.trim_in]);

  useLayoutEffect(() => {
    const merged = mergeOperatorFieldOnHydrate(
      trimBackSec,
      serverBack,
      { patchInFlight: isEditingBack() },
    );
    if (merged !== trimBackSec) {
      setTrimBackSecState(merged ?? serverBack);
      if (!isEditingBack()) backDirtyRef.current = false;
    }
  }, [
    serverBack,
    beatId,
    beat.phase_1?.trim_back,
    beat.phase_1?.trim_end,
    beat.trim_out,
    beat.audio_duration_s,
  ]);

  useLayoutEffect(() => {
    const merged = mergeOperatorFieldOnHydrate(
      delaySec,
      serverDelay,
      { patchInFlight: isEditingDelay() },
    );
    if (merged !== delaySec) {
      setDelaySecState(merged ?? serverDelay);
      if (!isEditingDelay()) delayDirtyRef.current = false;
    }
  }, [serverDelay, beatId, beat.phase_1?.audio_delay, beat.audio_delay, beat.delay_seconds]);

  const setTrimFrontSec = useCallback((v: string) => {
    frontDirtyRef.current = true;
    setTrimFrontSecState(v);
  }, []);

  const setTrimBackSec = useCallback((v: string) => {
    backDirtyRef.current = true;
    setTrimBackSecState(v);
  }, []);

  const setDelaySec = useCallback((v: string) => {
    delayDirtyRef.current = true;
    setDelaySecState(v);
  }, []);

  return {
    trimFrontSec,
    trimBackSec,
    delaySec,
    setTrimFrontSec,
    setTrimBackSec,
    setDelaySec,
    onTrimFrontFocus: useCallback(() => { frontFocusedRef.current = true; }, []),
    onTrimFrontBlur: useCallback(() => { frontFocusedRef.current = false; }, []),
    onTrimBackFocus: useCallback(() => { backFocusedRef.current = true; }, []),
    onTrimBackBlur: useCallback(() => { backFocusedRef.current = false; }, []),
    onDelayFocus: useCallback(() => { delayFocusedRef.current = true; }, []),
    onDelayBlur: useCallback(() => { delayFocusedRef.current = false; }, []),
  };
}

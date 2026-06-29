/**
 * usePhaseStemCut — PHASE_STEM_CUT_AUTHORITY_V1 client owner.
 * Stem cut geometry survives focus/visibility refresh when server omits cut fields.
 */
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { pathappPatch } from '../api/client';
import type { Scope } from '../state/scope';
import { mergeOperatorFieldOnHydrate } from '../utils/operatorEditMerge.ts';

export const PHASE_STEM_CUT_AUTHORITY_V1 = 'PHASE_STEM_CUT_AUTHORITY_V1';

export interface UsePhaseStemCutOptions {
  phase: 'a' | 'b';
  scope: Scope;
  onPatchError?: (message: string) => void;
}

export interface PhaseStemCutController {
  stemCutStartMs: number;
  stemCutEndMs: number;
  hasStemCut: boolean;
  adoptFromEventState: (state: Record<string, unknown>) => void;
  persistStemCut: (cutStartMs: number, cutEndMs: number) => Promise<boolean>;
  clearLocalCut: () => void;
}

function readCutFields(
  state: Record<string, unknown>,
  phase: 'a' | 'b',
): { startS?: number; endS?: number } {
  const prefix = `phase_${phase}_`;
  const startS = state[`${prefix}voice_stem_cut_start_s`] as number | undefined;
  const endS = state[`${prefix}voice_stem_cut_end_s`] as number | undefined;
  return { startS, endS };
}

export function usePhaseStemCut({
  phase,
  scope,
  onPatchError,
}: UsePhaseStemCutOptions): PhaseStemCutController {
  const startRef = useRef<number | undefined>(undefined);
  const endRef = useRef<number | undefined>(undefined);
  const patchInFlightRef = useRef(0);
  const [, bump] = useState(0);

  const syncRefs = useCallback((startS?: number, endS?: number) => {
    startRef.current = startS;
    endRef.current = endS;
    bump((n) => n + 1);
  }, []);

  useEffect(() => {
    syncRefs(undefined, undefined);
  }, [phase, scope.event_id, scope.version, syncRefs]);

  const adoptFromEventState = useCallback((state: Record<string, unknown>) => {
    const { startS: serverStart, endS: serverEnd } = readCutFields(state, phase);
    const opts = { patchInFlight: patchInFlightRef.current > 0 };
    const mergedStart = mergeOperatorFieldOnHydrate(startRef.current, serverStart, opts);
    const mergedEnd = mergeOperatorFieldOnHydrate(endRef.current, serverEnd, opts);
    syncRefs(mergedStart, mergedEnd);
  }, [phase, syncRefs]);

  const persistStemCut = useCallback(async (
    cutStartMs: number,
    cutEndMs: number,
  ): Promise<boolean> => {
    const startS = Math.round(cutStartMs) / 1000;
    const endS = Math.round(cutEndMs) / 1000;
    syncRefs(startS, endS);
    patchInFlightRef.current += 1;
    try {
      const startField = `phase_${phase}_voice_stem_cut_start_s`;
      const endField = `phase_${phase}_voice_stem_cut_end_s`;
      const legacyStart = `phase_${phase}_voice_stem_trim_start_s`;
      const legacyBack = `phase_${phase}_voice_stem_trim_back_s`;
      const [startRes, endRes] = await Promise.all([
        pathappPatch(scope, 'v2_module_patch', { field: startField, value: startS }),
        pathappPatch(scope, 'v2_module_patch', { field: endField, value: endS }),
        pathappPatch(scope, 'v2_module_patch', { field: legacyStart, value: 0 }),
        pathappPatch(scope, 'v2_module_patch', { field: legacyBack, value: 0 }),
      ]);
      if (!startRes.ok || !endRes.ok) {
        onPatchError?.(
          `✗ stem cut patch failed (HTTP ${startRes.status}/${endRes.status})`,
        );
        return false;
      }
      return true;
    } finally {
      patchInFlightRef.current = Math.max(0, patchInFlightRef.current - 1);
    }
  }, [onPatchError, phase, scope, syncRefs]);

  const clearLocalCut = useCallback(() => {
    syncRefs(undefined, undefined);
  }, [syncRefs]);

  const stemCutStartMs = Math.round((startRef.current ?? 0) * 1000);
  const stemCutEndMs = Math.round((endRef.current ?? 0) * 1000);
  const hasStemCut = stemCutEndMs > stemCutStartMs + 250;

  return {
    stemCutStartMs,
    stemCutEndMs,
    hasStemCut,
    adoptFromEventState,
    persistStemCut,
    clearLocalCut,
  };
}

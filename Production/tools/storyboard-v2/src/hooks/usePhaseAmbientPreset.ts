/**
 * usePhaseAmbientPreset — OPERATOR_EDIT_AUTHORITY_V1 scalar owner for ambient preset select.
 */
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { pathappPatch } from '../api/client';
import type { Scope } from '../state/scope';
import { mergeOperatorFieldOnHydrate } from '../utils/operatorEditMerge.ts';

export interface UsePhaseAmbientPresetOptions {
  phase: 'a' | 'b';
  scope: Scope;
  onPatchError?: (message: string) => void;
}

export interface PhaseAmbientPresetController {
  presetId: string;
  adoptFromEventState: (state: Record<string, unknown>) => void;
  pickPreset: (presetId: string) => Promise<boolean>;
}

function readPreset(state: Record<string, unknown>, phase: 'a' | 'b'): string | undefined {
  const v = state[`phase_${phase}_ambient_preset_id`];
  return typeof v === 'string' ? v : undefined;
}

export function usePhaseAmbientPreset({
  phase,
  scope,
  onPatchError,
}: UsePhaseAmbientPresetOptions): PhaseAmbientPresetController {
  const idRef = useRef<string>('');
  const patchInFlightRef = useRef(0);
  const [, bump] = useState(0);

  const sync = useCallback((id: string) => {
    idRef.current = id;
    bump((n) => n + 1);
  }, []);

  useEffect(() => {
    sync('');
  }, [phase, scope.event_id, sync]);

  const adoptFromEventState = useCallback((state: Record<string, unknown>) => {
    const serverId = readPreset(state, phase);
    const merged = mergeOperatorFieldOnHydrate(
      idRef.current || undefined,
      serverId,
      { patchInFlight: patchInFlightRef.current > 0 },
    );
    sync(merged ?? '');
  }, [phase, sync]);

  const pickPreset = useCallback(async (presetId: string): Promise<boolean> => {
    sync(presetId);
    patchInFlightRef.current += 1;
    const field = `phase_${phase}_ambient_preset_id`;
    try {
      const res = await pathappPatch(scope, 'v2_module_patch', {
        field,
        value: presetId,
      });
      if (!res.ok) {
        onPatchError?.(`✗ ${field} HTTP ${res.status}: ${res.error ?? ''}`);
      }
      return res.ok;
    } finally {
      patchInFlightRef.current = Math.max(0, patchInFlightRef.current - 1);
    }
  }, [onPatchError, phase, scope, sync]);

  return {
    presetId: idRef.current,
    adoptFromEventState,
    pickPreset,
  };
}

/**
 * usePhaseBaseClipPicker — OPERATOR_EDIT_AUTHORITY_V1 scalar owner for base clip selection.
 */
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import { pathappPatch } from '../api/client';
import type { Scope } from '../state/scope';
import { coercePhaseAArloBaseClipId } from '../phaseAArloContract';
import { coercePhaseBCedricBaseClipId } from '../phaseBCedricContract';
import { mergeOperatorFieldOnHydrate } from '../utils/operatorEditMerge.ts';

export interface UsePhaseBaseClipPickerOptions {
  phase: 'a' | 'b';
  scope: Scope;
  serverClipId?: string;
  onPatchError?: (message: string) => void;
}

export interface PhaseBaseClipPickerController {
  selectedClipId: string;
  adoptFromEventState: (state: Record<string, unknown>) => void;
  adoptServerClipId: (clipId: string | undefined) => void;
  pickClip: (clipId: string, field: string) => Promise<boolean>;
}

export function usePhaseBaseClipPicker({
  phase,
  scope,
  serverClipId,
  onPatchError,
}: UsePhaseBaseClipPickerOptions): PhaseBaseClipPickerController {
  const clipRef = useRef<string>('');
  const patchInFlightRef = useRef(0);
  const [selectedClipId, setSelectedClipId] = useState('');

  const sync = useCallback((id: string) => {
    clipRef.current = id;
    setSelectedClipId(id);
  }, []);

  useEffect(() => {
    sync('');
  }, [phase, scope.event_id, sync]);

  const adoptServerClipId = useCallback((clipId: string | undefined) => {
    const merged = mergeOperatorFieldOnHydrate(
      clipRef.current || undefined,
      clipId,
      { patchInFlight: patchInFlightRef.current > 0 },
    );
    if (merged !== undefined) sync(merged);
  }, [sync]);

  useEffect(() => {
    if (serverClipId !== undefined) adoptServerClipId(serverClipId);
  }, [serverClipId, adoptServerClipId]);

  const adoptFromEventState = useCallback((state: Record<string, unknown>) => {
    const field = phase === 'a'
      ? 'phase_a_chipper_sitting_clip_id'
      : 'phase_b_cedric_base_clip_id';
    if (!Object.prototype.hasOwnProperty.call(state, field)) {
      adoptServerClipId(undefined);
      return;
    }
    const raw = state[field];
    const serverId = typeof raw === 'string' && raw.trim() ? raw.trim() : undefined;
    const coerced = serverId === undefined
      ? undefined
      : phase === 'a'
        ? coercePhaseAArloBaseClipId(serverId)
        : coercePhaseBCedricBaseClipId(serverId);
    adoptServerClipId(coerced);
  }, [phase, adoptServerClipId]);

  const pickClip = useCallback(async (clipId: string, field: string): Promise<boolean> => {
    sync(clipId);
    patchInFlightRef.current += 1;
    try {
      const res = await pathappPatch(scope, 'v2_module_patch', { field, value: clipId });
      if (!res.ok) {
        onPatchError?.(`✗ ${field} HTTP ${res.status}: ${res.error ?? ''}`);
      }
      return res.ok;
    } finally {
      patchInFlightRef.current = Math.max(0, patchInFlightRef.current - 1);
    }
  }, [onPatchError, scope, sync]);

  return {
    selectedClipId,
    adoptFromEventState,
    adoptServerClipId,
    pickClip,
  };
}

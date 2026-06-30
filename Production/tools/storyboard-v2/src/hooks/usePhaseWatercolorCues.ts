/**
 * usePhaseWatercolorCues — PHASE_WATERCOLOR_CUE_AUTHORITY_V1 client owner.
 * All drop / resize / patch / delete / hydrate paths go through this hook.
 */
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import type { WatercolorCue } from '../components/phase/WaveformTimeline';
import { pathappPatch } from '../api/client';
import type { Scope } from '../state/scope';
import {
  mergeWatercolorCuesOnHydrate,
  parseWatercolorCuesFromEventState,
} from '../utils/phaseWatercolorCuesAuthority';

export interface WatercolorListItem {
  key: string;
  kind?: 'static' | 'animation' | string;
}

export interface UsePhaseWatercolorCuesOptions {
  phase: 'a' | 'b';
  scope: Scope;
  watercolors: WatercolorListItem[];
  onPatchError?: (message: string) => void;
}

export interface PhaseWatercolorCuesController {
  cues: WatercolorCue[];
  adoptFromEventState: (state: Record<string, unknown>) => void;
  onWatercolorDrop: (lib_key: string, offset_ms: number) => void;
  onCueRangeChange: (cueId: string, offsetMs: number, durationMs: number) => void;
  onCuePatch: (updated: WatercolorCue) => void;
  onCueDelete: (cueId: string) => void;
  remapWatercolorKey: (originalKey: string, animatedKey: string) => Promise<boolean>;
}

export function usePhaseWatercolorCues({
  phase,
  scope,
  watercolors,
  onPatchError,
}: UsePhaseWatercolorCuesOptions): PhaseWatercolorCuesController {
  const [cues, setCues] = useState<WatercolorCue[]>([]);
  const cuesRef = useRef<WatercolorCue[]>([]);
  const patchInFlightRef = useRef(0);
  const patchGenRef = useRef(0);
  const cueField = `phase_${phase}_watercolor_cues_json`;

  const syncCues = useCallback((next: WatercolorCue[]) => {
    cuesRef.current = next;
    setCues(next);
  }, []);

  // Reset only on event/phase switch — not scope.version (scope heal bumps version
  // after adoptFromEventState and would wipe hydrated cues).
  useEffect(() => {
    syncCues([]);
  }, [phase, scope.event_id, syncCues]);

  const persistCues = useCallback(async (next: WatercolorCue[]): Promise<boolean> => {
    syncCues(next);
    patchInFlightRef.current += 1;
    const gen = ++patchGenRef.current;
    try {
      const res = await pathappPatch(scope, 'v2_module_patch', {
        field: cueField,
        value: next,
      });
      if (gen !== patchGenRef.current) return res.ok;
      if (!res.ok) {
        onPatchError?.(`✗ cue patch HTTP ${res.status}: ${res.error ?? ''}`);
      }
      return res.ok;
    } finally {
      patchInFlightRef.current = Math.max(0, patchInFlightRef.current - 1);
    }
  }, [cueField, onPatchError, scope, syncCues]);

  const adoptFromEventState = useCallback((state: Record<string, unknown>) => {
    const serverCues = parseWatercolorCuesFromEventState(state, phase);
    const merged = mergeWatercolorCuesOnHydrate(cuesRef.current, serverCues, {
      patchInFlight: patchInFlightRef.current > 0,
    });
    syncCues(merged);
  }, [phase, syncCues]);

  const onWatercolorDrop = useCallback((lib_key: string, offset_ms: number) => {
    const wcItem = watercolors.find((w) => w.key === lib_key);
    const defaultDurationMs = wcItem?.kind === 'animation' ? 10000 : 3000;
    const cueType: string = wcItem?.kind === 'animation' ? 'video' : 'png';
    const newCue: WatercolorCue & { cue_type: string } = {
      id: `cue_${Math.random().toString(36).slice(2, 10)}`,
      watercolor_key: lib_key,
      offset_ms,
      duration_ms: defaultDurationMs,
      animation_type: 'fade_in',
      cue_type: cueType,
      volume: 1.0,
    };
    void persistCues([...cuesRef.current, newCue]);
  }, [persistCues, watercolors]);

  const onCueRangeChange = useCallback((cueId: string, offsetMs: number, durationMs: number) => {
    const current = cuesRef.current;
    if (!current.some((c) => c.id === cueId)) return;
    const next = current.map((c) =>
      c.id === cueId ? { ...c, offset_ms: offsetMs, duration_ms: durationMs } : c,
    );
    void persistCues(next);
  }, [persistCues]);

  const onCuePatch = useCallback((updated: WatercolorCue) => {
    const next = cuesRef.current.map((c) => (c.id === updated.id ? updated : c));
    void persistCues(next);
  }, [persistCues]);

  const onCueDelete = useCallback((cueId: string) => {
    const next = cuesRef.current.filter((c) => c.id !== cueId);
    void persistCues(next);
  }, [persistCues]);

  const remapWatercolorKey = useCallback(async (
    originalKey: string,
    animatedKey: string,
  ): Promise<boolean> => {
    if (!originalKey || !animatedKey || originalKey === animatedKey) return false;
    const next = cuesRef.current.map((cue) =>
      cue.watercolor_key === originalKey
        ? { ...cue, watercolor_key: animatedKey }
        : cue,
    );
    if (next.every((c, i) => c === cuesRef.current[i])) return false;
    return persistCues(next);
  }, [persistCues]);

  return {
    cues,
    adoptFromEventState,
    onWatercolorDrop,
    onCueRangeChange,
    onCuePatch,
    onCueDelete,
    remapWatercolorKey,
  };
}

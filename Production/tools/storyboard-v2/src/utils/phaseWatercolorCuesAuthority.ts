/**
 * PHASE_WATERCOLOR_CUE_AUTHORITY_V1 — single client owner for Phase A/B waveform cues.
 *
 * Server authority: phase_{a|b}_watercolor_cues_json (v2_module_patch validator).
 * Client authority: mergeWatercolorCuesOnHydrate — local geometry wins when server
 * omits cues or a patch is in flight (mirrors STITCH_SAVE_REFRESH_LOCAL_CUES_V1).
 */
import type { WatercolorCue } from '../components/phase/WaveformTimeline';
import {
  mergeOperatorArrayOnHydrate,
  type OperatorEditMergeOptions,
} from './operatorEditMerge.ts';

export const PHASE_WATERCOLOR_CUE_AUTHORITY_V1 = 'PHASE_WATERCOLOR_CUE_AUTHORITY_V1';

/** Server schema → frontend WatercolorCue. */
export function watercolorCueFromServerSchema(raw: Record<string, unknown>): WatercolorCue {
  return {
    id: String(raw['id'] ?? `cue_${Math.random().toString(36).slice(2, 10)}`),
    watercolor_key: String(raw['key'] ?? raw['watercolor_key'] ?? ''),
    offset_ms: Number(raw['timestamp_ms'] ?? raw['offset_ms'] ?? 0),
    duration_ms: Number(raw['duration_ms'] ?? 3000),
    animation_type: String(raw['animation'] ?? raw['animation_type'] ?? 'fade_in'),
    volume: Number(raw['volume'] ?? 1.0),
  };
}

/** Parse phase_*_watercolor_cues_json from v2 event state. Undefined = field absent. */
export function parseWatercolorCuesFromEventState(
  state: Record<string, unknown>,
  phase: 'a' | 'b',
): WatercolorCue[] | undefined {
  const raw = state[`phase_${phase}_watercolor_cues_json`];
  if (raw === undefined || raw === null) return undefined;
  try {
    const parsed: unknown = typeof raw === 'string' ? JSON.parse(raw)
      : Array.isArray(raw) ? raw : undefined;
    if (!Array.isArray(parsed)) return undefined;
    return (parsed as Record<string, unknown>[]).map(watercolorCueFromServerSchema);
  } catch {
    return undefined;
  }
}

export interface MergeWatercolorCuesOptions extends OperatorEditMergeOptions {}

export function mergeWatercolorCuesOnHydrate(
  localCues: readonly WatercolorCue[],
  serverCues: WatercolorCue[] | undefined,
  opts: MergeWatercolorCuesOptions,
): WatercolorCue[] {
  return mergeOperatorArrayOnHydrate(localCues, serverCues, opts);
}

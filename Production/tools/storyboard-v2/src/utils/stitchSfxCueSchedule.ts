export interface StitchSfxCueScheduleInput {
  id?: string;
  offset_ms?: number;
  duration_ms?: number;
  volume?: number;
  fadein_ms?: number;
  fadeout_ms?: number;
  source_path?: string;
}

/** Skip cues whose start is more than 50ms in the past (seek/play from mid-timeline). */
export const STITCH_SFX_PAST_CUE_SKIP_S = 0.05;

/** Delay from now until cue should fire, given current video playhead (seconds). */
export function stitchSfxCueDelaySeconds(offsetMs: number, videoTimeS: number): number {
  return offsetMs / 1000 - videoTimeS;
}

/** Cues to schedule on play/seek — excludes cues already passed. */
export function stitchSfxCuesToSchedule(
  cues: StitchSfxCueScheduleInput[],
  videoTimeS: number,
): Array<{ cue: StitchSfxCueScheduleInput; delayS: number }> {
  const out: Array<{ cue: StitchSfxCueScheduleInput; delayS: number }> = [];
  for (const cue of cues) {
    const delayS = stitchSfxCueDelaySeconds(cue.offset_ms ?? 0, videoTimeS);
    if (delayS < -STITCH_SFX_PAST_CUE_SKIP_S) continue;
    const srcPath = (cue.source_path ?? '').trim();
    if (!srcPath) continue;
    out.push({ cue, delayS });
  }
  return out;
}

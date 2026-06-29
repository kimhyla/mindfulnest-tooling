/** BG_KLING_CLIP_APPROVE_V1 — explicit operator approve before nav checkmark / stitch sign-off.
 *
 * Root cause (2026-06): KLING_STITCH_READINESS_V1 dropped the Approve control while
 * sidebar badges still gate on kling_o3_status === 'approved'. Agent import paths
 * pin clips as draft; tile radio onChange no-ops when already selected.
 */
export const BG_KLING_CLIP_APPROVE_CONTRACT_V1 = 'BG_KLING_CLIP_APPROVE_V1';

export interface KlingClipApproveBeatFields {
  kling_o3_status?: string | null;
  kling_o3_video_path?: string | null;
  kling_o3_still_stitch_approved?: boolean;
  pipeline?: string | null;
  beat_render_mode?: string | null;
}

function isStillInsertBeat(b: KlingClipApproveBeatFields): boolean {
  return b.pipeline === 'still_insert' || b.beat_render_mode === 'still_insert';
}

/** Non-still O3/Element beats with active clip but not yet operator-approved. */
export function klingBeatNeedsClipApprove(
  beat: KlingClipApproveBeatFields,
  opts?: { stillInsert?: boolean },
): boolean {
  if (opts?.stillInsert ?? isStillInsertBeat(beat)) return false;
  if (!(beat.kling_o3_video_path ?? '').trim()) return false;
  return (beat.kling_o3_status ?? '').toLowerCase() !== 'approved';
}

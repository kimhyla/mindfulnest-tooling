/** KLING_STITCH_READINESS_V1 — client mirror of Production/tools/kling_stitch_readiness.py */
export const KLING_STITCH_READINESS_V1 = 'KLING_STITCH_READINESS_V1';

export interface KlingStitchReadinessBeat {
  beat_id?: string;
  magic_still_path?: string | null;
  magic_still_path_exists?: boolean;
  magic_video_path?: string | null;
  kling_o3_video_path?: string | null;
  kling_o3_video_path_exists?: boolean;
  kling_o3_status?: string | null;
  kling_o3_still_stitch_approved?: boolean;
  pipeline?: string | null;
  beat_render_mode?: string | null;
  job_busy?: boolean | null;
  o3_current_job_id?: string | null;
}

function isStillInsertBeat(b: KlingStitchReadinessBeat): boolean {
  return b.pipeline === 'still_insert' || b.beat_render_mode === 'still_insert';
}

function o3JobBlocksExport(b: KlingStitchReadinessBeat): boolean {
  return Boolean(b.job_busy || b.o3_current_job_id);
}

/** Exported for bgStitchExport block labels — must stay aligned with server busy gate. */
export function o3JobBlocksStitchExport(b: KlingStitchReadinessBeat): boolean {
  return o3JobBlocksExport(b);
}

/** Must match ``beat_kling_stitch_export_ready`` in kling_stitch_readiness.py */
export function beatKlingStitchExportReady(b: KlingStitchReadinessBeat): boolean {
  if (b.magic_still_path && b.magic_still_path_exists !== false) {
    return true;
  }
  if (isStillInsertBeat(b)) {
    if (b.kling_o3_still_stitch_approved) return true;
    const st = (b.kling_o3_status ?? '').toLowerCase();
    return st === 'approved' && Boolean(b.kling_o3_video_path);
  }
  if (!b.kling_o3_video_path) return false;
  if (b.kling_o3_video_path_exists === false) return false;
  if (o3JobBlocksExport(b)) return false;
  return true;
}

/** Still-insert only — explicit operator stitch approve still required. */
export function stillBeatNeedsStitchApprove(b: KlingStitchReadinessBeat): boolean {
  if (!isStillInsertBeat(b)) return false;
  if (b.kling_o3_still_stitch_approved) return false;
  if (b.kling_o3_status === 'approved') return false;
  return Boolean(b.kling_o3_video_path);
}

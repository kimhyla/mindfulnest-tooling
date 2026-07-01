/** STITCH_MUX_VIDEO_LINEAGE_V1 — mux preview bytes must pin to slot source video. */

export const STITCH_MUX_VIDEO_LINEAGE_V1 = 'STITCH_MUX_VIDEO_LINEAGE_V1';

export interface StitchMuxVideoLineageFields {
  video_path?: string;
  mux_video_path?: string;
  mux_video_mtime_ms?: number;
  mux_preview_hash?: string;
}

export interface StitchAmbientMixLineageFields {
  video_path?: string;
  ambient_mix_hash?: string;
  ambient_mix_video_path?: string;
}

export interface StitchBgO3ExportLineageFields {
  video_path?: string;
  bg_o3_export_lineage_sig?: string;
  bg_o3_export_lineage_sig_expected?: string;
}

/** BG_O3_EXPORT_LINEAGE_HYDRATE_V1 — slot video must match server export lineage sig. */
export function stitchSlotBgO3ExportLineageMatches(
  slot: StitchBgO3ExportLineageFields | null | undefined,
): boolean {
  const videoPath = (slot?.video_path ?? '').trim();
  const stored = (slot?.bg_o3_export_lineage_sig ?? '').trim();
  const expected = (slot?.bg_o3_export_lineage_sig_expected ?? stored).trim();
  if (!videoPath || !stored) return true;
  if (!expected) return true;
  return stored === expected;
}

/** Server ambient mix artifact is pinned to the slot's current source video. */
export function stitchSlotAmbientMixLineageMatches(
  slot: StitchAmbientMixLineageFields | null | undefined,
): boolean {
  const hash = (slot?.ambient_mix_hash ?? '').trim();
  if (!hash) return false;
  const videoPath = (slot?.video_path ?? '').trim();
  const pinnedPath = (slot?.ambient_mix_video_path ?? '').trim();
  if (!videoPath || !pinnedPath || pinnedPath !== videoPath) return false;
  return true;
}

/** Server mux artifact is pinned to the slot's current source video. */
export function stitchSlotMuxPreviewLineageMatches(
  slot: StitchMuxVideoLineageFields | null | undefined,
): boolean {
  const videoPath = (slot?.video_path ?? '').trim();
  const muxVideoPath = (slot?.mux_video_path ?? '').trim();
  const muxHash = (slot?.mux_preview_hash ?? '').trim();
  if (!videoPath || !muxHash) return false;
  if (!muxVideoPath) return false;
  return muxVideoPath === videoPath;
}

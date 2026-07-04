/** Server response shape for POST /api/bg/kling-o3-trim (apply + preview). */
export type O3TrimApplyServerData = {
  trim_baked?: boolean;
  export_baked?: boolean;
  baked_path?: string;
  video_path?: string;
  preview_video_url?: string;
  trim_start?: number;
  trim_back?: number | null;
};

/** Element O3 export uses export_baked; still-insert uses trim_baked — one client predicate. */
export function o3TrimApplyIsBaked(data: O3TrimApplyServerData | null | undefined): boolean {
  return !!(data?.trim_baked || data?.export_baked);
}

/** Baked artifact on disk — prefer baked_path (export scratch) over video_path (still in-place). */
export function o3TrimApplyArtifactPath(data: O3TrimApplyServerData | null | undefined): string | undefined {
  if (!o3TrimApplyIsBaked(data)) return undefined;
  const baked = (data?.baked_path ?? '').trim();
  if (baked) return baked;
  const vp = (data?.video_path ?? '').trim();
  return vp || undefined;
}

export function o3TrimApplyPreviewUrl(
  data: O3TrimApplyServerData | null | undefined,
  serverBase: string,
): string | undefined {
  const preview = (data?.preview_video_url ?? '').trim();
  if (!preview) return undefined;
  return preview.startsWith('http') ? preview : `${serverBase}${preview}`;
}

/**
 * STITCH_DRY_MEDIA_FAIL_LOUD_V1 — operator-visible Stitcher slot video load failures.
 *
 * Bug class (Event_3): dry_export_path /files MP4s that are Dropbox File Provider
 * dataless (or HOT_SERVE materialize-failed) surface as a black player with no banner
 * because (1) pool onError ignored inactive slots, (2) slot-switch cleared composerVideoError,
 * (3) MEDIA_ERR_SRC_NOT_SUPPORTED ("Format error") had no Dropbox/hot-serve guidance.
 */

export const STITCH_DRY_MEDIA_FAIL_LOUD_V1 = 'STITCH_DRY_MEDIA_FAIL_LOUD_V1';

/** HTMLMediaElement.error.code names — keep stable for audit + UI. */
export function mediaErrorCodeName(code: number | null | undefined): string {
  switch (code) {
    case 1:
      return 'MEDIA_ERR_ABORTED';
    case 2:
      return 'MEDIA_ERR_NETWORK';
    case 3:
      return 'MEDIA_ERR_DECODE';
    case 4:
      return 'MEDIA_ERR_SRC_NOT_SUPPORTED';
    default:
      return `MEDIA_ERR_${code ?? '?'}`;
  }
}

export function stitchMediaLeafFromPathOrUrl(
  pathOrUrl: string | null | undefined,
): string {
  const raw = (pathOrUrl ?? '').trim();
  if (!raw) return '';
  try {
    if (raw.includes('path=')) {
      const u = new URL(raw, 'http://localhost');
      const path = u.searchParams.get('path') ?? '';
      if (path) {
        const parts = path.split('/').filter(Boolean);
        return parts[parts.length - 1] ?? path;
      }
    }
  } catch {
    /* fall through */
  }
  const noQuery = raw.split('?', 1)[0] ?? raw;
  const parts = noQuery.split('/').filter(Boolean);
  return parts[parts.length - 1] ?? noQuery;
}

export function stitchDryMediaLikelyFileProviderFailure(
  mediaErrorCode: number | null | undefined,
): boolean {
  // Format error (4) + network (2) are the Dropbox dataless / EDEADLK / 503 class.
  return mediaErrorCode === 2 || mediaErrorCode === 4;
}

export interface FormatStitchSlotVideoLoadErrorInput {
  slotKey: string;
  mediaErrorCode?: number | null | undefined;
  mediaErrorMessage?: string | null | undefined;
  srcUrl?: string | null | undefined;
  dryExportPath?: string | null | undefined;
  videoPath?: string | null | undefined;
  /** When true, mux preview failed and dry fallback may still apply. */
  usingMux?: boolean | undefined;
}

/** Operator-facing single-line failure — never silent black rectangle. */
export function formatStitchSlotVideoLoadError(
  input: FormatStitchSlotVideoLoadErrorInput,
): string {
  const leaf =
    stitchMediaLeafFromPathOrUrl(input.dryExportPath)
    || stitchMediaLeafFromPathOrUrl(input.srcUrl)
    || stitchMediaLeafFromPathOrUrl(input.videoPath)
    || 'slot video';
  const codeName = mediaErrorCodeName(input.mediaErrorCode);
  const detail = (input.mediaErrorMessage ?? '').trim();
  const codeBit = detail && detail !== codeName
    ? `${codeName}: ${detail}`
    : codeName;
  const fileProviderHint = stitchDryMediaLikelyFileProviderFailure(input.mediaErrorCode)
    ? ' Dropbox File Provider often causes this when the dry MP4 is cloud-only — make the assembled file available offline, then Retry (or hard-refresh Stitcher).'
    : '';

  if (input.usingMux) {
    return (
      `SFX mix preview failed (${codeBit}) for ${input.slotKey} (${leaf}) — `
      + `trying speech-only. Click Review to rebuild the mix.${fileProviderHint}`
    );
  }

  return (
    `${input.slotKey} video failed to load (${codeBit}: ${leaf}).`
    + fileProviderHint
  );
}

/** Resolve banner text when switching to a slot that already failed in the pool. */
export function resolveActiveSlotVideoError(opts: {
  slotKey: string;
  cachedError?: string | null | undefined;
  video?: HTMLVideoElement | null | undefined;
  dryExportPath?: string | null | undefined;
  videoPath?: string | null | undefined;
  usingMux?: boolean | undefined;
}): string | null {
  const cached = (opts.cachedError ?? '').trim();
  if (cached) return cached;
  const video = opts.video;
  if (!video?.error) return null;
  return formatStitchSlotVideoLoadError({
    slotKey: opts.slotKey,
    mediaErrorCode: video.error.code,
    mediaErrorMessage: video.error.message,
    srcUrl: video.currentSrc || video.src,
    dryExportPath: opts.dryExportPath ?? null,
    videoPath: opts.videoPath ?? null,
    usingMux: opts.usingMux ?? false,
  });
}

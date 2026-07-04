import { SERVER_BASE } from '../api/endpoints';

/** Rewrite legacy localhost:5111 absolute URLs to the active storyboard origin. */
export function resolveServerMediaUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith('/')) return `${SERVER_BASE}${url}`;
  if (url.startsWith('http://localhost:5111/') || url.startsWith('https://localhost:5111/')) {
    return url.replace(/^https?:\/\/localhost:5111/, SERVER_BASE);
  }
  return url;
}

export function normalizeProductionRelativePath(videoPath: string): string | undefined {
  if (videoPath.startsWith('Production/')) return videoPath;
  if (videoPath.startsWith('/')) {
    const marker = '/Production/';
    const idx = videoPath.indexOf(marker);
    if (idx >= 0) return videoPath.slice(idx + 1);
  }
  return undefined;
}

/** SFX cue source_path may be absolute Dropbox or Production/ relative — normalize for /files fetch. */
export function resolveStitchSfxFetchUrl(sourcePath: string): string {
  const trimmed = sourcePath.trim();
  const rel = normalizeProductionRelativePath(trimmed) ?? trimmed;
  return resolveServerMediaUrl(`/files?path=${encodeURIComponent(rel)}`);
}

/** Instant roadmap playback — serve the slot's on-disk source via /files (Beat Gen parity). */
export function resolveStitchSlotSourceVideoUrl(
  videoPath?: string | null,
): string | undefined {
  if (!videoPath) return undefined;
  const rel = normalizeProductionRelativePath(videoPath);
  if (!rel) return undefined;
  // Cache-bust /files playback when slot video_path changes (same-origin MP4 cache).
  const leaf = rel.split('/').pop() ?? rel;
  return `${SERVER_BASE}/files?path=${encodeURIComponent(rel)}&v=${encodeURIComponent(leaf)}`;
}

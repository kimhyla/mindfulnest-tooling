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

/** Instant roadmap playback — serve the slot's on-disk source via /files (Beat Gen parity). */
export function resolveStitchSlotSourceVideoUrl(
  videoPath?: string | null,
): string | undefined {
  if (!videoPath) return undefined;
  if (!videoPath.startsWith('Production/')) return undefined;
  return `${SERVER_BASE}/files?path=${encodeURIComponent(videoPath)}`;
}

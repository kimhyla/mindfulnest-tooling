import { SERVER_BASE } from '../api/endpoints';

/** Instant roadmap playback — serve the slot's on-disk source via /files (Beat Gen parity). */
export function resolveStitchSlotSourceVideoUrl(
  videoPath?: string | null,
): string | undefined {
  if (!videoPath) return undefined;
  if (!videoPath.startsWith('Production/')) return undefined;
  return `${SERVER_BASE}/files?path=${encodeURIComponent(videoPath)}`;
}

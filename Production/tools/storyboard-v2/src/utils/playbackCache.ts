import { activeScope } from '../state/scope';
import { pathappPatch } from '../api/client';
import { resolveServerMediaUrl } from './stitchSlotVideo';

const playbackUrlCache = new Map<string, string>();
const playbackTruthCache = new Map<string, ClipPlaybackTruth>();

export type ClipPlaybackTruth = {
  playbackUrl: string;
  rawDurationS: number;
};

export async function resolveClipPlaybackTruth(
  videoPath: string,
): Promise<ClipPlaybackTruth | null> {
  const key = videoPath.trim();
  if (!key) return null;
  const cached = playbackTruthCache.get(key);
  if (cached) return cached;

  const res = await pathappPatch<{
    ok?: boolean;
    playback_url?: string;
    duration_s?: number;
    raw_duration_s?: number;
  }>(activeScope.value, 'media_playback_resolve', { path: key });

  if (!res.ok || !res.data?.playback_url) return null;
  const url = resolveServerMediaUrl(res.data.playback_url);
  const rawDurationS = res.data.raw_duration_s ?? res.data.duration_s;
  if (rawDurationS == null || !(rawDurationS > 0)) return null;
  const truth: ClipPlaybackTruth = { playbackUrl: url, rawDurationS };
  playbackUrlCache.set(key, url);
  playbackTruthCache.set(key, truth);
  return truth;
}

export async function resolvePlaybackUrl(videoPath: string): Promise<string | null> {
  const truth = await resolveClipPlaybackTruth(videoPath);
  return truth?.playbackUrl ?? null;
}

export function clearPlaybackUrlCache(): void {
  playbackUrlCache.clear();
  playbackTruthCache.clear();
}

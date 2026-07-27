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

  // PLAYBACK_RESOLVE_NO_SNAPSHOT_V1 — resolve is cache-warm/read, not a write.
  // Snapshotting state.json through Dropbox before every Beat Gen tile load
  // was File Provider pressure that raced /files and left option videos spinning.
  const res = await pathappPatch<{
    ok?: boolean;
    playback_url?: string;
    duration_s?: number;
    raw_duration_s?: number;
    cache_token?: string;
  }>(activeScope.value, 'media_playback_resolve', { path: key }, { skipSnapshot: true });

  if (!res.ok || !res.data?.playback_url) return null;
  const url = resolveServerMediaUrl(res.data.playback_url);
  const rawDurationS = res.data.raw_duration_s ?? res.data.duration_s;
  // PLAYBACK_DURATION_OPTIONAL_V1 — accept URL even if duration missing so
  // <video> can load; callers that need trim math still check rawDurationS > 0.
  if (rawDurationS == null || !(Number(rawDurationS) > 0)) {
    const truthNoDur: ClipPlaybackTruth = { playbackUrl: url, rawDurationS: 0 };
    playbackUrlCache.set(key, url);
    return truthNoDur;
  }
  const truth: ClipPlaybackTruth = { playbackUrl: url, rawDurationS: Number(rawDurationS) };
  // Server token = sha256(path+mtime+size); always refetch so in-place clip swaps reach the tile.
  const cacheKey = res.data.cache_token ? `${key}|${res.data.cache_token}` : key;
  if (res.data.cache_token) {
    playbackUrlCache.delete(key);
    playbackTruthCache.delete(key);
  }
  playbackUrlCache.set(cacheKey, url);
  playbackTruthCache.set(cacheKey, truth);
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

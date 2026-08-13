/**
 * STITCH_DRY_HOT_SERVE_PLAYBACK_V1 — dry / four-files composer video binds only
 * after playback_resolve returns an APFS hot URL (same class as Beat Gen gray-tile fix).
 *
 * Never bind raw /files for these slots: Dropbox File Provider 503 JSON → MEDIA Format error.
 */

import { resolveClipPlaybackTruth } from './playbackCache';
import { SERVER_BASE } from '../api/endpoints';
import {
  stitchSlotUsesDryAuthorityClientMix,
  stitchSlotUsesFourFilesPlayback,
} from './stitchSlotMuxAudioSig';
import { resolveDrySlotSourceVideoUrl, isStitchDrySlotPlaybackUrl } from './stitchJobMediaHydrate';

export const STITCH_DRY_HOT_SERVE_PLAYBACK_V1 = 'STITCH_DRY_HOT_SERVE_PLAYBACK_V1';

export function stitchSlotRequiresHotServeComposerUrl(
  slot: { playback_recipe_version?: string } | null | undefined,
): boolean {
  return (
    stitchSlotUsesDryAuthorityClientMix(slot)
    || stitchSlotUsesFourFilesPlayback(slot)
  );
}

function isHotPlaybackApiUrl(url: string): boolean {
  const u = url.trim();
  if (!u) return false;
  if (u.includes('/api/media/playback/')) return true;
  // Never treat /files as hot — that is the gray-screen path.
  if (isStitchDrySlotPlaybackUrl(u)) return false;
  return false;
}

/**
 * Resolve APFS-backed playback URL for a dry concat / speech disk path.
 * Warm-poke /files only to materialize cache; never return /files as the bind URL.
 */
export async function resolveStitchDrySlotHotPlaybackUrl(
  diskPath: string,
): Promise<string | null> {
  const key = (diskPath || '').trim();
  if (!key) return null;

  const first = await resolveClipPlaybackTruth(key);
  if (first?.playbackUrl && isHotPlaybackApiUrl(first.playbackUrl)) {
    return first.playbackUrl;
  }

  // Cold miss: poke /files Range to run HOT_SERVE materialize, then resolve again.
  const filesUrl = resolveDrySlotSourceVideoUrl(key);
  if (filesUrl) {
    try {
      await fetch(filesUrl, {
        method: 'GET',
        headers: { Range: 'bytes=0-1' },
      });
    } catch {
      /* best-effort warm during File Provider storm */
    }
    const warmed = await resolveClipPlaybackTruth(key);
    if (warmed?.playbackUrl && isHotPlaybackApiUrl(warmed.playbackUrl)) {
      return warmed.playbackUrl;
    }
  }

  return null;
}

/** Test helper — hot URL shape contract. */
export function stitchHotPlaybackUrlLooksSafe(url: string | null | undefined): boolean {
  if (!url) return false;
  if (url.includes('/files?path=')) return false;
  return url.includes('/api/media/playback/') || url.startsWith(`${SERVER_BASE}/api/media/playback/`);
}

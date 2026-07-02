/** STITCH_SLOT_SESSION_CACHE_V1 — per-event in-memory cache for Stitcher slot composer.
 *
 * Once intro / phase_a / phase_b / resolution are loaded, switching the multiphase
 * track must not remux or re-peak unless slot content changes (video_path or mix sig).
 * Invalidated on event switch or when a slot's source video / mix geometry changes.
 */

import {
  stitchSlotLiveAmbientSig,
  stitchSlotMuxAudioSig,
  stitchSlotRequiresAmbientMix,
  stitchSlotRequiresMuxedPreview,
  stitchSlotUsesFourFilesPlayback,
  stitchSlotUsesDryAuthorityClientMix,
  stitchSlotSpeechPeaksSig,
  type StitchSlotMuxSigInput,
} from './stitchSlotMuxAudioSig';
import { stitchSlotMuxPreviewLineageMatches, stitchSlotAmbientMixLineageMatches } from './stitchMuxVideoLineage';

type StitchSlotArtifactFields = StitchSlotMuxSigInput & {
  mux_preview_hash?: string;
  mux_video_path?: string;
  ambient_mix_hash?: string;
  ambient_mix_video_path?: string;
};
/** localStorage mux URL survives hard refresh; in-memory session does not. */
export const STITCH_PREVIEW_LS_HYDRATE_V1 = 'STITCH_PREVIEW_LS_HYDRATE_V1';
export const STITCH_SFX_PLAYBACK_TRUTH_V1 = 'STITCH_SFX_PLAYBACK_TRUTH_V1';
export const STITCHER_PREVIEW_LS_PREFIX = 'storyboard_v2_stitcher_preview';

export interface CachedStitcherPreviewLs {
  video_path: string;
  preview_url: string;
  audio_sig?: string;
  playback_recipe_version?: string;
}

export type StitchSessionSlotKey = 'intro' | 'phase_a' | 'phase_b' | 'resolution' | 'standalone';

export interface StitchSlotWaveformSession {
  peaks: number[];
  durationS: number;
  mixSig: string;
}

export interface StitchSlotSessionRecord {
  muxPreviewUrl?: string;
  videoPath?: string;
  audioSig?: string;
  waveform?: StitchSlotWaveformSession;
}

type EventSessions = Partial<Record<StitchSessionSlotKey, StitchSlotSessionRecord>>;

const sessionsByKey = new Map<string, EventSessions>();

function sessionRow(sessionKey: string): EventSessions {
  let row = sessionsByKey.get(sessionKey);
  if (!row) {
    row = {};
    sessionsByKey.set(sessionKey, row);
  }
  return row;
}

export function stitchSlotMixSig(
  videoPath: string | undefined,
  slot: StitchSlotMuxSigInput | null | undefined,
): string {
  const path = (videoPath ?? '').trim();
  const audio = stitchSlotMuxAudioSig(slot);
  return `${path}#${audio}`;
}

export function stitchSlotWaveformPeaksSig(
  videoPath: string | undefined,
): string {
  return stitchSlotSpeechPeaksSig(videoPath);
}

export function getStitchSlotSession(
  sessionKey: string,
  slot: StitchSessionSlotKey,
): StitchSlotSessionRecord | undefined {
  return sessionRow(sessionKey)[slot];
}

export function clearStitchSlotSessionEvent(sessionKey: string): void {
  sessionsByKey.delete(sessionKey);
}

export function invalidateStitchSlotSessionSlot(
  sessionKey: string,
  slot: StitchSessionSlotKey,
): void {
  const row = sessionsByKey.get(sessionKey);
  if (!row) return;
  delete row[slot];
  if (Object.keys(row).length === 0) {
    sessionsByKey.delete(sessionKey);
  }
}

export function stitchSlotSessionExpectedSig(
  slotData: StitchSlotMuxSigInput & { video_path?: string } | null | undefined,
): string {
  if (!slotData) return '';
  if (stitchSlotRequiresMuxedPreview(slotData)) {
    return stitchSlotMuxAudioSig(slotData);
  }
  if (stitchSlotRequiresAmbientMix(slotData)) {
    return stitchSlotLiveAmbientSig(slotData);
  }
  return stitchSlotMuxAudioSig(slotData);
}

/** Server must expose a live artifact before session/localStorage preview URLs are trusted. */
export function stitchSlotServerArtifactReady(
  slotData: StitchSlotArtifactFields | null | undefined,
): boolean {
  if (!slotData?.video_path) return false;
  if (stitchSlotRequiresMuxedPreview(slotData)) {
    const hash = (slotData.mux_preview_hash ?? '').trim();
    return Boolean(hash && stitchSlotMuxPreviewLineageMatches(slotData));
  }
  if (stitchSlotRequiresAmbientMix(slotData)) {
    const hash = (slotData.ambient_mix_hash ?? '').trim();
    return Boolean(hash && stitchSlotAmbientMixLineageMatches(slotData));
  }
  return true;
}

export function isMuxSessionFresh(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  slotData: StitchSlotArtifactFields | null | undefined,
): boolean {
  const record = getStitchSlotSession(sessionKey, slot);
  const videoPath = (slotData?.video_path ?? '').trim();
  const audioSig = stitchSlotSessionExpectedSig(slotData);
  if (!stitchSlotServerArtifactReady(slotData)) {
    return false;
  }
  return Boolean(
    record?.muxPreviewUrl
    && record.videoPath === videoPath
    && (record.audioSig ?? '') === audioSig
    && videoPath,
  );
}

export function isWaveformSessionFresh(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  videoPath: string | undefined,
): boolean {
  const record = getStitchSlotSession(sessionKey, slot);
  const mixSig = stitchSlotSpeechPeaksSig(videoPath);
  const wf = record?.waveform;
  return Boolean(
    wf?.peaks?.length
    && wf.mixSig === mixSig
    && (videoPath ?? '').trim(),
  );
}

export function commitMuxSession(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  payload: { previewUrl: string; videoPath: string; audioSig: string },
): void {
  const row = sessionRow(sessionKey);
  const prev = row[slot] ?? {};
  row[slot] = {
    ...prev,
    muxPreviewUrl: payload.previewUrl,
    videoPath: payload.videoPath,
    audioSig: payload.audioSig,
  };
}

export function commitWaveformSession(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  payload: StitchSlotWaveformSession,
): void {
  const row = sessionRow(sessionKey);
  const prev = row[slot] ?? {};
  row[slot] = { ...prev, waveform: payload };
}

/** Drop cached mux + waveform when server slot source no longer matches session. */
export function readCachedStitcherPreviewLs(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  slotData?: { playback_recipe_version?: string } | null,
): CachedStitcherPreviewLs | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(`${STITCHER_PREVIEW_LS_PREFIX}:${sessionKey}:${slot}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedStitcherPreviewLs;
    if (parsed?.video_path && parsed?.preview_url) {
      const slotRecipe = (slotData?.playback_recipe_version ?? '').trim();
      const cachedRecipe = (parsed.playback_recipe_version ?? '').trim();
      if (slotRecipe && cachedRecipe && slotRecipe !== cachedRecipe) {
        return null;
      }
      return parsed;
    }
  } catch {
    // ignore corrupt cache
  }
  return null;
}

export function writeCachedStitcherPreviewLs(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  cache: CachedStitcherPreviewLs,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      `${STITCHER_PREVIEW_LS_PREFIX}:${sessionKey}:${slot}`,
      JSON.stringify(cache),
    );
  } catch {
    // localStorage may be unavailable in tests
  }
}

export function clearCachedStitcherPreviewLs(
  sessionKey: string,
  slot: StitchSessionSlotKey,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(`${STITCHER_PREVIEW_LS_PREFIX}:${sessionKey}:${slot}`);
  } catch {
    // ignore
  }
}

export function clearAllCachedStitcherPreviewsLs(sessionKey: string): void {
  if (typeof window === 'undefined') return;
  for (const slot of ['intro', 'phase_a', 'phase_b', 'resolution', 'standalone'] as const) {
    clearCachedStitcherPreviewLs(sessionKey, slot);
  }
}

/** Drop in-memory mux session + localStorage when server artifacts were cleared. */
export function purgeStitchSlotPlaybackCache(
  sessionKey: string,
  slot: StitchSessionSlotKey,
): void {
  invalidateStitchSlotSessionSlot(sessionKey, slot);
  clearCachedStitcherPreviewLs(sessionKey, slot);
}

/** Sync hydrate from localStorage into session + preview URL map (hard-refresh durable). */
export function hydrateMuxFromLocalStorage(
  sessionKey: string,
  slots: Partial<
    Record<StitchSessionSlotKey, (StitchSlotMuxSigInput & { video_path?: string }) | undefined>
  > | undefined,
): Partial<Record<StitchSessionSlotKey, string>> {
  const out: Partial<Record<StitchSessionSlotKey, string>> = {};
  if (!slots) return out;
  for (const slot of ['intro', 'phase_a', 'phase_b', 'resolution', 'standalone'] as const) {
    const slotData = slots[slot];
    const videoPath = (slotData?.video_path ?? '').trim();
    if (!videoPath) continue;
    if (stitchSlotUsesFourFilesPlayback(slotData) || stitchSlotUsesDryAuthorityClientMix(slotData)) {
      continue;
    }
    // Ambient/SFX previews must come from server artifacts — never dry LS alone.
    if (
      stitchSlotRequiresMuxedPreview(slotData)
      || stitchSlotRequiresAmbientMix(slotData)
    ) continue;
    const audioSig = stitchSlotMuxAudioSig(slotData);
    const cached = readCachedStitcherPreviewLs(sessionKey, slot, slotData);
    if (
      cached?.video_path === videoPath
      && (cached.audio_sig ?? '') === audioSig
      && cached.preview_url
    ) {
      out[slot] = cached.preview_url;
      commitMuxSession(sessionKey, slot, {
        previewUrl: cached.preview_url,
        videoPath,
        audioSig,
      });
    }
  }
  return out;
}

/**
 * Reconcile session cache when job slot data changes.
 * STITCH_MUX_STALE_WHILE_REVALIDATE_V1 — audio geometry drift alone must not
 * drop muxPreviewUrl; keep playing until buildSlotPreview commits a new hash.
 */
export function reconcileStitchSlotSession(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  slotData: (StitchSlotMuxSigInput & { video_path?: string }) | null | undefined,
): boolean {
  const record = getStitchSlotSession(sessionKey, slot);
  if (!record) return false;
  const videoPath = (slotData?.video_path ?? '').trim();
  const mixSig = stitchSlotSpeechPeaksSig(videoPath);
  let invalidated = false;
  if (record.muxPreviewUrl && record.videoPath !== videoPath) {
    delete record.muxPreviewUrl;
    delete record.videoPath;
    delete record.audioSig;
    invalidated = true;
  }
  if (record.waveform && record.waveform.mixSig !== mixSig) {
    delete record.waveform;
    invalidated = true;
  }
  if (!record.muxPreviewUrl && !record.waveform) {
    invalidateStitchSlotSessionSlot(sessionKey, slot);
  }
  return invalidated;
}

/** STITCH_SLOT_MEDIA_ARTIFACTS_V1 — hydrate mux + waveform from server job slot artifacts. */

import {
  commitMuxSession,
  commitWaveformSession,
  getStitchSlotSession,
  purgeStitchSlotPlaybackCache,
  stitchSlotSessionExpectedSig,
  type StitchSessionSlotKey,
} from './stitchSlotSessionCache';
import {
  stitchSlotLiveAmbientSig,
  stitchSlotLiveGeometrySig,
  stitchSlotRequiresAmbientMix,
  stitchSlotRequiresMuxedPreview,
  stitchSlotUsesFourFilesPlayback,
  reconcileFourFilesSlotArtifacts,
  type StitchSlotMuxSigInput,
} from './stitchSlotMuxAudioSig';
import { stitchSlotSpeechPeaksSig } from './stitchSlotMuxAudioSig';
import { resolveServerMediaUrl, resolveStitchSlotSourceVideoUrl } from './stitchSlotVideo';
import { stitchSlotMuxPreviewLineageMatches, stitchSlotAmbientMixLineageMatches, stitchSlotBgO3ExportLineageMatches } from './stitchMuxVideoLineage';
export { stitchSlotAmbientMixLineageMatches, stitchSlotBgO3ExportLineageMatches } from './stitchMuxVideoLineage';

export const STITCH_SLOT_MEDIA_ARTIFACTS_V1 = 'STITCH_SLOT_MEDIA_ARTIFACTS_V1';
export const STITCH_MUX_REBUILD_QUEUE_V1 = 'STITCH_MUX_REBUILD_QUEUE_V1';
export const STITCH_AMBIENT_BAKE_ON_SAVE_V1 = 'STITCH_AMBIENT_BAKE_ON_SAVE_V1';
/** STITCH_SFX_PLAYBACK_TRUTH_V1 — SFX slots must not bind dry /files as playback. */
export const STITCH_SFX_PLAYBACK_TRUTH_V1 = 'STITCH_SFX_PLAYBACK_TRUTH_V1';
/** STITCH_MUX_INTERIM_DRY_VIDEO_V1 — keep slot video visible while mux/ambient artifacts rebuild. */
export const STITCH_MUX_INTERIM_DRY_VIDEO_V1 = 'STITCH_MUX_INTERIM_DRY_VIDEO_V1';
/** STITCH_SLOT_TIMELINE_CLOCK_V1 — one duration for drop, cue markers, and mux offset. */
export const STITCH_SLOT_TIMELINE_CLOCK_V1 = 'STITCH_SLOT_TIMELINE_CLOCK_V1';
/** BG_O3_EXPORT_LINEAGE_HYDRATE_V1 — invalidate stitch preview when export authority changes. */
export const BG_O3_EXPORT_LINEAGE_HYDRATE_V1 = 'BG_O3_EXPORT_LINEAGE_HYDRATE_V1';

export interface StitchSlotMediaArtifactFields {
  video_path?: string;
  mix_sig?: string;
  ambient_mix_sig?: string;
  ambient_mix_hash?: string;
  ambient_mix_duration_ms?: number;
  ambient_mix_video_path?: string;
  ambient_mix_video_mtime_ms?: number;
  mux_preview_hash?: string;
  mux_preview_duration_ms?: number;
  video_dur_ms?: number;
  mux_video_path?: string;
  mux_video_mtime_ms?: number;
  waveform_peaks_hash?: string;
  waveform_peaks_duration_s?: number;
  _mux_preview_url?: string;
  _waveform_peaks_url?: string;
  _ambient_mix_url?: string;
  ambient_bed?: string;
  ambient_bed_path?: string;
  ambient_volume?: number;
  sfx_cues?: StitchSlotMuxSigInput['sfx_cues'];
  bg_o3_export_lineage_sig?: string;
  bg_o3_export_lineage_sig_expected?: string;
  playback_recipe_version?: string;
  dry_export_path?: string;
}

export interface HydratedJobMedia {
  previewUrls: Partial<Record<StitchSessionSlotKey, string>>;
  slotsNeedingMux: StitchSessionSlotKey[];
  slotsNeedingPeaks: StitchSessionSlotKey[];
  slotsNeedingAmbientMix: StitchSessionSlotKey[];
}

const SLOT_KEYS: StitchSessionSlotKey[] = [
  'intro',
  'phase_a',
  'phase_b',
  'resolution',
  'standalone',
];

export function resolvePersistedAmbientMixUrl(
  slot: StitchSlotMediaArtifactFields | null | undefined,
): string | undefined {
  if (!stitchSlotAmbientMixLineageMatches(slot)) return undefined;
  const hash = (slot?.ambient_mix_hash ?? '').trim();
  if (!hash) return undefined;
  const raw = (slot?._ambient_mix_url ?? '').trim();
  if (raw && raw.includes(hash)) {
    return resolveServerMediaUrl(raw);
  }
  return resolveServerMediaUrl(`/api/stitch_editor/slot_mix_file/${hash}`);
}

export function hydrateAllSlotMediaFromJob(
  sessionKey: string,
  slots: Partial<Record<StitchSessionSlotKey, StitchSlotMediaArtifactFields | undefined>> | undefined,
): HydratedJobMedia {
  const previewUrls: Partial<Record<StitchSessionSlotKey, string>> = {};
  const slotsNeedingMux: StitchSessionSlotKey[] = [];
  const slotsNeedingPeaks: StitchSessionSlotKey[] = [];
  const slotsNeedingAmbientMix: StitchSessionSlotKey[] = [];

  for (const slotKey of SLOT_KEYS) {
    const rawSlot = slots?.[slotKey];
    const slot = (reconcileFourFilesSlotArtifacts(rawSlot) ?? rawSlot) as
      | StitchSlotMediaArtifactFields
      | undefined;
    if (!slot?.video_path) continue;

    if (stitchSlotUsesFourFilesPlayback(slot)) {
      purgeStitchSlotPlaybackCache(sessionKey, slotKey);
      const flatUrl = resolveDrySlotSourceVideoUrl(slot.video_path);
      if (flatUrl) {
        previewUrls[slotKey] = flatUrl;
        commitMuxSession(sessionKey, slotKey, {
          previewUrl: flatUrl,
          videoPath: slot.video_path,
          audioSig: stitchSlotSessionExpectedSig({
            ...slot,
            sfx_cues: slot.sfx_cues ?? [],
          }),
        });
      }
      if (slot.waveform_peaks_hash && slot._waveform_peaks_url) {
        void fetchPeaksIntoSession(
          sessionKey,
          slotKey,
          slot._waveform_peaks_url,
          slot.video_path,
          slot.waveform_peaks_duration_s,
        );
      } else {
        slotsNeedingPeaks.push(slotKey);
      }
      continue;
    }

    if (!stitchSlotBgO3ExportLineageMatches(slot)) {
      purgeStitchSlotPlaybackCache(sessionKey, slotKey);
      slotsNeedingMux.push(slotKey);
      continue;
    }

    const liveGeometrySig = stitchSlotLiveGeometrySig({
      ...slot,
      sfx_cues: slot.sfx_cues ?? [],
    });
    const ambientSig = stitchSlotLiveAmbientSig({
      ...slot,
      sfx_cues: slot.sfx_cues ?? [],
    });
    const muxUrl = slot._mux_preview_url
      ? resolveServerMediaUrl(slot._mux_preview_url)
      : undefined;
    const ambientMixUrl = resolvePersistedAmbientMixUrl(slot);
    const requiresMux = stitchSlotRequiresMuxedPreview({
      ...slot,
      sfx_cues: slot.sfx_cues ?? [],
    });
    const requiresAmbientMix = stitchSlotRequiresAmbientMix({
      ...slot,
      sfx_cues: slot.sfx_cues ?? [],
    });

    if (requiresMux) {
      if (
        slot.mux_preview_hash
        && muxUrl
        && stitchSlotMuxPreviewLineageMatches(slot)
        && (slot.mix_sig ?? '').trim()
      ) {
        previewUrls[slotKey] = muxUrl;
        commitMuxSession(sessionKey, slotKey, {
          previewUrl: muxUrl,
          videoPath: slot.video_path,
          audioSig: liveGeometrySig,
        });
      } else {
        purgeStitchSlotPlaybackCache(sessionKey, slotKey);
        slotsNeedingMux.push(slotKey);
      }
    } else if (requiresAmbientMix) {
      const ambientPlaybackUrl = ambientMixUrl
        ?? (muxUrl && stitchSlotMuxPreviewLineageMatches(slot) ? muxUrl : undefined);
      if (ambientPlaybackUrl) {
        previewUrls[slotKey] = ambientPlaybackUrl;
        commitMuxSession(sessionKey, slotKey, {
          previewUrl: ambientPlaybackUrl,
          videoPath: slot.video_path,
          audioSig: ambientSig,
        });
      } else {
        purgeStitchSlotPlaybackCache(sessionKey, slotKey);
        slotsNeedingAmbientMix.push(slotKey);
      }
    }

    if (slot.waveform_peaks_hash && slot._waveform_peaks_url) {
      void fetchPeaksIntoSession(
        sessionKey,
        slotKey,
        slot._waveform_peaks_url,
        slot.video_path,
        slot.waveform_peaks_duration_s,
      );
    } else {
      slotsNeedingPeaks.push(slotKey);
    }
  }

  return { previewUrls, slotsNeedingMux, slotsNeedingPeaks, slotsNeedingAmbientMix };
}

/**
 * After operator export only rebuild slots whose video_path changed — not every
 * slot missing server mux artifacts (STITCH_MUX_REBUILD_QUEUE_V1).
 */
export function selectSlotsForMuxRebuild(
  lineageChanged: readonly StitchSessionSlotKey[],
  slotsNeedingMux: StitchSessionSlotKey[],
): StitchSessionSlotKey[] {
  if (lineageChanged.length === 0) {
    return slotsNeedingMux;
  }
  const changed = new Set(lineageChanged);
  return slotsNeedingMux.filter((slotKey) => changed.has(slotKey));
}

async function fetchPeaksIntoSession(
  sessionKey: string,
  slotKey: StitchSessionSlotKey,
  peaksUrl: string,
  videoPath: string,
  durationSHint?: number,
): Promise<void> {
  try {
    const res = await fetch(resolveServerMediaUrl(peaksUrl));
    if (!res.ok) return;
    const peaksJson = await res.json() as { data?: number[]; duration_s?: number };
    const peaks = Array.isArray(peaksJson.data) ? peaksJson.data : [];
    if (!peaks.length) return;
    const durS =
      typeof peaksJson.duration_s === 'number' && peaksJson.duration_s > 0
        ? peaksJson.duration_s
        : (durationSHint ?? 0);
    commitWaveformSession(sessionKey, slotKey, {
      peaks,
      durationS: durS,
      mixSig: stitchSlotSpeechPeaksSig(videoPath),
    });
  } catch {
    // caller may fall back to audio_extract
  }
}

export async function fetchPeaksFromArtifactUrl(
  peaksUrl: string,
): Promise<{ peaks: number[]; durationS: number } | null> {
  try {
    const res = await fetch(resolveServerMediaUrl(peaksUrl));
    if (!res.ok) return null;
    const peaksJson = await res.json() as { data?: number[]; duration_s?: number };
    const peaks = Array.isArray(peaksJson.data) ? peaksJson.data : [];
    const durationS =
      typeof peaksJson.duration_s === 'number' && peaksJson.duration_s > 0
        ? peaksJson.duration_s
        : 0;
    if (!peaks.length) return null;
    return { peaks, durationS };
  } catch {
    return null;
  }
}

export function resolvePersistedMuxPreviewUrl(
  slot: StitchSlotMediaArtifactFields | null | undefined,
): string | undefined {
  if (!stitchSlotMuxPreviewLineageMatches(slot)) return undefined;
  const hash = (slot?.mux_preview_hash ?? '').trim();
  if (!hash) return undefined;
  const raw = (slot?._mux_preview_url ?? '').trim();
  if (raw && raw.includes(hash)) {
    return resolveServerMediaUrl(raw);
  }
  return resolveServerMediaUrl(`/api/stitch_editor/preview_file/${hash}`);
}

/**
 * Server-persisted playback URL from job slot artifacts (no client state).
 * Ambient-only slots may store speech+ambient as mux_preview (ambient_mix_hash absent).
 */
export function resolvePersistedPlaybackFromArtifacts(
  slot: StitchSlotMediaArtifactFields | null | undefined,
): string | undefined {
  if (!slot?.video_path) return undefined;
  if (stitchSlotUsesFourFilesPlayback(slot)) {
    return resolveDrySlotSourceVideoUrl(slot.video_path);
  }
  const sigSlot = { ...slot, sfx_cues: slot.sfx_cues ?? [] };
  if (stitchSlotRequiresMuxedPreview(sigSlot)) {
    return resolvePersistedMuxPreviewUrl(slot);
  }
  if (stitchSlotRequiresAmbientMix(sigSlot)) {
    return resolvePersistedAmbientMixUrl(slot) ?? resolvePersistedMuxPreviewUrl(slot);
  }
  return resolveDrySlotSourceVideoUrl(slot.video_path);
}

/** `/files?path=…` for Production-relative paths — not a bare disk-relative string. */
export function resolveDrySlotSourceVideoUrl(
  videoPath: string | undefined | null,
): string | undefined {
  if (!videoPath) return undefined;
  return resolveStitchSlotSourceVideoUrl(videoPath) ?? resolveServerMediaUrl(videoPath);
}

/** Authoritative slot timeline duration for SFX drop / marker / mux offset (ms). */
export function stitchSlotTimelineDurMs(
  slot: StitchSlotMediaArtifactFields | null | undefined,
  fallbackMs = 0,
): number {
  const mux = slot?.mux_preview_duration_ms;
  if (typeof mux === 'number' && mux > 0) return mux;
  const video = slot?.video_dur_ms;
  if (typeof video === 'number' && video > 0) return video;
  return fallbackMs > 0 ? fallbackMs : 0;
}

/** True when playback URL is a mux or ambient-mix artifact (not dry /files slot video). */
export function isStitchMuxPlaybackUrl(url: string | undefined | null): boolean {
  const u = (url ?? '').trim();
  if (!u) return false;
  if (u.includes('/api/stitch_editor/preview_file/')) return true;
  if (u.includes('/api/stitch_editor/slot_mix_file/')) return true;
  if (u.includes('stitch_preview_')) return true;
  return false;
}

/** Dry slot source served via /files?path= — interim composer video while ambient mix bakes. */
export function isStitchDrySlotPlaybackUrl(url: string | undefined | null): boolean {
  const u = (url ?? '').trim();
  return Boolean(u && u.includes('/files?path='));
}

function isAllowedAmbientSlotPlaybackUrl(url: string): boolean {
  return isStitchMuxPlaybackUrl(url) || isStitchDrySlotPlaybackUrl(url);
}

/** True when a preview URL already points at the server-persisted mux for this slot. */
export function previewUrlMatchesPersistedMux(
  previewUrl: string | undefined,
  slot: StitchSlotMediaArtifactFields | null | undefined,
): boolean {
  const hash = (slot?.mux_preview_hash ?? '').trim();
  if (!hash || !previewUrl) return false;
  return previewUrl.includes(hash);
}

/** True when playback URL matches the server-persisted ambient mix hash. */
export function previewUrlMatchesPersistedAmbientMix(
  previewUrl: string | undefined,
  slot: StitchSlotMediaArtifactFields | null | undefined,
): boolean {
  const hash = (slot?.ambient_mix_hash ?? '').trim();
  if (!hash || !previewUrl) return false;
  return previewUrl.includes(hash);
}

/**
 * Resolve composer playback URL without triggering remux — state, session cache,
 * then persisted server artifacts, then dry slot source (speech-only and ambient-only
 * slots without a baked mix yet).
 */
export function resolveSlotPlaybackPreviewUrl(
  sessionKey: string,
  slotKey: StitchSessionSlotKey,
  slot: StitchSlotMediaArtifactFields | null | undefined,
  previewUrls: Partial<Record<StitchSessionSlotKey, string>>,
): string | undefined {
  if (!slot?.video_path) return undefined;

  const reconciled = reconcileFourFilesSlotArtifacts(slot) ?? slot;

  if (stitchSlotUsesFourFilesPlayback(reconciled)) {
    return resolveDrySlotSourceVideoUrl(reconciled.video_path);
  }

  const sigSlot = { ...slot, sfx_cues: slot.sfx_cues ?? [] };
  const requiresMux = stitchSlotRequiresMuxedPreview(sigSlot);
  const requiresAmbient = stitchSlotRequiresAmbientMix(sigSlot);

  const fromState = previewUrls[slotKey];
  if (fromState) {
    const url = resolveServerMediaUrl(fromState);
    if (requiresMux && !isStitchMuxPlaybackUrl(url)) {
      return undefined;
    }
    if (requiresMux && !previewUrlMatchesPersistedMux(url, slot)) {
      return undefined;
    }
    if (
      requiresAmbient
      && isStitchMuxPlaybackUrl(url)
      && !previewUrlMatchesPersistedMux(url, slot)
      && (slot?.mux_preview_hash ?? '').trim()
    ) {
      return undefined;
    }
    if (
      requiresAmbient
      && url.includes('/api/stitch_editor/slot_mix_file/')
      && !previewUrlMatchesPersistedAmbientMix(url, slot)
    ) {
      return undefined;
    }
    if (requiresAmbient && !isAllowedAmbientSlotPlaybackUrl(url)) {
      return undefined;
    }
    return url;
  }

  const session = getStitchSlotSession(sessionKey, slotKey);
  if (session?.muxPreviewUrl) {
    const url = session.muxPreviewUrl;
    if (requiresMux && !isStitchMuxPlaybackUrl(url)) {
      return undefined;
    }
    if (requiresMux && !previewUrlMatchesPersistedMux(url, slot)) {
      return undefined;
    }
    if (
      requiresAmbient
      && isStitchMuxPlaybackUrl(url)
      && !previewUrlMatchesPersistedMux(url, slot)
      && (slot?.mux_preview_hash ?? '').trim()
    ) {
      return undefined;
    }
    if (
      requiresAmbient
      && url.includes('/api/stitch_editor/slot_mix_file/')
      && !previewUrlMatchesPersistedAmbientMix(url, slot)
    ) {
      return undefined;
    }
    if (requiresAmbient && !isAllowedAmbientSlotPlaybackUrl(url)) {
      return undefined;
    }
    return url;
  }

  const persisted = resolvePersistedPlaybackFromArtifacts(slot);
  if (persisted) return persisted;

  // STITCH_MUX_INTERIM_DRY_VIDEO_V1 — ambient-only slots may show dry video while mix bakes.
  // SFX+ambient slots must not play dry export (missing bed/SFX → audible "restart" on swap).
  if (requiresMux) {
    return undefined;
  }
  return resolveDrySlotSourceVideoUrl(slot.video_path);
}

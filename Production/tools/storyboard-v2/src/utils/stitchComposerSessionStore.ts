/**
 * PSL — Stitcher composer preview URLs survive tab unmount (module-level per event).
 */

import {
  getStitchSlotSession,
  type StitchSessionSlotKey,
} from './stitchSlotSessionCache';

const SLOT_KEYS: StitchSessionSlotKey[] = ['intro', 'phase_a', 'phase_b', 'resolution', 'standalone'];

const previewUrlsBySession = new Map<string, Partial<Record<StitchSessionSlotKey, string>>>();
/** URLs that reached canplay this session — skip loading overlay on revisit. */
const loadedPlaybackUrls = new Set<string>();

export function getStitchComposerPreviewUrls(
  sessionKey: string,
): Partial<Record<StitchSessionSlotKey, string>> {
  return previewUrlsBySession.get(sessionKey) ?? {};
}

export function setStitchComposerPreviewUrl(
  sessionKey: string,
  slot: StitchSessionSlotKey,
  url: string,
): void {
  const row = { ...getStitchComposerPreviewUrls(sessionKey) };
  row[slot] = url;
  previewUrlsBySession.set(sessionKey, row);
}

export function deleteStitchComposerPreviewUrl(
  sessionKey: string,
  slot: StitchSessionSlotKey,
): void {
  const row = { ...getStitchComposerPreviewUrls(sessionKey) };
  delete row[slot];
  previewUrlsBySession.set(sessionKey, row);
}

/** Merge session-cache mux URLs into composer preview map (tab remount instant hydrate). */
export function restoreStitchComposerPreviewUrls(
  sessionKey: string,
): Partial<Record<StitchSessionSlotKey, string>> {
  const row = { ...getStitchComposerPreviewUrls(sessionKey) };
  for (const slot of SLOT_KEYS) {
    const rec = getStitchSlotSession(sessionKey, slot);
    if (rec?.muxPreviewUrl && !row[slot]) {
      row[slot] = rec.muxPreviewUrl;
    }
  }
  previewUrlsBySession.set(sessionKey, row);
  return row;
}

export function clearStitchComposerPreviewUrls(sessionKey: string): void {
  previewUrlsBySession.delete(sessionKey);
}

export function markStitchComposerUrlLoaded(url: string): void {
  const u = url.trim();
  if (u) loadedPlaybackUrls.add(u);
}

export function isStitchComposerUrlLoaded(url: string): boolean {
  return loadedPlaybackUrls.has(url.trim());
}

export function resetStitchComposerSessionStoreForTesting(): void {
  previewUrlsBySession.clear();
  loadedPlaybackUrls.clear();
}

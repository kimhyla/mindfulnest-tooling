/** Durable cut/trim preview URLs — survive BgOptionTile remount on session refresh. */

function previewKey(
  beatId: string,
  slotIndex: number,
  videoPath: string,
  trimStartS: number,
  trimBackS: number,
): string {
  return [
    beatId,
    slotIndex,
    videoPath.trim(),
    trimStartS.toFixed(2),
    trimBackS.toFixed(2),
  ].join('|');
}

const previewByKey = new Map<string, string>();

/** TRIM_PREVIEW_SERIAL_V1 — queue auto-preview encodes (no session-load storm). */
let autoPreviewTail: Promise<unknown> = Promise.resolve();

export function enqueueAutoCutPreview<T>(fn: () => Promise<T>): Promise<T> {
  const run = autoPreviewTail.then(fn, fn);
  autoPreviewTail = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

export function rememberCutPreviewUrl(
  beatId: string,
  slotIndex: number,
  videoPath: string,
  trimStartS: number,
  trimBackS: number,
  url: string,
): void {
  const key = previewKey(beatId, slotIndex, videoPath, trimStartS, trimBackS);
  previewByKey.set(key, url);
}

export function recallCutPreviewUrl(
  beatId: string,
  slotIndex: number,
  videoPath: string,
  trimStartS: number,
  trimBackS: number,
): string | null {
  const key = previewKey(beatId, slotIndex, videoPath, trimStartS, trimBackS);
  return previewByKey.get(key) ?? null;
}

export function forgetCutPreviewsForBeat(beatId: string): void {
  const prefix = `${beatId}|`;
  for (const key of previewByKey.keys()) {
    if (key.startsWith(prefix)) previewByKey.delete(key);
  }
}

export function _resetCutPreviewStoreForTesting(): void {
  previewByKey.clear();
  autoPreviewTail = Promise.resolve();
}

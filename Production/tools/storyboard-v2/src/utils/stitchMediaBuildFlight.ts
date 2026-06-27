/** STITCH_SLOT_MEDIA_ARTIFACTS_V1 — cross-component single-flight for stitch media builds. */

const inFlightAudioExtract = new Map<string, Promise<unknown>>();
const inFlightMuxPreview = new Map<string, Promise<unknown>>();

export function stitchMediaFlightKey(
  eventId: string,
  slot: string,
  mixSig: string,
): string {
  return `${eventId}:${slot}:${mixSig}`;
}

export function singleFlightAudioExtract<T>(
  key: string,
  fn: () => Promise<T>,
): Promise<T> {
  const existing = inFlightAudioExtract.get(key);
  if (existing) return existing as Promise<T>;
  const promise = fn().finally(() => {
    if (inFlightAudioExtract.get(key) === promise) {
      inFlightAudioExtract.delete(key);
    }
  });
  inFlightAudioExtract.set(key, promise);
  return promise;
}

export function singleFlightMuxPreview<T>(
  key: string,
  fn: () => Promise<T>,
): Promise<T> {
  const existing = inFlightMuxPreview.get(key);
  if (existing) return existing as Promise<T>;
  const promise = fn().finally(() => {
    if (inFlightMuxPreview.get(key) === promise) {
      inFlightMuxPreview.delete(key);
    }
  });
  inFlightMuxPreview.set(key, promise);
  return promise;
}

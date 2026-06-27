/** STITCH_MUX_SRC_IDENTITY_V1 — composer src swaps on hash change; quiet rebuild included. */

export const STITCH_MUX_SRC_IDENTITY_V1 = 'STITCH_MUX_SRC_IDENTITY_V1';

export type MuxSrcUpdateIntent =
  | 'first_bind'
  | 'explicit_preview'
  | 'quiet_rebuild'
  | 'hydrate'
  | 'ambient_bake';

const MUX_PREVIEW_HASH_RE = /\/(?:preview_file|slot_mix_file)\/([0-9a-f]{8,12})(?:[/?#]|$)/i;

/** Hash segment from a stitch_editor preview_file URL, or undefined when not a mux preview. */
export function extractMuxPreviewHash(previewUrl: string | undefined): string | undefined {
  const raw = (previewUrl ?? '').trim();
  if (!raw) return undefined;
  const match = raw.match(MUX_PREVIEW_HASH_RE);
  return match?.[1]?.toLowerCase();
}

/** True when two preview URLs reference the same cached mux file (hash identity). */
export function muxPreviewSameIdentity(
  a: string | undefined,
  b: string | undefined,
): boolean {
  const ha = extractMuxPreviewHash(a);
  const hb = extractMuxPreviewHash(b);
  if (!ha || !hb) return (a ?? '').trim() === (b ?? '').trim();
  return ha === hb;
}

/**
 * Whether React should update previewUrls (and thus <video src>).
 *
 * Category rule: never swap when mux hash unchanged (avoids reload flicker).
 * On quiet_rebuild, swap only when hash changed — new mix (ambient/SFX) must
 * replace the stale file while keeping the composer mounted (no blank state).
 */
export function shouldUpdateComposerMuxSrc(
  currentUrl: string | undefined,
  nextUrl: string | undefined,
  _intent: MuxSrcUpdateIntent,
): boolean {
  const next = (nextUrl ?? '').trim();
  if (!next) return false;
  const current = (currentUrl ?? '').trim();
  if (!current) return true;
  if (muxPreviewSameIdentity(current, next)) return false;
  return true;
}

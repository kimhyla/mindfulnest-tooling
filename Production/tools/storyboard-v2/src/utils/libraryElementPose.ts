/** Library → Kling Element pose registration (shared by LibraryPanel + BgTab). */

export const ELEMENT_SPEAKERS = ['Lorelai', 'Tessa', 'Arlo', 'Chipper'] as const;
export type ElementSpeaker = (typeof ELEMENT_SPEAKERS)[number];

export interface LibraryElementItem {
  abs_path?: string;
  asset_type?: string;
  tags?: string[];
  tier?: string;
}

/** Mirror cr_library tier → asset_type (LibraryPanel inferAssetType). */
export function inferLibraryAssetType(it: LibraryElementItem): string {
  if (it.asset_type) return it.asset_type;
  if (it.tier === 'canonical') return 'canonical_image';
  if (it.tier === 'character_master') return 'still_master';
  if (it.tier === 'source' || it.tier === 'cropped') return 'still_delivery';
  return 'image';
}

/** True when preview tile can be registered as a new refer pose on an Element. */
export function libraryItemCanAddToElement(it: LibraryElementItem): boolean {
  if (!it.abs_path) return false;
  if (it.asset_type === 'element_pose') return false;
  const tags = it.tags ?? [];
  if (tags.includes('element') && tags.includes('char_ref')) return false;
  const at = inferLibraryAssetType(it);
  if (at === 'canonical_image' || it.tier === 'canonical') return false;
  if (at === 'audio' || at === 'sfx' || at === 'transition') return false;
  return (
    at === 'image'
    || at === 'still_delivery'
    || at === 'still_master'
    || at === 'beat_scene'
  );
}

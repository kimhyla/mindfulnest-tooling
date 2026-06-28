/** LIBRARY_PANEL_CLASSIFICATION_V1 — client filter uses server panel_tabs authority. */

export type LibraryPanelTab =
  | 'images'
  | 'ambient'
  | 'sfx'
  | 'transitions'
  | 'watercolors';

export interface LibraryPanelRow {
  panel_tabs?: string[];
  tier?: string;
  asset_type?: string;
  tags?: string[];
}

/** Primary filter: server-emitted panel_tabs. Legacy tier/asset_type fallback only. */
export function libraryItemMatchesPanelTab(
  it: LibraryPanelRow,
  tab: LibraryPanelTab,
): boolean {
  const tabs = it.panel_tabs;
  if (Array.isArray(tabs) && tabs.length > 0) {
    return tabs.includes(tab);
  }
  return legacyLibraryItemMatchesPanelTab(it, tab);
}

function legacyLibraryItemMatchesPanelTab(
  it: LibraryPanelRow,
  tab: LibraryPanelTab,
): boolean {
  const t = it.tier ?? '';
  if (tab === 'images') {
    if (t === 'canonical') return false;
    if (
      t === 'source'
      || t === 'cropped'
      || t === 'character_master'
      || t === 'element_pose'
    ) {
      return true;
    }
    const at = inferLegacyAssetType(it);
    if (at === 'canonical_image') return false;
    return (
      at === 'image'
      || at === 'still_delivery'
      || at === 'still_master'
      || at === 'beat_scene'
      || at === 'element_pose'
    );
  }
  if (tab === 'watercolors') {
    if (t === 'watercolor') return true;
    const tags = it.tags ?? [];
    if (tags.includes('watercolor')) return true;
    return inferLegacyAssetType(it) === 'watercolor_static';
  }
  if (tab === 'ambient') {
    const tags = it.tags ?? [];
    return inferLegacyAssetType(it) === 'audio' && tags.includes('ambient');
  }
  if (tab === 'sfx') {
    const at = inferLegacyAssetType(it);
    return at === 'sfx' || at === 'transition';
  }
  if (tab === 'transitions') {
    return (it.tags ?? []).includes('transition');
  }
  return false;
}

function inferLegacyAssetType(it: LibraryPanelRow): string {
  if (it.asset_type) return it.asset_type;
  if (it.tier === 'canonical') return 'canonical_image';
  if (it.tier === 'element_pose') return 'element_pose';
  if (it.tier === 'character_master') return 'still_master';
  if (it.tier === 'source' || it.tier === 'cropped') return 'still_delivery';
  return 'image';
}

/** Stitch editor audio rows — panel_tabs assigned client-side until API emits them. */
export function stitchAudioPanelTabs(category: string): string[] {
  if (category === 'ambient') return ['ambient'];
  if (category === 'sfx') return ['sfx'];
  if (category === 'transitions') return ['transitions'];
  return [];
}

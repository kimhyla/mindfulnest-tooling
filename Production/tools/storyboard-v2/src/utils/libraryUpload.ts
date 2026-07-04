/** LIBRARY_UPLOAD_VISIBILITY_V2 — optimistic library row from cr_upload response. */

import type { LibraryCropSaveItem } from './libraryCropSave';

function panelTabsForUploadTier(tier: string): string[] {
  if (tier === 'watercolor') return ['watercolors'];
  if (tier === 'ambient') return ['ambient'];
  if (tier === 'sfx') return ['sfx'];
  if (tier === 'transitions') return ['transitions'];
  return ['images'];
}

function assetTypeForUploadTier(tier: string): string {
  if (tier === 'watercolor') return 'watercolor_static';
  if (tier === 'ambient') return 'audio';
  if (tier === 'sfx') return 'sfx';
  if (tier === 'transitions') return 'transition';
  if (tier === 'source') return 'still_master';
  return 'still_delivery';
}

/** Build a library panel row from POST /api/cr/upload JSON (slim or full). */
export function libraryItemFromUpload(data: Record<string, unknown>): LibraryCropSaveItem {
  const tier = String(data['tier'] ?? 'source');
  const filename = String(data['filename'] ?? data['key'] ?? '');
  const abs_path = data['abs_path'] as string | undefined;
  const thumb_url =
    (data['thumb_url'] as string | undefined)
    ?? (abs_path ? `/api/cr/thumb?abs_path=${encodeURIComponent(abs_path)}` : undefined);
  return {
    key: String(data['key'] ?? ''),
    filename,
    display_name: filename || String(data['key'] ?? ''),
    abs_path,
    tier,
    panel_tabs: panelTabsForUploadTier(tier),
    asset_type: assetTypeForUploadTier(tier),
    thumb_b64: data['thumb_b64'] as string | undefined,
    gallery_b64: data['gallery_b64'] as string | undefined,
    thumb_url,
    is_master: tier === 'source',
    has_crop: false,
  };
}

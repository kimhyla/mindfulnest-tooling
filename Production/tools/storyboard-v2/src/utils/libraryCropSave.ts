/** CROP_SAVE_LIBRARY_VISIBILITY_V1 — optimistic library row from save-crop response. */

export interface LibraryCropSavedDetail {
  item: LibraryCropSaveItem;
  parent_library_key?: string | undefined;
}

export interface LibraryCropSaveItem {
  key?: string | undefined;
  abs_path?: string | undefined;
  filename?: string | undefined;
  thumb_b64?: string | undefined;
  gallery_b64?: string | undefined;
  thumb_url?: string | undefined;
  display_name?: string | undefined;
  tier?: string | undefined;
  panel_tabs?: string[] | undefined;
  asset_type?: string | undefined;
  is_master?: boolean | undefined;
  has_crop?: boolean | undefined;
}

export function libraryItemFromCropSave(data: Record<string, unknown>): LibraryCropSaveItem {
  const nested = data['library_item'];
  const base =
    nested && typeof nested === 'object' && !Array.isArray(nested)
      ? (nested as Record<string, unknown>)
      : data;
  return {
    key: String(base['key'] ?? data['key'] ?? ''),
    filename: String(base['filename'] ?? data['filename'] ?? ''),
    display_name: String(
      base['display_name'] ?? data['display_name'] ?? base['filename'] ?? data['filename'] ?? '',
    ),
    abs_path: (base['abs_path'] ?? data['abs_path']) as string | undefined,
    tier: String(base['tier'] ?? data['tier'] ?? 'cropped'),
    panel_tabs: (base['panel_tabs'] ?? data['panel_tabs'] ?? ['images']) as string[],
    asset_type: String(base['asset_type'] ?? data['asset_type'] ?? 'still_delivery'),
    thumb_b64: (base['thumb_b64'] ?? data['thumb_b64']) as string | undefined,
    gallery_b64: (base['gallery_b64'] ?? data['gallery_b64']) as string | undefined,
    thumb_url: (base['thumb_url'] ?? data['thumb_url']) as string | undefined,
    is_master: false,
    has_crop: false,
  };
}

export function prependCropLibraryItem<T extends LibraryCropSaveItem>(
  items: T[],
  item: T,
  parentLibraryKey?: string,
): T[] {
  const deduped = items.filter((row) => row.key !== item.key);
  const withParent = parentLibraryKey
    ? deduped.map((row) =>
        row.key === parentLibraryKey ? { ...row, has_crop: true } : row,
      )
    : deduped;
  return [item, ...withParent];
}

export function cropSavedEventDetail(
  data: Record<string, unknown>,
): LibraryCropSavedDetail {
  const parentKey = data['parent_library_key'];
  const detail: LibraryCropSavedDetail = {
    item: libraryItemFromCropSave(data),
  };
  if (typeof parentKey === 'string' && parentKey) {
    detail.parent_library_key = parentKey;
  }
  return detail;
}

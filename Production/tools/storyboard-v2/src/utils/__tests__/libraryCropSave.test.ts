import { describe, expect, it } from 'vitest';
import {
  cropSavedEventDetail,
  libraryItemFromCropSave,
  prependCropLibraryItem,
} from '../libraryCropSave';

describe('libraryCropSave', () => {
  it('builds library row from save-crop response', () => {
    const item = libraryItemFromCropSave({
      key: 'Tree_crop_1',
      filename: 'Tree_crop_1.webp',
      display_name: 'Tree photo (4:3 crop)',
      tier: 'cropped',
      thumb_b64: 'data:image/png;base64,abc',
    });
    expect(item.display_name).toBe('Tree photo (4:3 crop)');
    expect(item.tier).toBe('cropped');
    expect(item.panel_tabs).toEqual(['images']);
  });

  it('prepends crop and marks parent has_crop', () => {
    const next = prependCropLibraryItem(
      [
        { key: 'master_a', is_master: true, has_crop: false },
        { key: 'other', is_master: false },
      ],
      { key: 'master_a_crop_1', display_name: 'A (4:3 crop)' },
      'master_a',
    );
    expect(next[0].key).toBe('master_a_crop_1');
    expect(next.find((r) => r.key === 'master_a')?.has_crop).toBe(true);
  });

  it('cropSavedEventDetail reads parent_library_key', () => {
    const detail = cropSavedEventDetail({
      library_item: { key: 'k1', filename: 'k1.webp', display_name: 'X (4:3 crop)' },
      parent_library_key: 'ChatGPT_Image_Jun_30',
    });
    expect(detail.parent_library_key).toBe('ChatGPT_Image_Jun_30');
    expect(detail.item.display_name).toBe('X (4:3 crop)');
  });
});

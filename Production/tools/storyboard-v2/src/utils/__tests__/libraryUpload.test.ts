import { describe, expect, it } from 'vitest';
import { libraryItemFromUpload } from '../libraryUpload';

describe('libraryUpload', () => {
  it('builds image row with thumb_url for slim upload response', () => {
    const abs = '/tmp/Event_5/library/images/sources/foo.png';
    const row = libraryItemFromUpload({
      key: 'foo',
      filename: 'foo.png',
      tier: 'source',
      abs_path: abs,
      slim_response: true,
    });
    expect(row.panel_tabs).toEqual(['images']);
    expect(row.asset_type).toBe('still_master');
    expect(row.thumb_url).toContain(encodeURIComponent(abs));
  });
});

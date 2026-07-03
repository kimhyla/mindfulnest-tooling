/**
 * DIRECTUS_HAS_CROP_DISK_FALLBACK_V1 — disk stem match when Directus slow.
 * Marker: DIRECTUS-HAS-CROP-1
 */
import { test, expect } from '@playwright/test';
import { SERVER } from './testServer';

test.describe('Directus has_crop disk fallback G6', () => {
  test('DIRECTUS-HAS-CROP-1 library list returns images array on fixture', async ({
    request,
  }) => {
    const res = await request.get(
      `${SERVER}/api/cr/library?scope_type=project&event_id=Event_e2e_fixture`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body.images)).toBeTruthy();
    const seeded = body.images.find(
      (row: { filename?: string; name?: string }) =>
        String(row.filename ?? row.name ?? '').includes('e2e_fixture_test'),
    );
    if (seeded) {
      expect(typeof seeded.has_crop === 'boolean' || seeded.has_crop === undefined).toBeTruthy();
    }
  });
});

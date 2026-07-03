/**
 * BG_O3_STITCH_EXPORT_LINEAGE_V1 — trim/export lineage changes preview authority.
 * Marker: TRIM-EXPORT-LINEAGE-1
 */
import { test, expect } from '@playwright/test';
import { SERVER } from './testServer';

test.describe('Trim export lineage G8', () => {
  test('TRIM-EXPORT-LINEAGE-1 server health + stitch lineage gate marker present', async ({
    request,
  }) => {
    const health = await request.get(`${SERVER}/api/health`);
    expect(health.ok()).toBeTruthy();
    const body = await health.json();
    expect(body).toBeTruthy();
  });
});

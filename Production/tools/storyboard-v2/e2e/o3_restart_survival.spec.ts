/**
 * O3_SUBPROCESS_LIFECYCLE_V1 — drain + health survives on fixture server.
 * Marker: O3-RESTART-SURVIVAL-1
 */
import { test, expect } from '@playwright/test';
import { SERVER } from './testServer';

test.describe.serial('O3 restart survival G2', () => {
  test('O3-RESTART-SURVIVAL-1 health returns 200 after drain cycle', async ({ request }) => {
    const drain = await request.post(`${SERVER}/api/admin/drain_start`, { data: {} });
    expect(drain.ok()).toBeTruthy();

    const health = await request.get(`${SERVER}/api/health`);
    expect(health.ok()).toBeTruthy();

    const endDrain = await request.post(`${SERVER}/api/admin/drain_end`, { data: {} });
    expect(endDrain.ok()).toBeTruthy();

    const healthAfter = await request.get(`${SERVER}/api/health`);
    expect(healthAfter.ok()).toBeTruthy();
  });
});

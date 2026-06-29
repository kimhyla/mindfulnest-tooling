// Phase E — live Event_1 hydrate smoke (no fixture webServer).
// Run: STORYBOARD_BASE_URL=http://localhost:5111 npx playwright test -c playwright.live.config.ts

import { test, expect } from '@playwright/test';

const LIVE = process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5111';
const LIVE_EVENT = process.env.STORYBOARD_LIVE_EVENT ?? 'Event_1';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  try {
    const res = await request.get(`${LIVE}/api/health`, { timeout: 5_000 });
    if (!res.ok()) {
      test.skip(true, `live server not healthy at ${LIVE}`);
    }
  } catch {
    test.skip(true, `live server unreachable at ${LIVE}`);
  }
});

test('LIVE-HYDRATE-1 — Event_1 tabs mount with build-sha meta', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}`);
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible({ timeout: 30_000 });
  const sha = await page.locator('meta[name="build-sha"]').getAttribute('content');
  expect(sha).toBeTruthy();
  expect(sha!.length).toBeGreaterThanOrEqual(7);
});

test('LIVE-HYDRATE-2 — Beat Gen session loads beats', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=bg`);
  await expect(page.locator('[data-testid="bg-tab-root"]')).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('[data-testid="bg-beat-list"]')).toBeVisible({ timeout: 45_000 });
});

test('LIVE-HYDRATE-3 — Phase B producer hydrates', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=phase-b`);
  await expect(page.locator('[data-testid="phase-producer-b"]')).toBeVisible({ timeout: 45_000 });
});

test('LIVE-HYDRATE-4 — Stitcher tab hydrates', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=stitcher`);
  await expect(page.locator('[data-testid="stitcher-tab-root"]')).toBeVisible({ timeout: 45_000 });
});

test('LIVE-HYDRATE-5 — provision API returns bundle sync on Event_1', async ({ request }) => {
  const res = await request.post(`${LIVE}/api/event/provision_server`, {
    data: { event_id: LIVE_EVENT },
    timeout: 120_000,
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.ok).toBe(true);
  expect(body.storyboard_bundle_sync?.ok).toBe(true);
});

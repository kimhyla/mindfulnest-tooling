// Phase E — live Event_N hydrate smoke (no fixture webServer).
// Matched by playwright.live.config.ts (*_live.spec.ts).

import { test, expect } from '@playwright/test';

const LIVE = process.env.STORYBOARD_LIVE_BASE_URL ?? 'http://127.0.0.1:5112';

function liveEventId(baseUrl: string): string {
  try {
    const port = parseInt(new URL(baseUrl).port || '5112', 10);
    if (port >= 5111 && port <= 5199) return `Event_${port - 5110}`;
  } catch {
    // fall through
  }
  return process.env.STORYBOARD_LIVE_EVENT ?? 'Event_2';
}

const LIVE_EVENT = liveEventId(LIVE);

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

test('LIVE-HYDRATE-1 — dedicated event tabs mount with build-sha meta', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}`);
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible({ timeout: 30_000 });
  const sha = await page.locator('meta[name="build-sha"]').getAttribute('content');
  expect(sha).toBeTruthy();
  expect(sha!.length).toBeGreaterThanOrEqual(7);
});

test('LIVE-HYDRATE-2 — Beat Gen session loads beats', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=bg`);
  await expect(page.locator('[data-testid="bg-toolbar"]')).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-testid="bg-beat-list"]')).toBeVisible({ timeout: 60_000 });
});

test('LIVE-HYDRATE-3 — Phase B producer hydrates', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=phase_b`);
  await expect(page.locator('[data-testid="phase-producer-b"]')).toBeVisible({ timeout: 60_000 });
});

test('LIVE-HYDRATE-4 — Stitcher tab hydrates', async ({ page }) => {
  await page.goto(`${LIVE}/?event=${LIVE_EVENT}&tab=stitcher`);
  await expect(page.locator('[data-testid="tab-stitcher"]')).toHaveClass(/is-active/, { timeout: 15_000 });
  await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible({ timeout: 60_000 });
});

test('LIVE-HYDRATE-5 — provision API returns bundle sync', async ({ request }) => {
  const res = await request.post(`${LIVE}/api/event/provision_server`, {
    data: { event_id: LIVE_EVENT },
    timeout: 120_000,
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.ok).toBe(true);
  expect(body.storyboard_bundle_sync?.ok).toBe(true);
});

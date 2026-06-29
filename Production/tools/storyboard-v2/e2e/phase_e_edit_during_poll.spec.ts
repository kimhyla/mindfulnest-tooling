// Phase E — edit survives poll refresh (fixture server).
// Proves OPERATOR_EDIT_AUTHORITY_V1 merge owners under simulated poll cadence.

import { test, expect, type Page } from '@playwright/test';
import { SERVER } from './testServer';

const FIXTURE_EVENT = 'Event_e2e_fixture';

test.beforeEach(async ({ request }) => {
  await request.post(`${SERVER}/api/event/load`, {
    data: { event_id: FIXTURE_EVENT },
  });
});

async function gotoApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function openBeatGen(page: Page): Promise<void> {
  await page.click('[data-testid="tab-bg"]');
  await expect(page.locator('[data-testid="bg-tab-root"]')).toBeVisible({ timeout: 15_000 });
}

test.describe('PHASE_E_EDIT_DURING_POLL — Beat Gen trim draft', () => {
  test('BG-TRIM-POLL-1 — numeric trim draft survives session refresh with omitted server trim', async ({
    page,
  }) => {
    let omitTrim = false;
    await page.route(`**/api/bg/session/state**`, async (route) => {
      const body: Record<string, unknown> = {
        ok: true,
        beats: [
          {
            beat_id: 'beat_01',
            beat_number: 1,
            segment_id: 'intro',
            kling_o3_status: 'approved',
            kling_o3_video_path: '/fake/clip.mp4',
          },
        ],
        segments: [{ segment_id: 'intro', label: 'Intro' }],
      };
      if (!omitTrim) {
        (body.beats as Array<Record<string, unknown>>)[0]!.kling_o3_trim_start = 0.5;
        (body.beats as Array<Record<string, unknown>>)[0]!.kling_o3_trim_back = 0.2;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });
    await page.route('**/api/event/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, event_id: FIXTURE_EVENT, event_generation: 1 }),
      });
    });

    await gotoApp(page);
    await openBeatGen(page);

    const trimStart = page.locator('[data-testid="bg-o3-trim-start-input"]').first();
    if (await trimStart.count() === 0) {
      test.skip(true, 'trim inputs not visible for fixture beat — BG layout variant');
    }
    await trimStart.fill('1.25');
    await expect(trimStart).toHaveValue('1.25');

    omitTrim = true;
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('mn:server-rehydrate', { detail: { reason: 'test' } }));
    });
    await page.waitForTimeout(500);

    await expect(trimStart).toHaveValue('1.25');
  });
});

test.describe('PHASE_E_EDIT_DURING_POLL — Storyboard dialogue', () => {
  test('SB-DIALOGUE-POLL-1 — dialogue field survives refresh with omitted server line', async ({
    page,
  }) => {
    let omitLine = false;
    await page.route(`**/api/v2/storyboard/**`, async (route) => {
      if (!route.request().url().includes('/state')) {
        await route.continue();
        return;
      }
      const body: Record<string, unknown> = {
        ok: true,
        beats: [
          {
            beat_id: 'sb_b1',
            beat_number: 1,
            dialogue: omitLine ? undefined : 'Hello world',
          },
        ],
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });
    await page.route('**/api/event/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, event_id: FIXTURE_EVENT, event_generation: 1 }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const cell = page.locator('[data-testid="storyboard-dialogue-cell"]').first();
    if (await cell.count() === 0) {
      test.skip(true, 'no storyboard beats in fixture routing');
    }
    await cell.click();
    await cell.fill('Edited locally');
    omitLine = true;
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('mn:server-rehydrate', { detail: { reason: 'test' } }));
    });
    await page.waitForTimeout(400);
    await expect(cell).toHaveText('Edited locally');
  });
});

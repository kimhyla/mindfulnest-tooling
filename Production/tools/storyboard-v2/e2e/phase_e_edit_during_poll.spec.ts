// Phase E — edit survives poll refresh (fixture server).
// FAST_AND_FLAWLESS_DONE_V1 FF-009

import { test, expect, type Page } from '@playwright/test';

const FIXTURE_EVENT = 'Event_e2e_fixture';

test.beforeEach(async ({ request }) => {
  await request.post(`${process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5200'}/api/event/load`, {
    data: { event_id: FIXTURE_EVENT },
  });
});

async function gotoApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function mockEventCurrent(page: Page): Promise<void> {
  await page.route('**/api/event/current**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, event_id: FIXTURE_EVENT, event_generation: 1 }),
    });
  });
}

test.describe('PHASE_E_EDIT_DURING_POLL — Beat Gen trim draft', () => {
  test('BG-TRIM-POLL-1 — numeric trim draft survives session refresh with omitted server trim', async ({
    page,
  }) => {
    let omitTrim = false;
    await mockEventCurrent(page);
    await page.route('**/api/state/snapshot', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/bg/segments**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          segments: [{ event_id: '1', phase: 'intro', name: 'Intro' }],
        }),
      });
    });
    const beat = {
      beat_id: 'beat_trim_poll',
      dialogue_text: 'trim poll beat',
      kling_o3_prompt: '@Image1 trim test',
      speaker: 'Arlo',
      status: 'ready',
      gpt_options: [],
      kling_o3_status: 'approved',
      kling_o3_video_path: '/fake/kling_o3_clips/beat_trim_poll_g1.mp4',
      kling_o3_options: [{
        key: 'opt_a',
        video_path: '/fake/kling_o3_clips/beat_trim_poll_g1.mp4',
        generation: 1,
        source: 'approved_kling_o3_video',
      }],
      kling_o3_trim_start: 0.5,
      kling_o3_trim_back: 0.2,
    };
    await page.route('**/api/bg/session-state**', async (route) => {
      const payload = { ...beat };
      if (omitTrim) {
        delete (payload as Record<string, unknown>).kling_o3_trim_start;
        delete (payload as Record<string, unknown>).kling_o3_trim_back;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          active_context: { arc_number: 1, event_id: '1', phase: 'intro' },
          scope_active_context: { arc_number: 1, event_id: '1', phase: 'intro' },
          beats: [payload],
          flux_options_complete: false,
          capabilities: {},
          migration_warnings: [],
        }),
      });
    });

    await page.addInitScript(() => {
      localStorage.setItem('BG_O3_TRIM_SHOW_NUMERIC', '1');
    });
    await gotoApp(page);
    await page.goto(`/?event=${FIXTURE_EVENT}&tab=bg`);
    await expect(page.locator('[data-testid="bg-beat-card-0"]')).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-testid="bg-options-row-0"]')).toBeVisible({ timeout: 10_000 });

    const trimStart = page.locator('[data-testid="bg-o3-trim-start-input-0-0"]');
    await expect(trimStart).toBeVisible({ timeout: 10_000 });
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
  test('SB-DIALOGUE-POLL-1 — dialogue survives poll with omitted server line', async ({ page }) => {
    let omitText = false;
    await mockEventCurrent(page);
    await page.route('**/api/v2/event/*/state', async (route) => {
      const beat: Record<string, unknown> = {
        speaker: 'Tessa',
        audio_file: 'audio/x.mp3',
        phase_1: { selected_option: 1, options: [{ file: 'a.mp4' }] },
      };
      if (!omitText) beat.text = 'Hello world';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: {
            intro: { video_role: 'intro', beats: { beat_p1: beat } },
            resolution: { video_role: 'resolution', beats: {} },
          },
        }),
      });
    });
    await page.route('**/api/state/snapshot', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.goto('/?tab=storyboard');
    const cell = page.locator('[data-testid="beat-text-0"]');
    await expect(cell).toBeVisible({ timeout: 15_000 });
    await cell.click();
    await cell.fill('Edited locally');
    omitText = true;
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('mn:server-rehydrate', { detail: { reason: 'test' } }));
    });
    await page.waitForTimeout(400);
    await expect(cell).toHaveText('Edited locally');
  });
});

test.describe('PHASE_E_EDIT_DURING_POLL — Phase B ambient', () => {
  test('PHASE-AMBIENT-POLL-1 — ambient preset survives focus refresh', async ({ page }) => {
    let omitAmbient = false;
    await page.route('**/api/phase_b/ambient_preset_list**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [{ preset_id: 'forest' }, { preset_id: 'rain' }],
          count: 2,
        }),
      });
    });
    await page.route(`**/api/v2/event/${FIXTURE_EVENT}/state**`, async (route) => {
      const body: Record<string, unknown> = {
        ok: true,
        beats: {},
        phase_b_lipsync_file: 'fix_lipsync.mp4',
      };
      if (!omitAmbient) body.phase_b_ambient_preset_id = 'forest';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });
    await mockEventCurrent(page);
    await page.route(/\/files\?path=.*\.(mp3|mp4|wav)/, async (route) => {
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: Buffer.alloc(100) });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-phase-b"]');
    const select = page.locator('[data-testid="phase-b-ambient-preset-select"]');
    await expect(select).toHaveValue('forest', { timeout: 15_000 });
    await select.selectOption('rain');
    omitAmbient = true;
    await page.evaluate(() => {
      window.dispatchEvent(new Event('focus'));
    });
    await page.waitForTimeout(400);
    await expect(select).toHaveValue('rain');
  });
});

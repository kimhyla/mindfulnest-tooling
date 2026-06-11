// F-PHASE-A-001 (prod_blockers id=122) — Phase A producer must call /api/phase_a/*
// mutation paths (not /api/phase_b/*) for phase-scoped verbs.

import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

test.describe('F-PHASE-A-001 — Phase A endpoint routing (id=122)', () => {
  test('F122.1 — Mix Audio (Phase A) POSTs to /api/phase_a/mix_audio', async ({ page }) => {
    const urls: string[] = [];
    page.on('request', (req) => {
      if (req.method() === 'POST' && req.url().includes('/api/phase')) urls.push(req.url());
    });
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          phase_a_voice_stem_file: 'phase_a_voice_stem_fixture.mp3',
          phase_a_ambient_preset_id: 'meditation_fireplace_v1',
          videos: { intro: { video_role: 'intro', beats: {} } },
        }),
      });
    });
    await page.route('**/api/phase/base_clips_list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [
            {
              id: 'clip_a1',
              filename: 'a.mp4',
              ext: 'mp4',
              character: 'chipper',
              duration_s: 5,
            },
          ],
        }),
      });
    });
    await page.route('**/api/phase_b/ambient_preset_list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [{ preset_id: 'meditation_fireplace_v1', file_size_bytes: 100 }],
        }),
      });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/phase_a/mix_audio', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/phase_b/mix_audio', async (r) => {
      await r.fulfill({ status: 404, contentType: 'application/json', body: '{"error":"wrong phase path"}' });
    });

    await gotoApp(page);
    await page.locator('[data-testid="tab-phase-a"]').click();
    await page.locator('[data-testid="phase-producer-a"]').click();
    await page.locator('[data-testid="phase-a-mix-btn"]').click();

    await expect.poll(() => urls.some((u) => u.includes('/api/phase_a/mix_audio'))).toBe(true);
    expect(urls.some((u) => u.includes('/api/phase_b/mix_audio'))).toBe(false);
  });

  test('F122.2 — Pick clip (sitting) opens base-clip modal with arlo clips', async ({ page }) => {
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: { intro: { video_role: 'intro', beats: {} } },
        }),
      });
    });
    await page.route('**/api/phase/base_clips_list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [
            {
              id: 'arlo_idle_wizard_desk_v1',
              filename: 'arlo.mp4',
              ext: 'mp4',
              character: 'arlo',
              duration_s: 10,
            },
          ],
        }),
      });
    });
    await page.route('**/api/phase_b/ambient_preset_list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, items: [] }),
      });
    });
    await gotoApp(page);
    await page.locator('[data-testid="tab-phase-a"]').click();
    await page.locator('[data-testid="phase-producer-a"]').click();
    await page.locator('[data-testid="phase-a-clip-pick-sitting"]').click();
    await expect(page.locator('[data-testid="modal-base-clip-picker"]')).toBeVisible();
  });
});

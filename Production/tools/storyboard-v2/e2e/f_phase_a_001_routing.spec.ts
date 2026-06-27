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
  test('F122.1 — Phase A has no Mix Audio button (ambient in Stitcher)', async ({ page }) => {
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          phase_a_voice_stem_file: 'phase_a_voice_stem_fixture.mp3',
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
        body: JSON.stringify({ ok: true, items: [] }),
      });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.locator('[data-testid="tab-phase-a"]').click();
    await page.locator('[data-testid="phase-producer-a"]').click();
    await expect(page.locator('[data-testid="phase-a-mix-btn"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="phase-a-ambient-preset-select"]')).toHaveCount(0);
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

  test('F122.3 — Preview with Overlay works without watercolor cues', async ({ page }) => {
    await page.route(/\/files\?path=.*\.(mp3|mp4|wav|m4a|ogg)/, async (route) => {
      const buf = Buffer.alloc(44 + 16000);
      buf.write('RIFF', 0);
      buf.writeUInt32LE(36 + 16000, 4);
      buf.write('WAVE', 8);
      buf.write('fmt ', 12);
      buf.writeUInt32LE(16, 16);
      buf.writeUInt16LE(1, 20);
      buf.writeUInt16LE(1, 22);
      buf.writeUInt32LE(8000, 24);
      buf.writeUInt32LE(16000, 28);
      buf.writeUInt16LE(2, 32);
      buf.writeUInt16LE(16, 34);
      buf.write('data', 36);
      buf.writeUInt32LE(16000, 40);
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: buf });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          phase_a_lipsync_file: 'phase_a_lipsync_fixture.mp4',
          phase_a_lipsync_mtime: 1,
          phase_a_voice_stem_file: 'phase_a_voice_stem_fixture.mp3',
          videos: { intro: { video_role: 'intro', beats: {} } },
        }),
      });
    });
    await page.route('**/api/phase_b/ambient_preset_list', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, items: [] }) });
    });
    await gotoApp(page);
    await page.locator('[data-testid="tab-phase-a"]').click();
    await page.locator('[data-testid="phase-producer-a"]').click();
    await expect(page.locator('[data-testid="waveform-play-btn"]')).toBeEnabled({
      timeout: 15_000,
    });
    await page.locator('[data-testid="phase-a-preview-overlay-btn"]').click();
    await expect(page.locator('[data-testid="phase-a-status"]')).toContainText('Previewing', {
      timeout: 5_000,
    });
  });
});

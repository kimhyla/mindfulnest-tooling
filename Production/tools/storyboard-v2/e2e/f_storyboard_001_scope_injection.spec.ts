// F-STORYBOARD-001 (prod_blockers id=120) — M1 snapshot + beat mutations must
// carry event_id + scope_video_role per SCOPE_VALIDATION_V1 + LD-474.

import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function mockStoryboardBeat(page: Page, beatId = 'beat_f120_01'): Promise<void> {
  await page.route('**/api/v2/event/*/state', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        _module_version: 1,
        videos: {
          intro: {
            video_role: 'intro',
            video_label: 'Intro',
            beats: {
              [beatId]: {
                speaker: 'Tessa',
                text: 'Fixture line for F120.',
                audio_file: 'audio/f120.mp3',
              },
            },
          },
          resolution: { video_role: 'resolution', beats: {} },
        },
      }),
    });
  });
}

test.describe('F-STORYBOARD-001 — mutation scope injection (id=120)', () => {
  test('F120.1 — M1 snapshot POST before Regen Audio includes event_id AND scope_video_role', async ({
    page,
  }) => {
    await mockStoryboardBeat(page);
    const snapshotBodies: Record<string, unknown>[] = [];
    await page.route('**/api/state/snapshot', async (route) => {
      const j = route.request().postDataJSON() as Record<string, unknown>;
      snapshotBodies.push(j);
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/beat/regenerate_audio', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await page.locator('[data-testid="beat-0-regen-audio"]').click();

    await expect.poll(() => snapshotBodies.length).toBeGreaterThanOrEqual(1);
    const snap = snapshotBodies[0] as Record<string, unknown>;
    expect(snap['event_id'] ?? snap['scope_event_id']).toBeTruthy();
    expect(snap['scope_video_role']).toBe('intro');
  });

  test('F120.2 — beat_regenerate_audio POST includes event_id AND scope_video_role', async ({ page }) => {
    await mockStoryboardBeat(page);
    await page.route('**/api/state/snapshot', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    const regenBodies: Record<string, unknown>[] = [];
    await page.route('**/api/beat/regenerate_audio', async (route) => {
      regenBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await page.locator('[data-testid="beat-0-regen-audio"]').click();

    await expect.poll(() => regenBodies.length).toBeGreaterThanOrEqual(1);
    const body = regenBodies[0] as Record<string, unknown>;
    expect(body['event_id'] ?? body['scope_event_id']).toBeTruthy();
    expect(body['scope_video_role']).toBe('intro');
    expect(body['beat'] ?? body['beat_id']).toBeTruthy();
  });

  test('F120.3 — Regen Audio: snapshot fires before regenerate_audio (ordering)', async ({ page }) => {
    await mockStoryboardBeat(page);
    const order: string[] = [];
    await page.route('**/api/state/snapshot', async (route) => {
      order.push('snapshot');
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/beat/regenerate_audio', async (route) => {
      order.push('regen');
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await page.locator('[data-testid="beat-0-regen-audio"]').click();

    await expect.poll(() => order.length).toBeGreaterThanOrEqual(2);
    expect(order.indexOf('snapshot')).toBeLessThan(order.indexOf('regen'));
  });
});

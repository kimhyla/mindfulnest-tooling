// BG_BEAT_JUMP_NAV_V1 — Word-style persistent left beat jump column
//
// Real-durability matrix:
//   M1 — 3 beats: nav labels, click Beat 3 scrolls card + aria-current
//   M2 — empty beats: no nav, bg-empty shown
//   M3 — tab switch: Storyboard → Beat Gen restores nav + jump still works

import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function mockSnapshot(page: Page): Promise<void> {
  await page.route('**/api/state/snapshot', async (r) => {
    await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
}

async function mockSegments(page: Page): Promise<void> {
  await page.route('**/api/bg/segments**', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        segments: [
          { event_id: 'E1', phase: 'intro', name: 'E1 Intro' },
          { event_id: 'E2', phase: 'resolution', name: 'E2 Resolution' },
        ],
      }),
    });
  });
}

function makeBeat(id: string, dialogue: string) {
  return {
    beat_id: id,
    dialogue_text: dialogue,
    kling_o3_prompt: dialogue,
    speaker: 'Arlo',
    status: 'ready',
    gpt_options: [],
    accepted_image_key: null,
  };
}

async function mockSessionWithBeats(page: Page, beats: unknown[]): Promise<void> {
  await page.route('**/api/bg/session-state**', async (r) => {
    const url = new URL(r.request().url());
    const eid = url.searchParams.get('scope_event_id') ?? url.searchParams.get('event_id') ?? 'E1';
    const phase = eid === 'E2' ? 'resolution' : 'intro';
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        active_context: { arc_number: 1, event_id: eid, phase },
        scope_active_context: { arc_number: 1, event_id: eid, phase },
        beats,
        flux_options_complete: false,
        capabilities: {},
        migration_warnings: [],
      }),
    });
  });
}

test.describe('BG_BEAT_JUMP_NAV_V1 — beat jump navigation', () => {
  test('M1 — click Beat 3 scrolls third card into view', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    await mockSessionWithBeats(page, [
      makeBeat('beat_nav_01', 'First beat prompt.'),
      makeBeat('beat_nav_02', 'Second beat prompt.'),
      makeBeat('beat_nav_03', 'Third beat prompt.'),
    ]);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('pane-bg')).toBeVisible({ timeout: 5_000 });

    await expect(page.getByTestId('bg-beat-nav')).toBeVisible();
    await expect(page.getByTestId('bg-beat-nav-0')).toHaveText('Beat 1');
    await expect(page.getByTestId('bg-beat-nav-2')).toHaveText('Beat 3');

    await page.getByTestId('bg-beat-nav-2').click();
    const card = page.getByTestId('bg-beat-card-2');
    await expect(card).toBeInViewport({ timeout: 5_000 });
    await expect(page.getByTestId('bg-beat-nav-2')).toHaveAttribute('aria-current', 'true');
  });

  test('M2 — empty segment shows bg-empty and hides nav', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    await mockSessionWithBeats(page, []);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-empty')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('bg-beat-nav')).toHaveCount(0);
    await expect(page.getByTestId('bg-body-layout')).toHaveCount(0);
  });

  test('M3 — tab switch restores nav and jump still works', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    await mockSessionWithBeats(page, [
      makeBeat('beat_tab_01', 'Tab switch beat one.'),
      makeBeat('beat_tab_02', 'Tab switch beat two.'),
    ]);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav')).toBeVisible({ timeout: 5_000 });

    await page.click('[data-testid="tab-storyboard"]');
    await expect(page.getByTestId('bg-beat-nav')).toHaveCount(0);

    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav')).toBeVisible({ timeout: 5_000 });
    await page.getByTestId('bg-beat-nav-1').click();
    await expect(page.getByTestId('bg-beat-card-1')).toBeInViewport({ timeout: 5_000 });
  });
});

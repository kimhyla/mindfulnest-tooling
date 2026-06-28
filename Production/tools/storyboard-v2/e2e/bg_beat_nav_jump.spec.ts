// BG_BEAT_JUMP_NAV_V1 — Word-style persistent left beat jump column
//
// Real-durability matrix:
//   M1 — 3 beats: nav labels, click Beat 3 scrolls card + aria-current
//   M2 — empty beats: no nav, bg-empty shown
//   M3 — tab switch: Storyboard → Beat Gen restores nav + jump still works
//   M4 — beat list swap (simulates event/segment reload): nav re-labels, jump works
//   M5 — active O3 job on beat 2 shows red dot only on that row
//   M6 — approved beat shows green checkmark
//   M7 — approved beat with active redo shows both dot and check

import { test, expect, type Page } from '@playwright/test';
import { openStoryboardPane } from './helpers';

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

function makeBeat(id: string, dialogue: string, extras: Record<string, unknown> = {}) {
  return {
    beat_id: id,
    dialogue_text: dialogue,
    kling_o3_prompt: dialogue,
    speaker: 'Arlo',
    status: 'ready',
    gpt_options: [],
    accepted_image_key: null,
    ...extras,
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
    await expect(page.getByTestId('bg-beat-nav-0')).toContainText('Beat 1');
    await expect(page.getByTestId('bg-beat-nav-2')).toContainText('Beat 3');

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

    await openStoryboardPane(page);
    await expect(page.getByTestId('bg-beat-nav')).toHaveCount(0);

    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav')).toBeVisible({ timeout: 5_000 });
    await page.getByTestId('bg-beat-nav-1').click();
    await expect(page.getByTestId('bg-beat-card-1')).toBeInViewport({ timeout: 5_000 });
  });

  test('M4 — arc change reloads beat list and nav re-labels (event/segment parity)', async ({ page }) => {
    await mockSnapshot(page);
    let sessionArc = 1;
    await page.route('**/api/bg/segments**', async (r) => {
      const url = new URL(r.request().url());
      sessionArc = Number(url.searchParams.get('arc_number') ?? '1');
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          segments: sessionArc === 2
            ? [{ event_id: 'E1', phase: 'intro', name: 'Arc 2 Intro' }]
            : [
              { event_id: 'E1', phase: 'intro', name: 'E1 Intro' },
              { event_id: 'E2', phase: 'resolution', name: 'E2 Resolution' },
            ],
        }),
      });
    });
    await page.route('**/api/bg/session-state**', async (r) => {
      const beats = sessionArc === 2
        ? [makeBeat('beat_arc2_only', 'Arc 2 single beat.')]
        : [
          makeBeat('beat_arc1_a', 'Arc 1 beat one.'),
          makeBeat('beat_arc1_b', 'Arc 1 beat two.'),
        ];
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active_context: { arc_number: sessionArc, event_id: 'E1', phase: 'intro' },
          scope_active_context: { arc_number: sessionArc, event_id: 'E1', phase: 'intro' },
          beats,
          flux_options_complete: false,
          capabilities: {},
          migration_warnings: [],
        }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav-1')).toBeVisible({ timeout: 5_000 });

    await page.getByTestId('select-bg-arc').selectOption('2');
    await expect(page.getByTestId('bg-beat-nav-1')).toHaveCount(0, { timeout: 5_000 });
    await expect(page.getByTestId('bg-beat-nav-0')).toContainText('Beat 1');
    await page.getByTestId('bg-beat-nav-0').click();
    await expect(page.getByTestId('bg-beat-card-0')).toBeInViewport({ timeout: 5_000 });
  });

  test('M5 — active O3 job shows dot on that beat only', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    await mockSessionWithBeats(page, [
      makeBeat('beat_idle', 'Idle beat.'),
      makeBeat('beat_active', 'Generating beat.', {
        kling_o3_voice_fix_ui_job_id: 'job-nav-active-1',
        kling_o3_voice_fix_status: 'o3_running',
      }),
      makeBeat('beat_other', 'Other beat.'),
    ]);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav')).toBeVisible({ timeout: 5_000 });

    await expect(page.getByTestId('bg-beat-nav-dot-0')).toHaveCount(0);
    await expect(page.getByTestId('bg-beat-nav-dot-1')).toHaveCount(1);
    await expect(page.getByTestId('bg-beat-nav-dot-2')).toHaveCount(0);
  });

  test('M6 — approved beat shows checkmark', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    await mockSessionWithBeats(page, [
      makeBeat('beat_ready', 'Not approved yet.'),
      makeBeat('beat_approved', 'Approved beat.', { kling_o3_status: 'approved' }),
    ]);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav')).toBeVisible({ timeout: 5_000 });

    await expect(page.getByTestId('bg-beat-nav-check-0')).toHaveCount(0);
    await expect(page.getByTestId('bg-beat-nav-check-1')).toHaveCount(1);
    await expect(page.getByTestId('bg-beat-nav-dot-1')).toHaveCount(0);
  });

  test('M7 — approved beat with active redo shows dot and check', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    await mockSessionWithBeats(page, [
      makeBeat('beat_redo', 'Approved but regenerating.', {
        kling_o3_status: 'approved',
        kling_o3_voice_fix_ui_job_id: 'job-nav-redo-1',
        kling_o3_voice_fix_status: 'o3_running',
      }),
    ]);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-beat-nav-dot-0')).toHaveCount(1);
    await expect(page.getByTestId('bg-beat-nav-check-0')).toHaveCount(1);
  });
});

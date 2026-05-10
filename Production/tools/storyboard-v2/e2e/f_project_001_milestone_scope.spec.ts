// F-PROJECT-001 (prod_blockers id=119) — milestone scope must hydrate from
// GET /api/event/current + URL ?milestone= without reload-induced UI drift.

import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page, query = ''): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto(`/${query}`);
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

test.describe('F-PROJECT-001 — milestone project scope (id=119)', () => {
  test('F119.1 — server scope_type=milestone disables event-only Phase A tab', async ({ page }) => {
    await page.route('**/api/event/current', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          event_id: 'Event_e2e_fixture',
          event_generation: 2,
          active_video: 'intro',
          partition_keys: ['intro', 'resolution'],
          scope_type: 'milestone',
          active_milestone_id: 'valid_test_smoke_001',
        }),
      });
    });
    await page.route('**/api/project/list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          events: [{ event_id: 'Event_e2e_fixture', path: '/' }],
          milestones: [
            { milestone_id: 'valid_test_smoke_001', milestone_label: 'Smoke MS' },
          ],
        }),
      });
    });
    await gotoApp(page);
    await expect(page.locator('[data-testid="tab-phase-a"]')).toBeDisabled();
    await expect(page.locator('[data-testid="tab-phase-b"]')).toBeDisabled();
  });

  test('F119.2 — Project dropdown value matches active milestone from server', async ({ page }) => {
    await page.route('**/api/event/current', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          event_id: 'Event_e2e_fixture',
          event_generation: 2,
          active_video: 'intro',
          partition_keys: ['intro', 'resolution'],
          scope_type: 'milestone',
          active_milestone_id: 'valid_test_smoke_001',
        }),
      });
    });
    await page.route('**/api/project/list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          events: [{ event_id: 'Event_e2e_fixture', path: '/' }],
          milestones: [{ milestone_id: 'valid_test_smoke_001', milestone_label: 'Smoke MS' }],
        }),
      });
    });
    await gotoApp(page);
    const select = page.locator('[data-testid="project-selector"] select');
    await expect(select).toHaveValue('milestone:valid_test_smoke_001');
  });

  test('F119.3 — switching Project to milestone does not reset tab to Storyboard when BG was active', async ({
    page,
  }) => {
    await page.route('**/api/event/current', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          event_id: 'Event_e2e_fixture',
          event_generation: 1,
          active_video: 'intro',
          partition_keys: ['intro', 'resolution'],
          scope_type: 'event',
          active_milestone_id: null,
        }),
      });
    });
    await page.route('**/api/project/list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          events: [{ event_id: 'Event_e2e_fixture', path: '/' }],
          milestones: [{ milestone_id: 'ms_switch_01', milestone_label: 'MS' }],
        }),
      });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/milestones/load', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          milestone_id: 'ms_switch_01',
          scope_type: 'milestone',
          event_generation: 2,
        }),
      });
    });
    await gotoApp(page);
    await page.locator('[data-testid="tab-bg"]').click();
    await expect(page.locator('[data-testid="tab-bg"]')).toHaveClass(/is-active/);

    await page.locator('[data-testid="project-selector"] select').selectOption('milestone:ms_switch_01');

    // Allow React to process + refetch event/current for any follow-up (no reload).
    await expect(page.locator('[data-testid="project-selector"] select')).toHaveValue(
      'milestone:ms_switch_01',
      { timeout: 8_000 },
    );
    await expect(page.locator('[data-testid="tab-bg"]')).toHaveClass(/is-active/);
  });
});

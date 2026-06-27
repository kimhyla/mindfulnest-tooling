// PSL — tab switch must not show full-pane loading when session cache is warm.
import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

test.describe('Producer Session Layer — tab switch without reload spinner', () => {
  test('BG → Stitcher → BG does not show bg-loading when cache warm', async ({ page }) => {
    await gotoApp(page);

    // Wait for Beat Generator to finish first load.
    await expect(page.locator('[data-testid="tab-bg"]')).toBeVisible();
    await page.locator('[data-testid="tab-bg"]').click();
    await expect(page.locator('[data-testid="bg-loading"]')).toBeHidden({ timeout: 120000 });

    // Warm cache: beat list or empty state visible.
    const bgReady = page.locator('[data-testid="bg-beat-nav"], [data-testid="pane-bg"] .mn-empty');
    await expect(bgReady.first()).toBeVisible({ timeout: 5000 });

    await page.locator('[data-testid="tab-stitcher"]').click();
    await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-stitcher"]')).toHaveClass(/is-active/);

    await page.locator('[data-testid="tab-bg"]').click();
    await expect(page.locator('[data-testid="tab-bg"]')).toHaveClass(/is-active/);

    // Category fix: no full-pane loading spinner on remount when PSL cache exists.
    await expect(page.locator('[data-testid="bg-loading"]')).toBeHidden({ timeout: 3000 });
    await expect(bgReady.first()).toBeVisible();
  });

  test('Stitcher → BG → Stitcher does not show stitcher-loading when cache warm', async ({ page }) => {
    await gotoApp(page);

    await page.locator('[data-testid="tab-stitcher"]').click();
    await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
    await expect(page.locator('[data-testid="stitcher-loading"]')).toBeHidden({ timeout: 120000 });

    const stitcherReady = page.locator(
      '[data-testid="stitcher-multiphase-track"], [data-testid="stitcher-no-job"]',
    );
    await expect(stitcherReady.first()).toBeVisible({ timeout: 5000 });

    await page.locator('[data-testid="tab-bg"]').click();
    await expect(page.locator('[data-testid="tab-bg"]')).toHaveClass(/is-active/);

    await page.locator('[data-testid="tab-stitcher"]').click();
    await expect(page.locator('[data-testid="tab-stitcher"]')).toHaveClass(/is-active/);
    await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();

    await expect(page.locator('[data-testid="stitcher-loading"]')).toBeHidden({ timeout: 3000 });
    await expect(stitcherReady.first()).toBeVisible();
    await expect(page.locator('[data-testid="pane-stitcher-keepalive"]')).toHaveCount(1);
  });
});

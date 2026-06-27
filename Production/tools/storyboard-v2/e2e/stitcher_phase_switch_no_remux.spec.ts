// Stitcher — phase track clicks must not remux when session cache is warm.
import { test, expect, type Page } from '@playwright/test';

async function gotoStitcher(page: Page): Promise<void> {
  await page.goto('/?event=Event_2');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
  await page.locator('[data-testid="tab-stitcher"]').click();
  await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
  // Wait for stitcher job load (composer or phase cards).
  await expect(
    page.locator('[data-testid="stitcher-slot-composer"], [data-testid="stitcher-phase-card"]').first(),
  ).toBeVisible({ timeout: 120000 });
}

const PHASES = ['intro', 'phase_a', 'phase_b', 'resolution'] as const;

test.describe('Stitcher phase switch — no remux on revisit', () => {
  test('second lap does not show Building muxed preview', async ({ page }) => {
    await gotoStitcher(page);

    // Warm all four slots (first lap may build mux/ambient once).
    for (const phase of PHASES) {
      const seg = page.locator(`[data-testid="stitcher-multiphase-segment-${phase}"]`);
      if (await seg.count() === 0) continue;
      await seg.click();
      await expect(page.locator('[data-testid="stitcher-composer-video"]')).toBeVisible({
        timeout: 120000,
      });
    }

    // Hard refresh — category fix: persisted server artifacts hydrate without remux.
    await page.reload();
    await page.locator('[data-testid="tab-stitcher"]').click();
    await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
    await expect(page.locator('[data-testid="stitcher-composer-video"]')).toBeVisible({
      timeout: 120000,
    });

    // Second lap — no remux/build banners.
    for (const phase of PHASES) {
      const seg = page.locator(`[data-testid="stitcher-multiphase-segment-${phase}"]`);
      if (await seg.count() === 0) continue;
      await seg.click();
      await expect(page.locator('[data-testid="stitcher-composer-video-waiting-mux"]')).toBeHidden({
        timeout: 3000,
      });
      await expect(page.getByText('Building muxed preview…')).toBeHidden({ timeout: 3000 });
      await expect(page.getByText('Saving ambient bed…')).toBeHidden({ timeout: 3000 });
    }
  });
});

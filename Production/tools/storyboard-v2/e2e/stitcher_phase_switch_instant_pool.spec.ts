// STITCH_COMPOSER_VIDEO_POOL_V1 — instant phase switch via 4 persistent preloaded videos.
import { test, expect, type Page } from '@playwright/test';

const PHASES = ['intro', 'phase_a', 'phase_b', 'resolution'] as const;

async function gotoStitcher(page: Page): Promise<void> {
  await page.goto('/?event=Event_2');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
  await page.locator('[data-testid="tab-stitcher"]').click();
  await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
  await expect(page.locator('[data-testid="stitcher-composer-video-pool"]')).toBeVisible({
    timeout: 120000,
  });
}

async function warmAllPhases(page: Page): Promise<void> {
  for (const phase of PHASES) {
    const seg = page.locator(`[data-testid="stitcher-multiphase-segment-${phase}"]`);
    if (await seg.count() === 0) continue;
    await seg.click();
    await expect(page.locator('[data-testid="stitcher-composer-video"]')).toBeVisible({
      timeout: 120000,
    });
    await page.waitForFunction(() => {
      const v = document.querySelector('[data-testid="stitcher-composer-video"]') as HTMLVideoElement | null;
      return v && v.readyState >= 1;
    }, { timeout: 120000 });
  }
}

test.describe('Stitch composer video pool — instant phase switch', () => {
  test('revisit lap has no loading overlay and pool videos stay mounted', async ({ page }) => {
    await gotoStitcher(page);
    await warmAllPhases(page);

    const poolCount = await page.locator('[data-testid="stitcher-composer-video-pool"] video').count();
    expect(poolCount).toBeGreaterThanOrEqual(3);

    for (const phase of PHASES) {
      const seg = page.locator(`[data-testid="stitcher-multiphase-segment-${phase}"]`);
      if (await seg.count() === 0) continue;
      await seg.click();
      await expect(page.locator('[data-testid="stitcher-composer-video-loading"]')).toBeHidden({
        timeout: 2000,
      });
      await expect(page.getByText('Building muxed preview…')).toBeHidden({ timeout: 2000 });
      const ready = await page.evaluate(() => {
        const v = document.querySelector('[data-testid="stitcher-composer-video"]') as HTMLVideoElement | null;
        return v ? v.readyState >= 1 : false;
      });
      expect(ready).toBe(true);
    }
  });
});

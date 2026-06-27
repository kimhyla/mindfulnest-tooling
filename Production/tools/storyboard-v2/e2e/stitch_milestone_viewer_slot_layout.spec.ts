/**
 * STITCH_VIEWER_SLOT_LAYOUT_V1 — milestone composer must review standalone slot,
 * not bleed event track focus (intro) from keepalive StitcherTab state.
 */
import { expect, test } from '@playwright/test';

const MILESTONE_STITCH_URL =
  '/?event=Event_2&milestone=milestone1_arc1&video=intro';

test.describe('STITCH_VIEWER_SLOT_LAYOUT_V1 milestone stitcher', () => {
  test('composer header is Standalone with video after hard refresh', async ({ page }) => {
    await page.goto(`http://localhost:5112${MILESTONE_STITCH_URL}`);
    await expect(page.locator('[data-testid="app-root"]')).toBeVisible({ timeout: 60_000 });

    // Seed stale event track focus — reproduces pre-fix bleed class
    await page.evaluate(() => {
      window.localStorage.setItem('storyboard_v2_stitcher_track_slot:Event_2', 'intro');
    });

    await page.reload();
    await expect(page.locator('[data-testid="app-root"]')).toBeVisible({ timeout: 60_000 });

    const stitcherTab = page.locator('button', { hasText: 'Stitcher' });
    await stitcherTab.click();

    const composer = page.locator('[data-testid="stitcher-slot-composer"]');
    await expect(composer).toBeVisible({ timeout: 30_000 });
    await expect(composer).toHaveAttribute('data-stitch-viewer-slot-layout', 'STITCH_VIEWER_SLOT_LAYOUT_V1');

    const header = composer.locator('.mn-stitcher-slot-composer-header strong');
    await expect(header).toContainText('Standalone', { timeout: 30_000 });
    await expect(header).not.toContainText('intro — slot review');

    const video = page.locator('[data-testid="stitcher-composer-video"]');
    await expect(video).toBeVisible({ timeout: 60_000 });
    const src = await video.getAttribute('src');
    expect(src ?? '').toMatch(/Milestones\/milestone1_arc1/i);

    // Strip shows composer hint, not duplicate waveform player
    await expect(page.locator('[data-testid="stitcher-slot-hint-standalone"]')).toBeVisible();
  });
});

// Rollback E2E — Session 2 v3.1 closes spec §3.6 verification probe #12.
//
// Pattern (from spec §3.6 + §6B.9):
//   1. v59 client stamps a unique marker into a beat's dialogue text.
//   2. The save fires through pathappPatch -> /api/beat/update_text;
//      server writes state.json AND regenerates the sidecar L.json
//      (universal autosave, LD-459).
//   3. Server is flag-flipped to serve v58 via POST /api/storyboard/switch.
//   4. We hard-fetch /api/v2/storyboard/L.json — v58's sidecar hydration
//      path — and assert the marker is present.
//   5. Tear-down: switch back to v59 so subsequent test runs aren't
//      affected.
//
// This test depends on:
//   * Production/Event_1/storyboard_v59_prod.html present (v59 active)
//   * Production/Event_1/storyboard_v58_prod.html present (v58 fallback)
//   * /api/storyboard/switch endpoint accepting {filename}
//   * Sidecar regeneration happening on every /api/beat/update_text

import { test, expect, request, type Page } from '@playwright/test';
import { protectBeatText } from './helpers';

async function gotoApp(page: Page) {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

test.describe('rollback E2E (closes spec verification probe #12)', () => {
  let v58_present = false;

  test.beforeAll(async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const url = await import('node:url');
    const here = path.dirname(url.fileURLToPath(import.meta.url));
    const v58 = path.resolve(here, '../../../Event_1/storyboard_v58_prod.html');
    v58_present = fs.existsSync(v58);
  });

  test('write via v59 → flip server to v58 → assert text visible via sidecar', async ({ page, request }) => {
    test.skip(!v58_present, 'v58 fallback file not present at Production/Event_1/');
    await using _r = await protectBeatText(request, 'beat_07');

    const stamp = `[rollback-${Date.now()}]`;

    // 1. Write dialogue via v59 UI.
    await gotoApp(page);
    await expect(page.locator('[data-testid="beat-list"]')).toBeVisible({ timeout: 10000 });
    const beatIdx = 6;
    const text = page.locator(`[data-testid="beat-text-${beatIdx}"]`);
    const indicator = page.locator(`[data-testid="beat-save-${beatIdx}"]`);
    const beatId = await page
      .locator(`[data-testid="beat-card-${beatIdx}"]`)
      .getAttribute('data-beat-id');
    await text.click();
    await page.keyboard.press('End');
    await text.pressSequentially(' ' + stamp, { delay: 5 });
    await page.keyboard.press('Tab');
    await expect(indicator).toHaveAttribute('data-save-status', 'saved', { timeout: 10000 });

    // 2. State.json should now have the stamp under beats[beat_id].text.
    const ctx = request;
    const stateRes = await ctx.get(`http://localhost:5111/api/v2/event/Event_1/state`);
    const state = (await stateRes.json()) as {
      beats?: Record<string, { text?: string }>;
    };
    const beatText = state.beats?.[beatId!]?.text ?? '';
    expect(beatText, 'state.json beat text after v59 write').toContain(stamp);

    // 3. Switch server to v58.
    const switchRes = await ctx.post('http://localhost:5111/api/storyboard/switch', {
      data: { filename: 'storyboard_v58_prod.html' },
    });
    expect(switchRes.ok(), `switch to v58 failed: ${switchRes.status()}`).toBe(true);

    try {
      // 4. Fetch v58's sidecar (L.json). Note: switching the storyboard
      // changes app.storyboard_path, so the sidecar path is now
      // storyboard_v58_prod.L.json. The endpoint materializes-on-read.
      const sidecarRes = await ctx.get(
        'http://localhost:5111/api/v2/storyboard/L.json',
      );
      // Sidecar shape (verified 2026-05-02 against
      // _write_sidecar_L_json projection): a dict keyed by beat_id with
      // values shaped `{t, selected_option?, trim_start?, ..., _version?}`.
      // The legacy array `[{a:"line_NN", t:"..."}]` form is NOT what's
      // currently emitted; we handle it for forward-compat anyway.
      const sidecar = (await sidecarRes.json()) as
        | Record<string, { t?: string }>
        | Array<{ a?: string; t?: string }>
        | { L?: Array<{ a?: string; t?: string }>; beats?: Record<string, { text?: string }> };

      let foundText = '';
      const anchor = beatId?.replace('beat_', 'line_');
      if (Array.isArray(sidecar)) {
        const entry = sidecar.find((e) => e.a === anchor);
        foundText = entry?.t ?? '';
      } else if ((sidecar as { L?: unknown }).L && Array.isArray((sidecar as { L?: unknown }).L)) {
        const arr = (sidecar as { L: Array<{ a?: string; t?: string }> }).L;
        const entry = arr.find((e) => e.a === anchor);
        foundText = entry?.t ?? '';
      } else if ((sidecar as { beats?: Record<string, { text?: string }> }).beats) {
        foundText =
          (sidecar as { beats: Record<string, { text?: string }> }).beats[beatId!]?.text ?? '';
      } else {
        // Current canonical form: flat dict keyed by beat_id with `t` field.
        const flat = sidecar as Record<string, { t?: string }>;
        foundText = flat[beatId!]?.t ?? '';
      }

      // Per LD-459 UNIVERSAL_AUTOSAVE_V1: the sidecar must contain the
      // stamp v59 just wrote. If not, autosave is broken or sidecar
      // regeneration didn't fire on /api/beat/update_text.
      expect(
        foundText,
        `v58 sidecar text after rollback (anchor=${beatId?.replace('beat_', 'line_')})`,
      ).toContain(stamp);
    } finally {
      // 5. Tear-down: switch back to v59 so other tests run against the
      // v59 frontend and the server doesn't stay on v58.
      await ctx.post('http://localhost:5111/api/storyboard/switch', {
        data: { filename: 'storyboard_v59_prod.html' },
      });
    }
  });
});

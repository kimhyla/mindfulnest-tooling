// Retroactive Coverage Sprint — S4 Magic Compositor
//
// Spec: STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md §3 S4
// LDs: LD-468 (magic on still), LD-469 (magic on video), LD-460
//      ASYNC_JOB_GENERATION_PIN_V1 (drain protocol), LD-461 SCOPE_BODY_HELPER_V1
//
// SUT note: spec §3 S4 says "Magic compositor invocation from BgTab" but the
// magic UI lives in StoryboardTab.tsx::BeatMagicButtons (lines 559-635), not
// BgTab. Server endpoints (production_server.py):
//   GET  /api/magic/status              — poll job
//   GET  /api/magic/resolve_bg          — scene_key → bg_path
//   POST /api/magic/submit_path         — kick off render (with_pin_and_drain)
//   POST /api/storyboard/magic_still    — finalize still result (with_pin_and_drain)
//   POST /api/storyboard/magic_video    — finalize video result (with_pin_and_drain)
//
// Tests cover (a) StoryboardTab button rendering + click → window.open
// contract, and (b) server endpoint contracts via direct request.

import { test, expect, type Page } from '@playwright/test';
import { openStoryboardPane } from './helpers';

const SERVER = 'http://localhost:5200';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

function stateWithBeat(beat: Record<string, unknown>, beatId = 'beat_s4_01') {
  return {
    _module_version: 1,
    videos: {
      intro: { video_role: 'intro', beats: { [beatId]: beat } },
      resolution: { video_role: 'resolution', beats: {} },
    },
  };
}

test.describe('S4 — magic compositor', () => {
  test('S4.1 — BeatMagicButtons: when image_path present and no magic_still_path → "Add magic on still" button is visible + enabled', async ({ page }) => {
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stateWithBeat({
          speaker: 'Tessa',
          text: 'Magic candidate.',
          image_path: 'cropped/beat_s4_01.png',
          // NOTE: no magic_still_path → button should be ENABLED.
        })),
      });
    });
    await gotoApp(page);
    await openStoryboardPane(page);
    const stillBtn = page.locator('[data-testid="beat-magic-still-0"]');
    await expect(stillBtn).toBeVisible();
    await expect(stillBtn).not.toBeDisabled();
    await expect(stillBtn).toContainText(/add magic/i);
  });

  test('S4.2 — BeatMagicButtons: when magic_still_path already exists → button shows Redo and stays enabled', async ({ page }) => {
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stateWithBeat({
          speaker: 'Tessa',
          text: 'Magic done.',
          image_path: 'cropped/beat_s4_01.png',
          magic_still_path: 'magic/beat_s4_01_magic.png',
        })),
      });
    });
    await gotoApp(page);
    await openStoryboardPane(page);
    const stillBtn = page.locator('[data-testid="beat-magic-still-0"]');
    await expect(stillBtn).toBeVisible();
    await expect(stillBtn).not.toBeDisabled();
    await expect(stillBtn).toContainText(/redo magic on still/i);
  });

  test('S4.3 — clicking magic-still button opens window.open() with required params (mode, beat_id, source_image_path, return_endpoint, scope_event_id)', async ({ page, context }) => {
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stateWithBeat({
          speaker: 'Tessa',
          text: 'Open magic editor.',
          image_path: 'cropped/beat_s4_01.png',
        })),
      });
    });
    // Capture window.open calls — overload page.evaluate to spy on it before
    // the button click. context.on('page') misses popups suppressed by browser.
    await gotoApp(page);
    await page.evaluate(() => {
      const w = window as unknown as { __mn_open_calls?: string[]; open: typeof window.open };
      w.__mn_open_calls = [];
      const orig = w.open;
      w.open = ((url?: string | URL, target?: string, features?: string) => {
        (w.__mn_open_calls!).push(String(url ?? ''));
        return orig.call(window, url ?? '', target, features);
      }) as typeof window.open;
    });
    await openStoryboardPane(page);
    await page.locator('[data-testid="beat-magic-still-0"]').click();
    const openedUrls = await page.evaluate(() =>
      (window as unknown as { __mn_open_calls?: string[] }).__mn_open_calls,
    );
    expect((openedUrls ?? []).length).toBeGreaterThanOrEqual(1);
    const u = new URL((openedUrls ?? [''])[0]);
    expect(u.pathname).toBe('/magic');
    expect(u.searchParams.get('mode')).toBe('magic_still');
    expect(u.searchParams.get('beat_id')).toBeTruthy();
    expect(u.searchParams.get('source_image_path')).toContain('cropped/beat_s4_01.png');
    expect(u.searchParams.get('return_endpoint')).toBe('/api/storyboard/magic_still');
    expect(u.searchParams.get('scope_event_id')).toBeTruthy();
  });

  test('S4.4 — GET /api/magic/status without job_id returns 400 + error message', async ({ request }) => {
    const res = await request.get(`${SERVER}/api/magic/status`);
    expect(res.status()).toBe(400);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body['ok']).toBe(false);
    expect(String(body['error'] ?? '')).toMatch(/job_id/i);
  });

  test('S4.5 — GET /api/magic/status with unknown job_id returns 404', async ({ request }) => {
    const res = await request.get(`${SERVER}/api/magic/status?job_id=does_not_exist_${Date.now()}`);
    expect(res.status()).toBe(404);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body['ok']).toBe(false);
    expect(String(body['error'] ?? '')).toMatch(/not found/i);
  });

  test('S4.6 — GET /api/magic/resolve_bg without scene_key returns 400', async ({ request }) => {
    const res = await request.get(`${SERVER}/api/magic/resolve_bg`);
    expect(res.status()).toBe(400);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body['ok']).toBe(false);
    expect(String(body['error'] ?? '')).toMatch(/scene_key/i);
  });

  test('S4.7 — POST /api/magic/submit_path with no body returns 4xx (scope-guard or validation)', async ({ request }) => {
    const res = await request.post(`${SERVER}/api/magic/submit_path`, {
      data: {},
      headers: { 'Content-Type': 'application/json' },
    });
    // Scope-guard returns 400/409 depending on path. The submit-path handler
    // demands selected_path / candidate_paths — without those it must NOT
    // silently accept (no 200) AND must NOT 500. Accept 400/409/422.
    expect([400, 409, 422]).toContain(res.status());
  });

  test('S4.8 — magic_video button gating: only renders when there is a video source (lipsync.file or selected animation option)', async ({ page }) => {
    // Beat with NEITHER lipsync.file NOR phase_1.options[selected_option].file.
    await page.route('**/api/v2/event/*/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stateWithBeat({
          speaker: 'Tessa',
          text: 'No video source.',
          image_path: 'cropped/beat_s4_01.png',
          // image_path makes magic-still button render
        })),
      });
    });
    await gotoApp(page);
    await openStoryboardPane(page);
    // magic-still renders (image_path present), but magic-video should NOT render.
    await expect(page.locator('[data-testid="beat-magic-still-0"]')).toBeVisible();
    await expect(page.locator('[data-testid="beat-magic-video-0"]')).toHaveCount(0);
  });
});

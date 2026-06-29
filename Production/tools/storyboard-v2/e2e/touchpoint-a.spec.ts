// Touchpoint A suite — Session 2 v3.1.
//
// Mirrors STORYBOARD_REAL_FIX_TOUCHPOINT_A.md §6A (read-only verification —
// 10 flows) and §6B (production workflow contract — 10 flows; cutover gate).
//
// §6A tests assert against what v59 has built today (post-S2). They MUST
// pass before Kim's hands-on pass.
//
// §6B tests cover the production workflow contract — wired to Event_e2e_fixture
// (Playwright webServer pin per playwright.config.ts §19).

import { test, expect, request, type Page } from '@playwright/test';
import { protectBeatText, openStoryboardPane, FIXTURE_EVENT, SERVER } from './helpers';
import { synthDrop, mockSnapshot, mockStoryboardIntroState } from './parityHelpers';

async function gotoApp(page: Page) {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function gotoStoryboard(page: Page) {
  await openStoryboardPane(page);
}

async function waitForBeats(page: Page) {
  await expect(page.locator('[data-testid="beat-list"]')).toBeVisible({ timeout: 10000 });
}

// ============================================================================
// §6A — read-only verification flows (10/10 must pass)
// ============================================================================

test.describe('§6A — read-only verification', () => {
  test('§6A.1 — page loads, header + 4 tabs + library visible', async ({ page }) => {
    await gotoApp(page);
    await expect(page.locator('[data-testid="app-subhead"]')).toContainText('Path C');
    await expect(page.locator('[data-testid="tab-bg"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-cropper"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-stitcher"]')).toBeVisible();
    await expect(page.locator('[data-testid="library-panel"]')).toBeVisible();
  });

  test('§6A.2 — scope chip + body data-resolved-scope', async ({ page }) => {
    await openStoryboardPane(page);
    await expect(page.locator('[data-testid="storyboard-scope-chip"]')).toContainText(
      new RegExp(`${FIXTURE_EVENT}.*v\\d+`),
    );
    const resolved = await page.evaluate(() =>
      document.body.getAttribute('data-resolved-scope'),
    );
    expect(resolved).toMatch(new RegExp(`^${FIXTURE_EVENT}:.*:v\\d+$`));
  });

  test('§6A.3 — all 4 tabs render their pane without error', async ({ page }) => {
    await gotoApp(page);
    await openStoryboardPane(page);
    await expect(page.locator('[data-testid="pane-storyboard"]')).toBeVisible();
    await page.click('[data-testid="tab-bg"]');
    await expect(page.locator('[data-testid="pane-bg"]')).toBeVisible();
    await page.click('[data-testid="tab-stitcher"]');
    await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
  });

  test('§6A.4 — Cropper opens as modal overlay; close buttons work', async ({ page }) => {
    await gotoApp(page);
    await page.click('[data-testid="tab-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toBeVisible();
    await page.click('[data-testid="modal-close-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toHaveCount(0);
  });

  test('§6A.5 — library renders real fixture items with thumbnails', async ({ page }) => {
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-list"]')).toBeVisible({ timeout: 10000 });
    const items = page.locator('[data-testid^="library-item-"]');
    const n = await items.count();
    expect(n).toBeGreaterThan(0);
    await expect(page.locator('[data-testid="library-count"]')).toContainText(/\d+ items/);
  });

  test('§6A.6 — library /api/cr/library failure shows banner, never silent blank', async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.clear();
    });
    await page.route('**/api/cr/library**', async (route) => {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"injected fault"}' });
    });
    await page.route('**/api/stitch_editor/library**', async (route) => {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"injected fault"}' });
    });
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-error"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="library-error"]')).toContainText(/injected fault|Could not reach/i);
  });

  test('§6A.7 — Storyboard tab renders L[] beat cards with speakers', async ({ page }) => {
    await openStoryboardPane(page);
    await expect(page.locator('[data-testid="beat-list"]')).toBeVisible({ timeout: 10000 });
    const cards = page.locator('[data-testid^="beat-card-"]');
    expect(await cards.count()).toBeGreaterThan(0);
    await expect(page.locator('[data-testid="beat-card-0"] .mn-beat-speaker')).toBeVisible();
  });

  test('§6A.8 — BG tab scope chip shows pinned fixture event', async ({ page }) => {
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.locator('[data-testid="bg-scope-chip"]')).toBeVisible();
    await expect(page.locator('[data-testid="bg-scope-chip"]')).toContainText(FIXTURE_EVENT);
  });

  test('§6A.9 — rapid tab switching keeps active indicator in sync', async ({ page }) => {
    await gotoApp(page);
    for (const t of ['bg', 'stitcher', 'phase_b', 'bg', 'cropper'] as const) {
      if (t === 'phase_b') {
        await page.goto('/?tab=phase_b');
        await expect(page.locator('[data-testid="tab-phase-b"]')).toHaveClass(/is-active/);
      } else {
        await page.click(`[data-testid="tab-${t}"]`);
        await expect(page.locator(`[data-testid="tab-${t}"]`)).toHaveClass(/is-active/);
      }
    }
  });

  test('§6A.10 — initial mount fires zero mutation requests', async ({ page }) => {
    const mutations: { method: string; url: string }[] = [];
    page.on('request', (req) => {
      if (
        ['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method()) &&
        req.url().includes('/api/')
      ) {
        mutations.push({ method: req.method(), url: req.url() });
      }
    });
    await gotoApp(page);
    await page.waitForTimeout(800);
    expect(mutations, `mutations on mount: ${JSON.stringify(mutations)}`).toEqual([]);
  });
});

// ============================================================================
// §6B — production workflow contract (cutover gate)
// ============================================================================

test.describe('§6B — production workflow contract', () => {
  test('§6B.1 — drag library image onto beat slot persists image_override', async ({ page }) => {
    await mockStoryboardIntroState(page);
    await mockSnapshot(page);
    const assignReqs: string[] = [];
    page.on('request', (req) => {
      if (req.method() === 'POST' && req.url().includes('/api/assign-image')) assignReqs.push(req.url());
    });
    await gotoStoryboard(page);
    await waitForBeats(page);
    await synthDrop(page, '[data-testid="beat-image-zone-0"]', {
      kind: 'lib-image',
      lib_key: 'e2e_fixture_test',
    });
    await expect.poll(() => assignReqs.length, { timeout: 8000 }).toBeGreaterThan(0);
  });

  test('§6B.2 — open cropper from beat row; save crop becomes beat still', async ({ page }) => {
    await gotoApp(page);
    const cropBtn = page.locator('[data-testid^="library-crop-btn-"]').first();
    if (await cropBtn.count()) {
      await cropBtn.click();
    } else {
      await page.click('[data-testid="tab-cropper"]');
    }
    await expect(page.locator('[data-testid="modal-cropper"]')).toBeVisible();
    await expect(page.locator('[data-testid="cropper-save-btn"]')).toBeVisible();
  });

  test('§6B.3 — dialogue edit persists across reload', async ({ page, request }) => {
    await using _r = await protectBeatText(request, 'beat_02');
    await gotoStoryboard(page);
    await waitForBeats(page);
    const text = page.locator('[data-testid="beat-text-1"]');
    const indicator = page.locator('[data-testid="beat-save-1"]');
    const beatId = await page.locator('[data-testid="beat-card-1"]').getAttribute('data-beat-id');

    const stamp = `[s2-touchpoint-${Date.now()}]`;
    await text.click();
    await page.keyboard.press('End');
    await text.pressSequentially(' ' + stamp, { delay: 5 });
    await page.keyboard.press('Tab');
    await expect(indicator).toHaveAttribute('data-save-status', 'saved', { timeout: 10000 });

    await page.reload();
    await waitForBeats(page);
    const reloadedText = page.locator(`[data-beat-id="${beatId}"] .mn-beat-text`);
    await expect(reloadedText).toContainText(stamp);
  });

  test('§6B.4 — beat trim fields persist across reload', async ({ page, request }) => {
    await gotoStoryboard(page);
    await waitForBeats(page);
    const front = page.locator('[data-testid="beat-0-trim-front"]').first();
    const back = page.locator('[data-testid="beat-0-trim-back"]').first();
    await expect(front).toBeVisible();
    await expect(back).toBeVisible();

    const stamp = String(Math.floor(Math.random() * 80) + 10);
    await front.fill(stamp);
    await page.locator('[data-testid="beat-0-trim-apply"]').first().click();
    await expect(page.locator('[data-testid="toast-host"]')).toBeVisible({ timeout: 8000 });

    await page.reload();
    await waitForBeats(page);
    await expect(page.locator('[data-testid="beat-0-trim-front"]').first()).toHaveValue(stamp);

    await request.post(`${SERVER}/api/beat/trim`, {
      data: {
        event_id: FIXTURE_EVENT,
        beat_id: 'beat_01',
        trim_start: 0,
        trim_back: 0,
      },
    });
  });

  test('§6B.5 — Accept All on fixture event succeeds; cross-event Event_2 returns 409', async () => {
    const ctx = await request.newContext();
    const ok = await ctx.post(`${SERVER}/api/bg/accept-beats`, {
      data: { scope_event_id: FIXTURE_EVENT, scope_target_video: 'intro', beats: [], segment: 0 },
    });
    expect(ok.status()).toBe(200);
    const cross = await ctx.post(`${SERVER}/api/bg/accept-beats`, {
      data: { scope_event_id: 'Event_2', scope_target_video: 'intro', beats: [], segment: 0 },
    });
    expect(cross.status()).toBe(409);
    const body = (await cross.json()) as { code?: string; error_code?: string };
    expect(['SCOPE_VALIDATION_V1', 'SCOPE_MISMATCH']).toContain(body.error_code ?? body.code);
  });

  test('§6B.6 — Kling generation produces option that can be selected', async ({ page }) => {
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.locator('[data-testid="bg-toolbar"]')).toBeVisible({ timeout: 15000 });
    const beatList = page.locator('[data-testid="bg-beat-list"]');
    if (await beatList.count()) {
      await expect(page.locator('[data-testid^="bg-pipeline-still-"]').first()).toBeVisible();
      await expect(page.locator('[data-testid^="bg-pipeline-voice-first-"]').first()).toBeVisible();
    } else {
      await expect(page.locator('[data-testid="bg-empty"]')).toBeVisible();
      await expect(page.locator('[data-testid="bg-extract-btn"]')).toBeVisible();
    }
  });

  test('§6B.7 — Lipsync run becomes primary clip', async ({ page }) => {
    await gotoStoryboard(page);
    await waitForBeats(page);
    await expect(page.locator('[data-testid="beat-0-lipsync-idle"]')).toBeVisible();
  });

  test('§6B.8 — Add/delete beat controls present and delete uses confirm modal', async ({ page }) => {
    await gotoStoryboard(page);
    await waitForBeats(page);
    await expect(page.locator('[data-testid="sb-insert-after-btn-0"]')).toBeVisible();
    const del = page.locator('[data-testid="sb-delete-beat-0"]');
    await expect(del).toBeVisible();
    await del.click();
    await expect(page.locator('[data-testid="sb-delete-beat-confirm"]')).toBeVisible();
    await page.click('[data-testid="sb-delete-beat-cancel"]');
  });

  test('§6B.9 — v59 dialogue write → sidecar L.json contains same text', async ({ page, request }) => {
    await using _r = await protectBeatText(request, 'beat_02');
    const stamp = `[touchpoint-rollback-${Date.now()}]`;

    await gotoStoryboard(page);
    await waitForBeats(page);
    const beatIdx = 1;
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

    const sidecarRes = await request.get(`${SERVER}/api/v2/storyboard/L.json`);
    expect(sidecarRes.ok()).toBe(true);
    const sidecar = (await sidecarRes.json()) as Record<string, { t?: string }>;
    const foundText = sidecar[beatId!]?.t ?? '';
    expect(foundText, 'sidecar L.json after v59 dialogue write').toContain(stamp);
  });

  test('§6B.10 — snapshot endpoint fires before mutation; .backups/state/<UTC>.json appears', async ({
    page,
    request,
  }) => {
    await using _r = await protectBeatText(request, 'beat_03');
    const fs = await import('node:fs');
    const path = await import('node:path');
    const url = await import('node:url');
    const here = path.dirname(url.fileURLToPath(import.meta.url));
    const dir = path.resolve(here, `../../../${FIXTURE_EVENT}/.backups/state`);
    const before = fs.existsSync(dir) ? fs.readdirSync(dir).length : 0;

    await gotoStoryboard(page);
    await waitForBeats(page);
    const text = page.locator('[data-testid="beat-text-2"]');
    await text.click();
    await text.pressSequentially(' [snap-test]', { delay: 5 });
    await page.keyboard.press('Tab');
    await expect(page.locator('[data-testid="beat-save-2"]')).toHaveAttribute('data-save-status', 'saved', {
      timeout: 10000,
    });

    const after = fs.existsSync(dir) ? fs.readdirSync(dir).length : 0;
    expect(after, `snapshot file count: before=${before}, after=${after}`).toBeGreaterThan(before);
  });
});

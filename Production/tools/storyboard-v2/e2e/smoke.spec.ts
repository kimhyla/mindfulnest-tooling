import { test, expect, type Request } from '@playwright/test';

// Session 1 smoke — verifies the v59 single-file bundle renders and the
// architectural commitments hold:
//   - core tabs visible (TabBar production order per TAB_STRUCTURE_PRODUCTION_ORDER_V1)
//   - ScopeBoundary resolves the active scope (data-resolved-scope set on body)
//   - Library panel attempts to load real data
//   - ZERO state-mutation requests fire (Session 1 is read-only)

test.describe('Session 1 smoke — v59 read-only preview', () => {
  test('app loads, core tabs visible, scope resolved, NO mutations', async ({ page }) => {
    // Capture all outgoing requests — used to assert ZERO mutations.
    const seenRequests: Array<{ method: string; url: string }> = [];
    page.on('request', (req: Request) => {
      seenRequests.push({ method: req.method(), url: req.url() });
    });

    await page.goto('/');

    // App root rendered.
    const appRoot = page.locator('[data-testid="app-root"]');
    await expect(appRoot).toBeVisible();

    // CRITICAL — initial mount must not fire state mutations before user action.
    const mutationsBeforeInteraction = seenRequests.filter(
      (r) =>
        ['POST', 'PATCH', 'PUT', 'DELETE'].includes(r.method) &&
        r.url.includes('/api/') &&
        !r.url.includes('/api/state/snapshot'),
    );
    expect(
      mutationsBeforeInteraction,
      `Initial mount must not mutate server state. Found:\n${mutationsBeforeInteraction
        .map((r) => `  ${r.method} ${r.url}`)
        .join('\n')}`,
    ).toEqual([]);

    // Header subhead.
    await expect(page.locator('[data-testid="app-subhead"]')).toContainText(
      'Path C rewrite',
    );

    // Core tabs present (7 total per TabBar.tsx; Phase A/B + Map added after S1 draft).
    await expect(page.locator('[data-testid="tab-bg"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-cropper"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-storyboard"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-phase-b"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-phase-a"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-stitcher"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-map"]')).toBeVisible();

    // ScopeBoundary resolved — body has the data attribute.
    // Format: `${event_id}:${beat_id ?? 'global'}:v${version}` per scope.ts scopeKey().
    // Regex is fixture-agnostic — matches Event_e2e_fixture, Event_1, etc.
    // [CONFIRMED against src/state/scope.ts scopeKey() return value]
    await expect.poll(async () =>
      page.evaluate(() => document.body.getAttribute('data-resolved-scope')),
    ).toMatch(/^\w[\w_-]*:[\w_-]+:v\d+$/);

    // Library panel mounted.
    await expect(page.locator('[data-testid="library-panel"]')).toBeVisible();

    // Library MUST render at least one item (regression guard for the
    // 2026-05-02 "0 items / Library is empty" bug — server returned
    // {"images": [...]} but LibraryPanel was looking for `items`/`sources`).
    // If the server response shape ever drifts again, this assertion fires.
    const libraryList = page.locator('[data-testid="library-list"]');
    await expect(
      libraryList,
      'Library list must render. If empty: check that /api/cr/library returns ' +
        '{"images": [...]} and LibraryPanel.flattenLibraryResponse handles it.',
    ).toBeVisible();
    const itemCount = await page
      .locator('[data-testid^="library-item-"]')
      .count();
    expect(
      itemCount,
      'Library must render >=1 item. In CI the global-setup seeds ' +
        'Production/beat_generator_stills/sources/e2e_fixture_test.png which ' +
        '/api/cr/library returns under the "source" tier. If this fails, check ' +
        'global-setup.ts seeding and _handle_cr_library BG_STILLS_DIR/sources/ scan.',
    ).toBeGreaterThanOrEqual(1);
    // Counter chip must reflect the rendered count (not "0 items").
    await expect(page.locator('[data-testid="library-count"]')).toContainText(
      /\d+ items/,
    );

    // Click read-only panes (Beat Gen + Storyboard). Stitcher tab auto-saves jobs
    // on mount (pathappPatch) — excluded from Session 1 zero-mutation contract.
    await page.click('[data-testid="tab-bg"]');
    await expect(page.locator('[data-testid="pane-bg"]')).toBeVisible();

    await page.click('[data-testid="tab-storyboard"]');
    await expect(page.locator('[data-testid="pane-storyboard"]')).toBeVisible();

    // Cropper tab opens the modal overlay.
    // [CONFIRMED against src/components/ui/Modal.tsx L49+63] Modal renders
    // data-testid="modal-{id}" on backdrop and data-testid="modal-close-{id}"
    // on the × button. CropperModal passes id="cropper" → modal-cropper /
    // modal-close-cropper. The original smoke draft used cropper-modal /
    // cropper-close which never existed in any .tsx source file.
    await page.click('[data-testid="tab-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toBeVisible();
    await page.click('[data-testid="modal-close-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toHaveCount(0);
  });
});

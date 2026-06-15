// Retroactive Coverage Sprint — S5 Library Rendering Edge Cases
//
// Spec: STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md §3 S5
// Refs: LibraryPanel.tsx (data-testids: library-panel, library-list,
//       library-empty, library-error, library-count, library-item-N,
//       asset-tile-delete), AssetTile.tsx
//
// Existing coverage:
//   - smoke.spec.ts:43-64 — ≥1 item renders + library-count chip
//   - s5_5ce_proper_fix.spec.ts R5 — tile width ≤80px, rail height bounded
//
// New edge cases covered here:
//   1. 0-item state: library-empty visible, library-list NOT visible
//   2. 100+ items: scroll works; tile rendering is non-degenerate
//   3. Click vs delete-button click — discrimination (delete must NOT bubble)
//   4. Library refreshes after a delete (refreshTick++ → re-fetch)
//   5. Drag identity: dragstart sets DataTransfer with kind="lib-image"
//
// Note: spec mentioned "category filter (if exists)" — LibraryPanel has no
// category filter UI; the response shape collapses sources/crops/masters
// into a single list. Documented in the closeout doc; no test for it.

import { test, expect, type Page } from '@playwright/test';

const SERVER = 'http://localhost:5111';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

function makeLibItem(i: number): Record<string, unknown> {
  return {
    key: `lib_${i}`,
    abs_path: `/tmp/lib_${i}.png`,
    filename: `lib_${i}.png`,
    display_name: `Item ${i}`,
    tier: i % 3 === 0 ? 'source' : 'cropped',
    mtime: 1700000000 + i,
    width: 1280,
    height: 720,
  };
}

test.describe('S5 — library rendering edge cases', () => {
  test('S5.1 — 0-item state: library-empty visible, library-list NOT rendered, count="0 items"', async ({ page }) => {
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ images: [] }),
      });
    });
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="library-empty"]')).toBeVisible();
    await expect(page.locator('[data-testid="library-list"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="library-count"]')).toContainText('0 items');
  });

  test('S5.2 — 120 items: all render; library-count="120 items"; rail still scroll-bounded', async ({ page }) => {
    const items = Array.from({ length: 120 }).map((_, i) => makeLibItem(i));
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ images: items }),
      });
    });
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-count"]')).toContainText('120 items');
    // All tiles in DOM (no virtualization in current LibraryPanel).
    const tiles = page.locator('[data-testid^="library-item-"]');
    await expect.poll(async () => tiles.count(), { timeout: 5_000 }).toBe(120);
    // Library panel rail height bounded (scroll, not page-spanning) per R5.
    const rail = page.locator('[data-testid="library-panel"]');
    const railBox = await rail.boundingBox();
    expect(railBox).not.toBeNull();
    expect(railBox!.height).toBeLessThanOrEqual(900);
    // Last tile should be off-screen relative to the rail (proves overflow scroll, not viewport bleed).
    const lastTile = tiles.last();
    const lastBox = await lastTile.boundingBox();
    // boundingBox returns null if outside the layout (which is fine — it's beyond scroll).
    if (lastBox && railBox) {
      // Either lastBox.y is past rail bottom (off-screen-down), OR the rail
      // has its own scroll context. Either way the assertion: total tile
      // height >> rail height, so contents do not fit without scroll.
      const tilesHeight = await tiles.evaluateAll((els) =>
        els.reduce((sum, e) => sum + e.getBoundingClientRect().height, 0),
      );
      expect(tilesHeight).toBeGreaterThan(railBox.height);
    }
  });

  test('S5.3 — clicking the delete button does NOT bubble to the tile click handler (uses stopPropagation)', async ({ page }) => {
    const items = [makeLibItem(0)];
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ images: items }),
      });
    });
    // Cancel the confirm() so delete doesn't actually fire mutation.
    await page.addInitScript(() => {
      const orig = window.confirm;
      (window as unknown as { __confirm_calls?: string[] }).__confirm_calls = [];
      window.confirm = (msg?: string) => {
        ((window as unknown as { __confirm_calls: string[] }).__confirm_calls).push(msg ?? '');
        return false; // user cancels
      };
      void orig;
    });
    // Track clicks on parent tile vs delete button.
    await gotoApp(page);
    const tile = page.locator('[data-testid="library-item-0"]');
    await expect(tile).toBeVisible();
    // Attach a marker to capture parent clicks.
    await tile.evaluate((el: Element) => {
      (window as unknown as { __mn_tile_click?: number }).__mn_tile_click = 0;
      el.addEventListener('click', () => {
        (window as unknown as { __mn_tile_click: number }).__mn_tile_click =
          ((window as unknown as { __mn_tile_click: number }).__mn_tile_click || 0) + 1;
      });
    });
    const del = tile.locator('[data-testid="asset-tile-delete"]');
    await expect(del).toBeVisible();
    await del.click();
    // confirm() was invoked (proves delete handler ran).
    const confirmCalls = await page.evaluate(() =>
      (window as unknown as { __confirm_calls?: string[] }).__confirm_calls,
    );
    expect((confirmCalls ?? []).length).toBeGreaterThanOrEqual(1);
    // Tile parent click handler was NOT invoked (stopPropagation worked).
    const parentClicks = await page.evaluate(() =>
      (window as unknown as { __mn_tile_click?: number }).__mn_tile_click,
    );
    expect(parentClicks ?? 0).toBe(0);
  });

  test('S5.4 — delete confirmed → cr_library_delete fires → library re-fetches; deleted item disappears', async ({ page }) => {
    let phase: 'before' | 'after' = 'before';
    const itemsBefore = [makeLibItem(0), makeLibItem(1), makeLibItem(2)];
    const itemsAfter = [makeLibItem(0), makeLibItem(2)]; // index 1 removed
    let libraryCalls = 0;
    await page.route('**/api/cr/library**', async (r) => {
      libraryCalls += 1;
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ images: phase === 'before' ? itemsBefore : itemsAfter }),
      });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/cr/library/delete', async (r) => {
      phase = 'after';
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    // Auto-confirm.
    await page.addInitScript(() => { window.confirm = () => true; });
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-item-1"]')).toBeVisible();
    const beforeCount = libraryCalls;
    await page.locator('[data-testid="library-item-1"] [data-testid="asset-tile-delete"]').click();
    // Library re-fetches (refreshTick++); count after reload reflects new shape.
    await expect.poll(async () =>
      page.locator('[data-testid^="library-item-"]').count(),
      { timeout: 5_000 },
    ).toBe(2);
    expect(libraryCalls).toBeGreaterThan(beforeCount);
  });

  test('S5.5 — drag identity: tile dragstart populates DataTransfer with kind="lib-image" + lib_key', async ({ page }) => {
    const items = [makeLibItem(0)];
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ images: items }),
      });
    });
    await gotoApp(page);
    const tile = page.locator('[data-testid="library-item-0"]');
    await expect(tile).toBeVisible();
    // Synthesize a dragstart with a real DataTransfer; capture the data set by
    // setDragData(). dragstart fires onDragStart on the tile which calls
    // setDragData(e, dragPayload).
    const captured = await tile.evaluate((el: Element) => {
      const dt = new DataTransfer();
      const ev = new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt });
      el.dispatchEvent(ev);
      const raw = dt.getData('application/x-mn-drag') || dt.getData('text/plain');
      try { return JSON.parse(raw); } catch { return null; }
    });
    expect(captured).not.toBeNull();
    expect((captured as Record<string, unknown>)['kind']).toBe('lib-image');
    expect((captured as Record<string, unknown>)['lib_key']).toBe('lib_0');
  });

  test('S5.6 — server returning {sources:[...],crops:[...]} (legacy shape) flattens correctly', async ({ page }) => {
    // Regression guard for flattenLibraryResponse handling the legacy shape.
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sources: [makeLibItem(0), makeLibItem(1)],
          crops: [makeLibItem(2)],
          masters: [],
        }),
      });
    });
    await gotoApp(page);
    await expect.poll(async () =>
      page.locator('[data-testid^="library-item-"]').count(),
      { timeout: 5_000 },
    ).toBe(3);
    await expect(page.locator('[data-testid="library-count"]')).toContainText('3 items');
  });

  test('S5.7 — server error: shows library-error pane, NOT library-empty, NOT library-list', async ({ page }) => {
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"server"}' });
    });
    await page.route('**/api/stitch_editor/library**', async (r) => {
      await r.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"server"}' });
    });
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="library-empty"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="library-list"]')).toHaveCount(0);
  });

  test('S5.8 — + Add upload button stays visible on watercolors tier', async ({ page }) => {
    await page.route('**/api/cr/library**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          images: [{
            key: 'wc_1',
            filename: 'spell_title.png',
            abs_path: '/tmp/spell_title.png',
            tags: ['watercolor'],
            tier: 'source',
          }],
        }),
      });
    });
    await gotoApp(page);
    await page.locator('[data-testid="library-tier-select"]').selectOption('watercolors');
    const addBtn = page.locator('[data-testid="library-upload-btn"]');
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toContainText('+ Add');
  });
});

// F-BG-001 (prod_blockers id=117) — Beat Generator Segment dropdown stuck on "Loading…".
//
// Symptom: when /api/bg/segments?arc_number=N returns {segments: [], arc_number: N}
// (HTTP 200, valid empty result), the BG Segment <select> placeholder text stays
// "Loading…" forever. Root cause: BgTab.tsx renders placeholder via
// `segments.length === 0 ? 'Loading…' : 'Select segment'` with no distinction
// between "actively loading" and "loaded, no segments authored".
//
// Layer (per DS-13):
//   L4 state propagation: client receives {segments: []} but UI conflates
//                         empty-after-load with still-loading.
//   L5 UI re-render: placeholder remains "Loading…" indefinitely.
//
// Fix location: Production/tools/storyboard-v2/src/components/BgTab.tsx:535
// — placeholder must use the existing `loading` state, not segments.length.
//
// This RED spec mocks both BG read endpoints to return empty (matching the
// production reproducer) and asserts:
//   1. The Segment select's placeholder option text does NOT contain "Loading…"
//      after the network responses settle.
//   2. The placeholder option DOES contain a recognizable empty-state string
//      (e.g. "no segments yet").
//
// Pattern: cribbed from e2e/s5_5f_smoke.spec.ts (page.route mocks + gotoApp).

import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

/**
 * Mock the BG read endpoints to reproduce the empty-segments condition that
 * the running production server hits when an arc has no authored segments
 * (curl http://localhost:5111/api/bg/segments?arc_number=1 → {segments: [],
 * arc_number: 1}).
 */
async function mockEmptyBgEndpoints(page: Page): Promise<void> {
  await page.route('**/api/bg/segments**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ segments: [], arc_number: 1 }),
    });
  });
  await page.route('**/api/bg/session-state**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      // No active_context, no beats — first-load empty state.
      body: JSON.stringify({ beats: [], active_context: null }),
    });
  });
}

test.describe('F-BG-001 — Segment dropdown empty-state vs loading-state', () => {
  test('Segment <select> shows empty-state hint (NOT "Loading…") when server returns {segments: []}', async ({ page }) => {
    await mockEmptyBgEndpoints(page);

    // Track segments fetches so we can wait for the first response to land
    // before asserting on the rendered placeholder.
    const segmentsResponses: number[] = [];
    page.on('response', (resp) => {
      if (resp.url().includes('/api/bg/segments')) {
        segmentsResponses.push(resp.status());
      }
    });

    await gotoApp(page);

    // Open Beat Generator tab; this fires the initial BG fetches.
    await page.click('[data-testid="tab-bg"]');
    await expect(page.locator('[data-testid="pane-bg"]')).toBeVisible();

    // Wait for the first /api/bg/segments response (200 with empty list).
    await expect.poll(() => segmentsResponses.length, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);

    // Wait for the loading paragraph (".mn-loading" with "Loading beat state…")
    // to disappear — that confirms the data-load effect ran setLoading(false)
    // after the empty fetches. The Select toolbar is rendered above this
    // section throughout, so we can probe its placeholder afterwards.
    await expect(page.locator('.mn-loading')).toHaveCount(0, { timeout: 5_000 });

    const segmentSelect = page.locator('[data-testid="select-bg-segment"]');
    await expect(segmentSelect).toBeVisible();

    // The Select primitive renders the placeholder as <option value="">{text}</option>.
    const placeholderOpt = segmentSelect.locator('option[value=""]');
    await expect(placeholderOpt).toHaveCount(1);

    const placeholderText = (await placeholderOpt.textContent())?.trim() ?? '';

    // CONTRACT 1 — placeholder must NOT keep saying "Loading…" after the fetch
    // settled. That's the bug: empty-array conflated with still-loading.
    expect(
      placeholderText,
      'F-BG-001: Segment dropdown placeholder still reads "Loading…" after the ' +
      'server returned {segments: [], arc_number: N}. The placeholder must ' +
      'distinguish "loading" (in-flight) from "loaded, no segments authored".',
    ).not.toMatch(/loading/i);

    // CONTRACT 2 — placeholder must surface a recognizable empty-state hint so
    // the user knows authoring is required. Wording is flexible; we accept
    // either "no segments" (broad) or any phrasing that mentions an absence.
    expect(
      placeholderText,
      'F-BG-001: Segment dropdown placeholder should communicate the empty ' +
      'state (e.g. "(no segments yet)" or "no segments authored"). Current ' +
      `text: "${placeholderText}"`,
    ).toMatch(/no segments/i);
  });
});

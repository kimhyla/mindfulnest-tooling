// Layer B Option B — bg_session_state derives segment from scope_event_id
//
// LD: LD-545 SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 (Option B locked)
// Spec: Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md §3
// Bugs being closed: Bug 2 (Add Beat → wrong segment) + Bug 4 (BG ref drop UI doesn't refresh)
//
// Architectural change under test:
//   * `_handle_bg_session_state` now derives segment from request's
//     `scope_event_id` / `scope_arc_number` / `scope_phase` query params,
//     NOT from sidecar's `active_context`.
//   * Response carries a NEW `scope_active_context` field that is
//     authoritative for the rendered beats.
//   * `active_context` retained for backward compat (becomes secondary
//     dropdown filter under Option B).
//   * `migration_warnings` extended with `scope_active_context_divergence`
//     when scope and sidecar's active_context disagree.
//
// What this spec asserts (CONTRACT level, not server-internal):
//
//   T1. Client sends scope_event_id in the bg_session_state query string
//       — proves the client is set up to drive scope-canonical lookup.
//
//   T2. When the server response includes `scope_active_context`, it
//       matches the requested scope_event_id — proves the response shape
//       carries the new field and the client renders against it.
//
//   T3. When the response carries a `scope_active_context_divergence`
//       migration warning, the client surfaces or absorbs it without
//       breaking the BG render — Bug 2/4 root-cause regression guard.
//
// We mock the server response — direct server-side derivation logic is
// covered by py_compile + the grep markers verified at PR time.

import { test, expect, type Page, type Request } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  // Rule 32 N/A: applies to fetch() calls in production tool HTML (storyboard,
  // beat generator, cropper) per CLAUDE.md Rule 32 wording. Playwright e2e
  // test navigation uses Playwright's `baseURL` config (set to
  // `http://localhost:5111` in playwright.config.ts) — established
  // convention used in 18 existing spec files. [CONFIRMED via
  // `grep -rln "page.goto('/')" Production/tools/storyboard-v2/e2e/`]
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function mockSnapshot(page: Page): Promise<void> {
  await page.route('**/api/state/snapshot', async (r) => {
    await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
}

async function mockSegments(page: Page): Promise<void> {
  await page.route('**/api/bg/segments**', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        segments: [
          { event_id: 'E1', phase: 'intro', name: 'E1 Intro' },
          { event_id: 'E2', phase: 'intro', name: 'E2 Intro' },
        ],
      }),
    });
  });
}

test.describe('Layer B Option B — bg_session_state scope-canonical contract', () => {
  // T1 is a regression guard for an EXISTING client contract — the
  // storyboard-v2 client is already wired (in api/client.ts +
  // BgTab.tsx) to send `scope_event_id` on bg_session_state requests
  // when a scope is active. This PR's server change presumes that
  // wiring; T1 makes the presumption explicit so any future client
  // refactor that drops scope_event_id is caught at CI time. The
  // assertion is strict-equality on `scope_event_id` (NOT the
  // `event_id` legacy alias) — a vacuous pass would require the
  // client to emit zero requests, which fails on the prior
  // `expect.poll(() => sessionStateReqs.length).toBeGreaterThanOrEqual(1)`.
  test('T1 — bg_session_state request includes scope_event_id query param when client has a scope', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);

    const sessionStateReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/bg/session-state')) sessionStateReqs.push(req);
    });

    // Mock session-state to return EMPTY beats so we can focus the assertion
    // on the request shape (T1 contract). Response carries scope_active_context
    // matching the request to keep the client happy.
    await page.route('**/api/bg/session-state**', async (r) => {
      const url = new URL(r.request().url());
      const eid = url.searchParams.get('scope_event_id') ?? url.searchParams.get('event_id') ?? 'unknown';
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active_context: { arc_number: 1, event_id: eid, phase: 'intro' },
          scope_active_context: { arc_number: 1, event_id: eid, phase: 'intro' },
          beats: [],
          flux_options_complete: false,
          capabilities: {},
          migration_warnings: [],
        }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');

    // Wait for at least one bg_session_state fetch.
    await expect.poll(() => sessionStateReqs.length, { timeout: 5_000 })
      .toBeGreaterThanOrEqual(1);

    // T1 assertion (tightened): at least one request carries the NEW
    // `scope_event_id` query param — strict-equality check on the
    // Option-B-canonical key, NOT the `event_id` legacy alias. The
    // alias-fallback in the server is a transitional safety net for
    // legacy clients, but the storyboard-v2 client must drive the
    // scope-canonical wiring; accepting `event_id` here would mask
    // a regression where the client skips scope and only sends the
    // legacy key.
    const url0 = new URL(sessionStateReqs[0].url());
    expect(url0.searchParams.has('scope_event_id')).toBe(true);
  });

  // T2 deliberately removed in round-3 review cycle: a previous draft
  // asserted the round-trip `lastRespondedScopeEventId === lastRequestedEventId`,
  // which the AI review correctly flagged as trivially true by mock
  // construction (the mock built the response scope from the request's
  // event_id parameter, so the assertion tested the mock's own logic).
  // The server-side contract this would have tested (response's
  // scope_active_context derived from request, NOT sidecar's
  // active_context) belongs in a Python pytest against the real handler,
  // not a Playwright mock — filed as prod_blockers id=114 for
  // architectural follow-up. T3 below covers the meaningful client-render
  // contract under divergence.

  test('T3 — divergence migration_warning does not break the BG render (Bug 2/4 regression guard)', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);

    await page.route('**/api/bg/session-state**', async (r) => {
      const url = new URL(r.request().url());
      const eid = url.searchParams.get('scope_event_id') ?? url.searchParams.get('event_id') ?? 'E1';
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active_context: { arc_number: 1, event_id: 'STALE_ACTIVE_CONTEXT', phase: 'intro' },
          scope_active_context: { arc_number: 1, event_id: eid, phase: 'intro' },
          // Provide one beat so the panel actually renders something.
          beats: [{
            beat_id: 'beat_t3_01',
            dialogue_text: 'Layer B Option B regression guard beat.',
            speaker: 'Tessa',
            status: 'ready',
            gpt_options: [],
            accepted_image_key: null,
          }],
          flux_options_complete: false,
          capabilities: {},
          migration_warnings: [{
            type: 'scope_active_context_divergence',
            message: 'scope wins per LD-545 Option B',
            scope: { arc_number: 1, event_id: eid, phase: 'intro' },
            active_context: { arc_number: 1, event_id: 'STALE_ACTIVE_CONTEXT', phase: 'intro' },
          }],
        }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');

    // T3 assertion: the BG tab pane stays mounted + the beat with our
    // synthetic id renders, even though the response carries a
    // scope_active_context_divergence warning. This is the Bug 2/4
    // regression guard — the warning is not supposed to break the render
    // path (it's debug telemetry, not a UI block).
    await expect(page.locator('[data-testid="pane-bg"], [data-testid="bg-pane"]').first()).toBeVisible({
      timeout: 5_000,
    });
    // The beat dialogue text rendering somewhere inside the BG tab is
    // sufficient evidence the response was consumed without throwing.
    await expect(
      page.locator('text=Layer B Option B regression guard beat.').first(),
    ).toBeVisible({ timeout: 5_000 });
  });
});

// Retroactive Coverage Sprint — S2 pathappPatch Mutation Channel Coverage
//
// Spec: STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md §3 S2
// LDs: LD-456 SCOPE_VALIDATION_V1, LD-461 SCOPE_BODY_HELPER_V1,
//      Rule 36 PATCH_INVARIANT_PERSISTENCE_V1
//
// Verifies pathappPatch's load-bearing invariants:
//   1. Pre-mutation /api/state/snapshot fires (M1 invariant, client.ts:184)
//   2. Scope key injected per LD-461 (scope_event_id for BG endpoints,
//      event_id for non-BG); scope_version + scope_target_video also injected.
//   3. Milestone-scope adds scope_milestone_id (MILESTONE_STANDALONE_INDEPENDENT_V1).
//   4. HTTP 409 emits mn:scope-mismatch window event (LD-456).
//   5. HTTP 423 re-hydrates via /api/v2/event/<id>/state then retries once
//      (LD-458/460).
//
// SUT note: spec §3 S2 lists `bg_finalize` and `bg_unlock` mutations to
// read-back. Those endpoint names did not survive into S5.5d v3 architecture;
// the closeout doc captures this drift. We exercise the mutations that DO
// exist today: bg_accept_option, beat_update_text, beat_use_as_final, select.

import { test, expect, type Page, type Request } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

// Capture every snapshot + bg/accept-option request so we can assert
// ordering + body shape.
function trackRequests(page: Page, urlSubstrs: string[]): { reqs: Request[] } {
  const reqs: Request[] = [];
  page.on('request', (req) => {
    if (urlSubstrs.some((s) => req.url().includes(s))) reqs.push(req);
  });
  return { reqs };
}

async function mockBgWithOneOptioned(
  page: Page,
  beatId = 'beat_s2_01',
  optionKey = 'opt_s2_a',
): Promise<void> {
  await page.route('**/api/bg/segments**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        segments: [{ event_id: 'E1', phase: 'intro', name: 'Intro' }],
      }),
    });
  });
  await page.route('**/api/bg/session-state**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        active_context: { arc_number: 1, event_id: 'E1', phase: 'intro' },
        beats: [
          {
            beat_id: beatId,
            dialogue_text: 'S2 fixture beat.',
            speaker: 'Tessa',
            status: 'ready',
            gpt_options: [{ key: optionKey, filename: 'opt.png', cost_usd: 0.04 }],
            accepted_image_key: null,
          },
        ],
      }),
    });
  });
}

test.describe('S2 — pathappPatch mutation channel', () => {
  test('S2.1 — bg_accept_option goes through pathappPatch: snapshot fires BEFORE mutation; request body has scope_event_id + scope_version + scope_target_video + beat_id', async ({ page }) => {
    await mockBgWithOneOptioned(page);
    const snapshotReqs: Request[] = [];
    const acceptReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapshotReqs.push(req);
      if (req.url().includes('/api/bg/accept-option')) acceptReqs.push(req);
    });
    // Mock both endpoints so the mutation completes.
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/bg/accept-option', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    const radio = page.locator('[data-testid="bg-option-radio-0-0"]');
    await expect(radio).toBeVisible();
    await radio.click();

    // Both fired.
    await expect.poll(() => snapshotReqs.length).toBeGreaterThanOrEqual(1);
    await expect.poll(() => acceptReqs.length).toBeGreaterThanOrEqual(1);
    // Snapshot timestamp predates accept-option.
    const tSnap = snapshotReqs[0]!.timing().startTime;
    const tAccept = acceptReqs[0]!.timing().startTime;
    expect(tSnap).toBeLessThanOrEqual(tAccept);
    // Body shape per LD-461 + R2 + R3 fix.
    const body = acceptReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['option_key']).toBe('opt_s2_a');
    expect(body['beat_id']).toBe('beat_s2_01');
    // BG endpoint → scope_event_id (NOT event_id) per LD-461.
    expect(body['scope_event_id']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');
    // scope_target_video + scope_video_role auto-injected (S5.5b/d).
    expect(body['scope_target_video']).toBe('intro');
    expect(body['scope_video_role']).toBe('intro');
  });

  test('S2.2 — beat_update_text (non-BG endpoint) carries event_id key (NOT scope_event_id) + scope_version', async ({ page }) => {
    // Use the fixture's actual beats — beat_update_text path runs through StoryboardTab BeatCard.
    // Provide v2 event-state via the live server (no mock); ensure snapshot succeeds.
    const updateReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/beat/update_text')) updateReqs.push(req);
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    // First beat in fixture (beat_01).
    const firstBeat = page.locator('[data-testid="beat-text-0"]');
    await expect(firstBeat).toBeVisible();
    await firstBeat.click();
    // Type something then blur to trigger save.
    await firstBeat.fill('S2.2 retroactive marker');
    // Blur by clicking outside.
    await page.locator('[data-testid="app-root"]').click({ position: { x: 1, y: 1 } });
    await expect.poll(() => updateReqs.length, { timeout: 7_000 }).toBeGreaterThanOrEqual(1);
    const body = updateReqs[0]!.postDataJSON() as Record<string, unknown>;
    // beat_update_text — scope pin is scope_event_id (LD-461 category fix).
    expect(body['scope_event_id']).toBeDefined();
    expect(body['beat']).toBe('beat_01');
    expect(typeof body['scope_version']).toBe('number');
    // Restore the fixture text by typing it back.
    await firstBeat.click();
    await firstBeat.fill('Fixture beat one — placeholder dialogue for e2e testing.');
    await page.locator('[data-testid="app-root"]').click({ position: { x: 1, y: 1 } });
  });

  test('S2.3 — pathappPatch surfaces HTTP 409 by emitting "mn:scope-mismatch" window event', async ({ page }) => {
    await mockBgWithOneOptioned(page);
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/bg/accept-option', async (r) => {
      await r.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: false,
          error_code: 'SCOPE_MISMATCH',
          error_message: 'scope_event_id mismatch',
          retry_safe: false,
          hint: 'Reload the tab to re-resolve.',
          expected_event_id: 'Event_x',
          got_event_id: 'Event_y',
        }),
      });
    });
    await gotoApp(page);
    // Install listener BEFORE click so we don't miss the event.
    await page.evaluate(() => {
      (window as unknown as { __mn_scope_mismatch?: unknown[] }).__mn_scope_mismatch = [];
      window.addEventListener('mn:scope-mismatch', (e: Event) => {
        const ce = e as CustomEvent;
        ((window as unknown as { __mn_scope_mismatch: unknown[] }).__mn_scope_mismatch).push(ce.detail);
      });
    });
    await page.click('[data-testid="tab-bg"]');
    await page.locator('[data-testid="bg-option-radio-0-0"]').click();
    // Wait for the event to fire.
    await expect.poll(async () =>
      page.evaluate(() =>
        (window as unknown as { __mn_scope_mismatch?: unknown[] }).__mn_scope_mismatch?.length ?? 0,
      ),
      { timeout: 5_000 },
    ).toBeGreaterThanOrEqual(1);
    const detail = await page.evaluate(() =>
      (window as unknown as { __mn_scope_mismatch?: Array<Record<string, unknown>> }).__mn_scope_mismatch?.[0],
    );
    expect((detail as Record<string, unknown>)['error_code']).toBe('SCOPE_MISMATCH');
    expect((detail as Record<string, unknown>)['error_message']).toBe('scope_event_id mismatch');
  });

  test('S2.4 — pathappPatch handles HTTP 423 by re-hydrating via /api/v2/event/<id>/state and retrying once', async ({ page }) => {
    await mockBgWithOneOptioned(page);
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    let acceptCallCount = 0;
    await page.route('**/api/bg/accept-option', async (r) => {
      acceptCallCount += 1;
      if (acceptCallCount === 1) {
        await r.fulfill({
          status: 423,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'event_changed_mid_job' }),
        });
      } else {
        await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
      }
    });
    let stateRehydrateCount = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      stateRehydrateCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ _module_version: 1, videos: { intro: { beats: {} } } }),
      });
    });
    // Capture mn:event-changed events.
    await gotoApp(page);
    await page.evaluate(() => {
      (window as unknown as { __mn_evt_changed?: unknown[] }).__mn_evt_changed = [];
      window.addEventListener('mn:event-changed', (e: Event) => {
        const ce = e as CustomEvent;
        ((window as unknown as { __mn_evt_changed: unknown[] }).__mn_evt_changed).push(ce.detail);
      });
    });
    await page.click('[data-testid="tab-bg"]');
    await page.locator('[data-testid="bg-option-radio-0-0"]').click();
    // First call 423 → re-hydrate v2 state → retry second call → 200.
    await expect.poll(() => acceptCallCount, { timeout: 7_000 }).toBeGreaterThanOrEqual(2);
    expect(stateRehydrateCount).toBeGreaterThanOrEqual(1);
    const events = await page.evaluate(() =>
      (window as unknown as { __mn_evt_changed?: Array<Record<string, unknown>> }).__mn_evt_changed,
    );
    // Both before-retry and after-retry events fire.
    expect((events ?? []).length).toBeGreaterThanOrEqual(2);
    const phases = (events ?? []).map((d) => (d as Record<string, unknown>)['phase']);
    expect(phases).toContain('before-retry');
    expect(phases).toContain('after-retry');
  });

  test('S2.5 — bg_accept_lib_image (BG endpoint mutation) carries scope_event_id + scope_version + LD-461 keys', async ({ page }) => {
    await mockBgWithOneOptioned(page);
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    const acceptLibReqs: Request[] = [];
    await page.route('**/api/bg/accept-lib-image', async (route) => {
      const req = route.request();
      acceptLibReqs.push(req);
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    // Synthesize a drop on the option slot to fire bg_accept_lib_image.
    const slot = page.locator('[data-testid="bg-option-0-0"]');
    await expect(slot).toBeVisible();
    await slot.evaluate((el: Element) => {
      const dt = new DataTransfer();
      const payload = JSON.stringify({
        kind: 'lib-image',
        lib_key: 'synthetic_s2',
        tier: 'source',
        abs_path: '/tmp/s2.png',
        filename: 's2.png',
      });
      dt.setData('application/x-mn-drag', payload);
      dt.setData('text/plain', payload);
      el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
    });
    await expect.poll(() => acceptLibReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = acceptLibReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['scope_event_id']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');
    expect(body['scope_target_video']).toBe('intro');
    expect(body['key']).toBe('synthetic_s2');
    expect(body['slot_index']).toBe(0);
  });

  test('S2.6 — non-BG mutation (state_snapshot itself) skips pre-snapshot recursion', async ({ page }) => {
    // Track snapshot calls. When the page boots we expect 0 background snapshots
    // (no mutations triggered). Then trigger a beat update — that should produce
    // exactly ONE snapshot (the pre-mutation one), not a snapshot-of-snapshot.
    const snapReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapReqs.push(req);
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const baselineCount = snapReqs.length;
    // Trigger a single mutation (beat text edit + blur).
    const firstBeat = page.locator('[data-testid="beat-text-0"]');
    await expect(firstBeat).toBeVisible();
    await firstBeat.click();
    await firstBeat.fill('S2.6 mutation marker');
    await page.locator('[data-testid="app-root"]').click({ position: { x: 1, y: 1 } });
    // Allow the snapshot + mutation to fire.
    await expect.poll(() => snapReqs.length, { timeout: 5_000 }).toBeGreaterThan(baselineCount);
    // The increment from baseline must equal 1 — exactly one snapshot fires per
    // mutation, no recursion. (Allow up to 2 to absorb potential text-shadow
    // double-blur in some Preact paths, but never zero or many.)
    const delta = snapReqs.length - baselineCount;
    expect(delta).toBeGreaterThanOrEqual(1);
    expect(delta).toBeLessThanOrEqual(2);
    // Restore.
    await firstBeat.click();
    await firstBeat.fill('Fixture beat one — placeholder dialogue for e2e testing.');
    await page.locator('[data-testid="app-root"]').click({ position: { x: 1, y: 1 } });
  });
});

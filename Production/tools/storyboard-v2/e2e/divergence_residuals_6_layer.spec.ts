// 6-Layer wiring tests for the two new mutation paths reconciled in PR #19
// (S5.5c-pass2 Phase A primitives). Filed per AI Review's non-blocking
// 6-Layer concern that BeatImageHolder.assign_image and BgTab.bg_delete_beat
// modal flow had no wiring assertion.
//
// LDs:
//   * LD-656 PHASED_DELIVERY_PRIMITIVE_HOOKS_S5_5C_V1 (Phase A drop surfaces)
//   * LD-542 LIBRARY_TIER_FILTER_V1 (referenced by surrounding work, not under test here)
//
// Test #3 — StoryboardTab BeatImageHolder
//   GIVEN a beat with no image_path (drop zone visible)
//   WHEN a synthetic `lib-image` payload is dropped onto the zone
//   THEN pathappPatch fires with op=assign_image and body { beat, image_key }
//
// Test #4 — BgTab executeDeleteBeat (modal flow, replaces window.confirm per BG-9)
//   GIVEN a BG beat
//   WHEN the user clicks the per-beat Delete button
//   THEN a modal appears (NOT browser window.confirm)
//   AND clicking [bg-delete-confirm] fires pathappPatch op=bg_delete_beat

import { test, expect, type Page, type Request } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

// Mirrors the synthDrop helper in s5_5g_smoke.spec.ts. Dispatches a synthetic
// DragEvent('drop') with a JSON payload — Playwright's dragTo is fragile
// across Preact subtrees that re-render mid-drag.
async function synthDrop(
  page: Page,
  selector: string,
  payload: Record<string, unknown>,
): Promise<void> {
  const el = page.locator(selector);
  await expect(el).toBeVisible();
  const box = await el.boundingBox();
  if (!box) throw new Error(`No bounding box for ${selector}`);
  const x = box.x + box.width * 0.5;
  const y = box.y + box.height * 0.5;
  await el.evaluate(
    (node: Element, args: { payloadStr: string; clientX: number; clientY: number }) => {
      const dt = new DataTransfer();
      dt.setData('application/x-mn-drag', args.payloadStr);
      dt.setData('text/plain', args.payloadStr);
      const drop = new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.clientX,
        clientY: args.clientY,
      });
      node.dispatchEvent(drop);
    },
    { payloadStr: JSON.stringify(payload), clientX: x, clientY: y },
  );
}

async function mockSnapshot(page: Page): Promise<void> {
  await page.route('**/api/state/snapshot', async (r) => {
    await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
}

// ----------------------------------------------------------------------------
// Test #3 — StoryboardTab BeatImageHolder assign_image drop
// ----------------------------------------------------------------------------

test.describe('Track A residual #3 — BeatImageHolder assign_image drop wiring', () => {
  test('drop on mn-storyboard-image-drop-zone fires pathappPatch op=assign_image with { beat, image_key } AND triggers parent re-fetch (Layer 5)', async ({ page }) => {
    // Mock state endpoint with a counter so we can prove Layer 5 — the
    // onMutated() callback in BeatImageHolder fires after the server
    // response, which bumps refreshTick in the parent StoryboardTab,
    // which re-runs the state-fetch useEffect. We expect ≥2 state
    // fetches: 1 on mount + ≥1 post-mutation.
    let stateFetchCount = 0;
    await page.route('**/api/v2/event/**/state', async (r) => {
      stateFetchCount += 1;
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: {
            // activeTargetVideo defaults to 'intro' (scope.ts L56) so the
            // storyboard renders from state.videos['intro']. Using 'phase_a'
            // here caused the beats to never render — beat-image-zone-0 not found.
            'intro': {
              video_role: 'intro',
              beats: {
                'beat_pa_01': {
                  speaker: 'Tessa',
                  text: 'No image yet — drop zone should render.',
                  // No image_path → BeatImageHolder shows drop placeholder.
                },
              },
              display_order: ['beat_pa_01'],
            },
          },
        }),
      });
    });

    await mockSnapshot(page);

    const assignReqs: Request[] = [];
    page.on('request', (req) => {
      // [CONFIRMED against src/api/endpoints.ts L63] pathappPatch routes
      // assign_image via POST /api/assign-image (not /pathapp/<op>).
      // Capture by URL — body only carries { beat, image_key, scope_* } keys,
      // not the operation name.
      if (req.method() === 'POST' && req.url().includes('/api/assign-image')) {
        assignReqs.push(req);
      }
    });
    // Stub the assign_image mutation so the request resolves.
    // [CONFIRMED against src/api/endpoints.ts L63] actual URL is /api/assign-image.
    await page.route('**/api/assign-image', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');

    const dropZone = page.locator('[data-testid="beat-image-zone-0"]');
    await expect(dropZone).toBeVisible({ timeout: 5_000 });
    await expect(dropZone).toHaveClass(/mn-storyboard-image-drop-zone/);

    // Capture initial state-fetch count so the post-mutation re-fetch can
    // be detected as a strict increase rather than an absolute number
    // (the mount sequence may issue >1 fetch depending on useEffect deps).
    const stateFetchCountAtDrop = stateFetchCount;

    // 6-Layer check: dispatch the synthetic drop and verify pathappPatch fires
    // with the right op + body.
    await synthDrop(page, '[data-testid="beat-image-zone-0"]', {
      kind: 'lib-image',
      lib_key: 'test_lib_key_pa01',
    });

    // Layer 4 — UI→backend mutation wiring.
    await expect.poll(() => assignReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = JSON.parse(assignReqs[0].postData() || '{}');
    // body shape: { beat, image_key, op or implied via URL routing }
    expect(body['beat']).toBe('beat_pa_01');
    expect(body['image_key']).toBe('test_lib_key_pa01');

    // Layer 5 — onMutated() callback triggers parent state re-fetch. The
    // contract: after the assign_image response resolves, BeatImageHolder
    // calls onMutated, which in StoryboardTab bumps refreshTick, which
    // re-runs the state-fetch useEffect. Assert state fetch count strictly
    // increased after the drop — proves the wiring is end-to-end, not
    // just request-only.
    await expect.poll(() => stateFetchCount, { timeout: 5_000, intervals: [200, 500, 1000] })
      .toBeGreaterThan(stateFetchCountAtDrop);
  });

  test('drop zone CSS class is present in DOM (sanity — proves PR #19 reconciliation landed)', async ({ page }) => {
    await page.route('**/api/v2/event/**/state', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: {
            // Must be 'intro' — activeTargetVideo defaults to 'intro' (scope.ts L56).
            'intro': {
              video_role: 'intro',
              beats: { 'beat_x': { speaker: 'Tessa', text: 'x' } },
              display_order: ['beat_x'],
            },
          },
        }),
      });
    });
    await mockSnapshot(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    // [CONFIRMED against archive/dropbox-resident/claude/preserve-uncommitted-divergence-20260507
    //  commit 95e4462, reconciled into main via PR #19 commit 62d8e91] CC-16
    // BeatImageHolder + .mn-storyboard-image-drop-zone CSS class now in main.
    const zone = page.locator('.mn-storyboard-image-drop-zone').first();
    await expect(zone).toBeVisible();
  });
});

// ----------------------------------------------------------------------------
// Test #4 — BgTab executeDeleteBeat modal-confirm flow (BG-9, replaces window.confirm)
// ----------------------------------------------------------------------------

test.describe('Track A residual #4 — BgTab delete-beat modal wiring', () => {
  test('Delete button opens modal (NOT window.confirm); confirm fires pathappPatch op=bg_delete_beat', async ({ page }) => {
    // Stub a single BG segment + one beat so the BgTab renders something
    // deletable. Shape mirrors retroactive_s2_pathapp_patch.spec.ts.
    await page.route('**/api/bg/segments**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          segments: [{ event_id: 'E1', phase: 'intro', name: 'Intro' }],
        }),
      });
    });
    await page.route('**/api/bg/session-state**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          active_context: { arc_number: 1, event_id: 'E1', phase: 'intro' },
          beats: [
            {
              beat_id: 'beat_del_01',
              dialogue_text: 'beat to delete via modal flow.',
              speaker: 'Tessa',
              status: 'ready',
              gpt_options: [],
              accepted_image_key: null,
            },
          ],
        }),
      });
    });
    await mockSnapshot(page);

    // 6-Layer guard: any window.confirm call would fail this test (BG-9
    // contract is modal-based confirm, not browser-confirm).
    let windowConfirmFired = false;
    await page.exposeFunction('__mn_test_record_confirm', () => {
      windowConfirmFired = true;
    });
    await page.addInitScript(() => {
      const orig = window.confirm;
      window.confirm = function (...args: unknown[]) {
        // @ts-ignore — exposeFunction
        if (typeof window.__mn_test_record_confirm === 'function') {
          // @ts-ignore
          window.__mn_test_record_confirm();
        }
        return orig.apply(window, args as []);
      };
    });

    const deleteReqs: Request[] = [];
    page.on('request', (req) => {
      // [CONFIRMED against src/api/endpoints.ts L124] pathappPatch routes
      // bg_delete_beat via POST /api/bg/delete-beat (not /pathapp/<op>).
      // Capture by URL — body only carries { beat_id, scope_* } keys,
      // not the operation name.
      if (req.method() === 'POST' && req.url().includes('/api/bg/delete-beat')) {
        deleteReqs.push(req);
      }
    });
    // [CONFIRMED against src/api/endpoints.ts L124] actual URL is /api/bg/delete-beat.
    await page.route('**/api/bg/delete-beat', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');

    // Click the per-beat Delete button (data-testid pattern: bg-beat-delete-{index}).
    const deleteBtn = page.locator('[data-testid="bg-beat-delete-0"]');
    await expect(deleteBtn).toBeVisible({ timeout: 5_000 });
    await deleteBtn.click();

    // Modal must appear with both buttons present (BG-9 contract).
    const cancelBtn = page.locator('[data-testid="bg-delete-cancel"]');
    const confirmBtn = page.locator('[data-testid="bg-delete-confirm"]');
    await expect(cancelBtn).toBeVisible({ timeout: 2_000 });
    await expect(confirmBtn).toBeVisible({ timeout: 2_000 });

    // 6-Layer assertion: modal-based, NOT window.confirm.
    expect(windowConfirmFired).toBe(false);

    await confirmBtn.click();

    await expect.poll(() => deleteReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = JSON.parse(deleteReqs[0].postData() || '{}');
    expect(body['beat_id']).toBe('beat_del_01');
  });
});

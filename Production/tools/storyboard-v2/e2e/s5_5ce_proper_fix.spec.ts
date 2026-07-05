// S5.5c+e proper-fix tests — TDD red→green for the 5 integration bugs surfaced
// by Kim's browser smoke on 2026-05-03 + the +NewEvent endpoint.
//
// Spec: Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md (§5 Phase 2.1)
// LDs: MANDATORY_E2E_GATE_V1 (CRITICAL), CI_PLAYWRIGHT_ON_COMMIT_V1 (HIGH),
//      NEW_EVENT_CREATION_UI_V1 (MEDIUM)
//
// Fixture: Production/Event_e2e_fixture/ (intro=3 beats, resolution=0 beats);
// see Production/Event_e2e_fixture/README.md for layout.
//
// Test ordering: infra smoke (Q10A counter) → R1 → R2 → R3 → R4 → R5 → +NewEvent.

import { test, expect, type Page, type Request } from '@playwright/test';
import { openStoryboardPane } from './helpers';
import { restoreE2eFixtureOnServer } from './fixtureRestore';

const SERVER = 'http://localhost:5200';
const FIXTURE_EVENT = 'Event_e2e_fixture';

const EMPTY_NEXT_OPTIONS = { ok: true, options: [], anomalies: [] };

async function mockEmptyNextOptions(page: Page): Promise<void> {
  await page.route('**/api/production/next-options**', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_NEXT_OPTIONS),
    });
  });
}

test.afterAll(async ({ request }) => {
  await restoreE2eFixtureOnServer(request);
});

async function gotoApp(page: Page): Promise<void> {
  // Capture pageerror so a bug-induced render crash surfaces in test output
  // instead of silent toolbar-emptiness.
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

// ----------------------------------------------------------------------------
// Infra-smoke (counter Q10A): proves CI workflow + webServer + globalSetup +
// fixture + bundle build all wire correctly. Always GREEN. If this is RED on
// CI but local is GREEN, the bug is in the workflow YAML, not the product.
// ----------------------------------------------------------------------------

test.describe('infra smoke', () => {
  test('infra-smoke — workflow + webServer + fixture + bundle all wire up', async ({ page }) => {
    await gotoApp(page);
    // Core operator tabs (Storyboard is hiddenFromBar — not in tab bar).
    await expect(page.locator('[data-testid="tab-bg"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-cropper"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-phase-a"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-phase-b"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-stitcher"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-map"]')).toBeVisible();
    // ScopeBoundary resolved against the fixture (not Event_1).
    await expect.poll(async () =>
      page.evaluate(() => document.body.getAttribute('data-resolved-scope')),
    ).toContain(FIXTURE_EVENT);
    // Server health round-trip via in-page fetch (proves CORS + server reachable).
    const health = await page.evaluate(async () => {
      const r = await fetch('http://localhost:5200/api/health');
      return { ok: r.ok, status: r.status };
    });
    expect(health.ok).toBe(true);
    expect(health.status).toBe(200);
  });
});

// ----------------------------------------------------------------------------
// R1 — Scope-change re-fetch + milestone auto-load
// ----------------------------------------------------------------------------

test.describe('R1 — scope-change re-fetch', () => {
  test('R1.1 — switching video from intro→resolution clears beats; back→restores', async ({ page }) => {
    await page.route('**/api/video/set_active', async (r) => {
      const reqBody = JSON.parse(r.request().postData() ?? '{}');
      const role = reqBody.video_role ?? reqBody.scope_target_video ?? 'intro';
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          event_id: FIXTURE_EVENT,
          active_video: role,
        }),
      });
    });
    await gotoApp(page);
    // Land on Storyboard tab (default).
    await openStoryboardPane(page);
    await expect(page.locator('[data-testid="pane-storyboard"]')).toBeVisible();
    // Initial intro state: fixture has 3 beats. Wait for cards to render.
    await expect.poll(async () =>
      page.locator('[data-testid^="beat-card-"]').count(),
      { timeout: 10_000 },
    ).toBe(3);
    // Switch active video to resolution via VideoSelector.
    // The selector is a <select>; use selectOption.
    await page.locator('[data-testid="video-select"]').selectOption('resolution');
    // After fix: re-fetch fires and beats list updates to 0 within ~1s.
    // Before fix (RED): refreshTick doesn't re-fire on video change → beats stay at 3.
    await expect.poll(async () =>
      page.locator('[data-testid^="beat-card-"]').count(),
      { timeout: 5_000 },
    ).toBe(0);
    // Switch back to intro — beats should reappear.
    await page.locator('[data-testid="video-select"]').selectOption('intro');
    await expect.poll(async () =>
      page.locator('[data-testid^="beat-card-"]').count(),
      { timeout: 5_000 },
    ).toBe(3);
  });

  test('R1.2 — + New Milestone Create auto-loads milestone scope', async ({ page }) => {
    await mockEmptyNextOptions(page);
    await gotoApp(page);
    // Open the project selector dropdown.
    const projectSelect = page.locator('[data-testid="project-selector"] select');
    await expect(projectSelect).toBeVisible();
    // Pick the "+ New Milestone" sentinel from the Milestones group.
    await projectSelect.selectOption('__new_milestone__');
    // Modal opens.
    const modalIdInput = page.locator('[data-testid="new-milestone-id-input"]');
    await expect(modalIdInput).toBeVisible();
    // Use a unique id so test reruns don't collide on the server.
    const milestoneId = `e2e_${Date.now().toString(36)}`;
    await modalIdInput.fill(milestoneId);
    // Capture network — milestone_load should fire after Create per spec Phase 3.1.
    const loadRequests: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/milestones/load') || req.url().includes('/api/milestone/load')) {
        loadRequests.push(req);
      }
    });
    await page.locator('[data-testid="new-milestone-create"]').click();
    // After fix: auto-load fires within 5s. Before fix (RED): no auto-load (line 351 says "Don't auto-load").
    await expect.poll(() => loadRequests.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
  });
});

// ----------------------------------------------------------------------------
// R2 — Drag-drop wiring (BgTab option slots, char/BG ref slots, Cropper, CSS)
// ----------------------------------------------------------------------------

// Helper: mock the BG state endpoints so a single beat with one slot renders
// without depending on the real BG sidecar (fixture sidecar is empty;
// "Add empty beat" requires an active segment which the empty sidecar lacks).
async function mockBgWithOneBeat(page: Page, beatId: string = 'beat_e2e_01'): Promise<void> {
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
            dialogue_text: 'Test beat for drag-drop assertions.',
            speaker: 'Tessa',
            status: 'ready',
            gpt_options: [],
            accepted_image_key: null,
          },
        ],
      }),
    });
  });
}

test.describe('R2 — drag-drop wiring', () => {
  test('R2.1 — drag library tile → drop on BG option slot fires bg_accept_lib_image with correct body', async ({ page }) => {
    await mockBgWithOneBeat(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.locator('[data-testid="pane-bg"]')).toBeVisible();
    const firstLibItem = page.locator('[data-testid^="library-item-"]').first();
    await expect(firstLibItem).toBeVisible();
    const dropTarget = page.locator('[data-testid="bg-option-0-0"]');
    await expect(dropTarget).toBeVisible();
    const apReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('bg_accept_lib_image') || req.url().includes('bg/accept-lib-image')) {
        apReqs.push(req);
      }
    });
    await firstLibItem.dragTo(dropTarget);
    await expect.poll(() => apReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = apReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['beat_id']).toBe('beat_e2e_01');
    expect(body['key']).toBeDefined();
    expect(body['slot_index']).toBe(0);
    // filename + abs_path may be empty strings if drag payload didn't carry them
    // (depends on library data shape); presence-assert only.
    expect('filename' in body).toBe(true);
    expect('abs_path' in body).toBe(true);
  });

  test('R2.2 — drag library tile → drop on char ref slot triggers update', async ({ page }) => {
    await mockBgWithOneBeat(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    const firstLibItem = page.locator('[data-testid^="library-item-"]').first();
    await expect(firstLibItem).toBeVisible();
    const charRefDrop = page.locator('[data-testid="bg-char-ref-0"]');
    await expect(charRefDrop).toBeVisible();
    const updateReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('bg_update_beat') || req.url().includes('bg/update-beat')) {
        updateReqs.push(req);
      }
    });
    await firstLibItem.dragTo(charRefDrop);
    await expect.poll(() => updateReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = updateReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['beat_id']).toBe('beat_e2e_01');
    // Either reference_image or bg_ref_image set (drag handler sends one).
    expect(body['reference_image'] !== undefined || body['bg_ref_image'] !== undefined).toBe(true);
  });

  test('R2.3 — Cropper canvas drop target wired (structural + synthetic drop)', async ({ page }) => {
    // Note: real cross-modal drag is structurally blocked — cropper modal's
    // fullscreen backdrop intercepts pointer events on the library panel
    // behind it, so Playwright's dragTo can't pick up the library tile.
    // This test verifies the drop target STRUCTURAL WIRING (the regression
    // R2 introduced was missing-drop-target entirely) by:
    // 1. Opening the cropper modal
    // 2. Asserting cropper-canvas-drop-target exists + has mn-drop-target class
    // 3. Synthesizing a drop event with a lib-image payload via DataTransfer
    // 4. Asserting data-loaded-source attribute updates
    await gotoApp(page);
    await page.click('[data-testid="tab-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toBeVisible();
    const cropperCanvas = page.locator('[data-testid="cropper-canvas-drop-target"]');
    await expect(cropperCanvas).toBeVisible();
    const hasDropTargetClass = await cropperCanvas.evaluate((el: Element) =>
      el.classList.contains('mn-drop-target')
    );
    expect(hasDropTargetClass).toBe(true);

    // Synthesize a drop with a lib-image payload (matches DragPayload shape).
    await cropperCanvas.evaluate((el: Element) => {
      const dt = new DataTransfer();
      const payload = JSON.stringify({
        kind: 'lib-image',
        lib_key: 'synthetic_test',
        tier: 'source',
        abs_path: '/tmp/synthetic.png',
        filename: 'synthetic.png',
      });
      dt.setData('application/x-mn-drag', payload);
      dt.setData('text/plain', payload);
      el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
    });

    // After drop, data-loaded-source should reflect the dropped image.
    await expect.poll(async () =>
      cropperCanvas.getAttribute('data-loaded-source'),
      { timeout: 5_000 },
    ).toBeTruthy();
  });

  test('R2.4 — dragenter sets is-drag-over class on drop target; dragleave removes it', async ({ page }) => {
    await mockBgWithOneBeat(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    const dropTarget = page.locator('[data-testid="bg-option-0-0"]');
    await expect(dropTarget).toBeVisible();
    // Synthesize dragenter / dragleave via DOM events (Playwright doesn't expose dragenter alone).
    const hasClassAfterEnter = await dropTarget.evaluate((el: Element) => {
      const ev = new DragEvent('dragover', { bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      return el.classList.contains('is-drag-over');
    });
    expect(hasClassAfterEnter).toBe(true);
    const hasClassAfterLeave = await dropTarget.evaluate((el: Element) => {
      const ev = new DragEvent('dragleave', { bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      return el.classList.contains('is-drag-over');
    });
    expect(hasClassAfterLeave).toBe(false);
  });
});

// ----------------------------------------------------------------------------
// R3 — option_key gate (BgTab radio button)
// ----------------------------------------------------------------------------

test.describe('R3 — option_key gate', () => {
  test('R3.1 — radio click on option WITH key fires bg_accept_option, returns 200', async ({ page }) => {
    // Mock the BG state to inject one beat with one option (with key).
    await page.route('**/api/bg/session-state**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          active_context: { arc_number: 1, event_id: 'E1', phase: 'intro' },
          beats: [
            {
              beat_id: 'beat_01_test',
              dialogue_text: 'Test beat with valid option key.',
              speaker: 'Tessa',
              status: 'ready',
              gpt_options: [
                { key: 'opt_valid_a', filename: 'opt_a.png', cost_usd: 0.05 },
              ],
              accepted_image_key: null,
            },
          ],
        }),
      });
    });
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
    const acceptReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('bg/accept-option') || req.url().includes('bg_accept_option')) acceptReqs.push(req);
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    // The radio for option index 0 of beat index 0 in BgTab.
    const radio = page.locator('[data-testid="bg-option-radio-0-0"]');
    await expect(radio).toBeVisible();
    await expect(radio).not.toBeDisabled();
    await radio.click();
    await expect.poll(() => acceptReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = acceptReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['option_key']).toBe('opt_valid_a');
    expect(body['beat_id']).toBe('beat_01_test');
  });

  test('R3.2 — option WITHOUT key renders radio DISABLED with tooltip', async ({ page }) => {
    await page.route('**/api/bg/session-state**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          active_context: { arc_number: 1, event_id: 'E1', phase: 'intro' },
          beats: [
            {
              beat_id: 'beat_01_test',
              dialogue_text: 'Test beat with falsy-key option.',
              speaker: 'Tessa',
              status: 'ready',
              gpt_options: [
                { filename: 'no_key.png', cost_usd: 0.05 }, // missing `key`
              ],
              accepted_image_key: null,
            },
          ],
        }),
      });
    });
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
    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    const radio = page.locator('[data-testid="bg-option-radio-0-0"]');
    await expect(radio).toBeVisible();
    // After fix: radio is disabled when option.key is falsy.
    await expect(radio).toBeDisabled();
    // After fix: tooltip explaining the disabled state is present.
    const tooltipMatch = await radio.evaluate((el: Element) => {
      const title = el.getAttribute('title') ?? '';
      const ariaLabel = el.getAttribute('aria-label') ?? '';
      return /missing key|regenerate beat/i.test(title + ' ' + ariaLabel);
    });
    expect(tooltipMatch).toBe(true);
  });
});

// ----------------------------------------------------------------------------
// R4 — Production Map placeholder + UI note
// ----------------------------------------------------------------------------

test.describe('R4 — Production Map placeholder', () => {
  test('R4 — Production Map shows UI note explaining V1 scope policy', async ({ page }) => {
    await gotoApp(page);
    await page.click('[data-testid="tab-map"]');
    await expect(page.locator('[data-testid="pane-map"]')).toBeVisible();
    // After fix (Phase 3.4): UI note above the map table explains the TBD policy.
    const note = page.locator('[data-testid="production-map-tbd-note"]');
    await expect(note).toBeVisible();
    await expect(note).toContainText(/Play order|Arc Skeleton|New Event|New Milestone/i);
  });
});

// ----------------------------------------------------------------------------
// R5 — Library tile sizing
// ----------------------------------------------------------------------------

test.describe('R5 — library tile sizing', () => {
  test('R5 — library tile width ≤ 80px on 1280-wide viewport; rail height bounded', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await gotoApp(page);
    const firstLibItem = page.locator('[data-testid^="library-item-"]').first();
    await expect(firstLibItem).toBeVisible();
    const tileBox = await firstLibItem.boundingBox();
    expect(tileBox).not.toBeNull();
    // After fix: tile width ≤ 80px (CSS variable --ui-library-tile-size).
    expect(tileBox!.width).toBeLessThanOrEqual(80);
    // Library panel rail height is bounded (not page-spanning).
    const railBox = await page.locator('[data-testid="library-panel"]').boundingBox();
    expect(railBox).not.toBeNull();
    // After fix: rail height = 600px (CSS variable --ui-library-rail-height).
    expect(railBox!.height).toBeLessThanOrEqual(700); // some flex chrome allowed
  });
});

// ----------------------------------------------------------------------------
// + NewEvent — modal + server endpoint
// ----------------------------------------------------------------------------

const EMPTY_NEXT_OPTIONS = { ok: true, options: [], anomalies: [] };

async function mockEmptyNextOptions(page: Page): Promise<void> {
  await page.route('**/api/production/next-options**', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_NEXT_OPTIONS),
    });
  });
}

test.describe('+ NewEvent — modal + server endpoint', () => {
  test('+NewEvent.1 — modal opens; reserved-word prefix rejected with regex error', async ({ page }) => {
    await mockEmptyNextOptions(page);
    await gotoApp(page);
    const projectSelect = page.locator('[data-testid="project-selector"] select');
    await projectSelect.selectOption('__new_event__');
    // After fix (Phase 3.6): modal opens. Before fix: stub was disabled → no modal.
    const modal = page.locator('[data-testid="new-event-id-input"]');
    await expect(modal).toBeVisible();
    await modal.fill('Test_invalid');
    // Reserved-word error surfaces inline (live regex feedback per ProjectSelector pattern).
    const error = page.locator('[data-testid="new-event-id-error"]');
    await expect(error).toBeVisible();
    await expect(error).toContainText(/reserved|regex|cannot start/i);
  });

  test('+NewEvent.2 — valid event_id POSTs to /api/event/create; succeeds (200) or already-exists (409)', async ({ page }) => {
    await mockEmptyNextOptions(page);
    await gotoApp(page);
    const projectSelect = page.locator('[data-testid="project-selector"] select');
    await projectSelect.selectOption('__new_event__');
    const modalInput = page.locator('[data-testid="new-event-id-input"]');
    await expect(modalInput).toBeVisible();
    // Use a fresh unique id so re-runs don't collide.
    const eventId = `E2eFix_${Date.now().toString(36)}`;
    await modalInput.fill(eventId);
    const createReqs: { req: Request; status: number }[] = [];
    page.on('response', async (resp) => {
      if (resp.url().includes('/api/event/create')) {
        createReqs.push({ req: resp.request(), status: resp.status() });
      }
    });
    await page.locator('[data-testid="new-event-create"]').click();
    // After fix: POST to /api/event/create returns 200 or 409 (collision). Before fix (RED): 404.
    await expect.poll(() => createReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const posted = createReqs[0]!.req.postDataJSON() as Record<string, unknown>;
    // pathappPatch must not clobber body.event_id with the pinned scope (Event_4-on-5114 bug).
    expect(posted['event_id']).toBe(eventId);
    expect(posted['unexpected']).toBe(true);
    expect([200, 409]).toContain(createReqs[0]!.status);
  });
});

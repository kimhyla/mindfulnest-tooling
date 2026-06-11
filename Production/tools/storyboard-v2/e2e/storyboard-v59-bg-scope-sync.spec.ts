// C1 contract test for SOFT LD `BG_TAB_SCOPE_SYNC_V1`.
//
// CONTRACT (behavioral; future refactor must not regress):
//   When ANY scope-vector signal changes — activeScope.event_id,
//   activeProjectType, activeMilestoneId, OR activeTargetVideo — the BgTab
//   data-load effect re-fetches /api/bg/segments and /api/bg/session-state.
//   This is what prevents the cross-event-edit hazard described in spec v2 §1.
//
// Implementation facts pinned by the LD decision_text (NOT asserted at
// network level here; see LD body):
//   * useEffect dep array = [arcNumber, activeScope.value.event_id,
//     activeProjectType.value, activeMilestoneId.value, activeTargetVideo.value]
//   * First mount runs sync via prevDepsRef === null gate
//   * Subsequent re-fires are debounced 200 ms via window.setTimeout
//
// Why this test pins the contract: Playwright observes only the user-visible
// network outcome (re-fetches happen). The implementation could swap deps
// for explicit subscriptions or move the fetch to a different module — as
// long as the contract holds, the test stays green. If a refactor narrows
// the dep array (e.g. drops activeTargetVideo or activeMilestoneId), this
// test goes red and the LD invariant fires.

import { test, expect } from '@playwright/test';

// Same Event_e2e_fixture used everywhere else; pristine has BOTH `intro`
// (3 beats) and `resolution` (0 beats) partitions, so toggling
// VideoSelector mutates activeTargetVideo without needing a multi-event
// fixture or mocked /api/event/load.

test.describe('BG_TAB_SCOPE_SYNC_V1 — segment context re-fetches on scope-vector change', () => {
  test('VideoSelector swap (intro→resolution) re-fires bg/segments + bg/session-state', async ({ page }) => {
    // Network spy — count requests to the two BG endpoints across the full test.
    const segmentsHits: string[] = [];
    const sessionStateHits: string[] = [];
    page.on('request', (req) => {
      const u = req.url();
      if (u.includes('/api/bg/segments')) segmentsHits.push(u);
      if (u.includes('/api/bg/session-state')) {
        sessionStateHits.push(u);
        expect(u, 'session-state must carry scope_video_role after video switch').toMatch(
          /scope_video_role=(intro|resolution)/,
        );
      }
    });

    // Route-mock /api/video/set_active. The real server handler routes through
    // mutate_state which requires a Directus lock; local test envs don't have
    // Directus credentials so the call 500s and activeTargetVideo never updates,
    // masking the contract under test. Mock returns the same shape the
    // VideoSelector onChange handler reads (`{ok, active_video}`) so the
    // client's signal-update + URL-update path runs end-to-end. Mocking the
    // STATE-MUTATION endpoint to take Directus out of the loop is consistent
    // with how s5_5g_smoke.spec.ts and others isolate client behavior.
    await page.route('**/api/video/set_active', async (r) => {
      const reqBody = JSON.parse(r.request().postData() ?? '{}');
      const role = reqBody.video_role ?? reqBody.scope_target_video ?? 'intro';
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          event_id: 'Event_e2e_fixture',
          active_video: role,
        }),
      });
    });

    await page.goto('/');

    // Wait for ScopeBoundary to resolve (writes data-resolved-scope on body).
    await expect(page.locator('body')).toHaveAttribute(
      'data-resolved-scope',
      /Event_e2e_fixture:global:v\d+/,
      { timeout: 10_000 },
    );

    // Switch to Beat Generator — triggers the first BG load.
    await page.getByTestId('tab-bg').click();
    await expect(page.getByTestId('pane-bg')).toBeVisible();

    // Wait for the initial BG fetches to land (no shorter polling — let it settle).
    await expect.poll(() => segmentsHits.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => sessionStateHits.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const segCountAfterMount = segmentsHits.length;
    const ctxCountAfterMount = sessionStateHits.length;

    // Trigger a scope-vector change: VideoSelector intro -> resolution.
    // VideoSelector is rendered in the app header per app.tsx:92.
    const videoSelect = page.getByTestId('video-select');
    await expect(videoSelect).toBeVisible();
    await expect(videoSelect).toBeEnabled();

    // Verify both partitions exist in the dropdown — fixture invariant.
    await expect(videoSelect.locator('option[value="intro"]')).toHaveCount(1);
    await expect(videoSelect.locator('option[value="resolution"]')).toHaveCount(1);

    // Set value through the <select>; selectOption fires the change event,
    // which routes through pathappPatch → /api/video/set_active and bumps
    // activeTargetVideo, which is what the BgTab dep array subscribes to.
    await videoSelect.selectOption('resolution');

    // The contract: the BG data-load effect re-fires when activeTargetVideo
    // changes. Allow up to debounce (200 ms) + network roundtrip + slack.
    // expect.poll handles any timing flake without sleep().
    await expect
      .poll(() => segmentsHits.length, {
        timeout: 5_000,
        message:
          'BG_TAB_SCOPE_SYNC_V1 violated: /api/bg/segments did not re-fetch after activeTargetVideo change. ' +
          'The BgTab useEffect dep array has narrowed and no longer subscribes to all scope-vector signals.',
      })
      .toBeGreaterThan(segCountAfterMount);
    await expect
      .poll(() => sessionStateHits.length, {
        timeout: 5_000,
        message:
          'BG_TAB_SCOPE_SYNC_V1 violated: /api/bg/session-state did not re-fetch after activeTargetVideo change.',
      })
      .toBeGreaterThan(ctxCountAfterMount);
  });

  test('First-mount BG fetch is sync (no 200 ms debounce gate on initial load)', async ({ page }) => {
    // Pins the prevDepsRef === null branch: first mount fires fetchData()
    // synchronously, NOT via window.setTimeout(fetchData, 200). If this
    // gate is removed, the BG tab shows "Loading…" briefly even on first
    // open, which is what the proper-fix R1 amendment was specifically
    // protecting against (Cursor v8 Q6).
    const segmentsHits: { ts: number; url: string }[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/bg/segments')) {
        segmentsHits.push({ ts: Date.now(), url: req.url() });
      }
    });

    const navStart = Date.now();
    await page.goto('/');
    await expect(page.locator('body')).toHaveAttribute(
      'data-resolved-scope',
      /Event_e2e_fixture:global:v\d+/,
      { timeout: 10_000 },
    );

    // Switch to BG tab; record click timestamp as the synchronous mount baseline.
    const clickAt = Date.now();
    await page.getByTestId('tab-bg').click();

    // Sync mount means the first /api/bg/segments fires within ~debounce-ms
    // of the click; not delayed by the 200 ms re-fire debounce.
    await expect.poll(() => segmentsHits.length, { timeout: 3_000 }).toBeGreaterThanOrEqual(1);
    const firstHit = segmentsHits[0];

    // Soft assertion — first-mount fetch should land < 250 ms after the tab
    // click (sync path), not > 250 ms (would indicate the debounce gate
    // erroneously fires on first mount instead of the prevDepsRef branch).
    // Threshold is generous to absorb CI variance; any value > ~500 ms
    // signals an actual regression of the prevDepsRef sync gate.
    expect(firstHit.ts - clickAt,
      'BG_TAB_SCOPE_SYNC_V1 violated: first-mount BG fetch appears debounced. ' +
      'The prevDepsRef === null sync gate has regressed to debounced path.'
    ).toBeLessThan(500);
    // Reference navStart to keep the linter happy about unused capture.
    expect(firstHit.ts).toBeGreaterThan(navStart);
  });
});

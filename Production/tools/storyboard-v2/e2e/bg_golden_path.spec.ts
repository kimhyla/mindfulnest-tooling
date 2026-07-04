// BG_GOLDEN_PATH_V1 — operator-critical Beat Gen chain (Kim 2026-06-15)
//
// Contract (behavioral):
//   GP.1 — beats visible (not bg-empty) when session has beats
//   GP.2 — O3 clip tile click → POST /api/bg/select-o3-video via pathappPatch
//   GP.3 — selection persists after mocked session refresh (poll/rehydrate regression)
//   GP.4 — all beats approved → Send to Stitcher enabled → preflight GET → POST export-to-stitcher
//
// Uses mocked BG endpoints (Event_e2e_fixture shape) — no Kling vendor calls.

import { test, expect, type Page, type Request } from '@playwright/test';

const FIXTURE_EVENT = 'Event_e2e_fixture';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  // Pin URL scope so persisted Event_2 (or other) sessionStorage cannot hijack fixture tests.
  await page.goto(`/?event=${FIXTURE_EVENT}`);
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
  await expect(page.locator('body')).toHaveAttribute(
    'data-resolved-scope',
    new RegExp(`${FIXTURE_EVENT}:`),
    { timeout: 15_000 },
  );
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
        segments: [{ event_id: '1', phase: 'intro', name: 'Event 1 Intro' }],
      }),
    });
  });
}

interface O3Option {
  key: string;
  video_path: string;
  generation?: number;
  source?: string;
}

function makeO3Beat(
  beatId: string,
  opts: {
    options: O3Option[];
    status?: string;
    selectedPath?: string | null;
  },
) {
  return {
    beat_id: beatId,
    dialogue_text: `${beatId} dialogue for golden path.`,
    kling_o3_prompt: `@Image1 ${beatId} staging prompt.`,
    speaker: 'Arlo',
    status: 'ready',
    gpt_options: [],
    kling_o3_options: opts.options,
    kling_o3_status: opts.status ?? 'pending',
    kling_o3_video_path: opts.selectedPath ?? null,
  };
}

/** Stateful session mock — updates when select-o3-video fires. */
async function installSessionStateMock(
  page: Page,
  beatsRef: { beats: unknown[] },
): Promise<void> {
  await page.route('**/api/bg/session-state**', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        active_context: { arc_number: 1, event_id: '1', phase: 'intro' },
        scope_active_context: { arc_number: 1, event_id: '1', phase: 'intro' },
        beats: beatsRef.beats,
        flux_options_complete: false,
        capabilities: {},
        migration_warnings: [],
      }),
    });
  });
}

test.describe('BG_GOLDEN_PATH_V1 — Beat Gen operator chain', () => {
  test('GP.1 — session with beats shows cards (not bg-empty)', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    const beatsRef = {
      beats: [
        makeO3Beat('beat_gp_01', {
          options: [{
            key: 'opt_gp_a',
            video_path: '/fake/kling_o3_clips/beat_gp_01_g1_element.mp4',
            generation: 1,
            source: 'approved_kling_o3_video',
          }],
        }),
      ],
    };
    await installSessionStateMock(page, beatsRef);

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('pane-bg')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('bg-beat-card-0')).toBeVisible();
    await expect(page.getByTestId('bg-empty')).toHaveCount(0);
  });

  test('GP.2 — O3 tile click posts select-o3-video with scope keys', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    const videoPath = '/fake/kling_o3_clips/beat_gp_02_g1_element.mp4';
    const beatsRef = {
      beats: [
        makeO3Beat('beat_gp_02', {
          options: [{
            key: 'opt_gp_b',
            video_path: videoPath,
            generation: 1,
            source: 'approved_kling_o3_video',
          }],
        }),
      ],
    };
    await installSessionStateMock(page, beatsRef);

    const selectReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/bg/select-o3-video') && req.method() === 'POST') {
        selectReqs.push(req);
      }
    });

    await page.route('**/api/bg/select-o3-video', async (r) => {
      const body = JSON.parse(r.request().postData() ?? '{}');
      const beat = beatsRef.beats[0] as ReturnType<typeof makeO3Beat>;
      beat.kling_o3_status = 'approved';
      beat.kling_o3_video_path = videoPath;
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, beat_id: body.beat_id, option_key: body.option_key }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-options-row-0')).toBeVisible({ timeout: 5_000 });
    await page.getByTestId('bg-option-0-0').click();

    await expect.poll(() => selectReqs.length).toBeGreaterThanOrEqual(1);
    const body = JSON.parse(selectReqs[0]!.postData() ?? '{}');
    expect(body.beat_id).toBe('beat_gp_02');
    expect(body.option_key).toBe('opt_gp_b');
    expect(body.scope_event_id ?? body.event_id).toBeTruthy();
  });

  test('GP.3 — O3 selection persists after refresh (rehydrate regression)', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    const videoPath = '/fake/kling_o3_clips/beat_gp_03_g2_element.mp4';
    const beatsRef = {
      beats: [
        makeO3Beat('beat_gp_03', {
          options: [{
            key: 'opt_gp_c',
            video_path: videoPath,
            generation: 2,
            source: 'approved_kling_o3_video',
          }],
        }),
      ],
    };
    await installSessionStateMock(page, beatsRef);

    await page.route('**/api/bg/select-o3-video', async (r) => {
      const beat = beatsRef.beats[0] as ReturnType<typeof makeO3Beat>;
      beat.kling_o3_status = 'approved';
      beat.kling_o3_video_path = videoPath;
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    await page.getByTestId('bg-option-0-0').click();
    await expect(page.getByTestId('bg-option-0-0')).toHaveClass(/is-selected/);

    // Simulate poll/rehydrate: client refreshState re-fetches session-state.
    await page.goto(`/?event=${FIXTURE_EVENT}`);
    await page.click('[data-testid="tab-bg"]');
    await expect(page.getByTestId('bg-option-0-0')).toHaveClass(/is-selected/, { timeout: 5_000 });
  });

  test('GP.4 — all beats approved enables Send to Stitcher → export-to-stitcher', async ({ page }) => {
    await mockSnapshot(page);
    await mockSegments(page);
    const videoPath = '/fake/kling_o3_clips/beat_gp_04_g1_element.mp4';
    const beatsRef = {
      beats: [
        makeO3Beat('beat_gp_04', {
          options: [{
            key: 'opt_gp_d',
            video_path: videoPath,
            generation: 1,
            source: 'approved_kling_o3_video',
          }],
          status: 'approved',
          selectedPath: videoPath,
        }),
      ],
    };
    await installSessionStateMock(page, beatsRef);

    const exportReqs: Request[] = [];
    const preflightReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/bg/export-to-stitcher-preflight') && req.method() === 'GET') {
        preflightReqs.push(req);
      }
      if (req.url().includes('/api/bg/export-to-stitcher') && req.method() === 'POST') {
        exportReqs.push(req);
      }
    });

    await page.route('**/api/bg/export-to-stitcher-preflight**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          ready: true,
          slot_key: 'intro',
          beats: [{ beat_id: 'beat_gp_04', ready: true }],
        }),
      });
    });

    await page.route('**/api/bg/export-to-stitcher', async (r) => {
      await r.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, submitted: true, job_id: 'export-test-1', status: 'queued' }),
      });
    });

    await page.route('**/api/bg/poll-export-to-stitcher*', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          job_id: 'export-test-1',
          status: 'done',
          result: { ok: true, slot_key: 'intro', video_path: '/fake/stitch/intro.mp4' },
        }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-bg"]');
    const exportBtn = page.getByTestId('bg-export-stitcher-btn');
    await expect(exportBtn).toBeEnabled({ timeout: 5_000 });
    await exportBtn.click();

    await expect.poll(() => preflightReqs.length).toBeGreaterThanOrEqual(1);
    await expect.poll(() => exportReqs.length).toBeGreaterThanOrEqual(1);
    const body = JSON.parse(exportReqs[0]!.postData() ?? '{}');
    expect(body.slot_key).toBe('intro');
    expect(body.scope_event_id ?? body.event_id).toBeTruthy();
  });
});

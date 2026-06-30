// Phase E — operator hydrate markers (fixture server).
// FAST_AND_FLAWLESS_DONE_V1 FF-008

import { test, expect, type Page } from '@playwright/test';

const FIXTURE_EVENT = 'Event_e2e_fixture';

test.beforeEach(async ({ request }) => {
  await request.post(`${process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5200'}/api/event/load`, {
    data: { event_id: FIXTURE_EVENT },
  });
});

async function gotoApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function mockEventCurrent(page: Page): Promise<void> {
  await page.route('**/api/event/current**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, event_id: FIXTURE_EVENT, event_generation: 1 }),
    });
  });
}

test.describe('STITCH-AMBIENT-HYDRATE-1 — Stitcher ambient bed', () => {
  test('STITCH-AMBIENT-HYDRATE-1 — focus refresh with omitted server field keeps local bed', async ({
    page,
  }) => {
    const JOB = `${FIXTURE_EVENT}_stitch`;
    let omitBed = false;
    await mockEventCurrent(page);
    await page.route('**/api/state/snapshot', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/phase_b/ambient_preset_list**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [{ preset_id: 'forest' }, { preset_id: 'rain' }],
          count: 2,
        }),
      });
    });
    const slots = () => ({
      intro: {
        video_path: '/abs/path/intro.mp4',
        video_dur_ms: 30000,
        ambient_bed: omitBed ? '' : 'forest',
        sfx_cues: [],
      },
      phase_a: { video_path: '/abs/a.mp4', video_dur_ms: 30000, ambient_bed: '', sfx_cues: [] },
      phase_b: { video_path: '/abs/b.mp4', video_dur_ms: 30000, ambient_bed: '', sfx_cues: [] },
      resolution: { video_path: '/abs/r.mp4', video_dur_ms: 30000, ambient_bed: '', sfx_cues: [] },
    });
    await page.route('**/api/stitch_editor/jobs', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          jobs: [{ name: JOB, created_at: 0, updated_at: 0, slot_count: 4 }],
        }),
      });
    });
    await page.route(`**/api/stitch_editor/job/${JOB}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, name: JOB, job: { name: JOB, slots: slots(), transitions: [] } }),
      });
    });
    await page.route(/\/api\/stitch_editor\/job(?:\?|$)/, async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
      } else {
        await route.continue();
      }
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-stitcher"]');
    await expect(page.locator('[data-testid="stitcher-strip"]')).toBeVisible({ timeout: 15_000 });
    await page.locator('[data-testid="stitcher-multiphase-segment-intro"]').click();

    const select = page.locator('[data-testid="stitcher-amb-intro"]');
    await expect(select).toBeVisible({ timeout: 15_000 });
    await expect(select).toHaveValue('forest');
    await select.selectOption('rain');
    await expect(select).toHaveValue('rain');

    omitBed = true;
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('mn:server-rehydrate', { detail: { reason: 'test' } }));
    });
    await page.waitForTimeout(400);
    await expect(select).toHaveValue('rain');
  });
});

test.describe('SB-DIALOGUE-HYDRATE-1 — Storyboard dialogue', () => {
  test('SB-DIALOGUE-HYDRATE-1 — focus refresh with omitted server text keeps local edit', async ({
    page,
  }) => {
    let omitText = false;
    await mockEventCurrent(page);
    await page.route('**/api/v2/event/*/state', async (route) => {
      const beat: Record<string, unknown> = {
        speaker: 'Tessa',
        audio_file: 'audio/x.mp3',
        phase_1: { selected_option: 1, options: [{ file: 'a.mp4' }] },
      };
      if (!omitText) beat.text = 'Hello world';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: {
            intro: { video_role: 'intro', beats: { beat_h1: beat } },
            resolution: { video_role: 'resolution', beats: {} },
          },
        }),
      });
    });
    await page.route('**/api/state/snapshot', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.goto('/?tab=storyboard');
    await expect(page.locator('[data-testid="pane-storyboard"]')).toBeVisible({ timeout: 15_000 });
    const cell = page.locator('[data-testid="beat-text-0"]');
    await expect(cell).toBeVisible({ timeout: 10_000 });
    await cell.click();
    await cell.fill('Edited locally');
    omitText = true;
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('mn:server-rehydrate', { detail: { reason: 'test' } }));
    });
    await page.waitForTimeout(400);
    await expect(cell).toHaveText('Edited locally');
  });
});

test.describe('SB-TRIM-HYDRATE-1 — Storyboard trim fields', () => {
  test('SB-TRIM-HYDRATE-1 — focus refresh with omitted server trim keeps local front value', async ({
    page,
  }) => {
    let omitTrim = false;
    await mockEventCurrent(page);
    await page.route('**/api/v2/event/*/state', async (route) => {
      const phase1: Record<string, unknown> = {
        selected_option: 1,
        options: [{ file: 'a.mp4' }],
      };
      if (!omitTrim) phase1.trim_start = 0.5;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: {
            intro: {
              video_role: 'intro',
              beats: {
                beat_t1: {
                  speaker: 'Tessa',
                  text: 'Hi',
                  audio_file: 'audio/x.mp3',
                  phase_1: phase1,
                },
              },
            },
            resolution: { video_role: 'resolution', beats: {} },
          },
        }),
      });
    });
    await page.route('**/api/state/snapshot', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.goto('/?tab=storyboard');
    const trimFront = page.locator('[data-testid="beat-0-trim-front"]');
    await expect(trimFront).toBeVisible({ timeout: 15_000 });
    await trimFront.fill('2.75');
    await expect(trimFront).toHaveValue('2.75');
    omitTrim = true;
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('mn:server-rehydrate', { detail: { reason: 'test' } }));
    });
    await page.waitForTimeout(400);
    await expect(trimFront).toHaveValue('2.75');
  });
});

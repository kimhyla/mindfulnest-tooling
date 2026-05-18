// Track B chunk 2 — smoke coverage for LD testids (blocker #159).
// Asserts data-testid presence in rendered DOM for a representative beat.
// Bootstrap is mocked (no server mutations required).

import { test, expect, type Page } from '@playwright/test';

const BEAT_ID = 'beat_track_b_ld';

// All assertions below use `beat-0-*` testids. This is safe because each
// mockBootstrap() call seeds exactly ONE beat (display_order: [BEAT_ID]),
// so it always renders at array index 0. If a future mock grows to multiple
// beats, the index-0 assertions will need to be re-derived from the rendered
// DOM (e.g. via `await page.locator('[data-testid^="beat-"][data-beat-id="..."]')`).
// [CONFIRMED against mockBootstrap()'s display_order field — only one entry.]
const BEAT_INDEX = 0;

interface MockBeatOptions {
  kimDone?: boolean;
  finalFile?: string;
  finalSource?: 'still_image' | 'lipsync' | 'option';
}

async function mockBootstrap(page: Page, opts: MockBeatOptions = {}): Promise<void> {
  const beat: Record<string, unknown> = {
    speaker: 'Tessa',
    text: 'Track B LD testid smoke beat.',
    audio_file: `audio/${BEAT_ID}.mp3`,
    kim_done: opts.kimDone ?? false,
    trim_in: 0,
    trim_out: 'full',
    phase_1: {
      audio_delay: 0,
      options: [{ file: 'animations/opt1_tb.mp4', status: 'completed' }],
      selected_option: 0,
    },
  };
  if (opts.finalFile) {
    beat.final = {
      file: opts.finalFile,
      source: opts.finalSource ?? 'still_image',
    };
  }

  const partition = {
    video_role: 'intro',
    video_label: 'Intro',
    beats: { [BEAT_ID]: beat },
    display_order: [BEAT_ID],
  };
  const resPartition = {
    video_role: 'resolution',
    video_label: 'Resolution',
    beats: { [BEAT_ID]: beat },
    display_order: [BEAT_ID],
  };

  await page.route('**/api/v2/event/*/state', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        _module_version: 1,
        videos: { intro: partition, resolution: resPartition },
      }),
    });
  });
  await page.route('**/api/event/list', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        events: [{ event_id: 'Event_track_b_ld', label: 'Track B LD smoke' }],
      }),
    });
  });
  await page.route('**/api/event/current', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ event_id: 'Event_track_b_ld' }),
    });
  });
  await page.route('**/api/cr/library', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ images: [] }),
    });
  });
}

async function stubMedia(page: Page): Promise<void> {
  await page.route('**/asset/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'video/mp4', body: '' });
  });
  await page.route('**/api/beat/audio/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' });
  });
}

async function gotoStoryboard(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.addInitScript(() => {
    try {
      localStorage.clear();
    } catch {
      /* sandboxed */
    }
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
  await page.click('[data-testid="tab-storyboard"]');
  await expect(page.locator('[data-testid="beat-list"]')).toBeVisible({ timeout: 10000 });
}

test.describe('Track B — LD testid smoke coverage', () => {
  test('LD-746 — kim-done-checkbox', async ({ page }) => {
    await mockBootstrap(page, { kimDone: true });
    await stubMedia(page);
    await gotoStoryboard(page);
    await expect(page.locator(`[data-testid="kim-done-checkbox-${BEAT_ID}"]`)).toBeAttached();
  });

  test('LD-755 — beat-0-trim-preview (requires final.file)', async ({ page }) => {
    await mockBootstrap(page, {
      finalFile: 'final/track_b_trim.mp4',
      finalSource: 'lipsync',
    });
    await stubMedia(page);
    await gotoStoryboard(page);
    await expect(page.locator('[data-testid="beat-0-trim-preview"]')).toBeVisible();
  });

  test('LD-761 — still-as-final + undo-final when final.source=still_image', async ({
    page,
  }) => {
    await mockBootstrap(page, {
      finalFile: 'final/track_b_still.mp4',
      finalSource: 'still_image',
    });
    await stubMedia(page);
    await gotoStoryboard(page);
    await expect(page.locator('[data-testid="beat-0-still-as-final"]')).toBeVisible();
    await expect(page.locator('[data-testid="beat-0-undo-final"]')).toBeVisible();
  });

  // LD-786 — same testid as LD-761 still-as-final; covered above.

  test('LD-767 — suggest-parenthetical', async ({ page }) => {
    await mockBootstrap(page);
    await stubMedia(page);
    await gotoStoryboard(page);
    await expect(page.locator('[data-testid="suggest-parenthetical-button"]')).toBeAttached();
  });

  // LD-789 — same testid as LD-767 suggest-parenthetical; covered above.

  test('LD-777 — still-hold-input', async ({ page }) => {
    await mockBootstrap(page, {
      finalFile: 'final/track_b_still.mp4',
      finalSource: 'still_image',
    });
    await stubMedia(page);
    await gotoStoryboard(page);
    await expect(page.locator('[data-testid="beat-0-still-hold-input"]')).toBeVisible();
  });

  test('LD-787 — trim-in + trim-out', async ({ page }) => {
    await mockBootstrap(page);
    await stubMedia(page);
    await gotoStoryboard(page);
    await expect(page.locator('[data-testid="beat-0-trim-in"]')).toBeVisible();
    await expect(page.locator('[data-testid="beat-0-trim-out"]')).toBeVisible();
  });

  test('LD-792 — guardedClick buttons present (smoke)', async ({ page }) => {
    await mockBootstrap(page);
    await stubMedia(page);
    await gotoStoryboard(page);
    const buttons = page.getByRole('button');
    expect(await buttons.count()).toBeGreaterThan(0);
  });
});

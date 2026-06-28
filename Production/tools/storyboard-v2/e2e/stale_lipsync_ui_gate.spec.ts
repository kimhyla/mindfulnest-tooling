// Stale-Lipsync UI Gate — F-STALE-LIPSYNC-UI-001 (blocker 149)
//
// LD: STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1
//
// Bug surface (DS-22 confirmed against beat_08 on 2026-05-17):
//   - beat_08_lipsync.mp4 mtime = April 18 2026 (~month old, 4.2s)
//   - audio_regenerated_at = 2026-05-17 (today)
//   - audio_duration_s = 9.447s (current text)
//   - lipsync.audio_changed flag was never written (silent freshness miss)
//
// The ▶ lipsync play button at StoryboardTab.tsx L515 gates on
// `beat.lipsync?.status === 'completed' && beat.lipsync?.file` — file
// existence ONLY, no freshness vs current audio. That makes Kim hit
// PLAY and hear month-old 4.2s phrase while the storyboard claims the
// beat is at 9.68s.
//
// Fix contract:
//   1. Server `_handle_v2_event_state` (production_server.py L15779)
//      computes `lipsync.file_mtime` (epoch seconds) for each beat whose
//      lipsync.file exists, and projects it into the bootstrap response.
//      Backwards-compat: field is additive — older clients ignore it.
//   2. Client gates the ▶ lipsync button on freshness:
//        fresh  if lipsync.file_mtime >= parse(audio_regenerated_at)
//        stale  otherwise
//      Stale renders the button in a DISABLED state with text
//      "⚠ stale lipsync — re-run" (audit-visible degradation per
//      Rule 19 — not a silent hide).
//   3. Missing file_mtime from server → treat as STALE (defensive
//      default). This protects against servers that haven't deployed
//      the additive field yet.
//   4. File absent or status != completed → button hidden as today
//      (regression guard).
//
// Tests (RED):
//   T-1 fresh    — lipsync_file_mtime > audio_regenerated_at → enabled play button
//   T-2 stale    — lipsync_file_mtime < audio_regenerated_at → disabled stale button
//   T-3 absent   — lipsync.file undefined → button hidden (regression guard)
//   T-4 missing  — lipsync.file_mtime missing → disabled stale button (defensive default)

import { test, expect, type Page } from '@playwright/test';
import { openStoryboardPane } from './helpers';

interface MockLipsyncBeatOptions {
  lipsyncFileMtime?: number | null;   // epoch SECONDS; undefined→omit key; null→explicit null
  audioRegeneratedAt: string;          // ISO8601
  withLipsyncFile?: boolean;           // default true
  withCompletedStatus?: boolean;       // default true
}

async function mockBootstrap(
  page: Page,
  opts: MockLipsyncBeatOptions,
  beatId = 'beat_sl_01',
): Promise<void> {
  const withLipsyncFile = opts.withLipsyncFile !== false;
  const withCompletedStatus = opts.withCompletedStatus !== false;

  const lipsync: Record<string, unknown> = {};
  if (withCompletedStatus) lipsync.status = 'completed';
  if (withLipsyncFile) lipsync.file = `lipsync/${beatId}_ls.mp4`;
  if (opts.lipsyncFileMtime !== undefined) {
    lipsync.file_mtime = opts.lipsyncFileMtime;
  }

  const beat: Record<string, unknown> = {
    speaker: 'Tessa',
    text: 'Stale-lipsync regression beat.',
    audio_file: `audio/${beatId}.mp3`,
    audio_regenerated_at: opts.audioRegeneratedAt,
    audio_duration_s: 9.447,
    // phase_1 with selected option — lifecycle becomes 'selected' so the
    // generic lipsync-play sentinel branch is hit (gated only on
    // lipsync.status === 'completed' + lipsync.file at SUT L515).
    phase_1: {
      audio_delay: 0,
      options: [{ file: 'animations/opt1_sl.mp4', status: 'completed' }],
      selected_option: 0,
    },
  };
  if (Object.keys(lipsync).length > 0) {
    beat.lipsync = lipsync;
  }

  // Bootstrap — populate BOTH intro and resolution partitions with the
  // beat so whichever role the storyboard activates renders it. Default
  // `activeTargetVideo` is 'intro' (scope.ts L56) but localStorage and
  // legacy session state can flip it to 'resolution'.
  const partition = {
    video_role: 'intro',
    video_label: 'Intro',
    beats: { [beatId]: beat },
    display_order: [beatId],
  };
  const resPartition = {
    video_role: 'resolution',
    video_label: 'Resolution',
    beats: { [beatId]: beat },
    display_order: [beatId],
  };
  await page.route('**/api/v2/event/*/state', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        _module_version: 1,
        videos: {
          intro: partition,
          resolution: resPartition,
        },
      }),
    });
  });
  // /api/event/list and /api/event/current — return our synthetic
  // event so the dropdowns don't fall back to localStorage Event_1.
  await page.route('**/api/event/list', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        events: [{ event_id: 'Event_stale_lipsync', label: 'Stale-lipsync test' }],
      }),
    });
  });
  await page.route('**/api/event/current', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ event_id: 'Event_stale_lipsync' }),
    });
  });
}

async function stubMediaEndpoints(page: Page): Promise<void> {
  await page.route('**/asset/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'video/mp4', body: '' });
  });
  await page.route('**/api/beat/audio/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'audio/mpeg', body: '' });
  });
}

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  // Pre-clear localStorage so stale `activeTargetVideo` / `event_id`
  // from a prior session can't override our mocked event.
  await page.addInitScript(() => {
    try { localStorage.clear(); } catch { /* sandboxed contexts */ }
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

test.describe('Stale-Lipsync UI Gate — F-STALE-LIPSYNC-UI-001', () => {
  test('T-1 FRESH — file_mtime > audio_regenerated_at → enabled play button', async ({ page }) => {
    // audio regen at 2026-05-01; lipsync file rendered at 2026-05-10 → FRESH
    const audioRegen = '2026-05-01T12:00:00+00:00';
    const lipsyncMtime = Math.floor(new Date('2026-05-10T12:00:00Z').getTime() / 1000);
    await mockBootstrap(page, {
      audioRegeneratedAt: audioRegen,
      lipsyncFileMtime: lipsyncMtime,
    });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await openStoryboardPane(page);

    const playBtn = page.locator('[data-testid="beat-0-lipsync-play"]');
    await expect(playBtn).toBeVisible();
    await expect(playBtn).toBeEnabled();
    await expect(playBtn).toContainText('lipsync');
    // Fresh button does NOT carry the stale marker.
    await expect(playBtn).not.toContainText('stale');
  });

  test('T-2 STALE — file_mtime < audio_regenerated_at → enabled stale button (BUG-C: still playable)', async ({ page }) => {
    // Mirrors beat_08: lipsync rendered April 18, audio regenerated May 17.
    const audioRegen = '2026-05-17T03:19:59+00:00';
    const lipsyncMtime = Math.floor(new Date('2026-04-18T12:00:00Z').getTime() / 1000);
    await mockBootstrap(page, {
      audioRegeneratedAt: audioRegen,
      lipsyncFileMtime: lipsyncMtime,
    });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await openStoryboardPane(page);

    const playBtn = page.locator('[data-testid="beat-0-lipsync-play"]');
    // BUG-C fix (Kim 2026-05-20): stale lipsync must STILL be playable so
    // Kim can review prior work. Stale affects only the LABEL and class
    // (mn-btn-stale), NOT the disabled state. Audit-visible via text label.
    // StoryboardTab.tsx BUG-C comment: "Stale only affects the LABEL (warning
    // prefix), not the disabled state."
    await expect(playBtn).toBeVisible();
    await expect(playBtn).toBeEnabled();
    await expect(playBtn).toContainText('stale');
    await expect(playBtn).toHaveAttribute('data-stale', 'true');
  });

  test('T-3 ABSENT — lipsync.file undefined → button hidden (regression guard)', async ({ page }) => {
    await mockBootstrap(page, {
      audioRegeneratedAt: '2026-05-17T03:19:59+00:00',
      lipsyncFileMtime: undefined,
      withLipsyncFile: false,
    });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await openStoryboardPane(page);

    const playBtn = page.locator('[data-testid="beat-0-lipsync-play"]');
    await expect(playBtn).toHaveCount(0);
  });

  test('T-4 MISSING — file_mtime missing → enabled stale button (BUG-C: still playable, defensive default)', async ({ page }) => {
    // Server returned lipsync.file but no file_mtime — older server, or
    // file disappeared mid-render. Treat as stale (safe default per Rule 19).
    // Per BUG-C (Kim 2026-05-20): stale = enabled-but-labelled, not disabled.
    await mockBootstrap(page, {
      audioRegeneratedAt: '2026-05-17T03:19:59+00:00',
      lipsyncFileMtime: undefined, // key omitted from response
    });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await openStoryboardPane(page);

    const playBtn = page.locator('[data-testid="beat-0-lipsync-play"]');
    await expect(playBtn).toBeVisible();
    await expect(playBtn).toBeEnabled();
    await expect(playBtn).toContainText('stale');
    await expect(playBtn).toHaveAttribute('data-stale', 'true');
  });
});

// Phase A/B waveform ▶ Play durability — regression gates for keep-alive + seek collision.
//
// Root causes this file prevents (2026-06-12):
//   1. ▶ Play inside seek wrapper → pointerdown seeks before play() → AbortError swallowed
//   2. async await ws.play() before user gesture expires
//   3. pauseOtherWaveformPlayback pausing self (unstable bus control identity)
//   4. render-time effect() calling stopAllPhasePlayback on every App re-render
//
// Enforced by: this spec (CI), check_storyboard_critical_features.sh markers,
// WaveformTimeline.tsx header comment block.

import { test, expect, type Page } from '@playwright/test';

const FIXTURE_EVENT = 'Event_e2e_fixture';

test.beforeEach(async ({ request }) => {
  await request.post('http://localhost:5111/api/event/load', {
    data: { event_id: FIXTURE_EVENT },
  });
});

function silentWavBytes(durationS: number, sampleRate: number = 8000): Buffer {
  const numSamples = Math.floor(durationS * sampleRate);
  const dataSize = numSamples * 2;
  const buf = Buffer.alloc(44 + dataSize);
  buf.write('RIFF', 0);
  buf.writeUInt32LE(36 + dataSize, 4);
  buf.write('WAVE', 8);
  buf.write('fmt ', 12);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(sampleRate, 24);
  buf.writeUInt32LE(sampleRate * 2, 28);
  buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write('data', 36);
  buf.writeUInt32LE(dataSize, 40);
  return buf;
}

async function gotoApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function mockAudioFiles(page: Page, durationS: number = 30): Promise<void> {
  await page.route(/\/files\?path=.*\.(mp3|mp4|wav|m4a|ogg)/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: silentWavBytes(durationS, 8000),
    });
  });
}

async function mockPhaseState(
  page: Page,
  patch: Record<string, unknown>,
): Promise<void> {
  await page.route(`**/api/v2/event/${FIXTURE_EVENT}/state**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, beats: {}, ...patch }),
    });
  });
}

async function openPhaseB(page: Page): Promise<void> {
  await page.click('[data-testid="tab-phase-b"]');
  await expect(page.locator('[data-testid="pane-phase-b-keepalive"]')).toBeVisible();
  await expect(page.locator('[data-testid="phase-producer-b"]')).toBeVisible();
}

async function openPhaseA(page: Page): Promise<void> {
  await page.click('[data-testid="tab-phase-a"]');
  await expect(page.locator('[data-testid="pane-phase-a-keepalive"]')).toBeVisible();
  await expect(page.locator('[data-testid="phase-producer-a"]')).toBeVisible();
}

async function waitForWaveformReady(page: Page, phase: 'a' | 'b' = 'b') {
  const waveform = page.locator(
    `[data-testid="pane-phase-${phase}-keepalive"] [data-testid="waveform-timeline"]`,
  );
  await expect(waveform).toBeVisible();
  await expect.poll(async () => {
    const v = await waveform.getAttribute('data-loaded-duration-ms');
    return v ? Number(v) : 0;
  }, { timeout: 15_000 }).toBeGreaterThan(0);
  return waveform;
}

test.describe('PHASE_WAVEFORM_PLAY — keep-alive + playback bus markers', () => {
  test('PLAY-0 — keep-alive panes + Stop audio header control present', async ({ page }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, { phase_b_lipsync_file: 'fix_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseB(page);

    await expect(page.locator('[data-testid="pane-phase-a-keepalive"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="pane-phase-b-keepalive"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="stop-all-audio-btn"]')).toBeVisible();
  });
});

test.describe('PHASE_WAVEFORM_PLAY — ▶ Play must not seek-collide', () => {
  test('PLAY-1 — ▶ Play toggles to Pause and time advances', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_b_lipsync_file: 'fix_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await expect(playBtn).toBeEnabled();
    await expect(playBtn).toHaveText(/▶ Play/);

    await playBtn.click();

    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-current-time-ms');
      return v ? Number(v) : 0;
    }, { timeout: 3_000 }).toBeGreaterThan(200);
  });

  test('PLAY-2 — ▶ Play from t≈0 does not seek-jump (seek/play collision regression)', async ({
    page,
  }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_b_lipsync_file: 'fix_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const canvas = waveform.locator('.mn-waveform-canvas');
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();

    // Park playhead at start via canvas seek (not the Play button).
    await canvas.click({ position: { x: 2, y: box!.height / 2 } });
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-current-time-ms');
      return v ? Number(v) : 0;
    }).toBeLessThan(1500);

    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();

    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });

    // If pointerdown seek fires on Play click, playhead jumps to button's X (~3–15% of
    // timeline) BEFORE playback — often >2500ms on a 30s file. Playing from 0 for
    // ~500ms should stay well under that.
    await page.waitForTimeout(500);
    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeLessThan(2500);
    expect(ms).toBeGreaterThan(50);
  });

  test('PLAY-3 — ⏸ Pause stops playback (no audioprocess restart loop)', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_b_lipsync_file: 'fix_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();
    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });

    await page.waitForTimeout(400);
    const msBeforePause = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(msBeforePause).toBeGreaterThan(100);

    await playBtn.click();
    await expect(playBtn).toHaveText(/▶ Play/, { timeout: 3_000 });

    await page.waitForTimeout(600);
    const msAfterPause = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(msAfterPause - msBeforePause).toBeLessThan(150);
  });
});

test.describe('PHASE_WAVEFORM_PLAY — Phase A parity (same WaveformTimeline + bus)', () => {
  test('PLAY-A1 — Phase A ▶ Play toggles without seek-jump', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_a_lipsync_file: 'fix_phase_a_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseA(page);

    const waveform = await waitForWaveformReady(page, 'a');
    const canvas = waveform.locator('.mn-waveform-canvas');
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();

    await canvas.click({ position: { x: 2, y: box!.height / 2 } });
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-current-time-ms');
      return v ? Number(v) : 0;
    }).toBeLessThan(1500);

    const playBtn = page.locator(
      '[data-testid="pane-phase-a-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();

    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await page.waitForTimeout(500);
    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeLessThan(2500);
    expect(ms).toBeGreaterThan(50);
  });

  test('PLAY-A2 — Phase A Preview with Overlay starts playback status', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, {
      phase_a_lipsync_file: 'fix_phase_a_lipsync.mp4',
      phase_a_watercolor_cues_json: JSON.stringify([
        {
          id: 'cue_test',
          key: 'hands_rubbing_animated_test',
          timestamp_ms: 1000,
          duration_ms: 5000,
          cue_type: 'video',
        },
      ]),
    });
    await page.route('**/api/phase/watercolor_list**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [
            {
              key: 'hands_rubbing_animated_test',
              filename: 'hands_rubbing_animated_test.mp4',
              ext: 'mp4',
              kind: 'animation',
              thumb_url: 'http://localhost:5111/api/phase/watercolor_file?key=hands_rubbing',
              animation_url:
                'http://localhost:5111/api/phase_b/watercolor/hands_rubbing_animated_test',
              mtime: 1,
              size_bytes: 1000,
            },
          ],
        }),
      });
    });
    await gotoApp(page);
    await openPhaseA(page);
    await waitForWaveformReady(page, 'a');

    await page.locator('[data-testid="phase-a-preview-overlay-btn"]').click();
    await expect(page.locator('[data-testid="phase-a-status"]')).toContainText('Previewing', {
      timeout: 5_000,
    });
    await expect(
      page.locator('[data-testid="pane-phase-a-keepalive"] [data-testid="waveform-play-btn"]'),
    ).toHaveText(/⏸ Pause/, { timeout: 3_000 });
  });
});

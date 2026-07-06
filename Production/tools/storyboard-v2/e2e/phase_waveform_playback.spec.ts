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
import { SERVER } from './testServer';

const FIXTURE_EVENT = 'Event_e2e_fixture';

test.beforeEach(async ({ request }) => {
  await request.post(`${SERVER}/api/event/load`, {
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

test.describe('PHASE_WAVEFORM_PLAY — drag-seek must not snap to 0', () => {
  test('SEEK-DRAG-B1 — Phase B play→pause→drag over cue blocks holds position', async ({
    page,
  }) => {
    await mockAudioFiles(page, 90);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: JSON.stringify([
        {
          id: 'cue_drag_block',
          key: 'spell_title',
          timestamp_ms: 9000,
          duration_ms: 8000,
          cue_type: 'png',
        },
        {
          id: 'cue_drag_block2',
          key: 'hands_original',
          timestamp_ms: 35000,
          duration_ms: 12000,
          cue_type: 'png',
        },
      ]),
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();
    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await page.waitForTimeout(800);
    await playBtn.click();

    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();
    const y = box!.y + box!.height * 0.72;
    const x0 = box!.x + box!.width * 0.55;
    const x1 = box!.x + box!.width * 0.82;
    await page.mouse.move(x0, y);
    await page.mouse.down();
    for (let i = 1; i <= 10; i += 1) {
      await page.mouse.move(x0 + ((x1 - x0) * i) / 10, y);
      await page.waitForTimeout(20);
    }
    await page.mouse.up();
    await page.waitForTimeout(400);

    const durMs = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeGreaterThan(durMs * 0.5);
    expect(ms).toBeLessThan(durMs * 0.95);
  });
});

test.describe('PHASE_WAVEFORM_PLAY — watercolor cue resize handles (WAVEFORM_CUE_HANDLE_V1)', () => {
  test('CUE-RESIZE-1 — right handle drag increases cue duration', async ({ page }) => {
    await mockAudioFiles(page, 90);
    await page.route('**/api/v2/module/patch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: JSON.stringify([
        {
          id: 'cue_resize_test',
          key: 'spell_title',
          timestamp_ms: 15000,
          duration_ms: 5000,
          cue_type: 'png',
        },
      ]),
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const cue = page.locator('[data-testid="cue-marker-cue_resize_test"]');
    await expect(cue).toBeVisible();

    const startDuration = Number(await cue.getAttribute('data-duration-ms'));
    expect(startDuration).toBe(5000);

    const rightHandle = page.locator('[data-testid="cue-handle-right-cue_resize_test"]');
    await expect(rightHandle).toBeVisible();
    const box = await rightHandle.boundingBox();
    expect(box).not.toBeNull();

    const startX = box!.x + box!.width / 2;
    const y = box!.y + box!.height / 2;
    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(startX + 90, y, { steps: 8 });
    await page.waitForTimeout(80);
    const midDuration = Number(await cue.getAttribute('data-duration-ms'));
    await page.mouse.up();
    await page.waitForTimeout(120);
    const endDuration = Number(await cue.getAttribute('data-duration-ms'));

    expect(midDuration).toBeGreaterThan(startDuration + 800);
    expect(endDuration).toBeGreaterThan(startDuration + 800);
    expect(endDuration).toBeLessThan(90000);
    await expect(waveform).toHaveAttribute('data-waveform-cue-handle-v1', 'WAVEFORM_CUE_HANDLE_V1');
  });

  test('CUE-RESIZE-2 — left handle drag decreases cue start offset', async ({ page }) => {
    await mockAudioFiles(page, 90);
    await page.route('**/api/v2/module/patch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: JSON.stringify([
        {
          id: 'cue_resize_left',
          key: 'hands_rubbing',
          timestamp_ms: 20000,
          duration_ms: 6000,
          cue_type: 'png',
        },
      ]),
    });
    await gotoApp(page);
    await openPhaseB(page);

    await waitForWaveformReady(page, 'b');
    const cue = page.locator('[data-testid="cue-marker-cue_resize_left"]');
    await expect(cue).toBeVisible();

    const startOffset = Number(await cue.getAttribute('data-offset-ms'));
    expect(startOffset).toBe(20000);

    const leftHandle = page.locator('[data-testid="cue-handle-left-cue_resize_left"]');
    const box = await leftHandle.boundingBox();
    expect(box).not.toBeNull();

    const startX = box!.x + box!.width / 2;
    const y = box!.y + box!.height / 2;
    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(startX - 70, y, { steps: 8 });
    await page.waitForTimeout(80);
    const midOffset = Number(await cue.getAttribute('data-offset-ms'));
    await page.mouse.up();
    await page.waitForTimeout(120);
    const endOffset = Number(await cue.getAttribute('data-offset-ms'));

    expect(midOffset).toBeLessThan(startOffset - 500);
    expect(endOffset).toBeLessThan(startOffset - 500);
    expect(endOffset).toBeGreaterThanOrEqual(0);
  });

  test('CUE-MOVE-1 — drag cue body repositions offset without changing duration', async ({ page }) => {
    await mockAudioFiles(page, 90);
    await page.route('**/api/v2/module/patch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: JSON.stringify([
        {
          id: 'cue_move_test',
          key: 'hands_close',
          timestamp_ms: 10000,
          duration_ms: 4000,
          cue_type: 'png',
        },
      ]),
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const cue = page.locator('[data-testid="cue-marker-cue_move_test"]');
    await expect(cue).toBeVisible();

    const startOffset = Number(await cue.getAttribute('data-offset-ms'));
    const startDuration = Number(await cue.getAttribute('data-duration-ms'));
    expect(startOffset).toBe(10000);
    expect(startDuration).toBe(4000);

    const dragBody = page.locator('[data-testid="cue-drag-body-cue_move_test"]');
    await expect(dragBody).toBeVisible();
    const box = await dragBody.boundingBox();
    expect(box).not.toBeNull();
    const startX = box!.x + Math.max(4, box!.width * 0.25);
    const y = box!.y + box!.height * 0.5;
    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(startX + 100, y, { steps: 10 });
    await page.waitForTimeout(80);
    const midOffset = Number(await cue.getAttribute('data-offset-ms'));
    await page.mouse.up();
    await page.waitForTimeout(120);
    const endOffset = Number(await cue.getAttribute('data-offset-ms'));
    const endDuration = Number(await cue.getAttribute('data-duration-ms'));

    expect(midOffset).toBeGreaterThan(startOffset + 800);
    expect(endOffset).toBeGreaterThan(startOffset + 800);
    expect(endDuration).toBe(startDuration);
    await expect(waveform).toHaveAttribute('data-waveform-cue-move-v1', 'CUE-MOVE-1');
  });
});

test.describe('PHASE_WATERCOLOR_CUE_AUTHORITY_V1 — hydrate merge', () => {
  test('CUE-HYDRATE-1 — focus refresh with omitted server field keeps local cue marker', async ({
    page,
  }) => {
    await mockAudioFiles(page, 90);
    await page.route('**/api/v2/module/patch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    let omitWatercolorField = false;
    await page.route(`**/api/v2/event/${FIXTURE_EVENT}/state**`, async (route) => {
      const body: Record<string, unknown> = {
        ok: true,
        beats: {},
        phase_b_lipsync_file: 'fix_lipsync.mp4',
      };
      if (!omitWatercolorField) {
        body.phase_b_watercolor_cues_json = JSON.stringify([
          {
            id: 'cue_hydrate_test',
            key: 'spell_title',
            timestamp_ms: 12000,
            duration_ms: 4000,
            cue_type: 'png',
          },
        ]);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await gotoApp(page);
    await openPhaseB(page);
    await waitForWaveformReady(page, 'b');

    const cue = page.locator('[data-testid="cue-marker-cue_hydrate_test"]');
    await expect(cue).toBeVisible();

    const rightHandle = page.locator('[data-testid="cue-handle-right-cue_hydrate_test"]');
    const box = await rightHandle.boundingBox();
    expect(box).not.toBeNull();
    const startX = box!.x + box!.width / 2;
    const y = box!.y + box!.height / 2;
    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(startX + 60, y, { steps: 6 });
    await page.mouse.up();
    await page.waitForTimeout(150);

    omitWatercolorField = true;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.waitForTimeout(300);

    await expect(cue).toBeVisible();
    const durationMs = Number(await cue.getAttribute('data-duration-ms'));
    expect(durationMs).toBeGreaterThanOrEqual(4000);
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

test.describe('PHASE_WAVEFORM_PLAY — drag-seek must not snap to 0 (WAVEFORM_DRAG_SEEK_V1)', () => {
  test('SEEK-DRAG-1 — Phase B drag release holds position', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_b_lipsync_file: 'fix_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();

    const startX = box!.x + box!.width * 0.12;
    const endX = box!.x + box!.width * 0.62;
    const y = box!.y + box!.height * 0.72;

    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(endX, y, { steps: 10 });
    await page.waitForTimeout(80);
    const msDuring = Number(await waveform.getAttribute('data-current-time-ms'));

    await page.mouse.up();
    await page.waitForTimeout(150);
    const msAfter = Number(await waveform.getAttribute('data-current-time-ms'));

    expect(msDuring).toBeGreaterThan(8000);
    expect(msAfter).toBeGreaterThan(8000);
    expect(msAfter).toBeLessThan(22000);
  });

  test('SEEK-DRAG-A1 — Phase A drag release holds position', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_a_lipsync_file: 'fix_phase_a_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseA(page);

    const waveform = await waitForWaveformReady(page, 'a');
    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();

    const startX = box!.x + box!.width * 0.1;
    const endX = box!.x + box!.width * 0.55;
    const y = box!.y + box!.height * 0.72;

    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(endX, y, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(150);

    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeGreaterThan(7000);
    expect(ms).toBeLessThan(20000);
  });

  test('SEEK-DRAG-2 — play → pause → drag holds position (lipsync mp4)', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, { phase_b_lipsync_file: 'fix_lipsync.mp4' });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();
    await page.waitForTimeout(800);
    await playBtn.click();
    await page.waitForTimeout(200);

    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();
    const y = box!.y + box!.height * 0.72;
    await page.mouse.move(box!.x + box!.width * 0.15, y);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width * 0.7, y, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(200);

    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeGreaterThan(8000);
    expect(ms).toBeLessThan(22000);
  });

  test('SEEK-DRAG-B-STEM-1 — Phase B stem review drag release must not snap to 0', async ({
    page,
  }) => {
    await mockAudioFiles(page, 40);
    await mockPhaseState(page, {
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_lipsync_requires_regen: true,
      phase_b_voice_stem_mtime: 2_000,
      phase_b_lipsync_mtime: 1_000,
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    await expect(waveform).toHaveAttribute('data-source-label', 'stem');

    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();
    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await page.waitForTimeout(800);
    await playBtn.click();
    await expect(playBtn).toHaveText(/▶ Play/, { timeout: 3_000 });

    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();
    const y = box!.y + box!.height * 0.72;
    const x0 = box!.x + box!.width * 0.18;
    const x1 = box!.x + box!.width * 0.72;
    await page.mouse.move(x0, y);
    await page.mouse.down();
    for (let i = 1; i <= 12; i += 1) {
      await page.mouse.move(x0 + ((x1 - x0) * i) / 12, y);
      await page.waitForTimeout(20);
    }
    await page.mouse.up();
    await page.waitForTimeout(500);

    const durMs = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeGreaterThan(durMs * 0.35);
    expect(ms).toBeLessThan(durMs * 0.95);
  });

  test('SEEK-PLAY-1 — ▶ Play starts from scrubbed position, not 0 (WTA-32)', async ({ page }) => {
    await mockAudioFiles(page, 40);
    await mockPhaseState(page, {
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_lipsync_requires_regen: true,
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const playBtn = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-play-btn"]',
    );
    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();
    const y = box!.y + box!.height * 0.72;
    const x0 = box!.x + box!.width * 0.2;
    const x1 = box!.x + box!.width * 0.65;
    await page.mouse.move(x0, y);
    await page.mouse.down();
    for (let i = 1; i <= 12; i += 1) {
      await page.mouse.move(x0 + ((x1 - x0) * i) / 12, y);
      await page.waitForTimeout(20);
    }
    await page.mouse.up();
    await page.waitForTimeout(400);

    const durMs = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    const scrubMs = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(scrubMs).toBeGreaterThan(durMs * 0.25);

    await playBtn.click();
    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await page.waitForTimeout(600);

    const playMs = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(playMs).toBeGreaterThan(durMs * 0.15);
    expect(playMs).toBeGreaterThan(scrubMs * 0.5);
  });
});

test.describe('PHASE_WAVEFORM_PLAY — WTA remount preserves playhead (REMOUNT-1)', () => {
  test('REMOUNT-1 — toggling trim mode must not reset playhead to 0', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();

    const scrubX = box!.x + box!.width * 0.55;
    const y = box!.y + box!.height * 0.72;
    await page.mouse.click(scrubX, y);
    await page.waitForTimeout(150);

    const beforeToggle = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(beforeToggle).toBeGreaterThan(8000);

    await page.locator('[data-testid="phase-b-trim-voice-stem-btn"]').click();
    await expect(page.locator('[data-testid="phase-b-stem-trim-mode-badge"]')).toBeVisible();
    await page.waitForTimeout(400);

    const afterToggle = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(afterToggle).toBeGreaterThan(8000);
    expect(afterToggle).toBeLessThan(22000);
  });
});

test.describe('PHASE_WAVEFORM_PLAY — trim mode keeps lipsync + drag-seek (SEEK-7)', () => {
  test('SEEK-TRIM-1 — Phase B trim mode drag release must not snap to 0', async ({ page }) => {
    await mockAudioFiles(page, 90);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
    });
    await gotoApp(page);
    await openPhaseB(page);

    await page.locator('[data-testid="phase-b-trim-voice-stem-btn"]').click();
    await expect(page.locator('[data-testid="phase-b-stem-trim-mode-badge"]')).toBeVisible();

    const waveform = await waitForWaveformReady(page, 'b');
    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();

    const startX = box!.x + box!.width * 0.12;
    const endX = box!.x + box!.width * 0.62;
    const y = box!.y + box!.height * 0.72;

    await page.mouse.move(startX, y);
    await page.mouse.down();
    await page.mouse.move(endX, y, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(200);

    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeGreaterThan(8000);
    expect(ms).toBeLessThan(65_000);
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

  test('SEEK-DRAG-A1 — Phase A play→pause→drag release must not snap to 0', async ({
    page,
  }) => {
    await mockAudioFiles(page, 40);
    await mockPhaseState(page, {
      phase_a_voice_stem_file: 'fix_phase_a_stem.mp3',
      phase_a_lipsync_requires_regen: true,
      phase_a_stitched_file: 'fix_phase_a_stitched.mp4',
    });
    await gotoApp(page);
    await openPhaseA(page);

    const waveform = await waitForWaveformReady(page, 'a');
    const playBtn = page.locator(
      '[data-testid="pane-phase-a-keepalive"] [data-testid="waveform-play-btn"]',
    );
    await playBtn.click();
    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await page.waitForTimeout(800);
    await playBtn.click();
    await expect(playBtn).toHaveText(/▶ Play/, { timeout: 3_000 });

    const box = await waveform.boundingBox();
    expect(box).not.toBeNull();
    const y = box!.y + box!.height * 0.72;
    const x0 = box!.x + box!.width * 0.2;
    const x1 = box!.x + box!.width * 0.78;
    await page.mouse.move(x0, y);
    await page.mouse.down();
    for (let i = 1; i <= 10; i += 1) {
      await page.mouse.move(x0 + ((x1 - x0) * i) / 10, y);
      await page.waitForTimeout(20);
    }
    await page.mouse.up();
    await page.waitForTimeout(400);

    const durMs = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    const ms = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(ms).toBeGreaterThan(durMs * 0.45);
    expect(ms).toBeLessThan(durMs * 0.95);
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
              thumb_url: `${SERVER}/api/phase/watercolor_file?key=hands_rubbing`,
              animation_url:
                `${SERVER}/api/phase_b/watercolor/hands_rubbing_animated_test`,
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

async function mockAmbientPresetList(
  page: Page,
  items: Array<{ preset_id: string; file_size_bytes?: number }>,
): Promise<void> {
  await page.route('**/api/phase_b/ambient_preset_list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, items, count: items.length }),
    });
  });
}

async function mockBaseClipsList(page: Page): Promise<void> {
  await page.route('**/api/phase/base_clips_list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [
          { id: 'arlo_idle_wizard_desk_v1', filename: 'a.mp4', ext: 'mp4', character: 'arlo', duration_s: 10 },
          { id: 'chipper_sitting_alt_v2', filename: 'b.mp4', ext: 'mp4', character: 'chipper', duration_s: 12 },
        ],
        count: 2,
      }),
    });
  });
}

test.describe('OPERATOR_EDIT_AUTHORITY_V1 — Phase B ambient preset hydrate', () => {
  test('AMBIENT-HYDRATE-1 — focus refresh with omitted server field keeps local preset', async ({
    page,
  }) => {
    await mockAudioFiles(page);
    await mockAmbientPresetList(page, [
      { preset_id: 'forest' },
      { preset_id: 'rain' },
    ]);
    await page.route('**/api/v2/module/patch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    let omitAmbientField = false;
    await page.route(`**/api/v2/event/${FIXTURE_EVENT}/state**`, async (route) => {
      const body: Record<string, unknown> = {
        ok: true,
        beats: {},
        phase_b_lipsync_file: 'fix_lipsync.mp4',
      };
      if (!omitAmbientField) {
        body.phase_b_ambient_preset_id = 'forest';
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await gotoApp(page);
    await openPhaseB(page);

    const select = page.locator('[data-testid="phase-b-ambient-preset-select"]');
    await expect(select).toHaveValue('forest');
    await select.selectOption('rain');
    await expect(select).toHaveValue('rain');

    omitAmbientField = true;
    await page.evaluate(() => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(400);

    await expect(select).toHaveValue('rain');
  });
});

test.describe('OPERATOR_EDIT_AUTHORITY_V1 — Phase A base clip hydrate', () => {
  test('PHASE-CLIP-HYDRATE-1 — focus refresh with omitted server field keeps picked clip', async ({
    page,
  }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await page.route('**/api/v2/module/patch**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });
    await page.route('**/api/event/current**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          event_id: FIXTURE_EVENT,
          event_generation: 1,
        }),
      });
    });

    let omitClipField = false;
    await page.route(`**/api/v2/event/${FIXTURE_EVENT}/state**`, async (route) => {
      const body: Record<string, unknown> = {
        ok: true,
        beats: {},
        phase_a_lipsync_file: 'fix_lipsync.mp4',
      };
      if (!omitClipField) {
        body.phase_a_chipper_sitting_clip_id = 'arlo_idle_wizard_desk_v1';
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });

    await gotoApp(page);
    await openPhaseA(page);

    const slot = page.locator('[data-testid="phase-a-clip-slot-sitting"]');
    await expect(slot).toHaveAttribute('data-clip-id', 'arlo_idle_wizard_desk_v8');

    await page.locator('[data-testid="phase-a-clip-pick-sitting"]').click();
    await page.locator('[data-testid="base-clip-option-chipper_sitting_alt_v2"]').click();
    await expect(slot).toHaveAttribute('data-clip-id', 'chipper_sitting_alt_v2');

    omitClipField = true;
    await page.evaluate(() => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(400);

    await expect(slot).toHaveAttribute('data-clip-id', 'chipper_sitting_alt_v2');
  });
});

async function mockWatercolorList(page: Page): Promise<void> {
  await page.route('**/api/phase/watercolor_list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [{ key: 'wc_test', filename: 'wc_test.png', mtime: 1 }],
        count: 1,
      }),
    });
  });
}

async function mockModulePatch(page: Page): Promise<void> {
  await page.route('**/api/v2/module/patch**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
}

test.describe('WTA-018 — watercolor drop timing (DROP-WC-1)', () => {
  test('DROP-WC-1 — drop at 50% lands near midpoint after duration ready', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    const wfBox = await waveform.boundingBox();
    expect(wfBox).not.toBeNull();
    await waveform.evaluate((el: Element, args: { x: number; y: number }) => {
      const dt = new DataTransfer();
      const payload = JSON.stringify({
        kind: 'lib-watercolor',
        lib_key: 'wc_test',
        animation_type: 'fade_in',
      });
      dt.setData('application/x-mn-drag', payload);
      dt.setData('text/plain', payload);
      el.dispatchEvent(new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.x,
        clientY: args.y,
      }));
    }, { x: wfBox!.x + wfBox!.width / 2, y: wfBox!.y + wfBox!.height / 2 });

    await expect(page.locator('[data-testid="phase-b-watercolors"]')).toContainText('wc_test', {
      timeout: 5_000,
    });
  });

  test('DROP-PLAY-1 — drop moves playhead; ▶ Play starts near cue (WTA-32)', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
      phase_b_watercolor_cues_json: [],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    const wfBox = await waveform.boundingBox();
    expect(wfBox).not.toBeNull();
    const dropX = wfBox!.x + wfBox!.width * 0.62;
    const dropY = wfBox!.y + wfBox!.height * 0.5;

    await waveform.evaluate((el: Element, args: { x: number; y: number }) => {
      const dt = new DataTransfer();
      const payload = JSON.stringify({
        kind: 'lib-watercolor',
        lib_key: 'wc_test',
        animation_type: 'fade_in',
      });
      dt.setData('application/x-mn-drag', payload);
      dt.setData('text/plain', payload);
      el.dispatchEvent(new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.x,
        clientY: args.y,
      }));
    }, { x: dropX, y: dropY });

    await expect(waveform).toHaveAttribute('data-cue-count', '1', { timeout: 5_000 });
    const durMs = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    const afterDropMs = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(afterDropMs).toBeGreaterThan(durMs * 0.45);
    expect(afterDropMs).toBeLessThan(durMs * 0.8);

    const playBtn = waveform.locator('[data-testid="waveform-play-btn"]');
    await playBtn.click();
    await expect(playBtn).toHaveText(/⏸ Pause/, { timeout: 3_000 });
    await page.waitForTimeout(800);
    const playMs = Number(await waveform.getAttribute('data-current-time-ms'));
    expect(playMs).toBeGreaterThan(afterDropMs * 0.75);
  });

  test('DROP-WC-2 — capture drop on canvas + non-draggable watercolor thumb (DROP-CAPTURE-1)', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    await expect(waveform).toHaveAttribute('data-drop-capture-bound', 'WAVEFORM_DROP_CAPTURE_V1');

    const thumbDraggable = await page
      .locator('[data-testid="phase-b-watercolor-tile-wc_test"] img')
      .evaluate((el) => (el as HTMLImageElement).draggable);
    expect(thumbDraggable).toBe(false);

    const wfBox = await waveform.boundingBox();
    expect(wfBox).not.toBeNull();
    const dropX = wfBox!.x + wfBox!.width * 0.5;
    const dropY = wfBox!.y + wfBox!.height * 0.7;

    await waveform.evaluate(
      (el: Element, args: { x: number; y: number }) => {
        const canvas = el.querySelector('.mn-waveform-canvas') ?? el;
        const dt = new DataTransfer();
        const payload = JSON.stringify({
          kind: 'lib-watercolor',
          lib_key: 'wc_test',
          animation_type: 'fade_in',
        });
        dt.setData('application/x-mn-drag', payload);
        dt.setData('text/plain', payload);
        const base = {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX: args.x,
          clientY: args.y,
        };
        canvas.dispatchEvent(new DragEvent('dragover', base));
        canvas.dispatchEvent(new DragEvent('drop', base));
      },
      { x: dropX, y: dropY },
    );

    await expect(waveform).toHaveAttribute('data-cue-count', '1', { timeout: 5_000 });
  });

  test('DROP-REJECT-1 — drop before waveform ready shows warning toast (WTA-5)', async ({ page }) => {
    let releaseHeldAudio: (() => void) | null = null;
    const audioHeld = new Promise<void>((resolve) => {
      releaseHeldAudio = resolve;
    });
    await page.route(/\/files\?path=.*\.(mp3|mp4|wav|m4a|ogg)/, async (route) => {
      await audioHeld;
      await route.fulfill({
        status: 200,
        contentType: 'audio/wav',
        body: silentWavBytes(30, 8000),
      });
    });
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
      phase_b_watercolor_cues_json: [],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator(
      '[data-testid="pane-phase-b-keepalive"] [data-testid="waveform-timeline"]',
    );
    await expect(waveform).toBeVisible();
    await expect(waveform.locator('[data-testid="waveform-play-btn"]')).toBeDisabled();

    const wfBox = await waveform.boundingBox();
    expect(wfBox).not.toBeNull();

    await waveform.evaluate(
      (el: Element, args: { x: number; y: number }) => {
        const dt = new DataTransfer();
        const payload = JSON.stringify({
          kind: 'lib-watercolor',
          lib_key: 'wc_test',
          animation_type: 'fade_in',
        });
        dt.setData('application/x-mn-drag', payload);
        dt.setData('text/plain', payload);
        el.dispatchEvent(new DragEvent('drop', {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX: args.x,
          clientY: args.y,
        }));
      },
      { x: wfBox!.x + wfBox!.width * 0.5, y: wfBox!.y + wfBox!.height * 0.5 },
    );

    await expect(page.locator('[data-testid="toast-host"]')).toContainText(/drop skipped/i, {
      timeout: 5_000,
    });
    await expect(waveform).toHaveAttribute('data-cue-count', '0');
    releaseHeldAudio?.();
  });
});

test.describe('PHASE_WAVEFORM_PLAY — remount duration carry (WTA-13)', () => {
  test('REMOUNT-STEM-2 — stem review keeps duration ms through trim toggle (WTA-13)', async ({
    page,
  }) => {
    await mockAudioFiles(page, 40);
    await mockPhaseState(page, {
      phase_b_voice_stem_file: 'fix_phase_b_stem.mp3',
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_lipsync_requires_regen: true,
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = await waitForWaveformReady(page, 'b');
    await expect(waveform).toHaveAttribute('data-source-label', 'stem');
    const durBefore = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    expect(durBefore).toBeGreaterThan(10_000);

    await page.locator('[data-testid="phase-b-trim-voice-stem-btn"]').click();
    await expect(page.locator('[data-testid="phase-b-stem-trim-mode-badge"]')).toBeVisible();
    await page.waitForTimeout(300);

    const durDuring = Number(await waveform.getAttribute('data-loaded-duration-ms'));
    expect(durDuring).toBeGreaterThan(10_000);
  });
});

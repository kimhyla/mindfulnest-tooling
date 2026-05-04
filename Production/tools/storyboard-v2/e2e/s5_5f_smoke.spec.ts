// S5.5f Phase B + downstream smoke tests — TDD red→green for the 18 F-gates
// distributed across Phases B-F per spec §19.2.
//
// Spec: Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md (§3, §4 Phase B-F, §19)
// LDs: WAVESURFER_TIMELINE_INTEGRATION_V1, MANDATORY_E2E_GATE_V1,
//      CI_PLAYWRIGHT_ON_COMMIT_V1
//
// Fixture: Production/Event_e2e_fixture/ (intro=3 beats, resolution=0 beats,
// phase_a/phase_b status pending). Pattern from e2e/s5_5ce_proper_fix.spec.ts.
//
// Phase distribution (TDD ordering — this file ships RED first per phase):
//   Phase B: F3, F4, F5, F6 — WaveSurfer integration
//   Phase C: F7, F8, F9 — CuePopover + drag-drop
//   Phase D: F10, F11, F12, F13 — Phase A 3-clip handling
//   Phase E: F14, F15 — Voice stem + ambient preset
//   Phase F: F1, F2, F16, F17, F18 — verification (F17 = grep gate; F18 = full suite green)

import { test, expect, type Page } from '@playwright/test';

const FIXTURE_EVENT = 'Event_e2e_fixture';

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

/**
 * Generate a silent WAV blob (PCM 16-bit mono) for WaveSurfer to decode.
 * 30s @ 8kHz = ~480 KB raw; small enough to round-trip without hitting timeouts.
 * Silence still has a real audio duration once decoded.
 */
function silentWavBytes(durationS: number, sampleRate: number = 8000): Buffer {
  const numSamples = Math.floor(durationS * sampleRate);
  const dataSize = numSamples * 2; // 16-bit mono = 2 bytes/sample
  const buf = Buffer.alloc(44 + dataSize);
  buf.write('RIFF', 0);
  buf.writeUInt32LE(36 + dataSize, 4);
  buf.write('WAVE', 8);
  buf.write('fmt ', 12);
  buf.writeUInt32LE(16, 16);                // fmt chunk size
  buf.writeUInt16LE(1, 20);                 // PCM
  buf.writeUInt16LE(1, 22);                 // mono
  buf.writeUInt32LE(sampleRate, 24);
  buf.writeUInt32LE(sampleRate * 2, 28);    // byte rate
  buf.writeUInt16LE(2, 32);                 // block align
  buf.writeUInt16LE(16, 34);                // bits per sample
  buf.write('data', 36);
  buf.writeUInt32LE(dataSize, 40);
  // Sample data zero-initialized = silence.
  return buf;
}

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

/**
 * Mock the /files endpoint to return a silent WAV regardless of the
 * requested filename / extension. WaveSurfer reads the bytes, not the URL —
 * Content-Type audio/wav makes it decode cleanly.
 */
async function mockAudioFiles(page: Page, durationS: number = 30): Promise<void> {
  await page.route(/\/files\?path=.*\.(mp3|mp4|wav|m4a|ogg)/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: silentWavBytes(durationS, 8000),
    });
  });
}

/**
 * Mock the v2 event-state endpoint with a flat-shape patch. PhaseProducer's
 * pickPhaseSlice() reads top-level state['phase_<a|b>_<suffix>'] keys, which
 * the real server hoists out of the nested phase_a / phase_b objects per
 * LD-484 / LD-485. The mock skips that hoist and just supplies flat keys.
 */
async function mockPhaseState(
  page: Page,
  patch: Record<string, unknown>,
): Promise<void> {
  await page.route(`**/api/v2/event/${FIXTURE_EVENT}/state**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        beats: {},
        ...patch,
      }),
    });
  });
}

async function openPhaseB(page: Page): Promise<void> {
  await page.click('[data-testid="tab-phase-b"]');
  await expect(page.locator('[data-testid="pane-phase-b"]')).toBeVisible();
  // PhaseProducer is collapsed by default — expand it.
  const summary = page.locator('[data-testid="phase-producer-b"] > summary');
  await expect(summary).toBeVisible();
  await summary.click();
}

// ----------------------------------------------------------------------------
// Phase B — WaveSurfer integration (F3-F6)
// ----------------------------------------------------------------------------

test.describe('F3 — WaveSurfer load probe', () => {
  test('F3 — phase_b_lipsync_file present → WaveformTimeline mounts', async ({ page }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toBeVisible();
    await expect(waveform).toHaveAttribute('data-audio-src', /fix_lipsync\.mp4/);
  });
});

test.describe('F4 — Audio source priority lipsync > mixed > stem', () => {
  test('F4.1 — lipsync wins when all three present', async ({ page }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_mixed_audio_file: 'fix_mixed.mp3',
      phase_b_voice_stem_file: 'fix_stem.mp3',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toHaveAttribute('data-source-label', 'lipsync');
  });

  test('F4.2 — mixed wins when lipsync absent', async ({ page }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, {
      phase_b_mixed_audio_file: 'fix_mixed.mp3',
      phase_b_voice_stem_file: 'fix_stem.mp3',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toHaveAttribute('data-source-label', 'mixed');
  });

  test('F4.3 — stem wins when only stem present', async ({ page }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, {
      phase_b_voice_stem_file: 'fix_stem.mp3',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toHaveAttribute('data-source-label', 'stem');
  });
});

test.describe('F5 — Click-to-seek on waveform', () => {
  test('F5 — click at 50% advances cursor to ~50% of duration', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toBeVisible();

    // WaveSurfer publishes duration via the ready event; component mirrors it
    // into data-loaded-duration-ms. Wait for that before clicking — clicking
    // before duration is known would seek into nothing.
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    const canvas = waveform.locator('.mn-waveform-canvas');
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    await canvas.click({
      position: { x: box!.width / 2, y: box!.height / 2 },
    });

    // 50% of a 30s duration ≈ 15000 ms; allow generous slack for WaveSurfer's
    // click-event coordinate rounding.
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-current-time-ms');
      return v ? Number(v) : 0;
    }, { timeout: 5_000 }).toBeGreaterThan(10_000);
  });
});

test.describe('F6 — Cue marker render at correct horizontal position', () => {
  test('F6 — cue at offset_ms=15000 / duration=30000 renders near 50% left', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [
        {
          id: 'cue_test_a',
          watercolor_key: 'wc_test',
          offset_ms: 15000,
          duration_ms: 3000,
          animation_type: 'fade_in',
          volume: 1.0,
        },
      ],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toBeVisible();

    // Marker positioning depends on a known audio duration.
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    const cue = page.locator('[data-testid="cue-marker-cue_test_a"]');
    await expect(cue).toBeVisible();

    const containerBox = await waveform.boundingBox();
    const markerBox = await cue.boundingBox();
    expect(containerBox).not.toBeNull();
    expect(markerBox).not.toBeNull();
    const markerLeftRelative = markerBox!.x - containerBox!.x;
    const expectedLeft = containerBox!.width * 0.5;
    // Allow ±10% of container width for marker centering / canvas padding.
    expect(Math.abs(markerLeftRelative - expectedLeft)).toBeLessThan(
      containerBox!.width * 0.1,
    );
  });
});

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

import { test, expect, type Page, type Request } from '@playwright/test';

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

// ----------------------------------------------------------------------------
// Phase C — CuePopover + drag-drop (F7-F9)
//
// These tests cover the cue authoring loop:
//   F7 — drag a watercolor tile onto the timeline → cue created with
//        offset_ms derived from drop X / container width × duration
//   F8 — click cue marker → CuePopover opens; change duration → fires
//        pathappPatch v2_module_patch with the updated cues array
//   F9 — Delete inside CuePopover with Modal-confirm (Cursor v8 Q8) removes
//        the cue. Shift+click on Delete skips confirm (power-user path).
// ----------------------------------------------------------------------------

/**
 * Mock the v2_module_patch endpoint to acknowledge writes without exercising
 * the server-side _V2_MODULE_FIELD_VALIDATORS — keeps tests focused on the
 * client request shape, not server validation (which is covered by Phase 6.5
 * boundary probes in production).
 */
async function mockModulePatch(page: Page): Promise<void> {
  await page.route('**/api/v2/module/patch', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
  // Snapshot endpoint fires before every pathappPatch — mock so it doesn't 500.
  await page.route('**/api/state/snapshot', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
}

/**
 * Mock /api/phase/watercolor_list with one tile so PhaseProducer renders a
 * draggable watercolor source. The keys / shape here mirror what the real
 * server returns to satisfy WatercolorListResponse in PhaseProducer.tsx.
 */
async function mockWatercolorList(page: Page): Promise<void> {
  await page.route('**/api/phase/watercolor_list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [
          {
            key: 'wc_test',
            filename: 'wc_test.png',
            ext: 'png',
            kind: 'static',
            thumb_url: '',
            mtime: 1714800000,
            size_bytes: 1024,
          },
        ],
        count: 1,
      }),
    });
  });
}

test.describe('F7 — Drag watercolor onto timeline → cue created', () => {
  test('F7 — drop on waveform fires v2_module_patch with phase_b_watercolor_cues_json + new cue', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [], // start empty
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toBeVisible();
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    const tile = page.locator('[data-testid="phase-b-watercolor-tile-wc_test"]');
    await expect(tile).toBeVisible();

    const patches: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v2/module/patch')) patches.push(req);
    });

    // dragTo synthesizes drag start → drop. Position the drop at the
    // 50% horizontal mark inside the waveform container.
    const wfBox = await waveform.boundingBox();
    expect(wfBox).not.toBeNull();
    await tile.dragTo(waveform, {
      targetPosition: { x: wfBox!.width / 2, y: wfBox!.height / 2 },
    });

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['field']).toBe('phase_b_watercolor_cues_json');
    const value = body['value'] as Array<Record<string, unknown>>;
    expect(Array.isArray(value)).toBe(true);
    expect(value.length).toBe(1);
    const cue = value[0]!;
    expect(cue['watercolor_key']).toBe('wc_test');
    expect(cue['animation_type']).toBe('fade_in');
    expect(cue['duration_ms']).toBe(3000);
    // offset_ms ≈ 50% of 30s ≈ 15000 ms; allow ±20% slack for click coordinates.
    const offsetMs = Number(cue['offset_ms']);
    expect(offsetMs).toBeGreaterThan(10_000);
    expect(offsetMs).toBeLessThan(20_000);
  });
});

test.describe('F8 — Click cue marker → CuePopover edit', () => {
  test('F8 — click marker opens popover; changing duration fires v2_module_patch with updated cue', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [
        {
          id: 'cue_existing',
          watercolor_key: 'wc_test',
          offset_ms: 8000,
          duration_ms: 3000,
          animation_type: 'fade_in',
          volume: 1.0,
        },
      ],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    await page.locator('[data-testid="cue-marker-cue_existing"]').click();
    const popover = page.locator('[data-testid="cue-popover"]');
    await expect(popover).toBeVisible();

    const patches: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v2/module/patch')) patches.push(req);
    });

    const durationInput = popover.locator('[data-testid="cue-popover-duration"]');
    await durationInput.fill('5000');
    await durationInput.blur();

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['field']).toBe('phase_b_watercolor_cues_json');
    const value = body['value'] as Array<Record<string, unknown>>;
    expect(value.length).toBe(1);
    expect(value[0]!['id']).toBe('cue_existing');
    expect(value[0]!['duration_ms']).toBe(5000);
  });
});

test.describe('F9 — CuePopover Delete with Modal-confirm', () => {
  test('F9.1 — Delete prompts modal-confirm; confirming removes cue', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [
        {
          id: 'cue_doomed',
          watercolor_key: 'wc_test',
          offset_ms: 12000,
          duration_ms: 3000,
          animation_type: 'fade_in',
          volume: 1.0,
        },
      ],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    await page.locator('[data-testid="cue-marker-cue_doomed"]').click();
    const popover = page.locator('[data-testid="cue-popover"]');
    await expect(popover).toBeVisible();

    // Click Delete (no shift) → confirmation modal appears (Cursor v8 Q8).
    await popover.locator('[data-testid="cue-popover-delete"]').click();
    const confirmModal = page.locator('[data-testid="modal-cue-delete"]');
    await expect(confirmModal).toBeVisible();

    const patches: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v2/module/patch')) patches.push(req);
    });

    await confirmModal.locator('[data-testid="cue-delete-confirm"]').click();

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['field']).toBe('phase_b_watercolor_cues_json');
    const value = body['value'] as Array<Record<string, unknown>>;
    // After delete, the cues array is empty.
    expect(value.length).toBe(0);
  });

  test('F9.2 — Shift+click on Delete skips confirm (power-user path)', async ({ page }) => {
    await mockAudioFiles(page, 30);
    await mockModulePatch(page);
    await mockWatercolorList(page);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
      phase_b_watercolor_cues_json: [
        {
          id: 'cue_skipconfirm',
          watercolor_key: 'wc_test',
          offset_ms: 12000,
          duration_ms: 3000,
          animation_type: 'fade_in',
          volume: 1.0,
        },
      ],
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect.poll(async () => {
      const v = await waveform.getAttribute('data-loaded-duration-ms');
      return v ? Number(v) : 0;
    }, { timeout: 15_000 }).toBeGreaterThan(0);

    await page.locator('[data-testid="cue-marker-cue_skipconfirm"]').click();
    const popover = page.locator('[data-testid="cue-popover"]');
    await expect(popover).toBeVisible();

    const patches: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v2/module/patch')) patches.push(req);
    });

    // Shift+click → no modal, mutation fires immediately.
    await popover.locator('[data-testid="cue-popover-delete"]').click({ modifiers: ['Shift'] });

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    const value = body['value'] as Array<Record<string, unknown>>;
    expect(value.length).toBe(0);
    // Confirmation modal should NOT have appeared.
    await expect(page.locator('[data-testid="modal-cue-delete"]')).toHaveCount(0);
  });
});

// ----------------------------------------------------------------------------
// Phase D — Phase A 3-clip handling (F10-F13)
//
// Phase A producer renders 3 base-clip slots (fly-in / sitting / fly-out)
// per LD PHASE_A_THREE_CLIP_HANDLING_V1. Phase B remains single-clip via
// the existing selectedBaseClip + Cedric filter. Re-stitch fires manually
// (Cursor v8 Q9) via the existing onMixAudio path
// (pathappPatch 'phase_b_mix_audio' with phase:'a').
// ----------------------------------------------------------------------------

async function mockBaseClipsList(page: Page): Promise<void> {
  await page.route('**/api/phase/base_clips_list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [
          { id: 'flyin_clip_a', filename: 'flyin_a.mp4', ext: 'mp4', character: 'chipper', duration_s: 1.5 },
          { id: 'sitting_clip_a', filename: 'sitting_a.mp4', ext: 'mp4', character: 'chipper', duration_s: 30.0 },
          { id: 'flyout_clip_a', filename: 'flyout_a.mp4', ext: 'mp4', character: 'chipper', duration_s: 1.0 },
          { id: 'cedric_clip_a', filename: 'cedric_a.mp4', ext: 'mp4', character: 'cedric', duration_s: 5.0 },
        ],
        count: 4,
      }),
    });
  });
}

async function mockMixAudio(page: Page): Promise<void> {
  await page.route('**/api/phase_b/mix_audio', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
}

async function openPhaseA(page: Page): Promise<void> {
  await page.click('[data-testid="tab-phase-a"]');
  await expect(page.locator('[data-testid="pane-phase-a"]')).toBeVisible();
  const summary = page.locator('[data-testid="phase-producer-a"] > summary');
  await expect(summary).toBeVisible();
  await summary.click();
}

test.describe('F10 — Phase A 3-clip render', () => {
  test('F10 — Phase A producer renders flyin / sitting / flyout slots', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseA(page);

    const section = page.locator('[data-testid="phase-a-clip-section"]');
    await expect(section).toBeVisible();
    await expect(page.locator('[data-testid="phase-a-clip-slot-flyin"]')).toBeVisible();
    await expect(page.locator('[data-testid="phase-a-clip-slot-sitting"]')).toBeVisible();
    await expect(page.locator('[data-testid="phase-a-clip-slot-flyout"]')).toBeVisible();
  });
});

test.describe('F11 — Phase A clip pick', () => {
  test('F11 — picking a clip in the sitting slot fires v2_module_patch with phase_a_chipper_sitting_clip_id', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockModulePatch(page);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseA(page);

    const patches: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v2/module/patch')) patches.push(req);
    });

    // Open the picker for the sitting slot.
    await page.locator('[data-testid="phase-a-clip-pick-sitting"]').click();
    const pickerModal = page.locator('[data-testid="modal-base-clip-picker"]');
    await expect(pickerModal).toBeVisible();

    // Modal should list chipper clips; cedric_clip_a should NOT appear.
    await expect(pickerModal.locator('[data-testid="base-clip-option-cedric_clip_a"]')).toHaveCount(0);
    await expect(pickerModal.locator('[data-testid="base-clip-option-sitting_clip_a"]')).toBeVisible();

    await pickerModal.locator('[data-testid="base-clip-option-sitting_clip_a"]').click();

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['field']).toBe('phase_a_chipper_sitting_clip_id');
    expect(body['value']).toBe('sitting_clip_a');
  });
});

test.describe('F12 — Phase A re-stitch', () => {
  test('F12 — Re-stitch button fires phase_b_mix_audio with phase=a', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockModulePatch(page);
    await mockMixAudio(page);
    await mockPhaseState(page, {
      phase_a_chipper_flyin_clip_id: 'flyin_clip_a',
      phase_a_chipper_sitting_clip_id: 'sitting_clip_a',
      phase_a_chipper_flyout_clip_id: 'flyout_clip_a',
    });
    await gotoApp(page);
    await openPhaseA(page);

    const mixReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/phase_b/mix_audio')) mixReqs.push(req);
    });

    await page.locator('[data-testid="phase-a-restitch-btn"]').click();

    await expect.poll(() => mixReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = mixReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['phase']).toBe('a');
  });
});

test.describe('F13 — Phase A vs Phase B branching', () => {
  test('F13 — Phase B does NOT render the 3-clip section', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseB(page);

    // 3-clip slots are Phase-A-only; under Phase B the section must be absent.
    await expect(page.locator('[data-testid="phase-a-clip-section"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="phase-a-clip-slot-flyin"]')).toHaveCount(0);
    // Single base-clip select still present for Phase B (existing behavior).
    await expect(page.locator('[data-testid="phase-b-baseclip-select"]')).toBeVisible();
  });
});

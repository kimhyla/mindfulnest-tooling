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

// Reset server-side event scope before every test (test-hygiene only — no
// production code change). The shared production_server can be left in
// scope_type='milestone' by earlier specs (e.g. f_project_001_milestone_scope.spec.ts
// R1.x → milestone_load). ScopeBoundary then hydrates UI as milestone scope
// (per ef0b007 F-PROJECT-001 fix), which disables the Phase A/B tabs every
// F-test in this file expects to click. Re-pin server to the fixture event so
// each test starts from a clean event-scope baseline. Absolute URL per Rule 32.
test.beforeEach(async ({ request }) => {
  await request.post('http://localhost:5200/api/event/load', {
    data: { event_id: FIXTURE_EVENT },
  });
});

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
  // PhaseProducer is always-open (collapse removed 2026-05-25, commit b6ac706).
  // No summary/details expansion needed — full content is immediately visible.
  await expect(page.locator('[data-testid="phase-producer-b"]')).toBeVisible();
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
    await mockAmbientPresetList(page, []);
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

    // Synthetic drop event — same pattern as s5_5ce_proper_fix R2.3
    // because Playwright's dragTo across nested Preact subtrees is fragile
    // when the source element re-renders mid-drag. The waveform receives a
    // DragEvent with the lib-watercolor payload at the 50% horizontal mark.
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
      const drop = new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.x,
        clientY: args.y,
      });
      el.dispatchEvent(drop);
    }, { x: wfBox!.x + wfBox!.width / 2, y: wfBox!.y + wfBox!.height / 2 });

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
    await mockAmbientPresetList(page, []);
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
    await mockAmbientPresetList(page, []);
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
    await mockAmbientPresetList(page, []);
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
// Phase A Arlo migration: single sitting/base clip (fly-in/out removed).
// Re-stitch fires phase_a_restitch (middle-only + ambient).
// ----------------------------------------------------------------------------

async function mockBaseClipsList(page: Page): Promise<void> {
  await page.route('**/api/phase/base_clips_list**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [
          { id: 'arlo_idle_wizard_desk_v1', filename: 'arlo_idle_wizard_desk_v1.mp4', ext: 'mp4', character: 'arlo', duration_s: 10.0 },
          { id: 'sitting_clip_a', filename: 'sitting_a.mp4', ext: 'mp4', character: 'chipper', duration_s: 30.0 },
          { id: 'cedric_clip_a', filename: 'cedric_a.mp4', ext: 'mp4', character: 'cedric', duration_s: 5.0 },
        ],
        count: 3,
      }),
    });
  });
}

async function mockRestitch(page: Page): Promise<void> {
  await page.route('**/api/phase_a/restitch', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });
}

async function mockMixAudio(page: Page): Promise<void> {
  const body = JSON.stringify({ ok: true });
  await page.route('**/api/phase_a/mix_audio', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body });
  });
  await page.route('**/api/phase_b/mix_audio', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body });
  });
}

async function openPhaseA(page: Page): Promise<void> {
  await page.click('[data-testid="tab-phase-a"]');
  await expect(page.locator('[data-testid="pane-phase-a"]')).toBeVisible();
  // PhaseProducer is always-open (collapse removed 2026-05-25, commit b6ac706).
  // No summary/details expansion needed — full content is immediately visible.
  await expect(page.locator('[data-testid="phase-producer-a"]')).toBeVisible();
}

test.describe('F10 — Phase A base clip section', () => {
  test('F10 — Phase A producer renders Arlo base (talking) slot only', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseA(page);

    const section = page.locator('[data-testid="phase-a-clip-section"]');
    await expect(section).toBeVisible();
    await expect(page.locator('[data-testid="phase-a-clip-slot-sitting"]')).toBeVisible();
    await expect(page.locator('[data-testid="phase-a-clip-slot-flyin"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="phase-a-clip-slot-flyout"]')).toHaveCount(0);
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

    // Modal should list arlo/chipper clips; cedric should NOT appear.
    await expect(pickerModal.locator('[data-testid="base-clip-option-cedric_clip_a"]')).toHaveCount(0);
    await expect(pickerModal.locator('[data-testid="base-clip-option-arlo_idle_wizard_desk_v1"]')).toBeVisible();

    await pickerModal.locator('[data-testid="base-clip-option-arlo_idle_wizard_desk_v1"]').click();

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['field']).toBe('phase_a_chipper_sitting_clip_id');
    expect(body['value']).toBe('arlo_idle_wizard_desk_v1');
  });
});

test.describe('F12 — Phase A re-stitch', () => {
  test('F12 — Re-stitch button fires phase_a/restitch', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockModulePatch(page);
    await mockRestitch(page);
    await mockPhaseState(page, {
      phase_a_chipper_sitting_clip_id: 'arlo_idle_wizard_desk_v1',
    });
    await gotoApp(page);
    await openPhaseA(page);

    const restitchReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/phase_a/restitch')) restitchReqs.push(req);
    });

    await page.locator('[data-testid="phase-a-restitch-btn"]').click();

    await expect.poll(() => restitchReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
  });
});

test.describe('F17 — Phase A single canonical player (LD-829)', () => {
  test('F17.1 — fresh stitched: one video, stitched src + waveform label', async ({ page }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, {
      phase_a_lipsync_file: 'phase_a_lipsync_e2e.mp4',
      phase_a_lipsync_mtime: 1_000,
      phase_a_stitched_file: 'phase_a_stitched_e2e.mp4',
      phase_a_stitched_mtime: 2_000,
    });
    await gotoApp(page);
    await openPhaseA(page);

    await expect(page.locator('[data-testid="phase-producer-a"]')).toHaveAttribute(
      'data-phase-a-single-player',
      'PHASE_A_SINGLE_PLAYER_V1',
    );
    await expect(page.locator('[data-testid="phase-a-stitched-preview"]')).toHaveCount(0);
    const videos = page.locator('[data-testid="phase-producer-a"] video');
    await expect(videos).toHaveCount(1);
    await expect(videos.first()).toHaveAttribute('src', /phase_a_stitched_e2e\.mp4/);
    await expect(page.locator('[data-testid="waveform-timeline"]')).toHaveAttribute(
      'data-source-label',
      'stitched',
    );
  });

  test('F17.2 — stale stitched: one lipsync video + stale banner, no second player', async ({
    page,
  }) => {
    await mockAudioFiles(page);
    await mockPhaseState(page, {
      phase_a_lipsync_file: 'phase_a_lipsync_e2e.mp4',
      phase_a_lipsync_mtime: 2_000,
      phase_a_stitched_file: 'phase_a_stitched_stale.mp4',
      phase_a_stitched_mtime: 1_000,
    });
    await gotoApp(page);
    await openPhaseA(page);

    await expect(page.locator('[data-testid="phase-a-stitched-preview"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="phase-producer-a"] video')).toHaveCount(1);
    await expect(page.locator('[data-testid="phase-producer-a"] video')).toHaveAttribute(
      'src',
      /phase_a_lipsync_e2e\.mp4/,
    );
    await expect(page.locator('[data-testid="phase-a-stitched-stale"]')).toBeVisible();
    await expect(page.locator('[data-testid="waveform-timeline"]')).toHaveAttribute(
      'data-source-label',
      'lipsync',
    );
  });
});

test.describe('F13 — Phase A vs Phase B branching', () => {
  test('F13 — Phase B does NOT render the 3-clip section', async ({ page }) => {
    await mockAudioFiles(page);
    await mockBaseClipsList(page);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseB(page);

    // 3-clip slots are Phase-A-only; under Phase B the section must be absent
    // from the Phase B pane (Phase A keepalive stays mounted but hidden).
    const phaseBPane = page.locator('[data-testid="pane-phase-b-keepalive"]');
    await expect(phaseBPane.locator('[data-testid="phase-a-clip-section"]')).toHaveCount(0);
    await expect(phaseBPane.locator('[data-testid="phase-a-clip-slot-flyin"]')).toHaveCount(0);
    // Phase B uses Avatar Pro (no legacy base-clip dropdown); producer + watercolors remain.
    await expect(phaseBPane.locator('[data-testid="phase-producer-b"]')).toBeVisible();
    await expect(phaseBPane.locator('[data-testid="phase-b-watercolors"]')).toBeVisible();
  });
});

// ----------------------------------------------------------------------------
// Phase E — Voice stem + ambient preset (F14-F15)
//
// Voice stem flow uses the existing (misnamed) /api/phase_b/regen_audio
// endpoint per Cursor v8 Q5 — UX label is "Generate stem from script", NOT
// file-upload (which is OUT OF SCOPE for this session per spec §3.6).
// Ambient preset selector saves preset_id via v2_module_patch with field
// phase_X_ambient_preset_id (whitelisted in _V2_MODULE_ALLOWED_FIELDS).
// ----------------------------------------------------------------------------

async function mockRegenAudio(page: Page): Promise<void> {
  await page.route('**/api/phase_b/regen_audio', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, voice_stem_file: 'phase_b_stem_e2e.mp3' }),
    });
  });
}

async function mockAmbientPresetList(
  page: Page,
  presets: Array<{ preset_id: string; file_size_bytes: number }>,
): Promise<void> {
  await page.route('**/api/phase_b/ambient_preset_list', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, items: presets, count: presets.length }),
    });
  });
}

test.describe('F14 — Voice stem button (Generate stem from script)', () => {
  test('F14 — clicking Generate-stem POSTs to /api/phase_b/regen_audio with phase + script', async ({ page }) => {
    await mockAudioFiles(page);
    await mockRegenAudio(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {
      phase_b_script: 'Test script for stem generation.',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const reqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/phase_b/regen_audio')) reqs.push(req);
    });

    await page.locator('[data-testid="phase-b-generate-stem-btn"]').click();

    await expect.poll(() => reqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = reqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['phase']).toBe('b');
    expect(typeof body['script']).toBe('string');
    expect(body['script']).toContain('stem generation');
  });
});

// ----------------------------------------------------------------------------
// Phase F — Verification gates that don't fit a single feature phase
//   F1   — npm run build clean (verified at build time, not in this suite)
//   F2   — server /api/health 200 (covered by infra-smoke in s5_5ce)
//   F16  — watercolor tile framing (LD-203: brown border / cream mat /
//          white interior / centered art) renders on PhaseProducer tiles.
//   F17  — grep gate for no `Production/Event_1/` literals in
//          PhaseProducer.tsx (covered by a one-line grep step in CI; see
//          §19.10 #2 — already enforced after Phase B wiring; this test
//          provides the in-suite assertion form for parity).
// ----------------------------------------------------------------------------

test.describe('F16 — Watercolor tile framing (LD-203)', () => {
  test('F16 — tile shows brown border + cream mat + white interior wrapping centered art', async ({ page }) => {
    await mockAudioFiles(page);
    await mockWatercolorList(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseB(page);

    const tile = page.locator('[data-testid="phase-b-watercolor-tile-wc_test"]');
    await expect(tile).toBeVisible();

    // Border — brown (any non-zero brown-ish color); cream mat background.
    const border = await tile.evaluate((el) =>
      window.getComputedStyle(el).borderTopColor,
    );
    const bg = await tile.evaluate((el) =>
      window.getComputedStyle(el).backgroundColor,
    );
    // CSS literal "#6b4f2a" → "rgb(107, 79, 42)"; cream "#f5e9c8" → "rgb(245, 233, 200)".
    expect(border).toBe('rgb(107, 79, 42)');
    expect(bg).toBe('rgb(245, 233, 200)');

    // White interior — the wrap around the thumb.
    const wrap = tile.locator('.mn-phase-watercolor-thumb-wrap');
    await expect(wrap).toBeVisible();
    const wrapBg = await wrap.evaluate((el) =>
      window.getComputedStyle(el).backgroundColor,
    );
    expect(wrapBg).toBe('rgb(255, 255, 255)');

    // Centered art — wrap uses flex centering.
    const display = await wrap.evaluate((el) => window.getComputedStyle(el).display);
    const justify = await wrap.evaluate((el) => window.getComputedStyle(el).justifyContent);
    const align = await wrap.evaluate((el) => window.getComputedStyle(el).alignItems);
    expect(display).toBe('flex');
    expect(justify).toBe('center');
    expect(align).toBe('center');
  });
});

test.describe('F17 — grep gate (no Production/Event_1/ literals)', () => {
  test('F17 — fileUrl + onExportToStitcher build paths from activeScope.event_id', async ({ page }) => {
    // Black-box assertion: open Phase B with a mocked state file and verify
    // the audio src URL contains the fixture event id (NOT "Event_1").
    await mockAudioFiles(page);
    await mockAmbientPresetList(page, []);
    await mockPhaseState(page, {
      phase_b_lipsync_file: 'fix_lipsync.mp4',
    });
    await gotoApp(page);
    await openPhaseB(page);

    const waveform = page.locator('[data-testid="waveform-timeline"]');
    await expect(waveform).toBeVisible();
    const src = (await waveform.getAttribute('data-audio-src')) ?? '';
    // Decoded fixture id appears in the path; "Event_1" does NOT.
    expect(src).toContain('Event_e2e_fixture');
    expect(src).not.toContain('Event_1');
  });
});

test.describe('F15 — Ambient preset selector', () => {
  test('F15 — selecting a preset fires v2_module_patch with phase_b_ambient_preset_id', async ({ page }) => {
    await mockAudioFiles(page);
    await mockModulePatch(page);
    await mockAmbientPresetList(page, [
      { preset_id: 'forest', file_size_bytes: 1024000 },
      { preset_id: 'rain', file_size_bytes: 980000 },
    ]);
    await mockPhaseState(page, {});
    await gotoApp(page);
    await openPhaseB(page);

    const select = page.locator('[data-testid="phase-b-ambient-preset-select"]');
    await expect(select).toBeVisible();
    // List should be populated from the mocked endpoint.
    await expect(select.locator('option[value="forest"]')).toHaveCount(1);
    await expect(select.locator('option[value="rain"]')).toHaveCount(1);

    const patches: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/v2/module/patch')) patches.push(req);
    });

    await select.selectOption('rain');

    await expect.poll(() => patches.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = patches[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['field']).toBe('phase_b_ambient_preset_id');
    expect(body['value']).toBe('rain');
  });
});

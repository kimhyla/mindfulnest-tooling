// S5.5g smoke — Stitcher SFX/transitions/trims + Production Map fixes
//
// Spec: Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md (Cursor v8 + v11 §19
//       + v12 R1-R5 fold APPROVED 2026-05-04; §19.2.1 canonical numbering;
//       §19.4 HARD/SOFT for new LDs; §19.10 Phase F revised)
// Phase A audit: Production/docs/STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md
// Continuation handoff: Production/docs/STORYBOARD_V59_S5_5_G_CONTINUATION_HANDOFF.md
// LDs (Phase H targets): STITCHER_SFX_CUE_UI_V1 (HARD), STITCHER_TRANSITIONS_V1 (HARD),
//   STITCHER_PER_SLOT_TRIMS_V1 (HARD), PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 (SOFT)
// Pattern: e2e/s5_5f_smoke.spec.ts (mocked /files + /api/v2/event state)
//        + e2e/architectural_fix.spec.ts (network-spy on M1 snapshot + scope keys)
// Fixture: Production/Event_e2e_fixture/ ONLY — never mutate Event_1/Event_2 (§17)
//
// Phase distribution per §19.2.1 canonical numbering table:
//   Phase B (this file's first wave): G3, G4, G5, G6 — per-slot SFX cue placement
//   Phase C (added in C wave):        G7, G8         — per-boundary transitions
//   Phase D (added in D wave):        G9, G10        — per-slot trims
//   Phase E (added in E wave):        G12, G13       — Production Map multi-event
//   G1/G2/G11/G14/G15/G16 are non-Playwright (build/health/grep/suite/retire) —
//   verified in Phase G + Phase F shell-level checks.

import { test, expect, type Page, type Request } from '@playwright/test';

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

interface MockSlot {
  video_path: string;
  video_dur_ms?: number;
  ambient_bed?: string;
  sfx_cues?: Array<Record<string, unknown>>;
  trim_in_ms?: number;
  trim_out_ms?: number | null;
}

const DEFAULT_SLOTS: Record<string, MockSlot> = {
  intro: {
    video_path: '/abs/path/intro.mp4',
    video_dur_ms: 30000,
    ambient_bed: '',
    sfx_cues: [],
  },
  phase_a: {
    video_path: '/abs/path/phase_a.mp4',
    video_dur_ms: 60000,
    ambient_bed: '',
    sfx_cues: [],
  },
  phase_b: {
    video_path: '/abs/path/phase_b.mp4',
    video_dur_ms: 45000,
    ambient_bed: '',
    sfx_cues: [],
  },
  resolution: {
    video_path: '/abs/path/resolution.mp4',
    video_dur_ms: 30000,
    ambient_bed: '',
    sfx_cues: [],
  },
};

/**
 * Mock /api/stitch_editor/jobs (list summary) + /api/stitch_editor/job/<name>
 * (full detail) so StitcherTab renders with all 4 slots populated.
 */
async function mockStitcherJob(
  page: Page,
  opts: { slots?: Record<string, MockSlot>; transitions?: Array<Record<string, unknown>> } = {},
): Promise<void> {
  const jobName = 'phase_a_Event_e2e_fixture';
  const slots = opts.slots ?? DEFAULT_SLOTS;
  const transitions = opts.transitions ?? [];
  await page.route('**/api/stitch_editor/jobs', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        jobs: [{ name: jobName, created_at: 0, updated_at: 0, slot_count: 4 }],
      }),
    });
  });
  await page.route(`**/api/stitch_editor/job/${jobName}`, async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        name: jobName,
        job: { name: jobName, slots, transitions },
      }),
    });
  });
}

async function mockSnapshot(page: Page): Promise<void> {
  await page.route('**/api/state/snapshot', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"ok":true}',
    });
  });
}

/**
 * Mock POST /api/stitch_editor/job (the save-job mutation). Note: the GET
 * handler is /api/stitch_editor/job/<name>; the regex below targets the
 * exact "/job" terminator so it only matches the POST, not the GET.
 */
async function mockStitchSaveJob(page: Page): Promise<void> {
  await page.route(/\/api\/stitch_editor\/job$/, async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"ok":true}',
    });
  });
}

async function mockTimelineCues(page: Page): Promise<void> {
  await page.route('**/api/timeline/cues', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
}

async function mockSfxLibrary(page: Page): Promise<void> {
  await page.route('**/api/timeline/sfx_library', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          filename: 'soft_chime.mp3',
          path: '/abs/path/sounds/soft_chime.mp3',
          duration_ms: 1500,
          category: 'sfx',
        },
        {
          filename: 'gentle_forest.mp3',
          path: '/abs/path/sounds/gentle_forest.mp3',
          duration_ms: 60000,
          category: 'ambient',
        },
      ]),
    });
  });
}

async function openStitcher(page: Page): Promise<void> {
  await page.click('[data-testid="tab-stitcher"]');
  await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();
  // Wait for the strip to render (job loaded).
  await expect(page.locator('[data-testid="stitcher-strip"]')).toBeVisible();
}

/**
 * Dispatch a synthetic DragEvent('drop') with the given drag payload at the
 * given viewport coordinates on the target element. Mirrors the F7 pattern
 * from s5_5f_smoke.spec.ts because Playwright's dragTo is fragile across
 * Preact subtrees that re-render mid-drag.
 */
async function synthDrop(
  page: Page,
  selector: string,
  payload: Record<string, unknown>,
  position: { xFrac: number; yFrac: number } = { xFrac: 0.5, yFrac: 0.5 },
): Promise<void> {
  const el = page.locator(selector);
  await expect(el).toBeVisible();
  const box = await el.boundingBox();
  if (!box) throw new Error(`No bounding box for ${selector}`);
  const x = box.x + box.width * position.xFrac;
  const y = box.y + box.height * position.yFrac;
  await el.evaluate(
    (node: Element, args: { payloadStr: string; clientX: number; clientY: number }) => {
      const dt = new DataTransfer();
      dt.setData('application/x-mn-drag', args.payloadStr);
      dt.setData('text/plain', args.payloadStr);
      const drop = new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.clientX,
        clientY: args.clientY,
      });
      node.dispatchEvent(drop);
    },
    { payloadStr: JSON.stringify(payload), clientX: x, clientY: y },
  );
}

// ============================================================================
// Phase B — Per-slot SFX cue placement (G3-G6)
// ============================================================================

test.describe('G3 — SFX drag onto slot waveform creates per-slot cue', () => {
  test('G3 — drop at 50% on intro slot fires pathappPatch stitch_save_job with slots.intro.sfx_cues=[new cue]', async ({ page }) => {
    await mockStitcherJob(page);
    await mockSnapshot(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().endsWith('/api/stitch_editor/job') && req.method() === 'POST') {
        saveJobReqs.push(req);
      }
    });

    await gotoApp(page);
    await openStitcher(page);

    const slotWaveform = page.locator('[data-testid="stitcher-slot-waveform-intro"]');
    await expect(slotWaveform).toBeVisible();

    await synthDrop(
      page,
      '[data-testid="stitcher-slot-waveform-intro"]',
      {
        kind: 'lib-sfx',
        lib_key: 'soft_chime',
        source_path: '/abs/path/sounds/soft_chime.mp3',
        filename: 'soft_chime.mp3',
        category: 'sfx',
      },
    );

    await expect.poll(() => saveJobReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = saveJobReqs[0]!.postDataJSON() as Record<string, unknown>;

    // Auto-injected scope keys per LD-461 + S5.5b/d.
    expect(body['event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');

    // Slot+cue contract.
    const slots = body['slots'] as Record<string, MockSlot>;
    expect(slots).toBeDefined();
    const intro = slots.intro!;
    expect(intro).toBeDefined();
    expect(Array.isArray(intro.sfx_cues)).toBe(true);
    expect(intro.sfx_cues!.length).toBe(1);
    const cue = intro.sfx_cues![0]! as Record<string, unknown>;
    expect(cue['source_path']).toBe('/abs/path/sounds/soft_chime.mp3');
    // intro dur=30000, drop at 50% → offset_ms ≈ 15000 (±20% slack for click rounding).
    const offsetMs = Number(cue['offset_ms']);
    expect(offsetMs).toBeGreaterThan(10_000);
    expect(offsetMs).toBeLessThan(20_000);
    // Server defaults consumed at the UI layer (server.py:14085-14087).
    expect(typeof cue['volume']).toBe('number');
    expect(typeof cue['fadein_ms']).toBe('number');
    expect(typeof cue['fadeout_ms']).toBe('number');
  });
});

test.describe('G4 — Click cue marker → SfxCuePopover edit', () => {
  test('G4 — changing volume re-fires stitch_save_job with updated cue', async ({ page }) => {
    const introWithCue: Record<string, MockSlot> = {
      ...DEFAULT_SLOTS,
      intro: {
        ...DEFAULT_SLOTS.intro!,
        sfx_cues: [
          {
            id: 'cue_existing',
            source_path: '/abs/path/sounds/soft_chime.mp3',
            name: 'soft_chime.mp3',
            offset_ms: 12000,
            volume: 0.45,
            fadein_ms: 300,
            fadeout_ms: 1200,
          },
        ],
      },
    };
    await mockStitcherJob(page, { slots: introWithCue });
    await mockSnapshot(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    await gotoApp(page);
    await openStitcher(page);

    const cueMarker = page.locator('[data-testid="stitcher-sfx-cue-marker-intro-cue_existing"]');
    await expect(cueMarker).toBeVisible();
    await cueMarker.click();

    const popover = page.locator('[data-testid="sfx-cue-popover"]');
    await expect(popover).toBeVisible();

    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().endsWith('/api/stitch_editor/job') && req.method() === 'POST') {
        saveJobReqs.push(req);
      }
    });

    // Volume slider (range input) — change to 0.8.
    const volumeInput = popover.locator('[data-testid="sfx-cue-popover-volume"]');
    await volumeInput.fill('0.8');
    // Trigger the input event (range inputs fire on input, not blur).
    await volumeInput.dispatchEvent('input');

    await expect.poll(() => saveJobReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = saveJobReqs[saveJobReqs.length - 1]!.postDataJSON() as Record<string, unknown>;
    const slots = body['slots'] as Record<string, MockSlot>;
    expect(slots.intro!.sfx_cues!.length).toBe(1);
    const updated = slots.intro!.sfx_cues![0] as Record<string, unknown>;
    expect(updated['id']).toBe('cue_existing');
    expect(Number(updated['volume'])).toBeCloseTo(0.8, 2);
  });
});

test.describe('G5 — SfxCuePopover Delete removes per-slot cue', () => {
  test('G5 — clicking Delete removes cue from slot.sfx_cues and re-fires stitch_save_job', async ({ page }) => {
    const introWithCue: Record<string, MockSlot> = {
      ...DEFAULT_SLOTS,
      intro: {
        ...DEFAULT_SLOTS.intro!,
        sfx_cues: [
          {
            id: 'cue_doomed',
            source_path: '/abs/path/sounds/soft_chime.mp3',
            name: 'soft_chime.mp3',
            offset_ms: 12000,
            volume: 0.45,
            fadein_ms: 300,
            fadeout_ms: 1200,
          },
        ],
      },
    };
    await mockStitcherJob(page, { slots: introWithCue });
    await mockSnapshot(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    await gotoApp(page);
    await openStitcher(page);

    await page.locator('[data-testid="stitcher-sfx-cue-marker-intro-cue_doomed"]').click();
    const popover = page.locator('[data-testid="sfx-cue-popover"]');
    await expect(popover).toBeVisible();

    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().endsWith('/api/stitch_editor/job') && req.method() === 'POST') {
        saveJobReqs.push(req);
      }
    });

    // Per-slot cue delete = re-save the slot without the cue (no DELETE HTTP
    // verb required — the slot.sfx_cues array is the source of truth and gets
    // POSTed via stitch_save_job).
    await popover.locator('[data-testid="sfx-cue-popover-delete"]').click();

    await expect.poll(() => saveJobReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = saveJobReqs[saveJobReqs.length - 1]!.postDataJSON() as Record<string, unknown>;
    const slots = body['slots'] as Record<string, MockSlot>;
    expect(Array.isArray(slots.intro!.sfx_cues)).toBe(true);
    expect(slots.intro!.sfx_cues!.length).toBe(0);
  });
});

test.describe('G6 — Module-level cue drop on timeline writes to module_sfx_cues', () => {
  test('G6 — drop on module timeline (below slots) POSTs /api/timeline/cues with cue_type=sfx', async ({ page }) => {
    await mockStitcherJob(page);
    await mockSnapshot(page);
    await mockTimelineCues(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    const moduleCueReqs: Request[] = [];
    page.on('request', (req) => {
      if (
        req.url().includes('/api/timeline/cues') &&
        req.method() === 'POST' &&
        !req.url().includes('/cues/bake')
      ) {
        moduleCueReqs.push(req);
      }
    });

    await gotoApp(page);
    await openStitcher(page);

    const moduleStrip = page.locator('[data-testid="stitcher-module-timeline"]');
    await expect(moduleStrip).toBeVisible();

    await synthDrop(
      page,
      '[data-testid="stitcher-module-timeline"]',
      {
        kind: 'lib-sfx',
        lib_key: 'gentle_forest',
        source_path: '/abs/path/sounds/gentle_forest.mp3',
        filename: 'gentle_forest.mp3',
        category: 'ambient',
      },
    );

    await expect.poll(() => moduleCueReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = moduleCueReqs[0]!.postDataJSON() as Record<string, unknown>;

    // Auto-injected scope keys.
    expect(body['event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');

    // Cue contract: cue_type='sfx' (not 'ambient_segment'); source_path; offset_ms; id.
    expect(body['cue_type']).toBe('sfx');
    expect(body['source_path']).toBe('/abs/path/sounds/gentle_forest.mp3');
    expect(typeof body['id']).toBe('string');
    expect(typeof body['offset_ms']).toBe('number');
  });
});

// ============================================================================
// Phase C — Per-boundary transitions (G7-G8) — STITCHER_TRANSITIONS_V1 (HARD)
//
// Per spec §3.3 + Q1 LOCKED 2026-05-04:
//   transition shape = { after_slot, kind: 'crossfade'|'cut'|'dissolve',
//                        fade_ms, audio_xfade_ms, source_path? }
//   Server defaults kind='crossfade' if absent; audio_xfade_ms = fade_ms if absent.
//   audio_xfade_ms = 0 → pure visual fadeblack with hard audio cut.
//   audio_xfade_ms > 0 → both visual + audio dissolve.
// ============================================================================

test.describe('G7 — Transition selectors render between adjacent slot pairs', () => {
  test('G7 — 3 transition selectors render (after_slot=0, 1, 2) between 4 slots', async ({ page }) => {
    await mockStitcherJob(page);
    await mockSnapshot(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    await gotoApp(page);
    await openStitcher(page);

    // 3 boundaries between 4 slots: intro→phase_a (after_slot=0),
    // phase_a→phase_b (1), phase_b→resolution (2).
    await expect(page.locator('[data-testid="stitcher-transition-after-0"]')).toBeVisible();
    await expect(page.locator('[data-testid="stitcher-transition-after-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="stitcher-transition-after-2"]')).toBeVisible();

    // Each selector exposes kind dropdown.
    await expect(page.locator('[data-testid="stitcher-transition-kind-after-0"]')).toBeVisible();
    await expect(page.locator('[data-testid="stitcher-transition-kind-after-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="stitcher-transition-kind-after-2"]')).toBeVisible();
  });
});

test.describe('G8 — Transition kind change saves via stitch_save_job', () => {
  test('G8 — selecting dissolve at boundary 0 saves transitions[].kind=dissolve + audio_xfade_ms', async ({ page }) => {
    await mockStitcherJob(page);
    await mockSnapshot(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().endsWith('/api/stitch_editor/job') && req.method() === 'POST') {
        saveJobReqs.push(req);
      }
    });

    await gotoApp(page);
    await openStitcher(page);

    // Boundary 0 (intro→phase_a): change kind to 'dissolve'.
    const kindSelect = page.locator('[data-testid="stitcher-transition-kind-after-0"]');
    await expect(kindSelect).toBeVisible();
    await kindSelect.selectOption('dissolve');

    await expect.poll(() => saveJobReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = saveJobReqs[saveJobReqs.length - 1]!.postDataJSON() as Record<string, unknown>;

    // Auto-injected scope keys.
    expect(body['event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');

    // transitions array contains a new entry for after_slot=0 with kind=dissolve.
    const transitions = body['transitions'] as Array<Record<string, unknown>>;
    expect(Array.isArray(transitions)).toBe(true);
    const t0 = transitions.find((t) => Number(t['after_slot']) === 0);
    expect(t0).toBeDefined();
    expect(t0!['kind']).toBe('dissolve');
    // fade_ms + audio_xfade_ms both numeric (server default audio_xfade_ms=fade_ms).
    expect(typeof t0!['fade_ms']).toBe('number');
    expect(typeof t0!['audio_xfade_ms']).toBe('number');
  });

  test('G8.2 — changing audio_xfade_ms input updates transitions[].audio_xfade_ms', async ({ page }) => {
    // Pre-seed boundary 0 with kind=dissolve so the audio_xfade_ms field renders.
    const seededTransitions: Array<Record<string, unknown>> = [
      { after_slot: 0, kind: 'dissolve', fade_ms: 500, audio_xfade_ms: 500, source_path: '' },
    ];
    await mockStitcherJob(page, { transitions: seededTransitions });
    await mockSnapshot(page);
    await mockStitchSaveJob(page);
    await mockSfxLibrary(page);

    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().endsWith('/api/stitch_editor/job') && req.method() === 'POST') {
        saveJobReqs.push(req);
      }
    });

    await gotoApp(page);
    await openStitcher(page);

    const audioInput = page.locator('[data-testid="stitcher-transition-audio-xfade-after-0"]');
    await expect(audioInput).toBeVisible();
    await audioInput.fill('0');
    await audioInput.blur();

    await expect.poll(() => saveJobReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = saveJobReqs[saveJobReqs.length - 1]!.postDataJSON() as Record<string, unknown>;
    const transitions = body['transitions'] as Array<Record<string, unknown>>;
    const t0 = transitions.find((t) => Number(t['after_slot']) === 0);
    expect(t0).toBeDefined();
    expect(Number(t0!['audio_xfade_ms'])).toBe(0);
    expect(t0!['kind']).toBe('dissolve');
  });
});

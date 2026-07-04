// Architectural Fix — V59 Wave 1 (mutation-channel + server hygiene)
//
// Spec: STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md
// LDs: LD-461 SCOPE_KEY_AUTO_INJECTION_V1, LD-456 SCOPE_VALIDATION_V1,
//      LD-453 PATCH_INVARIANT_PERSISTENCE_V1, PATH_C_REWRITE_V1,
//      MUTATION_CHANNEL_INVARIANT_V1 (NEW)
//
// Verifies:
//   AF.1.x — StitcherTab Preview/Bake/SaveJob now route through pathappPatch
//   AF.2.x — VideoSelector set_active/create now route through pathappPatch
//   AF.3.x — sidecar TypeError no longer fatal (covered by Python regression test
//            in Production/tools/tests/test_sidecar_display_order_int.py)
//
// Per Cursor R1: assertions target REAL mutation endpoint URLs (e.g.,
// /api/stitch_editor/preview, /api/video/set_active), NOT a unified
// /api/state/path endpoint (which doesn't exist). pathappPatch posts
// directly to the resolved MUTATION_ENDPOINTS[endpoint] URL with auto-
// injected scope keys per LD-461 + S5.5b/d.

import { test, expect, type Page, type Request } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

const FIXTURE_EVENT = 'Event_e2e_fixture';
const CANONICAL_STITCH_JOB = `${FIXTURE_EVENT}_stitch`;

const DEFAULT_CANONICAL_TRANSITIONS = [
  { after_slot: 0, kind: 'dissolve', fade_ms: 3800, audio_xfade_ms: 0 },
  { after_slot: 1, kind: 'dissolve', fade_ms: 3800, audio_xfade_ms: 0 },
  { after_slot: 2, kind: 'dissolve', fade_ms: 3800, audio_xfade_ms: 0 },
];

// Mock the stitcher /jobs (list) and /job/<name> (detail) so StitcherTab
// renders an active job with slots and the buttons are enabled.
async function mockStitcherJob(
  page: Page,
  jobName = 'phase_a_Event_e2e_fixture',
): Promise<void> {
  const slots = {
    intro: { video_path: '/abs/path/intro.mp4', video_dur_ms: 30000, ambient_bed: '', sfx_cues: [] },
    phase_a: { video_path: '/abs/path/phase_a.mp4', video_dur_ms: 60000, ambient_bed: '', sfx_cues: [] },
    phase_b: { video_path: '/abs/path/phase_b.mp4', video_dur_ms: 45000, ambient_bed: '', sfx_cues: [] },
    resolution: { video_path: '/abs/path/resolution.mp4', video_dur_ms: 30000, ambient_bed: '', sfx_cues: [] },
  };
  const transitions = DEFAULT_CANONICAL_TRANSITIONS;
  const fulfillJob = async (
    route: Parameters<Parameters<Page['route']>[1]>[0],
    name: string,
  ) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        name,
        job: { name, slots, transitions },
      }),
    });
  };
  await page.route('**/api/stitch_editor/jobs', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        jobs: [
          { name: CANONICAL_STITCH_JOB, created_at: 0, updated_at: 0, slot_count: 4 },
          { name: jobName, created_at: 0, updated_at: 0, slot_count: 4 },
        ],
      }),
    });
  });
  await page.route(`**/api/stitch_editor/job/${CANONICAL_STITCH_JOB}`, (r) =>
    fulfillJob(r, CANONICAL_STITCH_JOB),
  );
  await page.route(`**/api/stitch_editor/job/${jobName}`, (r) => fulfillJob(r, jobName));
}

// Mock /api/video/list so VideoSelector mounts with predictable options.
async function mockVideoList(
  page: Page,
  videos: Array<{ video_role: string; has_beats?: boolean; beat_count?: number }>,
  active = 'intro',
): Promise<void> {
  await page.route('**/api/video/list', async (r) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        event_id: 'Event_e2e_fixture',
        active_video: active,
        videos: videos.map((v) => ({
          video_role: v.video_role,
          video_label: null,
          has_beats: v.has_beats ?? true,
          beat_count: v.beat_count ?? 1,
        })),
      }),
    });
  });
}

// =============================================================================
// AF.1 — StitcherTab (F-S2-001): 3 raw fetches → pathappPatch
// =============================================================================

test.describe('AF.1 — StitcherTab mutation channel (F-S2-001)', () => {
  test('AF.1.1 — Preview: POST /api/stitch_editor/preview via pathappPatch; M1 snapshot fires before; body has auto-injected scope keys', async ({ page }) => {
    await mockStitcherJob(page);
    const snapReqs: Request[] = [];
    const previewReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapReqs.push(req);
      if (req.url().includes('/api/stitch_editor/preview')) previewReqs.push(req);
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/stitch_editor/preview', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ preview_url: '/x', duration_ms: 1000, slot_durations: [1000] }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-stitcher"]');
    const previewBtn = page.locator('[data-testid="stitcher-preview-intro"]');
    await expect(previewBtn).toBeVisible();
    await expect(previewBtn).toBeEnabled();
    await previewBtn.click();

    await expect.poll(() => previewReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => snapReqs.length).toBeGreaterThanOrEqual(1);

    // M1 invariant: snapshot fires BEFORE the mutation.
    const tSnap = snapReqs[0]!.timing().startTime;
    const tPrev = previewReqs[0]!.timing().startTime;
    expect(tSnap).toBeLessThanOrEqual(tPrev);

    // Auto-injected scope keys per LD-461 (non-BG → event_id) + S5.5b/d
    // (scope_target_video / scope_video_role + scope_version + scope_event_id).
    const body = previewReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_target_video']).toBe('intro');
    expect(body['scope_video_role']).toBe('intro');
    expect(typeof body['scope_version']).toBe('number');
    // Original payload fields preserved (slot, name).
    expect(body['slot']).toBe('intro');
  });

  test('AF.1.2 — Bake: POST /api/stitch_editor/bake via pathappPatch; M1 snapshot fires before; auto-injected scope keys', async ({ page }) => {
    await mockStitcherJob(page);
    const snapReqs: Request[] = [];
    const bakeReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapReqs.push(req);
      if (req.url().includes('/api/stitch_editor/bake')) bakeReqs.push(req);
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/stitch_editor/bake/status**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          job_id: 'test-bake-job',
          status: 'done',
          result: { ok: true, bake_path: '/abs/baked.mp4', canonical_path: '/abs/baked.mp4' },
        }),
      });
    });
    await page.route('**/api/stitch_editor/bake', async (r) => {
      await r.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          job_id: 'test-bake-job',
          status: 'queued',
          submitted: true,
        }),
      });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-stitcher"]');
    const bakeBtn = page.locator('[data-testid="stitcher-bake-btn"]');
    await expect(bakeBtn).toBeVisible();
    await expect(bakeBtn).toBeEnabled();
    await bakeBtn.click();

    await expect.poll(() => bakeReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => snapReqs.length).toBeGreaterThanOrEqual(1);
    const tSnap = snapReqs[0]!.timing().startTime;
    const tBake = bakeReqs[0]!.timing().startTime;
    expect(tSnap).toBeLessThanOrEqual(tBake);

    const body = bakeReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_target_video']).toBe('intro');
    expect(body['scope_video_role']).toBe('intro');
    expect(typeof body['scope_version']).toBe('number');
    // Original payload preserved.
    expect(body['name']).toBeDefined();
  });

  test('AF.1.3 — Save Job (ambient bed change): POST /api/stitch_editor/job via pathappPatch; M1 snapshot fires before; auto-injected scope keys', async ({ page }) => {
    await mockStitcherJob(page);
    // F-AMBIENT-001 — Stitcher now fetches the ambient catalog from
    // /api/phase_b/ambient_preset_list (replacing the pre-fix hardcoded
    // AMBIENT_BED_CHOICES constant). Pre-fix this test selected
    // 'warm_room_tone' (a fake hardcoded preset_id); post-fix that option
    // no longer exists, so we mock the catalog endpoint with a single
    // preset and select that. The test purpose is to verify mutation
    // routing (snapshot before save, auto-injected scope keys), not the
    // particular preset value.
    const ambientPresetId = 'meditation_pretty_v1';
    await page.route('**/api/phase_b/ambient_preset_list', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [{ preset_id: ambientPresetId, file_size_bytes: 1024 }],
          count: 1,
        }),
      });
    });
    const snapReqs: Request[] = [];
    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapReqs.push(req);
      // Match POST /api/stitch_editor/job EXACTLY (not /job/<name> which is the GET detail path).
      if (
        req.url().endsWith('/api/stitch_editor/job') ||
        req.url().includes('/api/stitch_editor/job?')
      ) {
        if (req.method() === 'POST') saveJobReqs.push(req);
      }
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    // Match POST to /api/stitch_editor/job (NOT the templated /job/<name> GET).
    await page.route(/\/api\/stitch_editor\/job$/, async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-stitcher"]');
    const ambientSelect = page.locator('[data-testid="stitcher-amb-intro"]');
    await expect(ambientSelect).toBeVisible();
    await expect(ambientSelect).toBeEnabled({ timeout: 10_000 });
    // Wait for the fetched preset option to appear before selecting.
    await expect(
      ambientSelect.locator(`option[value="${ambientPresetId}"]`),
    ).toHaveCount(1, { timeout: 5_000 });
    await ambientSelect.selectOption(ambientPresetId);

    await expect.poll(() => saveJobReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => saveJobReqs.some((req) => {
      const slots = (req.postDataJSON() as Record<string, unknown>)['slots'] as
        | Record<string, { ambient_bed?: string }>
        | undefined;
      return slots?.intro?.ambient_bed === ambientPresetId;
    }), { timeout: 5_000 }).toBe(true);
    const ambientSaveIdx = saveJobReqs.findIndex((req) => {
      const slots = (req.postDataJSON() as Record<string, unknown>)['slots'] as
        | Record<string, { ambient_bed?: string }>
        | undefined;
      return slots?.intro?.ambient_bed === ambientPresetId;
    });
    await expect.poll(() => snapReqs.length).toBeGreaterThanOrEqual(1);
    const tSnap = snapReqs[0]!.timing().startTime;
    const tSave = saveJobReqs[ambientSaveIdx]!.timing().startTime;
    expect(tSnap).toBeLessThanOrEqual(tSave);

    const body = saveJobReqs[ambientSaveIdx]!.postDataJSON() as Record<string, unknown>;
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_target_video']).toBe('intro');
    expect(body['scope_video_role']).toBe('intro');
    expect(typeof body['scope_version']).toBe('number');
    const slots = body['slots'] as Record<string, { ambient_bed?: string }>;
    expect(slots?.intro?.ambient_bed).toBe(ambientPresetId);
  });

  test('AF.1.4 — Preview HTTP 409 → emits mn:scope-mismatch window event (LD-456)', async ({ page }) => {
    await mockStitcherJob(page);
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/stitch_editor/preview', async (r) => {
      await r.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: false,
          error_code: 'SCOPE_MISMATCH',
          error_message: 'scope_event_id mismatch',
          retry_safe: false,
          hint: 'Reload the tab to re-resolve.',
        }),
      });
    });

    await gotoApp(page);
    await page.evaluate(() => {
      (window as unknown as { __mn_mismatch?: unknown[] }).__mn_mismatch = [];
      window.addEventListener('mn:scope-mismatch', (e: Event) => {
        const ce = e as CustomEvent;
        ((window as unknown as { __mn_mismatch: unknown[] }).__mn_mismatch).push(ce.detail);
      });
    });
    await page.click('[data-testid="tab-stitcher"]');
    await page.locator('[data-testid="stitcher-preview-intro"]').click();

    await expect
      .poll(
        async () =>
          page.evaluate(
            () =>
              (window as unknown as { __mn_mismatch?: unknown[] }).__mn_mismatch?.length ?? 0,
          ),
        { timeout: 5_000 },
      )
      .toBeGreaterThanOrEqual(1);
    const detail = await page.evaluate(
      () =>
        (window as unknown as { __mn_mismatch?: Array<Record<string, unknown>> }).__mn_mismatch?.[0],
    );
    expect((detail as Record<string, unknown>)['error_code']).toBe('SCOPE_MISMATCH');
    expect((detail as Record<string, unknown>)['error_message']).toBe('scope_event_id mismatch');
  });

  test('AF.1.5 — Bake HTTP 423 → re-hydrate v2 event-state + retry once succeeds (LD-458/460)', async ({ page }) => {
    await mockStitcherJob(page);
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    let bakeCount = 0;
    await page.route('**/api/stitch_editor/bake/status**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          job_id: 'retry-bake-job',
          status: 'done',
          result: { ok: true, bake_path: '/abs/baked.mp4', canonical_path: '/abs/baked.mp4' },
        }),
      });
    });
    await page.route('**/api/stitch_editor/bake', async (r) => {
      bakeCount += 1;
      if (bakeCount === 1) {
        await r.fulfill({
          status: 423,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'event_changed_mid_job' }),
        });
      } else {
        await r.fulfill({
          status: 202,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            job_id: 'retry-bake-job',
            status: 'queued',
            submitted: true,
          }),
        });
      }
    });
    let rehydrateCount = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      rehydrateCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ _module_version: 1, videos: { intro: { beats: {} } } }),
      });
    });

    await gotoApp(page);
    await page.evaluate(() => {
      (window as unknown as { __mn_evt?: unknown[] }).__mn_evt = [];
      window.addEventListener('mn:event-changed', (e: Event) => {
        const ce = e as CustomEvent;
        ((window as unknown as { __mn_evt: unknown[] }).__mn_evt).push(ce.detail);
      });
    });
    await page.click('[data-testid="tab-stitcher"]');
    await page.locator('[data-testid="stitcher-bake-btn"]').click();

    await expect.poll(() => bakeCount, { timeout: 7_000 }).toBeGreaterThanOrEqual(2);
    expect(rehydrateCount).toBeGreaterThanOrEqual(1);
    const events = await page.evaluate(
      () =>
        (window as unknown as { __mn_evt?: Array<Record<string, unknown>> }).__mn_evt,
    );
    const phases = (events ?? []).map((d) => (d as Record<string, unknown>)['phase']);
    expect(phases).toContain('before-retry');
    expect(phases).toContain('after-retry');
  });
});

// =============================================================================
// AF.2 — VideoSelector (F-S2-002): 2 raw fetches → pathappPatch
// =============================================================================

test.describe('AF.2 — VideoSelector mutation channel (F-S2-002)', () => {
  test('AF.2.1 — set_active: POST /api/video/set_active via pathappPatch; M1 snapshot fires before; auto-injected scope keys', async ({ page }) => {
    await mockVideoList(
      page,
      [
        { video_role: 'intro', has_beats: true, beat_count: 1 },
        { video_role: 'resolution', has_beats: false, beat_count: 0 },
      ],
      'intro',
    );
    const snapReqs: Request[] = [];
    const setActiveReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapReqs.push(req);
      if (req.url().includes('/api/video/set_active')) setActiveReqs.push(req);
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/video/set_active', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, event_id: 'Event_e2e_fixture', active_video: 'resolution' }),
      });
    });

    await gotoApp(page);
    const select = page.locator('[data-testid="video-select"]');
    await expect(select).toBeVisible();
    await select.selectOption('resolution');

    await expect.poll(() => setActiveReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => snapReqs.length).toBeGreaterThanOrEqual(1);
    const tSnap = snapReqs[0]!.timing().startTime;
    const tSet = setActiveReqs[0]!.timing().startTime;
    expect(tSnap).toBeLessThanOrEqual(tSet);

    const body = setActiveReqs[0]!.postDataJSON() as Record<string, unknown>;
    // video_set_active is non-BG → scopeKey='event_id' per LD-461.
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_target_video']).toBeDefined();
    expect(body['scope_video_role']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');
    // Original payload preserved.
    expect(body['video_role']).toBe('resolution');
  });

  test('AF.2.2 — create: POST /api/video/create via pathappPatch; M1 snapshot fires before; auto-injected scope keys', async ({ page }) => {
    await mockVideoList(page, [{ video_role: 'intro', has_beats: true, beat_count: 1 }], 'intro');
    const snapReqs: Request[] = [];
    const createReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot')) snapReqs.push(req);
      if (req.url().includes('/api/video/create')) createReqs.push(req);
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/video/create', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, event_id: 'Event_e2e_fixture', video_role: 'resolution' }),
      });
    });

    await gotoApp(page);
    const addBtn = page.locator('[data-testid="video-add-new"]');
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toBeEnabled();
    await addBtn.click();

    await expect.poll(() => createReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    await expect.poll(() => snapReqs.length).toBeGreaterThanOrEqual(1);
    const tSnap = snapReqs[0]!.timing().startTime;
    const tCreate = createReqs[0]!.timing().startTime;
    expect(tSnap).toBeLessThanOrEqual(tCreate);

    const body = createReqs[0]!.postDataJSON() as Record<string, unknown>;
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_event_id']).toBeDefined();
    expect(body['scope_target_video']).toBeDefined();
    expect(body['scope_video_role']).toBeDefined();
    expect(typeof body['scope_version']).toBe('number');
    // Original payload preserved.
    expect(body['video_role']).toBe('resolution');
    // video_label is null per the create call.
    expect(body['video_label']).toBeNull();
  });

  test('AF.2.3 — set_active scope-key shape (LD-461 + S5.5b/d auto-injection contract)', async ({ page }) => {
    // Specific contract test: every auto-injected key is present + correctly named.
    await mockVideoList(
      page,
      [
        { video_role: 'intro', has_beats: true, beat_count: 1 },
        { video_role: 'resolution', has_beats: true, beat_count: 1 },
      ],
      'intro',
    );
    const setActiveReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/video/set_active')) setActiveReqs.push(req);
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/video/set_active', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, active_video: 'resolution' }),
      });
    });

    await gotoApp(page);
    await page.locator('[data-testid="video-select"]').selectOption('resolution');
    await expect.poll(() => setActiveReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = setActiveReqs[0]!.postDataJSON() as Record<string, unknown>;
    // Contract-level assertion: ALL auto-inject keys present.
    // LD-461: scope pin is scope_event_id only — not top-level event_id.
    const keys = new Set(Object.keys(body));
    for (const k of [
      'scope_event_id',
      'scope_target_video',
      'scope_video_role',
      'scope_version',
    ]) {
      expect(keys.has(k)).toBe(true);
    }
  });

  test('AF.2.4 — set_active HTTP 423 → re-hydrate + retry once succeeds (LD-458/460)', async ({ page }) => {
    await mockVideoList(
      page,
      [
        { video_role: 'intro', has_beats: true, beat_count: 1 },
        { video_role: 'resolution', has_beats: true, beat_count: 1 },
      ],
      'intro',
    );
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    let setActiveCount = 0;
    await page.route('**/api/video/set_active', async (r) => {
      setActiveCount += 1;
      if (setActiveCount === 1) {
        await r.fulfill({
          status: 423,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'event_changed_mid_job' }),
        });
      } else {
        await r.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, active_video: 'resolution' }),
        });
      }
    });
    let rehydrateCount = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      rehydrateCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ _module_version: 1, videos: { intro: { beats: {} } } }),
      });
    });

    await gotoApp(page);
    await page.evaluate(() => {
      (window as unknown as { __mn_evt?: unknown[] }).__mn_evt = [];
      window.addEventListener('mn:event-changed', (e: Event) => {
        const ce = e as CustomEvent;
        ((window as unknown as { __mn_evt: unknown[] }).__mn_evt).push(ce.detail);
      });
    });
    await page.locator('[data-testid="video-select"]').selectOption('resolution');

    await expect.poll(() => setActiveCount, { timeout: 7_000 }).toBeGreaterThanOrEqual(2);
    expect(rehydrateCount).toBeGreaterThanOrEqual(1);
    const events = await page.evaluate(
      () => (window as unknown as { __mn_evt?: Array<Record<string, unknown>> }).__mn_evt,
    );
    const phases = (events ?? []).map((d) => (d as Record<string, unknown>)['phase']);
    expect(phases).toContain('before-retry');
    expect(phases).toContain('after-retry');
  });
});

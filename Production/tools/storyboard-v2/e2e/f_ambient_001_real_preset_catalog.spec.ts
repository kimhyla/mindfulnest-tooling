// F-AMBIENT-001 (prod_blockers id=118) — Ambient bed dropdowns surface a real
// catalog instead of an empty list (Phase A/B) or hardcoded fakes (Stitcher).
//
// Two coupled root causes:
//
//   A. Server scans the wrong directory.
//      `production_server.py:_handle_phase_b_ambient_preset_list` resolves
//      `Path(__file__).resolve().parent.parent / "audio_library" / "ambient"`
//      → `Production/audio_library/ambient/` which does NOT exist. Canonical
//      ambient assets live at `Production/assets/sound_library/ambient/`
//      (same convention used by `_handle_stitch_library` at line 15531).
//      Endpoint silently returns {ok: true, items: [], count: 0}.
//
//   B. Stitcher hardcodes fake AMBIENT_BED_CHOICES.
//      `StitcherTab.tsx:60-66` exports a constant of 4 fake preset_ids
//      (gentle_forest / soft_chimes / warm_room_tone / water_stream) that
//      do not resolve to any file on disk. Selecting any of them in
//      production fails at audio assembly. Phase B/A (PhaseProducer.tsx)
//      already fetches /api/phase_b/ambient_preset_list correctly — they
//      auto-recover once root cause A is fixed.
//
// This RED spec encodes 3 assertions per the brief:
//
//   1. Server endpoint test — GET /api/phase_b/ambient_preset_list returns
//      ≥3 items including the 3 known canonical preset_ids.
//   2. Phase B UI test — Ambient dropdown renders <option value> for each
//      of the 3 real preset_ids.
//   3. Stitcher UI test — Ambient dropdown contains the 3 real preset_ids
//      and does NOT contain any of the fake hardcoded preset_ids.
//
// Fixture seeding: beforeAll creates `Production/assets/sound_library/ambient/`
// (if missing) and writes 3 stub mp3 files matching the canonical names.
// The endpoint handler only checks `.suffix == ".mp3"` and `.stat().st_size`
// (no content decode), so empty stubs satisfy the contract. afterAll removes
// only the files we created.
//
// Pattern: cribbed from e2e/s5_5f_smoke.spec.ts (page.route mocks, gotoApp,
// openPhaseB) and e2e/architectural_fix.spec.ts (mockStitcherJob).

import { test, expect, type Page } from '@playwright/test';
import { mkdirSync, writeFileSync, unlinkSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname_spec = dirname(__filename);

// Resolve repo root: e2e/<spec>.ts → ../../../.. (mindfulnest-tooling/)
const repoRoot = resolve(__dirname_spec, '..', '..', '..', '..');
const ambientDir = resolve(repoRoot, 'Production', 'assets', 'sound_library', 'ambient');

// Three canonical preset_ids per the brief. Names matter: the F-AMBIENT-001
// fix is verified end-to-end against these specific ids. If Kim adds a new
// preset later, the test still passes (assertion uses .includes(), not equality).
const CANONICAL_PRESETS = [
  'ambient_silent_60s',
  'meditation_fireplace_v1',
  'meditation_pretty_v1',
] as const;

// Fake preset_ids that StitcherTab hardcoded pre-fix. The Stitcher refactor
// must purge them from the rendered dropdown. We only check labels/values
// the Select renders — these are FROM the hardcoded constant, not the server
// response, so the assertion proves the hardcoded list is gone.
const FAKE_HARDCODED_PRESETS = [
  'gentle_forest',
  'soft_chimes',
  'warm_room_tone',
  'water_stream',
] as const;

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function openPhaseB(page: Page): Promise<void> {
  await page.click('[data-testid="tab-phase-b"]');
  await expect(page.locator('[data-testid="pane-phase-b"]')).toBeVisible();
  // PhaseProducer is always-open (collapse removed 2026-05-25, commit b6ac706).
  // No summary/details expansion needed — full content is immediately visible.
  await expect(page.locator('[data-testid="phase-producer-b"]')).toBeVisible();
}

/**
 * Mock the StitcherTab's job-list and job-detail reads so the 4 slot
 * <select>s render. Without this mock, the StitcherTab shows the
 * "No active stitch job" empty state and the dropdown isn't even present.
 *
 * One slot ("intro") with a video_path is enough for the dropdown to
 * un-disable (`disabled={busy || !slot?.video_path}` in StitcherTab.tsx).
 */
async function mockStitcherJob(
  page: Page,
  jobName = 'phase_a_Event_e2e_fixture',
): Promise<void> {
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
        job: {
          name: jobName,
          slots: {
            intro: { video_path: '/abs/path/intro.mp4', ambient_bed: '' },
          },
          transitions: [],
        },
      }),
    });
  });
}

test.describe('F-AMBIENT-001 — real ambient preset catalog (server + Phase B + Stitcher)', () => {
  // Track files we created so afterAll only removes our seeds, not anything
  // else that might be in the dir.
  const seededFiles: string[] = [];

  test.beforeAll(() => {
    // `mkdirSync` with recursive:true is idempotent (no TOCTOU).
    mkdirSync(ambientDir, { recursive: true });
    for (const presetId of CANONICAL_PRESETS) {
      const filePath = resolve(ambientDir, `${presetId}.mp3`);
      // Atomic exclusive create — eliminates the check-then-act race that
      // CodeQL flags on `existsSync` + `writeFileSync`. If another process
      // (or a stale pre-existing file) holds the path, EEXIST is thrown and
      // we deliberately skip tracking it for cleanup so we never delete
      // files we didn't create.
      try {
        writeFileSync(filePath, Buffer.alloc(0), { flag: 'wx' });
        seededFiles.push(filePath);
      } catch (err: unknown) {
        if ((err as NodeJS.ErrnoException)?.code !== 'EEXIST') throw err;
      }
    }
    // eslint-disable-next-line no-console
    console.log(
      `[f_ambient_001] seeded ${seededFiles.length} stub mp3(s) at ${ambientDir}`,
    );
  });

  test.afterAll(() => {
    for (const filePath of seededFiles) {
      // Atomic delete — if the file is already gone (another runner / manual
      // cleanup) we swallow ENOENT instead of check-then-delete races.
      try {
        unlinkSync(filePath);
      } catch (err: unknown) {
        if ((err as NodeJS.ErrnoException)?.code !== 'ENOENT') throw err;
      }
    }
    // eslint-disable-next-line no-console
    console.log(`[f_ambient_001] removed ${seededFiles.length} seeded stub mp3(s)`);
  });

  // --------------------------------------------------------------------------
  // Assertion 1: Server endpoint
  // --------------------------------------------------------------------------

  test('Assertion 1 — GET /api/phase_b/ambient_preset_list returns the 3 canonical presets', async ({ request }) => {
    const res = await request.get('/api/phase_b/ambient_preset_list');
    expect(
      res.status(),
      'F-AMBIENT-001(A): /api/phase_b/ambient_preset_list must return 200.',
    ).toBe(200);
    const body = (await res.json()) as { ok: boolean; items?: Array<{ preset_id: string }> };
    expect(body.ok).toBe(true);
    const items = body.items ?? [];
    const presetIds = items.map((i) => i.preset_id);

    expect(
      items.length,
      `F-AMBIENT-001(A): expected at least 3 ambient presets after seeding ` +
      `${ambientDir}, got ${items.length}. The server is likely scanning the ` +
      `legacy "audio_library/ambient" path; canonical convention is ` +
      `"assets/sound_library/ambient" (see _handle_stitch_library:15531). ` +
      `preset_ids returned: ${JSON.stringify(presetIds)}`,
    ).toBeGreaterThanOrEqual(3);

    for (const expected of CANONICAL_PRESETS) {
      expect(
        presetIds,
        `F-AMBIENT-001(A): expected preset_id "${expected}" in the catalog, ` +
        `got: ${JSON.stringify(presetIds)}`,
      ).toContain(expected);
    }
  });

  // --------------------------------------------------------------------------
  // Assertion 2: Phase B UI dropdown
  // --------------------------------------------------------------------------

  test('Assertion 2 — Phase B Ambient dropdown lists the 3 real presets (no client mock)', async ({ page }) => {
    // Intentionally do NOT mock /api/phase_b/ambient_preset_list — Phase B
    // already fetches it correctly via PhaseProducer.tsx:161, so this test
    // exercises the real server response (which depends on root cause A).
    await gotoApp(page);
    await openPhaseB(page);

    const select = page.locator('[data-testid="phase-b-ambient-preset-select"]');
    await expect(select).toBeVisible();

    for (const presetId of CANONICAL_PRESETS) {
      await expect(
        select.locator(`option[value="${presetId}"]`),
        `F-AMBIENT-001(B-PhaseB): Phase B Ambient dropdown missing preset "${presetId}". ` +
        `PhaseProducer fetches /api/phase_b/ambient_preset_list correctly; if ` +
        `this fails, root cause A (server path) is unfixed.`,
      ).toHaveCount(1);
    }
  });

  // --------------------------------------------------------------------------
  // Assertion 3: Stitcher UI dropdown — real presets in, fake names out
  // --------------------------------------------------------------------------

  test('Assertion 3 — Stitcher Ambient dropdown lists real presets and excludes fake hardcoded names', async ({ page }) => {
    await mockStitcherJob(page);
    // Same intentional non-mock as Assertion 2: the Stitcher refactor must
    // populate its dropdown from the live endpoint, NOT a hardcoded constant.
    await gotoApp(page);

    await page.click('[data-testid="tab-stitcher"]');
    await expect(page.locator('[data-testid="pane-stitcher"]')).toBeVisible();

    const select = page.locator('[data-testid="stitcher-amb-intro"]');
    await expect(select).toBeVisible();

    // Wait for the post-refactor fetch to populate options. We poll for the
    // first canonical preset_id to land. Pre-refactor, this option will
    // never appear (hardcoded constant has no overlap with canonical names).
    await expect(
      select.locator(`option[value="${CANONICAL_PRESETS[0]}"]`),
      `F-AMBIENT-001(C-Stitcher): Stitcher Ambient dropdown is missing the ` +
      `real preset "${CANONICAL_PRESETS[0]}". The Stitcher must replace the ` +
      `hardcoded AMBIENT_BED_CHOICES constant with a fetch of ` +
      `/api/phase_b/ambient_preset_list (pattern: PhaseProducer.tsx:154-176).`,
    ).toHaveCount(1, { timeout: 10_000 });

    for (const presetId of CANONICAL_PRESETS) {
      await expect(
        select.locator(`option[value="${presetId}"]`),
        `F-AMBIENT-001(C-Stitcher): Stitcher Ambient dropdown missing preset "${presetId}".`,
      ).toHaveCount(1);
    }

    // Negative assertion — fake hardcoded preset_ids must NOT appear after
    // the refactor. Pre-refactor, all 4 of them DO appear (proving the
    // hardcoded constant is still in play).
    for (const fake of FAKE_HARDCODED_PRESETS) {
      await expect(
        select.locator(`option[value="${fake}"]`),
        `F-AMBIENT-001(C-Stitcher): Stitcher Ambient dropdown still contains ` +
        `the fake hardcoded preset "${fake}". The hardcoded AMBIENT_BED_CHOICES ` +
        `constant must be deleted entirely from StitcherTab.tsx.`,
      ).toHaveCount(0);
    }

    // The "— none —" option must remain present so users can clear a slot's
    // ambient bed. The refactor prepends it to the fetched list.
    await expect(
      select.locator('option[value=""]'),
      'F-AMBIENT-001(C-Stitcher): the empty/no-selection option (value="") ' +
      'must remain in the Stitcher Ambient dropdown after the refactor so ' +
      'users can clear a slot\'s ambient bed.',
    ).toHaveCount(1);
  });
});

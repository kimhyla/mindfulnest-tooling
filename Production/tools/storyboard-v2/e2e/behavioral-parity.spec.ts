// Behavioral-parity suite — Session 2 v3.1.
//
// Covers the 31 unique behaviors in
// Production/docs/PATCH_BEHAVIORAL_PARITY_AUDIT_v1.md (24 v58 patches deduped).
//
// Test types:
//   * `test(...)`  — v59 implements the behavior; assertion is real.
//   * `test.fixme(...)` — v59 doesn't yet implement (S3 polish); test is
//     written but skipped. The fixme description names the gap so it's
//     clear why and what S3 needs to add.
//   * Structural-eliminated rows (26, 27, 31): assertion proves v59's
//     architectural fix held (no parent-relative selectors, no wrap-chain
//     workarounds in code).

import { test, expect, request, type Page, type Request } from '@playwright/test';
import { SERVER } from './testServer';
import { protectBeatText, FIXTURE_EVENT, openStoryboardPane } from './helpers';

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

async function gotoApp(page: Page) {
  // Capture console errors so we can fail tests on Preact render errors.
  page.on('pageerror', (err) => {
    // Surface in test output; don't auto-fail (some tests intentionally
    // probe error paths).
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

async function gotoStoryboard(page: Page) {
  page.on('pageerror', (err) => {
    console.warn('[pageerror]', err.message);
  });
  await openStoryboardPane(page);
}

async function waitForBeats(page: Page) {
  await expect(page.locator('[data-testid="beat-list"]')).toBeVisible({ timeout: 10000 });
  return page.locator('[data-testid^="beat-card-"]');
}

// ----------------------------------------------------------------
// Category: dialogue (rows 1-4, 14, 25)
// ----------------------------------------------------------------

test.describe('parity / dialogue', () => {
  test('row 1a — save indicator goes saving -> saved on blur', async ({ page, request }) => {
    await using _r = await protectBeatText(request, 'beat_01');
    await gotoStoryboard(page);
    const beats = await waitForBeats(page);
    expect(await beats.count()).toBeGreaterThan(0);
    const text = page.locator('[data-testid="beat-text-0"]');
    const indicator = page.locator('[data-testid="beat-save-0"]');
    await text.click();
    await text.pressSequentially(' [v59-test-suffix]', { delay: 5 });
    // Tab away to blur.
    await page.keyboard.press('Tab');
    // Indicator should briefly be saving, then saved.
    await expect(indicator).toHaveAttribute('data-save-status', /saving|saved/, { timeout: 5000 });
    await expect(indicator).toHaveAttribute('data-save-status', 'saved', { timeout: 10000 });
  });

  test('row 1b — save indicator stays idle when text unchanged on blur', async ({ page }) => {
    await gotoStoryboard(page);
    await waitForBeats(page);
    const text = page.locator('[data-testid="beat-text-0"]');
    const indicator = page.locator('[data-testid="beat-save-0"]');
    await text.click();
    await page.keyboard.press('Tab');
    // No actual change — indicator should be idle (not saving).
    await expect(indicator).not.toHaveAttribute('data-save-status', 'saving');
  });

  test('row 4 — pathappPatch sends scope_version, not expected_version', async ({ page, request }) => {
    await using _r = await protectBeatText(request, 'beat_02');
    await gotoStoryboard(page);
    await waitForBeats(page);
    const requests: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/beat/update_text')) requests.push(req);
    });
    const text = page.locator('[data-testid="beat-text-1"]');
    await text.click();
    await text.pressSequentially(' x', { delay: 5 });
    await page.keyboard.press('Tab');
    // Wait for the request.
    await expect.poll(() => requests.length, { timeout: 10000 }).toBeGreaterThan(0);
    const body = requests[0]!.postDataJSON() as Record<string, unknown>;
    // We send scope_version (S1.5 v3.1 contract); we do NOT send expected_version.
    expect(body['scope_version']).toBeDefined();
    expect(body['expected_version']).toBeUndefined();
  });

  test('row 14 — module-patch endpoint is in MUTATION_ENDPOINTS catalog', async ({ page }) => {
    await gotoApp(page);
    // The endpoint exists in the bundle — assert by probing /api/v2/module/patch
    // returns 400 (missing field) not 404, proving the route is wired.
    const ctx = await request.newContext();
    const res = await ctx.post(`${SERVER}/api/v2/module/patch`, {
      data: { event_id: 'Event_1' },
    });
    expect([400, 409, 422]).toContain(res.status());
  });

  test('row 25a — localStorage shadow on keystroke', async ({ page, request }) => {
    await using _r = await protectBeatText(request, 'beat_03');
    await gotoStoryboard(page);
    await waitForBeats(page);
    const text = page.locator('[data-testid="beat-text-2"]');
    await text.click();
    await text.pressSequentially(' shadow-test', { delay: 5 });
    // Don't blur. Read localStorage.
    const beatId = await page.locator('[data-testid="beat-card-2"]').getAttribute('data-beat-id');
    const stored = await page.evaluate(
      ({ bid, eventId }) => localStorage.getItem(`mn:v59:dialogue-shadow:${eventId}:${bid}`),
      { bid: beatId, eventId: FIXTURE_EVENT },
    );
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored!);
    expect(typeof parsed.text).toBe('string');
    expect(parsed.text.includes('shadow-test')).toBe(true);
  });

  test('row 25b — localStorage shadow cleared after successful save', async ({ page, request }) => {
    await using _r = await protectBeatText(request, 'beat_02');
    await gotoStoryboard(page);
    await waitForBeats(page);
    const text = page.locator('[data-testid="beat-text-1"]');
    const beatId = await page.locator('[data-testid="beat-card-1"]').getAttribute('data-beat-id');
    await text.click();
    await text.pressSequentially(' clear-test', { delay: 5 });
    await page.keyboard.press('Tab');
    await expect(page.locator('[data-testid="beat-save-1"]')).toHaveAttribute('data-save-status', 'saved', { timeout: 10000 });
    const stored = await page.evaluate(
      ({ bid, eventId }) => localStorage.getItem(`mn:v59:dialogue-shadow:${eventId}:${bid}`),
      { bid: beatId, eventId: FIXTURE_EVENT },
    );
    expect(stored).toBeNull();
  });

  test.fixme('row 2 — global save toast (top-right)', async () => {
    // S3 polish — global toast component subscribed to save-state events.
    // Per-row indicator shipped in S2; global toast deferred.
  });

  test.fixme('row 3 — skip_tts_regen flag on [pause] tag click', async () => {
    // S3 polish — pause-tag click handler with TTS regen suppression.
  });
});

// ----------------------------------------------------------------
// Category: library (rows 5, 22, 26-30)
// ----------------------------------------------------------------

test.describe('parity / library', () => {
  test('library panel renders ≥1 item from real /api/cr/library', async ({ page }) => {
    await gotoApp(page);
    await expect(page.locator('[data-testid="library-list"]')).toBeVisible({ timeout: 10000 });
    const count = await page.locator('[data-testid^="library-item-"]').count();
    expect(count).toBeGreaterThan(0);
  });

  test('row 26 — structural-eliminated: no body > selectors in v59 CSS', async () => {
    // Per LD-453 Rule 36 §36.1 + spec §3.4. v59 uses class-only selectors.
    // We assert the BUILT html has no `body > X` selector (the v58 fragility class).
    const ctx = await request.newContext();
    const html = await (await ctx.get(`${SERVER}/`)).text();
    // Canonical anti-pattern: `body > X` direct-child selector.
    expect(html).not.toMatch(/body\s*>\s*[a-zA-Z]/);
  });

  test('row 27 — structural-eliminated: library panel has its own offset (no nav-clip dependency)', async ({ page }) => {
    await gotoApp(page);
    const lib = page.locator('[data-testid="library-panel"]');
    await expect(lib).toBeVisible();
    // The component is a class-anchored sidebar in v59; assert it's a child
    // of the app-main grid (not body-level positioned).
    const inMain = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="library-panel"]');
      return el?.parentElement?.classList.contains('mn-app-main') ?? false;
    });
    expect(inMain).toBe(true);
  });

  test('row 29 — library sources tier sorted mtime desc by server', async () => {
    const ctx = await request.newContext();
    const data = (await (await ctx.get(`${SERVER}/api/cr/library`)).json()) as {
      images: Array<{ tier?: string; abs_path?: string }>;
    };
    const sources = (data.images ?? []).filter((it) => it.tier === 'source');
    expect(sources.length).toBeGreaterThan(0);
    // Server returns mtime-desc per LD-452. Spot-check by re-querying the
    // mtime of the first vs second; first should be >= second.
    if (sources.length >= 2) {
      const fs = await import('node:fs');
      const m0 = fs.statSync(sources[0]!.abs_path!).mtimeMs;
      const m1 = fs.statSync(sources[1]!.abs_path!).mtimeMs;
      expect(m0).toBeGreaterThanOrEqual(m1);
    }
  });

  test.fixme('row 5 — drag library image onto beat slot persists image_override', async () => {
    // S3 polish — drag-drop wiring + assign-image call.
  });

  test.fixme('row 22 — lib-drop accepted-thumb corner + zombie sibling clear', async () => {
    // S3 polish — beat slot DOM updates on lib drop.
  });

  test.fixme('row 28 — library scroll resets to top after upload', async () => {
    // S3 polish — upload flow not wired in v59 yet.
  });

  test.fixme('row 30 — library item delete control + idempotent 404', async () => {
    // S3 polish — per-item delete UI with confirm.
  });
});

// ----------------------------------------------------------------
// Category: crop (rows 17, 18, 23, 24)
// ----------------------------------------------------------------

test.describe('parity / crop', () => {
  test('cropper modal opens from cropper tab and shows save action', async ({ page }) => {
    await gotoApp(page);
    await page.click('[data-testid="tab-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toBeVisible();
    await expect(page.locator('[data-testid="cropper-save-btn"]')).toBeVisible();
  });

  test('cropper modal closes on backdrop click', async ({ page }) => {
    await gotoApp(page);
    await page.click('[data-testid="tab-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toBeVisible();
    await page.click('[data-testid="modal-close-cropper"]');
    await expect(page.locator('[data-testid="modal-cropper"]')).toHaveCount(0);
  });

  test.fixme('row 17 — cropper sidebar Add Image / Library buttons', async () => {
    // S3 polish — full cropper sidebar UX with library item routing.
  });

  test.fixme('row 18 — cropper sidebar on left of canvas (not overlapped)', async () => {
    // S3 polish — full cropper layout once canvas + sidebar exist.
  });

  test.fixme('row 23 — crop key bg_bg_ prefix sanitization', async () => {
    // S3 polish — crop fetch key normalization (currently no fetch wiring).
  });

  test.fixme('row 24 — Crop button on lib-dropped slot routes to cropper with target', async () => {
    // S3 polish — lib-drop → Crop button → cropper-modal with targetBeatId.
  });
});

// ----------------------------------------------------------------
// Category: preview (rows 6, 10-13, 16)
// ----------------------------------------------------------------

test.describe('parity / preview', () => {
  test.fixme('row 6 — A/B/C radio persists selected_option', async () => {});
  test.fixme('row 10 — lipsync stale badge + always-on resend + in-flight task_id', async () => {});
  test.fixme('row 11 — lipsync source_option mismatch forces Re-run', async () => {});
  test.fixme('row 12 — Move-to-A on B/C with toast', async () => {});
  test.fixme('row 13 — preview-stitched bar with snapshot + 40vh cap', async () => {});
  test.fixme('row 16 — Phase B/A panels + watercolor timeline (WaveSurfer)', async () => {});
});

// ----------------------------------------------------------------
// Category: timeline (rows 7-9)
// ----------------------------------------------------------------

test.describe('parity / timeline', () => {
  test.fixme('row 7 — trim slider default-max 60s + loadedmetadata re-clamp', async () => {});
  test.fixme('row 8 — Fade-after slider with -1=inherit', async () => {});
  test.fixme('row 9 — pause/image/speaker dropdowns + reorder + Add Line', async () => {});
});

// ----------------------------------------------------------------
// Category: bg (rows 19-21)
// ----------------------------------------------------------------

test.describe('parity / bg', () => {
  test('row 21-ish — BG accept-beats requires scope_event_id', async () => {
    const ctx = await request.newContext();
    const ok = await ctx.post(`${SERVER}/api/bg/accept-beats`, {
      data: {
        scope_event_id: FIXTURE_EVENT,
        scope_target_video: 'intro',
        beats: [],
        segment: 0,
      },
    });
    expect(ok.status()).toBe(200);
    const cross = await ctx.post(`${SERVER}/api/bg/accept-beats`, {
      data: { scope_event_id: 'Event_2', scope_target_video: 'intro', beats: [], segment: 0 },
    });
    expect(cross.status()).toBe(409);
  });

  test.fixme('row 19 — BG GPT/FLUX mode toggle + endpoint routing', async () => {});
  test.fixme('row 20 — BG + Add Beat between rows', async () => {});
  test.fixme('row 21 — two-click delete inline guard', async () => {});
});

// ----------------------------------------------------------------
// Category: ui_chrome (row 15)
// ----------------------------------------------------------------

test.describe('parity / ui_chrome', () => {
  test('row 15 — header is sticky-style (single layout root)', async ({ page }) => {
    await gotoApp(page);
    // The v59 layout puts header + tab bar in flex column with main below.
    // Assert the header is the first child of the app-root.
    const isFirstChild = await page.evaluate(() => {
      const root = document.querySelector('[data-testid="app-root"]');
      const banner = root?.querySelector('.mn-scope-banner');
      const header = root?.querySelector('.mn-app-header');
      // Header is either first or second (banner may precede it when error active).
      return root?.firstElementChild === header || (banner && root?.firstElementChild === banner);
    });
    expect(isFirstChild).toBe(true);
  });
});

// ----------------------------------------------------------------
// Category: other (row 31 — runtime healthcheck)
// ----------------------------------------------------------------

test.describe('parity / other', () => {
  test('row 31 — runtime healthcheck endpoint exists (continuity of telemetry)', async () => {
    const ctx = await request.newContext();
    // POST a benign healthcheck violation; should 200.
    const res = await ctx.post(`${SERVER}/api/patch_health`, {
      data: { patch: 'v59-parity-test', msg: 'smoke probe from behavioral-parity.spec.ts' },
    });
    expect(res.status()).toBe(200);
  });

  test('row 31b — structural-eliminated: v59 has no `var IN=` v58 marker', async () => {
    const ctx = await request.newContext();
    const html = await (await ctx.get(`${SERVER}/`)).text();
    expect(html).not.toContain('var IN=');
  });
});

// ----------------------------------------------------------------
// Category: export (handoff §6 + S2-T39)
// ----------------------------------------------------------------

test.describe('parity / export', () => {
  test('send-out actions render in storyboard footer', async ({ page }) => {
    await gotoStoryboard(page);
    await expect(page.locator('[data-testid="send-out-actions"]')).toBeVisible();
    await expect(page.locator('[data-testid="send-out-mp4-btn"]')).toBeVisible();
  });

  test('clicking Send Out fires scene assemble with scope keys', async ({ page }) => {
    await gotoStoryboard(page);
    const requests: Request[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/state/snapshot') || req.url().includes('/api/scene/assemble'))
        requests.push(req);
    });
    await page.click('[data-testid="send-out-mp4-btn"]');
    await expect.poll(() => requests.length, { timeout: 8000 }).toBeGreaterThanOrEqual(1);
    const assembleReq = requests.find((r) => r.url().includes('/api/scene/assemble'));
    expect(assembleReq).toBeDefined();
    const body = assembleReq!.postDataJSON() as Record<string, unknown>;
    expect(body['scope_event_id']).toBe(FIXTURE_EVENT);
  });
});

// ----------------------------------------------------------------
// Category: scope (LD-456/461 — every guarded handler)
// ----------------------------------------------------------------

test.describe('parity / scope', () => {
  test('scope chip renders with current event', async ({ page }) => {
    await gotoStoryboard(page);
    const chip = page.locator('[data-testid="storyboard-scope-chip"]');
    await expect(chip).toBeVisible();
    await expect(chip).toContainText(new RegExp(`${FIXTURE_EVENT}.*v\\d+`));
  });

  test('scope mismatch on assign-image returns 409', async () => {
    const ctx = await request.newContext();
    const res = await ctx.post(`${SERVER}/api/assign-image`, {
      data: { event_id: 'Event_2', beat: 'beat_01', image_key: 'fake' },
    });
    expect(res.status()).toBe(409);
    const body = (await res.json()) as { code?: string };
    expect(body.code).toBe('SCOPE_VALIDATION_V1');
  });

  test('legacy no-scope body rejected (LD-456 C-5 flip)', async () => {
    const ctx = await request.newContext();
    const res = await ctx.post(`${SERVER}/api/bg/accept-beats`, {
      data: { beats: [] },
    });
    expect([400, 409]).toContain(res.status());
  });
});

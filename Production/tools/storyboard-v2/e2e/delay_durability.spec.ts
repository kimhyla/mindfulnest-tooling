// Delay-Durability Regression — T-5..T-9
//
// Spec: V59_STORYBOARD_AUDIO_DELAY_DURABILITY_SPEC_v1.md §5.5 (prod_reference_docs id=225)
// LDs: BEAT_DELAY_DURABLE_HYDRATION_V1 (this fix) — supersedes LD-694/695/698.
//
// SUT note: server canonically persists audio_delay at
//   state.videos[role].beats[bid].phase_1.audio_delay
// The bootstrap response /api/v2/event/<id>/state returns the raw state.json
// (production_server.py L15411 `_handle_v2_event_state`). It does NOT flatten
// audio_delay to top-level — that flattening happens ONLY on the
// /api/animate_status polling endpoint (production_server.py L12943
// `_handle_animate_status`). The 2026-05-14 client fix (LD-694) read the
// flattened key on bootstrap, where it's undefined → slider always re-defaulted
// to 0.0 and audio always played at t=0.
//
// These tests pin the corrected read pattern:
//   beat.phase_1?.audio_delay ?? beat.audio_delay ?? beat.delay_seconds ?? 0
//
// Tests:
//   T-5 — BeatCard hydrates slider from nested phase_1.audio_delay
//   T-6 — Preview useEffect schedules setTimeout(ms) where ms = phase_1.audio_delay * 1000
//   T-7 — Real-browser PLAY honors persisted delay (audio paused for delay window, then plays)
//   T-8 — Reload durability: hard refresh re-reads persisted delay
//   T-9 — Lipsync sentinel (previewOptIdx === 0) plays raw — no synthetic lead-in (per spec §5.4 Kim Q1=α)

import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helpers — pin bootstrap to a nested phase_1.audio_delay shape
// ---------------------------------------------------------------------------

interface MockBeatOptions {
  audioDelay: number; // value at beat.phase_1.audio_delay
  withOptions?: boolean; // include phase_1.options[0] so preview-option-1 renders
  withLipsync?: boolean; // include beat.lipsync.file so preview-option-0 (sentinel) renders
  withFinal?: boolean; // include beat.final.file so lifecycle = 'final'
}

async function mockBootstrapWithNestedDelay(
  page: Page,
  opts: MockBeatOptions,
  beatId = 'beat_dd_01',
): Promise<void> {
  // Build a beat that hits 'selected' lifecycle (phase_1.options + selected_option
  // present, audio_file present) so preview-option-1 button is rendered. Per
  // StoryboardTab.tsx deriveBeatLifecycle: selected = options + selected_option set.
  const phase1: Record<string, unknown> = {
    audio_delay: opts.audioDelay,
  };
  if (opts.withOptions) {
    phase1.options = [{ file: 'animations/opt1_dd.mp4' }];
    phase1.selected_option = 0;
  }
  const beat: Record<string, unknown> = {
    speaker: 'Tessa',
    text: 'Delay-durability regression beat.',
    audio_file: `audio/${beatId}.mp3`,
    phase_1: phase1,
  };
  if (opts.withLipsync) {
    // Status must be 'completed' for the SUT to render the sentinel PLAY
    // button (StoryboardTab.tsx L515 gates on beat.lipsync?.status === 'completed').
    // Per LD STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1 (2026-05-17): the
    // button is additionally gated on freshness — lipsync.file_mtime must be
    // ≥ Date.parse(beat.audio_regenerated_at). When either field is missing,
    // the new computeLipsyncFreshness() helper has defensive defaults: if
    // file_mtime is absent it returns 'stale' (button disabled). T-9 clicks
    // the button, so the mock must include both file_mtime and
    // audio_regenerated_at with file_mtime >= audio_regenerated_at to keep
    // T-9 testing the lipsync-sentinel branch (NOT the new stale gate).
    const audioRegen = '2026-05-01T00:00:00Z';
    const lipsyncMtimeS = Math.floor(new Date('2026-05-10T00:00:00Z').getTime() / 1000);
    beat.audio_regenerated_at = audioRegen;
    beat.lipsync = {
      file: `lipsync/${beatId}_ls.mp4`,
      status: 'completed',
      file_mtime: lipsyncMtimeS,
    };
  }
  if (opts.withFinal) {
    beat.final = { file: `final/${beatId}_final.mp4` };
  }
  await page.route('**/api/v2/event/*/state', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        _module_version: 1,
        videos: {
          intro: {
            video_role: 'intro',
            video_label: 'Intro',
            beats: { [beatId]: beat },
          },
          resolution: { video_role: 'resolution', beats: {} },
        },
      }),
    });
  });
}

// Stub asset + audio endpoints so the <video> / <audio> elements don't 404
// (Playwright still wires the elements; we just need bytes that decode).
async function stubMediaEndpoints(page: Page): Promise<void> {
  // 1-frame silent MP4 + 1-sample silent MP3 are out of scope; route to empty
  // 200s. The DOM elements exist + receive src; calling .play() returns a
  // rejected promise we catch in the SUT.
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
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

// Install a setTimeout spy BEFORE the SUT mounts so we capture every scheduled
// timeout. The SUT's preview useEffect calls window.setTimeout(callback, ms);
// the spy stores [ms, callbackTag] for inspection. We avoid replacing the
// timer (so cleanup clearTimeout still works) — we just record.
async function installSetTimeoutSpy(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __delayTimeouts: number[]; __origSetTimeout: typeof setTimeout };
    w.__delayTimeouts = [];
    w.__origSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = ((fn: TimerHandler, ms?: number, ...args: unknown[]) => {
      // Only record positive non-trivial ms (filter out 0/undefined polling jitter).
      if (typeof ms === 'number' && ms > 50) {
        w.__delayTimeouts.push(ms);
      }
      return w.__origSetTimeout(fn as Parameters<typeof setTimeout>[0], ms, ...(args as []));
    }) as typeof window.setTimeout;
  });
}

async function readSetTimeoutSpy(page: Page): Promise<number[]> {
  return await page.evaluate(() => (window as unknown as { __delayTimeouts: number[] }).__delayTimeouts);
}

async function clearSetTimeoutSpy(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as { __delayTimeouts: number[] }).__delayTimeouts = [];
  });
}

// ---------------------------------------------------------------------------
// T-5 — Slider hydrates from nested phase_1.audio_delay
// ---------------------------------------------------------------------------

test.describe('Delay durability — T-5..T-9 (spec id=225)', () => {
  test('T-5 — slider hydrates from beat.phase_1.audio_delay (nested), not top-level', async ({ page }) => {
    await mockBootstrapWithNestedDelay(page, { audioDelay: 2.5, withOptions: true });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const slider = page.locator('[data-testid="beat-0-delay"]');
    await expect(slider).toBeVisible();
    // EXPECTED (post-fix): slider initialized from phase_1.audio_delay = "2.5"
    // PRE-FIX: top-level beat.audio_delay is undefined → slider falls through to "0.0"
    await expect(slider).toHaveValue('2.5');
  });

  // -------------------------------------------------------------------------
  // T-6 — Preview useEffect reads delay from nested path; schedules setTimeout
  // -------------------------------------------------------------------------
  test('T-6 — clicking preview option schedules setTimeout(ms) where ms = phase_1.audio_delay × 1000', async ({ page }) => {
    await installSetTimeoutSpy(page);
    await mockBootstrapWithNestedDelay(page, { audioDelay: 1.7, withOptions: true });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await clearSetTimeoutSpy(page); // discard any mount-time timeouts
    // Click preview on option 1 (sentinel 0 = lipsync; option 1 = first real option).
    await page.click('[data-testid="beat-0-preview-option-1"]');
    // Allow the useEffect to run.
    await page.waitForTimeout(120);
    const observed = await readSetTimeoutSpy(page);
    // EXPECTED (post-fix): a setTimeout was scheduled at ~1700ms.
    // PRE-FIX: beat.audio_delay is undefined → audioDelaySec = 0 → setTimeout
    //          branch is skipped entirely; aud.play() is called inline.
    expect(observed.some((ms) => Math.abs(ms - 1700) < 10)).toBe(true);
  });

  // -------------------------------------------------------------------------
  // T-7 — Dep-array re-fires when phase_1.audio_delay changes (in-session change)
  // -------------------------------------------------------------------------
  test('T-7 — in-session delay change triggers preview useEffect with new value', async ({ page }) => {
    await installSetTimeoutSpy(page);
    // Mock bootstrap returns delay=1.0 initially; second fetch (post-mutation)
    // returns delay=3.0. We swap the route mid-test.
    let phase = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      const delay = phase === 0 ? 1.5 : 3.0;
      // Two options so the test can flip previewOptIdx 1→2 to retrigger the
      // useEffect after the post-PATCH refetch (clicking the same option
      // toggles play/pause without dep-array change per handlePreviewOption
      // L613-625; only an optIdx CHANGE forces previewOptIdx state update +
      // useEffect re-fire).
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: {
            intro: {
              video_role: 'intro',
              video_label: 'Intro',
              beats: {
                beat_dd_07: {
                  speaker: 'Tessa',
                  text: 'T-7 dep-array.',
                  audio_file: 'audio/beat_dd_07.mp3',
                  phase_1: {
                    audio_delay: delay,
                    options: [
                      { file: 'animations/opt1_dd07.mp4' },
                      { file: 'animations/opt2_dd07.mp4' },
                    ],
                    selected_option: 0,
                  },
                },
              },
            },
            resolution: { video_role: 'resolution', beats: {} },
          },
        }),
      });
    });
    // Mock the PATCH endpoint that onApplyDelay hits via pathappPatch. The
    // exact endpoint resolves to /api/beat/delay per StoryboardTab.tsx L338.
    await page.route('**/api/beat/delay', async (route) => {
      phase = 1; // next /state fetch returns 3.0
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, beat: 'beat_dd_07', audio_delay: 3.0 }),
      });
    });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    // First preview at delay=1.5 — captures the baseline setTimeout(1500).
    // (Used to confirm the spy mechanism is working before the mutation.)
    await clearSetTimeoutSpy(page);
    await page.click('[data-testid="beat-0-preview-option-1"]');
    await page.waitForTimeout(150);
    const beforeMutation = await readSetTimeoutSpy(page);
    expect(beforeMutation.some((ms) => Math.abs(ms - 1500) < 10)).toBe(true);
    // Now mutate: fill slider to 3.0, click apply → server responds → refetch
    // → next BeatCard render carries phase_1.audio_delay = 3.0. The dep-array
    // fix is what makes the preview useEffect re-fire when previewOptIdx
    // changes from 1→2 while phase_1.audio_delay also changed from 1.5→3.0.
    await page.fill('[data-testid="beat-0-delay"]', '3.0');
    await page.click('[data-testid="beat-0-delay-apply"]');
    // Wait for the refetch's effect to land + new beat prop to propagate.
    await page.waitForTimeout(400);
    await clearSetTimeoutSpy(page);
    // Click option 2 (not option 1) — previewOptIdx flips 1→2 which is a
    // genuine state change (not a play/pause toggle). The useEffect re-fires
    // with the new previewOptIdx + new audio_delay → setTimeout(3000).
    await page.click('[data-testid="beat-0-preview-option-2"]');
    await page.waitForTimeout(200);
    const afterMutation = await readSetTimeoutSpy(page);
    // EXPECTED (post-fix): setTimeout scheduled at ~3000ms (the new value).
    // PRE-FIX (with dep array on undefined top-level keys): effect would not
    //          re-fire on phase_1.audio_delay change; even if it did, the read
    //          would still be undefined and audioDelaySec = 0 → no setTimeout.
    expect(afterMutation.some((ms) => Math.abs(ms - 3000) < 10)).toBe(true);
  });

  // -------------------------------------------------------------------------
  // T-8 — Reload durability: persisted delay survives a hard refresh
  // -------------------------------------------------------------------------
  test('T-8 — page.reload() preserves the persisted delay value in the slider', async ({ page }) => {
    // Use 2.5 (non-trailing-zero) so String() preserves the decimal — avoids
    // the JS `String(2.0)` === `"2"` collapse that would muddy the assertion.
    // The bug class we pin is wrong-PATH read; non-zero values prove the
    // canonical phase_1.audio_delay path is honored on bootstrap + reload.
    await mockBootstrapWithNestedDelay(page, { audioDelay: 2.5, withOptions: true });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await expect(page.locator('[data-testid="beat-0-delay"]')).toHaveValue('2.5');
    await page.reload();
    await page.click('[data-testid="tab-storyboard"]');
    // EXPECTED (post-fix): slider re-hydrates from nested phase_1.audio_delay = 2.5
    // PRE-FIX: top-level audio_delay undefined → re-defaults to 0.0
    await expect(page.locator('[data-testid="beat-0-delay"]')).toHaveValue('2.5');
  });

  // -------------------------------------------------------------------------
  // T-9 — Lipsync sentinel (previewOptIdx === 0): raw playback, no synthetic delay
  // -------------------------------------------------------------------------
  test('T-9 — preview-option-0 (lipsync sentinel) does NOT schedule a delay setTimeout (per spec §5.4 Q1=α)', async ({ page }) => {
    await installSetTimeoutSpy(page);
    await mockBootstrapWithNestedDelay(page, {
      audioDelay: 4.0, // even with a large persisted delay
      withOptions: true,
      withLipsync: true, // sentinel preview-option-0 must be available
    });
    await stubMediaEndpoints(page);
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await clearSetTimeoutSpy(page);
    // Click the lipsync-play button (sets previewOptIdx = 0 = sentinel). The
    // SUT testid is `beat-${index}-lipsync-play` (StoryboardTab.tsx L519),
    // NOT `preview-option-0` — option-0 is a logical sentinel value, not a
    // distinct button. The button is only rendered when beat.lipsync.status
    // === 'completed' (gated at L515).
    // The SUT branch `isLipsyncPreview` must skip the setTimeout-defer audio
    // branch entirely (audio is baked into the lipsync video; double-audio
    // is the bug LD-695 originally fixed). Per Kim Q1=α (spec §7), we DO
    // NOT add synthetic video-only lead-in on the lipsync raw preview either.
    await page.click('[data-testid="beat-0-lipsync-play"]');
    await page.waitForTimeout(120);
    const observed = await readSetTimeoutSpy(page);
    // EXPECTED (post-fix, unchanged behavior): NO ~4000ms setTimeout was
    // scheduled. (Other innocuous setTimeouts in the app might exist; the spy
    // filters ms > 50, so we just assert none match the delay window.)
    expect(observed.some((ms) => Math.abs(ms - 4000) < 50)).toBe(false);
  });
});

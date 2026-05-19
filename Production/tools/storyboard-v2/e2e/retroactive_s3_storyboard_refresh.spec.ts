// Retroactive Coverage Sprint — S3 StoryboardTab Refresh Logic Beyond R1
//
// Spec: STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md §3 S3
//
// R1 (proper-fix) covered scope-change re-fetch. These tests cover the OTHER
// refresh triggers that were previously untested:
//   1. After a beat-level mutation completes → BeatCard.onMutated bumps
//      refreshTick → /api/v2/event/<id>/state re-fires (StoryboardTab.tsx:859).
//   2. After a "magic complete" window message → refreshTick++ (lines 778-786).
//
// SUT note: spec §3 S3 says "after bg_finalize_beat / bg_unlock". Those
// endpoints did not survive into S5.5d v3; the equivalent close-the-loop
// mutations today are beat_use_as_final + select + lipsync.

import { test, expect, type Page } from '@playwright/test';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

// Hand-rolled v2 event-state mock that flips between two snapshots so we can
// observe the StoryboardTab refresh: first call returns "draft" beat, after
// the "select option" mutation, subsequent calls return "selected" beat.
function makeFlippingStateMock(beatId = 'beat_s3_01') {
  let phase: 'draft' | 'selected' = 'draft';
  const setPhase = (p: 'draft' | 'selected') => { phase = p; };
  const draft = {
    _module_version: 1,
    videos: {
      intro: {
        video_role: 'intro',
        video_label: 'Intro',
        beats: {
          [beatId]: {
            speaker: 'Tessa',
            text: 'Awaiting selection.',
            audio_file: 'audio/x.mp3',
            phase_1: { options: [{ file: 'a.mp4' }, { file: 'b.mp4' }, { file: 'c.mp4' }] },
          },
        },
      },
      resolution: { video_role: 'resolution', beats: {} },
    },
  };
  const selected = {
    _module_version: 1,
    videos: {
      intro: {
        video_role: 'intro',
        video_label: 'Intro',
        beats: {
          [beatId]: {
            speaker: 'Tessa',
            text: 'Awaiting selection.',
            audio_file: 'audio/x.mp3',
            phase_1: {
              selected_option: 2,
              options: [{ file: 'a.mp4' }, { file: 'b.mp4' }, { file: 'c.mp4' }],
            },
          },
        },
      },
      resolution: { video_role: 'resolution', beats: {} },
    },
  };
  return { setPhase, body: () => (phase === 'draft' ? draft : selected) };
}

test.describe('S3 — StoryboardTab refresh logic beyond R1', () => {
  test('S3.1 — after select-option mutation, StoryboardTab re-fetches v2/event-state and lifecycle moves draft→selected', async ({ page }) => {
    const mock = makeFlippingStateMock('beat_s3_01');
    let stateGetCount = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      stateGetCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mock.body()),
      });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/select', async (route) => {
      // Server completes the select; flip the mock so the next state read returns "selected".
      mock.setPhase('selected');
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('data-lifecycle', 'animated');
    const initialFetches = stateGetCount;
    // Fire select-option-2.
    await page.locator('[data-testid="beat-0-select-option-2"]').click();
    // After mutation: refreshTick++ → state re-fetches → lifecycle becomes "selected".
    await expect.poll(async () => row.getAttribute('data-lifecycle'), { timeout: 5_000 }).toBe('selected');
    expect(stateGetCount).toBeGreaterThan(initialFetches);
  });

  test('S3.2 — after beat_use_as_final mutation, StoryboardTab re-fetches and lifecycle moves selected→final', async ({ page }) => {
    let phase: 'selected' | 'final' = 'selected';
    const beatId = 'beat_s3_02';
    const stateOf = () => ({
      _module_version: 1,
      videos: {
        intro: {
          video_role: 'intro',
          beats: {
            [beatId]: {
              speaker: 'Tessa',
              text: 'Will go final.',
              audio_file: 'audio/x.mp3',
              phase_1: {
                selected_option: 1,
                options: [{ file: 'a.mp4' }],
              },
              ...(phase === 'final'
                ? { final: { source: 'use_as_final', source_option: 1, file: 'final.mp4', approved_at: '2026-05-04T10:00:00Z' } }
                : {}),
            },
          },
        },
        resolution: { video_role: 'resolution', beats: {} },
      },
    });
    let stateGetCount = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      stateGetCount += 1;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(stateOf()) });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/beat/use_as_final', async (route) => {
      phase = 'final';
      // Mock must mirror the REAL server response so the LD-778 expectField
      // gate ({status: 'ok', beat: string}) passes. Pre-LD-778 mocks used
      // minimal {"ok":true} bodies; after the 4-gate validation was added,
      // those silently fail the gate (no toast, but onMutated() never fires
      // and lifecycle never flips to 'final'). Real handler:
      // production_server.py _handle_use_as_final returns
      // {status: 'ok', beat, file, final}.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          beat: 'beat_01',
          file: 'beat_01_opt0.mp4',
          final: { source: 'raw_option', source_option: 0, file: 'beat_01_opt0.mp4' },
        }),
      });
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'selected');
    const initialFetches = stateGetCount;
    await page.locator('[data-testid="beat-0-use-as-final"]').click();
    await expect.poll(async () => row.getAttribute('data-lifecycle'), { timeout: 5_000 }).toBe('final');
    await expect(page.locator('[data-testid="beat-0-final-marker"]')).toBeVisible();
    expect(stateGetCount).toBeGreaterThan(initialFetches);
  });

  test('S3.3 — postMessage "mn-magic-or-animate-complete" bumps refreshTick → state re-fetches', async ({ page }) => {
    let stateGetCount = 0;
    let phase: 'draft' | 'magic_done' = 'draft';
    const stateOf = () => ({
      _module_version: 1,
      videos: {
        intro: {
          video_role: 'intro',
          beats: {
            beat_s3_03: {
              speaker: 'Tessa',
              text: 'Magic complete?',
              ...(phase === 'magic_done' ? { magic_still_path: 'magic/done.png' } : {}),
            },
          },
        },
        resolution: { video_role: 'resolution', beats: {} },
      },
    });
    await page.route('**/api/v2/event/*/state', async (route) => {
      stateGetCount += 1;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(stateOf()) });
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    await expect(page.locator('[data-testid="beat-card-0"]')).toBeVisible();
    const initialCount = stateGetCount;
    // Flip phase + post the magic-complete message.
    phase = 'magic_done';
    await page.evaluate(() => {
      window.postMessage({ type: 'mn-magic-or-animate-complete' }, '*');
    });
    // Re-fetch fires within 1s (debounce 200ms + a margin).
    await expect.poll(() => stateGetCount, { timeout: 5_000 }).toBeGreaterThan(initialCount);
  });

  test('S3.4 — after BG drag-drop accept-lib-image (mutation routed via pathappPatch), StoryboardTab does NOT re-fetch (the mutation is in BgTab; StoryboardTab only refreshes on its own beat mutations)', async ({ page }) => {
    // Negative invariant test: Storyboard refresh is local to its tab — mutations
    // initiated from BgTab should NOT incidentally trigger StoryboardTab fetches.
    let stateGetCount = 0;
    await page.route('**/api/v2/event/*/state', async (route) => {
      stateGetCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          _module_version: 1,
          videos: { intro: { video_role: 'intro', beats: { x: { speaker: 'T', text: 't' } } }, resolution: { video_role: 'resolution', beats: {} } },
        }),
      });
    });
    await page.route('**/api/bg/segments**', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"segments":[{"event_id":"E1","phase":"intro"}]}' });
    });
    await page.route('**/api/bg/session-state**', async (r) => {
      await r.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          active_context: { arc_number: 1, event_id: 'E1', phase: 'intro' },
          beats: [{ beat_id: 'b', dialogue_text: 't', speaker: 'T', status: 'ready', gpt_options: [], accepted_image_key: null }],
        }),
      });
    });
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/bg/accept-lib-image', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await gotoApp(page);
    // Visit storyboard once to load it (fires initial fetch).
    await page.click('[data-testid="tab-storyboard"]');
    await expect(page.locator('[data-testid="pane-storyboard"]')).toBeVisible();
    const baselineFetches = stateGetCount;
    // Switch to BG and trigger a drop.
    await page.click('[data-testid="tab-bg"]');
    const slot = page.locator('[data-testid="bg-option-0-0"]');
    await expect(slot).toBeVisible();
    await slot.evaluate((el: Element) => {
      const dt = new DataTransfer();
      const payload = JSON.stringify({ kind: 'lib-image', lib_key: 's3', tier: 'source', abs_path: '/tmp/s3.png', filename: 's3.png' });
      dt.setData('application/x-mn-drag', payload);
      dt.setData('text/plain', payload);
      el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
    });
    // Give the StoryboardTab effect plenty of time NOT to fire.
    await page.waitForTimeout(800);
    // Storyboard's fetch count must NOT have increased (BG mutation is isolated).
    expect(stateGetCount).toBe(baselineFetches);
  });
});

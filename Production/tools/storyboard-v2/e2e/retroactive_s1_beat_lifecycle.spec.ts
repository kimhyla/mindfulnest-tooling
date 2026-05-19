// Retroactive Coverage Sprint — S1 Beat Lifecycle State Machine
//
// Spec: STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md §3 S1
// LD: BEAT_LIFECYCLE_STATE_MACHINE_V1
//
// SUT note: spec §3 S1 references S5.5e endpoints (`_handle_bg_finalize_beat`,
// `_handle_bg_unlock_beat`) that did not survive into the S5.5d v3 architecture
// revision. Today the lifecycle is derived client-side in
// StoryboardTab.tsx::deriveBeatLifecycle() from beat fields:
//   draft → audio_generated → animated → selected → lipsync_pending → final
// `data-lifecycle` is exposed on `[data-testid="beat-button-row-{i}"]`.
//
// These tests cover that derivation + the visible button-set per state per
// the S5.5e §3.1 visibility table (now in StoryboardTab.tsx lines 240-246).

import { test, expect, type Page } from '@playwright/test';

const SERVER = 'http://localhost:5111';

async function gotoApp(page: Page): Promise<void> {
  page.on('pageerror', (err) => {
    // eslint-disable-next-line no-console
    console.warn('[pageerror]', err.message);
  });
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

// Mock the v2 event-state endpoint with a single beat of given shape so we
// can drive deriveBeatLifecycle deterministically. Returned beat goes into
// videos.intro.beats[beat_id] per S5.5d v3 partition shape.
async function mockEventStateWithBeat(
  page: Page,
  beat: Record<string, unknown>,
  beatId = 'beat_lc_01',
): Promise<void> {
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

test.describe('S1 — beat lifecycle state machine', () => {
  test('S1.1 — draft state: no audio_file → lifecycle="draft"; only Pipeline group + no Animate/Select/Lipsync', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Draft beat — no audio yet.',
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('data-lifecycle', 'draft');
    // Per §3.1 table: showAnimate is FALSE in draft. Animate button not in DOM.
    await expect(page.locator('[data-testid="beat-0-animate"]')).toHaveCount(0);
    // Select-option radios (showSelectedOptionRadios) not visible in draft.
    await expect(page.locator('[data-testid="beat-options-group-0"]')).toHaveCount(0);
    // Lipsync not visible in draft.
    await expect(page.locator('[data-testid="beat-0-lipsync"]')).toHaveCount(0);
    // showRegenAudio is TRUE in draft per the included list.
    await expect(page.locator('[data-testid="beat-0-regen-audio"]')).toBeVisible();
  });

  test('S1.2 — audio_generated: audio_file present, no options → lifecycle="audio_generated"; Animate + Use-as-Final visible, Lipsync hidden', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Audio done.',
      audio_file: 'audio/beat_lc_01.mp3',
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'audio_generated');
    // Animate visible (only state where it's shown).
    await expect(page.locator('[data-testid="beat-0-animate"]')).toBeVisible();
    // Use-as-Final visible per spec §3.1 (audio_generated + selected).
    await expect(page.locator('[data-testid="beat-0-use-as-final"]')).toBeVisible();
    // Lipsync NOT visible — only selected/lipsync_pending get it.
    await expect(page.locator('[data-testid="beat-0-lipsync"]')).toHaveCount(0);
    // Options group NOT visible — animated/selected only.
    await expect(page.locator('[data-testid="beat-options-group-0"]')).toHaveCount(0);
  });

  test('S1.3 — animated: phase_1.options present, no selected_option → lifecycle="animated"; option radios visible, Add options button visible', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Animated 3 options.',
      audio_file: 'audio/beat_lc_01.mp3',
      phase_1: {
        options: [
          { file: 'animations/opt1.mp4' },
          { file: 'animations/opt2.mp4' },
          { file: 'animations/opt3.mp4' },
        ],
      },
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'animated');
    // 3 option radios shown.
    await expect(page.locator('[data-testid="beat-0-select-option-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="beat-0-select-option-2"]')).toBeVisible();
    await expect(page.locator('[data-testid="beat-0-select-option-3"]')).toBeVisible();
    // showAddOptions is TRUE only in animated.
    await expect(page.locator('[data-testid="beat-0-add-options"]')).toBeVisible();
    // Lipsync NOT visible (selected/lipsync_pending only).
    await expect(page.locator('[data-testid="beat-0-lipsync"]')).toHaveCount(0);
    // Final marker NOT shown.
    await expect(page.locator('[data-testid="beat-0-final-marker"]')).toHaveCount(0);
  });

  test('S1.4 — selected: phase_1.selected_option present → lifecycle="selected"; Lipsync + Use-as-Final visible, Add options hidden', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Selected option 2.',
      audio_file: 'audio/beat_lc_01.mp3',
      phase_1: {
        selected_option: 2,
        options: [
          { file: 'animations/opt1.mp4' },
          { file: 'animations/opt2.mp4' },
          { file: 'animations/opt3.mp4' },
        ],
      },
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'selected');
    // Lipsync visible (selected + lipsync_pending only).
    await expect(page.locator('[data-testid="beat-0-lipsync"]')).toBeVisible();
    // Use-as-Final visible (audio_generated + animated + selected per
    // StoryboardTab.tsx visibility expansion 2026-05-12, commit 829a5a5).
    await expect(page.locator('[data-testid="beat-0-use-as-final"]')).toBeVisible();
    // Add options VISIBLE — per commit 829a5a5 (Kim, 2026-05-12), add-options
    // is now always available in animated/selected/lipsync_pending/final so
    // Kim can generate fresh options at any pipeline stage. Server mutate_state
    // uses fcntl.lockf + threading.Lock so concurrent add_options during
    // lipsync_pending is race-safe.
    await expect(page.locator('[data-testid="beat-0-add-options"]')).toBeVisible();
    // Selected option indicator (✓ on the active radio).
    const opt2 = page.locator('[data-testid="beat-0-select-option-2"]');
    await expect(opt2).toBeVisible();
    await expect(opt2).toContainText('✓');
  });

  test('S1.5 — lipsync_pending: lipsync.status="pending" → lifecycle="lipsync_pending"; Lipsync button shows "in progress" and is disabled', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Lipsync running.',
      audio_file: 'audio/beat_lc_01.mp3',
      phase_1: { selected_option: 1, options: [{ file: 'animations/opt1.mp4' }] },
      lipsync: { status: 'pending' },
    });
    // Provide lipsync_status mock so the polling effect doesn't error.
    await page.route('**/api/lipsync/status*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'pending' }),
      });
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'lipsync_pending');
    const lip = page.locator('[data-testid="beat-0-lipsync"]');
    await expect(lip).toBeVisible();
    await expect(lip).toBeDisabled();
    await expect(lip).toContainText(/in progress/i);
  });

  test('S1.6 — final: beat.final.file present → lifecycle="final"; final marker visible; Animate/Use-as-Final hidden; Lipsync visible as Resend when source=lipsync', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Final beat.',
      audio_file: 'audio/beat_lc_01.mp3',
      phase_1: { selected_option: 1, options: [{ file: 'animations/opt1.mp4' }] },
      final: {
        source: 'lipsync',
        source_option: 1,
        file: 'final/beat_lc_01.mp4',
        approved_at: '2026-05-04T10:00:00Z',
      },
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'final');
    // Final marker visible with source.
    const marker = page.locator('[data-testid="beat-0-final-marker"]');
    await expect(marker).toBeVisible();
    await expect(marker).toContainText('lipsync');
    // Animate HIDDEN in final state (showAnimate excludes 'final').
    await expect(page.locator('[data-testid="beat-0-animate"]')).toHaveCount(0);
    // Use-as-Final HIDDEN in final state (showUseAsFinal = ['audio_generated','animated','selected']).
    await expect(page.locator('[data-testid="beat-0-use-as-final"]')).toHaveCount(0);
    // Lipsync VISIBLE in final state when final.source === 'lipsync' — labeled
    // "Resend Lipsync" per commit 829a5a5 (Kim, 2026-05-12). Allows regenerating
    // lipsync on a finalised beat without unwinding the final marker.
    const lipBtn = page.locator('[data-testid="beat-0-lipsync"]');
    await expect(lipBtn).toBeVisible();
    await expect(lipBtn).toContainText(/resend lipsync/i);
    // Regen audio still allowed in final per spec §3.1.
    await expect(page.locator('[data-testid="beat-0-regen-audio"]')).toBeVisible();
  });

  test('S1.7 — guard: state machine does not skip "selected" — beats with options but no selected_option stay in "animated" (cannot reach "final" without lipsync or use_as_final)', async ({ page }) => {
    // Same as S1.3 but explicitly assert that lifecycle is "animated" (not "selected" / "final")
    // even though phase_1.options is fully populated. Without selected_option in
    // phase_1, deriveBeatLifecycle MUST return 'animated'.
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Three opts but none chosen.',
      audio_file: 'audio/beat_lc_01.mp3',
      phase_1: {
        options: [
          { file: 'animations/opt1.mp4' },
          { file: 'animations/opt2.mp4' },
          { file: 'animations/opt3.mp4' },
        ],
      },
      // Note: NO selected_option, NO final, NO lipsync.
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const row = page.locator('[data-testid="beat-button-row-0"]');
    await expect(row).toHaveAttribute('data-lifecycle', 'animated');
    // Final marker MUST NOT appear without beat.final.file — proves no
    // shortcut via UI even with full option data present.
    await expect(page.locator('[data-testid="beat-0-final-marker"]')).toHaveCount(0);
  });

  test('S1.8 — Use as Final mutation fires beat_use_as_final endpoint with beat_id', async ({ page }) => {
    await mockEventStateWithBeat(page, {
      speaker: 'Tessa',
      text: 'Selected with audio.',
      audio_file: 'audio/beat_lc_01.mp3',
      phase_1: {
        selected_option: 1,
        options: [{ file: 'animations/opt1.mp4' }],
      },
    }, 'beat_lc_01');
    // Mock the beat_use_as_final endpoint and snapshot endpoint to return ok.
    await page.route('**/api/state/snapshot', async (r) => {
      await r.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    const useAsFinalReqs: { url: string; body: unknown }[] = [];
    await page.route('**/api/beat/use_as_final', async (route) => {
      const req = route.request();
      const reqBody = req.postDataJSON() as { beat_id?: string; beat?: string } | null;
      useAsFinalReqs.push({ url: req.url(), body: reqBody });
      // LD-778 expectField gate compliance — echo back the request's beat_id
      // so the gate sees a `beat: string` matching what the client sent (not
      // a hardcoded literal that could silently mask a mismatch). See
      // retroactive_s3:142 comment for the broader rationale.
      const echoedBeat = reqBody?.beat_id || reqBody?.beat || 'beat_lc_01';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          beat: echoedBeat,
          file: `${echoedBeat}_opt0.mp4`,
          final: { source: 'raw_option', source_option: 0, file: `${echoedBeat}_opt0.mp4` },
        }),
      });
    });
    await gotoApp(page);
    await page.click('[data-testid="tab-storyboard"]');
    const useFinal = page.locator('[data-testid="beat-0-use-as-final"]');
    await expect(useFinal).toBeVisible();
    await useFinal.click();
    await expect.poll(() => useAsFinalReqs.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1);
    const body = useAsFinalReqs[0]!.body as Record<string, unknown>;
    expect(body['beat_id']).toBe('beat_lc_01');
    // Per pathappPatch (LD-461) scope-key injection: beat_use_as_final is non-BG, so event_id key.
    expect(body['event_id'] !== undefined || body['scope_event_id'] !== undefined).toBe(true);
  });
});

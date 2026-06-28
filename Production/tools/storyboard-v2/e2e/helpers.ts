// Shared test helpers — Session 3 cleanup item A2.
//
// Tests that modify dialogue text MUST capture the original text before
// editing and restore it after, otherwise stamps accumulate in
// production_state.json across test runs (see Session 2 incident:
// reversed strings + " x" suffixes corrupted Kim's actual dialogue).
//
// Usage in a test:
//
//   import { protectBeatText } from './helpers';
//
//   test('row N — does X', async ({ page, request }) => {
//     await using _restore = await protectBeatText(request, 'beat_03');
//     // ... do the test ...
//     // _restore is auto-disposed on test exit, restoring beat_03 to original.
//   });
//
// Or imperatively:
//   const restore = await protectBeatText(request, 'beat_03');
//   try { ... } finally { await restore.restore(); }

import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const SERVER = process.env.STORYBOARD_BASE_URL ?? 'http://localhost:5200';
export const EVENT_ID = 'Event_1';
export const FIXTURE_EVENT = 'Event_e2e_fixture';

/** App root visible — fixture-agnostic (Playwright webServer pins Event_e2e_fixture). */
export async function gotoApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('[data-testid="app-root"]')).toBeVisible();
}

/**
 * Storyboard tab is hiddenFromBar in TabBar — open via ?tab=storyboard URL param
 * (refreshSignals.readUrlActiveTab maps tab=storyboard → activeTab 'storyboard').
 */
export async function openStoryboardPane(page: Page): Promise<void> {
  await page.goto('/?tab=storyboard');
  await expect(page.locator('[data-testid="pane-storyboard"]')).toBeVisible({ timeout: 10_000 });
}

export interface BeatProtector {
  beatId: string;
  originalText: string;
  restore(): Promise<void>;
  /** Symbol.asyncDispose support for `await using` syntax. */
  [Symbol.asyncDispose](): Promise<void>;
}

export async function protectBeatText(
  request: APIRequestContext,
  beatId: string,
): Promise<BeatProtector> {
  // Capture current text from server.
  const stateRes = await request.get(`${SERVER}/api/v2/event/${EVENT_ID}/state`);
  if (!stateRes.ok()) {
    throw new Error(`protectBeatText: failed to fetch state (HTTP ${stateRes.status()})`);
  }
  const state = (await stateRes.json()) as {
    beats?: Record<string, { text?: string }>;
  };
  const originalText = state.beats?.[beatId]?.text ?? '';

  const restore = async () => {
    // Read current; only restore if it differs from original.
    const cur = await request.get(`${SERVER}/api/v2/event/${EVENT_ID}/state`);
    if (!cur.ok()) return;
    const curState = (await cur.json()) as {
      beats?: Record<string, { text?: string }>;
    };
    const curText = curState.beats?.[beatId]?.text ?? '';
    if (curText === originalText) return;
    // Restore via /api/beat/update_text. allow_missing=True on server, so
    // event_id in body satisfies LD-456 scope guard.
    await request.post(`${SERVER}/api/beat/update_text`, {
      data: {
        event_id: EVENT_ID,
        beat: beatId,
        text: originalText,
        skip_tts_regen: true, // never regen TTS in test cleanup
      },
    });
  };

  return {
    beatId,
    originalText,
    restore,
    [Symbol.asyncDispose]: restore,
  };
}

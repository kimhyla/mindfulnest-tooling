// C2a contract test for HARD LD `DISPLAY_ORDER_STRICT_V1`.
//
// CONTRACT (StoryboardTab beatList renderer):
//   When state.videos[<role>].display_order is a PRESENT LIST, honor it
//   strictly:
//     - display_order = [bid_a, bid_b]  → render 2 beats in that order
//     - display_order = []              → render 0 beats (NOT all-beats fallthrough)
//   Only when display_order is GENUINELY MISSING (undefined OR non-list
//   legacy data) does the renderer fall through to Object.entries(beats)
//   sorted by beat_id.
//
// Background: spec v2 §2.3 Part 1 frames the contract as
//   `if (partition.display_order !== undefined)`. This e2e folds the
//   3 unit cases the spec calls for plus a DS-7 retroactive case
//   mirroring the actual `Event_2/production_state.json` shape
//   (beat_04 orphan + display_order=[]) that triggered Kim's report.
//   See deltas note Δ-C2a for the Array.isArray defensiveness rationale.

import { test, expect, type Route } from '@playwright/test';

interface BeatStateMin {
  speaker?: string;
  text?: string;
}
interface PartitionMin {
  beats?: Record<string, BeatStateMin>;
  display_order?: unknown;
}
interface EventStateMin {
  event_id?: string;
  videos?: Record<string, PartitionMin>;
}

// Helper: wire a state-shape mock so the StoryboardTab fetch always returns
// the same payload. The route pattern `**/api/v2/event/*/state` covers the
// fixture's URL `/api/v2/event/Event_e2e_fixture/state` regardless of
// scope-boundary resolution timing.
async function mockEventState(
  page: import('@playwright/test').Page,
  state: EventStateMin,
): Promise<void> {
  await page.route('**/api/v2/event/*/state', async (r: Route) => {
    await r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(state),
    });
  });
}

async function gotoStoryboard(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/');
  await expect(page.locator('body')).toHaveAttribute(
    'data-resolved-scope',
    /Event_e2e_fixture:global:v\d+/,
    { timeout: 10_000 },
  );
  // Default tab is 'storyboard'; force-click for clarity.
  await page.getByTestId('tab-storyboard').click();
  await expect(page.getByTestId('pane-storyboard')).toBeVisible();
}

test.describe('DISPLAY_ORDER_STRICT_V1 — empty list ≠ undefined', () => {
  test('Case 1: display_order = present list → renders only beats in the list, in order', async ({ page }) => {
    await mockEventState(page, {
      event_id: 'Event_e2e_fixture',
      videos: {
        intro: {
          display_order: ['beat_02', 'beat_01'],
          beats: {
            beat_01: { speaker: 'A', text: 'one' },
            beat_02: { speaker: 'B', text: 'two' },
            beat_03: { speaker: 'C', text: 'three (NOT in display_order — should NOT render)' },
          },
        },
      },
    });
    await gotoStoryboard(page);

    const cards = page.locator('[data-testid^="beat-card-"]');
    await expect(cards).toHaveCount(2);
    // Order: beat_02 first, beat_01 second (per display_order).
    await expect(cards.nth(0)).toHaveAttribute('data-beat-id', 'beat_02');
    await expect(cards.nth(1)).toHaveAttribute('data-beat-id', 'beat_01');
    // beat_03 is in beats{} but NOT in display_order — must not render.
    await expect(page.locator('[data-beat-id="beat_03"]')).toHaveCount(0);
  });

  test('Case 2: display_order = [] (explicitly empty) → renders ZERO beats, no fallthrough', async ({ page }) => {
    // This is the actual bug the spec describes. Pre-fix: Object.entries
    // fallthrough renders all beats. Post-fix: 0 beats + empty message.
    await mockEventState(page, {
      event_id: 'Event_e2e_fixture',
      videos: {
        intro: {
          display_order: [],
          beats: {
            beat_99: { speaker: 'orphan', text: 'should NOT render — only beats in display_order count' },
          },
        },
      },
    });
    await gotoStoryboard(page);

    const cards = page.locator('[data-testid^="beat-card-"]');
    await expect(
      cards,
      'DISPLAY_ORDER_STRICT_V1 violated: display_order=[] should render ZERO beats. ' +
      'If this assertion sees 1 (beat_99 the orphan), the renderer fell through to Object.entries fallback.',
    ).toHaveCount(0);
    // Empty message visible.
    await expect(page.getByTestId('storyboard-empty')).toBeVisible();
    await expect(page.getByText(/no beats in this event yet/i)).toBeVisible();
  });

  test('Case 3: display_order = undefined (legacy) → renders all beats sorted by beat_id', async ({ page }) => {
    // Pre-display_order partitions still work via the legacy fallthrough.
    await mockEventState(page, {
      event_id: 'Event_e2e_fixture',
      videos: {
        intro: {
          // display_order intentionally absent — TS object literal: just
          // omit the key. This exercises the `undefined` branch of the
          // contract.
          beats: {
            beat_02: { speaker: 'B', text: 'two' },
            beat_01: { speaker: 'A', text: 'one' },
          },
        },
      },
    });
    await gotoStoryboard(page);

    const cards = page.locator('[data-testid^="beat-card-"]');
    await expect(cards).toHaveCount(2);
    // Sorted by beat_id alphabetically: beat_01 first, beat_02 second.
    await expect(cards.nth(0)).toHaveAttribute('data-beat-id', 'beat_01');
    await expect(cards.nth(1)).toHaveAttribute('data-beat-id', 'beat_02');
  });

  test('DS-7 retroactive: actual Event_2/production_state.json shape (beat_04 orphan + display_order=[]) renders ZERO beats', async ({ page }) => {
    // Mirrors Dropbox/Production/Event_2/production_state.json as of 2026-05-05:
    // intro partition with a single orphan beat_04 + explicit display_order=[].
    // This is the shape Kim reported as the original Bug B symptom.
    await mockEventState(page, {
      event_id: 'Event_e2e_fixture',
      videos: {
        intro: {
          video_role: 'intro',
          video_label: null,
          beats: {
            beat_04: {
              speaker: 'Tessa',
              text: "The MindfulNest! ... Well don't you know? It's in all the stories. The MindfulNest was the Heart of the Ancient Magical City. ... Everdale?",
            },
          },
          display_order: [],
        } as PartitionMin,
        resolution: {
          beats: {},
          display_order: [],
        },
      },
    });
    await gotoStoryboard(page);

    const cards = page.locator('[data-testid^="beat-card-"]');
    await expect(
      cards,
      'DS-7 retroactive: Event_2 intro renders beat_04 even though display_order=[]. ' +
      'Original Bug B symptom — orphan beat surfaces because of the Object.entries fallthrough.',
    ).toHaveCount(0);
    // Specifically beat_04 must not be on screen.
    await expect(page.locator('[data-beat-id="beat_04"]')).toHaveCount(0);
    // Empty message visible.
    await expect(page.getByTestId('storyboard-empty')).toBeVisible();
  });
});

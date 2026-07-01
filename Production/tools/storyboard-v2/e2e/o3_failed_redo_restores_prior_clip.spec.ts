/**
 * O3_FAILED_REDO_HEAL_V1 — failed regen restores prior on-disk delivery.
 * Marker: O3-FAILED-REDO-1
 */
import { test, expect } from '@playwright/test';
import { SERVER } from './testServer';
import {
  O3_FAILED_REDO_BEAT_ID,
  O3_FAILED_REDO_JOB_ID,
  seedO3FailedRedoFixture,
} from './o3FixtureSeed';

const SCOPE_QS =
  'scope_type=project&event_id=Event_e2e_fixture&scope_event_id=Event_e2e_fixture&scope_arc_number=1&scope_video_role=intro';

test.describe('O3 failed redo heal G1', () => {
  test.beforeAll(async ({ request }) => {
    await seedO3FailedRedoFixture(request, SERVER);
  });

  test('O3-FAILED-REDO-1 session GET and poll agree on approved prior clip', async ({
    request,
  }) => {
    const beatId = O3_FAILED_REDO_BEAT_ID;
    const pollRes = await request.get(
      `${SERVER}/api/bg/poll-arlo-o3-voice-status?job_id=${encodeURIComponent(O3_FAILED_REDO_JOB_ID)}&${SCOPE_QS}`,
    );
    expect(pollRes.ok()).toBeTruthy();
    const pollBody = await pollRes.json();
    const pollBeat = pollBody?.beat ?? pollBody;

    const sessionRes = await request.get(`${SERVER}/api/bg/session-state?${SCOPE_QS}`);
    expect(sessionRes.ok()).toBeTruthy();
    const sessionBody = await sessionRes.json();
    const rows = sessionBody?.beats ?? [];
    const sessionBeat = (Array.isArray(rows) ? rows : []).find(
      (b: { beat_id?: string }) => b?.beat_id === beatId,
    );
    expect(sessionBeat).toBeTruthy();

    for (const beat of [pollBeat, sessionBeat]) {
      expect(String(beat?.kling_o3_status ?? '')).toMatch(/approved/i);
      expect(String(beat?.kling_o3_video_path ?? '')).toMatch(/\.mp4$/i);
      expect(String(beat?.kling_o3_voice_fix_status ?? '')).not.toMatch(/running/i);
    }
    expect(String(pollBeat?.kling_o3_video_path ?? '')).toBe(
      String(sessionBeat?.kling_o3_video_path ?? ''),
    );
  });
});

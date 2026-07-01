/**
 * O3_FAILED_REDO_HEAL_V1 — failed regen restores prior on-disk delivery.
 * G1 operator path: Generate → fail → prior clip restored.
 */
import { test, expect } from '@playwright/test';

const BASE = process.env.STORYBOARD_BASE_URL ?? 'http://127.0.0.1:5114';

test.describe('O3 failed redo heal G1', () => {
  test('O3-FAILED-REDO-1 poll snapshot shows approved after terminal failed with prior disk gen', async ({
    request,
  }) => {
    test.skip(!process.env.O3_FAILED_REDO_BEAT_ID, 'Set O3_FAILED_REDO_BEAT_ID for live proof');
    const beatId = process.env.O3_FAILED_REDO_BEAT_ID!;
    const res = await request.get(
      `${BASE}/api/storyboard/bg_o3_poll?beat_id=${encodeURIComponent(beatId)}`,
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    const beat = body?.beat ?? body;
    expect(String(beat?.kling_o3_status ?? '')).toMatch(/approved/i);
    expect(String(beat?.kling_o3_video_path ?? '')).toMatch(/\.mp4$/i);
    expect(String(beat?.kling_o3_voice_fix_status ?? '')).not.toMatch(/running/i);
  });
});

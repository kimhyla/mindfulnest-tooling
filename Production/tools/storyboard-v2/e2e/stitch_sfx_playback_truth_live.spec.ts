/**
 * STITCH_SFX_PLAYBACK_TRUTH_V1 + STITCH_TRUTH_CONTRACT_V2 — live milestone E2E.
 * STITCH_LIVE_E2E_MILESTONE_V1 — fixture + job-API mux truth (see TECH_SPEC_STITCH_LIVE_E2E_MILESTONE_V1.md).
 *
 * Requires Event_2 storyboard on :5112 with milestone1_arc1 stitch job hydrated.
 * Does NOT use Event_e2e_fixture or playwright webServer.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type APIRequestContext, type Page, type Request } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LIVE_BASE = process.env.STORYBOARD_LIVE_BASE_URL ?? 'http://127.0.0.1:5112';
const MILESTONE_URL =
  '/?event=Event_2&milestone=milestone1_arc1&video=standalone';
const JOB_NAME = 'milestone_milestone1_arc1_stitch';
const MILESTONE_ASSEMBLED_DIR =
  '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Milestones/milestone1_arc1/assembled';
const E2E_DROP_OFFSET_FRAC = 0.25;
const CANONICAL_CUE = {
  id: 'test_cue_79000',
  source_path:
    '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/assets/sound_library/sfx/magic_sound.mp3',
  name: 'magic_sound.mp3',
  offset_ms: 79000,
  duration_ms: 3000,
  volume: 1,
  fadein_ms: 50,
  fadeout_ms: 50,
};

let e2eDropCueIds: string[] = [];

async function serverReachable(request: APIRequestContext): Promise<boolean> {
  try {
    const res = await request.get(`${LIVE_BASE}/api/event/current`, { timeout: 5000 });
    return res.ok();
  } catch {
    return false;
  }
}

type StitchJobPayload = {
  job?: { slots?: { standalone?: Record<string, unknown> } };
  job_persisted?: boolean;
};

async function fetchStandaloneJob(request: APIRequestContext): Promise<StitchJobPayload> {
  // load_job may auto-bake Event_2 slots on the same server — allow up to 2 min (STITCH_LOAD_JOB_PLAYBACK_BAKE_V1).
  const res = await request.get(`${LIVE_BASE}/api/stitch_editor/job/${JOB_NAME}`, {
    timeout: 120_000,
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as StitchJobPayload;
}

async function fetchStandaloneSlot(request: APIRequestContext) {
  const data = await fetchStandaloneJob(request);
  return data.job?.slots?.standalone;
}

/** Durable mux truth — same field handle_stitch_preview persists (STITCH_LIVE_E2E_MILESTONE_V1). */
async function pollStandaloneMuxHash(
  request: APIRequestContext,
  opts?: { exclude?: string; timeoutMs?: number },
): Promise<string> {
  const timeoutMs = opts?.timeoutMs ?? 180_000;
  let hash = '';
  await expect
    .poll(
      async () => {
        const slot = await fetchStandaloneSlot(request);
        hash = String(slot?.mux_preview_hash ?? '').trim();
        if (hash.length < 8) return '';
        if (opts?.exclude && hash === opts.exclude) return '';
        return hash;
      },
      { timeout: timeoutMs, intervals: [500, 1000, 2000, 3000] },
    )
    .not.toBe('');
  return hash;
}

async function postStandaloneSlots(
  request: APIRequestContext,
  slot: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const cur = await request.get(`${LIVE_BASE}/api/event/current`);
  const curBody = await cur.json();
  const res = await request.post(`${LIVE_BASE}/api/stitch_editor/job`, {
    timeout: 300_000,
    data: {
      name: JOB_NAME,
      merge_slots: true,
      slots: { standalone: slot },
      transitions: [],
      scope_event_id: 'Event_2',
      scope_milestone_id: 'milestone1_arc1',
      scope_video_role: 'standalone',
      scope_target_video: 'standalone',
      event_id: 'Event_2',
      scope_version: curBody.event_generation ?? 1,
    },
  });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as {
    job_persisted?: boolean;
    saved_video_path?: string;
    saved_slots?: { standalone?: Record<string, unknown> };
  };
  expect(body.job_persisted).toBe(true);

  const incomingVideo = String(slot.video_path ?? '').trim();
  const savedStandalone = body.saved_slots?.standalone ?? {};
  if (incomingVideo) {
    const savedPath = String(
      body.saved_video_path ?? savedStandalone.video_path ?? '',
    ).trim();
    expect(savedPath.length).toBeGreaterThan(0);
    return { ...savedStandalone, video_path: savedPath };
  }

  // STITCH_E2E_SFX_ONLY_SAVE_V1 — merge_slots preserves lineage; heal if a failed run wiped video.
  const readback = await fetchStandaloneSlot(request);
  if (!String(readback?.video_path ?? '').trim()) {
    return ensureMilestoneStandaloneVideo(request);
  }
  return readback!;
}

/** STITCH_E2E_MILESTONE_VIDEO_BOOTSTRAP_V1 — single-owner: explicit POST, not load_job hydrate. */
async function bootstrapStandaloneVideoFromAssembled(
  request: APIRequestContext,
): Promise<Record<string, unknown>> {
  if (!fs.existsSync(MILESTONE_ASSEMBLED_DIR)) {
    throw new Error('milestone assembled dir missing for bootstrap');
  }
  const finals = fs
    .readdirSync(MILESTONE_ASSEMBLED_DIR)
    .filter((name) => name.endsWith('_final.mp4'))
    .sort()
    .reverse();
  const standalones = fs
    .readdirSync(MILESTONE_ASSEMBLED_DIR)
    .filter((name) => name.startsWith('standalone_') && name.endsWith('.mp4'))
    .sort()
    .reverse();
  const candidates = [...finals, ...standalones.filter((n) => !finals.includes(n))];
  if (!candidates.length) {
    throw new Error('no *_final.mp4 or standalone_*.mp4 in milestone assembled dir');
  }
  const videoPath = path.posix.join(
    'Production/Milestones/milestone1_arc1/assembled',
    candidates[0]!,
  );
  return postStandaloneSlots(request, {
    video_path: videoPath,
    ambient_bed: 'Intro video ambient bed',
    ambient_volume: 0.15,
    sfx_cues: [],
  });
}

/** Idempotent video lineage restore — used beforeAll + afterEach (STITCH_LIVE_E2E_MILESTONE_V1). */
async function ensureMilestoneStandaloneVideo(
  request: APIRequestContext,
): Promise<Record<string, unknown>> {
  let slot = await fetchStandaloneSlot(request);
  if (String(slot?.video_path ?? '').trim()) return slot!;
  return bootstrapStandaloneVideoFromAssembled(request);
}

/** Pin video_path on cue-only saves so merge never runs without lineage (STITCH_LIVE_E2E_MILESTONE_V1). */
function standaloneSavePayload(
  slot: Record<string, unknown>,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const videoPath = String(slot.video_path ?? patch.video_path ?? '').trim();
  return {
    ...(videoPath ? { video_path: videoPath } : {}),
    ambient_bed: slot.ambient_bed ?? 'Intro video ambient bed',
    ambient_volume: slot.ambient_volume ?? 0.15,
    ...patch,
  };
}

/** DEPLOY_MUX_WARM_G4_PRE_V1 — mux bake runs in deploy_mux_warm_g4_pre.sh, not here (RC14). */
async function assertMuxWarmFromG4Pre(request: APIRequestContext): Promise<void> {
  await ensureMilestoneStandaloneVideo(request);
  const slot = await fetchStandaloneSlot(request);
  const muxHash = String(slot?.mux_preview_hash ?? '').trim();
  if (muxHash.length >= 8) {
    await restoreCanonicalTestCue(request);
    return;
  }
  const markerPath = path.join(
    __dirname,
    '../../../.deploy_mux_warm/Event_2_milestone.ok',
  );
  const hint = fs.existsSync(markerPath)
    ? `marker exists but job hash empty — re-run deploy_mux_warm_g4_pre.sh on ${LIVE_BASE}`
    : `run Production/scripts/deploy_mux_warm_g4_pre.sh before live E2E`;
  throw new Error(`DEPLOY_MUX_WARM_G4_PRE_V1: mux_preview_hash missing. ${hint}`);
}

async function restoreCanonicalTestCue(request: APIRequestContext): Promise<void> {
  const slot = await ensureMilestoneStandaloneVideo(request);
  const cues = (slot.sfx_cues as Array<Record<string, unknown>> | undefined) ?? [];
  if (cues.some((c) => String(c.id) === CANONICAL_CUE.id)) return;
  await postStandaloneSlots(
    request,
    standaloneSavePayload(slot, { sfx_cues: [...cues, CANONICAL_CUE] }),
  );
}

async function cleanupE2eCues(request: APIRequestContext): Promise<void> {
  const slot = await ensureMilestoneStandaloneVideo(request);
  const cues = (slot.sfx_cues as Array<Record<string, unknown>> | undefined) ?? [];
  const dropSet = new Set(e2eDropCueIds);
  const kept = dropSet.size
    ? cues.filter((c) => !dropSet.has(String(c.id ?? '')))
    : cues;
  if (dropSet.size && kept.length !== cues.length) {
    await postStandaloneSlots(request, standaloneSavePayload(slot, { sfx_cues: kept }));
  }
  e2eDropCueIds = [];
}

async function restoreMilestoneFixture(request: APIRequestContext): Promise<void> {
  await ensureMilestoneStandaloneVideo(request);
  await cleanupE2eCues(request);
  await restoreCanonicalTestCue(request);
}

async function synthDrop(
  page: Page,
  selector: string,
  payload: Record<string, unknown>,
  position: { xFrac: number; yFrac: number } = { xFrac: 0.5, yFrac: 0.5 },
): Promise<void> {
  const el = page.locator(selector);
  await expect(el).toBeVisible();
  const box = await el.boundingBox();
  if (!box) throw new Error(`No bounding box for ${selector}`);
  const x = box.x + box.width * position.xFrac;
  const y = box.y + box.height * position.yFrac;
  await el.evaluate(
    (node: Element, args: { payloadStr: string; clientX: number; clientY: number }) => {
      const dt = new DataTransfer();
      dt.setData('application/x-mn-drag', args.payloadStr);
      dt.setData('text/plain', args.payloadStr);
      const drop = new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
        clientX: args.clientX,
        clientY: args.clientY,
      });
      node.dispatchEvent(drop);
    },
    { payloadStr: JSON.stringify(payload), clientX: x, clientY: y },
  );
}

test.describe('STITCH_SFX_PLAYBACK_TRUTH live milestone', () => {
  test.beforeAll(async ({ request }) => {
    test.setTimeout(120_000);
    test.skip(!(await serverReachable(request)), `Live server unreachable at ${LIVE_BASE}`);
    const cur = await request.get(`${LIVE_BASE}/api/event/current`);
    const body = await cur.json();
    expect(body.event_id).toBe('Event_2');
    await assertMuxWarmFromG4Pre(request);
  });

  test.afterEach(async ({ request }) => {
    await restoreMilestoneFixture(request);
  });

  test('TRUTH-LIVE-1 — rail duration, mux playback, pause-on-SFX-drop, mux rebuild', async ({
    page,
    request,
  }) => {
    const slotBefore = await fetchStandaloneSlot(request);
    expect(slotBefore?.video_dur_ms).toBeGreaterThan(80_000);
    const muxHashBefore = String(slotBefore?.mux_preview_hash ?? '');

    await page.goto(`${LIVE_BASE}${MILESTONE_URL}`);
    await expect(page.locator('[data-testid="app-root"]')).toBeVisible({ timeout: 60_000 });

    await page.locator('[data-testid="tab-stitcher"]').click();
    await expect(page.locator('[data-testid="stitcher-loading"]')).toBeHidden({ timeout: 60_000 });
    const composer = page.locator('[data-testid="stitcher-slot-composer"]');
    await expect(composer).toBeVisible({ timeout: 30_000 });
    await expect(composer).toHaveAttribute('data-stitch-sfx-playback-truth', 'STITCH_SFX_PLAYBACK_TRUTH_V1');
    await expect(composer).toHaveAttribute('data-stitch-slot-timeline-atomic', 'STITCH_SLOT_TIMELINE_ATOMIC_V1');
    await expect(composer).toHaveAttribute('data-stitch-mux-pause-on-geometry', 'STITCH_MUX_PAUSE_ON_GEOMETRY_V1');

    await expect(page.locator('body')).toHaveAttribute('data-active-project-type', 'milestone');

    const segmentMeta = page.locator(
      '[data-testid="stitcher-multiphase-segment-standalone"] .mn-stitcher-multiphase-segment-meta',
    );
    await expect(segmentMeta).toBeVisible({ timeout: 30_000 });
    const expectedDurSec = ((slotBefore?.video_dur_ms ?? 0) / 1000).toFixed(1);
    await expect(segmentMeta).toContainText(`${expectedDurSec}s`);

    const video = page.locator('[data-testid="stitcher-composer-video"]');
    const waitingMux = page.locator('[data-testid="stitcher-composer-video-waiting-mux"]');
    await expect
      .poll(async () => {
        if (await video.isVisible().catch(() => false)) return 'video';
        if (await waitingMux.isVisible().catch(() => false)) return 'waiting';
        const status = page.locator('[data-testid="stitcher-status"]');
        if (await status.isVisible().catch(() => false)) {
          const txt = (await status.textContent()) ?? '';
          if (/rebuilding SFX preview|Building SFX preview/i.test(txt)) return 'building';
        }
        return 'none';
      }, { timeout: 180_000 })
      .not.toBe('none');
    if (await waitingMux.isVisible().catch(() => false)) {
      await page.getByRole('button', { name: 'Review' }).click();
      await expect(video).toBeVisible({ timeout: 180_000 });
    } else {
      await expect(video).toBeVisible({ timeout: 10_000 });
    }
    await page.waitForFunction(() => {
      const v = document.querySelector('[data-testid="stitcher-composer-video"]') as HTMLVideoElement | null;
      const src = v?.src ?? '';
      return src.includes('/api/stitch_editor/preview_file/') || src.includes('stitch_preview_');
    }, { timeout: 90_000 });

    const libRes = await request.get(`${LIVE_BASE}/api/stitch_editor/library`);
    expect(libRes.ok()).toBeTruthy();
    const lib = await libRes.json();
    const sfx = (lib.sfx as Array<{ filename: string; path: string }> | undefined)?.[0];
    expect(sfx?.path).toBeTruthy();

    const saveJobReqs: Request[] = [];
    page.on('request', (req) => {
      if (req.url().endsWith('/api/stitch_editor/job') && req.method() === 'POST') {
        saveJobReqs.push(req);
      }
    });

    await page.evaluate(async () => {
      const v = document.querySelector('[data-testid="stitcher-composer-video"]') as HTMLVideoElement | null;
      if (!v) throw new Error('no composer video');
      v.muted = true;
      await v.play();
    });
    await page.waitForFunction(() => {
      const v = document.querySelector('[data-testid="stitcher-composer-video"]') as HTMLVideoElement | null;
      return v != null && !v.paused;
    }, { timeout: 10_000 });

    await synthDrop(
      page,
      '[data-testid="stitcher-slot-waveform-standalone"]',
      {
        kind: 'lib-sfx',
        lib_key: sfx!.filename,
        source_path: sfx!.path,
        tier: 'sfx',
      },
      { xFrac: E2E_DROP_OFFSET_FRAC, yFrac: 0.5 },
    );

    await expect(page.locator('[data-testid="stitcher-status"]')).toContainText(
      /Paused — updating SFX preview \(video stays loaded\)/i,
      { timeout: 15_000 },
    );

    await page.waitForFunction(() => {
      const v = document.querySelector('[data-testid="stitcher-composer-video"]') as HTMLVideoElement | null;
      return v != null && v.paused;
    }, { timeout: 10_000 });

    await expect.poll(() => saveJobReqs.length, { timeout: 30_000 }).toBeGreaterThanOrEqual(1);

    const saveBody = saveJobReqs[saveJobReqs.length - 1]!.postDataJSON() as Record<string, unknown>;
    const savedStandalone = (saveBody.slots as Record<string, Record<string, unknown>>)?.standalone;
    const savedCues = (savedStandalone?.sfx_cues as Array<Record<string, unknown>> | undefined) ?? [];
    const droppedCue = savedCues.find((c) => String(c.source_path) === sfx!.path);
    expect(droppedCue).toBeTruthy();
    e2eDropCueIds.push(String(droppedCue!.id));
    const offsetMs = Number(droppedCue!.offset_ms);
    expect(offsetMs).toBeGreaterThan(10_000);
    expect(offsetMs).toBeLessThan(Number(slotBefore?.video_dur_ms ?? 100_000));

    // STITCH_ARTIFACT_ORCHESTRATOR_V1 — durable mux truth is job API hash, not preview POST.
    const muxHashAfter = await pollStandaloneMuxHash(request, {
      exclude: muxHashBefore || undefined,
    });
    expect(muxHashAfter.length).toBeGreaterThan(8);
    expect(muxHashAfter).not.toBe(muxHashBefore);

    const slotAfter = await fetchStandaloneSlot(request);
    expect(String(slotAfter?.mux_preview_hash ?? '')).toBe(muxHashAfter);

    const cues = (slotAfter?.sfx_cues as Array<Record<string, unknown>> | undefined) ?? [];
    const persistedDrop = cues.find((c) => String(c.id) === e2eDropCueIds[0]);
    if (persistedDrop) {
      const persistedOffsetMs = Number(persistedDrop.offset_ms);
      const videoDur = Number(slotAfter?.video_dur_ms ?? 0);
      const muxDur = Number(slotAfter?.mux_preview_duration_ms ?? videoDur);
      const expectedSlot = Math.round(videoDur * E2E_DROP_OFFSET_FRAC);
      const expectedMux = Math.round(muxDur * E2E_DROP_OFFSET_FRAC);
      const nearSlot = Math.abs(persistedOffsetMs - expectedSlot) <= expectedSlot * 0.3;
      const nearMux = Math.abs(persistedOffsetMs - expectedMux) <= expectedMux * 0.3;
      expect(nearSlot || nearMux).toBe(true);
    }

    const finalSrc = await video.getAttribute('src').catch(() => null);
    if (finalSrc) {
      expect(finalSrc).toMatch(/preview_file|stitch_preview_/);
      expect(finalSrc).not.toMatch(/\/files\?path=/);
    }
  });
});

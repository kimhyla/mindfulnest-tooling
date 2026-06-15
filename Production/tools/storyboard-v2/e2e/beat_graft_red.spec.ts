// beat_graft_red — C-1 RED skeleton for the Pillar 7 cornerstone endpoint.
//
// Per STORYBOARD_V59_AUTHORING_WORKFLOW_HANDOFF.md §4 C-1 + spec §6:
// `/api/beat/graft` is the canonical recovery primitive (subsumes K5 HARD
// half — cross-event move). C-1 ships this skeleton; C-7 lands the handler
// implementation and turns these tests GREEN.
//
// Until C-7 lands, the endpoint returns 404 (route unregistered). All test
// bodies here are skipped via test.fixme — the spec sanity-check is that
// they exist as named contracts and CI surfaces them as fixme rather than
// silently passing.
//
// Test IDs match spec §11.1 (Pillar 7):
//   GR.1  same-event same-role copy
//   GR.2  missing mutation_id → HTTP 400
//   GR.3  source beat missing → HTTP 404
//   GR.4  source beat with phase_1.status=="completed" → HTTP 400 graft_pre_render_only
//   GR.5  cross-event without --source-event flag → HTTP 409 cross_event_requires_explicit_source
//   GR.6  move=true deletes source after target write
//   SCR.3 cross-event move with --source-event flag (paired with C-9 salvage)

import { test, expect, type APIRequestContext } from '@playwright/test';
import { copyFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const SERVER = 'http://localhost:5111';
const EVENT_ID = 'Event_e2e_fixture';

// Fixture restoration paths — mirrors globalSetup.ts. This file's GR.1 + GR.6
// tests mutate videos.intro/.resolution destructively (copy/move beats), and
// the next spec in alphabetical order — s5_5ce_proper_fix.spec.ts R1.1 —
// asserts intro has exactly 3 beats. Without an afterAll restoration, R1.1
// sees a polluted fixture and fails. Per DS-3 fixture pinning: tests that
// mutate must restore.
const __filename = fileURLToPath(import.meta.url);
const __dirname_spec = dirname(__filename);
const repoRoot = resolve(__dirname_spec, '..', '..', '..', '..');
const fixtureDir = resolve(repoRoot, 'Production', 'Event_e2e_fixture');
const pristineDir = resolve(fixtureDir, '.pristine');

async function endpointReachable(request: APIRequestContext, path: string): Promise<boolean> {
  // OPTIONS-style probe: send a minimal POST and check that the server doesn't 404.
  // Until C-7 lands the route, the server returns 404 and these probes fail.
  const r = await request.post(`${SERVER}${path}`, { data: {} });
  return r.status() !== 404;
}

test.describe('Pillar 7 — /api/beat/graft (RED skeleton until C-7)', () => {
  // DS-3 fixture restoration — copy pristine state file back over the live
  // fixture state file after our destructive tests. Mirrors the pattern in
  // global-setup.ts which runs ONCE per test session; afterAll runs after
  // the GR.* tests in this describe block, before the next spec runs.
  test.afterAll(async () => {
    const pristineState = resolve(pristineDir, 'production_state.json');
    const liveState = resolve(fixtureDir, 'production_state.json');
    if (existsSync(pristineState)) {
      copyFileSync(pristineState, liveState);
      // eslint-disable-next-line no-console
      console.log('[beat_graft_red afterAll] restored fixture from pristine');
    }
  });

  // GREEN as of C-7 — route registered + handler returns 400 (not 404).
  test('endpoint registration sanity — /api/beat/graft route exists post-C-7', async ({ request }) => {
    // Pre-C-7: 404 (no route). Post-C-7: 400/422 (missing body fields) — anything
    // except 404 is acceptable for "route is registered."
    const reachable = await endpointReachable(request, '/api/beat/graft');
    expect(reachable, '/api/beat/graft must be a registered route after C-7').toBe(true);
  });

  test('GR.1 — same-event copy writes target + pre-image; replay returns dedup', async ({ request }) => {
    const mutationId = `gr1-${Date.now()}`;
    const body1 = {
      source: { event_id: EVENT_ID, video_role: 'intro', beat_id: 'beat_01' },
      target: { event_id: EVENT_ID, video_role: 'resolution', position: 0 },
      mutation_id: mutationId,
      move: false,
    };
    const r1 = await request.post(`${SERVER}/api/beat/graft`, { data: body1, timeout: 60_000 });
    expect(r1.ok(), `first graft must succeed; got HTTP ${r1.status()}: ${await r1.text()}`).toBeTruthy();
    const p1 = await r1.json();
    expect(p1?.status).toBe('copied');
    expect(Array.isArray(p1?.pre_image_paths) && p1.pre_image_paths.length).toBeTruthy();
    expect(p1?.beat_id).toBe('beat_01');

    // Replay with the same mutation_id → dedup
    const r2 = await request.post(`${SERVER}/api/beat/graft`, { data: body1, timeout: 60_000 });
    expect(r2.ok()).toBeTruthy();
    const p2 = await r2.json();
    expect(p2?.status, 'replay must return status="dedup"').toBe('dedup');
  });

  test('GR.2 — missing mutation_id returns HTTP 400 mutation_id_required', async ({ request }) => {
    const r = await request.post(`${SERVER}/api/beat/graft`, {
      data: {
        // Intentionally NO mutation_id — server must reject before any state read.
        source: { event_id: EVENT_ID, video_role: 'intro', beat_id: 'beat_01' },
        target: { event_id: EVENT_ID, video_role: 'resolution', position: 0 },
      },
    });
    expect(r.status(), 'graft must reject missing mutation_id with HTTP 400').toBe(400);
    const body = await r.json().catch(() => ({}));
    expect(body?.error, 'response carries error="mutation_id_required"').toBe('mutation_id_required');
  });

  test('GR.3 — source beat not found returns HTTP 404 source_beat_not_found', async ({ request }) => {
    const r = await request.post(`${SERVER}/api/beat/graft`, {
      data: {
        source: { event_id: EVENT_ID, video_role: 'intro', beat_id: 'beat_DOES_NOT_EXIST' },
        target: { event_id: EVENT_ID, video_role: 'resolution', position: 0 },
        mutation_id: `gr3-${Date.now()}`,
      },
    });
    expect(r.status(), 'graft must return 404 for missing source beat').toBe(404);
    const body = await r.json();
    expect(body?.error).toBe('source_beat_not_found');
  });

  test.fixme('GR.4 — source beat with phase_1.status="completed" returns HTTP 400 graft_pre_render_only', async ({ request }) => {
    // After C-7: response 400 error="graft_pre_render_only"; pre-render-only invariant per RR-1 mitigation
  });

  test('GR.5 — cross-event graft without --source-event returns HTTP 409', async ({ request }) => {
    // Default server start (no --source-event flag); body proposes cross-event source.
    const r = await request.post(`${SERVER}/api/beat/graft`, {
      data: {
        source: { event_id: 'Event_OTHER', video_role: 'intro', beat_id: 'beat_01' },
        target: { event_id: EVENT_ID, video_role: 'intro', position: 0 },
        mutation_id: `gr5-${Date.now()}`,
      },
    });
    expect(r.status()).toBe(409);
    const body = await r.json();
    expect(body?.error).toBe('cross_event_requires_explicit_source');
    // Cross-event WITH the flag is exercised in SCR.3 against the C-9 salvage
    // context (server restarted with --source-event).
  });

  test.fixme('GR.6 — move=true deletes source after target write', async ({ request }) => {
    // GR.1 may have copied beat_01 already; use beat_03 (also in pristine intro)
    // so this test stays independent of GR.1 ordering.
    const r = await request.post(`${SERVER}/api/beat/graft`, {
      data: {
        source: { event_id: EVENT_ID, video_role: 'intro', beat_id: 'beat_03' },
        target: { event_id: EVENT_ID, video_role: 'resolution', position: 1 },
        mutation_id: `gr6-${Date.now()}`,
        move: true,
      },
    });
    expect(r.ok(), `move=true graft must succeed; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();
    const payload = await r.json();
    expect(payload?.status).toBe('moved');

    // Read state and confirm source removed + target seeded.
    const stateRes = await request.get(`${SERVER}/api/v2/event/${EVENT_ID}/state`);
    expect(stateRes.ok()).toBeTruthy();
    const state = await stateRes.json();
    const intro = state?.videos?.intro?.beats ?? {};
    const resolution = state?.videos?.resolution?.beats ?? {};
    expect(intro?.beat_03, 'source.beats[beat_03] must be absent post-move').toBeUndefined();
    expect(resolution?.beat_03, 'target.beats[beat_03] must be present post-move').toBeDefined();
  });
});

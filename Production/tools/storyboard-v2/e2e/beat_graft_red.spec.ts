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

const SERVER = 'http://localhost:5111';
const EVENT_ID = 'Event_e2e_fixture';

async function endpointReachable(request: APIRequestContext, path: string): Promise<boolean> {
  // OPTIONS-style probe: send a minimal POST and check that the server doesn't 404.
  // Until C-7 lands the route, the server returns 404 and these probes fail.
  const r = await request.post(`${SERVER}${path}`, { data: {} });
  return r.status() !== 404;
}

test.describe('Pillar 7 — /api/beat/graft (RED skeleton until C-7)', () => {
  // RED until C-7: un-fixme in C-7 commit (same commit as the /api/beat/graft handler implementation)
  test.fixme('endpoint registration sanity — /api/beat/graft route exists post-C-7', async ({ request }) => {
    // Pre-C-7: 404 (no route). Post-C-7: 400/422 (missing body fields) — anything
    // except 404 is acceptable for "route is registered."
    const reachable = await endpointReachable(request, '/api/beat/graft');
    expect(reachable, '/api/beat/graft must be a registered route after C-7').toBe(true);
  });

  test.fixme('GR.1 — same-event same-role graft writes target + pre-image + audit JSONL + Directus mirror; idempotent replay returns dedup', async ({ request }) => {
    // After C-7:
    //   - POST /api/beat/graft body = {source:{event_id,video_role,beat_id}, target:{...}, mutation_id:<uuid>}
    //   - Response 200 ok=true status="copied"
    //   - response.pre_image_paths contains a path under .backups/state/
    //   - Production/.recovery_audit.jsonl gains a row with action="beat_graft"
    //   - Directus prod_activity_log gains a mirror row
    //   - Replay with same mutation_id → status="dedup", no state change
  });

  test.fixme('GR.2 — missing mutation_id returns HTTP 400', async ({ request }) => {
    // After C-7: response 400 error="mutation_id_required"
  });

  test.fixme('GR.3 — source beat not found returns HTTP 404 + audit row beat_graft_failed', async ({ request }) => {
    // After C-7: response 404 error="source_beat_not_found"; audit row ok:false
  });

  test.fixme('GR.4 — source beat with phase_1.status="completed" returns HTTP 400 graft_pre_render_only', async ({ request }) => {
    // After C-7: response 400 error="graft_pre_render_only"; pre-render-only invariant per RR-1 mitigation
  });

  test.fixme('GR.5 — cross-event graft without --source-event flag returns HTTP 409 cross_event_requires_explicit_source', async ({ request }) => {
    // After C-7: response 409 error="cross_event_requires_explicit_source"
    // Note: server is started against a single event-dir; this test does NOT
    // restart the server. Cross-event with the flag is exercised in SCR.3
    // (which runs in the C-9 salvage context).
  });

  test.fixme('GR.6 — move=true deletes source after target write', async ({ request }) => {
    // After C-7:
    //   - First seed source beat (call /api/v2/beat/<bid>/patch)
    //   - POST /api/beat/graft body.move=true source/target same event different role
    //   - Source partition: source.beats[bid] absent; source.display_order excludes it
    //   - Target partition: target.beats[bid] present at requested position
  });
});

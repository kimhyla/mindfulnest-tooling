// scope_router_red — C-1 RED suite for the v59 authoring-workflow K-fixes.
//
// Per STORYBOARD_V59_AUTHORING_WORKFLOW_HANDOFF.md §4 C-1 + spec §10:
// these tests pin the prevention claims for K1-K8 + D5. They are expected
// to FAIL on this commit (RED phase per DS-2 TDD) and turn GREEN one at a
// time as C-2..C-7 + C-10 land:
//
//   K1 + D5 → C-2 (beat_update_text + patch_state via scope_router)
//   K2 + K7 → C-3 (bg_accept_beats partition write + speaker canon)
//   K3       → C-4 (bg_add_beat segment from scope)
//   K6       → C-5 (_assert_event_scope strict defaults)
//   K8       → C-6 (speaker dual-store mirror contract)
//   K4       → C-10 (DISPLAY_ORDER_STRICT_V2 in mutate_state — LAST per RR-4)
//
// All tests run against the live `production_server.py` Playwright spawns
// (see playwright.config.ts webServer block) against Event_e2e_fixture.
// global-setup.ts restores the pristine state before each run; tests can
// mutate freely.

import { test, expect, type APIRequestContext } from '@playwright/test';

const SERVER = 'http://localhost:5111';
const EVENT_ID = 'Event_e2e_fixture';

// Pristine fixture invariants (asserted by global-setup; mirrored here for
// reader convenience):
//   videos.intro      = display_order:int(1), beats:{beat_01, beat_02, beat_03}
//   videos.resolution = display_order:int(2), beats:{}
//   legacy state.beats = {} (top-level legacy is empty per LD-456)

async function getState(request: APIRequestContext): Promise<any> {
  const r = await request.get(`${SERVER}/api/v2/event/${EVENT_ID}/state`);
  if (!r.ok()) {
    throw new Error(`getState: HTTP ${r.status()} ${await r.text()}`);
  }
  return r.json();
}

test.describe('K1 — _handle_beat_update_text routes via scope_router (RED until C-2)', () => {
  // GREEN as of C-2 (un-fixme'd in same commit as the K1+D5 handler fix)
  test('TVMC-K1.1 — role=resolution edit lands in videos.resolution.beats, NOT videos.intro', async ({ request }) => {
    // beat_id MUST match _handle_beat_update_text's beat_NN parser
    // (`int(beat_id.split("_")[1])`); use a numeric form. beat_42 doesn't
    // collide with the fixture's beat_01..03 in intro.
    const beatId = 'beat_42';
    const text = `K1 RED ${Date.now()}`;
    const r = await request.post(`${SERVER}/api/beat/update_text`, {
      data: {
        event_id: EVENT_ID,
        scope_event_id: EVENT_ID,
        scope_target_video: 'resolution',
        beat: beatId,
        text,
        skip_tts_regen: true,
      },
    });
    expect(r.ok(), `update_text request must succeed; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();

    const state = await getState(request);
    const intro = state?.videos?.intro?.beats ?? {};
    const resolution = state?.videos?.resolution?.beats ?? {};

    // GREEN expectation (post-C-2): write lands in resolution; intro unchanged.
    expect(resolution?.[beatId]?.text, 'resolution.beats should hold the new text after C-2').toBe(text);
    expect(intro?.[beatId], 'videos.intro must NOT have been touched by a resolution-scoped write').toBeUndefined();
  });
});

test.describe('D5 — patch_state._apply routes target_partition via scope_router (RED until C-2)', () => {
  // GREEN as of C-2 (un-fixme'd in same commit)
  test('TVMC-D5.1 — patch_state pause_after_ms with role=resolution lands in videos.resolution', async ({ request }) => {
    // Numeric beat_NN (parser-friendly); 43 doesn't collide with fixture beats.
    const beatId = 'beat_43';
    const r = await request.post(`${SERVER}/api/v2/beat/${beatId}/patch`, {
      data: {
        field: 'pause_after_ms',
        value: 500,
        scope_event_id: EVENT_ID,
        scope_target_video: 'resolution',
        event_id: EVENT_ID,
        // expected_version omitted: handler treats None as "any" (skip version check).
        // Passing -1 explicitly triggers conflict (-1 != 0 current); that's a test-design
        // bug, not a contract one.
      },
    });
    // After C-2: HTTP 200 applied; before C-2: still 200 but write goes to videos.intro.
    expect(r.ok(), `patch_state must accept the request; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();

    const state = await getState(request);
    const introBeat = state?.videos?.intro?.beats?.[beatId];
    const resolutionBeat = state?.videos?.resolution?.beats?.[beatId];

    // pause_after_ms is stored at beat.phase_1.pause_after_ms per patch_state
    // _apply_partition (production_server.py: `beat.setdefault("phase_1", {})
    // ["pause_after_ms"] = int(_v)`). Asserting the top-level slot would
    // always be undefined regardless of fix correctness.
    expect(resolutionBeat?.phase_1?.pause_after_ms, 'resolution.beats[bid].phase_1.pause_after_ms must hold the patch value after C-2').toBe(500);
    expect(introBeat, 'videos.intro must NOT have been touched by a resolution-scoped patch').toBeUndefined();
  });
});

test.describe('K2 — bg_accept_beats writes to videos.<role>.beats, NOT top-level state.beats (RED until C-3)', () => {
  // GREEN as of C-3 (un-fixme'd in same commit as K2+K7 handler rewrite)
  test('TVMC-K2.1 — accept-beats partition write; legacy top-level state.beats stays empty', async ({ request }) => {
    const r = await request.post(`${SERVER}/api/bg/accept-beats`, {
      data: {
        event_id: EVENT_ID,
        scope_event_id: EVENT_ID,
        scope_target_video: 'intro',
        beats: [
          { accepted_image_key: 'k1', dialogue_text: 'partition test 1', speaker: 'Tessa' },
          { accepted_image_key: 'k2', dialogue_text: 'partition test 2', speaker: 'Chipper' },
        ],
      },
    });
    expect(r.ok(), `accept-beats must succeed; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();

    const state = await getState(request);
    const introBeats = state?.videos?.intro?.beats ?? {};
    const legacyBeats = state?.beats ?? {};

    // GREEN (post-C-3): seeded into the partition; legacy top-level untouched.
    expect(Object.keys(introBeats).length, 'videos.intro.beats must contain the seeded beats after C-3').toBeGreaterThanOrEqual(2);
    expect(Object.keys(legacyBeats).length, 'top-level state.beats (legacy) must remain empty per LD-456').toBe(0);
  });
});

test.describe('K6 — _assert_event_scope strict defaults (RED until C-5)', () => {
  // GREEN as of C-5 (un-fixme'd in C-5 commit; the underlying handler
  // _handle_beat_update_text was already migrated to scope_router in C-2,
  // but C-5 is the SCOPE_REQUIRED_DEFAULTS_V1 enforcement boundary)
  test('TVMC-K6.1 — POST without event_id returns HTTP 400 scope_required', async ({ request }) => {
    const r = await request.post(`${SERVER}/api/beat/update_text`, {
      data: {
        // Intentionally NO event_id / scope_event_id — server must reject after C-5.
        beat: 'beat_01',
        text: 'should be rejected',
      },
    });
    expect(r.status(), 'server must reject scope-less mutations with HTTP 400 after C-5').toBe(400);
    const body = await r.json().catch(() => ({}));
    expect(body?.error ?? body?.code, 'response must carry code "scope_required"').toBe('scope_required');
  });
});

test.describe('K7 — speaker write-boundary canonicalization (RED until C-3)', () => {
  // GREEN as of C-3 (un-fixme'd in same commit)
  test('TVMC-K7.1 — empty speaker stays empty (no "Guide Bird" default substitution)', async ({ request }) => {
    const r = await request.post(`${SERVER}/api/bg/accept-beats`, {
      data: {
        event_id: EVENT_ID,
        scope_event_id: EVENT_ID,
        scope_target_video: 'intro',
        beats: [
          { accepted_image_key: 'k7a', dialogue_text: 'empty speaker test', speaker: '' },
        ],
      },
    });
    expect(r.ok(), `accept-beats must succeed; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();

    const state = await getState(request);
    const introBeats = state?.videos?.intro?.beats ?? {};
    // Find the seeded beat (it'll be beat_01 — overwriting the fixture beat — per accept-beats positional naming).
    const seeded = introBeats?.beat_01;
    expect(seeded, 'seeded beat must be present in videos.intro.beats after C-3').toBeDefined();
    expect(seeded?.speaker, 'empty speaker must NOT be substituted with "Guide Bird"').not.toBe('Guide Bird');
    // Canonicalization of empty stays empty per LD-520 fail-loud-at-TTS contract.
    expect(seeded?.speaker, 'empty speaker remains empty').toBe('');
  });

  // GREEN as of C-3 (un-fixme'd in same commit)
  test('TVMC-K7.2 — "Guide Bird" sidecar value canonicalizes to "Chipper" at write boundary', async ({ request }) => {
    const r = await request.post(`${SERVER}/api/bg/accept-beats`, {
      data: {
        event_id: EVENT_ID,
        scope_event_id: EVENT_ID,
        scope_target_video: 'intro',
        beats: [
          { accepted_image_key: 'k7b', dialogue_text: 'guide bird canonicalize', speaker: 'Guide Bird' },
        ],
      },
    });
    expect(r.ok(), `accept-beats must succeed; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();

    const state = await getState(request);
    const seeded = state?.videos?.intro?.beats?.beat_01;
    expect(seeded?.speaker, '"Guide Bird" must be canonicalized to "Chipper" per _SPEAKER_ALIAS').toBe('Chipper');
  });
});

test.describe('K8 — speaker dual-store mirror (RED until C-6)', () => {
  // GREEN as of C-6 (un-fixme'd in same commit as K8 dual-store mirror contract)
  test('TVMC-K8.1 — patch_state speaker write mirrors to top-level partition.beats[bid].speaker AND phase_1.speaker', async ({ request }) => {
    // Use beat_44 (parser-friendly + non-colliding with fixture beat_01/02/03)
    // so this test does not pollute the rendered fixture for downstream tests.
    const beatId = 'beat_44';
    const r = await request.post(`${SERVER}/api/v2/beat/${beatId}/patch`, {
      data: {
        field: 'speaker',
        value: 'Guide Bird',  // canonicalizes to Chipper at write boundary per C-6
        scope_event_id: EVENT_ID,
        scope_target_video: 'intro',
        event_id: EVENT_ID,
        // expected_version omitted: skip version check (None == any).
      },
    });
    expect(r.ok(), `patch_state speaker must succeed; got HTTP ${r.status()}: ${await r.text()}`).toBeTruthy();

    const state = await getState(request);
    const beat = state?.videos?.intro?.beats?.[beatId];
    expect(beat, 'beat must exist post-patch').toBeDefined();
    // GREEN (post-C-6): both stores hold the canonical value.
    expect(beat?.speaker, 'top-level partition.beats[bid].speaker must hold canonical value after C-6').toBe('Chipper');
    expect(beat?.phase_1?.speaker, 'phase_1.speaker mirror must match top-level after C-6').toBe('Chipper');
  });
});

test.describe('K3 — bg_add_beat segment derived from scope (RED until C-4)', () => {
  // Skeleton: full BG-sidecar setup is non-trivial (requires arc-1/event-N/phase
  // segment seeded in the BG sidecar JSON). C-4 lands the handler change AND
  // the corresponding test fleshes out per the _resolve_bg_segment_for_scope
  // mapping (intro→pre, resolution→post, standalone→main). Skeleton intentionally
  // documents the assertion shape without exercising the sidecar — running RED
  // here would require fixture-tree mutation outside this commit's scope.
  test.fixme('TVMC-K3.1 — bg/add-beat segment matches (scope.event_id, scope.video_role)', async ({ request }) => {
    // After C-4 lands:
    //   - server reads scope_event_id + scope_target_video from body
    //   - derives (arc_number, event_id_int, phase) via _resolve_bg_segment_for_scope
    //   - calls bg.get_seg_entry with derived tuple
    //   - hardcoded `arc_number=1, event_id=2, phase="pre"` at line 9279 is gone
    //
    // Test contract (when fleshed out at C-4):
    //   - BG sidecar pre-seeded with segment for arc_1/event_<N>/phase_<intro→pre>
    //   - POST /api/bg/add-beat with scope_event_id=Event_<N>, scope_target_video=intro
    //   - Assert sidecar mutation lands in the matching segment, not arc_1/event_2/phase_pre
    expect(true).toBe(false);
  });
});

// TVMC-K4.1 (DISPLAY_ORDER_STRICT_V2 defense-in-depth in mutate_state)
// landed at C-10 as a Pytest per spec §11.1 — see
// Production/tools/tests/test_display_order_strict_v2.py. The Playwright
// scaffold here intentionally has no K4 test entry; CI runs both the
// Playwright suite + the Pytest suite (workflow `Sidecar TypeError
// regression` step adjacent to it runs the Pytest gate).

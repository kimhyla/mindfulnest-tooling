// PSL_STALE_KEY_HYDRATION_GUARD_V1 — stale session payloads must not hydrate
// the global UI signals after the active partition key changed mid-flight.
//
// Repro class (Event_5, 2026-07-17): page boots on ?video=intro, coordinator
// fetches the intro partition; VideoSelector adopts server active_video=
// resolution and a second fetch starts. The INTRO response lands LAST and
// last-writer-wins hydration clobbers bgBeats — header dropdown + authority
// badge say "resolution" while the beat list shows bg_arc1_event5_pre_beat_*.
//
// Golden payload shapes copied from live :5115 /api/bg/session-state probes
// (2026-07-17): active_context (sidecar) + scope_active_context (LD-545) +
// beats[] with real beat_id naming.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  activeMilestoneId,
  activeProjectType,
  activeScope,
  activeTargetVideo,
  makeScope,
} from '../scope';
import {
  bgActiveKey,
  bgBeats,
  ensureBgSession,
  refreshBgSession,
  resetBgSessionStoreForTesting,
} from '../bgSessionStore';
import {
  ensureMapSession,
  mapData,
  resetMapSessionStoreForTesting,
} from '../mapSessionStore';
import {
  ensureStoryboardSession,
  resetStoryboardSessionStoreForTesting,
  storyboardState,
} from '../storyboardSessionStore';
import {
  ensureStitchJobSession,
  resetStitchJobSessionStoreForTesting,
  stitchCachedJob,
} from '../stitchJobSessionStore';

// ---------------------------------------------------------------------------
// Environment stubs (node) — stores touch window/document at call time only.
// ---------------------------------------------------------------------------

const g = globalThis as Record<string, unknown>;
if (typeof g.window === 'undefined') g.window = globalThis;
if (typeof g.document === 'undefined') {
  g.document = {
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
    visibilityState: 'visible',
  };
}

// ---------------------------------------------------------------------------
// Controllable fetch — lets tests resolve responses OUT OF ORDER per request.
// ---------------------------------------------------------------------------

interface PendingRequest {
  url: URL;
  resolve: (body: unknown) => void;
}

let pendingRequests: PendingRequest[] = [];
const realFetch = globalThis.fetch;

function jsonResponse(body: unknown): unknown {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => body,
  };
}

function installFetchStub(): void {
  globalThis.fetch = (async (input: unknown) => {
    const url = new URL(String(input));
    // bg_segments resolves immediately — the race under test is on the
    // session-state / map / event-state / stitch-job payloads.
    if (url.pathname === '/api/bg/segments') {
      return jsonResponse({
        segments: [
          { event_id: '5', phase: 'pre', name: 'THERE IS NOTHING TO FEAR — Intro' },
          { event_id: '5', phase: 'post', name: 'THERE IS NOTHING TO FEAR — Resolution' },
        ],
        arc_number: 1,
      });
    }
    return await new Promise((resolveResponse) => {
      pendingRequests.push({
        url,
        resolve: (body: unknown) => resolveResponse(jsonResponse(body)),
      });
    });
  }) as typeof fetch;
}

function pendingMatching(predicate: (url: URL) => boolean): PendingRequest[] {
  return pendingRequests.filter((p) => predicate(p.url));
}

async function waitForPending(
  predicate: (url: URL) => boolean,
  label: string,
): Promise<PendingRequest> {
  for (let i = 0; i < 200; i += 1) {
    const match = pendingMatching(predicate)[0];
    if (match) return match;
    await new Promise((r) => { setTimeout(r, 1); });
  }
  throw new Error(`timed out waiting for pending request: ${label}`);
}

function releaseRequest(req: PendingRequest, body: unknown): void {
  pendingRequests = pendingRequests.filter((p) => p !== req);
  req.resolve(body);
}

// ---------------------------------------------------------------------------
// Golden payloads (live :5115 Event_5 shapes)
// ---------------------------------------------------------------------------

const INTRO_BEAT_IDS = [
  'bg_arc1_event5_pre_beat_01',
  'bg_arc1_event5_pre_beat_02',
  'bg_arc1_event5_pre_beat_03',
];
const RESOLUTION_BEAT_IDS = [
  'bg_arc1_event5_post_beat_01',
  'bg_arc1_event5_post_beat_02',
];

const INTRO_SESSION_PAYLOAD = {
  active_context: { arc_number: 1, event_id: '5', phase: 'pre' },
  scope_active_context: { arc_number: 1, event_id: '5', phase: 'pre' },
  beats: INTRO_BEAT_IDS.map((beat_id) => ({ beat_id, status: 'approved' })),
  flux_options_complete: false,
  capabilities: {},
  migration_warnings: [],
  o3_terminal_outcomes: [],
};

const RESOLUTION_SESSION_PAYLOAD = {
  active_context: { arc_number: 1, event_id: '5', phase: 'pre' },
  scope_active_context: { arc_number: 1, event_id: '5', phase: 'post' },
  beats: RESOLUTION_BEAT_IDS.map((beat_id) => ({ beat_id, status: 'approved' })),
  flux_options_complete: false,
  capabilities: {},
  migration_warnings: [],
  o3_terminal_outcomes: [],
};

const isBgSessionState = (u: URL) => u.pathname === '/api/bg/session-state';
const bgSessionStateForRole = (role: string) => (u: URL) =>
  isBgSessionState(u) && u.searchParams.get('scope_video_role') === role;

function beatIds(): string[] {
  return bgBeats.value.map((b) => b.beat_id);
}

beforeEach(() => {
  pendingRequests = [];
  installFetchStub();
  activeProjectType.value = 'event';
  activeMilestoneId.value = null;
  activeScope.value = makeScope('Event_5');
  activeTargetVideo.value = 'intro';
  resetBgSessionStoreForTesting();
  resetMapSessionStoreForTesting();
  resetStoryboardSessionStoreForTesting();
  resetStitchJobSessionStoreForTesting();
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe('PSL_STALE_KEY_HYDRATION_GUARD_V1 — Beat Gen session store', () => {
  it('boot race repro: stale INTRO payload landing after switch to resolution must not clobber beats', async () => {
    // Boot on intro (URL default) — fetch starts.
    const introEnsure = ensureBgSession('Event_5', 'intro');
    const introReq = await waitForPending(bgSessionStateForRole('intro'), 'intro session-state');

    // VideoSelector adopts server active_video=resolution mid-flight.
    activeTargetVideo.value = 'resolution';
    const resolutionEnsure = ensureBgSession('Event_5', 'resolution');
    const resolutionReq = await waitForPending(
      bgSessionStateForRole('resolution'),
      'resolution session-state',
    );

    // Resolution response lands FIRST — UI hydrates the correct partition.
    releaseRequest(resolutionReq, RESOLUTION_SESSION_PAYLOAD);
    await resolutionEnsure;
    expect(beatIds()).toEqual(RESOLUTION_BEAT_IDS);
    expect(bgActiveKey.value).toBe('Event_5|resolution');

    // Stale intro response lands LAST — must NOT hydrate global signals.
    releaseRequest(introReq, INTRO_SESSION_PAYLOAD);
    await introEnsure;
    expect(beatIds()).toEqual(RESOLUTION_BEAT_IDS);
    expect(bgActiveKey.value).toBe('Event_5|resolution');
  });

  it('reverse direction: stale RESOLUTION payload after switching back to intro must not clobber beats', async () => {
    activeTargetVideo.value = 'resolution';
    const resolutionEnsure = ensureBgSession('Event_5', 'resolution');
    const resolutionReq = await waitForPending(
      bgSessionStateForRole('resolution'),
      'resolution session-state',
    );

    activeTargetVideo.value = 'intro';
    const introEnsure = ensureBgSession('Event_5', 'intro');
    const introReq = await waitForPending(bgSessionStateForRole('intro'), 'intro session-state');

    releaseRequest(introReq, INTRO_SESSION_PAYLOAD);
    await introEnsure;
    expect(beatIds()).toEqual(INTRO_BEAT_IDS);

    releaseRequest(resolutionReq, RESOLUTION_SESSION_PAYLOAD);
    await resolutionEnsure;
    expect(beatIds()).toEqual(INTRO_BEAT_IDS);
    expect(bgActiveKey.value).toBe('Event_5|intro');
  });

  it('stale refreshBgSession completion after a partition switch must not clobber beats', async () => {
    // Hydrate intro fully first.
    const introEnsure = ensureBgSession('Event_5', 'intro');
    releaseRequest(
      await waitForPending(bgSessionStateForRole('intro'), 'intro session-state'),
      INTRO_SESSION_PAYLOAD,
    );
    await introEnsure;
    expect(beatIds()).toEqual(INTRO_BEAT_IDS);

    // Poll refresh for the intro key goes in flight…
    const refreshPromise = refreshBgSession();
    const refreshReq = await waitForPending(
      bgSessionStateForRole('intro'),
      'intro refresh session-state',
    );

    // …operator switches to resolution and it hydrates.
    activeTargetVideo.value = 'resolution';
    const resolutionEnsure = ensureBgSession('Event_5', 'resolution');
    releaseRequest(
      await waitForPending(bgSessionStateForRole('resolution'), 'resolution session-state'),
      RESOLUTION_SESSION_PAYLOAD,
    );
    await resolutionEnsure;
    expect(beatIds()).toEqual(RESOLUTION_BEAT_IDS);

    // Stale intro refresh lands last — must NOT clobber the live partition.
    releaseRequest(refreshReq, INTRO_SESSION_PAYLOAD);
    await refreshPromise;
    expect(beatIds()).toEqual(RESOLUTION_BEAT_IDS);
    expect(bgActiveKey.value).toBe('Event_5|resolution');
  });

  it('refreshBgSession with a desynced active key must not fetch (cross-partition cache poisoning)', async () => {
    // Hydrate intro fully first.
    const introEnsure = ensureBgSession('Event_5', 'intro');
    releaseRequest(
      await waitForPending(bgSessionStateForRole('intro'), 'intro session-state'),
      INTRO_SESSION_PAYLOAD,
    );
    await introEnsure;
    expect(bgActiveKey.value).toBe('Event_5|intro');

    // Live scope flips to resolution but the coordinator's ensure has not
    // hydrated yet — bgActiveKey is momentarily desynced. A wake refresh in
    // this window would fetch the RESOLUTION partition (query derives from
    // live scope) and cache it under the INTRO key.
    activeTargetVideo.value = 'resolution';
    const refreshed = await refreshBgSession();
    expect(refreshed).toBe(false);
    expect(pendingMatching(isBgSessionState)).toHaveLength(0);
  });
});

describe('PSL_STALE_KEY_HYDRATION_GUARD_V1 — sibling PSL stores', () => {
  it('map store: stale event payload after event switch must not clobber mapData', async () => {
    const isMap = (u: URL) => u.pathname === '/api/production/map';

    const ensureA = ensureMapSession('Event_1');
    const reqA = await waitForPending(isMap, 'map Event_1');

    activeScope.value = makeScope('Event_2');
    const ensureB = ensureMapSession('Event_2');
    let reqB = pendingMatching(isMap).find((p) => p !== reqA);
    for (let i = 0; !reqB && i < 200; i += 1) {
      await new Promise((r) => { setTimeout(r, 1); });
      reqB = pendingMatching(isMap).find((p) => p !== reqA);
    }
    if (!reqB) throw new Error('timed out waiting for pending request: map Event_2');

    releaseRequest(reqB, { modules: [{ module_id: 'M2E1', title: 'Event 2 map' }] });
    await ensureB;
    expect(mapData.value?.modules?.[0]?.module_id).toBe('M2E1');

    releaseRequest(reqA, { modules: [{ module_id: 'M1E1', title: 'Event 1 map' }] });
    await ensureA;
    expect(mapData.value?.modules?.[0]?.module_id).toBe('M2E1');
  });

  it('storyboard store: stale event-state payload after event switch must not clobber storyboardState', async () => {
    const isEventState = (eventId: string) => (u: URL) =>
      u.pathname === `/api/v2/event/${eventId}/state`;

    const ensureA = ensureStoryboardSession('Event_1', 'event', null);
    const reqA = await waitForPending(isEventState('Event_1'), 'event-state Event_1');

    activeScope.value = makeScope('Event_2');
    const ensureB = ensureStoryboardSession('Event_2', 'event', null);
    const reqB = await waitForPending(isEventState('Event_2'), 'event-state Event_2');

    releaseRequest(reqB, { event_id: 'Event_2', videos: {} });
    await ensureB;
    expect(storyboardState.value?.event_id).toBe('Event_2');

    releaseRequest(reqA, { event_id: 'Event_1', videos: {} });
    await ensureA;
    expect(storyboardState.value?.event_id).toBe('Event_2');
  });

  it('stitch store: stale job payload after event switch must not clobber stitchCachedJob', async () => {
    const isStitchJob = (jobName: string) => (u: URL) =>
      u.pathname === `/api/stitch_editor/job/${jobName}`;

    const ensureA = ensureStitchJobSession('Event_1', { projectType: 'event', milestoneId: null });
    const reqA = await waitForPending(isStitchJob('Event_1_stitch'), 'stitch job Event_1');

    activeScope.value = makeScope('Event_2');
    const ensureB = ensureStitchJobSession('Event_2', { projectType: 'event', milestoneId: null });
    const reqB = await waitForPending(isStitchJob('Event_2_stitch'), 'stitch job Event_2');

    releaseRequest(reqB, { job: { name: 'Event_2_stitch', slots: {} } });
    await ensureB;
    expect(stitchCachedJob.value?.name).toBe('Event_2_stitch');

    releaseRequest(reqA, { job: { name: 'Event_1_stitch', slots: {} } });
    await ensureA;
    expect(stitchCachedJob.value?.name).toBe('Event_2_stitch');
  });
});

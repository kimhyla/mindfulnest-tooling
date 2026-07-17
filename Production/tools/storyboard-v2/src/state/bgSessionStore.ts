/**
 * PSL — Beat Generator session store (beats, segments, poll job signals).
 */

import { signal } from '@preact/signals';
import { apiGet } from '../api/client';
import { handleO3TerminalOutcomesFromSession } from '../utils/o3SessionTerminalOutcomes';
import {
  applyPromptEditsToBeats,
} from './promptEditRegistry';
import { mergeBeatsOnSessionHydrate } from '../utils/bgSessionBeatMerge';
import type { BgBeat, BgSegment, GptOption } from '../types/bgBeat';
import { bgSessionKey } from './producerSessionKeys';
import {
  activeScope,
  activeScopeQueryParams,
  activeMilestoneId,
  activeProjectType,
  effectiveScopeVideoRole,
  readPersistedMilestoneId,
} from './scope';
import { confirmServerMilestoneScope } from './milestoneScopeGate';
import {
  isSessionFresh,
  runSessionFetch,
  sessionHasReadyCache,
  type SessionSliceMeta,
  resetSessionMeta,
} from './sessionCacheCore';
import {
  collectActiveGptBatchJobFromBeats,
  pruneActiveStillRenderJobs,
  pruneGptBatchSubmitPending,
  stillInsertBeatIdsFromBeats,
} from '../utils/bgBeatNavStatus';
import {
  activeO3PollJobsFromBeats,
  o3UiJobIdFromBeat,
  pruneO3SubmitPending,
  pruneSubmitPollLatch,
} from '../o3JobStatusContract';
import {
  expectedBgSessionKeyNow,
  sessionPayloadMayHydrate,
} from './sessionHydrationAuthority';
import { shouldToastBgSessionRefreshFailure } from '../utils/bgSessionRefreshFailure';
import { shouldToastBgSessionLoadFailure } from '../utils/bgSessionLoadFailure';
import {
  beatCountDropMessage,
  shouldWarnBeatCountDrop,
} from '../utils/bgSessionBeatCountDrop';
import {
  BG_SESSION_RESTART_RETRY_DELAYS_MS,
  delayBeforeBgSessionRetry,
  isTransientSessionFetchError,
} from '../utils/sessionFetchRetry';
import { pushToast } from '../components/ui/Toast';
import type { ApiResult } from '../api/client';

const BG_SESSION_STALE_MS = 30_000;
const BG_SESSION_STATE_FETCH_TIMEOUT_MS = 120_000;
const BG_SESSION_LOAD_SLOW_HINT_MS = 8000;

interface BgSegmentsResponse {
  segments?: BgSegment[];
  arc_number?: number;
}

interface BgSessionStateResponse {
  active_context?: { arc_number: number; event_id: string; phase: string } | null;
  scope_active_context?: { arc_number: number; event_id: string; phase: string } | null;
  beats?: BgBeat[];
  capabilities?: {
    lipsync_public_host_ready?: boolean;
    lipsync_public_host_message?: string | null;
  };
  o3_terminal_outcomes?: import('../utils/o3SessionTerminalOutcomes').O3TerminalOutcome[];
}

interface BgSessionRow {
  key: string;
  meta: SessionSliceMeta;
  arcNumber: number;
  segments: BgSegment[];
  beats: BgBeat[];
  activeSegment: string;
  lipsyncReady: boolean | null;
  lipsyncMessage: string | null;
  activeJobId: string | null;
  activeO3Jobs: Record<string, string>;
  o3SubmitPending: Record<string, boolean>;
  gptBatchSubmitPending: Record<string, boolean>;
  activeStillRenderJobs: Record<string, boolean>;
  activeNativeLipSyncJobs: Record<string, string>;
}

const rows = new Map<string, BgSessionRow>();

export const bgActiveKey = signal<string>('');

export const bgSegments = signal<BgSegment[]>([]);
export const bgArcNumber = signal<number>(1);
export const bgActiveSegment = signal<string>('');
export const bgBeats = signal<BgBeat[]>([]);
export const bgSessionLoading = signal(false);
export const bgSessionSlowHint = signal(false);
export const bgLipsyncPublicHostReady = signal<boolean | null>(null);
export const bgLipsyncPublicHostMessage = signal<string | null>(null);
export const bgActiveJobId = signal<string | null>(null);
export const bgActiveO3Jobs = signal<Record<string, string>>({});
export const bgO3IntentByBeat = signal<Record<string, unknown>>({});
export const bgO3SubmitAuditByBeat = signal<Record<string, unknown>>({});
export const bgO3SubmitPending = signal<Record<string, boolean>>({});
export const bgO3WarningByBeat = signal<Record<string, string>>({});
export const bgActiveStillRenderJobs = signal<Record<string, boolean>>({});
export const bgGptBatchSubmitPending = signal<Record<string, boolean>>({});
export const bgActiveNativeLipSyncJobs = signal<Record<string, string>>({});
export const bgPollResults = signal<Record<string, GptOption[]>>({});

export const submitPollLatchRef: { current: Record<string, string> } = { current: {} };
export const genFailureToastRef: { current: Set<string> } = { current: new Set() };
export const beatSaveNotFoundToastRef: { current: Set<string> } = { current: new Set() };
export const beatSaveBlockedRef: { current: Set<string> } = { current: new Set() };

function rowForKey(key: string): BgSessionRow {
  let row = rows.get(key);
  if (!row) {
    row = {
      key,
      meta: { status: 'idle', error: null, fetchedAt: 0, inflight: null },
      arcNumber: 1,
      segments: [],
      beats: [],
      activeSegment: '',
      lipsyncReady: null,
      lipsyncMessage: null,
      activeJobId: null,
      activeO3Jobs: {},
      o3SubmitPending: {},
      gptBatchSubmitPending: {},
      activeStillRenderJobs: {},
      activeNativeLipSyncJobs: {},
    };
    rows.set(key, row);
  }
  return row;
}

function pauseAllBeatGenMedia(root: ParentNode = document): void {
  root.querySelectorAll<HTMLMediaElement>(
    '.mn-bg-option video, .mn-bg-magic-preview video, .mn-bg-magic-preview audio',
  ).forEach((el) => {
    try {
      el.pause();
    } catch {
      // defensive
    }
  });
}

function collectActiveNativeLipSyncJobsFromBeats(beats: BgBeat[]): Record<string, string> {
  const jobs: Record<string, string> = {};
  for (const beat of beats) {
    const jobId = (beat.kling_native_lipsync_experiment_ui_job_id ?? '').trim();
    const status = (beat.kling_native_lipsync_experiment_status ?? '').trim().toLowerCase();
    if (jobId && status === 'running') {
      jobs[beat.beat_id] = jobId;
    }
  }
  return jobs;
}

function seedGenFailureSeenKeys(beats: BgBeat[]): void {
  for (const beat of beats) {
    const key = beat.kling_o3_voice_fix_error
      ? `vf:${beat.beat_id}:${beat.kling_o3_voice_fix_error}`
      : beat.status === 'failed' ? `st:${beat.beat_id}` : '';
    if (key) genFailureToastRef.current.add(key);
  }
}

const bgSessionStateQuery = (_eventId: string, _videoRole: string) => {
  const role = effectiveScopeVideoRole();
  return {
    ...activeScopeQueryParams(),
    scope_video_role: role,
    scope_target_video: role,
  };
};

function hydrateSignalsFromRow(row: BgSessionRow): void {
  bgActiveKey.value = row.key;
  bgSegments.value = row.segments;
  bgArcNumber.value = row.arcNumber;
  bgActiveSegment.value = row.activeSegment;
  bgBeats.value = row.beats;
  bgLipsyncPublicHostReady.value = row.lipsyncReady;
  bgLipsyncPublicHostMessage.value = row.lipsyncMessage;
  bgActiveJobId.value = row.activeJobId;
  bgActiveO3Jobs.value = row.activeO3Jobs;
  bgO3SubmitPending.value = row.o3SubmitPending;
  bgGptBatchSubmitPending.value = row.gptBatchSubmitPending;
  bgActiveStillRenderJobs.value = row.activeStillRenderJobs;
  bgActiveNativeLipSyncJobs.value = row.activeNativeLipSyncJobs;
}

function snapshotActiveRow(): void {
  const key = bgActiveKey.value;
  if (!key) return;
  const row = rowForKey(key);
  row.segments = bgSegments.value;
  row.arcNumber = bgArcNumber.value;
  row.activeSegment = bgActiveSegment.value;
  row.beats = bgBeats.value;
  row.lipsyncReady = bgLipsyncPublicHostReady.value;
  row.lipsyncMessage = bgLipsyncPublicHostMessage.value;
  row.activeJobId = bgActiveJobId.value;
  row.activeO3Jobs = bgActiveO3Jobs.value;
  row.o3SubmitPending = bgO3SubmitPending.value;
  row.gptBatchSubmitPending = bgGptBatchSubmitPending.value;
  row.activeStillRenderJobs = bgActiveStillRenderJobs.value;
  row.activeNativeLipSyncJobs = bgActiveNativeLipSyncJobs.value;
}

export function bgSessionHasCache(): boolean {
  const key = bgActiveKey.value;
  if (!key) return false;
  const row = rows.get(key);
  return Boolean(row && sessionHasReadyCache(row.meta.status, row.beats.length > 0));
}

export function updateBgBeats(
  updater: BgBeat[] | ((prev: BgBeat[]) => BgBeat[]),
): void {
  bgBeats.value = typeof updater === 'function' ? updater(bgBeats.value) : updater;
  snapshotActiveRow();
}

function applySessionPayload(
  key: string,
  segs: BgSegment[],
  stateRes: BgSessionStateResponse,
  arcHint: number,
  prevBeats: BgBeat[],
): void {
  const row = rowForKey(key);
  row.segments = segs;
  const ctx = stateRes.scope_active_context ?? stateRes.active_context;
  if (ctx) {
    row.arcNumber = Number(ctx.arc_number) || arcHint;
    row.activeSegment = `${ctx.event_id}|${ctx.phase}`;
  } else if (segs.length > 0) {
    row.activeSegment = `${segs[0].event_id}|${segs[0].phase}`;
  }
  const nextBeats = applyPromptEditsToBeats(stateRes.beats ?? []);
  pauseAllBeatGenMedia();
  row.beats = mergeBeatsOnSessionHydrate(prevBeats, nextBeats);
  row.lipsyncReady = stateRes.capabilities?.lipsync_public_host_ready ?? null;
  row.lipsyncMessage = stateRes.capabilities?.lipsync_public_host_message ?? null;
  seedGenFailureSeenKeys(row.beats);
  const nextGptJob = collectActiveGptBatchJobFromBeats(row.beats);
  row.activeJobId = nextGptJob;
  for (const id of stillInsertBeatIdsFromBeats(row.beats)) {
    delete submitPollLatchRef.current[id];
  }
  submitPollLatchRef.current = pruneSubmitPollLatch(row.beats, submitPollLatchRef.current);
  const nextO3Jobs = activeO3PollJobsFromBeats(row.beats, submitPollLatchRef.current);
  for (const id of stillInsertBeatIdsFromBeats(row.beats)) {
    delete nextO3Jobs[id];
  }
  row.activeO3Jobs = nextO3Jobs;
  row.o3SubmitPending = pruneO3SubmitPending(row.beats, {});
  row.gptBatchSubmitPending = pruneGptBatchSubmitPending(row.beats, {}, nextGptJob);
  row.activeStillRenderJobs = pruneActiveStillRenderJobs(row.beats, row.activeStillRenderJobs);
  row.activeNativeLipSyncJobs = collectActiveNativeLipSyncJobsFromBeats(row.beats);
  row.meta.status = 'ready';
  row.meta.fetchedAt = Date.now();
  // PSL_STALE_KEY_HYDRATION_GUARD_V1 — a payload fetched for a partition the
  // UI no longer shows updates its cache row above but must NOT clobber the
  // live signals (boot race: stale intro response landing after the operator
  // switched to resolution).
  if (sessionPayloadMayHydrate(key, expectedBgSessionKeyNow())) {
    hydrateSignalsFromRow(row);
  }
  void handleO3TerminalOutcomesFromSession(stateRes.o3_terminal_outcomes);
}

async function fetchBgSessionPayload(
  eventId: string,
  videoRole: string,
  arc: number,
): Promise<{
  segRes: ApiResult<BgSegmentsResponse>;
  stateRes: ApiResult<BgSessionStateResponse>;
  arc: number;
}> {
  const maxAttempts = BG_SESSION_RESTART_RETRY_DELAYS_MS.length + 1;
  let lastError = 'Beat Gen session-state unavailable';
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) {
      await delayBeforeBgSessionRetry(attempt);
    }
    const segRes = await apiGet<BgSegmentsResponse>('bg_segments', {
      arc_number: String(arc),
      ...activeScopeQueryParams(),
    });
    const stateRes = await apiGet<BgSessionStateResponse>(
      'bg_session_state',
      bgSessionStateQuery(eventId, videoRole),
      { fetchTimeoutMs: BG_SESSION_STATE_FETCH_TIMEOUT_MS },
    );
    if (stateRes.ok) {
      return { segRes, stateRes, arc };
    }
    lastError = stateRes.error ?? `HTTP ${stateRes.status}`;
    if (!isTransientSessionFetchError(lastError)) {
      throw new Error(lastError);
    }
  }
  throw new Error(lastError);
}

async function reloadMilestoneScopeIfNeeded(): Promise<boolean> {
  if (activeProjectType.value !== 'milestone') return false;
  const milestoneId = activeMilestoneId.value || readPersistedMilestoneId();
  if (!milestoneId) return false;
  const confirmed = await confirmServerMilestoneScope(activeScope.value);
  return confirmed.ok;
}

export async function ensureBgSession(
  eventId: string,
  _videoRole: string,
  opts?: { force?: boolean; arcNumber?: number },
): Promise<void> {
  const scopeRole = effectiveScopeVideoRole();
  const key = bgSessionKey(eventId, scopeRole);
  const row = rowForKey(key);
  const arc = opts?.arcNumber ?? row.arcNumber ?? bgArcNumber.value;
  const hadCachedBeats = row.beats.length > 0;

  if (hadCachedBeats) {
    hydrateSignalsFromRow(row);
  }

  let slowTimer: number | null = null;
  const clearSlow = () => {
    if (slowTimer !== null) {
      window.clearTimeout(slowTimer);
      slowTimer = null;
    }
    bgSessionSlowHint.value = false;
  };

  await runSessionFetch(row.meta, {
    force: opts?.force ?? false,
    staleMs: BG_SESSION_STALE_MS,
    hasPayload: () => sessionHasReadyCache(row.meta.status, row.beats.length > 0),
    showLoading: (on) => {
      if (on && !sessionHasReadyCache(row.meta.status, row.beats.length > 0)) {
        slowTimer = window.setTimeout(() => {
          bgSessionSlowHint.value = true;
        }, BG_SESSION_LOAD_SLOW_HINT_MS);
        bgSessionLoading.value = true;
      } else if (!on) {
        clearSlow();
        bgSessionLoading.value = false;
      }
    },
    fetcher: async () => {
      let payload = await fetchBgSessionPayload(eventId, scopeRole, arc);
      const beatCount = payload.stateRes.data?.beats?.length ?? 0;
      if (
        beatCount === 0
        && activeProjectType.value === 'milestone'
        && (activeMilestoneId.value || readPersistedMilestoneId())
      ) {
        const reloaded = await reloadMilestoneScopeIfNeeded();
        if (reloaded) {
          payload = await fetchBgSessionPayload(eventId, scopeRole, arc);
        }
      }
      return payload;
    },
    onSuccess: ({ segRes, stateRes, arc }) => {
      const segs = segRes.data?.segments ?? [];
      row.arcNumber = Number(segRes.data?.arc_number) || arc;
      const prevCount = row.beats.length;
      applySessionPayload(key, segs, stateRes.data ?? {}, row.arcNumber, row.beats);
      const nextCount = row.beats.length;
      if (shouldWarnBeatCountDrop(prevCount, nextCount)) {
        pushToast({
          kind: 'warning',
          message: beatCountDropMessage(prevCount, nextCount),
          source: 'bg-beat-count-drop',
        });
      }
    },
    onError: (message) => {
      if (
        !shouldToastBgSessionLoadFailure({
          message,
          hadCachedBeats,
          retriesExhausted: true,
        })
      ) {
        return;
      }
      pushToast({
        kind: 'error',
        message: `Could not load beat state: ${message}`,
        source: 'bg-session-load-error',
      });
    },
  });
}

export async function refreshBgSession(): Promise<boolean> {
  const key = bgActiveKey.value;
  if (!key) return false;
  // PSL_STALE_KEY_HYDRATION_GUARD_V1 — never poll a partition the UI no
  // longer shows. bgSessionStateQuery derives the role from live scope
  // truth, so a desynced key would cache the WRONG partition's beats into
  // this row (cross-partition poisoning). The coordinator ensures the
  // expected key on its own.
  if (!sessionPayloadMayHydrate(key, expectedBgSessionKeyNow())) return false;
  const [eventId, videoRole] = key.split('|');
  const row = rowForKey(key);
  const hadBusyLatch =
    Object.keys(bgActiveO3Jobs.value).length > 0
    || Object.values(bgO3SubmitPending.value).some(Boolean)
    || Object.keys(submitPollLatchRef.current).length > 0;

  const stateRes = await apiGet<BgSessionStateResponse>(
    'bg_session_state',
    bgSessionStateQuery(eventId, videoRole),
    { fetchTimeoutMs: BG_SESSION_STATE_FETCH_TIMEOUT_MS },
  );

  if (!stateRes.ok || !stateRes.data) {
    if (shouldToastBgSessionRefreshFailure(hadBusyLatch, stateRes.ok, Boolean(stateRes.data))) {
      pushToast({
        kind: 'error',
        message: 'Beat Gen refresh failed — retrying on next wake.',
        source: 'bg-session-refresh',
      });
    }
    return false;
  }

  applySessionPayload(key, row.segments, stateRes.data, row.arcNumber, row.beats);
  return true;
}

let refreshBgSessionInFlight: Promise<boolean> | null = null;
let refreshBgSessionDebounceTimer: ReturnType<typeof setTimeout> | null = null;

/** Coalesce overlapping poll refreshes — OPERATOR_SESSION_PERF_V1. */
export function scheduleRefreshBgSession(debounceMs = 150): void {
  if (refreshBgSessionDebounceTimer !== null) {
    clearTimeout(refreshBgSessionDebounceTimer);
  }
  refreshBgSessionDebounceTimer = setTimeout(() => {
    refreshBgSessionDebounceTimer = null;
    void refreshBgSessionCoalesced();
  }, debounceMs);
}

export async function refreshBgSessionCoalesced(): Promise<boolean> {
  if (refreshBgSessionInFlight) return refreshBgSessionInFlight;
  refreshBgSessionInFlight = refreshBgSession().finally(() => {
    refreshBgSessionInFlight = null;
  });
  return refreshBgSessionInFlight;
}

/** Wire submit ack or session reattach into poll map + nav busy indicators. */
export function applyO3SubmitPollLatch(beatId: string, jobId: string): void {
  const id = beatId.trim();
  const jid = jobId.trim();
  if (!id || !jid) return;
  submitPollLatchRef.current[id] = jid;
  bgActiveO3Jobs.value = activeO3PollJobsFromBeats(
    bgBeats.value,
    submitPollLatchRef.current,
  );
}

/** After ambiguous submit (network / BEAT_JOB_BUSY), reattach from server job_busy truth. */
export async function tryReattachO3JobFromSession(beatId: string): Promise<boolean> {
  const ok = await refreshBgSession();
  if (!ok) return false;
  const beat = bgBeats.value.find((b) => b.beat_id === beatId);
  if (!beat || beat.job_busy !== true) return false;
  const jobId = o3UiJobIdFromBeat(beat);
  if (!jobId) return false;
  applyO3SubmitPollLatch(beatId, jobId);
  return true;
}

export function resetBgSessionStoreForTesting(): void {
  rows.clear();
  bgActiveKey.value = '';
  bgSegments.value = [];
  bgArcNumber.value = 1;
  bgActiveSegment.value = '';
  bgBeats.value = [];
  bgSessionLoading.value = false;
  bgSessionSlowHint.value = false;
  submitPollLatchRef.current = {};
  genFailureToastRef.current = new Set();
  beatSaveNotFoundToastRef.current = new Set();
  beatSaveBlockedRef.current = new Set();
}

export function __bgSessionMetaForKey(key: string): SessionSliceMeta {
  return rowForKey(key).meta;
}

export function __isBgSessionFresh(key: string): boolean {
  const meta = rowForKey(key).meta;
  return isSessionFresh(meta.fetchedAt, BG_SESSION_STALE_MS);
}

export { resetSessionMeta };
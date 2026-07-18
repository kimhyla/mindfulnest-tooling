/** PSL — Stitch editor job JSON cache (hydration still runs in StitcherTab). */

import { signal } from '@preact/signals';
import { apiGet } from '../api/client';
import { stitchJobSessionKey, stitchJobNameForScope } from './producerSessionKeys';
import {
  expectedStitchJobSessionKeyNow,
  sessionPayloadMayHydrate,
} from './sessionHydrationAuthority';
import { activeMilestoneId, activeProjectType } from './scope';
import {
  runSessionFetch,
  sessionHasReadyCache,
  type SessionSliceMeta,
} from './sessionCacheCore';

const STITCH_STALE_MS = 30_000;

export interface StitchSlot {
  video_path?: string;
  video_dur_ms?: number;
  [key: string]: unknown;
}

export interface StitchJob {
  name?: string;
  slots?: Record<string, StitchSlot> | StitchSlot[];
  transitions?: unknown[];
  bake_path?: string;
  active_bake_job_id?: string;
  [key: string]: unknown;
}

interface StitchRow {
  meta: SessionSliceMeta;
  job: StitchJob | null;
  jobName: string;
}

const rows = new Map<string, StitchRow>();

export const stitchActiveKey = signal('');
export const stitchCachedJob = signal<StitchJob | null>(null);
export const stitchJobLoading = signal(false);
export const stitchJobError = signal<string | null>(null);

function rowForKey(key: string, jobName: string): StitchRow {
  let row = rows.get(key);
  if (!row) {
    row = {
      meta: { status: 'idle', error: null, fetchedAt: 0, inflight: null },
      job: null,
      jobName,
    };
    rows.set(key, row);
  }
  return row;
}

export function stitchJobSessionHasCache(): boolean {
  const row = rows.get(stitchActiveKey.value);
  return Boolean(row && sessionHasReadyCache(row.meta.status, Boolean(row.job)));
}

export async function ensureStitchJobSession(
  eventId: string,
  opts?: { force?: boolean; projectType?: string; milestoneId?: string | null },
): Promise<void> {
  const projectType = opts?.projectType ?? activeProjectType.value;
  const milestoneId = opts?.milestoneId !== undefined ? opts.milestoneId : activeMilestoneId.value;
  const key = stitchJobSessionKey(eventId, projectType, milestoneId);
  const jobName = stitchJobNameForScope(eventId, projectType, milestoneId);
  const row = rowForKey(key, jobName);
  stitchActiveKey.value = key;

  await runSessionFetch(row.meta, {
    force: opts?.force ?? false,
    staleMs: STITCH_STALE_MS,
    hasPayload: () => sessionHasReadyCache(row.meta.status, Boolean(row.job)),
    showLoading: (on) => { stitchJobLoading.value = on && !stitchJobSessionHasCache(); },
    fetcher: async () => {
      const res = await apiGet<{ job?: StitchJob; name?: string }>(
        'stitch_editor_job',
        { job_name: jobName },
        { fetchTimeoutMs: 120000 },
      );
      if (!res.ok) {
        throw new Error(res.error ?? `HTTP ${res.status}`);
      }
      return res.data?.job ?? null;
    },
    onSuccess: (job) => {
      row.job = job;
      // PSL_STALE_KEY_HYDRATION_GUARD_V1 — stale completions cache silently.
      if (sessionPayloadMayHydrate(key, expectedStitchJobSessionKeyNow())) {
        stitchCachedJob.value = job;
        stitchJobError.value = null;
      }
    },
    onError: (message) => {
      if (sessionPayloadMayHydrate(key, expectedStitchJobSessionKeyNow())) {
        stitchJobError.value = message;
      }
    },
  });
}

export function resetStitchJobSessionStoreForTesting(): void {
  rows.clear();
  stitchActiveKey.value = '';
  stitchCachedJob.value = null;
  stitchJobLoading.value = false;
  stitchJobError.value = null;
}

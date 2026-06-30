/**
 * BG async job polls — always mounted so jobs survive tab unmount (PSL).
 */

import { useEffect } from 'preact/hooks';
import { apiGet } from '../api/client';
import type { GptOption } from '../types/bgBeat';
import type { ArloO3PollResponse } from '../o3GenerationIntent';
import { pushToast } from './ui/Toast';
import {
  bgActiveJobId,
  bgActiveNativeLipSyncJobs,
  bgActiveO3Jobs,
  bgO3IntentByBeat,
  bgO3SubmitAuditByBeat,
  bgO3WarningByBeat,
  bgPollResults,
  scheduleRefreshBgSession,
  submitPollLatchRef,
  updateBgBeats,
} from '../state/bgSessionStore';
import {
  formatO3JobFailure,
  isNetworkPollBlip,
  isSidecarLockPollBlip,
  isStaleO3JobPoll,
  beatPatchFromO3PollTerminal,
  mergeBeatFromO3Poll,
  o3PollResultHasVideo,
} from '../utils/bgPollHelpers';

const POLL_INTERVAL_MS = 10000;
const O3_POLL_INTERVAL_MS = 3000;
const PER_IMAGE_COST_USD = 0.04;

interface GptPollResponse {
  status: 'running' | 'done';
  results: Record<string, GptOption[]>;
  total: number;
  done_count: number;
}

interface NativeLipSyncPollResponse {
  status: 'running' | 'done' | 'failed';
  beat_id?: string;
  route?: string;
  result?: {
    status?: string;
    passed_gate?: boolean;
    raw_profile?: {
      width?: number;
      height?: number;
      min_dimension?: number;
      has_audio?: boolean;
    };
    raw_output_path?: string;
    error?: string | null;
    error_code?: string | null;
  } | null;
  error?: string | null;
}

export function BgPollCoordinator() {
  // GPT batch poll
  useEffect(() => {
    const activeJobId = bgActiveJobId.value;
    if (!activeJobId) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const jobId = bgActiveJobId.value;
      if (!jobId) return;
      const res = await apiGet<GptPollResponse>('bg_poll_gpt_status', { job_id: jobId });
      if (cancelled) return;
      if (res.ok && res.data) {
        bgPollResults.value = res.data.results ?? {};
        if (res.data.status === 'done') {
          bgActiveJobId.value = null;
          let cost = 0;
          for (const opts of Object.values(res.data.results ?? {})) {
            for (const o of opts) {
              if (typeof o.cost_usd === 'number') cost += o.cost_usd;
            }
          }
          if (cost === 0) cost = res.data.done_count * PER_IMAGE_COST_USD;
          pushToast({
            kind: 'success',
            message: `Generated ${res.data.done_count} options ($${cost.toFixed(2)})`,
            source: 'bg-batch-done',
          });
          scheduleRefreshBgSession();
          return;
        }
      } else {
        pushToast({ kind: 'error', message: `Poll error: ${res.error}`, source: 'bg-poll-error' });
        bgActiveJobId.value = null;
        return;
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [bgActiveJobId.value]);

  // O3 voice poll
  useEffect(() => {
    const entries = Object.entries(bgActiveO3Jobs.value);
    if (entries.length === 0) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const jobs = Object.entries(bgActiveO3Jobs.value);
      let anyStillRunning = false;
      const completedBeatIds: string[] = [];
      const failedBeatIds: string[] = [];
      const staleBeatIds: string[] = [];
      const beatPatches: import('../types/bgBeat').BgBeat[] = [];

      await Promise.all(jobs.map(async ([beatId, jobId]) => {
        const res = await apiGet<ArloO3PollResponse>('bg_poll_arlo_o3_voice_status', { job_id: jobId });
        if (cancelled) return;
        if (res.ok && res.data) {
          if (res.data.intent) {
            bgO3IntentByBeat.value = { ...bgO3IntentByBeat.value, [beatId]: res.data.intent! };
          }
          if (res.data.status === 'done_with_warning') {
            completedBeatIds.push(beatId);
            const beatPatch = beatPatchFromO3PollTerminal(beatId, res.data);
            if (beatPatch) beatPatches.push(beatPatch);
            if (!o3PollResultHasVideo(res.data)) {
              pushToast({
                kind: 'error',
                message: `${beatId}: O3 job finished but no clip appeared in slots — check kling_o3_clips or retry Generate.`,
                source: 'bg-o3-empty',
              });
              return;
            }
            const warnMsg = res.data.warning?.message
              ?? res.data.terminal?.warning?.message
              ?? 'Delivery recovered with sidecar warning — verify clip in kling_o3_clips folder.';
            bgO3WarningByBeat.value = { ...bgO3WarningByBeat.value, [beatId]: warnMsg };
            pushToast({
              kind: 'success',
              message: `${beatId}: O3 voice video ready (recovered after Dropbox sync blip)`,
              source: 'bg-o3-warning',
            });
            return;
          }
          if (res.data.status === 'done') {
            completedBeatIds.push(beatId);
            const beatPatch = beatPatchFromO3PollTerminal(beatId, res.data);
            if (beatPatch) beatPatches.push(beatPatch);
            if (!o3PollResultHasVideo(res.data)) {
              pushToast({
                kind: 'error',
                message: `${beatId}: O3 job reported done but no clip appeared in slots — check kling_o3_clips or retry Generate.`,
                source: 'bg-o3-empty',
              });
              return;
            }
            pushToast({
              kind: 'success',
              message: `${beatId}: O3 voice video ready${res.data.result?.duration_s ? ` (${res.data.result.duration_s.toFixed(2)}s)` : ''}`,
              source: 'bg-o3-done',
            });
            return;
          }
          if (res.data.status === 'failed') {
            failedBeatIds.push(beatId);
            const beatPatch = beatPatchFromO3PollTerminal(beatId, res.data);
            if (beatPatch) beatPatches.push(beatPatch);
            pushToast({
              kind: 'error',
              message: `${beatId}: O3 voice job failed: ${formatO3JobFailure(res.data.error)}`,
              source: 'bg-o3-error',
            });
            return;
          }
          if (res.data.status === 'running' && res.data.beat) {
            beatPatches.push(res.data.beat as import('../types/bgBeat').BgBeat);
          }
          anyStillRunning = true;
          return;
        }
        if (isNetworkPollBlip(res) || isSidecarLockPollBlip(res)) {
          anyStillRunning = true;
          return;
        }
        if (isStaleO3JobPoll(res)) {
          staleBeatIds.push(beatId);
          pushToast({
            kind: 'info',
            message: res.error ?? 'O3 job lost after server restart — reloading beat from disk.',
            source: 'bg-o3-poll-stale',
          });
          return;
        }
        failedBeatIds.push(beatId);
        pushToast({ kind: 'error', message: `O3 poll error: ${res.error}`, source: 'bg-o3-poll-error' });
      }));
      if (cancelled) return;

      if (beatPatches.length > 0) {
        updateBgBeats((bs) => beatPatches.reduce((acc, patch) => mergeBeatFromO3Poll(acc, patch), bs));
      }

      if (completedBeatIds.length > 0 || failedBeatIds.length > 0 || staleBeatIds.length > 0) {
        bgActiveO3Jobs.value = (() => {
          const next = { ...bgActiveO3Jobs.value };
          for (const beatId of [...completedBeatIds, ...failedBeatIds, ...staleBeatIds]) {
            delete next[beatId];
            delete submitPollLatchRef.current[beatId];
          }
          return next;
        })();
        bgO3IntentByBeat.value = (() => {
          const next = { ...bgO3IntentByBeat.value };
          for (const beatId of [...completedBeatIds, ...failedBeatIds, ...staleBeatIds]) {
            delete next[beatId];
          }
          return next;
        })();
        bgO3SubmitAuditByBeat.value = (() => {
          const next = { ...bgO3SubmitAuditByBeat.value };
          for (const beatId of [...completedBeatIds, ...failedBeatIds, ...staleBeatIds]) {
            delete next[beatId];
          }
          return next;
        })();
        if (beatPatches.length === 0 || completedBeatIds.length > 0) {
          scheduleRefreshBgSession();
        }
      }
      if (!anyStillRunning) return;
      timer = window.setTimeout(poll, O3_POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [JSON.stringify(bgActiveO3Jobs.value)]);

  // Native lipsync experiment poll
  useEffect(() => {
    const entries = Object.entries(bgActiveNativeLipSyncJobs.value);
    if (entries.length === 0) return;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      const jobs = Object.entries(bgActiveNativeLipSyncJobs.value);
      let anyStillRunning = false;
      const completedBeatIds: string[] = [];

      await Promise.all(jobs.map(async ([beatId, jobId]) => {
        const res = await apiGet<NativeLipSyncPollResponse>(
          'bg_poll_kling_native_lipsync_experiment_status',
          { job_id: jobId },
        );
        if (cancelled) return;
        if (res.ok && res.data) {
          if (res.data.status === 'running') {
            anyStillRunning = true;
            return;
          }
          completedBeatIds.push(beatId);
          const profile = res.data.result?.raw_profile;
          const dims = profile?.width && profile?.height ? `${profile.width}x${profile.height}` : 'no raw dimensions';
          const passed = res.data.result?.passed_gate === true;
          pushToast({
            kind: passed ? 'success' : 'error',
            message: passed
              ? `Native Kling LipSync proof passed raw gate (${dims}). No approval was changed.`
              : `Native Kling LipSync proof failed or blocked (${dims}). No approval was changed.`,
            source: passed ? 'bg-native-lipsync-done' : 'bg-native-lipsync-failed',
          });
          return;
        }
        completedBeatIds.push(beatId);
        pushToast({ kind: 'error', message: `Native lipsync poll error: ${res.error}`, source: 'bg-native-lipsync-poll-error' });
      }));
      if (cancelled) return;

      if (completedBeatIds.length > 0) {
        bgActiveNativeLipSyncJobs.value = (() => {
          const next = { ...bgActiveNativeLipSyncJobs.value };
          for (const beatId of completedBeatIds) delete next[beatId];
          return next;
        })();
        scheduleRefreshBgSession();
      }
      if (!anyStillRunning) return;
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [JSON.stringify(bgActiveNativeLipSyncJobs.value)]);

  return null;
}

/** BG_BEAT_JUMP_NAV_V1 — read-only nav badges (active job dot + approved check). */

import { beatO3JobBusy, type O3JobBeatFields } from '../o3JobStatusContract';

export type BeatNavJobContext = {
  activeJobId: string | null;
  activeO3Jobs: Readonly<Record<string, string>>;
  o3SubmitPending: Readonly<Record<string, boolean>>;
  activeStillRenderJobs: Readonly<Record<string, boolean>>;
  activeNativeLipSyncJobs: Readonly<Record<string, string>>;
  gptBatchSubmitPending?: Readonly<Record<string, boolean>>;
};

export type BeatNavStatusFields = BeatNavStatusFieldsBase & O3JobBeatFields;

type BeatNavStatusFieldsBase = {
  beat_id: string;
  status?: string | null;
  bg_gpt_batch_job_id?: string | null;
  kling_o3_status?: string | null;
  pipeline?: string | null;
  beat_render_mode?: string | null;
};

/** Still+TTS beats use render-still-clip — not O3 voice job lifecycle. */
export function isStillInsertNavBeat(beat: BeatNavStatusFields): boolean {
  return beat.pipeline === 'still_insert' || beat.beat_render_mode === 'still_insert';
}

/** Drop client still-render latches when server reports idle. */
export function pruneActiveStillRenderJobs(
  beats: ReadonlyArray<BeatNavStatusFields>,
  jobs: Readonly<Record<string, boolean>>,
): Record<string, boolean> {
  const next = { ...jobs };
  for (const beat of beats) {
    const beatId = (beat.beat_id ?? '').trim();
    if (!beatId) continue;
    if (beat.job_busy !== true) delete next[beatId];
  }
  return next;
}

/** Server-owned GPT batch job — ``stills_pending`` + matching ``bg_gpt_batch_job_id``. */
export function collectActiveGptBatchJobFromBeats(
  beats: ReadonlyArray<BeatNavStatusFields>,
): string | null {
  for (const beat of beats) {
    const jobId = (beat.bg_gpt_batch_job_id ?? '').trim();
    if (jobId && beat.status === 'stills_pending') {
      return jobId;
    }
  }
  return null;
}

export type O3ClientJobRecords = {
  o3IntentByBeat: Record<string, unknown>;
  o3SubmitAuditByBeat: Record<string, unknown>;
  activeO3Jobs: Record<string, string>;
  o3SubmitPending: Record<string, boolean>;
  submitPollLatch: Record<string, string>;
};

function purgeRecordKeys<T>(rec: Record<string, T>, beatIds: ReadonlySet<string>): Record<string, T> {
  const next = { ...rec };
  for (const id of beatIds) delete next[id];
  return next;
}

/** Drop O3 voice job client latches for beats that must never show O3 busy chrome. */
export function purgeO3ClientJobStateForBeatIds<T extends O3ClientJobRecords>(
  beatIds: ReadonlyArray<string>,
  records: T,
): T {
  const ids = new Set(beatIds.map((id) => id.trim()).filter(Boolean));
  return {
    ...records,
    o3IntentByBeat: purgeRecordKeys(records.o3IntentByBeat, ids),
    o3SubmitAuditByBeat: purgeRecordKeys(records.o3SubmitAuditByBeat, ids),
    activeO3Jobs: purgeRecordKeys(records.activeO3Jobs, ids),
    o3SubmitPending: purgeRecordKeys(records.o3SubmitPending, ids),
    submitPollLatch: purgeRecordKeys(records.submitPollLatch, ids),
  };
}

export function stillInsertBeatIdsFromBeats(
  beats: ReadonlyArray<BeatNavStatusFields>,
): string[] {
  return beats
    .filter(isStillInsertNavBeat)
    .map((b) => (b.beat_id ?? '').trim())
    .filter(Boolean);
}

export function purgeO3ClientJobStateForStillInsertBeats(
  beats: ReadonlyArray<BeatNavStatusFields>,
  records: O3ClientJobRecords,
): O3ClientJobRecords {
  return purgeO3ClientJobStateForBeatIds(stillInsertBeatIdsFromBeats(beats), records);
}

export function pruneGptBatchSubmitPending(
  beats: ReadonlyArray<BeatNavStatusFields>,
  pending: Readonly<Record<string, boolean>>,
  activeGptJobId: string | null,
): Record<string, boolean> {
  const next = { ...pending };
  for (const beatId of Object.keys(next)) {
    const beat = beats.find((b) => (b.beat_id ?? '').trim() === beatId);
    const batchJobId = (beat?.bg_gpt_batch_job_id ?? '').trim();
    const stillPending = beat?.status === 'stills_pending'
      && !!batchJobId
      && (!activeGptJobId || batchJobId === activeGptJobId);
    if (!stillPending && !activeGptJobId) {
      delete next[beatId];
    }
  }
  return next;
}

export function beatHasActiveStillBatchJob(
  beat: BeatNavStatusFields,
  activeJobId: string | null,
): boolean {
  if (!activeJobId) return false;
  const jobId = (beat.bg_gpt_batch_job_id ?? '').trim();
  return beat.status === 'stills_pending' && jobId === activeJobId;
}

export function beatIsStitchApproved(beat: BeatNavStatusFields): boolean {
  return (beat.kling_o3_status ?? '').toLowerCase() === 'approved';
}

/** Mirrors BeatGenCard busy — pipeline-specific job truth (no O3 latch bleed on still_insert). */
export function beatHasActiveNavJob(
  beat: BeatNavStatusFields,
  ctx: BeatNavJobContext,
): boolean {
  const id = beat.beat_id;
  if (isStillInsertNavBeat(beat)) {
    return beat.job_busy === true || !!ctx.activeStillRenderJobs[id];
  }
  return (
    beatO3JobBusy(beat, !!ctx.o3SubmitPending[id])
    || !!ctx.activeO3Jobs[id]
    || !!ctx.gptBatchSubmitPending?.[id]
    || !!ctx.activeNativeLipSyncJobs[id]
    || beatHasActiveStillBatchJob(beat, ctx.activeJobId)
  );
}

export function beatOperatorMutationsLocked(beat: BeatNavStatusFields): boolean {
  return beat.job_busy === true;
}

type BeatElementCharRefFields = {
  element_char_ref_ok?: boolean;
  element_char_ref_error?: string;
  _derived?: BeatElementCharRefFields;
};

/** Session GET `_derived` gate wins over stale disk when operator workbench enrich ran. */
export function beatElementCharRefOk(beat: BeatElementCharRefFields): boolean | undefined {
  const derived = beat._derived?.element_char_ref_ok;
  if (typeof derived === 'boolean') return derived;
  return beat.element_char_ref_ok;
}

export function beatElementCharRefError(beat: BeatElementCharRefFields): string | undefined {
  return beat._derived?.element_char_ref_error ?? beat.element_char_ref_error;
}

export function beatNavActiveJobHint(
  beat: BeatNavStatusFields,
  ctx: BeatNavJobContext,
): string | null {
  const id = beat.beat_id;
  if (isStillInsertNavBeat(beat)) {
    if (ctx.activeStillRenderJobs[id] || beat.job_busy === true) return 'Still clip rendering';
    return null;
  }
  if (ctx.o3SubmitPending[id]) return 'Submitting generation…';
  if (ctx.gptBatchSubmitPending?.[id]) return 'Submitting GPT still batch…';
  if (beatO3JobBusy(beat, false)) return 'O3 / voice job running';
  const err = (beat.kling_o3_voice_fix_error ?? '').trim();
  if (err && beat.job_busy !== true) return `Last attempt failed: ${err.slice(0, 80)}`;
  if (ctx.activeStillRenderJobs[id]) return 'Still render running';
  if (ctx.activeNativeLipSyncJobs[id]) return 'Native lip-sync experiment running';
  if (beatHasActiveStillBatchJob(beat, ctx.activeJobId)) return 'GPT still options generating';
  return null;
}

export type BeatNavItemStatus = {
  hasActiveJob: boolean;
  isApproved: boolean;
  activeJobHint: string | null;
};

export function computeBeatNavItemStatuses(
  beats: ReadonlyArray<BeatNavStatusFields>,
  ctx: BeatNavJobContext,
): BeatNavItemStatus[] {
  return beats.map((beat) => ({
    hasActiveJob: beatHasActiveNavJob(beat, ctx),
    isApproved: beatIsStitchApproved(beat),
    activeJobHint: beatNavActiveJobHint(beat, ctx),
  }));
}

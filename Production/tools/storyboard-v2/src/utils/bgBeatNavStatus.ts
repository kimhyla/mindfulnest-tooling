/** BG_BEAT_JUMP_NAV_V1 — read-only nav badges (active job dot + approved check). */

export type BeatNavJobContext = {
  activeJobId: string | null;
  activeO3Jobs: Readonly<Record<string, string>>;
  o3SubmitPending: Readonly<Record<string, boolean>>;
  activeStillRenderJobs: Readonly<Record<string, boolean>>;
  activeNativeLipSyncJobs: Readonly<Record<string, string>>;
};

export type BeatNavStatusFields = {
  beat_id: string;
  status?: string | null;
  bg_gpt_batch_job_id?: string | null;
  kling_o3_status?: string | null;
};

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

/** Mirrors BeatGenCard busy — per-beat, not global still-job bleed. */
export function beatHasActiveNavJob(
  beat: BeatNavStatusFields,
  ctx: BeatNavJobContext,
): boolean {
  const id = beat.beat_id;
  return (
    !!ctx.activeO3Jobs[id]
    || !!ctx.o3SubmitPending[id]
    || !!ctx.activeStillRenderJobs[id]
    || !!ctx.activeNativeLipSyncJobs[id]
    || beatHasActiveStillBatchJob(beat, ctx.activeJobId)
  );
}

export function beatNavActiveJobHint(
  beat: BeatNavStatusFields,
  ctx: BeatNavJobContext,
): string | null {
  const id = beat.beat_id;
  if (ctx.o3SubmitPending[id]) return 'Submitting generation…';
  if (ctx.activeO3Jobs[id]) return 'O3 / Kling job running';
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

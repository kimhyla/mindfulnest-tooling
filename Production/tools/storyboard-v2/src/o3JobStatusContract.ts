export const O3_VOICE_FIX_RUNNING_STATUSES = new Set([
  'o3_running', 'job_running', 'job_starting', 'visual_running',
  'lipsync_running', 'tts_ready', 'o3_element_running',
]);
export const O3_BEAT_STATUS_PREFIXES = ['o3_voice_job_', 'o3_element_'] as const;
export const O3_VOICE_FIX_RUNNING_PHASES = new Set(['subprocess', 'o3_element', 'queued']);
export const O3_INTENT_TERMINAL_STATUSES = new Set(['done', 'failed', 'done_with_warning', 'cancelled']);
export type O3JobBeatFields = {
  status?: string | null; kling_o3_voice_fix_status?: string | null; kling_o3_status?: string | null;
  kling_o3_voice_fix_phase?: string | null; kling_o3_voice_fix_ui_job_id?: string | null;
  kling_o3_voice_fix_job_log_path?: string | null; kling_o3_voice_fix_error?: string | null;
  job_busy?: boolean | null;
  o3_current_job_id?: string | null;
  kling_o3_options?: Array<{ video_path?: string | null; source?: string | null } | null> | null;
};

function isUserSelectableO3Video(path?: string | null, source?: string | null): boolean {
  if (source === 'still_insert_static_hold' || source === 'still_insert_ken_burns' || source === 'still_insert_kling_idle') {
    return Boolean(path);
  }
  const name = (path ?? '').toLowerCase().split('/').pop() ?? '';
  return Boolean(path)
    && !name.includes('_silent_o3_base')
    && !name.includes('_delivery_input')
    && !name.includes('_noaudio');
}

/** Gallery tiles require a selectable option row — video_path alone is not enough. */
export function beatHasPopulatedO3Slot(
  beat: { kling_o3_options?: O3JobBeatFields['kling_o3_options'] } | null | undefined,
): boolean {
  if (!beat) return false;
  return (beat.kling_o3_options ?? []).some((o) => isUserSelectableO3Video(o?.video_path, o?.source));
}

/** Brief latch after Generate click until session GET returns ``job_busy``. */
export const O3_SUBMIT_PENDING_TTL_MS = 30_000;

/** Server-owned busy — ``job_busy`` from session GET; submit latch only until server catches up. */
export function beatO3JobBusy(
  beat: O3JobBeatFields & { beat_id?: string },
  submitPending: boolean,
): boolean {
  // Client submit latch wins over stale session ``job_busy:false`` between click and first GET.
  if (submitPending) return true;
  if (typeof beat.job_busy === 'boolean') return beat.job_busy;
  return false;
}

/** Server/poll truth only — for duplicate guards; never treat this beat's submit click as external busy. */
export function beatO3ServerJobInFlight(
  beatId: string,
  beat: O3JobBeatFields & { beat_id?: string },
  ctx: {
    activeO3Jobs: Readonly<Record<string, string>>;
    submitPollLatch: Readonly<Record<string, string>>;
  },
): boolean {
  const id = beatId.trim();
  if (!id) return false;
  return (
    beatO3JobBusy(beat, false)
    || !!ctx.activeO3Jobs[id]
    || !!ctx.submitPollLatch[id]
  );
}

/** True when an approved clip is idle — safe to drop submit latch / poll map. */
export function o3BeatTerminallyIdleForSubmitLatch(
  beat: O3JobBeatFields & { kling_o3_video_path?: string | null; kling_o3_status?: string | null },
): boolean {
  return (
    beat.kling_o3_status === 'approved'
    && beatHasPopulatedO3Slot(beat)
    && !beatO3JobLooksRunning(beat)
  );
}

/** Legacy sidecar-cache heuristic — error banners / nav hints only, not Generate authority. */
export function beatO3JobLooksRunning(beat: O3JobBeatFields): boolean {
  const status = (beat.status ?? '').toLowerCase();
  const voiceFix = (beat.kling_o3_voice_fix_status ?? '').toLowerCase();
  const klingStatus = (beat.kling_o3_status ?? '').toLowerCase();
  const phase = (beat.kling_o3_voice_fix_phase ?? '').toLowerCase();
  if (voiceFix === 'approved' && klingStatus === 'approved') return false;
  if (O3_BEAT_STATUS_PREFIXES.some((p) => status.startsWith(p))) return true;
  if (O3_VOICE_FIX_RUNNING_STATUSES.has(voiceFix)) return true;
  const jobId = (beat.kling_o3_voice_fix_ui_job_id ?? '').trim();
  if (!jobId || voiceFix.startsWith('failed')) return false;
  if (phase && O3_VOICE_FIX_RUNNING_PHASES.has(phase)) return true;
  if (voiceFix !== 'approved' && klingStatus !== 'approved') return true;
  return O3_VOICE_FIX_RUNNING_STATUSES.has(voiceFix);
}

export function o3UiJobIdFromBeat(beat: O3JobBeatFields): string {
  const fromCurrent = (beat.o3_current_job_id ?? '').trim();
  if (fromCurrent) return fromCurrent;
  const fromUi = (beat.kling_o3_voice_fix_ui_job_id ?? '').trim();
  if (fromUi) return fromUi;
  return '';
}

/** Poll loop targets — server ``job_busy`` + job id only. */
export function collectActiveO3JobsFromBeats(
  beats: Array<O3JobBeatFields & { beat_id?: string }>,
): Record<string, string> {
  const jobs: Record<string, string> = {};
  for (const beat of beats) {
    const beatId = (beat.beat_id ?? '').trim();
    if (!beatId || beat.job_busy !== true) continue;
    const jobId = o3UiJobIdFromBeat(beat);
    if (jobId) jobs[beatId] = jobId;
  }
  return jobs;
}

/** Until GET catches up after submit, poll the job id returned by submit API. */
export function activeO3PollJobsFromBeats(
  beats: Array<O3JobBeatFields & { beat_id?: string; kling_o3_video_path?: string | null; kling_o3_status?: string | null }>,
  submitPollLatch: Readonly<Record<string, string>>,
): Record<string, string> {
  const merged = collectActiveO3JobsFromBeats(beats);
  for (const [beatId, jobId] of Object.entries(submitPollLatch)) {
    if (merged[beatId] || !jobId) continue;
    const beat = beats.find((b) => (b.beat_id ?? '').trim() === beatId);
    if (beat && o3BeatTerminallyIdleForSubmitLatch(beat)) continue;
    merged[beatId] = jobId;
  }
  return merged;
}

export function pruneO3SubmitPending(
  beats: Array<O3JobBeatFields & { beat_id?: string }>,
  pending: Record<string, boolean>,
): Record<string, boolean> {
  const next = { ...pending };
  for (const beat of beats) {
    const beatId = (beat.beat_id ?? '').trim();
    if (!beatId) continue;
    if (typeof beat.job_busy === 'boolean' && !beat.job_busy) {
      delete next[beatId];
    }
  }
  return next;
}

export function pruneSubmitPollLatch(
  beats: Array<O3JobBeatFields & { beat_id?: string; kling_o3_video_path?: string | null; kling_o3_status?: string | null }>,
  latch: Record<string, string>,
): Record<string, string> {
  const next = { ...latch };
  for (const beat of beats) {
    const beatId = (beat.beat_id ?? '').trim();
    if (!beatId) continue;
    if (collectActiveO3JobsFromBeats([beat])[beatId]) {
      delete next[beatId];
    }
    if (o3BeatTerminallyIdleForSubmitLatch(beat)) {
      delete next[beatId];
    }
  }
  return next;
}

/** Generate authority — server job_busy, poll map, submit latch, or brief pending click.
 * BG_O3_SUBMIT_UI_REATTACH_V1 — latch must survive stale session job_busy:false. */
export function beatO3GenerateInFlight(
  beatId: string,
  beat: O3JobBeatFields & { beat_id?: string },
  ctx: {
    o3SubmitPending: Readonly<Record<string, boolean>>;
    activeO3Jobs: Readonly<Record<string, string>>;
    submitPollLatch: Readonly<Record<string, string>>;
  },
): boolean {
  const id = beatId.trim();
  if (!id) return false;
  if (beatO3ServerJobInFlight(id, beat, ctx)) return true;
  return beatO3JobBusy(beat, !!ctx.o3SubmitPending[id]);
}

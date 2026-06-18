export const O3_VOICE_FIX_RUNNING_STATUSES = new Set([
  'o3_running', 'job_running', 'job_starting', 'visual_running',
  'lipsync_running', 'tts_ready', 'o3_element_running',
]);
export const O3_BEAT_STATUS_PREFIXES = ['o3_voice_job_', 'o3_element_'] as const;
export const O3_VOICE_FIX_RUNNING_PHASES = new Set(['subprocess', 'o3_element', 'queued']);
export const O3_INTENT_TERMINAL_STATUSES = new Set(['done', 'failed', 'done_with_warning']);
export type O3JobBeatFields = {
  status?: string | null; kling_o3_voice_fix_status?: string | null; kling_o3_status?: string | null;
  kling_o3_voice_fix_phase?: string | null; kling_o3_voice_fix_ui_job_id?: string | null;
  kling_o3_voice_fix_job_log_path?: string | null;
};
export function o3UiJobIdFromBeat(beat: O3JobBeatFields): string {
  const fromUi = (beat.kling_o3_voice_fix_ui_job_id ?? '').trim();
  if (fromUi) return fromUi;
  const logPath = (beat.kling_o3_voice_fix_job_log_path ?? '').trim();
  const match = logPath.match(/\/([0-9a-f]{8})_[^/]+\.log$/i);
  return match?.[1] ?? '';
}
export function beatO3JobLooksRunning(beat: O3JobBeatFields): boolean {
  const status = (beat.status ?? '').toLowerCase();
  const voiceFix = (beat.kling_o3_voice_fix_status ?? '').toLowerCase();
  const klingStatus = (beat.kling_o3_status ?? '').toLowerCase();
  const phase = (beat.kling_o3_voice_fix_phase ?? '').toLowerCase();
  if (O3_BEAT_STATUS_PREFIXES.some((p) => status.startsWith(p))) return true;
  if (O3_VOICE_FIX_RUNNING_STATUSES.has(voiceFix)) return true;
  const jobId = o3UiJobIdFromBeat(beat);
  if (!jobId || voiceFix.startsWith('failed')) return false;
  if (phase && O3_VOICE_FIX_RUNNING_PHASES.has(phase)) return true;
  if (voiceFix !== 'approved' && klingStatus !== 'approved') return true;
  return O3_VOICE_FIX_RUNNING_STATUSES.has(voiceFix);
}
export function collectActiveO3JobsFromBeats(
  beats: Array<O3JobBeatFields & { beat_id?: string }>,
): Record<string, string> {
  const jobs: Record<string, string> = {};
  for (const beat of beats) {
    const beatId = (beat.beat_id ?? '').trim();
    const jobId = o3UiJobIdFromBeat(beat);
    if (!beatId || !jobId || !beatO3JobLooksRunning(beat)) continue;
    jobs[beatId] = jobId;
  }
  return jobs;
}

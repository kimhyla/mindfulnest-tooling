export const O3_VOICE_FIX_RUNNING_STATUSES = new Set([
  'o3_running', 'job_running', 'job_starting', 'visual_running',
  'lipsync_running', 'tts_ready', 'o3_element_running',
]);
export const O3_BEAT_STATUS_PREFIXES = ['o3_voice_job_', 'o3_element_'] as const;
export const O3_VOICE_FIX_RUNNING_PHASES = new Set(['subprocess', 'o3_element', 'queued']);
export type O3JobBeatFields = {
  status?: string | null; kling_o3_voice_fix_status?: string | null; kling_o3_status?: string | null;
  kling_o3_voice_fix_phase?: string | null; kling_o3_voice_fix_ui_job_id?: string | null;
};
export function beatO3JobLooksRunning(beat: O3JobBeatFields): boolean {
  const status = (beat.status ?? '').toLowerCase();
  const voiceFix = (beat.kling_o3_voice_fix_status ?? '').toLowerCase();
  const klingStatus = (beat.kling_o3_status ?? '').toLowerCase();
  const phase = (beat.kling_o3_voice_fix_phase ?? '').toLowerCase();
  if (O3_BEAT_STATUS_PREFIXES.some((p) => status.startsWith(p))) return true;
  if (O3_VOICE_FIX_RUNNING_STATUSES.has(voiceFix)) return true;
  const jobId = (beat.kling_o3_voice_fix_ui_job_id ?? '').trim();
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
    const jobId = (beat.kling_o3_voice_fix_ui_job_id ?? '').trim();
    if (!beatId || !jobId || !beatO3JobLooksRunning(beat)) continue;
    jobs[beatId] = jobId;
  }
  return jobs;
}

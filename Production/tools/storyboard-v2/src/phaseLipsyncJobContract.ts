/** Shared Phase A/B module lipsync job contract — mirrors phase_lipsync_job_contract.py */

export const PHASE_LIPSYNC_IN_FLIGHT_STATUSES = new Set([
  'running',
  'polling',
  'submitting',
  'submitted',
]);

export const PHASE_LIPSYNC_TERMINAL_SUCCESS = new Set([
  'done',
  'needs_manual_visual_review',
]);

export const PHASE_LIPSYNC_TERMINAL_CLEARED = new Set([
  'rejected',
  'idle',
]);

const TASK_BOUND = new Set(['polling', 'submitting', 'submitted']);

export function phaseLipsyncJobBusy(
  status: string | undefined | null,
  taskId?: string | null,
): boolean {
  const s = (status ?? '').trim().toLowerCase();
  if (!PHASE_LIPSYNC_IN_FLIGHT_STATUSES.has(s)) return false;
  if (TASK_BOUND.has(s)) return Boolean((taskId ?? '').trim());
  return s === 'running';
}

export function phaseLipsyncIsTerminal(status: string | undefined | null): boolean {
  const s = (status ?? '').trim().toLowerCase();
  if (!s) return true;
  if (PHASE_LIPSYNC_TERMINAL_SUCCESS.has(s)) return true;
  if (PHASE_LIPSYNC_TERMINAL_CLEARED.has(s)) return true;
  if (s === 'qa_failed') return true;
  return s.startsWith('error:');
}

export function phaseLipsyncProgressMessage(phase: 'a' | 'b'): string {
  if (phase === 'a') {
    return (
      '⏳ Kling Phase A lipsync (~8–20 min: still idle + LipSync). ' +
      'Safe to switch tabs — will auto-update when done.'
    );
  }
  return (
    '⏳ Kling lipsync in progress (~8–50 min depending on stem length). ' +
    'Safe to switch tabs — will auto-update when done.'
  );
}

export function phaseLipsyncTerminalBanner(
  status: string | undefined | null,
): string | null {
  const raw = (status ?? '').trim();
  if (!raw || phaseLipsyncJobBusy(raw)) return null;
  const low = raw.toLowerCase();
  if (PHASE_LIPSYNC_TERMINAL_CLEARED.has(low)) {
    return '✓ Lipsync cleared — waveform shows voice stem; trim or resend when ready.';
  }
  if (PHASE_LIPSYNC_TERMINAL_SUCCESS.has(low)) {
    return '✓ Lipsync complete — preview ready.';
  }
  if (low === 'qa_failed') return '✗ Lipsync QA failed — review frames or regenerate.';
  if (low.startsWith('error:')) {
    const detail = raw.split(':').slice(1).join(':').trim() || 'unknown error';
    return `✗ Lipsync failed: ${detail}`;
  }
  return null;
}

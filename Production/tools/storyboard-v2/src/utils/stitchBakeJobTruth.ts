/** STITCH_BAKE_JOB_TRUTH_V1 — client latch + poll helpers for async module bake. */

export const STITCH_BAKE_JOB_TRUTH_V1 = 'STITCH_BAKE_JOB_TRUTH_V1';
export const STITCH_BAKE_POLL_INTERVAL_MS = 2500;

export const TERMINAL_STITCH_BAKE_STATUSES = new Set(['done', 'failed', 'interrupted']);

export interface StitchBakePollResult {
  ok?: boolean;
  job_id?: string;
  status?: string;
  phase?: string;
  message?: string;
  error?: string;
  reattach?: boolean;
  submitted?: boolean;
  latest_terminal?: boolean;
  result?: {
    ok?: boolean;
    bake_path?: string;
    canonical_path?: string;
    asset_id?: number;
    error_code?: string;
    error_message?: string;
  };
  code?: string;
}

export interface StitchBakeJobSummary extends StitchBakePollResult {
  stitch_job_name?: string;
}

function latchKey(eventId: string, stitchJobName: string): string {
  return `mn:stitch-bake-latch:${eventId}:${stitchJobName}`;
}

export function readStitchBakeBusyLatch(eventId: string, stitchJobName: string): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    return sessionStorage.getItem(latchKey(eventId, stitchJobName));
  } catch {
    return null;
  }
}

export function writeStitchBakeBusyLatch(
  eventId: string,
  stitchJobName: string,
  jobId: string | null,
): void {
  if (typeof sessionStorage === 'undefined') return;
  const key = latchKey(eventId, stitchJobName);
  try {
    if (jobId) sessionStorage.setItem(key, jobId);
    else sessionStorage.removeItem(key);
  } catch {
    // ignore quota / private mode
  }
}

export function isStitchBakeStatusTerminal(status: string | undefined | null): boolean {
  return TERMINAL_STITCH_BAKE_STATUSES.has((status ?? '').toLowerCase());
}

export function isStitchBakeStatusActive(status: string | undefined | null): boolean {
  const s = (status ?? '').toLowerCase();
  return s === 'queued' || s === 'running';
}

/** True when we had a busy latch but reload could not confirm job truth. */
export function shouldToastStitchBakeRefreshFailure(
  hadBusyLatch: boolean,
  loadOk: boolean,
  bakeJobPresent: boolean,
): boolean {
  return hadBusyLatch && (!loadOk || !bakeJobPresent);
}

export function stitchBakeStatusMessage(payload: StitchBakePollResult | undefined): string {
  if (!payload) return 'Baking final MP4…';
  if (payload.message) return payload.message;
  const phase = payload.phase ?? payload.status ?? '';
  if (phase === 'encode') return 'Encoding final module MP4…';
  if (payload.status === 'queued') return 'Bake queued…';
  return 'Baking final MP4…';
}

export function stitchBakeSuccessPaths(payload: StitchBakePollResult | undefined): {
  canonical?: string | undefined;
  assetId?: number | undefined;
} {
  const result = payload?.result;
  if (!result) return {};
  return {
    canonical: result.canonical_path ?? result.bake_path,
    assetId: typeof result.asset_id === 'number' ? result.asset_id : undefined,
  };
}

/** Human-readable terminal bake failure for status line + empty preview hint. */
export function stitchBakeTerminalErrorLine(payload: StitchBakePollResult | undefined): string | null {
  if (!payload || !isStitchBakeStatusTerminal(payload.status)) return null;
  if (payload.status === 'done') return null;
  const err = payload.error ?? payload.message ?? payload.result?.error_message ?? 'Bake failed';
  if (payload.status === 'interrupted') return `Bake interrupted: ${err}`;
  return `Bake failed: ${err}`;
}

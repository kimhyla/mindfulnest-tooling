/** BG_EXPORT_TO_STITCHER_ASYNC_V1 — client latch + poll helpers for async export. */

export const BG_EXPORT_TO_STITCHER_ASYNC_V1 = 'BG_EXPORT_TO_STITCHER_ASYNC_V1';
export const BG_EXPORT_POLL_INTERVAL_MS = 2500;

export const TERMINAL_BG_EXPORT_STATUSES = new Set(['done', 'failed', 'interrupted']);

export interface BgExportPollResult {
  ok?: boolean;
  job_id?: string;
  status?: string;
  phase?: string;
  message?: string;
  error?: string;
  error_code?: string;
  reattach?: boolean;
  submitted?: boolean;
  beat_index?: number;
  beat_total?: number;
  slot_key?: string;
  scope_key?: string;
  code?: string;
  result?: {
    ok?: boolean;
    job_name?: string;
    slot_key?: string;
    video_path?: string;
    duration_s?: number;
    video_dur_ms?: number;
    warnings?: string[];
    beat_count?: number;
    error_code?: string;
    error_message?: string;
  };
}

function latchKey(scopeEventId: string, scopeKey: string): string {
  return `mn:bg-export-stitch-latch:${scopeEventId}:${scopeKey}`;
}

export function bgExportScopeKey(
  arcNumber: number,
  bgEventId: string,
  phase: string,
  slotKey: string,
): string {
  return `${arcNumber}|${bgEventId}|${phase}|${slotKey}`;
}

export function readBgExportBusyLatch(scopeEventId: string, scopeKey: string): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    return sessionStorage.getItem(latchKey(scopeEventId, scopeKey));
  } catch {
    return null;
  }
}

export function writeBgExportBusyLatch(
  scopeEventId: string,
  scopeKey: string,
  jobId: string | null,
): void {
  if (typeof sessionStorage === 'undefined') return;
  const key = latchKey(scopeEventId, scopeKey);
  try {
    if (jobId) sessionStorage.setItem(key, jobId);
    else sessionStorage.removeItem(key);
  } catch {
    // ignore quota / private mode
  }
}

export function isBgExportStatusTerminal(status: string | undefined | null): boolean {
  return TERMINAL_BG_EXPORT_STATUSES.has((status ?? '').toLowerCase());
}

export function isBgExportStatusActive(status: string | undefined | null): boolean {
  const s = (status ?? '').toLowerCase();
  return s === 'queued' || s === 'running';
}

export function bgExportStatusMessage(payload: BgExportPollResult | undefined): string {
  if (!payload) return 'Sending to Stitcher…';
  if (payload.message) return payload.message;
  const total = payload.beat_total ?? 0;
  const idx = payload.beat_index ?? 0;
  if (total > 0 && idx > 0) {
    return `Sending to Stitcher… (${idx}/${total})`;
  }
  if (payload.phase === 'concat') return 'Concatenating beats…';
  if (payload.phase === 'upsert') return 'Updating Stitcher slot…';
  if (payload.status === 'queued') return 'Export queued…';
  return 'Sending to Stitcher…';
}

export function bgExportTerminalSuccess(payload: BgExportPollResult | undefined): {
  slotKey?: string;
  warnings?: string[];
} {
  const result = payload?.result;
  if (!result) {
    const slotKey = payload?.slot_key;
    return slotKey ? { slotKey } : {};
  }
  const slotKey = result.slot_key ?? payload?.slot_key;
  const out: { slotKey?: string; warnings?: string[] } = {};
  if (slotKey) out.slotKey = slotKey;
  if (result.warnings?.length) out.warnings = result.warnings;
  return out;
}

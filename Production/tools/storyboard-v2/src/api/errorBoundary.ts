// V59 Phase 7 — global error boundary for canonical error shape.
// SCOPE_ERROR_DEDUPE_V1 — one banner surface; suppress duplicate scope events.

export interface V59Error {
  error_code: string;
  error_message: string;
  retry_safe: boolean;
  hint: string | null;
  [extra: string]: unknown;
}

const MN_SCOPE_MISMATCH = 'mn:scope-mismatch';
const MN_V59_ERROR = 'mn:v59-error';

/** Suppress identical scope-mismatch dispatches within this window (toast/banner storm). */
export const SCOPE_MISMATCH_DEDUPE_MS = 5000;

let lastScopeMismatchAt = 0;
let lastScopeMismatchKey = '';

function scopeMismatchDedupeKey(err: V59Error): string {
  return `${err.error_code}:${err.error_message}:${err.hint ?? ''}`;
}

export function resetScopeMismatchDedupe(): void {
  lastScopeMismatchAt = 0;
  lastScopeMismatchKey = '';
}

/** True when an identical scope mismatch was surfaced recently (for toast suppression). */
export function isScopeMismatchRecentlySurfaced(err: Pick<V59Error, 'error_code' | 'error_message' | 'hint'>): boolean {
  if (err.error_code !== 'SCOPE_MISMATCH') return false;
  const key = scopeMismatchDedupeKey(err as V59Error);
  return lastScopeMismatchKey === key
    && Date.now() - lastScopeMismatchAt < SCOPE_MISMATCH_DEDUPE_MS;
}

export function dispatchV59Error(err: V59Error) {
  if (err.error_code === 'SCOPE_MISMATCH') {
    const key = scopeMismatchDedupeKey(err);
    const now = Date.now();
    if (now - lastScopeMismatchAt < SCOPE_MISMATCH_DEDUPE_MS && key === lastScopeMismatchKey) {
      return;
    }
    lastScopeMismatchAt = now;
    lastScopeMismatchKey = key;
    window.dispatchEvent(new CustomEvent(MN_SCOPE_MISMATCH, { detail: err }));
    return;
  }
  window.dispatchEvent(new CustomEvent(MN_V59_ERROR, { detail: err }));
}

export function onV59Error(listener: (err: V59Error) => void): () => void {
  const handler = (e: Event) => listener((e as CustomEvent).detail as V59Error);
  window.addEventListener(MN_V59_ERROR, handler);
  return () => window.removeEventListener(MN_V59_ERROR, handler);
}

export function onScopeMismatch(listener: (err: V59Error) => void): () => void {
  const handler = (e: Event) => listener((e as CustomEvent).detail as V59Error);
  window.addEventListener(MN_SCOPE_MISMATCH, handler);
  return () => window.removeEventListener(MN_SCOPE_MISMATCH, handler);
}

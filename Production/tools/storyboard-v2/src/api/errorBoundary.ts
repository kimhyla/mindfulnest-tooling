// V59 Phase 7 — global error boundary for canonical error shape.
// Subscribers receive {error_code, error_message, retry_safe, hint, ...extra}.
// Used by pathappPatch and any direct apiGet/fetch wrappers.

export interface V59Error {
  error_code: string;
  error_message: string;
  retry_safe: boolean;
  hint: string | null;
  [extra: string]: unknown;
}

const MN_SCOPE_MISMATCH = 'mn:scope-mismatch';
const MN_V59_ERROR = 'mn:v59-error';

export function dispatchV59Error(err: V59Error) {
  // Scope-mismatch gets its own channel for ScopeBanner.
  if (err.error_code === 'SCOPE_MISMATCH') {
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

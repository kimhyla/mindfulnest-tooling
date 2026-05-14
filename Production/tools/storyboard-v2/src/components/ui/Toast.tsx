// Toast primitive — stackable transient notifications.
// Per LD UI_PRIMITIVES_SHARED_V1 (S5.5c).
//
// API:
//   import { pushToast, ToastHost } from './ui/Toast';
//   pushToast({ kind: 'info' | 'success' | 'warning' | 'error', message: string, ttlMs?: number });
//   <ToastHost /> mounts the host (already done in app.tsx).
//
// Cap: max 5 visible at once; oldest auto-dismisses early on overflow.
// Default ttl: 5000ms (info/success), 6500ms (warning), 8000ms (error).
// Click any toast to dismiss.
//
// 'warning' added 2026-05-14 per LD TTS_OVER_CAP_WARNING_AT_REGEN_V1 — surfaces
// recoverable pre-flight issues (e.g. audio > Kling 10s cap at TTS regen time)
// without erroring out a successful mutation.

import { signal } from '@preact/signals';

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface ToastEntry {
  id: number;
  kind: ToastKind;
  message: string;
  /** Optional source for debugging — never displayed. */
  source?: string;
  /** Time-to-live in ms; default depends on kind. */
  ttlMs?: number;
}

const _toasts = signal<ToastEntry[]>([]);
let _nextId = 1;
const MAX_VISIBLE = 5;

function defaultTtl(kind: ToastKind): number {
  if (kind === 'error') return 8000;
  if (kind === 'warning') return 6500;
  return 5000;
}

export function pushToast(entry: Omit<ToastEntry, 'id'>): number {
  const id = _nextId++;
  const ttl = entry.ttlMs ?? defaultTtl(entry.kind);
  // Cap MAX_VISIBLE — drop oldest when overflowing.
  const next = [..._toasts.value, { ...entry, id, ttlMs: ttl }];
  while (next.length > MAX_VISIBLE) next.shift();
  _toasts.value = next;
  // Schedule dismiss.
  setTimeout(() => dismissToast(id), ttl);
  return id;
}

export function dismissToast(id: number): void {
  _toasts.value = _toasts.value.filter((t) => t.id !== id);
}

export function clearToasts(): void {
  _toasts.value = [];
}

// Test-only access — used by Phase E gate to introspect queue state.
export function _toastsForTesting(): ReadonlyArray<ToastEntry> {
  return _toasts.value;
}

export function ToastHost() {
  const items = _toasts.value;
  if (items.length === 0) return null;
  return (
    <div class="mn-toast-host" data-testid="toast-host" aria-live="polite">
      {items.map((t) => (
        <div
          key={t.id}
          class={`mn-toast mn-toast-${t.kind}`}
          data-testid={`toast-${t.id}`}
          data-toast-kind={t.kind}
          role={t.kind === 'error' || t.kind === 'warning' ? 'alert' : 'status'}
          onClick={() => dismissToast(t.id)}
        >
          <span class="mn-toast-message">{t.message}</span>
          <button
            type="button"
            class="mn-toast-dismiss"
            data-testid={`toast-dismiss-${t.id}`}
            onClick={(e: MouseEvent) => {
              e.stopPropagation();
              dismissToast(t.id);
            }}
            aria-label="Dismiss notification"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  );
}

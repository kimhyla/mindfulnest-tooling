// SCOPE_RESTART_RECONCILE_V1 — gate mutations until boot or post-restart reconcile passes.

import { signal } from '@preact/signals';

export const scopeReady = signal(false);

export function setScopeReady(ready: boolean, source: string): void {
  scopeReady.value = ready;
  if (typeof document !== 'undefined') {
    document.body.setAttribute('data-scope-ready', ready ? 'true' : 'false');
    document.body.setAttribute('data-scope-ready-source', source);
  }
}

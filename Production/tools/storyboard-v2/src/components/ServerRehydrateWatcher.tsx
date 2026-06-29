// Watches production_server availability; rehydrates all tabs after restart/deploy.
// SCOPE_RESTART_RECONCILE_V1: down→up runs reconcileScopeAfterRestart before refresh tick.

import { useEffect, useRef } from 'preact/hooks';
import {
  probeProductionServer,
  syncScopeFromProbe,
  triggerServerRehydrate,
} from '../state/serverRehydrate';
import { waitForStableProductionServer } from '../state/serverRestartHydrate';
import { reconcileScopeAfterRestart } from '../state/scopeReconcile';
import { checkBuildShaDriftAndAutoReload } from '../state/buildShaDrift';
import { pushToast } from './ui/Toast';

const POLL_MS = 20_000;

export function ServerRehydrateWatcher() {
  const reachableRef = useRef<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async (reason: string) => {
      const probe = await probeProductionServer();
      if (cancelled) return;
      const wasReachable = reachableRef.current;
      reachableRef.current = probe.ok;

      if (probe.ok) {
        const drifted = await checkBuildShaDriftAndAutoReload(reason);
        if (cancelled || drifted) return;

        if (wasReachable === false) {
          const reconciled = await reconcileScopeAfterRestart(reason);
          if (cancelled) return;
          if (!reconciled) {
            pushToast({
              kind: 'error',
              message: 'Server is back but scope could not be verified — reload the page.',
              source: 'server-rehydrate-scope-fail',
            });
            return;
          }
          const stable = await waitForStableProductionServer();
          if (cancelled) return;
          if (!stable) {
            reachableRef.current = false;
            return;
          }
          triggerServerRehydrate(reason);
          pushToast({
            kind: 'success',
            message: 'Storyboard server is back — scope verified, refreshing tabs…',
            source: 'server-rehydrate',
          });
          return;
        }
        await syncScopeFromProbe(probe);
      }
    };

    void check('mount');

    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void check('visibility');
      }
    };
    const onFocus = () => { void check('focus'); };

    window.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);

    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void check('poll');
      }
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
      window.clearInterval(interval);
    };
  }, []);

  return null;
}

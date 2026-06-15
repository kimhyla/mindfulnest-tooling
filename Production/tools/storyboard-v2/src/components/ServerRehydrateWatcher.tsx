// Watches production_server availability; rehydrates all tabs after restart/deploy.

import { useEffect, useRef } from 'preact/hooks';
import {
  probeProductionServer,
  syncScopeFromProbe,
  triggerServerRehydrate,
} from '../state/serverRehydrate';
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
        await syncScopeFromProbe(probe);
        if (wasReachable === false) {
          triggerServerRehydrate(reason);
          pushToast({
            kind: 'success',
            message: 'Storyboard server is back — refreshing tabs…',
            source: 'server-rehydrate',
          });
        }
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

import { signal } from '@preact/signals';
import { TABS, ACTIVE_TAB_STORAGE_KEY, type TabKey } from '../components/TabBar';

function readStoredActiveTab(): TabKey {
  try {
    const raw = sessionStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
    if (raw && raw !== 'cropper' && TABS.some((t) => t.key === raw)) return raw as TabKey;
  } catch {
    // ignore
  }
  return 'storyboard';
}

/** Active storyboard tab — shared across TabBar and cross-tab navigators. */
export const activeTab = signal<TabKey>(readStoredActiveTab());

/** Bumped on scene_assemble / export — StitcherTab re-fetches jobs. */
export const stitcherRefreshTick = signal(0);

/** Bumped when production_server becomes reachable after restart/deploy. */
export const serverRehydrateTick = signal(0);

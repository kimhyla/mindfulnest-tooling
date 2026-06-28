import { signal } from '@preact/signals';
import { TABS, ACTIVE_TAB_STORAGE_KEY, type TabKey } from '../components/TabBar';

function readUrlActiveTab(): TabKey | null {
  if (typeof window === 'undefined') return null;
  try {
    const tab = new URLSearchParams(window.location.search).get('tab');
    if (tab === 'storyboard') return 'storyboard';
    if (tab && tab !== 'cropper' && TABS.some((t) => t.key === tab)) return tab as TabKey;
  } catch {
    // ignore
  }
  return null;
}

function readStoredActiveTab(): TabKey {
  const fromUrl = readUrlActiveTab();
  if (fromUrl) return fromUrl;
  try {
    const raw = sessionStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
    if (raw === 'storyboard') return 'storyboard';
    if (raw && raw !== 'cropper' && TABS.some((t) => t.key === raw)) return raw as TabKey;
  } catch {
    // ignore
  }
  return 'bg';
}

/** Active storyboard tab — shared across TabBar and cross-tab navigators. */
export const activeTab = signal<TabKey>(readStoredActiveTab());

/** Bumped on scene_assemble / export — StitcherTab re-fetches jobs. */
export const stitcherRefreshTick = signal(0);

/** Bumped when production_server becomes reachable after restart/deploy. */
export const serverRehydrateTick = signal(0);

// TabBar — top-of-app tab switcher. 4 tabs per Path C plan.
//
// Tabs: Storyboard | BG | Cropper | Stitcher
// Cropper is a "tab" but its UI presents as an inline modal overlay (per
// PATH_C_REWRITE_V1 architecture commitments — eliminates the double-crop
// detour that v58 had).

import type { Signal } from '@preact/signals';

export type TabKey = 'storyboard' | 'bg' | 'cropper' | 'stitcher';

export const TABS: Array<{ key: TabKey; label: string; testid: string }> = [
  { key: 'storyboard', label: 'Storyboard', testid: 'tab-storyboard' },
  { key: 'bg', label: 'Beat Generator', testid: 'tab-bg' },
  { key: 'cropper', label: 'Cropper', testid: 'tab-cropper' },
  { key: 'stitcher', label: 'Stitcher', testid: 'tab-stitcher' },
];

export interface TabBarProps {
  activeTab: Signal<TabKey>;
}

export function TabBar({ activeTab }: TabBarProps) {
  return (
    <nav class="mn-tab-bar" data-testid="tab-bar">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          class={`mn-tab ${activeTab.value === t.key ? 'is-active' : ''}`}
          data-testid={t.testid}
          data-tab-key={t.key}
          onClick={() => {
            activeTab.value = t.key;
          }}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}

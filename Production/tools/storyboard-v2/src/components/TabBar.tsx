// TabBar — top-of-app tab switcher. S5.5d (v3 architecture revision, 2026-05-03)
// per TAB_STRUCTURE_PRODUCTION_ORDER_V1.
//
// Tabs in production order:
//   Beat Generator | Cropper | Storyboard | Phase B | Phase A | Stitcher | Production Map
//
// Phase A + Phase B are top-level dedicated tabs (no longer siblings inside
// Storyboard) per PHASE_A_TOP_LEVEL_STATE_V1 + PHASE_B_TOP_LEVEL_STATE_V1.
// They are DISABLED when activeProjectType === 'milestone' (milestones are
// single-video standalone, no phases).
//
// Cropper is a "tab" but its UI presents as an inline modal overlay (per
// PATH_C_REWRITE_V1 architecture commitments — eliminates the double-crop
// detour that v58 had).

import type { Signal } from '@preact/signals';
import { activeProjectType } from '../state/scope';

export type TabKey =
  | 'storyboard' | 'bg' | 'cropper' | 'stitcher'
  | 'phase_a' | 'phase_b' | 'map';

export interface TabDef {
  key: TabKey;
  label: string;
  testid: string;
  /** When true, the tab is hidden/disabled in milestone scope. */
  eventOnly?: boolean;
}

// Production order per v3 spec §3.2.
export const TABS: ReadonlyArray<TabDef> = [
  { key: 'bg', label: 'Beat Generator', testid: 'tab-bg' },
  { key: 'cropper', label: 'Cropper', testid: 'tab-cropper' },
  { key: 'storyboard', label: 'Storyboard', testid: 'tab-storyboard' },
  { key: 'phase_b', label: 'Phase B', testid: 'tab-phase-b', eventOnly: true },
  { key: 'phase_a', label: 'Phase A', testid: 'tab-phase-a', eventOnly: true },
  { key: 'stitcher', label: 'Stitcher', testid: 'tab-stitcher' },
  { key: 'map', label: 'Production Map', testid: 'tab-map' },
];

export interface TabBarProps {
  activeTab: Signal<TabKey>;
}

export function TabBar({ activeTab }: TabBarProps) {
  const isMilestone = activeProjectType.value === 'milestone';
  return (
    <nav class="mn-tab-bar" data-testid="tab-bar">
      {TABS.map((t) => {
        const disabled = isMilestone && t.eventOnly === true;
        return (
          <button
            key={t.key}
            type="button"
            class={`mn-tab ${activeTab.value === t.key ? 'is-active' : ''} ${disabled ? 'is-disabled' : ''}`}
            data-testid={t.testid}
            data-tab-key={t.key}
            disabled={disabled}
            title={disabled ? 'Disabled in milestone scope (event-only tab)' : undefined}
            onClick={() => {
              if (!disabled) activeTab.value = t.key;
            }}
          >
            {t.label}
          </button>
        );
      })}
    </nav>
  );
}

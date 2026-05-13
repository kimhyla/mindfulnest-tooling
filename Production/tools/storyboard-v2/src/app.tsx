// App — root of the storyboard-v2 (Path C) frontend. Composes:
//   ScopeBoundary (LD SCOPE_VALIDATION_V1 client side)
//     -> TabBar + active tab pane + LibraryPanel side rail
//     -> CropperModal overlay (rendered on top when state.open=true)
//
// Session 1 ships read-only preview. ZERO mutation calls. The single mutation
// channel pathappPatch() exists in src/api/client.ts but has no callers.

import { signal } from '@preact/signals';
import { useEffect } from 'preact/hooks';
import { ScopeBoundary } from './components/ScopeBoundary';
import { ScopeBanner } from './components/ScopeBanner';
import { ToastHost } from './components/ui/Toast';
import { TabBar, TABS, ACTIVE_TAB_STORAGE_KEY, type TabKey } from './components/TabBar';
import { StoryboardTab } from './components/StoryboardTab';
import { BgTab } from './components/BgTab';
import { CropperModal } from './components/CropperModal';
import { cropperState } from './state/cropper';
import { StitcherTab } from './components/StitcherTab';
import { LibraryPanel } from './components/LibraryPanel';
import { ProductionMapTab, MAP_CELL_NAVIGATE_EVENT } from './components/ProductionMapTab';
// S5.5e: EventSelector → ProjectSelector (LD PROJECT_SELECTOR_V1).
// Adds milestone listing + grouped Events/Milestones with "+ New Milestone".
import { ProjectSelector } from './components/ProjectSelector';
import { VideoSelector } from './components/VideoSelector';
import { PhaseATab } from './components/tabs/PhaseATab';
import { PhaseBTab } from './components/tabs/PhaseBTab';
import { activeScope, scopeKey } from './state/scope';
import './app.css';

function readStoredActiveTab(): TabKey {
  try {
    const raw = sessionStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
    if (raw && raw !== 'cropper' && TABS.some((t) => t.key === raw)) return raw as TabKey;
  } catch {
    // ignore
  }
  return 'storyboard';
}

// Top-level signals — cross-tab UI state lives here, NOT in any component
// closure. This keeps state explicit and inspectable.
const activeTab = signal<TabKey>(readStoredActiveTab());
function ActivePane() {
  switch (activeTab.value) {
    case 'storyboard':
      return <StoryboardTab />;
    case 'bg':
      return <BgTab />;
    case 'cropper':
      // Cropper "tab" presents as a tab AND can open as a modal from
      // Storyboard/BG. When on the Cropper tab itself, ensure the modal is open.
      if (!cropperState.value.open) {
        cropperState.value = { ...cropperState.value, open: true };
      }
      return (
        <section class="mn-tab-pane mn-cropper-pane" data-testid="pane-cropper">
          <header class="mn-pane-header">
            <h2>Cropper</h2>
            <span class="mn-scope-chip">scope: {scopeKey(activeScope.value)}</span>
          </header>
          <p class="mn-dim">
            Cropper opens as a modal overlay. Close it to return to whichever tab
            opened it.
          </p>
        </section>
      );
    case 'stitcher':
      return <StitcherTab />;
    case 'phase_a':
      return <PhaseATab />;
    case 'phase_b':
      return <PhaseBTab />;
    case 'map':
      return <ProductionMapTab />;
    default:
      return <p class="mn-warn">Unknown tab</p>;
  }
}

export function App() {
  // S4 — Production Map cell click → switch to Storyboard tab.
  useEffect(() => {
    const onMapNavigate = () => {
      activeTab.value = 'storyboard';
    };
    window.addEventListener(MAP_CELL_NAVIGATE_EVENT, onMapNavigate);
    return () => window.removeEventListener(MAP_CELL_NAVIGATE_EVENT, onMapNavigate);
  }, []);
  return (
    <ScopeBoundary>
      <div class="mn-app" data-testid="app-root">
        <ScopeBanner />
        <ToastHost />
        <header class="mn-app-header">
          <h1>Storyboard v2</h1>
          <span class="mn-app-subhead" data-testid="app-subhead">
            Path C rewrite &middot; Session 4 v3.1 — full producer wiring + animate + stitcher complete
          </span>
          <ProjectSelector />
          <VideoSelector />
        </header>

        <TabBar activeTab={activeTab} />

        <main class="mn-app-main">
          <div class="mn-app-tab-content">
            <ActivePane />
          </div>
          <LibraryPanel />
        </main>

        <CropperModal
          state={cropperState}
          onClose={() => {
            // If the modal was opened by clicking the Cropper tab, flip back
            // to Storyboard so ActivePane's auto-open doesn't re-open it on
            // the next render.
            if (activeTab.value === 'cropper') {
              activeTab.value = 'storyboard';
            }
          }}
          onSaved={(_result) => {
            // Crop saved to library — notify LibraryPanel to refresh.
            window.dispatchEvent(new CustomEvent('mn:library-refresh'));
          }}
        />
      </div>
    </ScopeBoundary>
  );
}

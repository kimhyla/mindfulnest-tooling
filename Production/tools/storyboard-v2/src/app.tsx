// App — root of the storyboard-v2 (Path C) frontend. Composes:
//   ScopeBoundary (LD SCOPE_VALIDATION_V1 client side)
//     -> TabBar + active tab pane + LibraryPanel side rail
//     -> CropperModal overlay (rendered on top when state.open=true)
//
// Session 1 ships read-only preview. ZERO mutation calls. The single mutation
// channel pathappPatch() exists in src/api/client.ts but has no callers.

import { useEffect, useRef, useState } from 'preact/hooks';
import { effect } from '@preact/signals';
import { ScopeBoundary } from './components/ScopeBoundary';
import { ScopeBanner } from './components/ScopeBanner';
import { ToastHost } from './components/ui/Toast';
import { TabBar } from './components/TabBar';
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
import { activeScope, activeProjectType, scopeKey } from './state/scope';
import { activeTab } from './state/refreshSignals';
import { ServerRehydrateWatcher } from './components/ServerRehydrateWatcher';
import { StoryboardTab } from './components/StoryboardTab';
import { stopAllPhasePlayback } from './utils/waveformPlaybackBus';
import './app.css';

export { stitcherRefreshTick, serverRehydrateTick } from './state/refreshSignals';

/** Phase A/B producers stay mounted (hidden) so lipsync polling never dies on tab switch. */
function PhaseTabsKeepAlive({ visibleTab }: { visibleTab: string }) {
  if (activeProjectType.value !== 'event') {
    if (visibleTab === 'phase_a') return <PhaseATab />;
    if (visibleTab === 'phase_b') return <PhaseBTab />;
    return null;
  }
  return (
    <>
      <div
        class="mn-tab-pane-keepalive"
        hidden={visibleTab !== 'phase_a'}
        data-testid="pane-phase-a-keepalive"
      >
        <PhaseATab />
      </div>
      <div
        class="mn-tab-pane-keepalive"
        hidden={visibleTab !== 'phase_b'}
        data-testid="pane-phase-b-keepalive"
      >
        <PhaseBTab />
      </div>
    </>
  );
}

function ActivePane() {
  const tab = activeTab.value;
  const isEvent = activeProjectType.value === 'event';
  const phaseVisible =
    tab === 'phase_a' || tab === 'phase_b' ? tab : '';

  let main = null as preact.JSX.Element | null;
  switch (tab) {
    case 'storyboard':
      main = <StoryboardTab />;
      break;
    case 'bg':
      main = <BgTab />;
      break;
    case 'cropper':
      if (!cropperState.value.open) {
        cropperState.value = { ...cropperState.value, open: true };
      }
      main = (
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
      break;
    case 'stitcher':
      main = <StitcherTab />;
      break;
    case 'map':
      main = <ProductionMapTab />;
      break;
    case 'phase_a':
    case 'phase_b':
      main = null;
      break;
    default:
      main = <p class="mn-warn">Unknown tab</p>;
  }

  return (
    <>
      {isEvent ? <PhaseTabsKeepAlive visibleTab={phaseVisible} /> : null}
      {!isEvent && tab === 'phase_a' ? <PhaseATab /> : null}
      {!isEvent && tab === 'phase_b' ? <PhaseBTab /> : null}
      {main}
    </>
  );
}

export function App() {
  const [buildSha, setBuildSha] = useState('');

  useEffect(() => {
    setBuildSha(
      document.querySelector('meta[name="build-sha"]')?.getAttribute('content') ?? '?',
    );
  }, []);

  // Stop ghost audio on tab change only — never call effect() during render (leaks + stops play).
  const prevTabRef = useRef(activeTab.value);
  useEffect(() => {
    const dispose = effect(() => {
      const tab = activeTab.value;
      if (tab === prevTabRef.current) return;
      prevTabRef.current = tab;
      stopAllPhasePlayback();
    });
    return dispose;
  }, []);

  useEffect(() => {
    const onHidden = () => {
      if (document.hidden) stopAllPhasePlayback();
    };
    document.addEventListener('visibilitychange', onHidden);
    return () => document.removeEventListener('visibilitychange', onHidden);
  }, []);

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
        <ServerRehydrateWatcher />
        <ScopeBanner />
        <ToastHost />
        <header class="mn-app-header">
          <h1>Storyboard v2</h1>
          <span class="mn-app-subhead" data-testid="app-subhead">
            Path C rewrite &middot; Session 4 v3.1 — full producer wiring + animate + stitcher complete
            {buildSha ? (
              <>
                {' '}
                &middot; build{' '}
                <span data-testid="app-build-sha">{buildSha}</span>
              </>
            ) : null}
          </span>
          <button
            type="button"
            class="mn-btn mn-btn-stop-audio"
            data-testid="stop-all-audio-btn"
            title="Stop Phase A/B waveform and preview audio (fixes ghost playback)"
            onClick={() => stopAllPhasePlayback()}
          >
            Stop audio
          </button>
          <ProjectSelector />
          {/* CC-9: hide VideoSelector in milestone scope — milestones have no
              per-video-role partitioning; their content is the single
              'standalone' video. Reactive on activeProjectType signal. */}
          {activeProjectType.value === 'event' ? <VideoSelector /> : null}
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

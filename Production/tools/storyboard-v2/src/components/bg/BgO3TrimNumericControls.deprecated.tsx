/**
 * DEPRECATED — legacy numeric front/back trim controls for Beat Gen O3 clips.
 *
 * Restore instructions (zero guesswork):
 * Numeric trim is ON by default (below amber cut controls on the selected tile).
 * To hide: `localStorage.setItem('BG_O3_TRIM_HIDE_NUMERIC', '1')` then hard-refresh.
 * To force on in a custom build: `VITE_BG_O3_TRIM_SHOW_NUMERIC=1` in storyboard-v2/.env.local
 * 2. Wired in BgTab.tsx `BgOptionTile` via `showBgO3NumericTrimControls()`.
 * 3. Server still accepts legacy `trim_start` / `trim_back` on POST /api/bg/kling-o3-trim.
 */
import type { FunctionalComponent } from 'preact';

export interface BgO3TrimNumericControlsProps {
  beatIndex: number;
  optionIndex: number;
  trimStartDraft: string;
  trimBackDraft: string;
  savedTrimInvalid: boolean;
  onTrimStartInput: (value: string) => void;
  onTrimBackInput: (value: string) => void;
  onStartFromPlayhead: () => void;
  onEndFromPlayhead: () => void;
  onApplyTrim: () => void;
  onPreviewTrim: () => void;
  onClearTrim: () => void;
}

export const BgO3TrimNumericControls: FunctionalComponent<BgO3TrimNumericControlsProps> = ({
  beatIndex,
  optionIndex,
  trimStartDraft,
  trimBackDraft,
  savedTrimInvalid,
  onTrimStartInput,
  onTrimBackInput,
  onStartFromPlayhead,
  onEndFromPlayhead,
  onApplyTrim,
  onPreviewTrim,
  onClearTrim,
}) => (
  <div class="mn-bg-o3-trim-controls" data-testid={`bg-o3-trim-controls-${beatIndex}-${optionIndex}`}>
    {savedTrimInvalid ? (
      <span class="mn-dim" style={{ color: '#f88' }}>
        trim invalid for this clip — Clear Trim or Apply a shorter back trim
      </span>
    ) : null}
    <span class="mn-dim">trim front</span>
    <input
      type="number"
      min="0"
      step="0.1"
      class="mn-bg-o3-trim-input"
      data-testid={`bg-o3-trim-start-input-${beatIndex}-${optionIndex}`}
      value={trimStartDraft}
      onClick={(e) => e.stopPropagation()}
      onInput={(e) => onTrimStartInput((e.target as HTMLInputElement).value)}
      aria-label="Seconds to trim from the beginning"
    />
    <span class="mn-dim">s / back</span>
    <input
      type="number"
      min="0"
      step="0.1"
      class="mn-bg-o3-trim-input"
      data-testid={`bg-o3-trim-back-input-${beatIndex}-${optionIndex}`}
      value={trimBackDraft}
      onClick={(e) => e.stopPropagation()}
      onInput={(e) => onTrimBackInput((e.target as HTMLInputElement).value)}
      aria-label="Seconds to trim from the end"
    />
    <span class="mn-dim">s</span>
    <button
      type="button"
      class="mn-btn mn-btn-small"
      data-testid={`bg-o3-start-trim-${beatIndex}-${optionIndex}`}
      onClick={(e) => { e.stopPropagation(); onStartFromPlayhead(); }}
      title="Set front trim from playhead"
    >
      Start Trim
    </button>
    <button
      type="button"
      class="mn-btn mn-btn-small"
      data-testid={`bg-o3-end-trim-${beatIndex}-${optionIndex}`}
      onClick={(e) => { e.stopPropagation(); onEndFromPlayhead(); }}
      title="Set back trim from playhead"
    >
      End Trim
    </button>
    <button
      type="button"
      class="mn-btn mn-btn-small"
      data-testid={`bg-o3-apply-trim-${beatIndex}-${optionIndex}`}
      onClick={(e) => { e.stopPropagation(); onApplyTrim(); }}
    >
      Apply Trim
    </button>
    <button
      type="button"
      class="mn-btn mn-btn-small"
      data-testid={`bg-o3-preview-trim-${beatIndex}-${optionIndex}`}
      onClick={(e) => { e.stopPropagation(); onPreviewTrim(); }}
    >
      Preview Trim
    </button>
    <button
      type="button"
      class="mn-btn mn-btn-small"
      data-testid={`bg-o3-clear-trim-${beatIndex}-${optionIndex}`}
      onClick={(e) => { e.stopPropagation(); onClearTrim(); }}
    >
      Clear Trim
    </button>
  </div>
);

export function showBgO3NumericTrimControls(): boolean {
  try {
    if (localStorage.getItem('BG_O3_TRIM_HIDE_NUMERIC') === '1') return false;
    if (import.meta.env['VITE_BG_O3_TRIM_HIDE_NUMERIC'] === '1') return false;
    if (import.meta.env['VITE_BG_O3_TRIM_SHOW_NUMERIC'] === '1') return true;
    if (localStorage.getItem('BG_O3_TRIM_SHOW_NUMERIC') === '1') return true;
    // Off by default — amber cut-out (Start cut / Apply Cut) is the primary UX.
    return false;
  } catch {
    return true;
  }
}

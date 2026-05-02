// CropperModal — the inline-modal form of the Cropper. Replaces the v58
// "switch to Cropper tab, then come back, then drag from library" detour.
// In Path C the cropper opens AS A MODAL over whichever tab triggered it
// (Storyboard or BG slot click).
//
// Session 1 ships the modal shell + open/close mechanics. Crop mutation
// (POST /api/cr/save-crop) lands in Session 1.5+ once the server scope guard
// is in place per LD SCOPE_VALIDATION_V1.

import type { Signal } from '@preact/signals';
import { activeScope, scopeKey } from '../state/scope';

export interface CropperModalState {
  open: boolean;
  /** Image abs_path (from library or master) currently being cropped. */
  source: string | null;
  /** Beat slot the crop output should attach to, if any. */
  targetBeatId: string | null;
}

export const initialCropperModalState: CropperModalState = {
  open: false,
  source: null,
  targetBeatId: null,
};

export interface CropperModalProps {
  state: Signal<CropperModalState>;
  /**
   * Optional callback fired on close. Used by the App to flip activeTab
   * away from 'cropper' so the auto-open in ActivePane doesn't immediately
   * re-open the modal. (When the modal is opened from a non-cropper tab,
   * pass a no-op or omit.)
   */
  onClose?: () => void;
}

export function CropperModal({ state, onClose }: CropperModalProps) {
  if (!state.value.open) return null;
  const close = () => {
    state.value = { ...state.value, open: false };
    onClose?.();
  };
  return (
    <div
      class="mn-cropper-modal"
      data-testid="cropper-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cropper-modal-title"
      onClick={(e: MouseEvent) => {
        // Click on backdrop closes; clicks inside the panel don't bubble.
        if (e.target === e.currentTarget) close();
      }}
    >
      <div class="mn-cropper-modal-panel">
        <header class="mn-cropper-modal-header">
          <h2 id="cropper-modal-title">Cropper</h2>
          <button
            type="button"
            class="mn-cropper-close"
            data-testid="cropper-close"
            onClick={close}
            aria-label="Close cropper"
          >
            &times;
          </button>
        </header>
        <div class="mn-cropper-body">
          <p class="mn-dim">
            Source: <code>{state.value.source ?? '(no source)'}</code>
          </p>
          <p class="mn-dim">
            Target beat: <code>{state.value.targetBeatId ?? '(no target)'}</code>
          </p>
          <p class="mn-dim">
            Active scope: <code>{scopeKey(activeScope.value)}</code>
          </p>
          <p class="mn-readonly-banner">
            Session 1 read-only preview. Crop save (POST /api/cr/save-crop)
            ships in Session 1.5 with scope guard.
          </p>
        </div>
      </div>
    </div>
  );
}

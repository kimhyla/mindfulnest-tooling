// CropperModal — the inline-modal form of the Cropper. Replaces the v58
// "switch to Cropper tab, then come back, then drag from library" detour.
// In Path C the cropper opens AS A MODAL over whichever tab triggered it
// (Storyboard or BG slot click).
//
// Session 1 ships the modal shell + open/close mechanics. Crop mutation
// (POST /api/cr/save-crop) lands in Session 1.5+ once the server scope guard
// is in place per LD SCOPE_VALIDATION_V1.

import type { Signal } from '@preact/signals';
import { useState } from 'preact/hooks';
import { activeScope, scopeKey } from '../state/scope';
import { pathappPatch } from '../api/client';

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
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveDetail, setSaveDetail] = useState<string | null>(null);

  if (!state.value.open) return null;
  const close = () => {
    state.value = { ...state.value, open: false };
    setSaveStatus('idle');
    setSaveDetail(null);
    onClose?.();
  };

  // S2 v3.1 — save crop button stub. Sends a tiny placeholder b64 payload
  // through pathappPatch so the scope-guard + snapshot round-trip can be
  // exercised end-to-end. The full canvas + crop math is S3 polish.
  const onSaveCrop = async () => {
    if (!state.value.targetBeatId) {
      setSaveStatus('error');
      setSaveDetail('No target beat — open the cropper from a beat slot.');
      return;
    }
    setSaveStatus('saving');
    setSaveDetail(null);
    // Tiny 1x1 transparent png as placeholder b64 — real canvas wiring is S3.
    const placeholder_b64 =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/x8AAusB9eRWnLkAAAAASUVORK5CYII=';
    const result = await pathappPatch(activeScope.value, 'cr_save_crop', {
      crop_png_b64: placeholder_b64,
      beat_id: state.value.targetBeatId,
      source_key: state.value.source ?? '',
    });
    if (result.ok) {
      setSaveStatus('saved');
      const data = (result.data as { key?: string } | undefined) ?? {};
      setSaveDetail(`Saved as ${data.key ?? '(unnamed)'} — full canvas wiring lands in S3.`);
    } else {
      setSaveStatus('error');
      setSaveDetail(`HTTP ${result.status}: ${result.error}`);
    }
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
          <div class="mn-cropper-actions">
            <button
              type="button"
              class="mn-btn mn-btn-primary"
              data-testid="cropper-save-btn"
              onClick={onSaveCrop}
              disabled={saveStatus === 'saving' || !state.value.targetBeatId}
            >
              {saveStatus === 'saving' ? 'Saving…' : 'Save crop'}
            </button>
            <span
              class={`mn-cropper-save-status mn-cropper-save-${saveStatus}`}
              data-testid="cropper-save-status"
              data-save-status={saveStatus}
            >
              {saveStatus === 'idle'
                ? ''
                : saveStatus === 'saving'
                  ? 'sending…'
                  : saveStatus === 'saved'
                    ? `✓ ${saveDetail}`
                    : `✗ ${saveDetail}`}
            </span>
          </div>
          <p class="mn-readonly-banner">
            S2 v3.1 — placeholder canvas. The 1×1 PNG payload exercises the
            scope-guard + snapshot round-trip end-to-end. Full canvas + crop
            math lands in S3.
          </p>
        </div>
      </div>
    </div>
  );
}

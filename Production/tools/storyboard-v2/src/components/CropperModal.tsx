// CropperModal — wraps CropperCanvas in the shared Modal primitive.
// Per LD CROPPER_CANVAS_REAL_V1 + UI_PRIMITIVES_SHARED_V1 (S5.5c).
//
// S5.5c — replaces the v58/Session 2 1×1 placeholder PNG. Real <canvas> with
// 8 drag handles + aspect lock lives in CropperCanvas; CropperModal owns the
// Modal shell + Save flow → pathappPatch('cr_save_crop', ...) per Rule 7
// (single mutation channel).

import type { Signal } from '@preact/signals';
import { useRef, useState } from 'preact/hooks';
import { activeScope, scopeKey } from '../state/scope';
import { pathappPatch } from '../api/client';
import { Modal } from './ui/Modal';
import { Spinner } from './ui/Spinner';
import { pushToast } from './ui/Toast';
import { CropperCanvas, type CropperCanvasHandle } from './CropperCanvas';

export interface CropperModalState {
  open: boolean;
  /** Image src (data: URI or http: URL) currently being cropped. */
  source: string | null;
  /** Display label shown in the modal header — usually the source filename. */
  sourceLabel?: string | null;
  /** Beat slot the crop output should attach to, if any. */
  targetBeatId: string | null;
}

export const initialCropperModalState: CropperModalState = {
  open: false,
  source: null,
  sourceLabel: null,
  targetBeatId: null,
};

export interface CropperModalProps {
  state: Signal<CropperModalState>;
  /**
   * Optional callback fired on close. Used by the App to flip activeTab away
   * from 'cropper' so ActivePane's auto-open doesn't immediately re-open.
   */
  onClose?: () => void;
  /**
   * Optional callback fired after a successful crop save with the resulting
   * server response (key, filename, etc.). Lets parents (Beat Generator,
   * Storyboard) attach the crop to the right slot.
   */
  onSaved?: (result: { key: string; filename: string }) => void;
}

interface SaveResult {
  key?: string;
  filename?: string;
  thumb_b64?: string;
  gallery_b64?: string;
}

export function CropperModal({ state, onClose, onSaved }: CropperModalProps) {
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'error'>('idle');
  const [saveDetail, setSaveDetail] = useState<string | null>(null);
  const canvasRef = useRef<CropperCanvasHandle | null>(null);

  const close = () => {
    state.value = { ...state.value, open: false };
    setSaveStatus('idle');
    setSaveDetail(null);
    canvasRef.current = null;
    onClose?.();
  };

  const onSaveCrop = async () => {
    if (!state.value.targetBeatId) {
      setSaveStatus('error');
      setSaveDetail('No target beat — open the cropper from a beat slot.');
      return;
    }
    if (!canvasRef.current) {
      setSaveStatus('error');
      setSaveDetail('Canvas not ready.');
      return;
    }
    const cropPngB64 = canvasRef.current.exportCropPngB64();
    if (!cropPngB64) {
      setSaveStatus('error');
      setSaveDetail('Crop region is empty or image not loaded.');
      return;
    }
    setSaveStatus('saving');
    setSaveDetail(null);
    const result = await pathappPatch<SaveResult>(activeScope.value, 'cr_save_crop', {
      crop_png_b64: cropPngB64,
      beat_id: state.value.targetBeatId,
      source_key: state.value.source ?? '',
    });
    if (result.ok) {
      const data = result.data ?? {};
      pushToast({
        kind: 'success',
        message: `Crop saved: ${data.filename ?? data.key ?? 'unnamed'}`,
        source: 'cropper-save',
      });
      onSaved?.({
        key: String(data.key ?? ''),
        filename: String(data.filename ?? ''),
      });
      close();
    } else {
      setSaveStatus('error');
      setSaveDetail(`HTTP ${result.status}: ${result.error}`);
      pushToast({
        kind: 'error',
        message: `Crop save failed: ${result.error ?? 'unknown'}`,
        source: 'cropper-save-error',
      });
    }
  };

  if (!state.value.open) return null;

  return (
    <Modal
      id="cropper"
      title={`Cropper — ${state.value.sourceLabel ?? state.value.source ?? '(no source)'}`}
      open={state.value.open}
      onClose={close}
      panelClass="mn-modal-wide"
      footer={
        <>
          <span
            class={`mn-cropper-save-status mn-cropper-save-${saveStatus}`}
            data-testid="cropper-save-status"
            data-save-status={saveStatus}
          >
            {saveStatus === 'saving' ? (
              <>
                <Spinner size="sm" inline /> sending…
              </>
            ) : saveStatus === 'error' ? (
              <>✗ {saveDetail}</>
            ) : null}
          </span>
          <button
            type="button"
            class="mn-btn"
            data-testid="cropper-cancel"
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="button"
            class="mn-btn mn-btn-primary"
            data-testid="cropper-save-btn"
            onClick={onSaveCrop}
            disabled={saveStatus === 'saving' || !state.value.targetBeatId}
          >
            {saveStatus === 'saving' ? 'Saving…' : 'Save crop'}
          </button>
        </>
      }
    >
      <p class="mn-dim">
        Source: <code>{state.value.source ?? '(no source)'}</code>{' '}
        · Target beat: <code>{state.value.targetBeatId ?? '(no target)'}</code>{' '}
        · Active scope: <code>{scopeKey(activeScope.value)}</code>
      </p>
      <CropperCanvas
        imageSrc={state.value.source}
        initialAspect="4:3"
        onReady={(h) => { canvasRef.current = h; }}
      />
    </Modal>
  );
}

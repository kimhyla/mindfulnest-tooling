// CropperModal — wraps CropperCanvas in the shared Modal primitive.
// Per LD CROPPER_CANVAS_REAL_V1 + UI_PRIMITIVES_SHARED_V1 (S5.5c).
//
// S5.5c — replaces the v58/Session 2 1×1 placeholder PNG. Real <canvas> with
// 8 drag handles + aspect lock lives in CropperCanvas; CropperModal owns the
// Modal shell + Save flow → pathappPatch('cr_save_crop', ...) per Rule 7
// (single mutation channel).

import type { Signal } from '@preact/signals';
import { useEffect, useRef, useState } from 'preact/hooks';
import { activeScope } from '../state/scope';
import { apiGet, pathappPatch } from '../api/client';
import { SERVER_BASE } from '../api/endpoints';
import { makeDropTarget } from '../utils/dragdrop';
import { Modal } from './ui/Modal';
import { Spinner } from './ui/Spinner';
import { pushToast } from './ui/Toast';
import { CropperCanvas, type CropperCanvasHandle } from './CropperCanvas';
import { flattenLibraryResponse } from './LibraryPanel';

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

// ----------------------------------------------------------------
// LibraryStrip — compact horizontal scroller shown inside the modal
// so images can be loaded without drag-drop (which is blocked by the
// modal backdrop overlay). Fetches /api/cr/library when modal opens.
// ----------------------------------------------------------------

interface LibStripItem {
  key?: string;
  abs_path?: string;
  filename?: string;
  thumb_b64?: string;
  thumb_url?: string;
  display_name?: string;
}

function useLibraryStrip(open: boolean, eventId: string) {
  const [items, setItems] = useState<LibStripItem[]>([]);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      const res = await apiGet<object>('cr_library', { event_id: eventId });
      if (cancelled || !res.ok || !res.data) return;
      setItems(flattenLibraryResponse(res.data as Parameters<typeof flattenLibraryResponse>[0]));
    })();
    return () => { cancelled = true; };
  }, [open, eventId]);

  const filtered = query
    ? items.filter((it) => (it.filename ?? it.display_name ?? it.key ?? '').toLowerCase().includes(query.toLowerCase()))
    : items;

  return { filtered, query, setQuery };
}

export function CropperModal({ state, onClose, onSaved }: CropperModalProps) {
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'error'>('idle');
  const [saveDetail, setSaveDetail] = useState<string | null>(null);
  const canvasRef = useRef<CropperCanvasHandle | null>(null);

  // Load-from-library strip — workaround for modal backdrop blocking Library panel drag-drop
  const { filtered: libItems, query: libQuery, setQuery: setLibQuery } =
    useLibraryStrip(state.value.open, activeScope.value.event_id);

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

  // R2.3 fix: drop target on the cropper canvas. Drop a library tile here →
  // the modal's source image swaps to the dropped image. The drop handler
  // sets state.source via the signal, and CropperCanvas re-renders the new src.
  const canvasDropHandlers = makeDropTarget(
    (payload) => {
      if (payload.kind !== 'lib-image') return;
      // Resolve a server-fetchable URL: prefer abs_path through /api/cr/full,
      // fall back to lib_key. Either way, set source so canvas reloads.
      const newSrc = payload.abs_path
        ? `${SERVER_BASE}/api/cr/full?abs_path=${encodeURIComponent(payload.abs_path)}`
        : payload.lib_key;
      state.value = {
        ...state.value,
        source: newSrc,
        sourceLabel: payload.filename ?? payload.lib_key,
      };
    },
    (p) => p.kind === 'lib-image',
  );

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
      {/* Load-from-library strip — modal backdrop blocks Library panel drag-drop,
          so we show a compact scrollable row of library thumbnails here.
          Click any thumbnail to load it as the crop source. */}
      <div class="mn-cropper-lib-strip" data-testid="cropper-lib-strip">
        <div class="mn-cropper-lib-strip-header">
          <span class="mn-dim" style="font-size:11px;white-space:nowrap">Load from library:</span>
          <input
            type="search"
            class="mn-cropper-lib-search"
            placeholder="filter…"
            value={libQuery}
            onInput={(e) => setLibQuery((e.target as HTMLInputElement).value)}
            data-testid="cropper-lib-search"
          />
        </div>
        <div class="mn-cropper-lib-thumbs" data-testid="cropper-lib-thumbs">
          {libItems.length === 0 ? (
            <span class="mn-dim" style="font-size:11px;padding:4px 8px">Library empty</span>
          ) : (
            libItems.map((it, i) => {
              const src = it.thumb_b64 ?? it.thumb_url;
              const label = it.display_name ?? it.filename ?? it.key ?? `item-${i}`;
              const loadSrc = it.abs_path
                ? `${SERVER_BASE}/api/cr/full?abs_path=${encodeURIComponent(it.abs_path)}`
                : src ?? '';
              return (
                <button
                  key={it.key ?? it.abs_path ?? i}
                  type="button"
                  class="mn-cropper-lib-thumb"
                  title={label}
                  data-testid={`cropper-lib-thumb-${i}`}
                  onClick={() => {
                    if (!loadSrc) return;
                    state.value = { ...state.value, source: loadSrc, sourceLabel: label };
                  }}
                >
                  {src ? (
                    <img src={src} alt={label} class="mn-cropper-lib-thumb-img" />
                  ) : (
                    <span class="mn-dim" style="font-size:10px">{label.slice(0, 8)}</span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>
      <p class="mn-dim" style="font-size:11px;margin:0 0 8px 0">
        Source: <code>{state.value.source ? state.value.sourceLabel ?? state.value.source.slice(-30) : '(none — pick from library above or open cropper from a beat)'}</code>{' '}
        · Beat: <code>{state.value.targetBeatId ?? '(none)'}</code>
      </p>
      <div
        class="mn-cropper-canvas-wrap mn-drop-target"
        data-testid="cropper-canvas-drop-target"
        data-loaded-source={state.value.source ?? ''}
        onDragOver={canvasDropHandlers.onDragOver}
        onDragLeave={canvasDropHandlers.onDragLeave}
        onDrop={canvasDropHandlers.onDrop}
      >
        <CropperCanvas
          imageSrc={state.value.source}
          initialAspect="4:3"
          onReady={(h) => { canvasRef.current = h; }}
        />
      </div>
    </Modal>
  );
}

// CropperCanvas — real <canvas> with 8 drag handles + aspect ratio constraint.
// Per LD CROPPER_CANVAS_REAL_V1 (S5.5c).
//
// Replaces the v58/Session 2 1×1 placeholder PNG. Loads source image, draws
// it on a canvas at fitted size, and lets Kim drag a crop rectangle with
// 8 handles (4 corners + 4 edges). Aspect-ratio is locked by default to 4:3
// (matching server-side asset_type='crop_4x3' in _handle_cr_save_crop:9611).
//
// On Save: extracts the cropped pixels into a separate canvas, exports as PNG
// base64, and bubbles up via the onSave callback (which the parent CropperModal
// pipes through pathappPatch → /api/cr/save-crop).
//
// All math is in CSS-pixel coordinates on the displayed canvas; the export
// canvas reconstructs the full-resolution crop using the natural-size scaling
// factor. Result is real cropped pixels (not 1×1 placeholder).

import { useEffect, useRef, useState } from 'preact/hooks';

export type AspectMode = '4:3' | '16:9' | '1:1' | 'free';

export interface CropperCanvasProps {
  /** Image source URL (http: or data:). When this changes, image reloads. */
  imageSrc: string | null;
  /** Initial aspect ratio constraint. */
  initialAspect?: AspectMode;
  /** Callback when user clicks Save in the parent. parent calls our save() via ref. */
  onCropChange?: (rect: CropRect) => void;
  /** Width of the canvas display area in CSS px. */
  displayWidth?: number;
  /** Height of the canvas display area in CSS px. */
  displayHeight?: number;
}

export interface CropRect {
  /** In displayed (CSS) pixel space. */
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CropperCanvasHandle {
  /** Returns base64 PNG of the cropped region at native resolution, or null on error. */
  exportCropPngB64: () => string | null;
  /** Switch aspect-ratio constraint at runtime. */
  setAspect: (mode: AspectMode) => void;
  /** Manually overwrite the crop rectangle (used by parent for numeric inputs). */
  setCrop: (rect: CropRect) => void;
  /** Read current crop. */
  getCrop: () => CropRect;
}

type Handle =
  | 'nw' | 'n' | 'ne'
  | 'w' |       'e'
  | 'sw' | 's' | 'se'
  | 'inside';

interface DragState {
  handle: Handle;
  startX: number;   // mouse client x at dragstart (CSS px)
  startY: number;
  startRect: CropRect;
}

const HANDLE_SIZE = 10;

function aspectRatio(mode: AspectMode): number | null {
  switch (mode) {
    case '4:3': return 4 / 3;
    case '16:9': return 16 / 9;
    case '1:1': return 1;
    case 'free': return null;
  }
}

function clampRectToCanvas(r: CropRect, canvasW: number, canvasH: number): CropRect {
  let { x, y, w, h } = r;
  if (w < 8) w = 8;
  if (h < 8) h = 8;
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (x + w > canvasW) x = Math.max(0, canvasW - w);
  if (y + h > canvasH) y = Math.max(0, canvasH - h);
  if (x + w > canvasW) w = canvasW - x;
  if (y + h > canvasH) h = canvasH - y;
  return { x, y, w, h };
}

/** Apply aspect lock by adjusting w (or h) around the dragged side. */
function applyAspect(
  rect: CropRect, ratio: number | null, canvasW: number, canvasH: number,
): CropRect {
  if (ratio === null) return rect;
  // Fix width, recompute height (height anchored at top of original rect).
  let { x, y, w } = rect;
  let h = w / ratio;
  if (h > canvasH - y) {
    h = canvasH - y;
    w = h * ratio;
    if (x + w > canvasW) w = canvasW - x;
    h = w / ratio;
  }
  return { x, y, w, h };
}

interface CropperCanvasInner extends CropperCanvasProps {
  onReady?: (handle: CropperCanvasHandle) => void;
}

export function CropperCanvas(props: CropperCanvasInner) {
  const {
    imageSrc, initialAspect = '4:3', onCropChange, onReady,
    displayWidth = 720, displayHeight = 540,
  } = props;

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [aspect, setAspect] = useState<AspectMode>(initialAspect);
  const [crop, setCropState] = useState<CropRect>({ x: 0, y: 0, w: 0, h: 0 });
  const [drag, setDrag] = useState<DragState | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [imageReady, setImageReady] = useState(false);
  // The rendered image's bounding box inside the canvas (letterboxed).
  const renderRectRef = useRef<{ x: number; y: number; w: number; h: number; sx: number; sy: number } | null>(null);

  // Load the image when src changes.
  useEffect(() => {
    setImageReady(false);
    setImageError(null);
    renderRectRef.current = null;
    imgRef.current = null;
    if (!imageSrc) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      setImageReady(true);
      // Fit image into canvas with letterboxing.
      const canvasW = displayWidth;
      const canvasH = displayHeight;
      const naturalW = img.naturalWidth || img.width;
      const naturalH = img.naturalHeight || img.height;
      if (naturalW === 0 || naturalH === 0) {
        setImageError('Image has zero size');
        return;
      }
      const scale = Math.min(canvasW / naturalW, canvasH / naturalH);
      const w = naturalW * scale;
      const h = naturalH * scale;
      const x = (canvasW - w) / 2;
      const y = (canvasH - h) / 2;
      renderRectRef.current = { x, y, w, h, sx: scale, sy: scale };
      // Default crop = 80% centered, aspect-locked.
      const defaultW = w * 0.8;
      const ratio = aspectRatio(aspect);
      const defaultH = ratio ? defaultW / ratio : h * 0.8;
      const finalH = Math.min(defaultH, h);
      const finalW = ratio ? finalH * ratio : defaultW;
      const initial = {
        x: x + (w - finalW) / 2,
        y: y + (h - finalH) / 2,
        w: finalW,
        h: finalH,
      };
      setCropState(initial);
    };
    img.onerror = () => {
      setImageError(`Failed to load image: ${imageSrc}`);
    };
    img.src = imageSrc;
  }, [imageSrc, displayWidth, displayHeight]);

  // Re-draw when crop or image changes.
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, c.width, c.height);
    const img = imgRef.current;
    const rr = renderRectRef.current;
    if (img && rr && imageReady) {
      ctx.drawImage(img, rr.x, rr.y, rr.w, rr.h);
    }
    if (crop.w > 0 && crop.h > 0) {
      // Dim outside the crop.
      ctx.fillStyle = 'rgba(0, 0, 0, 0.55)';
      ctx.fillRect(0, 0, c.width, crop.y);
      ctx.fillRect(0, crop.y, crop.x, crop.h);
      ctx.fillRect(crop.x + crop.w, crop.y, c.width - (crop.x + crop.w), crop.h);
      ctx.fillRect(0, crop.y + crop.h, c.width, c.height - (crop.y + crop.h));
      // Crop border + handles.
      ctx.strokeStyle = '#5b8cff';
      ctx.lineWidth = 2;
      ctx.strokeRect(crop.x, crop.y, crop.w, crop.h);
      // 8 handles.
      ctx.fillStyle = '#5b8cff';
      const positions: Array<[number, number]> = [
        [crop.x, crop.y],
        [crop.x + crop.w / 2, crop.y],
        [crop.x + crop.w, crop.y],
        [crop.x, crop.y + crop.h / 2],
        [crop.x + crop.w, crop.y + crop.h / 2],
        [crop.x, crop.y + crop.h],
        [crop.x + crop.w / 2, crop.y + crop.h],
        [crop.x + crop.w, crop.y + crop.h],
      ];
      for (const [hx, hy] of positions) {
        ctx.fillRect(hx - HANDLE_SIZE / 2, hy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
      }
    }
  }, [crop, imageReady]);

  // Hit-test which handle the mouse is on.
  const hitHandle = (mx: number, my: number): Handle | null => {
    const within = (px: number, py: number) =>
      Math.abs(mx - px) < HANDLE_SIZE && Math.abs(my - py) < HANDLE_SIZE;
    if (within(crop.x, crop.y)) return 'nw';
    if (within(crop.x + crop.w / 2, crop.y)) return 'n';
    if (within(crop.x + crop.w, crop.y)) return 'ne';
    if (within(crop.x, crop.y + crop.h / 2)) return 'w';
    if (within(crop.x + crop.w, crop.y + crop.h / 2)) return 'e';
    if (within(crop.x, crop.y + crop.h)) return 'sw';
    if (within(crop.x + crop.w / 2, crop.y + crop.h)) return 's';
    if (within(crop.x + crop.w, crop.y + crop.h)) return 'se';
    if (mx > crop.x && mx < crop.x + crop.w && my > crop.y && my < crop.y + crop.h) {
      return 'inside';
    }
    return null;
  };

  const onMouseDown = (e: MouseEvent) => {
    const c = canvasRef.current;
    if (!c) return;
    const rect = c.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const h = hitHandle(mx, my);
    if (!h) return;
    e.preventDefault();
    setDrag({ handle: h, startX: mx, startY: my, startRect: { ...crop } });
  };

  const onMouseMove = (e: MouseEvent) => {
    if (!drag) return;
    const c = canvasRef.current;
    if (!c) return;
    const rect = c.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const dx = mx - drag.startX;
    const dy = my - drag.startY;
    let next: CropRect = { ...drag.startRect };
    const h = drag.handle;
    if (h === 'inside') {
      next = { ...drag.startRect, x: drag.startRect.x + dx, y: drag.startRect.y + dy };
    } else {
      if (h.includes('w')) { next.x = drag.startRect.x + dx; next.w = drag.startRect.w - dx; }
      if (h.includes('e')) { next.w = drag.startRect.w + dx; }
      if (h.includes('n')) { next.y = drag.startRect.y + dy; next.h = drag.startRect.h - dy; }
      if (h.includes('s')) { next.h = drag.startRect.h + dy; }
      if (next.w < 8) { next.w = 8; if (h.includes('w')) next.x = drag.startRect.x + drag.startRect.w - 8; }
      if (next.h < 8) { next.h = 8; if (h.includes('n')) next.y = drag.startRect.y + drag.startRect.h - 8; }
    }
    next = applyAspect(next, aspectRatio(aspect), c.width, c.height);
    next = clampRectToCanvas(next, c.width, c.height);
    setCropState(next);
    onCropChange?.(next);
  };

  const onMouseUp = () => {
    setDrag(null);
  };

  // Imperative handle for parent to call exportCropPngB64.
  useEffect(() => {
    if (!onReady) return;
    const handle: CropperCanvasHandle = {
      exportCropPngB64: () => {
        const img = imgRef.current;
        const rr = renderRectRef.current;
        if (!img || !rr) return null;
        if (crop.w < 4 || crop.h < 4) return null;
        // Translate displayed crop → natural-image crop.
        const sx = (crop.x - rr.x) / rr.sx;
        const sy = (crop.y - rr.y) / rr.sy;
        const sw = crop.w / rr.sx;
        const sh = crop.h / rr.sy;
        if (sw < 1 || sh < 1) return null;
        const exportCanvas = document.createElement('canvas');
        exportCanvas.width = Math.round(sw);
        exportCanvas.height = Math.round(sh);
        const ec = exportCanvas.getContext('2d');
        if (!ec) return null;
        ec.drawImage(img, sx, sy, sw, sh, 0, 0, exportCanvas.width, exportCanvas.height);
        const dataUrl = exportCanvas.toDataURL('image/png');
        // Strip "data:image/png;base64," prefix.
        const i = dataUrl.indexOf(',');
        return i >= 0 ? dataUrl.slice(i + 1) : null;
      },
      setAspect: (mode) => setAspect(mode),
      setCrop: (rect) => {
        const c = canvasRef.current;
        if (!c) return;
        let next = applyAspect(rect, aspectRatio(aspect), c.width, c.height);
        next = clampRectToCanvas(next, c.width, c.height);
        setCropState(next);
      },
      getCrop: () => crop,
    };
    onReady(handle);
  }, [crop, aspect, onReady]);

  return (
    <div class="mn-cropper-canvas-wrap" data-testid="cropper-canvas-wrap">
      <div class="mn-cropper-toolbar">
        <span>Aspect:</span>
        <div class="mn-cropper-aspect-row">
          {(['4:3', '16:9', '1:1', 'free'] as AspectMode[]).map((m) => (
            <button
              key={m}
              type="button"
              class={`mn-cropper-aspect-pill${aspect === m ? ' is-active' : ''}`}
              data-testid={`cropper-aspect-${m.replace(':', '-')}`}
              onClick={() => setAspect(m)}
            >
              {m}
            </button>
          ))}
        </div>
        <span data-testid="cropper-crop-dims">
          {Math.round(crop.w)} × {Math.round(crop.h)} display px
        </span>
      </div>
      <div class="mn-cropper-canvas-stage">
        <canvas
          ref={canvasRef}
          width={displayWidth}
          height={displayHeight}
          data-testid="cropper-canvas"
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
        />
      </div>
      {imageError ? (
        <p class="mn-warn" data-testid="cropper-image-error">{imageError}</p>
      ) : null}
      {!imageReady && imageSrc && !imageError ? (
        <p class="mn-loading">Loading image…</p>
      ) : null}
    </div>
  );
}

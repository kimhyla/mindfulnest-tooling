/**
 * Browser preview overlay box — mirrors production_server._PHASE_FRAME_* on
 * full-bleed 1280×720 (no letterbox content offset).
 *
 * LD-331 / LD-821 / WATERCOLOR_OVERLAY_SCALE_TO_BBOX_NO_PAD_V2.
 * Single source for CSS vars on .mn-lipsync-video-wrapper — do not fork % in app.css.
 */
export type PhaseOverlayPhase = 'a' | 'b';

/** Canvas is 1280×720; overlay bbox uses absolute pixel coords from production_server. */
const NORMALIZED_CANVAS_W = 1280;
const NORMALIZED_CANVAS_H = 720;

/** Mirrors production_server._PHASE_FRAME_* — wc_v17 full-bleed rounded canonical. */
const SERVER_BBOX: Record<
  PhaseOverlayPhase,
  { frameX: number; frameY: number; maxW: number; maxH: number }
> = {
  b: { frameX: 64, frameY: 64, maxW: 368, maxH: 508 },
  a: { frameX: 870, frameY: 64, maxW: 368, maxH: 508 },
};

export function phaseWatercolorOverlayCssVars(phase: PhaseOverlayPhase): Record<string, string> {
  const { frameX, frameY, maxW, maxH } = SERVER_BBOX[phase];
  // ffmpeg overlay uses absolute pixels on the 1280×720 canvas; CSS % must be
  // canvas-relative (not content-box-relative) or overlays land in letterbox bars.
  const leftPct = (frameX / NORMALIZED_CANVAS_W) * 100;
  const topPct = (frameY / NORMALIZED_CANVAS_H) * 100;
  const widthPct = (maxW / NORMALIZED_CANVAS_W) * 100;
  const maxHeightPct = (maxH / NORMALIZED_CANVAS_H) * 100;
  return {
    '--wc-overlay-left': `${leftPct.toFixed(2)}%`,
    '--wc-overlay-top': `${topPct.toFixed(2)}%`,
    '--wc-overlay-width': `${widthPct.toFixed(2)}%`,
    '--wc-overlay-max-height': `${maxHeightPct.toFixed(2)}%`,
  };
}

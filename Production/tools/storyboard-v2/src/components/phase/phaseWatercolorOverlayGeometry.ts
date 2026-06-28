/**
 * Browser preview overlay box — mirrors production_server._PHASE_FRAME_* +
 * NORMALIZATION_VF_EXPR letterbox (720×544 lipsync → 953×720 content in 1280×720).
 *
 * LD-331 / LD-821 / WATERCOLOR_OVERLAY_SCALE_TO_BBOX_NO_PAD_V2.
 * Single source for CSS vars on .mn-lipsync-video-wrapper — do not fork % in app.css.
 */
export type PhaseOverlayPhase = 'a' | 'b';

/** Canvas is 1280×720; overlay bbox uses absolute pixel coords from production_server. */
const NORMALIZED_CANVAS_W = 1280;
const NORMALIZED_CANVAS_H = 720;

/** Mirrors production_server._PHASE_FRAME_X / _PHASE_FRAME_Y / _PHASE_FRAME_MAX_* */
const SERVER_BBOX: Record<
  PhaseOverlayPhase,
  { frameX: number; frameY: number; maxW: number; maxH: number }
> = {
  b: { frameX: 185, frameY: 30, maxW: 340, maxH: 540 },
  a: { frameX: 800, frameY: 30, maxW: 480, maxH: 540 },
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

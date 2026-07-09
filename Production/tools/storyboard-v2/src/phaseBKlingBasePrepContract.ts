/** Phase B Kling base prep — mirrors phase_b_kling_base_prep.py operator contract. */

import {
  PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID,
} from './phaseBCedricContract';

export const PHASE_B_KLING_AUTO_PREP_CODE = 'PHASE_B_KLING_AUTO_BOOKEND_UNIT_V1';

export const PHASE_B_KLING_VIDEO_TAILROOM_S = 2;

export type PhaseBLipsyncBasePrepMeta = {
  code?: string;
  strategy?: 'trim_long_base' | 'auto_loop_bookend_unit';
  base_clip?: string;
  base_duration_s?: number;
  target_video_s?: number;
  loop_unit?: string;
  loop_unit_duration_s?: number;
  looped_duration_s?: number;
  submit_size_mb?: number;
};

export function formatPhaseBLipsyncBasePrepHint(): string {
  return (
    `On send: idle video auto-sized to voice stem + ${PHASE_B_KLING_VIDEO_TAILROOM_S}s. ` +
    `Short bases loop from approved bookend unit (${PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID}, ~29s); ` +
    'long bases trim only — no arbitrary short-idle re-loop.'
  );
}

export function formatPhaseBLipsyncBasePrepSummary(
  prep: PhaseBLipsyncBasePrepMeta | null | undefined,
): string | null {
  if (!prep?.strategy || !prep.target_video_s) return null;
  const target = prep.target_video_s.toFixed(1);
  if (prep.strategy === 'auto_loop_bookend_unit') {
    const unit = prep.loop_unit ?? PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID;
    return `Last send prep: looped ${unit} → ${target}s (stem + ${PHASE_B_KLING_VIDEO_TAILROOM_S}s tail).`;
  }
  if (prep.strategy === 'trim_long_base') {
    const base = prep.base_clip ?? 'base';
    return `Last send prep: trimmed ${base} → ${target}s (stem + ${PHASE_B_KLING_VIDEO_TAILROOM_S}s tail).`;
  }
  return null;
}

import { describe, expect, it } from 'vitest';
import {
  formatPhaseBLipsyncBasePrepHint,
  formatPhaseBLipsyncBasePrepSummary,
  PHASE_B_KLING_AUTO_PREP_CODE,
} from '../../phaseBKlingBasePrepContract';

describe('phaseBKlingBasePrepContract', () => {
  it('exports auto prep code', () => {
    expect(PHASE_B_KLING_AUTO_PREP_CODE).toBe('PHASE_B_KLING_AUTO_BOOKEND_UNIT_V1');
  });

  it('hint mentions bookend unit and stem tailroom', () => {
    const hint = formatPhaseBLipsyncBasePrepHint();
    expect(hint).toContain('cedric_idle_bookend_unit_v1');
    expect(hint).toContain('+ 2s');
  });

  it('summarizes auto loop prep', () => {
    const summary = formatPhaseBLipsyncBasePrepSummary({
      strategy: 'auto_loop_bookend_unit',
      target_video_s: 183,
      loop_unit: 'cedric_idle_bookend_unit_v1.mp4',
    });
    expect(summary).toContain('183.0s');
    expect(summary).toContain('cedric_idle_bookend_unit_v1.mp4');
  });

  it('summarizes trim prep', () => {
    const summary = formatPhaseBLipsyncBasePrepSummary({
      strategy: 'trim_long_base',
      target_video_s: 120,
      base_clip: 'cedric_idle_newstyle_v13_200s_7xloop.mp4',
    });
    expect(summary).toContain('trimmed');
    expect(summary).toContain('120.0s');
  });
});

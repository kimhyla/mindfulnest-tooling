import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergeOperatorFieldOnHydrate } from '../../utils/operatorEditMerge.ts';

/** Contract tested by PHASE-CLIP-HYDRATE-1 — omitted server field keeps local clip. */
function mergeClipOnHydrate(
  local: string | undefined,
  state: Record<string, unknown>,
  field: string,
  patchInFlight: boolean,
): string | undefined {
  if (!Object.prototype.hasOwnProperty.call(state, field)) {
    return local;
  }
  const raw = state[field];
  const server = typeof raw === 'string' && raw.trim() ? raw : undefined;
  return mergeOperatorFieldOnHydrate(local, server, { patchInFlight });
}

describe('usePhaseBaseClipPicker hydrate contract', () => {
  const field = 'phase_a_chipper_sitting_clip_id';

  it('omitted server field keeps local clip id', () => {
    const state = { ok: true, phase_a_lipsync_file: 'fix.mp4' };
    const out = mergeClipOnHydrate('chipper_sitting_alt_v2', state, field, false);
    assert.equal(out, 'chipper_sitting_alt_v2');
  });

  it('present server field wins when idle', () => {
    const state = { [field]: 'arlo_idle_wizard_desk_v4' };
    const out = mergeClipOnHydrate('chipper_sitting_alt_v2', state, field, false);
    assert.equal(out, 'arlo_idle_wizard_desk_v4');
  });

  it('patch in flight keeps local clip id', () => {
    const state = { [field]: 'arlo_idle_wizard_desk_v4' };
    const out = mergeClipOnHydrate('chipper_sitting_alt_v2', state, field, true);
    assert.equal(out, 'chipper_sitting_alt_v2');
  });
});

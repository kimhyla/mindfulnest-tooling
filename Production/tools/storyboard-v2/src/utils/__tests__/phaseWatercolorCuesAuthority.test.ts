import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  mergeWatercolorCuesOnHydrate,
  parseWatercolorCuesFromEventState,
  watercolorCueFromServerSchema,
} from '../phaseWatercolorCuesAuthority.ts';

describe('PHASE_WATERCOLOR_CUE_AUTHORITY_V1', () => {
  const local = [
    {
      id: 'cue_local',
      watercolor_key: 'hands_rubbing',
      offset_ms: 11000,
      duration_ms: 6000,
    },
  ];

  it('parseWatercolorCuesFromEventState reads server schema from flat state', () => {
    const parsed = parseWatercolorCuesFromEventState(
      {
        phase_b_watercolor_cues_json: JSON.stringify([
          {
            id: 'cue_srv',
            key: 'spell_title',
            timestamp_ms: 5000,
            duration_ms: 3000,
          },
        ]),
      },
      'b',
    );
    assert.equal(parsed?.length, 1);
    assert.equal(parsed?.[0]?.watercolor_key, 'spell_title');
    assert.equal(parsed?.[0]?.offset_ms, 5000);
  });

  it('merge keeps local cues when server omits field (refreshAll blind-wipe class)', () => {
    const merged = mergeWatercolorCuesOnHydrate(local, undefined, { patchInFlight: false });
    assert.equal(merged.length, 1);
    assert.equal(merged[0]?.id, 'cue_local');
  });

  it('merge keeps local cues while patch is in flight', () => {
    const merged = mergeWatercolorCuesOnHydrate(local, [], { patchInFlight: true });
    assert.equal(merged.length, 1);
    assert.equal(merged[0]?.offset_ms, 11000);
  });

  it('merge adopts server cues when field present and idle', () => {
    const server = [
      watercolorCueFromServerSchema({
        id: 'cue_srv',
        key: 'new_asset',
        timestamp_ms: 2000,
        duration_ms: 4000,
      }),
    ];
    const merged = mergeWatercolorCuesOnHydrate(local, server, { patchInFlight: false });
    assert.equal(merged.length, 1);
    assert.equal(merged[0]?.watercolor_key, 'new_asset');
  });

  it('merge clears cues when server explicitly returns empty array', () => {
    const merged = mergeWatercolorCuesOnHydrate(local, [], { patchInFlight: false });
    assert.equal(merged.length, 0);
  });
});

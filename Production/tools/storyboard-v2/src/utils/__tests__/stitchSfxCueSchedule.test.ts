import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  stitchSfxCueDelaySeconds,
  stitchSfxCuesToSchedule,
  type StitchSfxCueScheduleInput,
} from '../stitchSfxCueSchedule.ts';

describe('STITCH_SFX_CUE_SCHEDULE_V1', () => {
  const whoosh: StitchSfxCueScheduleInput = {
    id: 'whoosh',
    offset_ms: 0,
    duration_ms: 3104,
    source_path: '/Users/x/Dropbox/Production/Event_3/library/whoosh sound.mp3',
  };
  const exitCue: StitchSfxCueScheduleInput = {
    id: 'exit',
    offset_ms: 20228,
    duration_ms: 1647,
    source_path: 'Production/Event_3/library/exit resolution.mp3',
  };

  it('schedules whoosh and exit when playhead is at start', () => {
    const scheduled = stitchSfxCuesToSchedule([whoosh, exitCue], 0);
    assert.equal(scheduled.length, 2);
    assert.equal(stitchSfxCueDelaySeconds(0, 0), 0);
    assert.ok(Math.abs(scheduled[1].delayS - 20.228) < 0.001);
  });

  it('skips past cues when playhead is at end', () => {
    const scheduled = stitchSfxCuesToSchedule([whoosh, exitCue], 21.875);
    assert.equal(scheduled.length, 0);
  });

  it('whoosh is skipped after ~80ms drift resync — documents why timeupdate resync was removed', () => {
    const afterFalseResync = stitchSfxCuesToSchedule([whoosh, exitCue], 0.25);
    assert.equal(afterFalseResync.some((c) => c.cue.id === 'whoosh'), false);
    assert.ok(afterFalseResync.some((c) => c.cue.id === 'exit'));
  });

  it('STITCH_AMBIENT_NO_TIMEUPDATE_RESYNC_V1 — ambient bed must not seek on every timeupdate', () => {
    const src = readFileSync(
      new URL('../../components/StitchSlotAmbientBedAudio.tsx', import.meta.url),
      'utf8',
    );
    assert.doesNotMatch(src, /addEventListener\('timeupdate'/);
  });
});

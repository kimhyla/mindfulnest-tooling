// Run: cd Production/tools/storyboard-v2 && node --experimental-strip-types --test src/utils/__tests__/o3JobStatusContract.test.ts
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  activeO3PollJobsFromBeats,
  beatO3GenerateInFlight,
  beatO3JobBusy,
  beatO3ServerJobInFlight,
  pruneSubmitPollLatch,
} from '../../o3JobStatusContract.ts';

describe('o3JobStatusContract — submit latch vs stale session', () => {
  it('keeps submit latch when session beat has job_busy false (pre-enrich GET)', () => {
    const beats = [{
      beat_id: 'bg_arc1_event3_pre_beat_03',
      job_busy: false,
      o3_current_job_id: null,
    }];
    const latch = { bg_arc1_event3_pre_beat_03: '7f6f760b' };
    const merged = activeO3PollJobsFromBeats(beats, latch);
    assert.equal(merged.bg_arc1_event3_pre_beat_03, '7f6f760b');
  });

  it('does not prune latch on stale job_busy false alone', () => {
    const beats = [{
      beat_id: 'bg_arc1_event3_pre_beat_03',
      job_busy: false,
      kling_o3_status: 'draft',
    }];
    const latch = { bg_arc1_event3_pre_beat_03: '7f6f760b' };
    const pruned = pruneSubmitPollLatch(beats, latch);
    assert.equal(pruned.bg_arc1_event3_pre_beat_03, '7f6f760b');
  });

  it('prunes latch once server job_busy true catches up', () => {
    const beats = [{
      beat_id: 'bg_arc1_event3_pre_beat_03',
      job_busy: true,
      o3_current_job_id: '7f6f760b',
    }];
    const latch = { bg_arc1_event3_pre_beat_03: '7f6f760b' };
    const pruned = pruneSubmitPollLatch(beats, latch);
    assert.equal(pruned.bg_arc1_event3_pre_beat_03, undefined);
  });

  it('beatO3GenerateInFlight true when poll latch set but job_busy false', () => {
    const beat = { beat_id: 'bg_arc1_event3_pre_beat_03', job_busy: false };
    assert.equal(
      beatO3GenerateInFlight('bg_arc1_event3_pre_beat_03', beat, {
        o3SubmitPending: {},
        activeO3Jobs: {},
        submitPollLatch: { bg_arc1_event3_pre_beat_03: '7f6f760b' },
      }),
      true,
    );
  });

  it('submit pending shows busy even when session job_busy is false', () => {
    const beat = { beat_id: 'bg_arc1_event3_pre_beat_02', job_busy: false };
    assert.equal(beatO3JobBusy(beat, true), true);
    assert.equal(beatO3JobBusy(beat, false), false);
  });

  it('server flight guard ignores submit pending latch', () => {
    const beat = { beat_id: 'bg_arc1_event3_pre_beat_02', job_busy: false };
    assert.equal(
      beatO3ServerJobInFlight('bg_arc1_event3_pre_beat_02', beat, {
        activeO3Jobs: {},
        submitPollLatch: {},
      }),
      false,
    );
  });
});

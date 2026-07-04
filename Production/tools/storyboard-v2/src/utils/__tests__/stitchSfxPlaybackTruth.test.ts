import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  isStitchMuxPlaybackUrl,
  resolveSlotPlaybackPreviewUrl,
  stitchSlotTimelineDurMs,
} from '../stitchJobMediaHydrate.ts';

describe('STITCH_SFX_PLAYBACK_TRUTH_V1', () => {
  it('SFX slot with no mux artifact returns undefined (not dry /files)', () => {
    const slot = {
      video_path: 'Production/Milestones/milestone1_arc1/assembled/standalone_kling_o3_test.mp4',
      sfx_cues: [{ id: 'c1', offset_ms: 79000, duration_ms: 3000, source_path: '/x/sfx.mp3' }],
    };
    const url = resolveSlotPlaybackPreviewUrl('milestone:milestone1_arc1', 'standalone', slot, {});
    assert.equal(url, undefined);
  });

  it('speech-only slot still resolves dry /files', () => {
    const slot = {
      video_path: 'Production/Event_2/assembled/intro_kling_o3_test.mp4',
      sfx_cues: [],
    };
    const url = resolveSlotPlaybackPreviewUrl('Event_2', 'intro', slot, {});
    assert.match(url ?? '', /\/files\?path=/);
  });

  it('four-files SFX slot resolves dry_export_path for live client mix (not stale playback bake)', () => {
    const slot = {
      video_path: 'Production/Event_3/assembled/resolution_playback_20260703T175619Z.mp4',
      dry_export_path: 'Production/Event_3/assembled/resolution_kling_o3_20260703T175509Z.mp4',
      playback_recipe_version: 'STITCH_FOUR_FILES_V1',
      sfx_cues: [{ id: 'c1', offset_ms: 19000, duration_ms: 3000, source_path: '/x/sfx.mp3' }],
    };
    const url = resolveSlotPlaybackPreviewUrl('Event_3', 'resolution', slot, {});
    assert.match(url ?? '', /resolution_kling_o3_20260703T175509Z\.mp4/);
    assert.doesNotMatch(url ?? '', /resolution_playback_/);
  });

  it('ambient-only slot resolves dry /files until ambient mix is baked', () => {
    const slot = {
      video_path: 'Production/Milestones/milestone1_arc1/assembled/standalone_kling_o3_test.mp4',
      ambient_bed: 'Intro video ambient bed',
      sfx_cues: [],
    };
    const url = resolveSlotPlaybackPreviewUrl('milestone:milestone1_arc1', 'standalone', slot, {});
    assert.match(url ?? '', /\/files\?path=/);
  });

  it('isStitchMuxPlaybackUrl detects preview_file URLs', () => {
    assert.equal(
      isStitchMuxPlaybackUrl('http://localhost:5112/api/stitch_editor/preview_file/abc123'),
      true,
    );
    assert.equal(
      isStitchMuxPlaybackUrl('http://localhost:5112/files?path=Production%2FEvent_2%2Fx.mp4'),
      false,
    );
  });

  it('stitchSlotTimelineDurMs prefers mux_preview_duration_ms then video_dur_ms', () => {
    assert.equal(
      stitchSlotTimelineDurMs({ mux_preview_duration_ms: 94000, video_dur_ms: 80000 }),
      94000,
    );
    assert.equal(stitchSlotTimelineDurMs({ video_dur_ms: 94100 }), 94100);
  });
});

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { resolvePersistedPlaybackFromArtifacts, resolveDrySlotSourceVideoUrl, resolveSlotPlaybackPreviewUrl } from '../stitchJobMediaHydrate.ts';

describe('resolvePersistedPlaybackFromArtifacts', () => {
  it('ambient-only slot uses mux_preview when ambient_mix_hash absent', () => {
    const slot = {
      video_path: 'Production/Event_2/preview/phase_a/foo.mp4',
      mux_video_path: 'Production/Event_2/preview/phase_a/foo.mp4',
      mux_preview_hash: '6ff62c2141e0',
      _mux_preview_url: 'http://localhost:5112/api/stitch_editor/preview_file/6ff62c2141e0',
      ambient_bed: 'ambient bed pretty option2',
      ambient_volume: 0.15,
      sfx_cues: [],
    };
    const url = resolvePersistedPlaybackFromArtifacts(slot);
    assert.match(url ?? '', /6ff62c2141e0/);
  });

  it('speech-only slot resolves Production path via /files', () => {
    const url = resolveDrySlotSourceVideoUrl(
      'Production/Event_2/assembled/intro_kling_o3_test.mp4',
    );
    assert.match(url ?? '', /\/files\?path=Production%2FEvent_2%2Fassembled%2Fintro_kling_o3_test\.mp4/);
  });

  it('STITCH_SFX_PLAYBACK_TRUTH_V1 — SFX slot with no mux returns undefined', () => {
    const slot = {
      video_path: 'Production/Event_2/assembled/intro_kling_o3_20260622T230816Z.mp4',
      ambient_bed: 'Intro video ambient bed',
      ambient_volume: 0.15,
      sfx_cues: [{ id: 'whoosh', offset_ms: 173000, duration_ms: 3000, source_path: '/x/sfx.mp3' }],
    };
    const url = resolveSlotPlaybackPreviewUrl('Event_2', 'intro', slot, {});
    assert.equal(url, undefined);
  });

  it('STITCH_AMBIENT_LOOP_XFADE_V1 — rejects stale previewUrls when mux hash drifted', () => {
    const slot = {
      video_path: 'Production/Event_4/assembled/intro_kling_o3_test.mp4',
      mux_video_path: 'Production/Event_4/assembled/intro_kling_o3_test.mp4',
      mux_preview_hash: '85646d0ff84b',
      ambient_bed: 'Intro video ambient bed',
      ambient_volume: 0.15,
      sfx_cues: [{ id: 'whoosh', offset_ms: 1000, source_path: '/x/sfx.mp3' }],
    };
    const stalePreviewUrls = {
      intro: 'http://localhost:5114/api/stitch_editor/preview_file/deadbeef0001',
    };
    const url = resolveSlotPlaybackPreviewUrl('Event_4', 'intro', slot, stalePreviewUrls);
    assert.equal(url, undefined);
  });
});

describe('STITCH_STANDALONE_DRY_VIDEO_V1', () => {
  it('milestone standalone slot resolves dry /files without Review previewUrls', async () => {
    const { resolveStandaloneStitchSlotVideoUrl } = await import('../stitchModulePreview.ts');
    const slot = {
      video_path: 'Production/Milestones/milestone1_arc1/assembled/standalone_kling_o3_20260625T233953Z.mp4',
      ambient_bed: 'Intro video ambient bed',
      ambient_volume: 0.15,
      sfx_cues: [],
    };
    const url = resolveStandaloneStitchSlotVideoUrl({ eventId: 'Event_2', slot, previewUrls: {} });
    assert.match(
      url ?? '',
      /\/files\?path=Production%2FMilestones%2Fmilestone1_arc1%2Fassembled%2Fstandalone_kling_o3_20260625T233953Z\.mp4/,
    );
  });
});

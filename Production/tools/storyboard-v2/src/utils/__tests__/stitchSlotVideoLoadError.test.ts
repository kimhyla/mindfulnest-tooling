import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  STITCH_DRY_MEDIA_FAIL_LOUD_V1,
  formatStitchSlotVideoLoadError,
  mediaErrorCodeName,
  resolveActiveSlotVideoError,
  stitchDryMediaLikelyFileProviderFailure,
  stitchMediaLeafFromPathOrUrl,
} from '../stitchSlotVideoLoadError.ts';

describe('stitchSlotVideoLoadError — STITCH_DRY_MEDIA_FAIL_LOUD_V1', () => {
  it('exports contract marker', () => {
    assert.equal(STITCH_DRY_MEDIA_FAIL_LOUD_V1, 'STITCH_DRY_MEDIA_FAIL_LOUD_V1');
  });

  it('names MEDIA_ERR codes', () => {
    assert.equal(mediaErrorCodeName(4), 'MEDIA_ERR_SRC_NOT_SUPPORTED');
    assert.equal(mediaErrorCodeName(2), 'MEDIA_ERR_NETWORK');
  });

  it('extracts leaf from Production path and /files URL', () => {
    assert.equal(
      stitchMediaLeafFromPathOrUrl(
        'Production/Event_3/assembled/intro_kling_o3_20260704T021028Z.mp4',
      ),
      'intro_kling_o3_20260704T021028Z.mp4',
    );
    assert.equal(
      stitchMediaLeafFromPathOrUrl(
        'http://127.0.0.1:5113/files?path=Production%2FEvent_3%2Fassembled%2Fresolution_kling_o3_x.mp4&v=1',
      ),
      'resolution_kling_o3_x.mp4',
    );
  });

  it('flags Format/Network as File Provider class', () => {
    assert.equal(stitchDryMediaLikelyFileProviderFailure(4), true);
    assert.equal(stitchDryMediaLikelyFileProviderFailure(2), true);
    assert.equal(stitchDryMediaLikelyFileProviderFailure(3), false);
  });

  it('fail-loud dry message includes slot, leaf, and Dropbox guidance', () => {
    const msg = formatStitchSlotVideoLoadError({
      slotKey: 'intro',
      mediaErrorCode: 4,
      mediaErrorMessage: 'Format error',
      dryExportPath: 'Production/Event_3/assembled/intro_kling_o3_20260704T021028Z.mp4',
    });
    assert.match(msg, /intro video failed to load/);
    assert.match(msg, /MEDIA_ERR_SRC_NOT_SUPPORTED/);
    assert.match(msg, /intro_kling_o3_20260704T021028Z\.mp4/);
    assert.match(msg, /Dropbox File Provider/);
    assert.match(msg, /Retry/);
  });

  it('mux failure path keeps Review rebuild guidance', () => {
    const msg = formatStitchSlotVideoLoadError({
      slotKey: 'phase_b',
      mediaErrorCode: 4,
      usingMux: true,
      videoPath: 'Production/Event_3/assembled/phase_b_playback_x.mp4',
    });
    assert.match(msg, /SFX mix preview failed/);
    assert.match(msg, /Review/);
  });

  it('resolveActiveSlotVideoError prefers cached banner over remint', () => {
    assert.equal(
      resolveActiveSlotVideoError({
        slotKey: 'resolution',
        cachedError: 'cached loud banner',
        video: null,
      }),
      'cached loud banner',
    );
  });

  it('resolveActiveSlotVideoError mints from video.error when cache empty', () => {
    const video = {
      error: { code: 4, message: 'Format error' },
      currentSrc:
        'http://127.0.0.1:5113/files?path=Production%2FEvent_3%2Fassembled%2Fresolution_kling_o3_x.mp4',
      src: '',
    } as unknown as HTMLVideoElement;
    const msg = resolveActiveSlotVideoError({
      slotKey: 'resolution',
      cachedError: null,
      video,
      dryExportPath: 'Production/Event_3/assembled/resolution_kling_o3_x.mp4',
    });
    assert.ok(msg);
    assert.match(msg!, /resolution video failed/);
    assert.match(msg!, /Dropbox File Provider/);
  });

  it('resolveActiveSlotVideoError returns null when healthy', () => {
    assert.equal(
      resolveActiveSlotVideoError({
        slotKey: 'intro',
        cachedError: null,
        video: { error: null } as unknown as HTMLVideoElement,
      }),
      null,
    );
  });
});

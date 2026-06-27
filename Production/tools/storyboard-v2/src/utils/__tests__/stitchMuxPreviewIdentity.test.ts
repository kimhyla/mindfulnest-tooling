import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  extractMuxPreviewHash,
  muxPreviewSameIdentity,
  shouldUpdateComposerMuxSrc,
  STITCH_MUX_SRC_IDENTITY_V1,
} from '../stitchMuxPreviewIdentity.ts';

describe('stitchMuxPreviewIdentity', () => {
  const a = 'http://localhost:5112/api/stitch_editor/preview_file/54ce49736a79';
  const b = 'http://localhost:5112/api/stitch_editor/preview_file/54ce49736a79?ts=1';
  const c = 'http://localhost:5112/api/stitch_editor/preview_file/abc123def456';

  it('exports contract marker', () => {
    assert.equal(STITCH_MUX_SRC_IDENTITY_V1, 'STITCH_MUX_SRC_IDENTITY_V1');
  });

  it('extracts mux hash from preview_file URLs', () => {
    assert.equal(extractMuxPreviewHash(a), '54ce49736a79');
    assert.equal(extractMuxPreviewHash(b), '54ce49736a79');
    assert.equal(extractMuxPreviewHash(undefined), undefined);
  });

  it('treats same-hash URLs as same identity', () => {
    assert.equal(muxPreviewSameIdentity(a, b), true);
    assert.equal(muxPreviewSameIdentity(a, c), false);
  });

  it('allows first bind always', () => {
    assert.equal(shouldUpdateComposerMuxSrc(undefined, a, 'quiet_rebuild'), true);
  });

  it('allows quiet rebuild src swap when mux hash changed (new ambient/SFX mix)', () => {
    assert.equal(shouldUpdateComposerMuxSrc(a, c, 'quiet_rebuild'), true);
  });

  it('blocks quiet rebuild when mux hash unchanged (no reload flicker)', () => {
    assert.equal(shouldUpdateComposerMuxSrc(a, a, 'quiet_rebuild'), false);
    assert.equal(shouldUpdateComposerMuxSrc(a, b, 'quiet_rebuild'), false);
  });

  it('blocks same-identity swap for all intents', () => {
    assert.equal(shouldUpdateComposerMuxSrc(a, b, 'explicit_preview'), false);
    assert.equal(shouldUpdateComposerMuxSrc(a, b, 'hydrate'), false);
  });

  it('allows explicit preview when hash changes', () => {
    assert.equal(shouldUpdateComposerMuxSrc(a, c, 'explicit_preview'), true);
    assert.equal(shouldUpdateComposerMuxSrc(a, c, 'hydrate'), true);
  });
});

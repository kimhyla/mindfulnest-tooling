import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  STITCH_SFX_FETCH_MAX_ATTEMPTS,
  fetchStitchSfxArrayBuffer,
  stitchSfxFetchIsRetryableStatus,
  stitchSfxFetchRetryDelayMs,
} from '../stitchSfxFetch.ts';

describe('STITCH_SFX_HOT_SERVE_PREFETCH_V1 fetch', () => {
  it('retries 503 then returns bytes', async () => {
    let calls = 0;
    const fetchImpl = async () => {
      calls += 1;
      if (calls < 3) {
        return new Response(JSON.stringify({ error_code: 'HOT_SERVE_MATERIALIZE_FAILED' }), {
          status: 503,
        });
      }
      return new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 });
    };
    const buf = await fetchStitchSfxArrayBuffer('http://localhost/files?path=x', fetchImpl as typeof fetch);
    assert.equal(calls, 3);
    assert.equal(buf.byteLength, 4);
  });

  it('does not retry permanent 404', async () => {
    let calls = 0;
    const fetchImpl = async () => {
      calls += 1;
      return new Response('missing', { status: 404 });
    };
    await assert.rejects(
      () => fetchStitchSfxArrayBuffer('http://localhost/files?path=x', fetchImpl as typeof fetch),
      /HTTP 404/,
    );
    assert.equal(calls, 1);
  });

  it('retry helper marks 503/429 only', () => {
    assert.equal(stitchSfxFetchIsRetryableStatus(503), true);
    assert.equal(stitchSfxFetchIsRetryableStatus(429), true);
    assert.equal(stitchSfxFetchIsRetryableStatus(404), false);
    assert.equal(stitchSfxFetchRetryDelayMs(0), 200);
    assert.equal(STITCH_SFX_FETCH_MAX_ATTEMPTS, 4);
  });
});

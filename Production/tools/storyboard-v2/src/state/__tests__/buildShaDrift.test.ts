// BUILD_SHA_DRIFT_V1 — zero-dep unit tests.
// Run: cd storyboard-v2 && node --experimental-strip-types --test src/state/__tests__/buildShaDrift.test.ts

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseBuildShaFromHtml,
  readBuildShaMetaContent,
  buildShaDriftDetected,
} from '../buildShaMeta.ts';

describe('buildShaMeta', () => {
  it('parseBuildShaFromHtml extracts meta content', () => {
    const html = '<html><head><meta name="build-sha" content="abc1234"></head></html>';
    assert.equal(parseBuildShaFromHtml(html), 'abc1234');
  });

  it('readBuildShaMetaContent reads document meta', () => {
    const doc = {
      querySelector: (sel: string) => {
        if (sel.includes('build-sha')) {
          return { getAttribute: (n: string) => (n === 'content' ? 'deadbeef' : null) };
        }
        return null;
      },
    };
    assert.equal(readBuildShaMetaContent(doc), 'deadbeef');
  });

  it('buildShaDriftDetected true when shas differ', () => {
    assert.equal(buildShaDriftDetected('oldsha1', 'newsha2'), true);
  });

  it('buildShaDriftDetected false when shas match', () => {
    assert.equal(buildShaDriftDetected('same', 'same'), false);
  });

  it('buildShaDriftDetected false for missing or placeholder shas', () => {
    assert.equal(buildShaDriftDetected('', 'abc'), false);
    assert.equal(buildShaDriftDetected('?', 'abc'), false);
  });
});

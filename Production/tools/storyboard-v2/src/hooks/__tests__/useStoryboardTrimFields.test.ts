import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergeOperatorFieldOnHydrate } from '../../utils/operatorEditMerge.ts';

/** SB-TRIM-HYDRATE-1 — poll must not clobber LD-756 trim draft while editing. */
function mergeTrimOnHydrate(local: string, server: string, editing: boolean): string {
  return mergeOperatorFieldOnHydrate(local, server, { patchInFlight: editing }) ?? server;
}

describe('SB-TRIM-HYDRATE-1 — useStoryboardTrimFields hydrate contract', () => {
  it('omitted server field keeps local trim front draft', () => {
    assert.equal(mergeTrimOnHydrate('2.50', undefined as unknown as string, false), '2.50');
  });

  it('editing keeps local trim front draft over server', () => {
    assert.equal(mergeTrimOnHydrate('2.50', '0.0', true), '2.50');
  });

  it('idle adopts server trim when present', () => {
    assert.equal(mergeTrimOnHydrate('2.50', '1.25', false), '1.25');
  });
});

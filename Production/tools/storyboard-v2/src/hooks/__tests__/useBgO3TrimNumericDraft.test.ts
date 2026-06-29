import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mergeOperatorFieldOnHydrate } from '../../utils/operatorEditMerge.ts';

/** Contract for BG-O3-TRIM-HYDRATE-1 — poll must not clobber dirty trim draft. */
function mergeTrimDraftOnHydrate(
  local: string,
  server: string,
  editing: boolean,
): string {
  return mergeOperatorFieldOnHydrate(local, server, { patchInFlight: editing }) ?? server;
}

describe('useBgO3TrimNumericDraft hydrate contract', () => {
  it('idle server trim wins over local', () => {
    assert.equal(mergeTrimDraftOnHydrate('1.5', '0.0', false), '0.0');
  });

  it('editing keeps local trim draft', () => {
    assert.equal(mergeTrimDraftOnHydrate('1.5', '0.0', true), '1.5');
  });
});

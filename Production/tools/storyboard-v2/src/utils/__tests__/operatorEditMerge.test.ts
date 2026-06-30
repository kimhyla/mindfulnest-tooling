import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  mergeOperatorArrayOnHydrate,
  mergeOperatorFieldOnHydrate,
  OPERATOR_EDIT_AUTHORITY_V1,
} from '../operatorEditMerge.ts';

describe('OPERATOR_EDIT_AUTHORITY_V1', () => {
  it('exports marker', () => {
    assert.equal(OPERATOR_EDIT_AUTHORITY_V1, 'OPERATOR_EDIT_AUTHORITY_V1');
  });

  it('mergeOperatorFieldOnHydrate — patch in flight keeps local', () => {
    assert.equal(
      mergeOperatorFieldOnHydrate('local', 'server', { patchInFlight: true }),
      'local',
    );
  });

  it('mergeOperatorFieldOnHydrate — server present wins when idle', () => {
    assert.equal(
      mergeOperatorFieldOnHydrate('local', 'server', { patchInFlight: false }),
      'server',
    );
    assert.equal(
      mergeOperatorFieldOnHydrate(5, 0, { patchInFlight: false }),
      0,
    );
  });

  it('mergeOperatorFieldOnHydrate — omitted server keeps local', () => {
    assert.equal(
      mergeOperatorFieldOnHydrate('local', undefined, { patchInFlight: false }),
      'local',
    );
  });

  it('mergeOperatorArrayOnHydrate — omitted server keeps local cues', () => {
    const local = [{ id: 'a' }];
    const merged = mergeOperatorArrayOnHydrate(local, undefined, { patchInFlight: false });
    assert.deepEqual(merged, [{ id: 'a' }]);
  });

  it('mergeOperatorArrayOnHydrate — empty server clears when idle', () => {
    const merged = mergeOperatorArrayOnHydrate([{ id: 'a' }], [], { patchInFlight: false });
    assert.deepEqual(merged, []);
  });
});

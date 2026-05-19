// LD-778 expectField unit tests — Node built-in test runner (no Vitest/Jest).
// Orchestrator / CI: node --experimental-strip-types --test src/api/__tests__/expectField.test.ts
// (from storyboard-v2/; requires Node 22+ strip-types or pre-compile via tsc)

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { expectField, type ExpectFieldSpec } from "../expectFieldGate.ts";;

describe('expectField', () => {
  it('returns ok for empty specs', () => {
    assert.deepEqual(expectField({ a: 1 }, []), { ok: true });
  });

  it('rejects non-object root', () => {
    assert.deepEqual(expectField(null, []), { ok: false, failing: '<root>' });
    assert.deepEqual(expectField('x', []), { ok: false, failing: '<root>' });
    assert.deepEqual(expectField([], []), { ok: false, failing: '<root>' });
  });

  it('type match — string/number/boolean/array/object', () => {
    const data = {
      s: 'hi',
      n: 1,
      b: true,
      a: [1],
      o: { x: 1 },
    };
    const specs: ExpectFieldSpec[] = [
      { key: 's', type: 'string' },
      { key: 'n', type: 'number' },
      { key: 'b', type: 'boolean' },
      { key: 'a', type: 'array' },
      { key: 'o', type: 'object' },
    ];
    assert.deepEqual(expectField(data, specs), { ok: true });
  });

  it('type mismatch reports first failing key', () => {
    const specs: ExpectFieldSpec[] = [
      { key: 'ok', type: 'string' },
      { key: 'bad', type: 'number' },
    ];
    assert.deepEqual(expectField({ ok: 'yes', bad: 'nope' }, specs), {
      ok: false,
      failing: 'bad',
    });
  });

  it('equals match — true/false/string', () => {
    assert.deepEqual(
      expectField({ ok: true, status: 'ok' }, [
        { key: 'ok', equals: true },
        { key: 'status', equals: 'ok' },
      ]),
      { ok: true },
    );
    assert.deepEqual(
      expectField({ ok: false }, [{ key: 'ok', equals: true }]),
      { ok: false, failing: 'ok' },
    );
  });
});

// LD-778 — expectField 4-gate response body validator for runMutation callers.
//
// Extracted from client.ts so it has ZERO module dependencies (no state, no
// scope, no DOM). The test file Production/tools/storyboard-v2/src/api/
// __tests__/expectField.test.ts can `node --experimental-strip-types` this
// file directly without pulling in the rest of the storyboard-v2 module tree
// (state/scope, etc.) that uses bundler-style extensionless imports
// incompatible with Node's strict ESM resolver.
//
// client.ts re-exports both symbols so existing callers (StoryboardTab.tsx's
// runMutation) keep importing from '../api/client'.

export type ExpectFieldSpec =
  | { key: string; type: 'string' | 'number' | 'boolean' | 'object' | 'array' }
  | { key: string; equals: unknown };

export function expectField(
  data: unknown,
  specs: ExpectFieldSpec[],
): { ok: true } | { ok: false; failing: string } {
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return { ok: false, failing: '<root>' };
  }
  const obj = data as Record<string, unknown>;
  for (const spec of specs) {
    const val = obj[spec.key];
    if ('equals' in spec) {
      if (val !== spec.equals) {
        return { ok: false, failing: spec.key };
      }
      continue;
    }
    if (spec.type === 'array') {
      if (!Array.isArray(val)) {
        return { ok: false, failing: spec.key };
      }
    } else if (spec.type === 'object') {
      if (typeof val !== 'object' || val === null || Array.isArray(val)) {
        return { ok: false, failing: spec.key };
      }
    } else if (typeof val !== spec.type) {
      return { ok: false, failing: spec.key };
    }
  }
  return { ok: true };
}

/**
 * OPERATOR_EDIT_AUTHORITY_V1 — canonical client hydration merge for all operator surfaces.
 * Tier C = server owns disk. Tier D = this module owns in-memory edit sessions.
 *
 * Used by: phase watercolor cues, phase stem cut, phase ambient preset, stitch sfx (via
 * specialized wrappers), and any new operator edit surface — never ad-hoc slice replace.
 */
export const OPERATOR_EDIT_AUTHORITY_V1 = 'OPERATOR_EDIT_AUTHORITY_V1';

export interface OperatorEditMergeOptions {
  patchInFlight: boolean;
}

/**
 * Scalar / object field merge — server omitted → keep local; server present → server wins when idle.
 */
export function mergeOperatorFieldOnHydrate<T>(
  local: T | undefined,
  server: T | undefined,
  opts: OperatorEditMergeOptions,
): T | undefined {
  if (opts.patchInFlight) return local;
  if (server !== undefined) return server;
  return local;
}

/**
 * Array field merge (e.g. watercolor cues, sfx_cues geometry arrays).
 * Empty server array is explicit clear when idle.
 */
export function mergeOperatorArrayOnHydrate<T>(
  local: readonly T[],
  server: T[] | undefined,
  opts: OperatorEditMergeOptions,
): T[] {
  if (opts.patchInFlight) return [...local];
  if (server !== undefined) return server;
  if (local.length > 0) return [...local];
  return [];
}

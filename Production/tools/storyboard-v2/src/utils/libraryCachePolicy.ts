/** LIBRARY_CLIENT_CACHE_COHERENCE_V2 — server-authoritative list + tagged optimistic overlay.
 *  LIBRARY_CLIENT_CACHE_COHERENCE_V1 — legacy marker retained for closure grep (session-only bust). */

export const LIBRARY_ITEMS_SESSION_KEY = 'mn.library.items.v5';

export interface LibraryOptimisticRow {
  key?: string;
  /** True only for rows inserted client-side before server refetch confirms the key. */
  _libraryOptimistic?: boolean;
}

export function libraryItemsStorageKey(eventId: string): string {
  return `${LIBRARY_ITEMS_SESSION_KEY}:${eventId}`;
}

export function invalidateLibrarySessionCache(eventId: string): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.removeItem(libraryItemsStorageKey(eventId));
  } catch {
    /* best effort */
  }
}

export function libraryRefetchCacheBustParam(): string {
  return String(Date.now());
}

export function isLibraryOptimisticPending(row: LibraryOptimisticRow): boolean {
  return row._libraryOptimistic === true;
}

export function markLibraryOptimistic<T extends { key?: string }>(
  row: T,
): T & { _libraryOptimistic: true } {
  return { ...row, _libraryOptimistic: true };
}

export function stripLibraryOptimisticFlag<T extends LibraryOptimisticRow>(row: T): T {
  if (!isLibraryOptimisticPending(row)) return row;
  const { _libraryOptimistic: _drop, ...rest } = row;
  return rest as T;
}

/** Rows safe to persist in sessionStorage — never store unconfirmed optimistic overlay. */
export function itemsForLibrarySessionPersist<T extends LibraryOptimisticRow>(items: T[]): T[] {
  return items
    .filter((row) => !isLibraryOptimisticPending(row))
    .map((row) => stripLibraryOptimisticFlag(row));
}

/** Keep tagged optimistic rows until server confirms the same key; drop all other client-only rows. */
export function mergeLibraryRefetchWithOptimistic<T extends LibraryOptimisticRow>(
  serverItems: T[],
  clientItems: T[],
): T[] {
  const serverKeys = new Set(serverItems.map((row) => String(row.key ?? '')));
  const pending = clientItems.filter((row) => {
    if (!isLibraryOptimisticPending(row)) return false;
    const key = String(row.key ?? '');
    return key && !serverKeys.has(key);
  });
  const confirmedServer = serverItems.map((row) => stripLibraryOptimisticFlag(row));
  if (!pending.length) return confirmedServer;
  const merged = [...pending, ...confirmedServer];
  const seen = new Set<string>();
  const out: T[] = [];
  for (const row of merged) {
    const key = String(row.key ?? '');
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(serverKeys.has(key) ? stripLibraryOptimisticFlag(row) : row);
  }
  return out;
}

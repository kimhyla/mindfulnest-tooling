/** LIBRARY_CLIENT_CACHE_COHERENCE_V1 — unified mutation → cache bust → refetch merge. */

export const LIBRARY_ITEMS_SESSION_KEY = 'mn.library.items.v4';

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

/** Keep optimistic rows until server confirms the same key. */
export function mergeLibraryRefetchWithOptimistic<T extends { key?: string }>(
  serverItems: T[],
  optimisticItems: T[],
): T[] {
  const serverKeys = new Set(serverItems.map((row) => String(row.key ?? '')));
  const pending = optimisticItems.filter((row) => {
    const key = String(row.key ?? '');
    return key && !serverKeys.has(key);
  });
  if (!pending.length) return serverItems;
  const merged = [...pending, ...serverItems];
  const seen = new Set<string>();
  const out: T[] = [];
  for (const row of merged) {
    const key = String(row.key ?? '');
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}

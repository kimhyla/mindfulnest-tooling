import { describe, expect, it } from 'vitest';
import {
  itemsForLibrarySessionPersist,
  isLibraryOptimisticPending,
  markLibraryOptimistic,
  mergeLibraryRefetchWithOptimistic,
} from '../libraryCachePolicy';

describe('libraryCachePolicy V2', () => {
  it('drops ghost client rows not tagged optimistic on refetch', () => {
    const server = [{ key: 'a' }, { key: 'b' }];
    const client = [
      { key: 'ghost_1' },
      { key: 'ghost_2' },
      { key: 'a' },
    ];
    expect(mergeLibraryRefetchWithOptimistic(server, client).map((r) => r.key)).toEqual(['a', 'b']);
  });

  it('keeps tagged optimistic rows until server confirms key', () => {
    const server = [{ key: 'a' }];
    const client = [markLibraryOptimistic({ key: 'pending_upload' })];
    expect(mergeLibraryRefetchWithOptimistic(server, client).map((r) => r.key)).toEqual([
      'pending_upload',
      'a',
    ]);
  });

  it('clears optimistic flag once server returns the key', () => {
    const server = [{ key: 'pending_upload' }];
    const client = [markLibraryOptimistic({ key: 'pending_upload', tier: 'source' })];
    const merged = mergeLibraryRefetchWithOptimistic(server, client);
    expect(merged).toHaveLength(1);
    expect(isLibraryOptimisticPending(merged[0]!)).toBe(false);
  });

  it('persist helper excludes optimistic rows', () => {
    const rows = [
      { key: 'confirmed' },
      markLibraryOptimistic({ key: 'pending' }),
    ];
    expect(itemsForLibrarySessionPersist(rows).map((r) => r.key)).toEqual(['confirmed']);
  });
});

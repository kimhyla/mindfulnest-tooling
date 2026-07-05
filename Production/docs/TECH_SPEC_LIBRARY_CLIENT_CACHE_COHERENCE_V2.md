# TECH_SPEC — Library Client Cache Coherence V2

**Status:** shipped (replaces session-only V1 bust)  
**Marker:** `LIBRARY_CLIENT_CACHE_COHERENCE_V2`  
**Supersedes:** `LIBRARY_CLIENT_CACHE_COHERENCE_V1` (sessionStorage bust only)

## Problem class (G7 extension)

Library panel treated **all client-only rows** as optimistic pending on refetch. Session cache bust cleared `sessionStorage` but not React state, so ghost tiles (e.g. 91 client vs 47 server) persisted and new uploads were invisible until hard refresh.

## Root cause

Client list = `merge(server_scan, entire_react_prev)` instead of `merge(server_scan, tagged_optimistic_only)`.

## Contract

| Layer | Authority |
|-------|-----------|
| Disk + `GET /api/cr/library` | Truth after refetch |
| `_libraryOptimistic: true` rows | Narrow overlay until server confirms same `key` |
| `sessionStorage` (`mn.library.items.v5`) | Paint cache — **server-confirmed rows only** (no optimistic flag) |

## Mutations

1. **Upload** — prepend row from `cr_upload` response; mark optimistic; refetch; drop flag when key appears on server.
2. **Crop save** — same (existing prepend + optimistic tag).
3. **Delete** — filter local row + refetch (unchanged).
4. **Refetch** — `mergeLibraryRefetchWithOptimistic(server, prev)` merges **only** `_libraryOptimistic` rows from `prev`, never ghost history.

## Verification

- `src/utils/__tests__/libraryCachePolicy.test.ts` — ghost rejection + optimistic retention
- `verify_library_cache_coherence_durability.sh` — structural + vitest
- Playwright `library_cache_coherence.spec.ts` — upload row shape on API (existing gate extended)

# BG_SESSION_RESTART_HYDRATE_V1 — Beat Gen load after server restart

## Problem

After `production_server.py` stops and starts, the storyboard shows:

`Could not load beat state: TypeError: Failed to fetch`

Root cause class: **scoped session hydration races server startup**. A single successful
`/api/event/current` probe is treated as “server ready”, then Beat Gen immediately
force-fetches `/api/bg/session-state` while the listener is still binding, being
preempted by port-guard, or serving O3-blocking work. `apiGet` retries network errors
once (2s); scope reconcile gets ~10s backoff on dedicated ports. `ensureBgSession`
always error-toasts; `refreshBgSession` suppresses transient failures.

## Category fix (this spec)

1. **Stable probe gate** — before `triggerServerRehydrate`, require **2 consecutive**
   successful `/api/event/current` probes with the same backoff schedule as scope
   reconcile (`EVENT_CURRENT_RETRY_DELAYS_MS`).
2. **BG session fetch retry** — `ensureBgSession` fetcher loops through the same
   backoff schedule before surfacing failure (not one 2s `apiGet` retry).
3. **Toast policy** — error toast only when retries are exhausted **and** the tab has
   no cached beats to show (first load / hard failure). Transient network blips during
   restart with cached beats stay silent.
4. **Scope gate** — `ProducerSessionCoordinator` skips session hydration while
   `scopeReady === false` (mutations already gated; reads now aligned).

## Files

| File | Change |
|------|--------|
| `storyboard-v2/src/state/serverRestartHydrate.ts` | Transient error detect, stable probe, retry delays |
| `storyboard-v2/src/utils/bgSessionLoadFailure.ts` | Toast policy for `ensureBgSession` |
| `storyboard-v2/src/state/bgSessionStore.ts` | Retry loop + toast gate |
| `storyboard-v2/src/components/ServerRehydrateWatcher.tsx` | Stable probe before rehydrate tick |
| `storyboard-v2/src/components/ProducerSessionCoordinator.tsx` | `scopeReady` gate |

## Verification

- Unit: `node --experimental-strip-types --test src/state/__tests__/serverRestartHydrate.test.ts src/utils/__tests__/bgSessionLoadFailure.test.ts`
- Deploy: `deploy_storyboard_v59.sh` (or `post_tooling_change_smoke.sh` for Event_2)
- User path: restart server via `POST /api/server/restart`; hard-refresh Beat Gen tab;
  confirm no red toast while beats list remains; `build-sha` matches commit.

## Non-goals

- Does not change ambient bed canonical defaults (see `STITCH_DEFAULT_AMBIENT_BEDS`).
- Does not replace port-guard server-side stability work (complementary).

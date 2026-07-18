# TECH SPEC — PSL_STALE_KEY_HYDRATION_GUARD_V1

**Date:** 2026-07-17
**Status:** SHIPPED (same change as this spec)
**Marker:** `PSL_STALE_KEY_HYDRATION_GUARD_V1`
**Module:** `Production/tools/storyboard-v2/src/state/sessionHydrationAuthority.ts`
**Tests:** `Production/tools/storyboard-v2/src/state/__tests__/sessionHydrationStaleKey.test.ts`
**Deploy gate:** `Production/scripts/verify_psl_stale_key_hydration_durability.sh` (wired into `verify_storyboard_session_durability.sh`)

## 1. Bug (Kim repro, Event_5 :5115, 2026-07-17)

Header Video dropdown + Beat Gen authority badge showed `resolution` (matching
server truth — `/api/video/list` `active_video: "resolution"`), but the beat
list showed the **intro** partition (`bg_arc1_event5_pre_beat_*`) and the URL
still said `?video=intro`.

### Root cause

Producer Session Layer stores cache payloads per key (`Event|role`, etc.) but
hydrated the shared UI signals **last-writer-wins**:

1. Boot on `?video=intro` → coordinator fetches the **intro** partition.
2. `VideoSelector` mounts, adopts server `active_video=resolution` →
   `activeTargetVideo` flips → second fetch for **resolution** starts.
3. Both requests are in flight. If the **intro** response lands last,
   `applySessionPayload` hydrated `bgBeats`/`bgActiveSegment`/`bgActiveKey`
   from the stale intro row. State then **sticks**: `bgActiveKey` pins refresh
   polling to the wrong partition until the operator manually toggles roles.

The same unguarded hydration existed in `mapSessionStore`,
`storyboardSessionStore`, and `stitchJobSessionStore` (event / project-type
switches), including their **error** paths (a stale failing fetch could blank
the live view).

Cousin symptom: `VideoSelector` mount adoption updated the signal but not the
URL `?video=` hint, and kept a local `useState` copy of the role that went
stale when the role changed elsewhere (BG segment dropdown).

## 2. Invariant

> A completed session fetch may write into the shared UI signals **only when
> its cache key equals the key the live scope signals expect at completion
> time**. Stale completions update their own cache row silently.

Authority: `sessionPayloadMayHydrate(completedKey, expectedKeyNow)` plus one
`expected*SessionKeyNow()` helper per store, all in
`sessionHydrationAuthority.ts`. Stores MUST NOT inline their own comparison.

| Store | Guarded paths | Expected key |
|---|---|---|
| `bgSessionStore` | `applySessionPayload` (covers `ensureBgSession` + `refreshBgSession`) | `bgSessionKey(activeScope.event_id, effectiveScopeVideoRole())` |
| `mapSessionStore` | `onSuccess` + `onError` | `mapSessionKey(activeScope.event_id)` |
| `storyboardSessionStore` | `onSuccess` + `onError` | `storyboardSessionKey(event, projectType, milestoneId)` |
| `stitchJobSessionStore` | `onSuccess` + `onError` | `stitchJobSessionKey(event, projectType, milestoneId)` |

Companion fixes (same change):

- `syncUrlVideoParam(role)` in `videoRole.ts` — single URL `?video=` writer;
  called by `setActiveVideoRole` and by `VideoSelector` mount adoption.
- `VideoSelector` renders the role from the `activeVideoRole` signal directly
  (no stale local `useState` copy).

## 3. Non-goals

- No server changes. Server partition routing (LD-474/LD-545) was verified
  correct via live curl on :5115 before this fix.
- No change to cache rows: stale payloads are still cached for instant
  hydration when the operator switches back.
- O3 terminal-outcome toasts still process on stale completions (job
  completion toasts are partition-independent).

## 4. Proof

- Red→green vitest suite `sessionHydrationStaleKey.test.ts` (6 behavior tests,
  golden payload shapes from live :5115 probes):
  1. Boot race repro (stale intro after switch to resolution) — bg store
  2. Reverse direction (stale resolution after switch to intro) — bg store
  3. Stale `refreshBgSession` completion after partition switch — bg store
  4–6. Event-switch stale completions — map / storyboard / stitch stores
- Deploy gate greps marker + authority usage in all four stores and runs the
  vitest suite on every deploy.

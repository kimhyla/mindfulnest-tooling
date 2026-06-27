# TECH_SPEC — Producer Session Layer (PSL) v1

**Status:** Implemented  
**Repos:** `mindfulnest-tooling` → `storyboard-v2`  
**Replaces:** per-tab keepalive hacks (`mn-tab-pane-keepalive` for BG / Map / Storyboard / Stitcher)

## Problem

Tab switching uses conditional render → **unmount**. Producer tabs stored session data in component `useState` and treated **mount = cold start** (`setLoading(true)` + full API fetch). Users saw “Loading beat state…” on every tab switch without browser refresh.

Keepalive (hide DOM instead of unmount) was a **UI-layer patch** — it preserved state but kept heavy DOM, duplicate fetch rules, and inconsistent tab architecture.

## Category fix

**Producer Session Layer:** session data lives **above tabs** in keyed signal stores + a single **ProducerSessionCoordinator** (always mounted). Tabs are **views** that read signals; remount is instant from cache (stale-while-revalidate).

## 3×3 agent / counter debate (decision record)

### Axis 1 — Persistence mechanism

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Keepalive only** | Minimal diff; Stitcher/Phase already use it. | **Rejected** — patches mount lifecycle; memory + poll duplication. |
| **Agent B — React Query / SWR** | Industry SWR pattern. | **Rejected** — new dependency; signals already canonical in scope. |
| **Counter — Signal session stores** | Matches `scope.ts`, `getScopedStore`, no new deps, unit-testable modules. | **Chosen** |

### Axis 2 — What to cache

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — API payloads only** | Beats, map, event state, stitch job JSON. | **Partial** |
| **Agent B — Everything including UI modals** | Single store for all state. | **Rejected** — modal state is ephemeral view state. |
| **Counter — Session + poll orchestration** | Cache API payloads + in-flight job IDs; polls run in coordinator; modals stay local. | **Chosen** |

### Axis 3 — Fetch orchestration

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Per-tab fetch on mount** | Simple components. | **Rejected** — root cause of reload UX. |
| **Agent B — Background refresh on every tab focus** | Always fresh. | **Rejected** — wastes server on rapid tab hopping. |
| **Counter — Coordinator + SWR** | `ensure*` on scope/rehydrate signals; show cache if fresh; background refresh if stale; dedupe in-flight. | **Chosen** |

### Axis 4 — Phase A/B

| Position | Argument | Verdict |
|----------|----------|---------|
| **Agent A — Full PSL for Phase producers now** | Consistency. | **Deferred** — PhaseProducer couples WaveSurfer/video DOM lifecycle; separate spec. |
| **Counter — Keep Phase keepalive** | Documented exception until Phase producer store refactor. | **Chosen** (documented exception) |

## Architecture

```
App
 ├── ServerRehydrateWatcher
 ├── ProducerSessionCoordinator  ← always mounted
 │    ├── ensureBgSession (scope + video_role)
 │    ├── ensureMapSession (event_id)
 │    ├── ensureStoryboardSession (event_id)
 │    └── BgPollCoordinator (GPT/O3/native lipsync polls)
 └── ActivePane (tabs mount/unmount freely)
      ├── BgTab → reads bgSessionStore signals
      ├── Map → mapSessionStore
      ├── Storyboard → storyboardSessionStore
      └── Stitcher → stitchJobSessionStore + existing mux session cache
```

### Cache keys

| Resource | Key |
|----------|-----|
| Beat Gen | `{event_id}|{video_role}` |
| Production Map | `{event_id}` |
| Storyboard | `{event_id}|{project_type}|{milestone_id}` |
| Stitch job | `{event_id}` → job `{event_id}_stitch` |

### Staleness

| Resource | Stale after | Hard refresh trigger |
|----------|-------------|----------------------|
| BG session | 30s | `serverRehydrateTick`, scope/video change |
| Map | 120s | scope change, rehydrate |
| Storyboard | 30s | scope change, rehydrate |
| Stitch job | 30s | `stitcherRefreshTick`, rehydrate |

### Loading UX rule

**Never show full-pane spinner if cached `ready` data exists for the active key.** Background refresh may run silently.

## Files

| File | Role |
|------|------|
| `src/state/sessionCacheCore.ts` | In-flight dedupe, staleness, slice factory |
| `src/state/producerSessionKeys.ts` | Key builders |
| `src/state/bgSessionStore.ts` | BG beats, segments, poll job signals |
| `src/state/mapSessionStore.ts` | Production map |
| `src/state/storyboardSessionStore.ts` | v2 event state |
| `src/state/stitchJobSessionStore.ts` | Stitch job JSON cache |
| `src/components/ProducerSessionCoordinator.tsx` | Scope-driven ensure* |
| `src/components/BgPollCoordinator.tsx` | BG async job polls (survive tab unmount) |

## Verification

- Unit: `src/state/__tests__/producerSessionStore.test.ts` (node:test)
- E2E: `e2e/producer_session_tab_switch.spec.ts` — tab switch without loading spinner
- Deploy: `deploy_storyboard_v59.sh` + build-sha match commit
- Browser: BG → Stitcher → BG on Event_2 `:5112`

## Non-goals (v1)

- Phase A/B producer session store (keepalive retained)
- Moving all BgTab modal UI state to store

# Tech Spec — Event Switch Automation v1

**Marker:** `TECH_SPEC_EVENT_SWITCH_AUTOMATION_v1`  
**Status:** Shipped  
**Related:** `TECH_SPEC_DEDICATED_PORT_EVENT_NAV_v1`, `EVENT_DEDICATED_SERVER_PROVISION_V1`, `BUILD_SHA_DRIFT_V1`

## Problem

Kim must never manually deploy, provision, or hard-refresh when switching events from the Project dropdown or creating a new event. Prior flow required:

1. Manual `deploy_storyboard_v59.sh` fanout before visiting Event_N  
2. Manual click on **Reload for fresh bundle** after deploy  
3. Manual server start for new dedicated ports  

## Zero-touch contract

| Operator action | Automatic server behavior | Automatic client behavior |
|-----------------|---------------------------|---------------------------|
| Select `Event_N` in dropdown (cross-port) | `POST /api/event/provision_server` syncs storyboard bundle + launchd | Navigate to `:511N`; destination serves fresh HTML |
| Create `+ New Event` | `event_create` copies bundle, bootstraps stitch job, starts provision thread | `provisionAndNavigateToDedicatedPortEvent` → dedicated port |
| Deploy while tab open | N/A | `checkBuildShaDriftAndAutoReload` on focus/poll — silent reload once per sha pair |
| Same-port scope (legacy) | `event/load` under lock | Scope refresh via existing load path |

Kim **never** runs terminal for any of the above.

## Server: bundle sync (`EVENT_SWITCH_STORYBOARD_BUNDLE_SYNC_V1`)

Module: `Production/lib/event_storyboard_bundle_sync.py`

- Canonical source: `Production/tools/storyboard-v2/dist/index.html`  
- Target: `{Event_N}/storyboard_v59_prod.html`  
- Called from: `handle_event_create` (force), `handle_event_provision_server` (idempotent, mtime-aware)  
- Response field: `storyboard_bundle_sync` on provision API  

## Client: auto reload on build-sha drift

Module: `storyboard-v2/src/state/buildShaDrift.ts`

- `checkBuildShaDriftAndAutoReload(reason)` — replaces manual banner click  
- Guard: skipped when `navigator.webdriver` (Playwright) or session flag `mn:disable-build-sha-auto-reload`  
- Loop guard: one auto-reload per `bundled → live` pair per tab session  

## Client: dropdown orchestration

Existing (unchanged wiring, now complete end-to-end):

- `ProjectSelector.tsx` → `provisionAndNavigateToDedicatedPortEvent` on cross-port switch  
- `NewEventModal` → `event_create` → `onCreated` → provision + navigate  
- `scopeEventNavigate.ts` → `ensureDedicatedEventServerReady` awaits HTTP ready  

## Durability gate

```bash
bash Production/scripts/verify_event_switch_automation_durability.sh
```

Checks: sync module markers, provision handler wiring, client auto-reload, pytest bundle sync.

## Perf adjunct (`OPERATOR_SESSION_PERF_V1`)

- Lazy `phase_base_clips_list` fetch (picker open only) — `PhaseProducer.tsx`  
- Debounced BG session refresh — `scheduleRefreshBgSession` in `bgSessionStore.ts`  
- Cold-boot budget: 180s aligned with `event_server_provision.DEFAULT_WAIT_SECONDS`  

Gate: `verify_operator_session_perf.sh`

## Out of scope

- Remote/non-Mac provision (launchd only)  
- Auto-deploy on every git commit (deploy remains agent/CI triggered; drift reload closes the gap for open tabs)

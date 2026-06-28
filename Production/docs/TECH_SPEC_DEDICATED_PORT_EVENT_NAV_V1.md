# TECH_SPEC_DEDICATED_PORT_EVENT_NAV_V1

**Status:** Shipped 2026-06-26  
**Amends:** `SCOPE_CLIENT_AUTHORITY_SPEC_v1.md`, `EVENT_DEDICATED_PORT_V1`  
**Marker:** `PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1`

## Problem

Each `Event_N` runs on an immutable dedicated port `5110+N`. `POST /api/event/load` to a different event on that port returns `409 DEDICATED_PORT_PIN_IMMUTABLE`. The Project dropdown still called `loadEvent()`, so Kim saw Event_1 selected while Phase B (and all tabs) kept serving Event_2 data.

A duplicate **EventSelector** in the tab bar repeated the same broken `event/load` path, causing split-scope UI (two dropdowns, one scope chip).

## Category fix

**Cross-event scope change on dedicated ports = navigation, not mutation.**

| User action | Client behavior |
|-------------|-----------------|
| Pick `Event_M` on port `5110+N`, `M ≠ N` | `window.location.assign(http://localhost:5110+M/?event=Event_M&tab=…&video=…)` |
| Pick `Event_N` on port `5110+N` (same event) | Existing no-op / `loadEvent` when switching from milestone |
| Pick non-`Event_<digits>` on dedicated port | `loadEvent` (shared-port / fixture path) |
| Milestone pick | Unchanged — `milestone_load` on current server |

## Components

| File | Role |
|------|------|
| `scopeAuthorityResolve.ts` | Pure `buildDedicatedPortEventUrl`, `resolveEventSwitchMode` |
| `scopeEventNavigate.ts` | `navigateToDedicatedPortEvent`, flash toast via `sessionStorage` |
| `ProjectSelector.tsx` | Calls navigate before `loadEvent` |
| `refreshSignals.ts` | Reads `?tab=` on boot (cross-port tab preservation) |
| `TabBar.tsx` | EventSelector removed — scope chip only |
| `app.tsx` | `consumePortNavToast` on mount |

## URL contract

Cross-port navigation preserves operator context:

```
http://localhost:5111/?event=Event_1&tab=phase_b&video=phase_b
```

- `event` — authoritative event id (required)
- `tab` — optional; restores Beat Gen / Phase B / Stitcher tab on destination
- `video` — optional; restores target video role

## Durability gates

- Unit: `scopeEventNavigate.test.ts` + existing scope authority tests
- Script: `verify_scope_client_authority_durability.sh` greps `PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1`
- Live: `event/load` cross-event → 409 on `:5112`; Project dropdown → `:5111` with correct Phase B lipsync file

## Sibling bugs closed

- ProjectSelector cross-event stale tab content
- EventSelector duplicate scope control (removed from UI)

## Remaining open

- Wrong-port deep link (`?event=Event_1` on `:5112`) still shows ScopeBoundary banner — boot reconcile unchanged
- ProductionMapTab / other surfaces that call `loadEvent` directly without navigate guard (grep if needed)

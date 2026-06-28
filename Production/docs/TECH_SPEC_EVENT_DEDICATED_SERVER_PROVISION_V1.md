# TECH_SPEC_EVENT_DEDICATED_SERVER_PROVISION_V1

**Status:** Shipped 2026-06-26  
**Extends:** `TECH_SPEC_DEDICATED_PORT_EVENT_NAV_V1.md`, `EVENT_DEDICATED_PORT_V1`, `SERVER_LAUNCHD_SINGLE_OWNER_V1`  
**Marker:** `EVENT_DEDICATED_SERVER_PROVISION_V1`

## Problem

`Event_N` → port `5110+N` is wired in the client (`navigateToDedicatedPortEvent`), but **launchd agents are not auto-created** when:

1. `+ New Event` creates `Production/Event_3/` on disk, or
2. An existing folder (e.g. `Event_4`) appears in Project dropdown while `:5114` has no listener.

Kim navigates to the correct URL and gets **connection refused** until an agent runs `start_event_server.sh Event_N` manually.

**Repro evidence (2026-06-26):**

| Check | Result |
|-------|--------|
| `Production/Event_4/` on disk | exists |
| `GET http://localhost:5114/api/event/current` | connection refused (`000`) |
| `:5111`, `:5112` | HTTP 200 |

## 3×3 design debate

### Axis A — Where provisioning runs

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **A1. Sync inside `event_create`** | One round trip | Blocks HTTP 15–45s; create fails if launchd fails | **Reject** |
| **A2. Background thread in `event_create` only** | Fast create response | Race: client navigates before agent ready | **Partial** (kickstart only) |
| **A3. Idempotent `POST /api/event/provision_server` + client wait before navigate** | Clear contract; works for existing Event_4; any port can provision any Event_N | Extra API call | **Adopt** |

### Axis B — Implementation layer

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **B1. Reimplement launchd in Python** | No subprocess | Duplicates `install_production_server_launchagent.sh`; drift | **Reject** |
| **B2. Python wrapper calling existing bash scripts** | Single owner (`start_event_server.sh` path); idempotent plist cmp | Subprocess | **Adopt** |
| **B3. Client calls shell via new operator-only endpoint** | — | Browser cannot shell | **Reject** |

### Axis C — Blast radius

| Risk | Mitigation |
|------|------------|
| Provision while on wrong port kills other event | `ensure_server_port.sh` + port-scoped flock; never `event/load` during provision |
| Concurrent double-provision | Per-port `fcntl` lock in `lib/event_server_provision.py` |
| Non-`Event_<digits>` ids (e.g. `M5E1`) | Skip provision; return `{skipped: true}`; client uses `loadEvent` |
| `Event_0` (milestone folder) | Port 5110 below dedicated range → skip |
| launchd from server process | Same as deploy/start scripts; operator Mac only; log failures, don't roll back disk create |
| 89 events all provisioned at once | Only on explicit create/select; no scan-all loop |

**Decision:** **A3 + B2** — idempotent provision API, Python lib delegates to bash, client awaits `ready` before port navigation; `event_create` fires background provision as kickstart.

## Architecture

```
+ New Event / Project dropdown (Event_N)
        │
        ▼
POST /api/event/provision_server { event_id }
        │  (callable from any live server — e.g. :5111 provisions Event_4)
        ▼
lib/event_server_provision.provision_dedicated_event_server()
        │  per-port flock
        ├─ skip if not Event_<digits>
        ├─ skip if already healthy on :5110+N
        ├─ ensure_server_port.sh
        └─ install_production_server_launchagent.sh
        ▼
wait_for_event_server_http(port, event_id)
        │
        ▼
{ ok, ready, port, bookmark_url }
        │
        ▼
navigateToDedicatedPortEvent()  (existing PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1)
```

## API

### `POST /api/event/provision_server`

**Body:** `{ "event_id": "Event_4" }`

**Response 200:**

```json
{
  "ok": true,
  "event_id": "Event_4",
  "port": 5114,
  "bookmark_url": "http://localhost:5114/?event=Event_4",
  "ready": true,
  "skipped": false,
  "already_running": false
}
```

**Skipped (non-dedicated id):** `{ "ok": true, "skipped": true, "reason": "not_dedicated_event" }`

**Failure:** 503 `{ "ok": false, "error_code": "EVENT_SERVER_PROVISION_FAILED", ... }`

## Client

- `ensureDedicatedEventServerReady(eventId)` in `scopeEventNavigate.ts` — calls provision API before `navigateToDedicatedPortEvent`.
- Toast: "Starting Event_4 server on port 5114…" while waiting.
- `ProjectSelector`: event pick + `+ New Event` onCreated await provision then navigate.

## Durability gates

- Unit: `test_event_server_provision.py` (port map, skip rules, lock idempotency with mocked subprocess)
- Script: `verify_event_server_provision_durability.sh`
- Live: cold `:5114` → provision → HTTP 200 + `/api/event/current` event_id match
- Browser: dropdown Event_4 on `:5112` → lands on `:5114` with scope chip

## Out of scope

- Auto-provision on deploy fanout for all `Event_*` dirs (would start N agents every deploy)
- Remote/cloud servers (launchd is local Mac operator machine)

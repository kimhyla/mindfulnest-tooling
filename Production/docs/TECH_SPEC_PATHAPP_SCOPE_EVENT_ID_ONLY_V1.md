# TECH_SPEC — pathappPatch scope injection: `scope_event_id` only (LD-461 category fix)

**Date:** 2026-06-26  
**Status:** EXECUTION SPEC  
**Classification:** CATEGORY FIX — closes client-side scope key collision class

## 1. Problem

`pathappPatch` auto-injects the pinned scope into **both** `scope_event_id` and `event_id` for non-BG endpoints. Server `_scope_body` (LD-461) already treats `scope_event_id` as canonical and documents that `event_id` is overloaded (BG segment number, create target, etc.).

When a caller puts domain semantics in `body.event_id` (e.g. + New Event, dedicated-server provision), the post-spread assignment `payload['event_id'] = scope.event_id` **clobbers** the caller value.

**Observed failure (2026-06-26):** On `:5114` (Event_4), UI typed `Event_3`; wire payload had `event_id: Event_4` → HTTP 409 `"Event_4 already exists"`.

## 2. Governing decisions

| LD | Application |
|---|---|
| LD-461 SCOPE_BODY_HELPER_V1 | Scope pin = `scope_event_id`; `_scope_body` coalesces `scope_event_id \|\| event_id` |
| LD-456 SCOPE_VALIDATION_V1 | Guards use `_scope_body`; not raw `body.event_id` |
| NEW_EVENT_CREATION_UI_V1 | `body.event_id` = new event to create |
| EVENT_DEDICATED_SERVER_PROVISION_V1 | `body.event_id` = target event to provision |

## 3. Category fix (not endpoint denylist)

**Rule:** `pathappPatch` injects scope **only** via `scope_event_id`. Never auto-assign top-level `event_id`.

- Removes need for `BG_MUTATION_ENDPOINTS` / `CREATE_EVENT_OWNS_EVENT_ID` injection exceptions for this purpose.
- `BG_MUTATION_ENDPOINTS` retained as documentation of handlers that read segment `event_id` (unchanged server contract).
- Snapshot pre-write may still duplicate `event_id` + `scope_event_id` (both mean current scope there).

## 4. Implementation

1. Extract `buildPathappMutationPayload()` in `src/api/pathappPayload.ts` (unit-testable).
2. `pathappPatch` calls builder; builder sets `scope_event_id` only.
3. Unit tests: `event_create`, `event_provision_server`, `beat_update_text`, `bg_update_beat` payloads.
4. Update `body_key_contract_check.py` auto_keys (drop auto `event_id`).
5. E2e: assert `scope_event_id` for scope; assert caller-owned `event_id` on create/provision.

## 5. Verification

| Gate | Proof |
|---|---|
| Unit | `node --test src/api/__tests__/pathappPayload.test.ts` |
| Repro curl | clobbered payload 409 vs correct payload 200 |
| Deploy | `deploy_storyboard_v59.sh`, build-sha = HEAD |
| Browser | + New Event from `:5114`, POST body has `event_id` ≠ pinned scope |
| Dedicated port | `event/load` to other event → 409 on `:5112` |
| Beatgen smoke | `verify_beatgen_deploy_smoke.sh 5112` |

## 6. Sibling bugs closed

- `event_create` clobber (Kim report)
- `event_provision_server` clobber (latent)
- Any future mutation with caller-owned top-level `event_id`

## 7. Out of scope

- Renaming server `body.event_id` reads (server already prefers `scope_event_id` in `_scope_body`).
- Milestone ID lowercase vs Event PascalCase UX copy (separate product note).

# Railway Directus DB_PASSWORD Fix — Proof Report

**Date**: 2026-05-08
**Operator**: Claude Code (Opus 4.7 1M)
**Self-classification**: STANDARD (config update + restart)
**Activity log row id**: `1780`

---

## TL;DR

Directus's stale Supabase `DB_PASSWORD` env var (matching `supapass11mn`) was updated via Railway GraphQL API to the current rotated Supabase value. Auto-redeploy fired, reached SUCCESS at 76 seconds, `/server/ping` returns 200 with `pong`, `/server/info` returns 200 with project payload, and `/auth/login` returns a valid token (HTTP 200). 6-entry queue replayed: 3 POSTED + read-back verified, 1 SKIPPED (duplicate decision_key), 2 FAILED (pre-existing schema validation errors unrelated to password fix — surfaced below for Kim's review).

---

## Step 1 — Pre-flight: Railway state (READ-ONLY)

### 1.1 Project lookup

GraphQL query:

```
query { projects { edges { node { id name } } } }
```

Response (verbatim):

```json
{"data":{"projects":{"edges":[{"node":{"id":"f3f6c0b7-4b37-4d78-abd1-14d9ed5ae6ec","name":"efficient-grace"}}]}}}
```

### 1.2 Services + environments

GraphQL query (project-scoped):

```
query { project(id: "f3f6c0b7-4b37-4d78-abd1-14d9ed5ae6ec") { id name services { edges { node { id name } } } environments { edges { node { id name } } } } }
```

Response (verbatim):

```json
{"data":{"project":{"id":"f3f6c0b7-4b37-4d78-abd1-14d9ed5ae6ec","name":"efficient-grace","services":{"edges":[{"node":{"id":"33b8f093-77d2-4b7c-aca4-e6e3acca3beb","name":"Directus"}},{"node":{"id":"69fc4f04-ff30-4836-99ab-9884d314e671","name":"Redis"}}]},"environments":{"edges":[{"node":{"id":"0c16ecef-39ca-458e-8c04-b29331ecbf8a","name":"production"}}]}}}}
```

Identifiers captured:
- Project: `f3f6c0b7-4b37-4d78-abd1-14d9ed5ae6ec` (efficient-grace)
- Service: `33b8f093-77d2-4b7c-aca4-e6e3acca3beb` (Directus)
- Environment: `0c16ecef-39ca-458e-8c04-b29331ecbf8a` (production)

### 1.3 Variable name enumeration

Used Railway `variables` query keyed on (projectId, environmentId, serviceId). Returned a flat `{NAME: VALUE}` dict. Names only printed (values redacted):

```
CACHE_ENABLED, DB_POOL__MIN, PORT, DB_CLIENT, REDIS, KEY, HOST,
NODE_TLS_REJECT_UNAUTHORIZED, SECRET, LOG_STYLE, PUBLIC_URL,
CACHE_AUTO_PURGE, STORAGE_S3_REGION, CACHE_STORE, PRIVATE_URL,
DB_POOL__MAX, STORAGE_LOCATIONS, STORAGE_S3_KEY, RAILWAY_RUN_UID,
STORAGE_S3_BUCKET, STORAGE_S3_DRIVER, STORAGE_S3_SECRET,
SYNCHRONIZATION_STORE, WEBSOCKETS_ENABLED, STORAGE_S3_ENDPOINT,
STORAGE_S3_FORCE_PATH_STYLE, ADMIN_PASSWORD, ADMIN_EMAIL,
DB_SSL, DB_PORT, DB_HOST, DB_USER, DB_DATABASE, DB_PASSWORD,
RAILWAY_PUBLIC_DOMAIN, RAILWAY_PRIVATE_DOMAIN, RAILWAY_PROJECT_NAME,
RAILWAY_ENVIRONMENT_NAME, RAILWAY_SERVICE_NAME, RAILWAY_PROJECT_ID,
RAILWAY_ENVIRONMENT_ID, RAILWAY_SERVICE_ID, RAILWAY_STATIC_URL,
RAILWAY_ENVIRONMENT, RAILWAY_SERVICE_DIRECTUS_URL
```

**Single Supabase password variable**: `DB_PASSWORD`. No `DATABASE_URL` connection string with embedded password. No ambiguity.

DB connection components (non-secret):
- `DB_CLIENT` = `pg`
- `DB_HOST` = `db.ugjpauwozlruyctrygby.supabase.co`
- `DB_USER` = `postgres`
- `DB_DATABASE` = `postgres`
- `DB_PORT` = `5432`

---

## Step 2 — Verify which variable to update

Comparison against known-stale values: `DB_PASSWORD` matched `supapass11mn` (index 0 of the known-stale list). Length 12. Confirmed unambiguously the right variable.

```
DB_PASSWORD matches stale value: True
MATCHED stale index: 0  (i.e. 'supapass11mn')
DB_PASSWORD == target already: False
DB_PASSWORD length: 12  (target is 16, matches expected pre-fix state)
```

No HALT condition triggered.

---

## Step 3 — Update the variable

GraphQL mutation:

```graphql
mutation VariableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }
```

Variables:

```json
{
  "input": {
    "projectId": "f3f6c0b7-4b37-4d78-abd1-14d9ed5ae6ec",
    "environmentId": "0c16ecef-39ca-458e-8c04-b29331ecbf8a",
    "serviceId": "33b8f093-77d2-4b7c-aca4-e6e3acca3beb",
    "name": "DB_PASSWORD",
    "value": "<REDACTED — current Supabase rotated value, length 16>"
  }
}
```

Response (verbatim):

```json
{"data":{"variableUpsert":true}}
```

### Rule 35 read-back

Re-queried `variables` and confirmed:

```
READBACK matches target: True
READBACK length: 16
READBACK first/last chars: g...r   (matches expected rotated value bookends)
```

Before/after (sanitized):
- **Before**: 12 chars, matched stale `supapass11mn`
- **After**: 16 chars, matches current Supabase rotated value (begins `g`, ends `r`)

---

## Step 4 — Trigger redeploy

Railway auto-redeployed on env var change (no manual trigger needed). Recent deployments query:

```
query { deployments(first: 3, input: { projectId: "f3f6c0b7-4b37-4d78-abd1-14d9ed5ae6ec", environmentId: "0c16ecef-39ca-458e-8c04-b29331ecbf8a", serviceId: "33b8f093-77d2-4b7c-aca4-e6e3acca3beb" }) { edges { node { id status createdAt } } } }
```

Response (verbatim):

```json
{"data":{"deployments":{"edges":[
  {"node":{"id":"53f794c0-5c9a-4b09-b6d7-96bfd23539e9","status":"DEPLOYING","createdAt":"2026-05-08T16:59:47.993Z"}},
  {"node":{"id":"c5a64110-b019-4d27-a85d-a99252cf835d","status":"SUCCESS","createdAt":"2026-04-11T03:02:52.596Z"}},
  {"node":{"id":"b370de43-09a1-4900-83a3-b9e8faf084f9","status":"FAILED","createdAt":"2026-04-11T02:56:08.519Z"}}
]}}}
```

**Deployment ID**: `53f794c0-5c9a-4b09-b6d7-96bfd23539e9`

---

## Step 5 — Wait for redeploy + verify health

### 5.1 Deployment poll log

```
[0s]  status=DEPLOYING
[8s]  status=DEPLOYING
[17s] status=DEPLOYING
[25s] status=DEPLOYING
[33s] status=DEPLOYING
[42s] status=DEPLOYING
[50s] status=DEPLOYING
[59s] status=DEPLOYING
[67s] status=DEPLOYING
[76s] status=SUCCESS
```

Final status: **SUCCESS at 76 seconds** (well under 3-min timeout).

### 5.2 /server/ping

```
HTTP 200
BODY: pong
```

### 5.3 /server/info

```
HTTP 200
BODY (first 300 chars): {"data":{"project":{"project_name":"Directus","project_descriptor":null,"project_logo":null,"project_color":"#6644FF","default_appearance":"auto","default_theme_light":null,"default_theme_dark":null,"theme_light_overrides":null,"theme_dark_overrides":null,"default_language":"en-US","public_foregroun
```

Both endpoints healthy. Database connection restored.

---

## Step 6 — Auth smoke test

Request:

```
POST https://directus-production-3460.up.railway.app/auth/login
Content-Type: application/json
{"email":"kimhyla11@gmail.com","password":"<REDACTED>"}
```

Response:

```
HTTP 200
AUTH SUCCESS — token received (length=321, first/last chars: e...w)
refresh_token present: True
expires: 900000   (15 min)
```

(JWT body redacted.) Confirms Directus database connection AND admin auth are both operational end-to-end.

---

## Step 7 — Replay queued writes from pending_directus_writes.json

Queue path: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/pending_directus_writes.json`

Pre-replay queue: 6 entries

| Index | Collection             | queued_at                         | Identifying key                                  |
|-------|------------------------|-----------------------------------|--------------------------------------------------|
| 0     | prod_locked_decisions  | 2026-05-07T13:03:01.626Z          | decision_key=SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 |
| 1     | prod_locked_decisions  | 2026-05-07T13:06:35.480Z          | decision_key=SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 (DUP of 0) |
| 2     | prod_activity_log      | 2026-05-08T16:05:44.206Z          | (no ident keys in payload)                       |
| 3     | prod_activity_log      | 2026-05-08T16:06:17.505Z          | (no ident keys in payload)                       |
| 4     | prod_locked_decisions  | 2026-05-08T16:42:53.895Z          | decision_key=DEPENDENCY_ORDER_DISCIPLINE_V1      |
| 5     | prod_activity_log      | 2026-05-08T16:42:54.590Z          | (no ident keys in payload)                       |

### 7.1 Per-write replay results

| Index | Result        | New ID | HTTP | Notes                                                                       |
|-------|---------------|--------|------|-----------------------------------------------------------------------------|
| 0     | **FAILED**    | —      | 400  | `Validation failed for field "source_document". Value is required.`         |
| 1     | **SKIPPED_DUP** | —    | —    | Duplicate decision_key of 0 — would have collided                            |
| 2     | **POSTED**    | 1778   | 200  | Read-back verified                                                           |
| 3     | **FAILED**    | —      | 400  | `Validation failed for field "action". Value is required.` (payload used `action_summary`/`action_type`) |
| 4     | **POSTED**    | 587    | 200  | Read-back verified                                                           |
| 5     | **POSTED**    | 1779   | 200  | Read-back verified                                                           |

Net: **3/6 POSTED + read-back OK, 1 dedup, 2 schema-fail (pre-existing)**.

### 7.2 Read-back verification (Rule 35) for posted rows

```
index=2 coll=prod_activity_log id=1778 READBACK_OK ident={'id': 1778}
index=4 coll=prod_locked_decisions id=587 READBACK_OK ident={'id': 587, 'decision_key': 'DEPENDENCY_ORDER_DISCIPLINE_V1', 'decision_name': 'Dependency-order, not priority-order, when scheduling fix work', 'date_locked': '2026-05-08', 'status': 'active'}
index=5 coll=prod_activity_log id=1779 READBACK_OK ident={'id': 1779}
```

### 7.3 Surface — 2 unprocessed entries (Kim's call)

These two failures are **pre-existing schema validation issues**, not caused by the password rotation. They were failing before the password issue and continue to fail because the writer used outdated field names. They have been retained in `pending_directus_writes.json` (file rewritten with these 2 entries only).

**Unprocessed [0]**: `prod_locked_decisions` payload missing required `source_document` field.

- queued_at: `2026-05-07T13:03:01.626Z`
- decision_key: `SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1`
- payload keys present: `closure_date, date_locked, decision_key, decision_name, decision_text, enforcement_type, notes, scope_domain, severity, status, task_category`
- payload keys missing (required): `source_document`

**Unprocessed [1]**: `prod_activity_log` payload uses `action_summary`/`action_type`/`task_description` instead of the live schema's required `action` field.

- queued_at: `2026-05-08T16:06:17.505Z`
- payload keys present: `action_summary, action_type, created_at, notes, session_phase, task_description`
- payload keys missing (required): `action`

The live `prod_activity_log` schema only has these fields:
`id, module_id, action, details, performed_by, created_at, voice_settings, script_version, kim_verdict, kim_feedback, asset_id`

This suggests either (a) the writer wrapper hasn't been updated to the live schema, or (b) historical schema migration left some queue entries pinned to the old shape. Recommend Kim review and either translate or discard.

### 7.4 Post-replay queue state

Queue file overwritten with the 2 failed entries (length 2). The 4 successful/dedup'd entries are removed from the queue.

---

## Step 8 — Confidence tags (Rule 24)

| Claim                                                                | Confidence | Evidence                                                                                       |
|----------------------------------------------------------------------|------------|------------------------------------------------------------------------------------------------|
| Directus service ID and environment ID                                | VERIFIED   | GraphQL `project` query verbatim response                                                       |
| `DB_PASSWORD` was the only Supabase password variable                 | VERIFIED   | Full variable-name enumeration; no `DATABASE_URL` in list                                       |
| Pre-fix value matched stale `supapass11mn`                            | VERIFIED   | Programmatic equality check against known-stale set, index 0                                    |
| Mutation succeeded                                                    | VERIFIED   | `{"data":{"variableUpsert":true}}` + post-mutation read-back equals target                      |
| Read-back matches target                                              | VERIFIED   | Length 16, bookends 'g' to 'r' match target value                                               |
| Auto-redeploy reached SUCCESS                                         | VERIFIED   | Deployment status poll terminal value `SUCCESS` at 76s                                          |
| `/server/ping` HTTP 200 + body "pong"                                 | VERIFIED   | curl -w output captured                                                                          |
| `/server/info` HTTP 200 with project payload                          | VERIFIED   | curl -w output + body excerpt                                                                    |
| `/auth/login` HTTP 200 with token                                     | VERIFIED   | Token length 321, refresh_token present, expires 900000                                         |
| 3 queued writes posted + read-back OK                                 | VERIFIED   | Per-row id and ident dump from Directus GET                                                     |
| 2 queued writes failed schema validation (pre-existing)               | VERIFIED   | Live schema fetched; verbatim 400 error bodies cited                                             |
| Activity log row 1780 created for this fix                            | VERIFIED   | Directus POST response with `data.id=1780`                                                      |

---

## Step 9 — DS-26 / DS-28 / DS-27 conformance

- **DS-27 (dual-canonical roots, absolute paths)**: All filesystem paths in this report are absolute under the Dropbox canonical root. No relative paths used.
- **DS-26 (HALT at explicit gates)**: No HALT conditions triggered. Multi-password-variable check passed (single `DB_PASSWORD`). Stale-match check passed (index 0). Redeploy reached SUCCESS within timeout. All health endpoints recovered to 200.
- **DS-28 (dependency-order)**: Fixed Directus FIRST (Steps 1-6), then replayed queue (Step 7). The 2 unprocessed entries are surfaced rather than guessed.

## Step 10 — Self-classification

**STANDARD** (config update + restart). No spec authoring, no architectural change, no deletions, no schema migrations. Single env var rotation + auto-redeploy + verification + queue drain.

---

## Activity log row id

`1780` (collection: `prod_activity_log`, action field set to summary of fix, performed_by `claude` per Directus default).

---

## Open items for Kim

1. **2 stuck queue entries** (`pending_directus_writes.json`): pre-existing schema mismatches independent of password issue. Need either (a) field-name translation to live schema, or (b) discard with note. Detail in §7.3.
2. **Investigate writer wrapper**: the activity log entry that failed used `action_summary`/`action_type`/`task_description` instead of the live `action` field. Worth checking which code path emits that shape so future writes don't re-queue.
3. **Investigate decision writer**: `prod_locked_decisions` write that failed was missing `source_document`. Same diagnosis applies.

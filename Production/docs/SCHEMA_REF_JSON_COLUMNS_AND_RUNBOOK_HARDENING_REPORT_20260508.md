# Schema Ref JSON-Column Flag + Runbook Hardening — Proof Report

**Date:** 2026-05-08
**Session author:** claude_code_terminal_session
**Activity log:** prod_activity_log id=1782 (read-back PASS)

---

## What was done

### Fix 1 — JSON-column inventory added to schema reference

**File:** `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §9

Previous §9 was partial (only `agent_advocates`, `agent_counters`, `details` listed; no HTTP 500 warning).

New §9 now contains:
- Hard rule: send native dict/list, not JSON-stringified string
- HTTP 500 confirmation: `prod_activity_log.details` string → 500; dict → 200 (2026-05-08 incident)
- Complete live-schema inventory (queried via `DirectusAdminClient.fields()` 2026-05-08):

| collection | field | type |
|---|---|---|
| prod_locked_decisions | related_files | cast-json |
| prod_locked_decisions | keyword_synonyms | cast-json |
| prod_reference_docs | tags | cast-json |
| prod_preflight_reviews | agent_advocates | cast-json |
| prod_preflight_reviews | agent_counters | cast-json |
| prod_activity_log | details | json (native) — **HTTP 500 if string** |
| prod_activity_log | voice_settings | cast-json |
| prod_modules | session_checklist | cast-json |
| prod_assets | tags | cast-json |

- Highest-risk callout: `prod_activity_log.details` — most-written JSON column; string payload = HTTP 500

---

### Fix 2 — Railway DB_PASSWORD step added to rotation runbook

**File:** `Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md`

Root-cause: Supabase rotation 2026-05-08 left Directus on Railway unreachable for several hours. Railway-hosted Directus stores `DB_PASSWORD` as its own service env var — Doppler update does NOT propagate to Railway automatically. The step was absent from the runbook.

Previous Step 4.3 was titled "Railway (Directus service env vars)" with 4 generic bullet points. No incident note, no API option.

New Step 4.3 now contains:
- `⚠️ CRITICAL — do not skip` header
- Root-cause incident note dated 2026-05-08
- **Option A** — Railway dashboard walkthrough (project: `efficient-grace`, service: Directus, Variables tab → `DB_PASSWORD` → Save → auto-redeploy ~30-60s → curl verify)
- **Option B** — Railway GraphQL API (token from `API_KEYS_MASTER.md` line 70; `variableUpsert` mutation + `serviceInstanceRedeploy` mutation; stub code included)
- §5.4 `consumers_updated` key updated: `railway` → `railway_directus_db_password`
- Change log entry added

---

## Verification

| Check | Result |
|---|---|
| Schema ref §9 multipass read | PASS — all 9 columns present, HTTP 500 note in place |
| Runbook Step 4.3 multipass read | PASS — incident note + Option A + Option B present |
| Activity log POST (id=1782) | HTTP 200, `details` stored as dict |
| Activity log read-back (Rule 35) | PASS — `details` type=dict, 9 json_columns_catalogued, action correct |

---

## Files modified

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — §9 rewritten
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md` — Step 4.3 expanded + §9 change log

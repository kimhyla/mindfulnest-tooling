# Supabase DB Password Rotation Runbook v1

**Authority:** LD `SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1` (this runbook is its `enforcement_artifact_ref`).
**Authored:** 2026-05-08.
**Owner:** Kim. **Operator:** Kim or Claude under explicit direction.
**Audience:** anyone (human or agent) rotating the Supabase Postgres DB password backing the production Directus instance.

---

## 0. What this runbook does

Rotates the Supabase Postgres database password used by Directus (Railway-hosted) and by the daily backup launchd job. Updates every consumer in the right order so no consumer is left holding a stale password.

The Supabase password is the highest-blast-radius secret in the production stack: a stale value silently breaks the daily backup chain and (eventually) Directus itself. Quarterly rotation + drift monitor catch this early.

---

## 1. When to rotate

| Trigger | Cadence | Mode |
|---|---|---|
| Planned hygiene rotation | Quarterly (every 90 days) | Scheduled, off-hours |
| Suspected leak / accidental commit / ex-contractor | Within 24h | Emergency |
| Doppler audit log shows unexpected reads | Within 7 days | Investigation-led |
| Drift monitor surfaces auth-fail (see §6) | Within 24h | Incident |

Quarterly cadence is enforceable via a `scheduled-tasks` MCP entry (template at end of this runbook).

---

## 2. Pre-rotation checklist (do this BEFORE clicking "Reset password")

Identify every consumer. Today (2026-05-08) the canonical consumers are:

- [ ] **Doppler** (`mindfulnest` project, `dev` and `prd` configs) — secret name `SUPABASE_DB_PASSWORD`. Single source of truth post-LD-227 Phase 1.
- [ ] **`Production/API_KEYS_MASTER.md`** line 64 (Infrastructure Credentials table, `**Supabase** | DB Password | \`<value>\``). Transitional fallback per LD-227 SHORTCUT_CREDSTORE_MD_FALLBACK_20260418. Removed by LD-227 Phase 4 — until then, must be kept in sync.
- [ ] **Local launchd / cron** — `Production/scripts/daily_backup.sh` reads from Doppler when `DOPPLER_PROJECT` is set; otherwise reads `SUPABASE_DB_PASSWORD` from env. Both paths land on the same Doppler value if launchd is configured to invoke under `doppler run --`. Verify with `launchctl list | grep mindfulnest` or `crontab -l`.
- [ ] **Railway** — Directus on Railway connects to Supabase via env vars set in the Railway service. Check Railway dashboard → Directus service → Variables: `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (or whatever names that service uses; Directus on Railway typically uses `DB_PASSWORD`).
- [ ] **GitHub Actions** — search workflow YAMLs for `SUPABASE_DB_PASSWORD` references: `grep -r "SUPABASE_DB_PASSWORD" .github/workflows/` in tooling repo. None expected today, but verify before rotation.
- [ ] **Vercel** — N/A today (no Vercel deploy uses Supabase). Re-check before each rotation.
- [ ] **Local dev `.env` files** — `find . -name '.env*' -not -path './node_modules/*' | xargs grep -l SUPABASE 2>/dev/null`. Document each match.
- [ ] **Memory / handoff files** — `grep -rn iXfcu9uDbZElkpl6 ~/.claude/ Production/ 2>/dev/null`. The current value should NOT be quoted in any auto-memory or handoff outside `API_KEYS_MASTER.md` line 64.

If any consumer surfaces that is not in this list, **add it to the list before proceeding** and update this runbook (a `governance_file` LD update qualifies as "small mechanical change", no debate needed).

---

## 3. Rotation steps (Supabase dashboard)

1. Open Supabase dashboard → project `ugjpauwozlruyctrygby` (mindfulnest-production, us-east-1).
2. Settings → Database → Database Password → **Reset password**.
3. Generate a new strong password (Supabase's default generator is fine — 16+ chars, avoid `$` `\`` and other shell-special chars that have historically been mangled by Railway env var passthrough; see the LD-227 historical note about "Railway mangled the `$`").
4. Copy the new value to clipboard. **Do not paste it into chat.**
5. Click **Reset password**. Supabase rotates immediately. Existing connections are NOT killed (they continue with the old auth grant) — but new connections from this point forward require the new value.

---

## 4. Update steps (in this order — order matters)

The order here minimizes the window where any consumer is broken. Doppler first (it is canonical); MD second (fallback path); Railway third (Directus picks up new password on next pod restart, which we trigger explicitly); local backup last (lowest blast radius if it lags by minutes).

### Step 4.1 — Doppler (canonical secret store)

```
doppler secrets set SUPABASE_DB_PASSWORD='<new_value>' --project mindfulnest --config dev
doppler secrets set SUPABASE_DB_PASSWORD='<new_value>' --project mindfulnest --config prd
```

Verify:
```
doppler secrets get SUPABASE_DB_PASSWORD --project mindfulnest --config dev --plain
doppler secrets get SUPABASE_DB_PASSWORD --project mindfulnest --config prd --plain
```

Both must echo the new value.

### Step 4.2 — `Production/API_KEYS_MASTER.md` line 64

Until LD-227 Phase 4 redacts the MD file, the fallback-path value MUST stay in sync. Edit the file:

```
| **Supabase** | DB Password | `<NEW_VALUE>` | Changed YYYY-MM-DD from `<OLD_HINT>` (rotation per SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1). Direct host: `db.ugjpauwozlruyctrygby.supabase.co` |
```

Replace the previous-value reference with a date-stamped note. **Do not commit the new value to git** — `API_KEYS_MASTER.md` is `.gitignore`d in the tooling repo by design. If git complains the file is tracked somewhere, stop and re-check `.gitignore`.

After LD-227 Phase 4 lands and `API_KEYS_MASTER.md` is redacted, this step becomes **delete it from the runbook** — Doppler is the only path. Until then, sync is mandatory.

### Step 4.3 — Railway (Directus `DB_PASSWORD` env var) ⚠️ CRITICAL — do not skip

**Why this step exists:** Supabase rotation silently breaks Directus on Railway because Railway-hosted Directus stores its own copy of `DB_PASSWORD` as a service env var. Doppler update (Step 4.1) does NOT propagate to Railway automatically. Skipping this step leaves Directus unable to connect to Postgres; the failure is silent until the next Directus restart (pod recycle) or cold deploy — which can be hours later.

**Root cause incident:** 2026-05-08 rotation left Directus down for several hours because Step 4.3 was not in the original runbook.

#### Option A — Railway dashboard (recommended for manual rotations)

1. Open Railway dashboard → project `efficient-grace` → service **Directus** → **Variables** tab.
2. Find `DB_PASSWORD` (it is the env var Directus uses to connect to Postgres).
3. Edit its value to the new password. Click **Save**.
4. Railway automatically queues a redeploy. Wait ~30-60s for the new pod to come up.
5. Verify: `curl -s https://directus-production-3460.up.railway.app/server/info | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:', d.get('data',{}).get('project',{}).get('project_name','?'))"` — expect a valid project name.

If Directus fails to come up, **rollback immediately** (§7).

#### Option B — Railway API (for scripted/agent-driven rotations)

Railway API token is in `Production/API_KEYS_MASTER.md` line 70 (`200d4b4e-c009-475e-ae4e-d5a677fd4835`). GraphQL endpoint: `https://backboard.railway.com/graphql/v2`.

```python
import urllib.request, json

RAILWAY_TOKEN = "<from API_KEYS_MASTER.md line 70>"
# Step 1: query serviceId for Directus in efficient-grace project
# Step 2: upsert the DB_PASSWORD variable via variableUpsert mutation
query = """
mutation variableUpsert($input: VariableUpsertInput!) {
  variableUpsert(input: $input)
}
"""
variables = {
  "input": {
    "projectId": "<efficient-grace project ID>",
    "environmentId": "<production environment ID>",
    "serviceId": "<Directus service ID>",
    "name": "DB_PASSWORD",
    "value": "<new_password>"
  }
}
payload = json.dumps({"query": query, "variables": variables}).encode()
req = urllib.request.Request(
    "https://backboard.railway.com/graphql/v2",
    data=payload,
    headers={"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
print(json.loads(resp.read()))
# Step 3: trigger redeploy via serviceInstanceRedeploy mutation
```

Note: Railway project/environment/service IDs can be found via the `me { projects { id name services { edges { node { id name } } } } }` query. The Option A dashboard method is faster for manual rotations; Option B is for future automation.

### Step 4.4 — GitHub Actions secrets (if applicable)

If the pre-rotation checklist surfaced any workflow that uses `SUPABASE_DB_PASSWORD`:

```
gh secret set SUPABASE_DB_PASSWORD --repo kimhyla/mindfulnest-tooling --body '<new_value>'
```

(Repeat for any other repo that needs it.)

### Step 4.5 — Local launchd / cron

If `daily_backup.sh` is invoked under `doppler run --`, no action needed — it picks up the new value on the next run.

If it is invoked with bare env vars (legacy), edit your launchd plist or crontab and update `SUPABASE_DB_PASSWORD`. Reload the launchd job:

```
launchctl unload ~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist
launchctl load ~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist
```

---

## 5. Verification

Run all three checks. All three must pass before declaring rotation complete.

### 5.1 — Daily backup smoke test

```
cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
doppler run --project mindfulnest --config prd -- bash Production/scripts/daily_backup.sh
```

Expect `SUCCESS` in `~/MindfulNestBackups/directus/backup.log`. A new `.sql.gz` file should appear in that directory dated today.

### 5.2 — Direct psql probe

```
doppler run --project mindfulnest --config prd -- bash -c '
PGPASSWORD="$SUPABASE_DB_PASSWORD" psql \
  -h "${SUPABASE_DB_HOST:-db.ugjpauwozlruyctrygby.supabase.co}" \
  -p 5432 \
  -U "${SUPABASE_DB_USER:-postgres.ugjpauwozlruyctrygby}" \
  -d postgres \
  -c "SELECT 1 AS rotation_smoke;"
'
```

Expect `rotation_smoke` = `1` printed back. Auth failure here means Doppler is out of sync with Supabase.

### 5.3 — Directus smoke test (proves Railway env is updated)

```
curl -s https://directus-production-3460.up.railway.app/server/info | jq -r '.data.project.project_name'
```

Expect a valid name string. Empty / 5xx means Directus cannot reach Postgres.

### 5.4 — Audit log

After all three pass, append to the rotation log row in Directus (`prod_activity_log` or equivalent governance log):

```
action: "supabase_password_rotation"
performed_by: "Kim" (or "Claude under Kim direction")
details: {
  "rotation_date": "YYYY-MM-DD",
  "trigger": "quarterly" | "emergency" | "drift_monitor" | "investigation",
  "consumers_updated": ["doppler.dev","doppler.prd","md_fallback","railway_directus_db_password","launchd"],
  "next_rotation_due": "YYYY-MM-DD (today + 90d)"
}
```

This row is what the drift monitor checks against to know "rotation is current."

---

## 6. Drift monitor — `check_supabase_password_drift`

A new sub-check in `Production/scripts/weekly_preflight_audit.py` runs every weekly cron:

- Performs an actual `psql -c 'SELECT 1'` against Supabase, fed by Doppler.
- **Auth fails** → emit a CRITICAL `app_blockers` row + `prod_activity_log` row tagged `severity=critical` + `category=supabase_password_drift`. Surfaces at next session start (`dashboard-gate` skill).
- **Auth succeeds** → silent (no log noise).

Frequency: weekly only. Auth attempts are observable in Supabase audit logs and in Doppler audit logs; running this hourly would create unnecessary noise in those audit trails. Weekly catches drift within 7 days, which is acceptable since the daily-backup smoke test would also catch a hard break within 24h.

The function and its wiring into the existing audit are in `Production/scripts/weekly_preflight_audit.py` (search for `check_supabase_password_drift`).

---

## 7. Rollback

If §5 verification fails AND you can re-key the previous password (Supabase keeps no history — if you lost the old value, rollback is impossible, which is why §3 step 4 says "copy first, click second"):

1. Supabase dashboard → reset password BACK to the previous value (paste from clipboard or password manager).
2. Re-run §4.1 + §4.2 + §4.3 with the previous value.
3. Re-run §5 verification.
4. File a `prod_blockers` row capturing what failed.
5. Investigate before retrying. Common causes:
   - Special chars in password mangled by Railway (use only alphanumeric + safe-class symbols).
   - Doppler config wrong (`dev` vs `prd` confusion).
   - Railway service did not actually redeploy.

If the old password is unrecoverable, you are committed to the new one. In that case fix-forward, not roll-back: identify the broken consumer in §5, update it, retry verification.

---

## 8. Quarterly scheduled task template

Schedule via the `scheduled-tasks` MCP at runbook approval time (do this once, then forget):

```
title: "Supabase DB password rotation due"
prompt: "Quarterly Supabase DB password rotation per SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md. Walk Kim through §3 and §4, run §5 verification, log §5.4 audit row."
trigger_at: <today + 90d>
recurrence: every 90 days
```

The drift monitor catches forgotten rotations within 7 days regardless of whether this task fires.

---

## 9. Change log

- 2026-05-08 — v1 authored. Locked alongside LD `SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1`. Drift monitor `check_supabase_password_drift` shipped in `weekly_preflight_audit.py` same session.
- 2026-05-08 (same day, second edit) — Step 4.3 expanded with root-cause incident note (Directus down for hours after rotation because Railway `DB_PASSWORD` env var was not updated). Added Option A (dashboard) + Option B (Railway API with token from `API_KEYS_MASTER.md` line 70). Updated §5.4 `consumers_updated` key to `railway_directus_db_password` for clarity. Pre-rotation checklist Railway bullet already correctly mentioned `DB_PASSWORD` — no change needed there.

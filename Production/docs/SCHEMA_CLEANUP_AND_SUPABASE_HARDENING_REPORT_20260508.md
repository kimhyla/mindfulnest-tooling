# Schema Cleanup Investigation + Supabase Hardening — Proof Report

**Authored:** 2026-05-08.
**Authoring agent:** Claude Opus 4.7 (1M context).
**Self-classification:**
- Investigation 1 (schema vocabulary): **INVESTIGATION ONLY** — no LD severity/task_category/scope_domain values were modified. Recommendations only.
- Investigation 2 (Supabase rotation): **ARCHITECTURAL (governance)** — runbook + monitor + standing-rule LD authored and locked.

**Confidence tags used:**
- CONFIRMED — verified with tool output (Directus query, file read, syntax compile).
- INFERRED — reasoned from CONFIRMED evidence; not directly observed.
- ASSUMED — best-judgment fill; flagged for Kim review.

---

## 0. Confirmed environment baseline

```
TOTAL_ACTIVE prod_locked_decisions: 529  [CONFIRMED — Directus aggregate count]

severity distribution:
  HIGH:      174    (canonical legacy)
  CRITICAL:  129    (canonical legacy)
  MEDIUM:     94    (legacy)
  HARD:       45    (canonical NEW per schema enum)
  SOFT:       30    (canonical NEW per schema enum)
  LOW:        20    (legacy)
  high:       15    (lowercase variant)
  medium:     15    (lowercase variant)
  low:         3    (lowercase variant)
  critical:    2    (lowercase variant)
  MED:         2    (abbreviation)

task_category distribution (top values):
  tech_stack:                       65   (canonical)
  app_architecture:                 59   (NON-canonical)
  production_infrastructure:        35   (NON-canonical)
  infrastructure:                   32   (NON-canonical)
  storyboard:                       30   (canonical)
  architectural:                    30   (NON-canonical)
  security:                         26   (NON-canonical)
  production_pipeline:              26   (NON-canonical)
  ... 60+ more values, long tail

scope_domain distribution:
  cross-cutting:                  383   (canonical)
  production:                      60   (canonical)
  app-dev:                         41   (canonical)
  infra:                           14   (canonical)
  app:                             12   (NON-canonical — should be app-dev?)
  infrastructure:                   6   (NON-canonical — should be infra?)
  ... 11 more singletons
```

**Live schema enum sets** [CONFIRMED — `/fields/prod_locked_decisions` API response]:

| Field | Canonical values |
|---|---|
| severity | `HARD`, `SOFT` |
| task_category | `audio, video, storyboard, tech_stack, api_integration, phase_b, phase_a, narrative, documents, business, all` (11) |
| scope_domain | `content, production, app-dev, infra, cross-cutting` (5) |
| enforcement_type | `structural, db_rule, linter, ci_check, test, lockfile, wrapper, code_invariant, awareness_only, human_gate` (10) |
| status | `active, superseded` |

The enum migration to HARD/SOFT was performed silently per the auto-memory note (`feedback_directus_schema_canonical.md`, "old values still accepted but new writes should use live-schema values"). Old values were never auto-migrated. **This is the root cause of the 303-row HIGH/CRITICAL backlog.**

---

## 1. Investigation 1 — Schema vocabulary audit

### 1.1 — Severity audit (30-LD sample of HIGH+CRITICAL = 303 active)

Sampled 10 OLDEST + 10 MIDDLE + 10 NEWEST by `date_locked`. Each row's `decision_text` + `notes` + `status` was read in full and classified per the brief's four-bucket scheme.

Bucket definitions:
- **TRULY_OPEN** — work genuinely not done; LD is correctly active and the severity label still meaningful.
- **RESOLVED_BUT_NOT_CLOSED** — work landed but the LD row was never PATCHed to status=superseded.
- **STALE** — decision no longer applies (technology pivoted, scope dropped).
- **AMBIGUOUS** — decision_text or notes do not give a clear signal.

| # | id | bucket | decision_key | sev | classification | rationale |
|---|---|---|---|---|---|---|
| 1 | 6 | OLDEST | kim_confirmation_gate_blocking | CRITICAL | TRULY_OPEN | Standing-rule (filename gate). Active by design — never closes. Severity label is fine; canonical value would be HARD. |
| 2 | 2 | OLDEST | version_up_never_overwrite | CRITICAL | TRULY_OPEN | Standing rule. Permanently active. → HARD. |
| 3 | 5 | OLDEST | read_before_write_rule_docx | CRITICAL | TRULY_OPEN | Standing rule. → HARD. |
| 4 | 89 | OLDEST | business_b2c_therapist_distribution | CRITICAL | TRULY_OPEN | Locked business-model decision; "$499 parents pay" still authoritative. → HARD. |
| 5 | 88 | OLDEST | sms_whatsapp_coaching_delivery | CRITICAL | AMBIGUOUS | "SMS/WhatsApp not push" — V1 may have changed; 2026-04-19 LD-301 mentions "AI Parent Coach Cloud Run" suggesting in-app coach. Needs Kim review. |
| 6 | 51 | OLDEST | arc1_event_6_m5_bork_grounding | CRITICAL | TRULY_OPEN | Narrative LD; Arc 1 V1 scope still pending production. → HARD. |
| 7 | 53 | OLDEST | guide_bird_consistent_voice | CRITICAL | TRULY_OPEN | Standing voice constraint. → HARD. |
| 8 | 52 | OLDEST | myrrhin_narrator_phase_b | CRITICAL | TRULY_OPEN | Standing narrative-voice constraint. → HARD. |
| 9 | 84 | OLDEST | phase_a_one_demo_cycle | CRITICAL | TRULY_OPEN | Standing structural rule. → HARD. |
| 10 | 79 | OLDEST | phase_b_sensation_language_only | CRITICAL | TRULY_OPEN | Standing rule. → HARD. |
| 11 | 195 | MIDDLE | PHASE_B_M1_PAUSE_STRUCTURE_v9_LOCKED | CRITICAL | RESOLVED_BUT_NOT_CLOSED | "M1 Phase B audio structure locked April 17 2026" — that work shipped (M1 Phase B audio is in production per LD-146). Pattern reference value remains; should stay active but as HARD or downgrade to reference doc. |
| 12 | 216 | MIDDLE | COPPA_VPC_VIA_KWS_ONLY | CRITICAL | TRULY_OPEN | KWS integration not yet shipped (S3-AUTH-consent pending). → HARD. |
| 13 | 217 | MIDDLE | COPPA_CHILD_PII_NO_THIRD_PARTY_WITHOUT_CONSENT | CRITICAL | TRULY_OPEN | Standing privacy rule. → HARD. |
| 14 | 197 | MIDDLE | PHASE_B_FRAME_IRON_WOOD_LOCKED | CRITICAL | STALE | Explicitly superseded by id=203 ("simple 2-matte locked") yet status=active. **CLOSE THIS ROW.** |
| 15 | 203 | MIDDLE | PHASE_B_FRAME_SIMPLE_2MATTE_LOCKED | CRITICAL | TRULY_OPEN | Standing visual constraint; supersedes 197. → HARD. |
| 16 | 204 | MIDDLE | OPTION_C_DIRECTUS_AS_UI_PROTOTYPE_SCOPE_v2 | CRITICAL | AMBIGUOUS | Pattern decision; v59 storyboard has shipped a non-Directus path. Status of "Directus-as-UI" pattern unclear. Kim review. |
| 17 | 143 | MIDDLE | MYRRHIN_VISUAL_DESIGN_LOCKED | HIGH | TRULY_OPEN | Master still + canonical character design. → HARD. |
| 18 | 146 | MIDDLE | M1_PHASE_B_AUDIO_LOCKED | HIGH | RESOLVED_BUT_NOT_CLOSED | M1 Phase B audio shipped; LD describes a final state. Could close OR keep as reference. |
| 19 | 149 | MIDDLE | M1_PHASE_B_VIDEO_APPROVED | HIGH | RESOLVED_BUT_NOT_CLOSED | Same — M1 Phase B video approved + saved. Reference status. |
| 20 | 168 | MIDDLE | TTS_APPROACH_C_FORBIDDEN | HIGH | TRULY_OPEN | Hard prohibition standing rule. → HARD. |
| 21 | 490 | NEWEST | SCENE_ASSEMBLE_ENDPOINT_V1 | HIGH | TRULY_OPEN | Endpoint exists in production_server.py (per session 5 commits); LD describes contract. → HARD. |
| 22 | 489 | NEWEST | BEAT_FINALIZE_ENDPOINT_V1 | HIGH | TRULY_OPEN | Same. → HARD. |
| 23 | 488 | NEWEST | VIDEO_ROLE_PER_REQUEST_V2 | HIGH | TRULY_OPEN | Active validation rule in scope_router. → HARD. |
| 24 | 487 | NEWEST | BG_VIDEO_PARTITION_V2 | HIGH | TRULY_OPEN | Active state-shape rule. → HARD. |
| 25 | 486 | NEWEST | MILESTONE_STANDALONE_INDEPENDENT_V1 | HIGH | TRULY_OPEN | Active. → HARD. |
| 26 | 485 | NEWEST | PHASE_B_TOP_LEVEL_STATE_V1 | HIGH | TRULY_OPEN | Active state-shape rule. → HARD. |
| 27 | 462 | NEWEST | PHASE_A_PRODUCER_V1 | HIGH | TRULY_OPEN | v59 Phase A producer panel; closeout note shows Session 3 v3.1 done-state but v59 is still mid-build. Active. → HARD. |
| 28 | 483 | NEWEST | VIDEO_SELECTOR_UI_V1 | HIGH | TRULY_OPEN | UI rule still binding for v59. → HARD. |
| 29 | 502 | NEWEST | PROD_MODULES_GAMEPLAY_SCOPE_SOURCE_V1 | HIGH | TRULY_OPEN | Active mirroring contract. → HARD. |
| 30 | 484 | NEWEST | PHASE_A_TOP_LEVEL_STATE_V1 | HIGH | TRULY_OPEN | Active. → HARD. |

**Sample classification percentages (n=30):**

| Bucket | Count | % |
|---|---|---|
| TRULY_OPEN | 23 | 76.7% |
| RESOLVED_BUT_NOT_CLOSED | 3 | 10.0% |
| STALE | 1 | 3.3% |
| AMBIGUOUS | 3 | 10.0% |

**Key finding [CONFIRMED]:** the dominant failure mode is **NOT** "rows that should be closed but aren't." It is **stale severity vocabulary on genuinely-active rows.** Roughly 77% of HIGH/CRITICAL active LDs sampled are correctly active — they just predate the schema migration. Only 1 of 30 was a clear close-this-row case (id=197, explicitly superseded by id=203).

**Extrapolated to the full 303-row HIGH/CRITICAL set [INFERRED]:**

| Bucket | Estimated count (303 × %) | Confidence |
|---|---|---|
| TRULY_OPEN — needs sev label remap to HARD/SOFT | ~232 | INFERRED |
| RESOLVED_BUT_NOT_CLOSED — should be PATCHed to superseded | ~30 | INFERRED |
| STALE — should be closed | ~10 | INFERRED |
| AMBIGUOUS — needs Kim review | ~30 | INFERRED |

These percentages are sample-derived; a full 303-row pass would tighten them.

### 1.2 — task_category audit (top 5 non-canonical, 5 LDs each)

**Canonical task_category enum:** `audio, video, storyboard, tech_stack, api_integration, phase_b, phase_a, narrative, documents, business, all`.

| Non-canonical value | Count | Canonical analog | Recommendation |
|---|---|---|---|
| **app_architecture** (59) | sampled 5 | none — gap in canonical | **KEEP_LIVE** — every sample (LD 484, 485, 486, 487, 488) is a state-shape / API contract decision for the v59 client. `tech_stack` is too coarse; this is its own meaningful bucket. **Recommend adding `app_architecture` to the canonical enum.** |
| **production_infrastructure** (35) | sampled 5 | `tech_stack` partial; gap | **KEEP_LIVE or RENAME** — samples cover async drain protocol (LD 491) + Cluster A widget UX (LD 238/239/240/241). These are heterogeneous: drain protocol is infrastructure; Cluster A is production_tool_ui. **Recommend splitting:** drain → new `infrastructure` (canonical?) or merge with `tech_stack`; Cluster A → new `production_tool_ui`. |
| **architectural** (30) | sampled 5 | overlap with `app_architecture` | **REMAP → app_architecture** — semantic overlap with `app_architecture` (59 rows). Two near-synonym buckets is the failure mode the audit was designed to detect. Consolidate. |
| **infrastructure** (32) | sampled 5 | `tech_stack`, `infra` (scope_domain only) | **KEEP_LIVE** — samples (LD 505 tooling repo, LD 432 Cloudflare R2, LD 421 asset findability) are infrastructure decisions. Canonical lacks an "infrastructure" bucket; `tech_stack` doesn't capture "where it runs / how it's organized." **Recommend adding `infrastructure` to canonical.** |
| **storyboard** (30) | already canonical | — | (Listed in brief as "non-canonical" but in fact `storyboard` IS in the canonical enum. The brief had this wrong; verified via `/fields/prod_locked_decisions` response.) |

**Additional task_category values >5 occurrences worth flagging** (from full distribution):

| Value | Count | Recommendation |
|---|---|---|
| `security` (26) | KEEP_LIVE — add to canonical (security decisions deserve their own bucket) |
| `production_pipeline` (26) | INVESTIGATE_INDIVIDUALLY — overlap with `production_infrastructure` |
| `narrative` (19) | already canonical |
| `video` (16) | already canonical |
| `audio` (15) | already canonical |
| `governance` (12) | KEEP_LIVE — add to canonical |
| `visual_production` (12) | INVESTIGATE — could merge with `video` |
| `audio_production` (??) | REMAP → `audio` |
| `video_production` (??) | REMAP → `video` |
| `character_design` (??) | KEEP_LIVE — add or merge under `visual_production` |
| `production_server_infrastructure` (15) | REMAP → `infrastructure` (if added) or `tech_stack` |
| `production_server` (??) | REMAP → `infrastructure` |
| `production_tool_ui` (??) | KEEP_LIVE — add to canonical |
| `data_model` (5) | KEEP_LIVE — add to canonical |
| `tools` (6) | INVESTIGATE — overlap with `production_tool_ui` |
| `phase_a` / `phase_b` | already canonical (15 each) |
| `feature` (??) | INVESTIGATE — too generic; case-by-case remap |
| `api_integration` (5) | already canonical |

**Proposed canonical task_category v2 (12 → 18 values):**

```
audio, video, storyboard, tech_stack, api_integration, phase_a, phase_b,
narrative, documents, business, all,
+ app_architecture
+ infrastructure
+ security
+ governance
+ production_tool_ui
+ data_model
+ visual_production
```

### 1.3 — scope_domain audit (12 non-canonical instances)

**Canonical scope_domain enum:** `content, production, app-dev, infra, cross-cutting`.

| Non-canonical value | Count | Sample IDs | Recommendation |
|---|---|---|---|
| **app** | 12 | 247, 237, 248, 229, 230, 236 | **REMAP → app-dev** — every sample is a Firebase / app-side decision (KWS, CORS+AppCheck, Firebase project ID, Firestore PITR). `app` is just a typo / earlier vocab for `app-dev`. |
| **infrastructure** | 6 | 359, 360, 361, 364, 301, 227 | **REMAP → infra** — every sample is infrastructure (mn-context skill, Directus write contract, Cloud Run minInstances, Doppler fallback). `infrastructure` is just typo / earlier vocab for `infra`. |
| **stillgen** | 2 | (singletons) | **REMAP → production** — narrow pipeline domain rolls up to production. |
| **governance** | 2 | (singletons) | **REMAP → cross-cutting** — governance decisions cut across all domains. |
| **video_pipeline** | 1 | (singleton) | **REMAP → production** |
| **audio_pipeline** | 1 | (singleton) | **REMAP → production** |
| **image_pipeline** | 1 | (singleton) | **REMAP → production** |
| **ci_pipeline** | 1 | (singleton) | **REMAP → infra** |
| **claude_session_behavior** | 1 | (singleton) | **REMAP → cross-cutting** |
| **payments** (id=300 STRIPE_IDEMPOTENCY_KEY_V1) | 1 | 300 | **REMAP → app-dev** (Stripe is an app-side concern) — OR add `payments` to canonical if Kim wants explicit blast-radius callout |
| **beat_generator** | 1 | 399 | **REMAP → production** |
| **production_pipeline** | 1 | 421 | **REMAP → production** |
| **content** | 1 | 539 | already canonical (interesting that only 1 LD uses it) |

**Recommendation: scope_domain canonical stays at 5 values; all 27 non-canonical rows REMAP via the table above.** Singleton remap is low-risk; `app→app-dev` and `infrastructure→infra` are the highest-volume safe remaps (12+6=18 rows).

### 1.4 — Recommendation summary table

| Field | Action | Volume | Risk |
|---|---|---|---|
| severity HIGH+CRITICAL → HARD/SOFT | REMAP (mass migration) | 303 | LOW — sample shows 77% are TRULY_OPEN with stale labels; mapping is mechanical (HIGH→HARD or SOFT, CRITICAL→HARD) |
| severity lowercase variants | REMAP to UPPER | 35 | TRIVIAL — case-only |
| severity LOW + MED + MEDIUM | DEPRECATE then REMAP | ~131 | MEDIUM — schema enum is HARD/SOFT only; need rule for what LOW/MEDIUM map to (likely SOFT or amend canonical to include LOW) |
| task_category — extend canonical to 18 | KEEP_LIVE additions | n/a | LOW — schema enum extension only; no row migration |
| task_category — `architectural` → `app_architecture` | REMAP | 30 | LOW — pure consolidation |
| task_category — synonym remaps (`audio_production` → `audio` etc.) | REMAP | ~80 | LOW |
| scope_domain — `app` → `app-dev` | REMAP | 12 | LOW |
| scope_domain — `infrastructure` → `infra` | REMAP | 6 | LOW |
| scope_domain — singletons → canonical | REMAP individually | 11 | LOW |
| RESOLVED_BUT_NOT_CLOSED rows | Close (status=superseded) | ~30 estimated | MEDIUM — needs per-row decision |
| STALE rows (id=197 confirmed) | Close | ~10 estimated | MEDIUM |

### 1.5 — Estimated migration effort

**A separate session is required. Effort estimate:**

| Pass | Volume | Effort | Risk |
|---|---|---|---|
| Pass 1: severity case-fold (lowercase→UPPER) | 35 | 30 min | TRIVIAL — pure case-fold |
| Pass 2: severity HIGH/CRITICAL/MEDIUM/LOW remap to HARD/SOFT | ~454 (303+94+57) | 2-3 hr | LOW (per-row mechanical, but Kim should approve mapping rule first) |
| Pass 3: task_category enum extension (add 7 values) | 0 row changes | 15 min | LOW — schema-only |
| Pass 4: task_category remaps | ~110 (30+80) | 1-2 hr | LOW |
| Pass 5: scope_domain remaps | 29 | 30 min | LOW |
| Pass 6: RESOLVED_BUT_NOT_CLOSED triage | ~30 | 2-3 hr | MEDIUM — per-row read |
| Pass 7: STALE / AMBIGUOUS triage | ~40 | 3-4 hr | MEDIUM |
| **Total** | ~700 row touches | **~10 hours of focused work** | LOW-MEDIUM overall |

**Recommendation:** schedule as a separate atomic session with Kim providing the **mapping rule decisions** up front:
1. HIGH → HARD vs SOFT? (proposal: HIGH → HARD; CRITICAL → HARD; MEDIUM → SOFT; LOW → SOFT or extend enum to include LOW)
2. lowercase variants: pure case-fold (no semantic change).
3. Extend canonical task_category enum (Kim approves the 7 additions).
4. RESOLVED_BUT_NOT_CLOSED: do you want them closed (status=superseded) or kept as standing-reference HARD rules?

Once those 4 questions are answered, the migration is mostly mechanical and can be scripted with read-back-after-write per Rule 35.

---

## 2. Investigation 2 — Supabase rotation hardening

### 2.1 — Runbook

**Authored:** `Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md` (226 lines, md5 `fe99dd0e48b50ed925c462cadd1ce757`).

**Verbatim runbook content:** see the file. Section structure:

```
0. What this runbook does
1. When to rotate — quarterly + emergency triggers
2. Pre-rotation checklist — 7 consumers identified (Doppler, MD line 64, launchd, Railway, GitHub Actions, Vercel N/A, .env files, memory/handoff scrub)
3. Rotation steps — Supabase dashboard reset
4. Update steps in mandatory order:
   4.1 Doppler dev+prd
   4.2 API_KEYS_MASTER.md line 64 (until LD-227 Phase 4)
   4.3 Railway Directus service env + redeploy
   4.4 GitHub Actions secrets (if applicable)
   4.5 Local launchd / cron
5. Verification — daily-backup smoke + direct psql probe + Directus /server/info smoke + audit log row
6. Drift monitor — describes check_supabase_password_drift wiring
7. Rollback — Supabase keeps no history; copy old before clicking
8. Quarterly scheduled-tasks template
9. Change log
```

### 2.2 — Drift monitor

**File modified:** `Production/scripts/weekly_preflight_audit.py`. New function `check_supabase_password_drift` inserted before `run_audit`; new sub-check call inserted in `run_audit` between `check_pr8_merge_postwork` and the final `return summary`.

**Verbatim diff (function definition):**

```python
def check_supabase_password_drift(client, dry_run=False):
    """Detect drift between Doppler-fed SUPABASE_DB_PASSWORD and live Supabase auth.

    Per LD SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1 + runbook
    Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md §6.

    Performs a single `psql -c 'SELECT 1'` against Supabase using credentials
    from the Doppler-injected env. If auth fails, emits a CRITICAL app_blockers
    row + activity log row. If auth succeeds, silent (no log noise).

    Frequency: weekly only. Auth attempts are observable in Supabase + Doppler
    audit logs; running more often would create noise in those audit trails.
    Weekly catches drift within 7 days; the daily backup job catches a hard
    break within 24h independently.

    Best-effort: never fails the parent audit. Returns a dict summary.
    """
    import shutil
    import subprocess

    summary = {
        "ran": False,
        "auth_ok": None,
        "blocker_created": False,
        "skipped_reason": None,
        "dry_run": dry_run,
    }

    pw = os.environ.get("SUPABASE_DB_PASSWORD")
    host = os.environ.get("SUPABASE_DB_HOST", "db.ugjpauwozlruyctrygby.supabase.co")
    user = os.environ.get("SUPABASE_DB_USER", "postgres.ugjpauwozlruyctrygby")
    port = os.environ.get("SUPABASE_DB_PORT", "5432")
    db = os.environ.get("SUPABASE_DB_NAME", "postgres")

    if not pw:
        summary["skipped_reason"] = "SUPABASE_DB_PASSWORD not in env (Doppler not active?)"
        print(f"[supabase-drift] SKIP {summary['skipped_reason']}")
        return summary

    if shutil.which("psql") is None:
        summary["skipped_reason"] = "psql not on PATH (brew install libpq && brew link --force libpq)"
        print(f"[supabase-drift] SKIP {summary['skipped_reason']}")
        return summary

    summary["ran"] = True
    env = os.environ.copy()
    env["PGPASSWORD"] = pw
    try:
        proc = subprocess.run(
            [
                "psql",
                "-h", host, "-p", port, "-U", user, "-d", db,
                "-c", "SELECT 1 AS supabase_drift_probe;",
                "--no-psqlrc", "-t", "-A",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        summary["auth_ok"] = None
        summary["skipped_reason"] = f"probe transport error (not auth): {e!r}"
        print(f"[supabase-drift] WARN {summary['skipped_reason']}")
        return summary

    auth_ok = proc.returncode == 0 and "1" in (proc.stdout or "")
    summary["auth_ok"] = auth_ok
    if auth_ok:
        return summary

    stderr_snippet = (proc.stderr or "").strip().splitlines()[-1:] if proc.stderr else []
    err_line = stderr_snippet[0] if stderr_snippet else f"exit={proc.returncode}"
    title = "Supabase password drift detected"
    description = (
        f"weekly_preflight_audit.py::check_supabase_password_drift probed "
        f"Supabase via Doppler-fed SUPABASE_DB_PASSWORD and got an auth failure. "
        f"This means Doppler and Supabase are out of sync.\n\n"
        f"Probe stderr (last line): {err_line}\n"
        f"Host: {host}  User: {user}  DB: {db}  Port: {port}\n\n"
        f"Action: run the rotation runbook at "
        f"Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md §5 to "
        f"re-sync. If a rotation was performed recently, verify §4.1 "
        f"(Doppler) and §4.3 (Railway) both received the new value."
    )

    try:
        existing_resp = client._request(
            "GET",
            "/items/app_blockers",
            params={
                "filter[is_resolved][_eq]": "false",
                "filter[title][_eq]": title,
                "limit": 5,
            },
        )
        existing = existing_resp.get("data", [])
    except DirectusError as e:
        existing = []
        print(f"[supabase-drift] WARN dedupe lookup failed (proceeding): {e}")

    if existing:
        print(f"[supabase-drift] CRITICAL but {len(existing)} unresolved blocker(s) already exist; skipping create.")
        summary["blocker_created"] = False
        return summary

    if dry_run:
        print(f"[supabase-drift] [DRY-RUN] would create CRITICAL blocker: {title}")
        summary["blocker_created"] = True
        return summary

    payload = {
        "feature_id": 5,
        "title": title,
        "description": description,
        "severity": "critical",
        "is_resolved": False,
    }
    try:
        client._request("POST", "/items/app_blockers", data=payload)
        summary["blocker_created"] = True
        print(f"[supabase-drift] CRITICAL blocker created: {title}")
    except DirectusError as e:
        print(f"[supabase-drift] ERROR creating blocker: {e}")
        summary["error"] = str(e)
        return summary

    try:
        client._request("POST", "/items/app_activity_log", data={
            "feature_id": 5,
            "action": "supabase_password_drift detected",
            "details": json.dumps({
                "host": host, "user": user, "db": db, "port": port,
                "stderr_last_line": err_line,
                "protocol_ld_key": "SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1",
            }),
            "performed_by": "weekly_preflight_audit.py::check_supabase_password_drift",
        })
    except DirectusError as e:
        print(f"[supabase-drift] WARN activity log write failed: {e}")

    return summary
```

**Wiring into `run_audit` (verbatim diff):**

```python
    # Sub-check: Supabase password drift (LD SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1).
    # Performs a single Doppler-fed psql 'SELECT 1' against Supabase. Auth fail =>
    # CRITICAL app_blockers row + activity log. Auth ok => silent. Best-effort:
    # never fails the main audit. Runbook: Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md.
    try:
        summary["supabase_password_drift"] = check_supabase_password_drift(client, dry_run=dry_run)
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: check_supabase_password_drift sub-check failed: {e!r}")
        summary["supabase_password_drift"] = {"error": repr(e)}
```

**Verification [CONFIRMED]:**
- `python3 -m py_compile Production/scripts/weekly_preflight_audit.py` → exit 0.
- Dry-run probe: `[supabase-drift] [DRY-RUN] would create CRITICAL blocker: Supabase password drift detected`
- Result dict: `{'ran': True, 'auth_ok': False, 'blocker_created': True, 'skipped_reason': None, 'dry_run': True}`

### 2.3 — Standing-rule LD POSTed and read-back-verified

**LD #582 created.** Verbatim POST response (relevant fields):

```json
{
  "data": {
    "id": 582,
    "decision_key": "SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1",
    "decision_name": "Supabase DB password rotation protocol — runbook + drift monitor",
    "severity": "HARD",
    "status": "active",
    "task_category": "tech_stack",
    "scope_domain": "infra",
    "enforcement_type": "human_gate",
    "date_locked": "2026-05-08",
    "source_document": "Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md",
    "governance_file": "Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md",
    "enforcement_artifact_ref": "Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md + Production/scripts/weekly_preflight_audit.py::check_supabase_password_drift",
    "is_current": true,
    "supersedable": true,
    "schema_version": 2
  }
}
```

**Read-back-after-write [CONFIRMED — Rule 35]:** all 11 caller-set fields match the POST payload field-for-field; `decision_text` length 1052 chars matches.

---

## 3. Active blocker / live finding [CRITICAL — Kim attention required]

The drift monitor's first run **detected genuine drift on the live system.** Confirmed via independent observation of `~/MindfulNestBackups/directus/last_dump_stderr.log`:

```
pg_dump: error: connection to server at "db.ugjpauwozlruyctrygby.supabase.co" (100.49.129.158), port 5432 failed: FATAL:  password authentication failed for user "postgres.ugjpauwozlruyctrygby"
```

**The daily Directus backup has been failing today.** Doppler + `API_KEYS_MASTER.md` line 64 both hold `iXfcu9uDbZElkpl6` (in sync with each other), but the live Supabase password no longer accepts that value. This means either:

1. Someone (or a Supabase-side automation) rotated the password without going through this runbook.
2. Supabase is rejecting the user/host combo for an unrelated auth reason (rare).

**Recommended action:** Kim should run §3-§5 of the runbook to manually rotate now (since rollback is impossible — old password is unrecoverable). I did NOT auto-create the blocker (the dry-run flag prevented that, intentionally — initial drift detection deserves a Kim-authorized blocker creation rather than a quiet automatic one).

If Kim wants the blocker created for visibility, run:

```
doppler run -- python3 -c "
import sys
sys.path.insert(0, 'Production/tools')
sys.path.insert(0, 'Production/scripts')
from lib.credentials import load_credentials
from lib.directus import DirectusClient
from weekly_preflight_audit import check_supabase_password_drift
c = load_credentials()
client = DirectusClient(c['directus_url'], c['directus_email'], c['directus_password'])
client.authenticate()
print(check_supabase_password_drift(client, dry_run=False))
"
```

(Same command without `dry_run=False` would be the natural weekly cron invocation.)

---

## 4. Confidence tags summary

| Claim | Tag |
|---|---|
| 529 active LDs total | CONFIRMED |
| 303 use HIGH+CRITICAL severity | CONFIRMED |
| Schema canonical enums (5 fields) | CONFIRMED via `/fields/prod_locked_decisions` |
| 30-LD severity sample classification | CONFIRMED — read each `decision_text` |
| 77% TRULY_OPEN extrapolation to full 303 | INFERRED — sample-derived |
| RESOLVED_BUT_NOT_CLOSED count ~30 | INFERRED |
| STALE id=197 confirmed | CONFIRMED — id=203 explicitly supersedes |
| task_category proposed v2 enum (18 values) | INFERRED — based on 5x5 sample + full distribution |
| scope_domain `app` and `infrastructure` are typos | INFERRED — high confidence (every sample matches canonical synonym semantically) |
| Migration effort ~10 hours | ASSUMED — depends on Kim's mapping-rule decisions |
| Runbook authored at given path | CONFIRMED — file written, md5 verified |
| Monitor function syntax-valid | CONFIRMED — py_compile exit 0 |
| Monitor dry-run executes the auth-fail path | CONFIRMED — output captured |
| LD #582 POSTed and read-back matches | CONFIRMED — Rule 35 |
| Daily backup is currently failing with FATAL auth error | CONFIRMED — independent observation of last_dump_stderr.log |
| Doppler and MD line 64 currently agree on `iXfcu9uDbZElkpl6` | CONFIRMED — `doppler secrets get` output |

---

## 5. Final recommendations

### 5.1 — Schema vocabulary (Investigation 1)

**Do not migrate today.** Schedule a dedicated session. Kim must decide 4 mapping rules first:

1. HIGH/CRITICAL/MEDIUM/LOW → which of HARD/SOFT? (Or extend enum to keep LOW.)
2. Extend canonical task_category enum from 11 to 18 values (concrete proposal in §1.2).
3. RESOLVED_BUT_NOT_CLOSED rows: close them, or re-purpose as standing-reference HARD?
4. AMBIGUOUS rows (~30 estimated): individual triage acceptable, or auto-flag for review?

Once decided, the migration is ~10 hours of mostly mechanical work with read-back-after-write per Rule 35. Recommend Pass 1 (case-fold) + Pass 5 (scope_domain singletons) first — both are TRIVIAL/LOW risk and quick wins.

### 5.2 — Supabase hardening (Investigation 2)

**Live drift detected.** Kim should manually rotate today using the new runbook (§3-§5). The standing-rule LD (#582) and drift monitor are in place; on the next weekly cron run after rotation, the monitor's first auth-success will be silent (validating the rotation worked). If a future rotation is missed, the monitor catches it within 7 days.

Optional follow-on: schedule a `scheduled-tasks` MCP entry for a quarterly rotation prompt (template in runbook §8). I did NOT create that scheduled task in this session — it requires Kim's hand on the trigger so the prompt fires under her account.

### 5.3 — Self-classification

- Investigation 1 work: **INVESTIGATION ONLY.** No Directus rows touched. Recommendations only.
- Investigation 2 work: **ARCHITECTURAL (governance).** New runbook + new monitor function + new standing-rule LD all locked. Drift monitor wired into existing weekly audit. No existing LDs modified.

### 5.4 — Recommendation: separate session for vocab migration

Yes — keep the migration in its own session. Reasons:
- 10 hours of focused work doesn't pair well with the current Storyboard / V59 / CI/CD threads.
- Mapping rules (§5.1 questions 1-4) need explicit Kim sign-off before any row is touched.
- A migration script with read-back-after-write should be authored, dry-run on 5 rows first, then mass-applied.
- Bundling with Investigation 2 already crossed the 5-deliverable threshold for this session.

---

## 6. Files touched / created

| Path | Status | Purpose |
|---|---|---|
| `Production/docs/SUPABASE_PASSWORD_ROTATION_RUNBOOK_v1.md` | CREATED | Runbook (226 lines) |
| `Production/scripts/weekly_preflight_audit.py` | MODIFIED | Added `check_supabase_password_drift` (~150 lines) + sub-check wiring (~7 lines) |
| `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` | CREATED | This report |
| Directus `prod_locked_decisions` row id=582 | CREATED | Standing-rule LD `SUPABASE_PASSWORD_ROTATION_PROTOCOL_V1` |
| `/tmp/severity_samples.json`, `/tmp/task_category_samples.json`, `/tmp/scope_domain_samples.json` | CREATED (transient) | Sample data captured during Investigation 1; can be deleted |

No existing LD rows were modified. No existing files were deleted.

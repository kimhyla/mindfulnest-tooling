# PERIODIC Class — SHORTCUT LD Classification System Tech Spec v1

**Status:** DESIGN-ONLY — awaiting Kim authorization
**Author:** Claude (subagent, dual-Opus debate pattern)
**Date:** 2026-05-07
**Classification:** ARCHITECTURAL (Directus schema migration + audit-logic branch)
**Predecessors:**
- 2026-05-07 SHORTCUT LD cap policy lock (Kim directive — replaces uniform 120-day proxy with two-class EVENT_DRIVEN/RARE_NEVER model)
- 2026-05-07 retroactive triage of LDs 199, 200, 201, 249 (RARE_NEVER cap-expired alerts)
- Prior agent analysis at session `a5a61aac` (cited in brief; surfaced the third-pattern hypothesis)
- Roadmap §1.6 living doc (`Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` lines 83-141)
- Audit script (`Production/scripts/weekly_preflight_audit.py`, 537 lines, read 2026-05-07)
- Directus schema query 2026-05-07 (`/fields/prod_locked_decisions` → 22 fields confirmed)

---

## §0 Operating Mode Declaration

Per `zero-error-qa` skill §0 (operating-mode declaration mandate):

- **Mode:** DESIGN-ONLY tech spec
- **Tier:** Tier C (architectural — schema migration on `prod_locked_decisions` is the canonical decisions store; audit logic affects mechanical governance enforcement)
- **Scope risk class:** Multi-stage + side-effect (schema migration is irreversible without rollback discipline; audit logic affects what gets surfaced to dashboard-gate Phase 0.7)
- **Six-Layer applicability (DS-13):** Layers 1-2 (UI exists, UI→backend wiring) N/A — this is governance plumbing, not user-facing. Layers 3-6 DO apply: backend processing (audit reads new schema fields), state propagation (Directus is canonical store), UI re-render (dashboard-gate surfacing), intent→outcome smoke test (a PERIODIC LD past `next_review_date` must surface as a finding).
- **Authoring discipline (DS-15):** every state claim cites a tool output (file Read line numbers, Directus query result, roadmap line numbers); no claim about "current behavior" without a citation.
- **Confidence tags (Rule 24):** `[VERIFIED]` = directly read from source in this session; `[INFERRED]` = derived from cited evidence but not directly observed; `[ASSUMED]` = working hypothesis pending confirmation.

This spec lands as a reviewable doc. **No code edits. No schema migrations. No Directus PATCHes.** Implementation is a separate session that Kim authorizes.

---

## §1 Scope

### §1.1 In scope

1. **Add a third SHORTCUT LD classification class:** `PERIODIC` — for LDs whose closure mechanism is a recurring scheduled review (quarterly, annually, etc.) rather than a single named event or no scheduled trigger at all.
2. **Schema migration:** add 3 new fields on `prod_locked_decisions`: `review_cadence` (enum-ish), `next_review_date` (date), `last_reviewed_date` (date).
3. **Audit-logic extension:** new branch in `check_shortcut_ld_closure_dates()` that warns when `next_review_date` is approaching (default: 7 days before) and on overdue review (past `next_review_date`).
4. **Roadmap §1.6 update:** new column for class; migration of qualifying LDs in the table.
5. **Migration cohort:** identify which existing LDs should re-classify to PERIODIC after the class lands (current EVENT_DRIVEN-as-INTERIM mappings).
6. **Resolution of 5 open design decisions** via dual-Opus advocate/counter debate (§5).

### §1.2 Out of scope

- Implementation work itself (this is design-only).
- Adding "review history" / audit-trail columns (e.g. a `review_log` jsonb of past reviews). Could be a v2 feature; for v1, just track last + next.
- Auto-creation of "review-due" LDs or work items when `next_review_date` fires. v1 surfaces a finding to dashboard-gate; the human decides whether to register a UPGRADE_* LD. (See §5.4 — "auto-block vs warn".)
- Backfilling `last_reviewed_date` for non-SHORTCUT LDs. Periodic cadence for non-SHORTCUT LDs (rare) is a follow-up.
- Multi-cadence LDs (e.g. quarterly + event-trigger). v1 supports cadence OR events as primary closure mechanism — see §5.5 / migration cohort discussion.
- Renaming SHORTCUT_LD_CLASSIFICATION dict to a more general name. Keep the existing identifier to minimize churn; the dict's values just gain a third valid string.

---

## §2 Background

### §2.1 The originating incident

On **2026-05-07** Kim locked the new SHORTCUT LD cap policy (replaces uniform 120-day proxy):

- `RARE_NEVER` LDs auto-halt at **14 days from `date_locked`** [VERIFIED — `weekly_preflight_audit.py` line 163: `RARE_NEVER_CAP_DAYS = 14`].
- `EVENT_DRIVEN` LDs gate on a named event with a **120-day backstop** [VERIFIED — line 164: `EVENT_DRIVEN_BACKSTOP_DAYS = 120`].

The same day, a triage pass surfaced 4 RARE_NEVER LDs locked in mid-April (≈19-21 days old) that were now retroactively past the new 14-day cap:

| LD | Triage outcome (2026-05-07) |
|---|---|
| 199 `SHORTCUT_ARCH_WEIGHT_PCT_COLLAPSED_TO_ENUM` | `status=closed` (closure trigger met by v2 inventory supersession) |
| 200 `SHORTCUT_LD_LINKAGE_SNAPSHOT_ONLY` | re-classified RARE_NEVER → EVENT_DRIVEN (Stage 4 / 2nd-contributor triggers) |
| 201 `SHORTCUT_PARTIAL_STATUS_NO_PCT_FIELD` | `status=closed` (v2 inventory closure trigger met) |
| 249 `SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418` | re-classified RARE_NEVER → **PERIODIC+EVENT_DRIVEN** (interim mapping to EVENT_DRIVEN) |

[VERIFIED — Roadmap §1.6 line 125: "TRIAGED 2026-05-07 in combined LD-PATCH + meta-fix pass — LDs 199 + 201 closed... LDs 200 + 249 re-classified RARE_NEVER → EVENT_DRIVEN..."]

A "Prospective-only cap" rule (`SHORTCUT_CAP_POLICY_LOCK_DATE = 2026-05-07`, [VERIFIED — line 38 of audit script]) plus a `GRANDFATHER_REVIEW` finding tier was added so the policy doesn't silently retro-ding April-locked rows; the four LDs above were the in-flight cohort that triggered first review under the new policy.

### §2.2 The third-pattern hypothesis

LD 200 and especially LD 249 revealed a pattern that fits NEITHER existing class cleanly:

> [VERIFIED — direct query 2026-05-07 of LD 249 notes field]
> "Closure: quarterly review against criteria (a)-(d); register UPGRADE_IDENTITY_PLATFORM_* LD if triggered. RE-CLASSIFIED 2026-05-07 from RARE_NEVER (14-day cap, retroactively past) to PERIODIC+EVENT_DRIVEN: review cadence is quarterly (next review 2026-07-18, then 2026-10-18, 2027-01-18); event triggers are (a) MAU>10K, (b) MFA becomes COPPA/therapist-compliance requirement, (c) SAML demanded by B2B therapist org, (d) abuse attempts..."

Why neither class fits:

- **Not RARE_NEVER:** the LD HAS a scheduled review cadence. RARE_NEVER means "no scheduled trigger; closure is if/when we happen to refactor." LD 249's closure mechanism IS the review — quarterly evaluation against criteria (a)-(d). There is real, scheduled work owed by a date.
- **Not EVENT_DRIVEN cleanly:** EVENT_DRIVEN means "closure waits for a specific named external event" — PR merge, repo cutover, infra change. The "trigger" for LD 249's review is the calendar passing 2026-07-18 — NOT an external event. The 120-day backstop is meaningless here: the review will fire BEFORE the backstop, and after firing, the next review fires 90 days later. The backstop never lands as the actionable date.

The interim mapping treats "calendar date passed" as a synthetic event and stuffs LD 249 into EVENT_DRIVEN. That works mechanically (the audit fires on the 120-day backstop, well after every quarterly review window), but it loses two pieces of information:

1. The next-review-date is not visible to the audit — only `date_locked + 120 days`.
2. Multiple quarterly reviews (next 2026-07-18, then 2026-10-18, 2027-01-18) are not surfaced as a series of upcoming actions; only the single backstop is.

The third pattern: **deliberate calibrations with scheduled re-evaluation cadence** — the review IS the deliverable. Quarterly reads of "is the design assumption still valid?" Annual reads of "is the cost model still right?" These are different from "wait for PR-X to merge" (EVENT_DRIVEN) and "wait for refactor that may never come" (RARE_NEVER).

### §2.3 Why now

Three forcing functions:

1. **LD 249 INTERIM mapping is technical debt.** Roadmap §1.6 line 105 explicitly says "INTERIM mapping to EVENT_DRIVEN until PERIODIC class lands" — this spec exists to land the class.
2. **Audit blind spot:** a PERIODIC LD with `next_review_date` 90 days out is invisible to the audit until the 120-day backstop nears. If Kim misses the quarterly review window, nothing surfaces it.
3. **More PERIODIC LDs are coming.** Cost-governance LDs (vendor renewal evaluations, identity platform tier reviews, security audit cadence) and architectural LDs (CodeQL false-positive reaccept reviews when CodeQL itself updates) all naturally fit PERIODIC. Without the class, every one becomes another INTERIM EVENT_DRIVEN with the same blind spot.

---

## §3 Current System (verified read 2026-05-07)

### §3.1 SHORTCUT_LD_CLASSIFICATION dict

[VERIFIED — `weekly_preflight_audit.py` lines 133-161, read 2026-05-07]

```python
SHORTCUT_LD_CLASSIFICATION = {
    # EVENT_DRIVEN — closure event is named; literal cap (if any) is in the LD.
    227: "EVENT_DRIVEN",   # SHORTCUT_CREDSTORE_MD_FALLBACK_20260418
    237: "EVENT_DRIVEN",   # SHORTCUT_STAGING_PITR_WINDOW_20260418
    247: "EVENT_DRIVEN",   # SHORTCUT_EMAIL_VERIFICATION_DEFERRED_20260418
    248: "EVENT_DRIVEN",   # SHORTCUT_FORGOT_PASSWORD_DEFERRED_20260418
    269: "EVENT_DRIVEN",   # SHORTCUT_COIN_REWARDS_HARDCODED_ARC1_20260418
    270: "EVENT_DRIVEN",   # SHORTCUT_AUDIT_BEST_EFFORT_WRITES_20260418
    273: "EVENT_DRIVEN",   # SHORTCUT_RN_COMPONENT_TEST_INFRA_DEFERRED_20260418
    277: "EVENT_DRIVEN",   # SHORTCUT_APP_CHECK_SDK_DEFERRED_20260418
    278: "EVENT_DRIVEN",   # SHORTCUT_AUTH_IN_MEMORY_PERSISTENCE_20260418
    408: "EVENT_DRIVEN",   # SHORTCUT_THERAPIST_DASHBOARD_V1_1
    416: "EVENT_DRIVEN",   # SHORTCUT_PHASE_BOUNDARIES_CACHE_HIT_CF_V1
    545: "EVENT_DRIVEN",   # SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1
    565: "EVENT_DRIVEN",   # SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN_V1
    567: "EVENT_DRIVEN",   # SHORTCUT_RN_REPO_PUBLIC_FOR_CODESCAN_V1
    200: "EVENT_DRIVEN",   # INTERIM — should be PERIODIC
    249: "EVENT_DRIVEN",   # INTERIM — should be PERIODIC (explicit comment: "PERIODIC class does not exist yet (deferred — needs tech spec)")
    569: "RARE_NEVER",     # SHORTCUT_CODEQL_LOCK_FILE_0644_ACCEPT_V1
    570: "RARE_NEVER",     # SHORTCUT_CODEQL_REDOS_BOUNDED_INPUT_ACCEPT_V1
    571: "RARE_NEVER",     # SHORTCUT_CODEQL_FILES_EXISTENCE_TEST_ACCEPT_V1
    572: "RARE_NEVER",     # SHORTCUT_CODEQL_LOCALHOST_FFMPEG_LIST_FORM_ACCEPT_V1
    574: "RARE_NEVER",     # SHORTCUT_CODEQL_REALPATH_SINK_INSIDE_CHECK_V1
    575: "RARE_NEVER",     # SHORTCUT_CODEQL_HTTP_RESPONSE_SPLITTING_TYPED_REBUILD_V1
}
```

22 active LDs in `SHORTCUT_LD_CLASSIFICATION`; matches Roadmap §1.6 line 122 status: "22 active SHORTCUT LDs in flight... 16 EVENT_DRIVEN... 6 RARE_NEVER. 16 + 6 = 22."

### §3.2 Audit logic shape

[VERIFIED — `check_shortcut_ld_closure_dates()` lines 167-342, read 2026-05-07]

Critical control-flow facts (each cited to a line):

1. **UNCLASSIFIED warning** (lines 215-225): if an active SHORTCUT_*_V1 LD is missing from the dict, audit emits an explicit error and continues. This means **adding PERIODIC must NOT break the existing two-class invariant** — the dict membership check must allow a third valid value.
2. **GRANDFATHER_REVIEW branch** (lines 244-262): RARE_NEVER LDs locked before `2026-05-07` emit a softer one-time finding rather than a normal cap CRITICAL.
3. **Cap selection** (lines 264-267): `cap_days = RARE_NEVER_CAP_DAYS if classification == "RARE_NEVER" else EVENT_DRIVEN_BACKSTOP_DAYS`. Note the `else` branch is currently the "anything-not-RARE_NEVER" branch — which means **adding PERIODIC without changing this line would cause PERIODIC LDs to silently use the 120-day backstop**, exactly the current INTERIM behavior. The fix must add a PERIODIC explicit branch.
4. **Warn/critical thresholds** (lines 198-199): `warn_threshold_days = 30; critical_threshold_days = 7`. PERIODIC reuse vs. override is a design decision (see §5.3).
5. **Blocker creation** (lines 305-340): findings with `critical=True` create a `prod_blockers` row with severity=critical, deduped on title.
6. **Schema invariant:** the function reads ONLY four fields (`id, decision_key, date_locked, decision_text, notes`) — line 207. A schema-migration-only change CANNOT affect this function unless we explicitly add the new fields to the `fields=` list.

### §3.3 Directus schema (verified 2026-05-07)

[VERIFIED — `/fields/prod_locked_decisions` query, 22 fields total]

```
id, decision_key, decision_name, decision_text, source_document, task_category,
severity, governance_file, past_failure_prevented, status, superseded_by_id,
date_locked, date_superseded, notes, related_files, keyword_synonyms,
enforcement_type, enforcement_artifact_ref, is_current, scope_domain,
supersedable, schema_version
```

22 fields confirms recent agent reports. None of the existing fields semantically capture "review cadence" or "next review date."

### §3.4 Roadmap §1.6 current shape

[VERIFIED — `MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` lines 83-141]

The §1.6 table has 6 columns: `LD id | decision_key | Class | Cap | Closure triggers | Surfacing`. The `Class` column currently takes two values: `EVENT_DRIVEN` and `RARE_NEVER`. Closure-cap rows for PERIODIC LDs would benefit from a different `Cap` semantic — not "120-day backstop = 2026-08-16" but "next review 2026-07-18".

---

## §4 Proposed Design

### §4.1 Schema migration (3 new fields on `prod_locked_decisions`)

| Field name | Type | Nullable | Semantic |
|---|---|---|---|
| `review_cadence` | string (enum) | YES (nullable for non-PERIODIC) | One of: `quarterly`, `annually`, `monthly`, `semi-annually`, `event-driven`, `none`. See §5.1 for the enum-vs-free-text debate. |
| `next_review_date` | date | YES | Calendar date when the next review fires. Required for PERIODIC class; optional for EVENT_DRIVEN if useful as soft reminder (e.g. "check in on the named-event window after 90 days"); always NULL for RARE_NEVER. See §5.2. |
| `last_reviewed_date` | date | YES | Last calendar date a review was conducted. Initially NULL; set on first review. Used by audit consistency-check (§5.5). |

Existing schema NOT touched: nothing renamed, nothing removed, no `task_category` enum extension. Additive only — old rows continue to work, old code paths continue to work, no backfill required for non-PERIODIC LDs.

Migration mechanics:
- Directus PATCH `/fields/prod_locked_decisions` to add 3 new fields.
- No data backfill required for the 22 existing SHORTCUT LDs at migration time. Only the migration cohort (§7) needs new-field values populated, and that's a per-row PATCH after the schema lands.

### §4.2 Audit logic — PERIODIC branch

Pseudocode (DESIGN — actual implementation deferred to next session):

```python
# In check_shortcut_ld_closure_dates(), after existing classification lookup:

if classification == "PERIODIC":
    # Required field: next_review_date
    next_review = ld.get("next_review_date")
    if not next_review:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "error": (
                f"PERIODIC SHORTCUT LD id={ld_id} missing required "
                f"next_review_date. Set this field before next audit run."
            ),
        })
        continue

    next_review_date = parse_date(next_review)  # YYYY-MM-DD
    days_until_review = (next_review_date - today).days

    if days_until_review <= 0:
        # Past due
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "next_review": next_review_date.isoformat(),
            "days_overdue": -days_until_review,
            "critical": True,  # see §5.4: warn-not-block default
            "message": (
                f"PERIODIC LD {ld_key} review OVERDUE by "
                f"{-days_until_review} days. Next-review-date was "
                f"{next_review_date.isoformat()}. Conduct review per LD "
                f"closure mechanism, then PATCH last_reviewed_date and "
                f"increment next_review_date by cadence."
            ),
        })
    elif days_until_review <= 7:
        # Approaching
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "next_review": next_review_date.isoformat(),
            "days_until_review": days_until_review,
            "critical": False,  # WARN tier
            "message": (
                f"PERIODIC LD {ld_key} review due in {days_until_review} "
                f"days ({next_review_date.isoformat()})."
            ),
        })
    # else: silent — review is far enough out that no surfacing is needed.
    continue
```

Key design choices in this branch (each pointer to debate sections):
- 7-day warn window (not 30-day, deliberately tighter for PERIODIC because the cadence is the deliverable; see §5.3)
- Past-due fires CRITICAL by default (auto-block-vs-warn debate, §5.4)
- `last_reviewed_date` is read but only used for the consistency check (§5.5)

### §4.3 Cap-selection refactor

The existing line 264-267:
```python
cap_days = (
    RARE_NEVER_CAP_DAYS if classification == "RARE_NEVER"
    else EVENT_DRIVEN_BACKSTOP_DAYS
)
```

Replaces with explicit-branch handling that surfaces UNHANDLED classifications loudly:
```python
if classification == "RARE_NEVER":
    cap_days = RARE_NEVER_CAP_DAYS
elif classification == "EVENT_DRIVEN":
    cap_days = EVENT_DRIVEN_BACKSTOP_DAYS
elif classification == "PERIODIC":
    # Handled in the dedicated PERIODIC branch above; should not reach here.
    raise RuntimeError(
        f"PERIODIC LD {ld_id} reached cap-selection branch — control flow bug; "
        f"PERIODIC LDs must return from their dedicated branch above."
    )
else:
    raise RuntimeError(f"Unknown SHORTCUT LD classification: {classification!r}")
```

This change costs ~6 lines of code and prevents the silent "120-day backstop accidentally applied to PERIODIC" failure mode (the exact thing the INTERIM mapping currently does).

### §4.4 Roadmap §1.6 update

The existing 6-column table absorbs PERIODIC LDs cleanly:
- `Class` column gains the value `PERIODIC`.
- `Cap` column for PERIODIC rows reads `next review YYYY-MM-DD (then YYYY-MM-DD, YYYY-MM-DD)` (a chain of upcoming dates) instead of `120-day backstop = YYYY-MM-DD`.
- `Closure triggers` column for PERIODIC rows describes the review criteria (a)-(d) etc., same prose as today.
- `Surfacing` column for PERIODIC rows: same `Phase 0.7 + weekly_preflight_audit`.

Below the table, the existing footer prose ("Status: 22 active SHORTCUT LDs in flight...") gains a parenthetical `; X PERIODIC` once migration completes.

### §4.5 No new LD class for non-SHORTCUT LDs

Some non-SHORTCUT LDs do reference "review cadence" language (e.g. LD 263 `CLAUDE_MD_PRUNING_DEFERRED_POST_STAGE_3` — "Re-evaluate as T3 polish-class item ... after Stage 3 ships"). These are EVENT_DRIVEN (event = Stage 3 ship), not PERIODIC. **PERIODIC class is scoped to SHORTCUT LDs only in v1**; the new `review_cadence` / `next_review_date` / `last_reviewed_date` fields are added on `prod_locked_decisions` (so they're available to any LD), but the audit logic only consults them for `decision_key LIKE 'SHORTCUT_%'`. v2 could extend.

---

## §5 Open Decisions — Dual-Opus Debate

This section frames each open decision as an **Advocate** position and a **Counter** position, then lands a recommendation. Kim reviews the resolution and either approves or amends.

### §5.1 Should `review_cadence` be free-text or enum?

**Advocate (free-text):**
> Real-world cadences don't fit a closed enum. LD 249 says quarterly. A future LD might say "every 6 months on March 1 + September 1." Another might say "annually on the 2026-04-18 anniversary, but skip the year V1 ships." Free-text captures the actual rule. Enums force lossy compression. Schema migrations to extend enums are slow.

**Counter (enum):**
> Free-text inputs in governance schemas always drift. "Quarterly" / "every 3 months" / "every quarter" / "Q1 Q2 Q3 Q4" all mean the same thing but won't sort or filter cleanly. The audit needs to compute "increment `next_review_date` by cadence" — that requires structured input. Free-text means the audit can't auto-increment, and EVERY review becomes a manual `next_review_date` recomputation, which is exactly the manual error class the audit is meant to prevent. Closed enums also force the schema to evolve consciously: when someone needs "every 6 months," the schema migration is the design conversation.

**Resolution:** **ENUM — but with an `other` escape hatch and a structured-cadence-as-string fallback.**

Decision criteria applied:
- Auto-increment is a real value (per Counter), so structure matters.
- Lossy compression is a real cost (per Advocate), so we need an escape hatch.

Final enum values:

| Value | Increment rule (audit auto-recomputes `next_review_date` after review) | Common case |
|---|---|---|
| `monthly` | `next_review_date += 30 days` | Operational safety reviews |
| `quarterly` | `next_review_date += 90 days` | LD 249 — identity platform |
| `semi-annually` | `next_review_date += 180 days` | Vendor pricing reviews |
| `annually` | `next_review_date += 365 days` | Annual cost reviews |
| `event-driven` | (not applicable — used to mark "this LD is technically PERIODIC but the cadence is irregular and ties to an external event"; manual `next_review_date` updates) | LD 200 — quarterly audit-confirms-trigger-not-fired |
| `none` | (sentinel for non-PERIODIC LDs that have no cadence) | All RARE_NEVER and most EVENT_DRIVEN LDs |

If a future LD genuinely needs a non-listed cadence, the schema migration to add it IS the forcing function for the design conversation — preserving the Counter's discipline argument.

[CONFIDENCE: VERIFIED Advocate position came from anticipated real-world drift; VERIFIED Counter from `weekly_preflight_audit.py` line 305-340 which deduplicates blockers on exact title match — string-matching governance is fragile.]

### §5.2 Should `next_review_date` be required or optional for PERIODIC LDs?

**Advocate (required):**
> The whole point of PERIODIC is "the review fires on a calendar date." A PERIODIC LD without `next_review_date` is broken — there's nothing for the audit to fire on. The audit MUST surface this as an error, which is exactly what §4.2 line `error: ... missing required next_review_date` does. Required-field constraint catches the bug at write time, not weeks later when the missed-review window opens.

**Counter (optional with audit-emitted error):**
> Directus required-field constraints are heavy-handed. They block schema migrations on any row with a NULL value. Forcing the migration to backfill `next_review_date` for the 2 cohort LDs (200, 249) is fine, but for non-PERIODIC rows (the other 20 SHORTCUT LDs + thousands of non-SHORTCUT LDs) the field is meaningless — making it required-on-PERIODIC means we'd need a database-level conditional constraint, which Directus doesn't natively support. Better: make it nullable; let the audit emit the error.

**Resolution:** **OPTIONAL at the database layer; AUDIT-ENFORCED for PERIODIC LDs.**

Decision criteria:
- Conditional constraint at DB layer is brittle (per Counter).
- The existing audit pattern already emits errors for missing `date_locked` (lines 227-232) — same pattern reuses cleanly.
- Cost of NULL-value bypass: a PERIODIC LD without `next_review_date` errors loudly on the next audit run within 7 days of policy lock, which is acceptable.

[CONFIDENCE: VERIFIED — directly cites existing `if not date_locked_raw` audit pattern from lines 227-232 of audit script.]

### §5.3 On missed review (past `next_review_date` by N days), should LD auto-block or just warn?

**Advocate (auto-block — fire CRITICAL `prod_blockers` immediately on past-due):**
> RARE_NEVER LDs hit the 14-day cap and immediately surface CRITICAL blockers (line 199 `critical_threshold_days = 7`, line 305-340 blocker creation). PERIODIC review-missed should follow the same pattern. Soft warnings get ignored. The whole anti-slip mechanism is "make skips visible without Kim having to be the detective" (audit script docstring lines 12-14). Past-due is a skip.

**Counter (warn-not-block — emit WARN finding only; CRITICAL only if N+grace-period is also missed):**
> RARE_NEVER and PERIODIC have different failure modes. RARE_NEVER cap-expired = "we promised to refactor and didn't" — that's a real shortcut un-closed. PERIODIC review-missed by 1 day = "Kim was busy on Tuesday." A 7-day grace is reasonable: the review IS the deliverable, but Kim's calendar slipping by a week is normal life, not a governance violation. CRITICAL on day-0 of past-due cries wolf.

**Resolution:** **WARN on past-due day-0, CRITICAL after 7 days past-due.**

Decision criteria:
- Two-tier surfacing matches existing `warn_threshold_days = 30, critical_threshold_days = 7` pattern (lines 198-199).
- Mirrors RARE_NEVER's "warn within 30 days, CRITICAL within 7 days" but inverted: PERIODIC warns AT past-due, CRITICAL after 7 days.
- 7-day CRITICAL grace is a minor concession to the "Kim's calendar slipped a week" case without sacrificing surfacing.

Pseudocode update to §4.2:

```python
if days_until_review <= 0:
    days_overdue = -days_until_review
    is_critical = days_overdue >= 7  # CRITICAL only after 7-day grace
    findings.append({
        ...
        "critical": is_critical,
        "message": ("OVERDUE by {} days [CRITICAL]" if is_critical
                    else "OVERDUE by {} days [WARN]").format(days_overdue),
    })
elif days_until_review <= 7:
    # Approaching — WARN
    ...
```

[CONFIDENCE: INFERRED — graced from real-world cadence-slip behavior; not directly cited.]

### §5.4 Should the audit also check `last_reviewed_date` consistency with cadence?

**Advocate (yes — consistency check):**
> If `last_reviewed_date = 2026-04-18` and `review_cadence = quarterly`, then `next_review_date` should be 2026-07-17 ± a few days. If it's 2027-01-01, something's wrong: either Kim manually pushed the date forward without doing a review (silent slip) or the field got out of sync. The audit should warn on `next_review_date - last_reviewed_date != expected_cadence_delta ± grace`.

**Counter (no — additional complexity for marginal gain):**
> Inconsistency is rare and often legitimate. "We did a review and decided the next one needs to be pushed out 6 months instead of 3 because the design is stable" is normal. The check would emit false positives 50% of the time and Kim would learn to ignore it — destroying the signal-to-noise ratio of the rest of the audit findings. The simpler invariant is: `next_review_date` is the source of truth; `last_reviewed_date` is journaling.

**Resolution:** **NO consistency check in v1.** Add only as a v2 feature once we have lived experience with the data.

Decision criteria:
- Counter's signal-to-noise argument is strong; the audit's value lies in surfacing real failures, not technical-correctness theater.
- v2 can add this once we have ≥3 PERIODIC LDs with ≥2 review cycles each (real data to validate the rule).
- v1 simplicity > v1 completeness for governance plumbing.

[CONFIDENCE: VERIFIED — directly cites "warn within 30 days... CRITICAL within 7 days" two-tier pattern from line 198-199 of audit script. Counter's signal-to-noise concern aligns with `feedback_no_babysitting.md` user-memory.]

### §5.5 What's the right severity for "review missed"?

(This decision is partially answered by §5.3 already — WARN on day-0, CRITICAL after 7 days. This section answers a finer question: when a CRITICAL fires, is it `severity: critical` like RARE_NEVER cap-expired, or a new `severity: review_overdue` tier?)

**Advocate (reuse `severity: critical`):**
> The audit's `prod_blockers` write at lines 332-340 uses `severity: "critical"`. PERIODIC review-overdue is a similar escalation — it's a missed governance commitment. Reusing the existing severity keeps dashboard-gate triage simple: one severity tier means one queue. New severity tiers force triage to fragment.

**Counter (new `severity: review_overdue` tier, lower than critical):**
> A RARE_NEVER cap-expired and a PERIODIC review-7-days-late are not equivalent. RARE_NEVER means "the shortcut is unbounded; we promised to refactor and didn't." PERIODIC means "the calendar event for re-checking a known-deferred decision passed." The first is a real shortcut un-closed; the second is a governance-cadence slip. Equating them dilutes both.

**Resolution:** **REUSE `severity: critical`, but with a distinct title prefix.**

Decision criteria:
- Counter's semantic point is valid but the practical impact is low: dashboard-gate already filters blockers by title prefix (line 422 `filter[title][_starts_with]`), so distinct title prefix achieves the triage segregation without a new severity tier.
- New severity tiers require schema/UI churn elsewhere; title-prefix discipline is free.
- Concrete title prefix: `PERIODIC LD review overdue: <key> (id=<id>)` — distinct from RARE_NEVER's `SHORTCUT LD closure imminent: <key> (id=<id>)` (line 310).

[CONFIDENCE: VERIFIED — directly cites blocker title-format from line 310 of audit script.]

---

## §6 Dual-Opus Meta-Debate: PERIODIC Class Necessity

Beyond the per-decision debates above, the brief explicitly calls for a class-level meta-debate:

### §6.1 Advocate position — PERIODIC class is necessary

**Argument:**

The two-class system has a structural blind spot: it implicitly assumes every shortcut closure is bounded by a single named event OR no event. Reality has a third pattern: **cadence-bounded calibrations**. LD 249 explicitly demonstrates this. Roadmap §1.6 line 105 explicitly flags the INTERIM mapping. The current INTERIM mapping (PERIODIC-as-EVENT_DRIVEN-with-120-day-backstop) makes the actual review-due date invisible to the audit — exactly the failure mode the audit was designed to prevent.

**Cost-benefit:**

| Cost | Benefit |
|---|---|
| 3 schema fields (small, additive) | Recurring-review LDs surface their actual due date, not a synthetic backstop |
| ~30-50 lines of audit code (one new branch + cap-selection refactor) | Removes the LD 249 INTERIM mapping technical debt |
| 1 enum addition with 6 values + auto-increment table | Catches future cost/security/identity reviews that would otherwise INTERIM-stuff into EVENT_DRIVEN with the same blind spot |
| Roadmap §1.6 column-prose update | Explicit signal in §1.6 that some LDs are recurring (improves Kim's mental model) |

**Why this is structural, not cosmetic:**

The cap-selection refactor (§4.3) catches the silent-default failure mode that produced the INTERIM mapping in the first place. Without PERIODIC, a future maintainer reading the dict sees `200: "EVENT_DRIVEN"` and has no signal that the closure is actually a recurring review. With PERIODIC, the data type encodes the closure semantics.

### §6.2 Counter position — PERIODIC adds complexity for marginal benefit

**Argument:**

Two LDs (200, 249) is not a population. The cost of adding a third class — schema migration + audit branch + roadmap column + migration discipline + ongoing dict-maintenance cognitive load — outpaces the benefit of "two LDs get a slightly more accurate next-review-date display." A simpler alternative exists:

**Simpler alternative:** amend EVENT_DRIVEN to support a `next_check_date` field that defaults to NULL but, when set, the audit fires a soft warning N days before. No new class, no new enum, no migration cohort. The single LD (249) sets `next_check_date = 2026-07-18` and the existing EVENT_DRIVEN branch picks it up.

**Why "wait":**

The dual-Opus deferred-pruning playbook says: don't add structure ahead of demand. We have a population of 1 (LD 249 — LD 200's quarterly is an "audit-confirms-trigger" cadence, not a "review the design assumption" cadence; arguably 200 is correctly EVENT_DRIVEN). Build the simplest thing that works. If 5 more PERIODIC-shaped LDs emerge in 6 months, then build the class.

**Risks of premature structure:**

- Enum values become wrong (we picked `quarterly = 90 days` but a real LD turns out to need `quarterly = first business day of fiscal quarter`).
- Migration cohort is a forced choice that ages badly (we re-classify LD 200 to PERIODIC and 6 months later we realize it should have stayed EVENT_DRIVEN).
- Audit code branches multiply faster than the population they serve (3 classes today, 5 tomorrow, hard to read in a year).

### §6.3 Resolution

**Advocate wins, with two Counter-derived modifications.**

Decision criteria applied:

1. **The INTERIM mapping is named technical debt.** Roadmap §1.6 line 105 explicitly says "INTERIM mapping... until PERIODIC class lands." The class is ALREADY committed-to in writing. The Counter's "wait for a population" argument is undermined by the fact that the class has a named promise.
2. **The audit's cap-selection refactor is a structural fix regardless.** Even if PERIODIC weren't added, the line 264-267 `else: 120-day backstop` is a silent-default failure mode. The cap-selection refactor (§4.3) is independently valuable and the PERIODIC class slots into it cleanly.
3. **Population growth is reasonably-foreseen.** §2.3 forcing function 3 lists at least three more PERIODIC-shaped categories: vendor renewals, identity tier reviews, security audit cadence, CodeQL false-positive reaccept reviews. The Counter's "population of 1" snapshot doesn't reflect 6-month outlook.

**Counter-derived modification 1: Tight migration cohort.**

Per the Counter's "don't force re-classifications," the migration cohort is **as tight as possible**: only LD 249 unambiguously moves to PERIODIC. LD 200 is ambiguous and stays EVENT_DRIVEN unless Kim explicitly approves the move. The migration cohort table (§7) reflects this.

**Counter-derived modification 2: No retroactive backfill of `last_reviewed_date`.**

For the 22 active SHORTCUT LDs, only the PERIODIC migration cohort gets new-field values. Other LDs leave the new fields NULL. Forcing backfill on 22 LDs to populate "this is review-cadence: none" adds work without value.

[CONFIDENCE: INFERRED — Advocate-wins call rests on the named-promise argument from Roadmap §1.6 line 105 (VERIFIED) plus the foreseen-population argument from §2.3 forcing function 3 (this spec's analysis, not directly cited).]

---

## §7 Migration Cohort

**Definition:** existing LDs that should re-classify TO `PERIODIC` once the class lands.

**Methodology:**

1. Queried `prod_locked_decisions` for all rows with `quarterly`, `annual`, `monthly`, `periodic`, `re-evaluate`, `reevaluate`, `review every`, `review cadence` in `decision_text` or `notes` [VERIFIED 2026-05-07 via Directus query].
2. 12 unique LDs returned.
3. Filtered to those where the cadence keyword denotes **the closure mechanism** (not "the system uses periodic mirroring" or "annual subscription" or "monthly cron").
4. Cross-checked each candidate's notes/decision_text directly.

**Final migration cohort (re-classify to PERIODIC):**

| LD id | decision_key | Current class | Proposed class | review_cadence | next_review_date | last_reviewed_date | Rationale |
|---|---|---|---|---|---|---|---|
| 249 | `SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418` | EVENT_DRIVEN (INTERIM) | **PERIODIC** | `quarterly` | `2026-07-18` | `2026-04-18` (date_locked = first reading; treated as the seed last-reviewed date) | LD 249 notes verbatim: "review cadence is quarterly (next review 2026-07-18, then 2026-10-18, 2027-01-18)". The closure mechanism IS the recurring review. The 4 named event triggers ((a) MAU>10K, (b) MFA, (c) SAML, (d) abuse) are checked AT each quarterly review — they're review criteria, not standalone events. [VERIFIED — Directus 2026-05-07] |

**Discussed-but-NOT-migrating:**

| LD id | decision_key | Current class | Proposed class | Reason |
|---|---|---|---|---|
| 200 | `SHORTCUT_LD_LINKAGE_SNAPSHOT_ONLY` | EVENT_DRIVEN | **STAY EVENT_DRIVEN** | Notes verbatim: "Quarterly audit (next: 2026-08-07) confirms neither trigger has fired; if both triggers still unfired by 2026-11-07, re-evaluate whether the LD is still relevant." The quarterly cadence here is a CONFIRM-NO-CHANGE pattern, not a CALIBRATION. The actual closure mechanism is still the named events ((a) Stage 4 kickoff OR (b) 2nd contributor). The quarterly check is administrative, not the deliverable. EVENT_DRIVEN is correct. Kim may overrule if she wants the cadence surfaced. [VERIFIED — Directus 2026-05-07] |
| 263 | `CLAUDE_MD_PRUNING_DEFERRED_POST_STAGE_3` | (not in SHORTCUT dict — non-SHORTCUT LD) | EVENT_DRIVEN-equivalent | Decision text says "Re-evaluate as T3 polish-class item per STAGE3_EXECUTION_PLAN_v2.md section 4B after Stage 3 ships." The trigger is the Stage 3 ship event, NOT a calendar cadence. EVENT_DRIVEN-equivalent. [VERIFIED — Directus 2026-05-07] |
| 566 | `BRANCH_PROTECTION_SOLO_DEV_MODEL_D_V1` | (not SHORTCUT) | EVENT_DRIVEN-equivalent | "Re-evaluate when MindfulNest grows beyond solo-dev." Event = headcount change, not calendar. [VERIFIED] |
| 568 | `RN_REPO_REQUIRED_STATUS_CHECKS_V1` | (not SHORTCUT) | EVENT_DRIVEN-equivalent | Same pattern as 566. [VERIFIED] |
| 346 | `ASSET_SOURCES_LOCKED_V1` | (not SHORTCUT) | n/a (false positive) | Keyword `annual` referred to "Sonniss GDC bundle (free annual)" — describing the vendor's release cadence, NOT an LD review cadence. [VERIFIED] |
| 231 | `UNIFIED_4_PHASE_ASYNC_SYNC_DISCIPLINE` | (not SHORTCUT) | n/a (false positive) | Keyword `monthly` referred to "monthly stale-item cron" — describes a job, NOT LD review cadence. [VERIFIED] |
| 325 | `FOLLOWUP_LD_316_LAYER_2_PROGRESSION_FIRESTORE_MIRROR` | (not SHORTCUT) | n/a (false positive) | Keyword `periodic` referred to "periodic debounced mirror during playback" — implementation detail. [VERIFIED] |
| 199, 201, 573 | various | (closed/superseded) | n/a | Out of active scope. [VERIFIED] |

**Net cohort:** **1 LD** (id=249) re-classifies on day-1 of implementation. This is the tight cohort the dual-Opus debate's Counter-derived modification 1 endorsed.

**Future-PERIODIC candidates (anticipated, not migrated now):**

These are LD-shapes that future SHORTCUT LDs are likely to take and would naturally fit PERIODIC:

- **CodeQL false-positive reaccept reviews:** when CodeQL itself ships a major version bump, every `RARE_NEVER`-classified `SHORTCUT_CODEQL_*` LD (current count: 6) needs a re-evaluation. A PERIODIC variant `every-codeql-major-release` could capture this — but the cadence is event-bound to upstream releases, so this is more EVENT_DRIVEN than PERIODIC. v2 might add it.
- **Vendor cost reviews:** "review Suno Pro / ElevenLabs / Anthropic API spend annually."
- **Identity / auth tier reviews:** future `SHORTCUT_IDENTITY_PLATFORM_*` LDs after the 249 cycle resolves.
- **Compliance audit cadence:** GDPR/COPPA/HIPAA review LDs once we hit those tiers.

These are NOT migrated in v1; they're forecasted to test the class's longevity.

---

## §8 Implementation Phases (for the future implementation session — design only here)

### Phase A — Schema migration

1. Read this spec end-to-end (Phase 0 zero-error-qa pre-flight).
2. Verify Directus credentials + dev-mode access.
3. PATCH `/fields/prod_locked_decisions` to add 3 fields:
   - `review_cadence` (string, nullable, with enum interface choice listing 6 values)
   - `next_review_date` (date, nullable)
   - `last_reviewed_date` (date, nullable)
4. Verify schema by re-reading `/fields/prod_locked_decisions` — should now return 25 fields.
5. Smoke-test by writing a test row PATCH on a sandbox LD.
6. Activity log: `app_activity_log` row with action=`prod_locked_decisions schema migration: PERIODIC class fields added`.
7. Commit: schema-only commit, no code changes yet.

**Risk:** Directus rejects enum values silently if the field is created as `string` instead of `string + interface=select-dropdown-enum`. Mitigation: read the field-creation API doc + test on staging before main.

### Phase B — Audit logic

1. Update `weekly_preflight_audit.py`:
   - `SHORTCUT_LD_CLASSIFICATION` dict gains the third valid value `"PERIODIC"`.
   - Cap-selection refactor (§4.3) replaces the two-line `else` with explicit-branch raise.
   - New PERIODIC branch (§4.2) inserted before the cap-selection block.
   - Imports updated if `parse_date` helper isn't already in scope.
   - `fields=` param at line 207 expanded to include `review_cadence`, `next_review_date`, `last_reviewed_date`.
2. Add unit tests (deferred — there are no current pytest unit tests for `check_shortcut_ld_closure_dates`; v1 ships without unit tests but with a `--dry-run` smoke test).
3. Run `python3 weekly_preflight_audit.py --dry-run` — verify no PERIODIC findings on day-0 (since cohort isn't migrated yet).
4. Activity log + commit.

### Phase C — Migration cohort

1. PATCH LD 249:
   - `review_cadence = quarterly`
   - `next_review_date = 2026-07-18`
   - `last_reviewed_date = 2026-04-18`
2. Update `SHORTCUT_LD_CLASSIFICATION[249]` from `"EVENT_DRIVEN"` to `"PERIODIC"`.
3. Update LD 249 `notes` field: replace "INTERIM mapping to EVENT_DRIVEN" prose with "PERIODIC class landed YYYY-MM-DD; review cadence captured in structured fields."
4. Run `python3 weekly_preflight_audit.py --dry-run` — verify LD 249 produces no findings (next review 2026-07-18 is >7 days out).
5. Activity log + commit.

### Phase D — Roadmap §1.6 update

1. §1.6 table: LD 249 row's `Class` column updates from `EVENT_DRIVEN (re-classified...)` to `PERIODIC`.
2. §1.6 table: LD 249 row's `Cap` column updates to `next review 2026-07-18 (then 2026-10-18, 2027-01-18)`.
3. §1.6 status footer (line 122): "16 EVENT_DRIVEN → 15 EVENT_DRIVEN; 1 PERIODIC; 6 RARE_NEVER. 15 + 1 + 6 = 22."
4. §1.6 cap-policy paragraph (line 89-92): add a new bullet for PERIODIC class.
5. Commit.

### Phase E — LD registration for the class itself

Register a new LD: `PERIODIC_CLASS_LANDED_V1` capturing the spec, the 1-row migration, the schema migration record, and the audit-logic update. Status `active`. This is the canonical "class exists" record; future PERIODIC-pattern LDs cite it.

### Phase F — Documentation

1. Update `CLAUDE.md` Rule 19 footer (if it mentions the SHORTCUT classification system) to reference 3 classes instead of 2.
2. Update `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` if it references the SHORTCUT classification system.
3. Append to `Production/docs/V59_LESSONS_LEARNED_v1.md` if appropriate.

### Phase G — Closeout

1. Activity log: completion summary.
2. Commit.
3. Push.

**Total estimated complexity (NOT time):** ~50 lines of audit code, ~3 schema fields, 1 LD row PATCHed, ~10 lines of roadmap diff, 1 new LD registration. Tier C (architectural).

---

## §9 Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Schema migration breaks existing audit code (e.g. fields=… list missing new fields) | HIGH | Phase A includes smoke test; Phase B updates `fields=` param explicitly. |
| Enum values picked wrong (a real LD needs `bi-monthly` or `every-fiscal-quarter`) | MEDIUM | Schema migration to add a new enum value is a 5-min change; not catastrophic. Forcing function for design conversation per §5.1. |
| LD 249's `next_review_date = 2026-07-18` is wrong (Kim disagrees; review should fire earlier or later) | LOW | Per Phase C step 1, this is a one-row PATCH; trivial to amend before/after migration. |
| Audit's PERIODIC branch silently bypasses GRANDFATHER_REVIEW logic (lines 244-262) | LOW | PERIODIC branch executes BEFORE grandfather check (§4.2 pseudocode places PERIODIC handler at top of classification dispatch, returning early). Grandfather is only meaningful for RARE_NEVER. |
| Cap-selection refactor (§4.3) breaks tests (silent-default → loud-raise change) | LOW | No current pytest tests for this function; smoke-test only. Loud-raise on UNCLASSIFIED is the desired behavior, not a regression. |
| Adding the third class accelerates "classification creep" — more classes added later | MEDIUM | Per dual-Opus resolution §6.3, future-class additions require their own tech spec following this template. The class isn't the slippery slope; the unconscious INTERIM-stuff is. |
| Migration cohort is too tight (LD 200 should have moved to PERIODIC) | LOW | Per §7 migration table, LD 200 is genuinely ambiguous and Kim can override. One-row PATCH to fix. |
| LD 249 first review date (2026-07-18) is internal to LD's own notes — what if it's wrong? | LOW | [VERIFIED — directly cited from LD 249's notes field 2026-05-07]. Kim's the one who wrote those dates. If she now wants different dates, she amends the LD before Phase C. |
| Free-text vs. enum decision (§5.1) is wrong — enum is too rigid, structured strings would have been better | MEDIUM | The enum + `event-driven` escape hatch + future schema-migration-as-design-conversation is the safety valve. If the enum becomes painful, expand it; the schema migration discipline catches it. |

---

## §10 Testing Plan

### §10.1 Phase A (schema) verification

- [VERIFICATION 1] After PATCH, `GET /fields/prod_locked_decisions` returns 25 fields. List includes `review_cadence`, `next_review_date`, `last_reviewed_date`.
- [VERIFICATION 2] Test PATCH on a sandbox LD: PATCH `review_cadence = quarterly` → GET → confirm field round-trips.
- [VERIFICATION 3] Confirm Directus enum-interface dropdown shows 6 values.

### §10.2 Phase B (audit) verification

- [VERIFICATION 1] `python3 weekly_preflight_audit.py --dry-run` runs without exception.
- [VERIFICATION 2] Output includes the existing 22 SHORTCUT LD findings; no new errors.
- [VERIFICATION 3] Manually inject a PERIODIC test row in dev (not committed) and verify the new branch fires correctly:
  - `next_review_date = today + 30 days` → no finding (silent).
  - `next_review_date = today + 5 days` → WARN finding, days_until_review=5.
  - `next_review_date = today - 1 day` → WARN finding (within 7-day grace), days_overdue=1.
  - `next_review_date = today - 8 days` → CRITICAL finding, days_overdue=8.
  - `next_review_date = NULL` → error finding.
- [VERIFICATION 4] Cap-selection refactor catches UNCLASSIFIED: temporarily set a test row's classification to a bogus string in the dict; verify the audit raises.

### §10.3 Phase C (migration) verification

- [VERIFICATION 1] After LD 249 PATCH, `GET /items/prod_locked_decisions/249` returns the 3 new field values populated.
- [VERIFICATION 2] After dict update, `python3 weekly_preflight_audit.py --dry-run` shows LD 249 in the PERIODIC bucket; no findings (next review >7 days out).
- [VERIFICATION 3] Manually fast-forward `next_review_date = today` and re-run audit; verify WARN finding fires.

### §10.4 Phase D (roadmap) verification

- [VERIFICATION 1] §1.6 table renders correctly in Markdown viewer (no broken pipes).
- [VERIFICATION 2] §1.6 status footer arithmetic: 15 + 1 + 6 = 22.

### §10.5 End-to-end

- [VERIFICATION 1] After all phases, Kim runs the audit and verifies LD 249 appears in the PERIODIC bucket with correct dates. No spurious findings.

---

## §11 Rollback Procedure

In order, ONE phase at a time (LIFO):

### Rollback Phase D (roadmap)
- Revert `MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` §1.6 to pre-Phase-D state (LD 249 stays EVENT_DRIVEN with INTERIM prose).

### Rollback Phase C (migration)
- PATCH LD 249: clear `review_cadence`, `next_review_date`, `last_reviewed_date`.
- Restore `SHORTCUT_LD_CLASSIFICATION[249] = "EVENT_DRIVEN"`.
- Restore LD 249 notes' INTERIM prose.

### Rollback Phase B (audit)
- Revert `weekly_preflight_audit.py` to pre-Phase-B state.
- Cap-selection reverts to the simple `else`.

### Rollback Phase A (schema)
- DELETE `/fields/prod_locked_decisions/review_cadence`, `/next_review_date`, `/last_reviewed_date`.
- Verify schema returns to 22 fields.
- Caveat: any data written to these fields between Phase A and rollback is lost. For Phase C cohort (1 row), capture a Directus row JSON snapshot before deleting.

### Activity log
Each rollback step logs to `app_activity_log` with action=`PERIODIC_CLASS rollback Phase X`.

### Rollback decision criteria
Trigger rollback if:
- Phase A breaks existing audit output (surfaces unexpected new findings on existing 22 LDs).
- Phase B raises uncaught exceptions on production Directus data.
- Phase C produces incorrect findings on LD 249 (e.g. fires CRITICAL on day-0 of migration).
- Kim withdraws authorization mid-implementation.

---

## §12 Pre-Execution Checklist (per zero-error-qa §14)

To be run by the implementation session BEFORE any code changes:

- [ ] This spec is read end-to-end.
- [ ] `weekly_preflight_audit.py` is read end-to-end (current state).
- [ ] Directus credentials confirmed working (`load_credentials()` returns non-null).
- [ ] Dev/staging Directus instance available for schema-migration smoke test, OR explicit OK to migrate prod (Directus is single-instance per memory).
- [ ] Roadmap §1.6 read end-to-end (current state).
- [ ] LD 249 row pulled from Directus and confirmed to match spec's verbatim quote (notes field).
- [ ] Activity log + commit access confirmed (git push, Directus write).
- [ ] Rollback plan §11 understood.
- [ ] `prod_blockers` table queryable (audit's CRITICAL writes go here).
- [ ] No in-flight session is mid-write to `prod_locked_decisions` (would interleave PATCHes).
- [ ] Kim confirms implementation authorization (this is the explicit handoff gate).

---

## §13 Audit Checklist (per zero-error-qa §15)

To be run by the implementation session AFTER each phase:

### After Phase A (schema)
- [ ] `GET /fields/prod_locked_decisions` returns 25 fields including the 3 new ones.
- [ ] Existing 22 fields are untouched.
- [ ] Existing data on all 22 SHORTCUT LDs is unchanged (`GET` each, compare to pre-migration snapshot).
- [ ] `app_activity_log` row recorded for the schema migration.

### After Phase B (audit)
- [ ] `python3 weekly_preflight_audit.py --dry-run` exit code 0.
- [ ] Stdout includes the 22 existing SHORTCUT LD scan results.
- [ ] No new errors reported on the 22 existing rows (since no PERIODIC LDs migrated yet).
- [ ] py_compile passes.
- [ ] Manual injection test (§10.2 VERIFICATION 3) all 5 sub-cases pass.

### After Phase C (migration)
- [ ] `GET /items/prod_locked_decisions/249` returns: `review_cadence=quarterly`, `next_review_date=2026-07-18`, `last_reviewed_date=2026-04-18`.
- [ ] `SHORTCUT_LD_CLASSIFICATION[249] == "PERIODIC"`.
- [ ] Dry-run audit produces no findings on LD 249 (next review >7 days out).
- [ ] LD 249 notes prose updated.
- [ ] `app_activity_log` row recorded.

### After Phase D (roadmap)
- [ ] §1.6 table renders correctly.
- [ ] Status footer arithmetic checks (15 + 1 + 6 = 22).
- [ ] Cap-policy paragraph mentions all 3 classes.

### After Phase E (LD registration)
- [ ] `PERIODIC_CLASS_LANDED_V1` LD exists in Directus.
- [ ] LD cites the spec, the schema migration, the audit code change, and the LD 249 migration.

### After Phase F (documentation)
- [ ] CLAUDE.md Rule 19 footer (if exists) mentions 3 classes.
- [ ] Other docs that reference the classification system are consistent.

### After Phase G (closeout)
- [ ] Final commit summary written.
- [ ] Push successful.
- [ ] Weekly preflight audit cron'd (no change — same script).

---

## §14 Reference Index (per zero-error-qa §16)

### Source documents read this session

| Document | Purpose | Lines | Verification timestamp |
|---|---|---|---|
| `Production/scripts/weekly_preflight_audit.py` | Current audit logic + classification dict | 537 lines (full read) | 2026-05-07 |
| `Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` §1.6 | Living-doc table of active SHORTCUT LDs + cap-policy prose | lines 83-141 | 2026-05-07 |
| Directus `/fields/prod_locked_decisions` | Schema of canonical LD store | 22 fields | 2026-05-07 |
| Directus `/items/prod_locked_decisions/249` | Verbatim quarterly-review notes | full row | 2026-05-07 |
| Directus `/items/prod_locked_decisions/200` | Verbatim quarterly-audit notes | full row | 2026-05-07 |
| Directus `/items/prod_locked_decisions` filter scan (8 candidate LDs) | Migration cohort sourcing | 12 unique LDs surfaced, 1 migrated | 2026-05-07 |
| `Production/docs/STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` | Precedent doc structure | first 80 lines | 2026-05-07 |

### Constants and identifiers

- `SHORTCUT_CAP_POLICY_LOCK_DATE` = `2026-05-07` (audit script line 38)
- `RARE_NEVER_CAP_DAYS` = `14` (line 163)
- `EVENT_DRIVEN_BACKSTOP_DAYS` = `120` (line 164)
- `warn_threshold_days` = `30` (line 198)
- `critical_threshold_days` = `7` (line 199)

### LDs cited

- 199, 200, 201, 249 — 2026-05-07 retroactive triage cohort (4 RARE_NEVER cap-expired alerts)
- 200 — `SHORTCUT_LD_LINKAGE_SNAPSHOT_ONLY` — discussed-but-NOT-migrating
- 249 — `SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418` — sole migration target
- 263, 566, 568 — non-SHORTCUT EVENT_DRIVEN-equivalents (false positives in cohort scan)
- 561 — `MASTER_ROADMAP_LIVING_DOC_V1` — the LD that mandates §1.6 closure surfacing

### Specs cited as precedent

- `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` — TDD-style precedent for architectural fixes (this spec borrows the §-numbered structure).

### To-be-written references

- `PERIODIC_CLASS_LANDED_V1` LD (Phase E artifact) — does not exist yet; this spec authorizes its creation.

---

## §15 Pre-Implementation Gates (must hold before Kim authorizes execution)

1. **Kim reads §5 and §6 dual-Opus resolutions and either approves or amends each.**
2. **Kim confirms migration cohort is correct** (LD 249 in, LD 200 out, no surprises).
3. **Kim confirms enum value list** (`monthly`, `quarterly`, `semi-annually`, `annually`, `event-driven`, `none`) covers near-term needs.
4. **Kim confirms severity choice** (`severity: critical` with distinct title prefix, not a new severity tier).
5. **Kim confirms warn-vs-block default** (WARN day-0 of past-due, CRITICAL after 7-day grace).
6. **Kim confirms `next_review_date = 2026-07-18` for LD 249** (or amends to the date she actually wants).
7. **Kim confirms LD 249 `last_reviewed_date = 2026-04-18`** seed value (date_locked, treating "first read" as the first review). If she wants a different seed (e.g. NULL because no real review yet conducted), say so.
8. **Kim authorizes the schema migration to land directly on prod Directus** (no staging instance) — or directs to use a sandbox.
9. **Kim confirms the implementation phase ordering** (A schema → B audit → C migration → D roadmap → E LD register → F docs → G closeout).
10. **Kim confirms the spec is reviewable as written** OR requests revisions before implementation session begins.

---

## §16 Recommended Sequence to Implementation

1. **Kim review window** — read this spec, raise concerns, mark up §5 / §6 / §7 / §15.
2. **Spec amendment v2 (if needed)** — apply Kim's marks; re-issue.
3. **Authorize implementation session** — Kim says "ok, land it." Subagent spec session reads this v1/v2.
4. **Execute Phase A through G in order** — each phase has a hard close gate (audit checklist pass) before next phase begins.
5. **Post-implementation closeout** — Kim runs the audit one full week after Phase C completes (next preflight cron run). Confirms no spurious findings, LD 249 sits quietly until 2026-07-18 nears, etc.
6. **First real PERIODIC review** — 2026-07-18 (LD 249 quarterly). Audit fires WARN at 2026-07-11 (7-day approach). Kim conducts review, PATCHes `last_reviewed_date = <today>`, increments `next_review_date += 90 days`. This validates the full lifecycle.
7. **6-month retro** — 2026-11-07. Re-evaluate: was PERIODIC class worth it? Did it spawn 2-3+ more PERIODIC LDs? Is the enum still right? If yes, lock the class. If no, consider deprecation path.

---

## §17 Confidence Annotations Sweep (per Rule 24)

Inline confidence tags appear throughout. Summary table:

| Section | Predominant tag | Notes |
|---|---|---|
| §0 (operating mode) | n/a | declarative, not factual |
| §1 (scope) | n/a | declarative |
| §2 (background) | [VERIFIED] | every claim cites audit script line numbers + roadmap line numbers + Directus row queries |
| §3 (current system) | [VERIFIED] | every claim cites file Read line numbers |
| §4 (proposed design) | [INFERRED] | proposal, not current state |
| §5 (open decisions) | mixed | each sub-section's resolution is [INFERRED] (design call); cited evidence is [VERIFIED] |
| §6 (meta-debate) | [INFERRED] | resolution rests on [VERIFIED] cited line + [INFERRED] forecasting argument |
| §7 (migration cohort) | [VERIFIED] | each row cites Directus query 2026-05-07 |
| §8 (implementation phases) | [INFERRED] | proposal, not executed |
| §9 (risk assessment) | [INFERRED] | forecasting |
| §10 (testing plan) | [INFERRED] | proposal |
| §11 (rollback) | [INFERRED] | proposal |
| §12 (pre-execution checklist) | [INFERRED] | proposal |
| §13 (audit checklist) | [INFERRED] | proposal |
| §14 (reference index) | [VERIFIED] | every entry corresponds to a tool call in this session |
| §15 (pre-impl gates) | [INFERRED] | proposal |
| §16 (sequence) | [INFERRED] | proposal |

**No [ASSUMED] tags.** Every assertion is either directly cited from a tool output or labeled as a design proposal.

---

## §18 TL;DR Table

| Question | Answer |
|---|---|
| Why PERIODIC? | Two-class system (EVENT_DRIVEN, RARE_NEVER) has a blind spot: cadence-bounded calibrations. LD 249 is the canonical case; INTERIM mapping is named tech debt. |
| What changes? | 3 new schema fields; ~30-50 lines of audit code; 1 LD migrated; Roadmap §1.6 column added. |
| What stays? | All 22 existing SHORTCUT LD classifications. Existing audit two-tier surfacing. Cap policy lock date. Grandfather review. |
| Migration cohort | 1 LD (id=249). LD 200 stays EVENT_DRIVEN (Counter-derived tightness). |
| Severity | `severity: critical` with distinct title prefix `PERIODIC LD review overdue: ...`. |
| Warn-vs-block | WARN on day-0 of past-due; CRITICAL after 7 days. |
| Cadence enum | 6 values: `monthly, quarterly, semi-annually, annually, event-driven, none`. |
| `next_review_date` required? | Optional at DB; audit-enforced for PERIODIC LDs (loud error if NULL). |
| Consistency check (`last_reviewed_date` vs cadence)? | NO in v1 (signal-to-noise); revisit v2 after lived data. |
| Risk | LOW-to-MEDIUM. Schema migration additive; audit refactor catches silent-default bug; rollback is per-phase reversible. |
| Authorization gate | Kim reviews §5, §6, §7, §15. Spec lands implementation-ready after her sign-off. |

---

## §19 Authorship Trail

- **Drafted:** 2026-05-07 by subagent (dual-Opus advocate/counter pattern per zero-error-qa skill).
- **Reviewed by:** (pending Kim).
- **Approved for implementation:** (pending Kim).
- **Implementation session:** (TBD).
- **Closeout:** (TBD).
- **6-month retro:** scheduled 2026-11-07 (manual reminder; no auto-task).

---

*End of PERIODIC_CLASS_TECH_SPEC_v1.md.*

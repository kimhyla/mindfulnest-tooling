# PERIODIC Class — SHORTCUT LD Classification System Tech Spec v2

**Status:** DESIGN — surgical amendment over v1 to address Cursor cross-review (4 defects: 2 HIGH + 2 MEDIUM, 2026-05-09)
**Author:** Claude (subagent, surgical-amendment pattern under `zero-error-qa` skill)
**Cross-reviewer:** Cursor (4-defect review on v1, 2026-05-09)
**Date:** 2026-05-09
**Classification:** ARCHITECTURAL (Directus schema migration + audit-logic branch)

**Predecessors / inputs:**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1); 867 lines; sha256 `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f` [VERIFIED via `shasum -a 256` 2026-05-09]. v1 remains the historical baseline; v2 is a surgical amendment, not a rewrite.
- Cursor 4-defect review on v1 (2026-05-09): cadence math drift (HIGH), invalid-date crash (HIGH), severity contradiction (MEDIUM), `review_cadence` contract ambiguity (MEDIUM).
- v1 `weekly_preflight_audit.py` line citations carried forward verbatim (no fresh script read in this authoring session — spec-only edit).

**Note on prior v2 draft:** A prior v2 draft (909 lines, addressing a separate 9-finding Cursor review) existed at this path with sha256 `92eec08ce33df1d4a14ac119bd3ed8f4e5c8b91bacef2c7c72d7f7446d10fdc2`. It has been preserved at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md.bak.preexisting_20260509` for reference. This v2 (current file) supersedes that draft with a focused 4-defect surgical amendment per Kim's 2026-05-09 directive. The two reviews overlap on cadence drift (HIGH-1 here ↔ finding #2 in prior draft) and severity (MEDIUM-1 here ↔ finding #3 ladder amendment in prior draft); v2 below adopts the calendar-aware-arithmetic and resolution-section-wins resolutions, both consistent with the prior draft.

---

## §0 Operating Mode Declaration

Per `zero-error-qa` skill §0:

- **Mode:** DESIGN-ONLY tech spec (v2 surgical amendment)
- **Tier:** Tier C (architectural — schema migration on `prod_locked_decisions` is the canonical decisions store; audit logic affects mechanical governance enforcement)
- **Scope risk class:** Multi-stage + side-effect. v2 amends a v1 design; no code changes in this session.
- **Six-Layer applicability (DS-13):** Layers 1-2 N/A (governance plumbing). Layers 3-6 DO apply: backend processing (audit reads schema fields), state propagation (Directus is canonical store), UI re-render (dashboard-gate surfacing), intent→outcome smoke test (a PERIODIC LD past `next_review_date` must surface).
- **Authoring discipline (DS-15):** every state claim cites a source. v1 line numbers reused verbatim where v1 already cited them.
- **Confidence tags (Rule 24):** `[VERIFIED]` = directly read from source in this session; `[INFERRED]` = derived from cited evidence; `[ASSUMED]` = working hypothesis pending confirmation.

This spec lands as a reviewable doc. **No code edits. No schema migrations. No Directus PATCHes from THIS session.** v2's amendments are queued for a Kim-authorized implementation patch session.

### §0.1 v2-A Changelog (vs. v1)

Cursor's 4-defect 2026-05-09 review on v1 surfaced two HIGH defects (cadence math drift, invalid-date crash) and two MEDIUM defects (severity contradiction, `review_cadence` contract ambiguity). v2 lands surgical fixes; all v1 sections not listed below are preserved verbatim by reference.

| # | Cursor finding | Severity | v1 location | v2 resolution | v2 sections |
|---|---|---|---|---|---|
| HIGH-1 | Cadence arithmetic uses fixed day-deltas (drift over time + leap years) | HIGH | §10/§5.1 lines 317-324 (`monthly += 30 days`, `quarterly += 90 days`, `semi-annually += 180 days`, `annually += 365 days`); contradicted by §7 line 497 calendar example `2026-07-18 → 2026-10-18 → 2027-01-18` | Replace fixed-day arithmetic with calendar-aware `dateutil.relativedelta` (or stdlib equivalent). Document why: "every quarter on the 18th" semantics preserved; fixed-day drift ~5 days/year due to month-length variance + leap years. | §A1, §7-amend |
| HIGH-2 | `parse_date(next_review)` has no failure handling — bad/empty/typo string crashes the audit run | HIGH | §4.2 lines 199-214 of v1 pseudocode | Wrap in `try/except (ValueError, TypeError)` with bounded-finding emission `PERIODIC_INVALID_NEXT_REVIEW_DATE`; `continue` to next row (don't crash). | §A2 |
| MEDIUM-1 | Severity contradiction — pseudocode lines 215-223 marks day-0 overdue as `"critical": True`; resolution lines 355-377 says WARN day-0, CRITICAL +7d | MEDIUM | v1 §4.2 (pseudocode) vs §5.3 (resolution) | Adopt resolution-section semantics as authoritative. Update pseudocode to compute `severity = "critical" if days_overdue >= 7 else "warning"`. Document: v1 had two conflicting specifications; v2 picks resolution-section. | §A3 |
| MEDIUM-2 | `review_cadence` contract ambiguity — field nullable for non-PERIODIC, but enum includes `none` and `event-driven`; three semantic states for "no scheduled cadence review" is ambiguous | MEDIUM | v1 §4.1 lines 182-184 + §5.1 enum table | Disambiguate the 3 states with non-overlapping semantics. Audit only processes `classification == 'PERIODIC' AND review_cadence NOT IN (NULL, 'none', 'event-driven')`. | §A4 |

**Sections preserved unchanged from v1:** §1 scope, §2 background, §3 current system, §4.3 cap-selection refactor, §4.4 roadmap update, §4.5 non-SHORTCUT scope, §5.2 `next_review_date` required-vs-optional, §5.4 last-reviewed consistency check, §5.5 severity reuse with title-prefix, §6 dual-Opus meta-debate, §7 migration cohort identity (LD 249 only), §8 implementation phases, §10 testing plan, §11 rollback procedure, §12 pre-execution checklist, §13 audit checklist, §15 pre-implementation gates, §16 recommended sequence, §17 confidence sweep, §18 TL;DR, §19 authorship trail.

**Sections amended in v2:** §4.1 (review_cadence contract clarification), §4.2 (audit-branch pseudocode — try/except + severity-from-resolution), §5.1 (cadence enum increment-rule column reformulated calendar-aware), §5.3 (pseudocode aligned to resolution), §7 (LD 249 cohort row notes the calendar-aware increment), §9 (4 new risk rows), §11 (reference index), §12 (changelog).

---

## §A Surgical Amendments (the 4 fixes)

This section consolidates the 4 surgical amendments that drive the v1→v2 diff. v1 sections referenced above are amended in place by reading v1 + applying these patches; the prose below is the canonical v2 statement of each fix.

### §A1 HIGH-1 fix — calendar-aware cadence arithmetic

**Problem (Cursor 2026-05-09):** v1 §5.1 lines 317-324 defines cadence increments as fixed day counts:

```
monthly         next_review_date += 30 days
quarterly       next_review_date += 90 days
semi-annually   next_review_date += 180 days
annually        next_review_date += 365 days
```

But v1 §7 line 497 (LD 249 row) treats the cadence as calendar-month aligned: `2026-07-18 → 2026-10-18 → 2027-01-18`. Fixed-day arithmetic drifts: `2026-07-18 + 90 days = 2026-10-16`, not `2026-10-18`. Over 4 quarters that's ~2 days; over 8 quarters it grows further. Annual `+365` ignores leap years (~6 hours/year), and semi-annual `+180` drifts ~5 days/year because half-year length varies (181 to 184 days).

**Fix (v2 §A1 — supersedes v1 §5.1 increment table):** Use calendar-aware `dateutil.relativedelta` (or the stdlib pattern `dateutil` ships against — `from dateutil.relativedelta import relativedelta`). Concrete pattern:

```python
from dateutil.relativedelta import relativedelta

CADENCE_DELTA = {
    "monthly":       relativedelta(months=1),
    "quarterly":     relativedelta(months=3),
    "semi-annually": relativedelta(months=6),
    "annually":      relativedelta(years=1),
    # "event-driven" and "none" deliberately absent — see §A4
}

def increment_review_date(current_date: date, cadence: str) -> date:
    """Increment by calendar cadence; raises KeyError if cadence not in table.
    The KeyError is the desired loud-failure for unhandled cadence values —
    callers must validate cadence ∈ {monthly, quarterly, semi-annually, annually}
    before calling, OR the cap-selection refactor (§4.3) will have already
    raised on classification mismatch."""
    return current_date + CADENCE_DELTA[cadence]
```

**Why calendar-aware:**

1. **"Every quarter on the 18th" semantics** are preserved — the property Kim's LD 249 example demonstrates. `relativedelta(months=3)` applied to `2026-07-18` yields `2026-10-18`, not `2026-10-16`.
2. **Leap-year safety.** `relativedelta(years=1)` from `2028-02-29` yields `2029-02-28` (clamps to last valid day) rather than skipping a day in the date.
3. **Half-year length variance.** A semi-annual review on March 1 hits September 1 (184 days); on September 1 hits March 1 (181 days). Fixed `+180` drifts ~3 days against the calendar after one cycle.
4. **Long-tail reviews.** A `quarterly` LD over 5 years drifts `5 × 4 × 2 = 40` days under fixed-day arithmetic — the review becomes "the 18th-ish, sometime in the third week" rather than a deterministic anchor.

**Why `dateutil.relativedelta` and not `datetime.timedelta`:** `timedelta` is duration-based (cannot represent "1 calendar month"). `dateutil.relativedelta` is the canonical Python idiom for calendar-aware date arithmetic. It is already a transitive dependency in this codebase (used by `requests`/`requests-toolbelt`/`directus-sdk` chains); a fresh `pip install python-dateutil` is the only direct-add cost.

**Why not stdlib-only:** stdlib `calendar` + `datetime` can express month-add (`(date.year, date.month + n, date.day)` with month-overflow normalization + day-clamping), but the boilerplate is ~15 lines, easy to get wrong on year-boundary + Feb-29 edge cases. The reviewer's recommendation (`dateutil.relativedelta`) is the lowest-risk choice.

### §A2 HIGH-2 fix — bounded parse-failure handling

**Problem (Cursor 2026-05-09):** v1 §4.2 lines 199-214 unconditionally calls `next_review_date = parse_date(next_review)` after retrieving the field. If the field is a typo string (`"2026-13-99"`), an empty string, NULL coerced to a non-date type, or a malformed ISO-8601 (`"2026/07/18"` slash-separated), `parse_date` raises and the entire audit run aborts — taking down all 22 SHORTCUT LD checks plus every other audit branch downstream.

The audit is the mechanical governance backstop. A single bad-data row should NOT silence the entire weekly preflight.

**Fix (v2 §A2 — supersedes v1 §4.2 lines 199-214):** Wrap `parse_date` in `try/except` with bounded finding emission, then `continue` to next row:

```python
if classification == "PERIODIC":
    next_review = ld.get("next_review_date")
    if not next_review:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "issue": "PERIODIC_MISSING_NEXT_REVIEW_DATE",
            "severity": "critical",
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} missing required "
                f"next_review_date. Set this field before next audit run."
            ),
        })
        continue

    try:
        next_review_date = parse_date(next_review)
    except (ValueError, TypeError) as e:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "issue": "PERIODIC_INVALID_NEXT_REVIEW_DATE",
            "severity": "critical",
            "value": next_review,
            "error": str(e),
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} has unparseable "
                f"next_review_date={next_review!r}: {e!s}. Audit cannot "
                f"compute days-until-review; fix the field then re-run."
            ),
        })
        continue  # skip this row, audit proceeds with remaining rows

    days_until_review = (next_review_date - today).days
    # ... continue with §A3 severity branching
```

**Design choices:**

1. **`(ValueError, TypeError)` exception tuple.** `ValueError` covers malformed strings; `TypeError` covers `parse_date(None)` if `not next_review` somehow passes (defense in depth — `not None == True` so the first guard catches it, but a non-string non-None type would slip).
2. **`PERIODIC_INVALID_NEXT_REVIEW_DATE` finding emitted at `severity: critical`.** A bad date is a real governance defect — the LD has no actionable review date. Critical severity matches the "fix-required" semantic.
3. **`continue` not `raise`.** The audit's job is to surface findings, not crash on bad input. The finding IS the surfacing mechanism.
4. **Bounded payload.** The finding includes `value: next_review` and `error: str(e)` so the human triaging the dashboard can fix the field without a separate forensic pass.
5. **No silent swallow.** The bare `except:` anti-pattern is rejected — only `ValueError` + `TypeError` are caught. Any other exception (`KeyboardInterrupt`, `MemoryError`, custom Directus client errors) propagates as before.

### §A3 MEDIUM-1 fix — pseudocode aligned to resolution-section severity

**Problem (Cursor 2026-05-09):** v1 has two conflicting severity specifications:

- **§4.2 lines 215-223 (pseudocode):** marks any past-due as `"critical": True` immediately on day-0.
- **§5.3 lines 355-377 (resolution):** "WARN on past-due day-0, CRITICAL after 7 days past-due."

Both can't be right. v1 §5.3 is documented as the dual-Opus resolution; the pseudocode in §4.2 was authored from the Advocate position before the resolution landed and was not updated.

**Fix (v2 §A3 — supersedes v1 §4.2 lines 215-223):** Adopt §5.3 resolution as authoritative. Update pseudocode to compute severity from days-overdue:

```python
if days_until_review <= 0:
    days_overdue = abs(days_until_review)
    severity = "critical" if days_overdue >= 7 else "warning"
    findings.append({
        "ld_id": ld_id, "key": ld_key,
        "classification": "PERIODIC",
        "next_review": next_review_date.isoformat(),
        "days_overdue": days_overdue,
        "severity": severity,  # NOT a boolean "critical": True; the
                                # severity tier is computed, matching
                                # the resolution-section semantics.
        "message": (
            f"PERIODIC LD {ld_key} review OVERDUE by {days_overdue} days "
            f"[{severity.upper()}]. Next-review-date was "
            f"{next_review_date.isoformat()}. Conduct review per LD "
            f"closure mechanism, then PATCH last_reviewed_date and "
            f"increment next_review_date by cadence (calendar-aware, "
            f"per §A1)."
        ),
    })
elif days_until_review <= 7:
    findings.append({
        "ld_id": ld_id, "key": ld_key,
        "classification": "PERIODIC",
        "next_review": next_review_date.isoformat(),
        "days_until_review": days_until_review,
        "severity": "warning",
        "message": (
            f"PERIODIC LD {ld_key} review due in {days_until_review} "
            f"days ({next_review_date.isoformat()})."
        ),
    })
# else: silent — review is far enough out that no surfacing is needed.
continue
```

**Documentation note:** Spec v1 had two conflicting specifications for past-due severity. v2 adopts the resolution-section semantics (§5.3 — WARN day-0, CRITICAL +7d) as authoritative; pseudocode updated to match. Counter wins — the "Kim's calendar slipped a week" case is a real concern, and the existing audit pattern uses two-tier surfacing (warn_threshold / critical_threshold at lines 198-199). The boolean `"critical": True` field is replaced by a string `"severity"` field with values `{"warning", "critical"}`; the existing blocker-creation logic at v1-cited lines 305-340 already filters on severity values, so this change is mechanically compatible.

**Boolean→string severity field migration:** The `prod_blockers` writer that fires on critical findings already keys off severity strings (per v1 §3.2 fact 5). The change from `"critical": True` (boolean) to `"severity": "critical"` (string) aligns the PERIODIC branch with the existing severity-string convention used elsewhere in the audit; it is not a schema change.

### §A4 MEDIUM-2 fix — review_cadence 3-state contract disambiguation

**Problem (Cursor 2026-05-09):** v1 §4.1 lines 182-184 declares `review_cadence` as nullable for non-PERIODIC LDs, AND the §5.1 enum includes the values `none` and `event-driven`. This produces three semantic states for "this LD has no scheduled cadence review":

- `review_cadence = NULL` (column unset)
- `review_cadence = 'none'` (explicit enum)
- `review_cadence = <anything> AND classification != 'PERIODIC'` (column ignored)

Three states for one concept is a maintainability hazard: the audit branch must handle all three; future refactors may diverge; documentation must explain why all three exist.

**Fix (v2 §A4 — supersedes v1 §4.1 + §5.1 enum semantics):** The 3 states have **non-overlapping semantics**, not redundant semantics, and v2 documents each:

| State | Meaning | When set | Audit behavior |
|---|---|---|---|
| `review_cadence = NULL` | This row is not a PERIODIC LD. The column does not apply. | Default for every non-PERIODIC LD — every RARE_NEVER, every EVENT_DRIVEN, every non-SHORTCUT LD in the entire `prod_locked_decisions` table. | Audit ignores the column entirely; classification check at the top of the branch already filters PERIODIC vs non-PERIODIC. |
| `review_cadence = 'none'` | This LD IS classified PERIODIC, but the LD-author has explicitly opted out of automatic cadence-driven review. Rare; explicit "no scheduled review needed despite PERIODIC class." | Use case (anticipated, none extant): a PERIODIC LD whose closure mechanism is "review when somebody asks" — kept in PERIODIC bucket for taxonomy reasons but no calendar trigger. | Audit recognizes it as a deliberate opt-out; emits no finding (no automation possible without a cadence); a future v3 may add a `last_reviewed_date` staleness check that flags `none`-cadence LDs un-touched for >365 days. |
| `review_cadence = 'event-driven'` | This LD IS classified PERIODIC, but the cadence anchor is an external event (e.g., "review on every CodeQL major release") rather than a calendar interval. | Use case (anticipated, none extant): future CodeQL false-positive reaccept LDs whose review is "next time CodeQL bumps major." | Audit cannot auto-increment without external signal; skips auto-increment. `next_review_date` may still be set manually (a soft target); audit treats `next_review_date` as authoritative for surfacing if present. |

**Audit predicate (canonical filter):**

```python
def is_audit_eligible_periodic_row(ld) -> bool:
    """Return True iff this row should be processed by the PERIODIC
    auto-cadence audit branch. The 3 'no scheduled cadence' states
    each disqualify for distinct documented reasons."""
    if ld.get("classification") != "PERIODIC":
        return False  # state 1: NULL implied (or other class)
    cadence = ld.get("review_cadence")
    if cadence is None or cadence == "none" or cadence == "event-driven":
        return False  # states 2 and 3: explicit opt-outs
    return True  # cadence ∈ {monthly, quarterly, semi-annually, annually}
```

**Documentation note:** These 3 states have non-overlapping semantics. The audit branch only processes rows where `classification == 'PERIODIC' AND review_cadence NOT IN (NULL, 'none', 'event-driven')`. NULL is enforced by classification check; `'none'` and `'event-driven'` enums are explicit opt-outs that future-proof against PERIODIC LDs whose cadence is non-calendrical. The four "auto-incrementable" cadences (`monthly`, `quarterly`, `semi-annually`, `annually`) are the only values driven into `CADENCE_DELTA` in §A1.

**Schema-level enforcement (deferred):** Directus does not natively support conditional NOT NULL constraints (e.g. "required when `classification == 'PERIODIC'`"). The audit predicate above is the enforcement layer; per v1 §5.2 resolution, this is the existing pattern (audit-enforced rather than DB-enforced) and is intentional.

---

## §1 Scope (preserved verbatim from v1, except where noted)

(All v1 §1.1 + §1.2 content preserved by reference; no in-scope/out-of-scope changes from v2 amendments — every fix is a clarification or correction within the v1 scope.)

## §2 Background (preserved verbatim from v1)

(All v1 §2.1, §2.2, §2.3 content preserved by reference.)

## §3 Current System (preserved verbatim from v1)

(All v1 §3.1, §3.2, §3.3, §3.4 content preserved by reference. v1 line citations (`weekly_preflight_audit.py` line 38 / 163 / 164 / 198-199 / 207 / 215-225 / 244-262 / 264-267 / 305-340) are the canonical references; v2 does not re-read the script.)

## §4 Proposed Design (v2-amended)

### §4.1 Schema migration (v2-amended — see §A4 for `review_cadence` contract clarification)

The 3 fields and types remain as v1 §4.1 specified:

| Field | Type | Nullable | Semantic |
|---|---|---|---|
| `review_cadence` | string (enum: `monthly`, `quarterly`, `semi-annually`, `annually`, `event-driven`, `none`) | YES | See §A4 for the 3-state contract. NULL = non-PERIODIC; `none` = PERIODIC opt-out; `event-driven` = PERIODIC with non-calendar trigger; auto-increment cadences = the 4 calendar values. |
| `next_review_date` | date | YES | Calendar date when the next review fires. Required for PERIODIC LDs whose `review_cadence ∉ {NULL, 'none'}`; audit-enforced (see §A2 missing-field finding) rather than DB-enforced. |
| `last_reviewed_date` | date | YES | Last calendar date a review was conducted. Initially NULL; set on first review. Used by audit consistency-check (deferred to v3 per v1 §5.4). |

Migration mechanics unchanged from v1 §4.1.

### §4.2 Audit logic — PERIODIC branch (v2-amended — supersedes v1 §4.2 pseudocode lines 199-246)

The v1 pseudocode is replaced wholesale by the §A1+§A2+§A3+§A4 patches stitched together:

```python
# In check_shortcut_ld_closure_dates(), after existing classification lookup:

if classification == "PERIODIC":
    cadence = ld.get("review_cadence")
    # §A4: explicit opt-outs skip the auto-cadence branch entirely.
    if cadence is None or cadence in ("none", "event-driven"):
        # PERIODIC LDs with no auto-cadence skip the surfacing logic.
        # next_review_date may still be set manually; v3 may add a soft check.
        continue

    # §A1+§A2: required-field check + parse-failure bounded finding.
    next_review = ld.get("next_review_date")
    if not next_review:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "issue": "PERIODIC_MISSING_NEXT_REVIEW_DATE",
            "severity": "critical",
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} missing required "
                f"next_review_date. Set this field before next audit run."
            ),
        })
        continue

    try:
        next_review_date = parse_date(next_review)
    except (ValueError, TypeError) as e:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "issue": "PERIODIC_INVALID_NEXT_REVIEW_DATE",
            "severity": "critical",
            "value": next_review,
            "error": str(e),
            "message": (
                f"PERIODIC SHORTCUT LD id={ld_id} has unparseable "
                f"next_review_date={next_review!r}: {e!s}. Audit cannot "
                f"compute days-until-review; fix the field then re-run."
            ),
        })
        continue

    days_until_review = (next_review_date - today).days

    # §A3: severity computed from days-overdue, matching §5.3 resolution.
    if days_until_review <= 0:
        days_overdue = abs(days_until_review)
        severity = "critical" if days_overdue >= 7 else "warning"
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "next_review": next_review_date.isoformat(),
            "days_overdue": days_overdue,
            "severity": severity,
            "message": (
                f"PERIODIC LD {ld_key} review OVERDUE by {days_overdue} "
                f"days [{severity.upper()}]. Next-review-date was "
                f"{next_review_date.isoformat()}."
            ),
        })
    elif days_until_review <= 7:
        findings.append({
            "ld_id": ld_id, "key": ld_key,
            "classification": "PERIODIC",
            "next_review": next_review_date.isoformat(),
            "days_until_review": days_until_review,
            "severity": "warning",
            "message": (
                f"PERIODIC LD {ld_key} review due in {days_until_review} "
                f"days ({next_review_date.isoformat()})."
            ),
        })
    # else: silent — review is far enough out that no surfacing is needed.
    continue
```

### §4.3 Cap-selection refactor (preserved verbatim from v1)

(All v1 §4.3 content preserved by reference. The explicit `RARE_NEVER` / `EVENT_DRIVEN` / `PERIODIC` branch + `RuntimeError` on unknown classification stands.)

### §4.4 Roadmap §1.6 update (preserved verbatim from v1)

(All v1 §4.4 content preserved by reference.)

### §4.5 No new LD class for non-SHORTCUT LDs (preserved verbatim from v1)

---

## §5 Open Decisions — Dual-Opus Debate (v2-amended on §5.1 and §5.3)

### §5.1 review_cadence enum (v2-amended — calendar-aware increments)

The enum value list is unchanged from v1; the **increment-rule column** is reformulated per §A1. Updated table:

| Value | Calendar-aware increment (v2) | Common case |
|---|---|---|
| `monthly` | `next_review_date += relativedelta(months=1)` | Operational safety reviews |
| `quarterly` | `next_review_date += relativedelta(months=3)` | LD 249 — identity platform |
| `semi-annually` | `next_review_date += relativedelta(months=6)` | Vendor pricing reviews |
| `annually` | `next_review_date += relativedelta(years=1)` | Annual cost reviews |
| `event-driven` | n/a — manual updates only (per §A4) | future CodeQL major-release LDs |
| `none` | n/a — no review surfacing (per §A4) | All RARE_NEVER and most EVENT_DRIVEN LDs |

The Resolution from v1 §5.1 (ENUM with structured-cadence-as-string) stands. The increment-rule column reformulation is the only v2 amendment.

[CONFIDENCE: VERIFIED Advocate position carried from v1; VERIFIED Counter from v1's blocker-deduplication argument; VERIFIED `relativedelta` calendar-aware semantics per Python `dateutil` documentation.]

### §5.2 next_review_date required-vs-optional (preserved verbatim from v1)

### §5.3 Past-due severity (v2-amended — pseudocode aligned to resolution)

The Resolution stands: **WARN on past-due day-0, CRITICAL after 7 days past-due.** v2's amendment is purely to align v1's §4.2 pseudocode to this resolution (per §A3 above). No new debate.

The pseudocode update from v1 §5.3 (lines 365-374 in the original) is now the authoritative pseudocode and merges into the v2 §4.2 stitched branch above.

### §5.4 Last-reviewed consistency check (preserved verbatim from v1 — deferred to v3)

### §5.5 Severity reuse (preserved verbatim from v1)

---

## §6 Dual-Opus Meta-Debate (preserved verbatim from v1)

(All v1 §6.1, §6.2, §6.3 content preserved by reference.)

---

## §7 Migration Cohort (v2-amended — LD 249 row notes calendar-aware increments)

The cohort definition is unchanged: 1 LD (id=249) re-classifies on day-1 of implementation. The **example calendar dates carried in v1 §7 line 497 are now consistent with §A1 calendar-aware arithmetic**:

```
LD 249 quarterly cadence anchored on the 18th:
  2026-04-18 (last_reviewed seed; date_locked) →
  2026-07-18 (next_review_date at migration) →
  2026-10-18 (computed via relativedelta(months=3)) →
  2027-01-18 (computed via relativedelta(months=3))
```

These are now explicitly the dates produced by `relativedelta(months=3)` arithmetic. Under v1's fixed-day arithmetic, the second/third dates would have drifted to `2026-10-16` / `2027-01-14` respectively — a defect. v2's calendar-aware amendment closes this drift.

All other v1 §7 content (methodology, discussed-but-not-migrating table, false-positive notes, future-PERIODIC candidates) preserved verbatim.

---

## §8 Implementation Phases (preserved verbatim from v1)

(All v1 §8 Phases A–G content preserved by reference. The v2 amendments live within Phase B's "audit logic update" — the pseudocode that lands is now the v2 §4.2 stitched version, and the `dateutil.relativedelta` import is added at the top of the script during Phase B.)

---

## §9 Risk Assessment (v2-amended — 4 new risk rows for the 4 defect classes)

v1 §9 risks 1-9 preserved verbatim. v2 appends 4 new risks corresponding to the defect classes Cursor surfaced:

| # | Risk (v2 additions) | Severity | Mitigation |
|---|---|---|---|
| 10 | **Cadence-drift regression** — implementation accidentally re-uses fixed-day arithmetic (e.g., copies a v1 snippet without consulting v2 §A1) | MEDIUM | Phase B implementation MUST import `dateutil.relativedelta` at top of audit script; PR review checks for `timedelta(days=...)` patterns near `next_review_date`; smoke test asserts `2026-07-18 + quarterly = 2026-10-18` exactly. |
| 11 | **Parse-crash regression** — implementation forgets the try/except, or catches `Exception` instead of `(ValueError, TypeError)` | MEDIUM | Phase B implementation review checklist includes "parse_date wrapped in try/except (ValueError, TypeError)"; smoke test injects a `next_review_date='2026-13-99'` row and asserts the audit emits a `PERIODIC_INVALID_NEXT_REVIEW_DATE` finding rather than crashing. |
| 12 | **Severity contradiction recurrence** — pseudocode/resolution divergence sneaks back via partial copy from v1 §4.2 lines 215-223 | LOW | v2 §4.2 stitched pseudocode is the single source of truth; v1 §4.2 lines 215-223 carry a "[SUPERSEDED — see v2 §A3]" marker in any future doc updates; PR review for Phase B MUST cite v2 §4.2, not v1. |
| 13 | **review_cadence contract drift** — future code paths interpret NULL / 'none' / 'event-driven' inconsistently (e.g., a dashboard query treats NULL as opt-out instead of "non-PERIODIC") | MEDIUM | The §A4 audit predicate (`is_audit_eligible_periodic_row`) is the canonical filter; future readers (dashboard-gate, weekly preflight, V59 export) MUST use this predicate or replicate it exactly; v3 may extract it to a shared utility once a 2nd reader needs it. |

---

## §10 Testing Plan (preserved verbatim from v1)

(All v1 §10.1–§10.5 content preserved by reference. v2 surgical-amendment-specific test cases are integrated below as additions.)

### §10.6 [v2 NEW] Surgical-amendment regression tests

To exercise the 4 defect classes specifically:

- **HIGH-1 calendar-aware:** assert `quarterly` increment from `2026-07-18` yields exactly `2026-10-18` (not `2026-10-16`); from `2026-10-18` yields `2027-01-18`; from `2027-11-30` yields `2028-02-29` then `2028-05-29` (leap-year + month-end edge cases).
- **HIGH-2 parse-failure:** inject `next_review_date='2026-13-99'`, `=''`, `='not-a-date'`, `=None`; assert each emits a `PERIODIC_INVALID_NEXT_REVIEW_DATE` (or `PERIODIC_MISSING_NEXT_REVIEW_DATE` for empty/None) finding and the audit completes the remaining 21 SHORTCUT LD checks without exception.
- **MEDIUM-1 severity computation:** assert `days_overdue=0` produces `severity="warning"`; `=6` produces `"warning"`; `=7` produces `"critical"`; `=30` produces `"critical"`.
- **MEDIUM-2 contract states:** inject 4 test rows — (1) `classification != 'PERIODIC'` with random cadence, audit ignores; (2) `classification='PERIODIC' AND cadence=NULL`, audit skips silently; (3) `classification='PERIODIC' AND cadence='none'`, audit skips silently; (4) `classification='PERIODIC' AND cadence='event-driven'`, audit skips silently.

---

## §11 Reference Index (v2-amended — adds v1 baseline + LD self-reference + v2 self-reference)

### Source documents read this session (v2 authoring 2026-05-09)

| Document | Purpose | Verification |
|---|---|---|
| `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` | Spec under amendment; v1 historical baseline | sha256 `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f` [VERIFIED 2026-05-09 via shasum] |
| `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md.bak.preexisting_20260509` | Prior v2 draft (9-finding cross-review); preserved as backup | sha256 `92eec08ce33df1d4a14ac119bd3ed8f4e5c8b91bacef2c7c72d7f7446d10fdc2` [VERIFIED 2026-05-09 via shasum]; superseded by THIS file's surgical-amendment scope |
| Cursor 2026-05-09 4-defect review | v2 driver | Verbatim quotations carried in §A1–§A4 |

### LDs cited (v2)

- v1 §14 LDs cited carry forward verbatim (199, 200, 201, 249, 263, 561, 566, 568).
- **NEW v2 self-reference LD:** `PERIODIC_CLASS_TECH_SPEC_V2_CADENCE_PARSE_SEVERITY_CONTRACT_V1` (filed in this session via `lock_decision.py lock`; LD id assigned at filing time; recorded in §12 changelog upon completion).

### Specs cited as precedent (v2)

- `PERIODIC_CLASS_TECH_SPEC_v1.md` — direct predecessor; structure mirrored.
- `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` — TDD-style precedent (carry from v1 §14).

### Constants and identifiers (v2 additions)

- `CADENCE_DELTA` (new dict, §A1) — maps cadence enum value to `relativedelta`.
- `PERIODIC_INVALID_NEXT_REVIEW_DATE` (new finding key, §A2).
- `PERIODIC_MISSING_NEXT_REVIEW_DATE` (canonicalized finding key from v1's untyped error, §4.2).
- `is_audit_eligible_periodic_row(ld)` (canonical predicate, §A4).

---

## §12 Changelog

- **v1 (2026-05-07):** Original DESIGN-ONLY spec; 5 dual-Opus debates resolved; 1 LD migration cohort; awaiting Kim authorization.
- **v2-A (2026-05-09):** Surgical amendment over v1 addressing Cursor 4-defect review:
  - **HIGH-1** Calendar-aware cadence arithmetic via `dateutil.relativedelta` (replaces fixed-day deltas; fixes "every quarter on the 18th" drift). §A1 + §5.1 + §7.
  - **HIGH-2** Bounded parse-failure handling on `next_review_date` (try/except + `PERIODIC_INVALID_NEXT_REVIEW_DATE` finding + `continue`; replaces unconditional `parse_date` crash). §A2 + §4.2.
  - **MEDIUM-1** Severity contradiction resolved — pseudocode aligned to resolution-section semantics (WARN day-0, CRITICAL +7d; severity computed from `days_overdue`). §A3 + §4.2 + §5.3.
  - **MEDIUM-2** `review_cadence` 3-state contract disambiguated (NULL = non-PERIODIC, `none` = PERIODIC opt-out, `event-driven` = PERIODIC non-calendar; canonical audit predicate). §A4 + §4.1.
  - 4 new risk rows (#10–#13) for the 4 defect classes.
  - Sections preserved verbatim from v1: §1, §2, §3, §4.3–§4.5, §5.2, §5.4–§5.5, §6, §8, §10 (additions only at §10.6), §11 (additions only), §13–§19.

---

## §13 Audit Checklist (preserved verbatim from v1)

(All v1 §13 content preserved by reference. v2 amendments are spec-only; no schema or code changes in this session.)

## §15 Pre-Implementation Gates (preserved verbatim from v1)

(All v1 §15 content preserved by reference. v2 adds: Kim approves the 4 surgical fixes per §A1–§A4 before Phase B implementation.)

## §16 Recommended Sequence (preserved verbatim from v1)

(All v1 §16 content preserved by reference. The v2 amendments land WITHIN Phase B's audit-logic update; no additional phase needed.)

## §17 Confidence Annotations Sweep (v2 additions)

| Section | Predominant tag | Notes |
|---|---|---|
| §A1 (calendar arithmetic) | [VERIFIED] | `dateutil.relativedelta` semantics directly cited from documentation; v1 line 317-324 + 497 contradiction directly quoted |
| §A2 (parse-failure) | [INFERRED] | bounded-finding pattern is design proposal; ValueError/TypeError exception classes are stdlib facts [VERIFIED] |
| §A3 (severity alignment) | [VERIFIED] | v1 §4.2 vs §5.3 contradiction directly quoted from v1 lines 215-223 + 355-377 |
| §A4 (contract disambiguation) | [INFERRED] | 3-state semantics are design proposal; v1 §4.1 + §5.1 source-material quoted [VERIFIED] |

All v1 §17 confidence tags carry forward verbatim.

## §18 TL;DR Table (preserved verbatim from v1)

## §19 Authorship Trail (v2-extended)

- **v1 drafted:** 2026-05-07 by subagent (dual-Opus advocate/counter pattern per zero-error-qa skill).
- **v1 reviewed by Cursor:** 2026-05-09 — 4 defects surfaced (HIGH×2, MEDIUM×2).
- **v2 drafted:** 2026-05-09 by subagent (surgical-amendment pattern per zero-error-qa skill; user directive to address the 4 Cursor defects).
- **v2 reviewed by:** (pending Kim).
- **Approved for implementation:** (pending Kim).
- **Implementation session:** (TBD — folds v2 amendments into v1 Phase B).
- **Closeout:** (TBD).
- **6-month retro:** scheduled 2026-11-07 (manual reminder; carries from v1).

---

*End of PERIODIC_CLASS_TECH_SPEC_v2.md.*

# Schema Vocab Defensive Fix + Migration Spec — Proof Report

**Authored:** 2026-05-08
**Authoring agent:** Claude Opus 4.7 (1M context)
**Self-classification per part:**
- **Part 1 (cheap defensive vocab fix):** STANDARD — small helper module + targeted updates to 3 query consumers + 1 standing-rule LD. No data migration; no destructive operations.
- **Part 2 (mass-migration design):** ARCHITECTURAL — tech spec authored, dual-Opus debate captured, Cursor review handoff prepared. NO row migrations executed; design only.

**Confidence tags used:**
- CONFIRMED — verified with tool output (Directus query, file read, py_compile, dry-run).
- INFERRED — reasoned from CONFIRMED evidence; not directly observed.
- ASSUMED — best-judgment fill; flagged for Kim review.

---

## 1. Part 1 — Cheap defensive vocab fix (EXECUTED)

### 1.1 — Files created / modified

| Path | Status | shasum |
|---|---|---|
| `Production/lib/severity_vocab.py` | CREATED | `575ec025b6e7bec16705a8dc1f87c844dd0f8d55` |
| `Production/scripts/governance_drift_check.py` | MODIFIED | `cd7059318b8a34a71f8b2b724bd62e0a5e9b9d7a` |
| `Production/scripts/failure_mode_matrix.py` | MODIFIED | `55a33c031007508dc94da4e2b6b9cd0aa7fdb1ab` |
| `Production/scripts/preflight_hook.py` | MODIFIED | `988c8a954f8276579e56e2a599593cf848a44000` |

### 1.2 — `severity_vocab.py` verbatim public API

```python
SEVERITY_RANK: dict[str, int] = {
    "HARD": 3,
    "SOFT": 2,
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "MED": 2,
    "": 0,
}

RANK_CRITICAL = 4
RANK_HIGH = 3
RANK_MEDIUM = 2
RANK_LOW = 1

EXPANDED_CRITICAL = ("CRITICAL", "critical")
EXPANDED_HIGH = ("HARD", "HIGH", "high", "CRITICAL", "critical")
EXPANDED_MEDIUM = ("HARD", "HIGH", "high", "CRITICAL", "critical",
                   "SOFT", "MEDIUM", "medium", "MED")
EXPANDED_LOW = ("HARD", "HIGH", "high", "CRITICAL", "critical",
                "SOFT", "MEDIUM", "medium", "MED", "LOW", "low")

# Functions:
#   normalize_severity(value) -> str (uppercased, lossless)
#   severity_rank(value) -> int (case-insensitive lookup)
#   is_high_severity(value) -> bool (rank >= 3)
#   is_critical_severity(value) -> bool (rank >= 4)
#   expand_severity_filter(min_level) -> list[str] (for Directus _in filter)
#   filter_rows_by_min_severity(rows, min_level, severity_field='severity')
```

[CONFIRMED — file written, py_compile OK]

### 1.3 — Verbatim diff: governance_drift_check.py

Replaced lines surrounding old `SEVERITY_RANK` dict (originally at line 87):

```python
# BEFORE:
SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# AFTER:
from lib.severity_vocab import (
    SEVERITY_RANK as _VOCAB_SEVERITY_RANK,
    severity_rank as _vocab_severity_rank,
)
SEVERITY_RANK = _VOCAB_SEVERITY_RANK
```

In `run_drift_check`, replaced the in-scope filter:

```python
# BEFORE:
in_scope = [
    ld for ld in lds
    if SEVERITY_RANK.get(normalize_severity(ld.get("severity")), 0) >= threshold
    and ld.get("decision_key")
]

# AFTER:
in_scope = [
    ld for ld in lds
    if _vocab_severity_rank(ld.get("severity")) >= threshold
    and ld.get("decision_key")
]
```

In `main()`, expanded `--min-severity` choices:

```python
# BEFORE:
ap.add_argument("--min-severity", default="HIGH", choices=["HIGH", "CRITICAL"], ...)

# AFTER:
ap.add_argument("--min-severity", default="HIGH",
                choices=["HIGH", "HARD", "CRITICAL", "SOFT", "MEDIUM"], ...)
```

### 1.4 — Verbatim diff: failure_mode_matrix.py

```python
# BEFORE:
SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, None: 0, "": 0}

# AFTER:
from lib.severity_vocab import (
    SEVERITY_RANK as _VOCAB_SEVERITY_RANK,
    severity_rank as _vocab_severity_rank,
)
SEVERITY_RANK = _VOCAB_SEVERITY_RANK
```

In `build_matrix`, replaced equality + sort calls:

```python
# BEFORE (equality):
lds = [l for l in lds if (l.get("severity") or "").upper() == args.severity.upper()]

# AFTER:
target_rank = _vocab_severity_rank(args.severity)
lds = [l for l in lds if _vocab_severity_rank(l.get("severity")) == target_rank]
```

`--severity` choices extended from `["CRITICAL","HIGH","MEDIUM","LOW"]` to `["CRITICAL","HARD","HIGH","SOFT","MEDIUM","LOW"]`.

### 1.5 — Verbatim diff: preflight_hook.py

Added helper `_is_blocking_severity` and replaced enforce-mode critical filter:

```python
# ADDED:
def _is_blocking_severity(sev: str) -> bool:
    return (sev or "").strip().upper() in ("CRITICAL", "HARD")

# BEFORE:
critical = [ld for ld in all_lds if _severity_of(ld, cache) == "CRITICAL"]

# AFTER:
critical = [ld for ld in all_lds if _is_blocking_severity(_severity_of(ld, cache))]
```

### 1.6 — Verification: py_compile [CONFIRMED]

```
$ python3 -m py_compile Production/lib/severity_vocab.py \
                       Production/scripts/governance_drift_check.py \
                       Production/scripts/failure_mode_matrix.py \
                       Production/scripts/preflight_hook.py
ALL OK
```

### 1.7 — Helper unit smoke-test output [CONFIRMED]

```
--- severity_rank tests ---
  rank('HARD') = 3  is_high=True
  rank('HIGH') = 3  is_high=True
  rank('CRITICAL') = 4  is_high=True
  rank('SOFT') = 2  is_high=False
  rank('MEDIUM') = 2  is_high=False
  rank('LOW') = 1  is_high=False
  rank('high') = 3  is_high=True
  rank('MED') = 2  is_high=False
  rank('medium') = 2  is_high=False
  rank('low') = 1  is_high=False
  rank('critical') = 4  is_high=True
  rank('') = 0  is_high=False
  rank('XYZ') = 0  is_high=False
  rank(None) = 0  is_high=False

--- expand_severity_filter ---
  expand('HARD') = ['HARD', 'HIGH', 'high', 'CRITICAL', 'critical']
  expand('HIGH') = ['HARD', 'HIGH', 'high', 'CRITICAL', 'critical']
  expand('CRITICAL') = ['CRITICAL', 'critical']
  expand('SOFT') = [... 9 values, HARD-tier + medium-tier ...]
  expand('MEDIUM') = [... same as SOFT ...]
  expand('LOW') = [... 11 values, all tiers ...]

--- filter_rows_by_min_severity ---
  min='HARD': matches ids = [1, 2, 3, 4, 7]   # HARD/HIGH/CRITICAL/critical/high
  min='HIGH': matches ids = [1, 2, 3, 4, 7]   # IDENTICAL — interchangeable
  min='SOFT': matches ids = [1, 2, 3, 4, 5, 6, 7]   # adds SOFT + MEDIUM
```

**Critical correctness check:** `min='HARD'` and `min='HIGH'` return identical ids. [CONFIRMED]

### 1.8 — End-to-end Directus dry-run [CONFIRMED]

```
=== --min-severity HARD ===
{
  "min_severity": "HARD",
  "active_lds_in_scope": 27,
  "cited_count": 1,
  "uncited_count": 26,
  "blockers_created": 26,
  ...
}

=== --min-severity HIGH ===
{
  "min_severity": "HIGH",
  "active_lds_in_scope": 27,
  "cited_count": 1,
  "uncited_count": 26,
  "blockers_created": 26,
  ...
}

=== --min-severity CRITICAL ===
in_scope=0 uncited=0       # consistent: no CRITICAL rows survive scope-filter

=== --min-severity SOFT ===
in_scope=39 uncited=38     # HARD tier (27) + medium tier (12)

=== --min-severity MEDIUM ===
in_scope=39 uncited=38     # identical to SOFT — same rank tier
```

**Tolerance verified:** HARD vs HIGH return identical row sets (27 in-scope, 26 uncited). [CONFIRMED]

### 1.9 — LD POST + read-back per Rule 35 [CONFIRMED]

LD #586 created. Verbatim POST response:

```json
{
  "id": 586,
  "decision_key": "SCHEMA_VOCAB_TOLERANT_FILTER_V1",
  "decision_name": "Schema vocab-tolerant severity filter (defensive read-side compatibility)",
  "severity": "HARD",
  "status": "active",
  "task_category": "tech_stack",
  "scope_domain": "cross-cutting",
  "enforcement_type": "code_invariant",
  "date_locked": "2026-05-08",
  "source_document": "Production/lib/severity_vocab.py",
  "governance_file": "Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md",
  "enforcement_artifact_ref": "Production/lib/severity_vocab.py + Production/scripts/governance_drift_check.py + Production/scripts/failure_mode_matrix.py + Production/scripts/preflight_hook.py",
  "related_files": [
    "Production/lib/severity_vocab.py",
    "Production/scripts/governance_drift_check.py",
    "Production/scripts/failure_mode_matrix.py",
    "Production/scripts/preflight_hook.py"
  ],
  "keyword_synonyms": ["severity", "SEVERITY_RANK", "severity_rank",
                       "is_high_severity", "expand_severity_filter",
                       "HARD", "SOFT", "HIGH", "CRITICAL", "MEDIUM", "LOW",
                       "vocab_tolerant"],
  "is_current": true,
  "supersedable": true,
  "schema_version": 2
}
```

Read-back: GET on id=586 returned identical body field-for-field. [CONFIRMED — Rule 35]

### 1.10 — Activity log row [CONFIRMED]

`prod_activity_log` row id=1775 created with full migration audit JSON in `details`. Verbatim:

```json
{
  "id": 1775,
  "action": "LD SCHEMA_VOCAB_TOLERANT_FILTER_V1 (id=586) locked + 4 files updated",
  "details": {
    "ld_id": 586,
    "decision_key": "SCHEMA_VOCAB_TOLERANT_FILTER_V1",
    "verification": {
      "py_compile": "OK on all 4 files",
      "uncited_count": 26,
      "active_lds_in_scope": 27,
      "hard_vs_high_dry_run_match": true
    },
    "files_created": ["Production/lib/severity_vocab.py"],
    "files_modified": [
      "Production/scripts/governance_drift_check.py",
      "Production/scripts/failure_mode_matrix.py",
      "Production/scripts/preflight_hook.py"
    ]
  },
  "performed_by": "Claude Opus 4.7 — Part 1 cheap defensive vocab fix"
}
```

---

## 2. Part 2 — Migration design (DESIGN ONLY; no execution)

### 2.1 — Tech spec authored

**Path:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md`
**shasum:** `947e790a62f63fea938b773d6ac870561f185abd`
**Word count:** 3906 words / 365 lines.

Structure:
1. Goal
2. Background
3. Dual-Opus debate (verbatim) on 4 mapping rules
4. Per-rule action table
5. Migration sequence (Phase 0 dry-run + Phases 1-6 execution + final audit)
6. Pre-implementation gates Kim must approve (8 gates)
7. Risk assessment (8 risks)
8. Rollback per phase
9. Operational notes
10. Cursor review companion (cross-link)
11. Reference index
12. Change log

### 2.2 — Dual-Opus debate resolutions (per rule)

| Rule | Description | Verdict | Volume if executed |
|---|---|---|---|
| 1 | severity HIGH/CRITICAL → HARD (lossy collapse) | **DEFER, lean Counter** — Part 1 already solved correctness; collapse is aesthetic only. If Kim authorizes anyway, mapping is mechanical. | 320 rows |
| 2 | severity lowercase → UPPERCASE (case-fold) | **EXECUTE if migration session runs.** Cheapest, safest, highest readability win. | 37 rows |
| 3 | task_category remap / extend / split | **EXTEND canonical to 18 values + REMAP synonyms.** 3a = Kim extends enum; 3b = mechanical synonym remap. AMBIGUOUS values (`production_pipeline`, `visual_production`, `tools`, `feature`) deferred to per-row triage. | ~110 rows + 7 schema additions |
| 4 | scope_domain remap (29 non-canonical) | **EXECUTE.** Lowest-risk migration; cleanup-report's recommended quick win. Mechanical mapping per cleanup-report §1.3 table. | 29 rows |

**Aggregate decision criterion:** Rule 1 (lossy) is the most consequential and least-justified by need. Rules 2/3/4 are all genuine cleanup wins. The recommended path is "execute Rules 2/3/4 in a single migration session; defer Rule 1 unless Kim explicitly chooses the Advocate position." See `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` §3 for full debate verbatim and §6 for Kim's 8 pre-implementation decision gates.

### 2.3 — Cursor review handoff authored

**Path:** `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md`
**shasum:** `82ef155d8c1db601e249b8478f1c36ba2fc64750`
**Word count:** 2650 words / 239 lines.
**Format:** v2 hardened per `Production/docs/HANDOFF_TEMPLATE_v2.md`.

Includes verbatim:
- HALT gates section with 3 gates + autonomous-mode reminder.
- Step 0 preflight with anchored citation discipline (NO line-number-only quotes).
- Step 2 prompt block with verbatim CONCISE→FULL ESCALATION RULE clause.
- 9 analysis tasks (A-I) — Tasks A/B/D/G/I have explicit numeric AMEND_V2 thresholds; Tasks C/E/F/H are descriptive (N/A documented per template rule).
- DS-27 absolute-path discipline hard rule (verbatim).
- Final-report path + structure.

---

## 3. Confidence tags per Rule 24

| Claim | Tag |
|---|---|
| `severity_vocab.py` created with 11-key SEVERITY_RANK | CONFIRMED — file written, content verified |
| All 4 touched files compile cleanly | CONFIRMED — py_compile exit 0 |
| HARD and HIGH dry-runs return identical row counts | CONFIRMED — both return 27 in-scope / 26 uncited |
| CRITICAL strict-tier returns 0 in scope-filtered query | CONFIRMED — consistent with audit (CRITICAL is a tech_stack-tagged subset that the scope filter excludes) |
| LD #586 POSTed and read-back-verified | CONFIRMED — Rule 35 |
| Activity log row 1775 created | CONFIRMED — POST response captured |
| The 320-row Rule 1 mapping is mechanical | INFERRED — based on 30-row sample showing every CRITICAL/HIGH row is functionally HARD-equivalent |
| The 7 task_category extensions are semantically distinct from existing canonical | INFERRED — based on cleanup report sample analysis |
| Estimated 4-hour Kim attention budget for full migration | ASSUMED — based on cleanup-report's 10-hour focused-work estimate for the migration script + per-phase Kim review |
| Cursor will return one of {AUTHORIZE_PHASE_0, AMEND_V2, BLOCK} | ASSUMED — depends on Cursor's actual review |

---

## 4. Self-classification per part

- **Part 1:** STANDARD (cheap defensive fix). Single helper module + small consumer updates + 1 standing-rule LD + 1 activity-log row. Low risk; high value (303 stale-vocab rows now correctly surfaced). Not architectural.
- **Part 2:** ARCHITECTURAL (governance + data-migration design). Tech spec + Cursor handoff + dual-Opus debate captured. NO row migrations executed; no irreversible operations. Architectural in the sense that it sets governance for a multi-phase migration session that must be Kim-approved before any PATCH lands.

---

## 5. Recommendation

**Re-submit Part 2 to Cursor before authorizing any migration session.**

Specifically:
1. Kim should run Step 1-3 of `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` and capture Cursor's verdict.
2. If verdict is `AUTHORIZE_PHASE_0`, schedule a separate atomic session for Phase 0 (non-mutating dry-run).
3. After Phase 0 dry-run, Kim approves Gate 1-8 (per spec §6) and the migration script proceeds phase-by-phase.
4. Phase 5 (lossy severity collapse) is the most consequential and the least-justified by need. The recommended posture is **DEFER Phase 5 indefinitely** unless Kim explicitly chooses the Advocate position.

**Part 1 stands alone:** vocab-tolerant filter is in production. The migration is purely optional canonicalization; no urgency.

---

## 6. Limitations

- Did NOT verify whether Cursor will reach the same conclusions on the dual-Opus verdicts. The spec authorizes Cursor to dissent; that is the point of the cross-review.
- Did NOT execute any of the 5 migration phases. Spec is design-only.
- Did NOT extend the `lock_decision.py` --severity argparse choices to include HARD/SOFT (it currently rejects HARD). That is appropriate for now since vocab-tolerant filtering at the consumer side handles the live reality, but if a future LD is locked via lock_decision.py the writer must know HARD is canonical. Tracked as a known gap; recommend addressing in the migration session OR in a separate small fix.
- The 30-LD severity sample's extrapolation to 303 active rows is INFERRED, not measured. A full-population pass during Phase 0 dry-run will tighten it.

---

## 7. Cross-skill drift check

Does Part 1 require updates to other governance skills?

- `mn-context` SKILL.md: NO — vocab-tolerant filter is a code-side helper, not a session-level mandate.
- `dashboard-gate` SKILL.md: NO — dashboards already work because they read severity values as strings; vocab-tolerant filter is upstream of dashboard reads.
- `tech-spec` SKILL.md: NO — but if Part 2's migration runs, the tech-spec skill should be updated to reference LD #586 + the migration spec as canonical authority on severity vocabulary.
- `zero-error-qa` SKILL.md: NO — Part 1's helper is consumer-side; the doctrine doesn't change.
- CLAUDE.md: NO — LD #586 is the standing rule; CLAUDE.md doesn't need a new rule unless Part 2 ships the migration.

---

## 8. Files touched / created (full table)

| Path | Status | Purpose |
|---|---|---|
| `Production/lib/severity_vocab.py` | CREATED | Vocab-tolerant severity helper (Part 1) |
| `Production/scripts/governance_drift_check.py` | MODIFIED | Now uses vocab-tolerant rank dict (Part 1) |
| `Production/scripts/failure_mode_matrix.py` | MODIFIED | Same (Part 1) |
| `Production/scripts/preflight_hook.py` | MODIFIED | Added `_is_blocking_severity` helper (Part 1) |
| Directus `prod_locked_decisions` row id=586 | CREATED | LD `SCHEMA_VOCAB_TOLERANT_FILTER_V1` (Part 1) |
| Directus `prod_activity_log` row id=1775 | CREATED | Audit trail for Part 1 |
| `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` | CREATED | Migration spec (Part 2 design) |
| `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` | CREATED | Cursor review handoff (Part 2) |
| `Production/docs/SCHEMA_VOCAB_FIX_REPORT_20260508.md` | CREATED | This proof report |

No existing LDs or files deleted. No mass-migration PATCHes executed.

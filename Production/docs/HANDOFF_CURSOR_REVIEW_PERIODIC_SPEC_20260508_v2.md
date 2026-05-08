# Handoff v2 — Cursor Cross-Review of PERIODIC Class Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08 (v2 incorporates Cursor's own meta-review of v1)
**Spec under review:** `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md`

**v1 → v2 changes:** added mandatory citation format; added preflight block; added prod_locked_decisions reader enumeration; removed framing-bias language; added strict gate-decision format; added dependency-graph requirement.

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** `ls -la "Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** `shasum "Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md"` — capture hex digest.
3. **Quote the spec header:** read the first 20 lines and quote them inline as proof you read the actual file (not a stale cached copy or a hallucinated version).

If any preflight fails (file not found, etc.), **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md (867 lines). It proposes adding a third "PERIODIC" class to a SHORTCUT LD classification system (alongside existing EVENT_DRIVEN and RARE_NEVER). It would add 3 new fields to the prod_locked_decisions Directus table (review_cadence, next_review_date, last_reviewed_date) and a new branch in our weekly audit logic.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (one advocate position, one counter position). The debate concluded with a per-decision resolution. Treat this as background, not as a judgment. Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline):
1. Confirm file exists; capture size + mtime.
2. shasum the file; capture digest.
3. Quote first 20 lines of the spec verbatim.
If preflight fails, HALT and report.

ANALYSIS REQUIREMENTS:

Every concern you raise MUST be in this format:
| # | Concern (one sentence) | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (file + line ranges quoted) | Suggested mitigation | Blocker (Y/N) |

"Severity" rubric:
- CRITICAL = ship-blocker; spec must not advance to implementation
- HIGH = revise spec before implementation
- MED = address in v2 amendment OR document as known-deferred
- LOW = nice-to-have, optional

"Blocker" rubric:
- Y = Kim should NOT authorize implementation until this is resolved
- N = informational; documented and proceed acceptable

REQUIRED ANALYSIS TASKS:

A. ARCHITECTURAL & SCHEMA
   - Enumerate EVERY reader of prod_locked_decisions in the codebase. Use ripgrep or equivalent across .py, .md, .ts, .tsx, .yml. For each reader: classify break risk (none/low/med/high) given the 3 new fields. The spec must address every high-risk reader OR explicitly accept the risk.
   - What schema migration risks aren't addressed? (rollback, partial-failure, multi-environment drift)
   - What test gaps exist in the implementation phases?

B. CLASSIFICATION SYSTEM
   - Is "PERIODIC" the right name? Other ecosystems use "scheduled review" or "recurring decision."
   - Are the 6 cadence enum values (monthly, quarterly, semi-annually, annually, event-driven, none) correct? Missing? Redundant?
   - Spec proposes migrating only LD 249 to PERIODIC. Independently assess whether LD 200 (or any other current LD) should also migrate. Do NOT defer to the spec's prior conclusion.

C. AUDIT LOGIC
   - Spec proposes WARN day-0 / CRITICAL +7 days. Industry norm is to warn 30+ days before due. Is the spec's choice defensible? Cite reasoning.
   - Should there be a missed-review auto-escalation (e.g., if next_review_date is past by 30 days with no last_reviewed_date update)?

D. DECISIONS THAT MIGHT MERIT RE-DEBATE (independent of prior outcome)
   - Spec §5.4 defers `last_reviewed_date` cadence-consistency check to v2. Right call?
   - Spec §5.5 reuses severity=critical with title prefix. Should there be a new severity (e.g., "review-overdue")?

E. RISKS NOT IN §13 (Risk Assessment)
   - Silent data loss of next_review_date — audit fail-mode?
   - Audit running before schema migration completes — sequence?
   - Concurrent edit during Phase B migration — race condition?

F. SEQUENCING (Phases A→G in §16)
   - Build a dependency graph: which phase produces prerequisites for which? Write the graph inline.
   - Identify any phase where the spec's ordering creates risk if reversed.
   - Identify any phases that could parallelize without breaking dependencies.

REQUIRED OUTPUT:

1. Preflight evidence (size, mtime, shasum, first 20 lines quoted)
2. Reader enumeration table (every prod_locked_decisions reader + risk classification)
3. Concerns table (mandatory citation format above)
4. Phase dependency graph
5. Final gate decision in STRICT form (pick exactly one):

   **AUTHORIZE_IMPLEMENTATION**: spec is sound; Kim can advance to Terminal CLI implementation handoff.
   **AMEND_V2**: spec needs a revision; list specific blocker concerns that must be addressed.
   **PAUSE_FOR_REDEBATE**: spec has fundamental design issues; recommend a fresh dual-Opus or expanded review.

6. If AMEND_V2 or PAUSE: provide the specific blocker list.
```

---

## Step 3 — After Cursor responds

If verdict is **AUTHORIZE_IMPLEMENTATION**:
- Open the implementation handoff at `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`
- Spawn a Terminal CLI session

If verdict is **AMEND_V2**:
- Bring the blocker list back to Claude Code
- Author `PERIODIC_CLASS_TECH_SPEC_v2.md` addressing each blocker
- Re-run this Cursor cross-review on v2 (with the same gate format)

If verdict is **PAUSE_FOR_REDEBATE**:
- Bring the findings back to Claude Code
- Spawn fresh dual-Opus debate or expanded review session
- Do NOT advance to implementation

---

## Why this v2 exists

Cursor cross-reviewed v1 of this handoff doc and surfaced 6 valid meta-concerns: missing evidence requirements, no source-of-truth checks, no stale-content safeguard, framing bias from "Advocate wins" language, output format too loose for gate decisions, and weak sequencing validation asks. Verdict: REVISE BEFORE SHIP. v2 incorporates all 6 fixes:
1. Mandatory citation format with severity + blocker tags
2. Preflight block (file exists, hash, mtime, quote header)
3. Reader enumeration task (every prod_locked_decisions reader)
4. Removed "Advocate wins" framing; reframed as "background, not anchor"
5. Strict gate-decision format (AUTHORIZE / AMEND / PAUSE)
6. Phase dependency graph requirement

This v2 is the canonical handoff. v1 is superseded.

---

## What you DON'T need to do

- Don't have Cursor edit the spec (review-only)
- Don't have Cursor implement anything (Terminal CLI handoff)
- Don't paste sensitive info; the spec doesn't contain any

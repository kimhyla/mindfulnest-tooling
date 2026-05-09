# Handoff — Cursor Cross-Review of PATCH-FORWARD PERIODIC Class Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session, 2026-05-08
**Spec under review:** `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md`
**Companion specs (read for context only):** `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (867 lines, historical baseline), `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` (~900 lines, 9-amendment refresh), `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` (336 lines, Terminal A's narrative)
**Companion code (read for context only):** `Production/scripts/weekly_preflight_audit.py` (999 lines; PERIODIC-related code at lines 130-411)

---

## Why this handoff exists

A prior Terminal A session executed v1 of the PERIODIC class spec against prod Directus on 2026-05-08 without halting at v1's pre-implementation gates. Subsequently, a v2 spec was authored incorporating 9 Cursor-derived amendments. This created a gap: v1 is live in prod; v2 is the higher-quality spec; v2's amendments are NOT yet applied to the landed v1 code.

`PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` proposes a disciplined PATCH-FORWARD path (NOT roll-back-and-reimplement) to take v1-as-built code up to v2 quality, governed by four "Hard Rules" intended to ensure end-state code is byte-equivalent to a clean v2-from-scratch implementation.

The fundamental question for your review: **Are these four-discipline rules actually sufficient to produce sticky-note-free architecture, or are they aspirational?**

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** `ls -la "Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** `shasum "Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md"` — capture hex digest.
3. **Companion files:** capture size + shasum for `PERIODIC_CLASS_TECH_SPEC_v1.md`, `PERIODIC_CLASS_TECH_SPEC_v2.md`, `PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md`.
4. **Audit script:** capture line count + shasum for `Production/scripts/weekly_preflight_audit.py`.
5. **Quote the patch-forward spec header:** read first 25 lines and quote them verbatim as proof-of-fresh-read.

If any preflight fails (file not found, etc.), **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

Recommended additional editor tabs (read-only context):
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md`
- `Production/scripts/weekly_preflight_audit.py`

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md. It proposes how to take v1-as-built PERIODIC class code (executed without authorization by a prior session) up to v2 quality via disciplined PATCH-FORWARD instead of roll-back-and-reimplement.

The spec defines four "Hard Rules" (rewrite v1 logic in-place; rewrite v1 comments; v2 spec becomes canonical; honest activity log) and claims that if the rules are followed, the end-state code is byte-equivalent to a clean v2-from-scratch implementation.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (PATCH-FORWARD advocate vs. ROLL-BACK counter). The debate concluded with PATCH-FORWARD winning on 5/5 explicit criteria. Treat this as background, not as a judgment. Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline):
1. Confirm `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` exists; capture size + mtime.
2. shasum the patch-forward spec; capture digest.
3. Capture size + shasum for the 3 companion specs (PERIODIC_CLASS_TECH_SPEC_v1.md, PERIODIC_CLASS_TECH_SPEC_v2.md, PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md).
4. Capture line count + shasum for Production/scripts/weekly_preflight_audit.py.
5. Quote first 25 lines of the patch-forward spec verbatim.
If preflight fails, HALT and report.

ANALYSIS REQUIREMENTS:

Every concern you raise MUST be in this format:
| # | Concern (one sentence) | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (file + line ranges quoted) | Suggested mitigation | Blocker (Y/N) |

"Severity" rubric:
- CRITICAL = ship-blocker; spec must not advance to implementation
- HIGH = revise spec before implementation
- MED = address in v2 amendment of THIS spec OR document as known-deferred
- LOW = nice-to-have, optional

"Blocker" rubric:
- Y = Kim should NOT authorize implementation until this is resolved
- N = informational; documented and proceed acceptable

REQUIRED ANALYSIS TASKS:

A. THE FOUR-DISCIPLINE RULES — DO THEY ACTUALLY WORK?
   - Read §6 of the patch-forward spec. Each Hard Rule has an explicit verification mechanism (grep checks, ls checks, Directus query checks).
   - Q1 — Are these verifications GENUINELY sufficient? Could a sticky-note pattern slip through every grep? E.g., what if the v1-residue prose is paraphrased rather than verbatim — would the grep miss it?
   - Q2 — Is Rule 1 (in-place rewrite) actually achievable, or are there v2 amendments that genuinely cannot be cleanly applied as REPLACEMENTS (vs ADDITIONS)? Look at §7 per-amendment plan and challenge each "REPLACE" claim.
   - Q3 — Is the Rule 2 (comment rewrite) checklist comprehensive? grep for v1-voice phrases assumes the implementation knows which phrases are "v1-voice." Are there v1 doctrinal phrases not on the §6.2 list?
   - Q4 — Is the Rule 3 (canonical spec) move clean? Does archiving v1 to .archive/ break any inbound link from another doc that the spec didn't catch? Run a sweep.

B. TERMINAL A RESIDUES — IS ANYTHING ELSE LURKING?
   - Read `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` and `Production/scripts/weekly_preflight_audit.py` (PERIODIC area lines 130-411).
   - Q5 — Are there v1-doctrine residues in the audit script that the patch-forward spec missed? E.g., dead code, half-applied logic, comments still referring to v1 design choices that didn't make it into §6.2's table.
   - Q6 — Are there v1 residues in OTHER files (not just the audit script)? Spot-check Roadmap §1.6, LD 577 notes (via implementation report §4), CLAUDE.md, V59_LESSONS_LEARNED if present.

C. THIRD-PATH EXISTENCE
   - Q7 — Is there a third architectural option between PATCH-FORWARD and ROLL-BACK that the spec is missing? E.g., partial roll-back (revert only audit code; keep schema + LD 249 data), or feature-flag-then-deprecate-then-remove (sticky-note explicitly bounded by a TODO).
   - Q8 — If a third path exists, is it strictly better than PATCH-FORWARD on any cited criterion? Cite reasoning.

D. THE V1 SPEC FATE — DELETE OR ARCHIVE?
   - Spec recommends ARCHIVE (move to .archive/). v2 Cursor handoff (precedent) similarly archived.
   - Q9 — Counter position: should v1 be DELETED entirely, with git history serving as the only audit trail of its existence? Why or why not?
   - Q10 — If archived, is `.archive/` the right location? Project precedent shows 1 prior archive file; is archive convention well-established or should this spec set/refine it?

E. RISKS NOT IN §11 (Risk Assessment)
   - Q11 — Cross-session race: if the implementation session is running while another terminal is mid-cron of the audit, does the §6 grep verification window expose any consistency gap?
   - Q12 — `python-dateutil` dependency: if it's NOT installed and the implementation session vendors `relativedelta` (per §11 mitigation), is that vendoring discipline-compliant or itself sticky-note?
   - Q13 — Activity-log row ordering: the patch-forward spec says one new row at session execution date. Does this create gaps with the v1 implementation rows (1763-1768) when a future reader reconstructs the chronology?

F. SEQUENCING (Phases A2 → F2 in §8)
   - Q14 — Build a dependency graph: which phase produces prerequisites for which? Write the graph inline.
   - Q15 — Identify any phase where the spec's ordering creates risk if reversed.
   - Q16 — Confirm spec's parallelization claim: B2/C2/D2/E2 parallelizable after A2 dry-run.

G. DOCTRINE PRECEDENT
   - The spec sets a doctrine for future Terminal-A-style incidents: "PATCH-FORWARD by default if (a) schema additive, (b) data correct under new spec, (c) discipline applicable; otherwise ROLL-BACK."
   - Q17 — Is this doctrine sound at scale? Imagine 3 more incidents in 12 months — does PATCH-FORWARD-as-default produce stratified architecture or stay clean?
   - Q18 — Does the doctrine create a perverse incentive — i.e., does "patch-forward bails out unauthorized executions" inadvertently encourage Terminal-A-style behavior in the future?

REQUIRED OUTPUT:

1. Preflight evidence (size, mtime, shasum, line count, first 25 lines quoted)
2. Concerns table (mandatory citation format above) — minimum coverage of Q1-Q18
3. Phase dependency graph (Q14)
4. Final gate decision in STRICT form (pick exactly one):

   **AUTHORIZE_IMPLEMENTATION**: spec is sound; Kim can advance to Terminal CLI implementation handoff.
   **AMEND_V2**: spec needs a revision; list specific blocker concerns that must be addressed.
   **PAUSE_FOR_REDEBATE**: spec has fundamental design issues; recommend a fresh dual-Opus or expanded review.

5. If AMEND_V2 or PAUSE: provide the specific blocker list with severity and citation.
6. Specific recommendation on the v1-spec FATE question (Q9-Q10): DELETE / ARCHIVE / OTHER.
```

---

## Step 3 — After Cursor responds

If verdict is **AUTHORIZE_IMPLEMENTATION**:
- Author the implementation handoff at `Production/docs/HANDOFF_PATCH_FORWARD_PERIODIC_IMPLEMENTATION_<date>.md` mirroring the v1 implementation handoff structure but with §10 gates from the patch-forward spec
- Spawn a Terminal CLI session

If verdict is **AMEND_V2**:
- Bring the blocker list back to Claude Code
- Author `PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md` addressing each blocker
- Re-run this Cursor cross-review on v2 (with the same gate format)

If verdict is **PAUSE_FOR_REDEBATE**:
- Bring the findings back to Claude Code
- Spawn fresh dual-Opus debate (the dual-Opus question is most likely "is PATCH-FORWARD the right doctrine?" or "is there a third path?")
- Do NOT advance to implementation

---

## Specific questions Kim wants Cursor to answer regardless of verdict

These appear in the prompt above as Q1-Q18 but are restated here for emphasis:

1. **(Q1-Q4)** Do the four-discipline rules actually produce sticky-note-free architecture, or are they aspirational? Is the verification (grep + ls + Directus query) sufficient?
2. **(Q5-Q6)** Are there Terminal A residues (comments, dead code, half-applied logic) that the patch-forward spec specifically missed?
3. **(Q7-Q8)** Is there a third path between PATCH-FORWARD and ROLL-BACK that the spec is missing?
4. **(Q9-Q10)** Should v1 spec be deleted entirely or archived? Why/why not?
5. **(Q14-Q16)** Is the phase sequence and parallelization correct?
6. **(Q17-Q18)** Does the doctrine ("PATCH-FORWARD by default") set a sound precedent? Does it create perverse incentives?

---

## Why this handoff is structured this way

This handoff mirrors `HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md` (the v2 Cursor handoff that incorporated Cursor's own meta-review of v1):

- **Mandatory citation format** with severity + blocker tags (forces evidentiary rigor)
- **Preflight block** (file exists, hash, mtime, quote header — defends against stale or hallucinated reads)
- **Strict gate-decision format** (AUTHORIZE / AMEND_V2 / PAUSE — prevents soft "looks fine" verdicts)
- **Reader / dependency graph requirements** (forces structural analysis, not just spot reads)
- **Removed framing bias** (told Cursor explicitly not to anchor on the dual-Opus resolution)

Plus three new requirements specific to this spec:

- **Discipline-rule sufficiency** (Q1-Q4): the spec's load-bearing claim is that §6 rules ensure clean end-state. Cursor must independently verify or challenge this.
- **Doctrine-precedent analysis** (Q17-Q18): the spec sets a doctrine for future incidents. Cursor must evaluate the precedent at scale.
- **Third-path search** (Q7-Q8): the dual-Opus binary may be missing a third option.

---

## What you DON'T need to do

- Don't have Cursor edit the spec (review-only)
- Don't have Cursor implement anything (that's a separate Terminal CLI handoff)
- Don't paste sensitive info; the spec doesn't contain any
- Don't dual-review the v2 spec (Cursor already reviewed v2 in the prior round; v2 is canonical for amendment content). Cursor is reviewing the PATCH-FORWARD path itself.

---

*End of HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md.*

# Handoff v2-hardened — Cursor Cross-Review of DS-26 Mechanical Gate Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md`
**Companion docs:**
- `.claude/skills/zero-error-qa/SKILL.md` lines 338-390 (DS-26 discipline-only)
- `.claude/skills/mn-context/SKILL.md` lines 251-321 (DS-20 / DS-22 precedent patterns)
- `Production/docs/HANDOFF_TEMPLATE_v1.md` (handoff-side authoring mandate; canonical HALT-gate format)
- `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` + `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` (originating incident)

This handoff incorporates the v2-hardened format (preflight block, mandatory citation format, strict gate-decision verdict, framing-bias removal) proven on the PERIODIC spec Cursor review.

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** `ls -la "Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** `shasum "Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture hex digest.
3. **Quote the spec header:** read the first 25 lines and quote them inline as proof you read the actual file (not a stale cached copy or hallucinated version).
4. **Companion-file existence checks:** confirm each of these exists (capture mtime):
   - `.claude/skills/zero-error-qa/SKILL.md`
   - `.claude/skills/mn-context/SKILL.md`
   - `Production/docs/HANDOFF_TEMPLATE_v1.md`
   - `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`

If any preflight check fails, **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md. It proposes a mechanical SAVE-time gate ("Step 2.5c" in mn-context SKILL.md) that detects when a session executed a handoff containing a HALT gate but bypassed it. The spec is design-only; implementation is deferred.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (one advocate position, one counter position). The debate resolution selected Step 2.5c at SAVE time over a pre-execution PostToolUse hook variant (deferred to v2). Treat this as background, not as a judgment. Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline):
1. Confirm spec file exists; capture size + mtime.
2. shasum the spec file; capture digest.
3. Quote first 25 lines of the spec verbatim.
4. Confirm companion files exist: zero-error-qa SKILL.md, mn-context SKILL.md, HANDOFF_TEMPLATE_v1.md, HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md.
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

A. DETECTION ALGORITHM SOUNDNESS
   - Walk through §6's algorithm against each test case in §13. For each test, predict the output and confirm it matches the "Expected verdict" column. Flag any case where the algorithm as specified would produce a different verdict than §13 claims.
   - §3.4 has a 7-row truth table mapping (parsed gate_count, declared N) to (PASS / FAIL reason). Is the table complete? Find at least one combination not covered.
   - §3.4.1 evidence-citation cross-check: is "12-word substring overlap" a defensible heuristic? What's the false-negative rate (real check missed) vs false-positive rate (faked echo accepted)?
   - §3.5 MET/NOT MET cross-check: is `complete_writes` defined precisely enough? What counts as a `*_COMPLETE` row?

B. REGEX PARSER ROBUSTNESS
   - §3.3 regex set: run each regex against the actual `## HALT gates` example in HANDOFF_TEMPLATE_v1.md lines 60-74. Confirm every regex matches as intended.
   - What handoff-authoring patterns survive the v1 template but break the parser? Examples to consider: tables with merged cells, tables with extra whitespace columns, gates as nested bullets instead of numbered lists, autonomous-mode reminder paraphrased instead of verbatim.
   - Will the parser handle handoffs that have BOTH `## HALT gates` and `## HALT Gates` (case mismatch in same doc, hypothetical)? What about UTF-8 BOMs?

C. FALSE-POSITIVE GUARD (§3.7)
   - The three-condition silent-skip: (no candidate handoffs) AND (no Agent calls) AND (no `*_COMPLETE` writes). Find a session shape that genuinely has zero HALT-gate context but trips one of the three conditions (false-fire).
   - Find a session shape that bypasses a HALT gate but escapes all three conditions (false-skip — the gate doesn't fire when it should).

D. ANTI-FAKERY DEFENSE (§3.4.1)
   - The spec acknowledges this is partial. Quantify: how many lines of fake-output does an autonomous agent need to produce to bypass §3.4.1? Is the "audit trail of fabrication" claim (§4.3 advocate rebuttal) defensible — would a casual post-hoc audit by Kim actually catch the fabrication?
   - Is there a stronger anti-fakery mechanism that fits in v1 without growing into the v2 hook? (e.g., requiring the agent to quote the gate's evidence_source string verbatim from the handoff text, with a substring-match cross-check against the handoff content as ground truth.)

E. RISKS NOT IN §11
   - The spec lists 8 risks. Find at least 2 risks not enumerated. Examples to seed (not exhaustive — find your own): adversarial-author handoff designed to defeat the parser; race condition between session SAVE and async Directus write of `*_COMPLETE` rows; disk-state inconsistency where halt-report exists but is empty.
   - The override-leak risk (last row in §11) assumes the audit-row rationale is "Kim-typed, not agent-typed". How is that distinction enforced mechanically? Is it actually enforceable, or is it discipline?

F. SCHEMA & AUDIT-TRAIL
   - The spec claims no schema changes are needed. Verify: does any field in §3.4.1 / §3.5 / §6 require a column that doesn't exist on `prod_activity_log` today? (Reference Directus schema if you can.)
   - The override audit row name is `DS_26_MECHANICAL_GATE_BYPASSED`. Does that conflict with any existing audit-row naming convention?

G. SEQUENCING (§8 Phases A-H)
   - Build a dependency graph: which phase produces prerequisites for which? Write the graph inline.
   - Phase E amends DS-26 line 390. Phase F amends DS-26 again for §6.1's "one declaration per handoff" rule. Are these safely in sequence (E before F)? Could they collide if both ran in parallel?
   - Phase G test cases come AFTER Phase F. Should Phase G's tests run BEFORE Phase E (which closes the blocker), so that test failures don't accidentally close `DS_26_MECHANICAL_GATE_PENDING` prematurely?

H. CROSS-SKILL DRIFT
   - The spec lists 4 cross-skill drift sites in §14. Find any drift site missing from the list (e.g., does dashboard-gate need to know about Step 2.5c? does tech-spec skill need a reference?).
   - Does this spec require an update to CLAUDE.md (e.g., a new Rule, or an amendment to Rule 19's "no path open for error" prose)?

REQUIRED OUTPUT:

1. Preflight evidence (size, mtime, shasum, first 25 lines quoted, companion-file mtimes)
2. Algorithm walk-through (one row per §13 test case, predicted vs claimed)
3. Concerns table (mandatory citation format above)
4. Phase dependency graph (§8 Phases A-H)
5. Cross-skill drift completeness check
6. Final gate decision in STRICT form (pick exactly one):

   **AUTHORIZE_IMPLEMENTATION**: spec is sound; Kim can advance to a Terminal CLI implementation handoff.
   **AMEND_V2**: spec needs a revision; list specific blocker concerns that must be addressed.
   **PAUSE_FOR_REDEBATE**: spec has fundamental design issues; recommend a fresh dual-Opus or expanded review.

7. If AMEND_V2 or PAUSE: provide the specific blocker list (one row per blocker).
```

---

## Step 3 — After Cursor responds

If verdict is **AUTHORIZE_IMPLEMENTATION**:
- Author a separate Terminal CLI implementation handoff at `Production/docs/HANDOFF_DS_26_MECHANICAL_GATE_IMPLEMENTATION_<DATE>.md` (use HANDOFF_TEMPLATE_v1.md format — REQUIRED `## HALT gates` section enumerating §10's 10 pre-implementation gates).
- Spawn the Terminal CLI session per the implementation handoff.

If verdict is **AMEND_V2**:
- Bring the blocker list back to Claude Code.
- Author `DS_26_MECHANICAL_GATE_TECH_SPEC_v2.md` addressing each blocker.
- Re-run this Cursor cross-review on v2 (with the same gate format).

If verdict is **PAUSE_FOR_REDEBATE**:
- Bring the findings back to Claude Code.
- Spawn fresh dual-Opus debate or expanded review session.
- Do NOT advance to implementation.

---

## Why this v2-hardened format

The v1 PERIODIC Cursor handoff was meta-reviewed by Cursor itself and surfaced 6 issues: missing evidence requirements, no source-of-truth checks, no stale-content safeguard, framing bias from "Advocate wins" language, output format too loose for gate decisions, weak sequencing validation. v2-hardened incorporates all 6 fixes. This DS-26 handoff inherits the v2-hardened format directly:

1. Mandatory citation format with severity + blocker tags
2. Preflight block (file exists, hash, mtime, header quote, companion-file existence)
3. Specific reader/dependency enumeration tasks (analysis sections A through H)
4. No "Advocate wins" framing; reframed as "background, not anchor"
5. Strict gate-decision format (AUTHORIZE / AMEND / PAUSE)
6. Phase dependency graph requirement (§8 Phases A-H)

---

## What you DON'T need to do

- Don't have Cursor edit the spec (review-only).
- Don't have Cursor implement Step 2.5c (Terminal CLI handoff after AUTHORIZE).
- Don't have Cursor write Directus rows or close the `DS_26_MECHANICAL_GATE_PENDING` blocker — implementation session does that, not review.
- Don't paste sensitive info; the spec doesn't contain any.

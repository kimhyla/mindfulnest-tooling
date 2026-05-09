# Handoff v2 — Cursor Cross-Review of DS-26 Mechanical Gate Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md`
**Companion docs:**
- `.claude/skills/zero-error-qa/SKILL.md` lines 338-390 (DS-26 discipline-only)
- `.claude/skills/mn-context/SKILL.md` lines 251-321 (DS-20 / DS-22 precedent patterns)
- `Production/docs/HANDOFF_TEMPLATE_v1.md` (handoff-side authoring mandate; canonical HALT-gate format)
- `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` + `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` (originating incident)

This handoff is **v2** — it incorporates 4 Cursor amendments on top of v1 (which is preserved as historical baseline at `HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508.md`). The v2-hardened format (preflight block, mandatory citation format, strict gate-decision verdict, framing-bias removal) carries forward unchanged from v1.

---

## §0.1 v2 Changelog — Cursor amendments applied

Cursor's review of v1 returned **AUTHORIZE_IMPLEMENTATION with minor hardening** and surfaced 4 findings. Each is addressed below; v1 sections are preserved verbatim except where a finding required a targeted insert/replace.

| # | Cursor finding | Severity | v2 section addressing it |
|---|----------------|----------|--------------------------|
| 1 | Preflight integrity: companion check is existence-only; need shasum or first-line signature for all 4 companion files | MED | Step 0 §4 (companion-file shasum + first-line signature block) |
| 2 | Regex robustness corpus: §3.3 asks for validation but no minimum corpus | MED | Analysis Task B (minimum 10 positive + 10 negative cases with explicit pass/fail tally) |
| 3 | Anti-fakery acceptance threshold: quantification asked but no verdict trigger | MED | Analysis Task D (hard threshold: ≤5 lines + no detectable contradiction ⇒ AMEND_V2) |
| 4 | Schema-check fallback: no rule when Directus unreachable | LOW | Analysis Task F (explicit fallback: classify as unresolved MED risk; do not auto-authorize on that point) |

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** `ls -la "Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** `shasum "Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md"` — capture hex digest.
3. **Quote the spec header:** read the first 25 lines and quote them inline as proof you read the actual file (not a stale cached copy or hallucinated version).
4. **Companion-file integrity checks (v2 amendment #1 — shasum + first-line signature):** for each of the 4 companion files below, capture mtime, run `shasum`, AND quote the first non-blank line verbatim. Existence-only is no longer sufficient.

   | Companion file | Required check |
   |----------------|----------------|
   | `.claude/skills/zero-error-qa/SKILL.md` | `ls -la` + `shasum` + first non-blank line quoted |
   | `.claude/skills/mn-context/SKILL.md` | `ls -la` + `shasum` + first non-blank line quoted |
   | `Production/docs/HANDOFF_TEMPLATE_v1.md` | `ls -la` + `shasum` + first non-blank line quoted |
   | `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` | `ls -la` + `shasum` + first non-blank line quoted |

   Acceptance criterion: 4 shasum digests + 4 first-line quotes emitted inline. If any digest cannot be computed OR any quote cannot be reproduced, **HALT and report which companion failed**. Existence-only does NOT pass v2 preflight.

5. **LD 578 row check (v2 amendment #4 — schema-check fallback baseline):** attempt to query Directus `prod_locked_decisions` for LD 578 row to confirm it exists. If Directus is unreachable, record "Directus unreachable — schema-check deferred to Analysis Task F fallback rule" and proceed; do NOT HALT for this single check.

If any preflight check (1-4) fails, **HALT and report**. Do not proceed.

---

## Step 1 — Open the project in Cursor

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/DS_26_MECHANICAL_GATE_TECH_SPEC_v1.md. It proposes a mechanical SAVE-time gate ("Step 2.5c" in mn-context SKILL.md) that detects when a session executed a handoff containing a HALT gate but bypassed it. The spec is design-only; implementation is deferred.

This is the v2 review handoff. v1 found AUTHORIZE_IMPLEMENTATION with 4 minor hardening points. v2 incorporates those 4 fixes and asks you to re-verify with stricter preflight + corpus + threshold rules.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (one advocate position, one counter position). The debate resolution selected Step 2.5c at SAVE time over a pre-execution PostToolUse hook variant (deferred to v2). Treat this as background, not as a judgment. Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline) — v2 hardened:
1. Confirm spec file exists; capture size + mtime.
2. shasum the spec file; capture digest.
3. Quote first 25 lines of the spec verbatim.
4. v2 AMENDMENT #1 — Companion integrity (no longer existence-only): for each of zero-error-qa SKILL.md, mn-context SKILL.md, HANDOFF_TEMPLATE_v1.md, HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md, capture mtime AND shasum AND quote first non-blank line verbatim. 4 digests + 4 first-line quotes inline.
5. v2 AMENDMENT #4 — LD 578 row check: attempt Directus query. If unreachable, log "Directus unreachable — fallback rule applies in Task F". Do NOT HALT for this single check.
If preflight 1-4 fails, HALT and report.

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

B. REGEX PARSER ROBUSTNESS — v2 AMENDMENT #2 (corpus required)
   - §3.3 regex set: run each regex against the actual `## HALT gates` example in HANDOFF_TEMPLATE_v1.md lines 60-74. Confirm every regex matches as intended.
   - **REQUIRED CORPUS (new in v2):** construct a test corpus with at least **10 positive cases** (handoff fragments the parser MUST match) and at least **10 negative cases** (fragments the parser MUST NOT match — false-positive bait). Emit a table with columns: `# | case kind (POS/NEG) | snippet | expected verdict | actual verdict | pass/fail`. Tally pass/fail counts at the bottom (e.g., "POS 10/10, NEG 10/10").
   - Acceptance criterion: if corpus pass rate < 100% on either POS or NEG, the regex set FAILS Task B and verdict must include AMEND_V2 for §3.3.
   - Seed positive cases (you must add more): tables with merged cells; tables with extra whitespace columns; gates as nested bullets instead of numbered lists; autonomous-mode reminder paraphrased instead of verbatim; handoffs containing BOTH `## HALT gates` and `## HALT Gates` (case mismatch); UTF-8 BOMs.
   - Seed negative cases (you must add more): handoffs WITHOUT a HALT-gate section; handoffs with `## HALT gates` mentioned only in prose (e.g., "we removed the ## HALT gates section last week"); code-fenced examples that quote a HALT-gate template inside a triple-backtick block.

C. FALSE-POSITIVE GUARD (§3.7)
   - The three-condition silent-skip: (no candidate handoffs) AND (no Agent calls) AND (no `*_COMPLETE` writes). Find a session shape that genuinely has zero HALT-gate context but trips one of the three conditions (false-fire).
   - Find a session shape that bypasses a HALT gate but escapes all three conditions (false-skip — the gate doesn't fire when it should).

D. ANTI-FAKERY DEFENSE (§3.4.1) — v2 AMENDMENT #3 (hard threshold)
   - The spec acknowledges this is partial. Quantify: how many lines of fake-output does an autonomous agent need to produce to bypass §3.4.1?
   - **HARD THRESHOLD (new in v2):** if a fabricated bypass can succeed with **≤5 lines of fake output AND no detectable internal contradiction**, the verdict MUST be AMEND_V2 for §3.4.1 — auto-authorize is forbidden on that point. Document your line-count estimate and the contradiction-detection chain explicitly.
   - Is the "audit trail of fabrication" claim (§4.3 advocate rebuttal) defensible — would a casual post-hoc audit by Kim actually catch the fabrication?
   - Is there a stronger anti-fakery mechanism that fits in v1 without growing into the v2 hook? (e.g., requiring the agent to quote the gate's evidence_source string verbatim from the handoff text, with a substring-match cross-check against the handoff content as ground truth.)

E. RISKS NOT IN §11
   - The spec lists 8 risks. Find at least 2 risks not enumerated. Examples to seed (not exhaustive — find your own): adversarial-author handoff designed to defeat the parser; race condition between session SAVE and async Directus write of `*_COMPLETE` rows; disk-state inconsistency where halt-report exists but is empty.
   - The override-leak risk (last row in §11) assumes the audit-row rationale is "Kim-typed, not agent-typed". How is that distinction enforced mechanically? Is it actually enforceable, or is it discipline?

F. SCHEMA & AUDIT-TRAIL — v2 AMENDMENT #4 (fallback rule)
   - The spec claims no schema changes are needed. Verify: does any field in §3.4.1 / §3.5 / §6 require a column that doesn't exist on `prod_activity_log` today? (Reference Directus schema if you can.)
   - The override audit row name is `DS_26_MECHANICAL_GATE_BYPASSED`. Does that conflict with any existing audit-row naming convention?
   - **FALLBACK RULE (new in v2):** if Directus schema is unreachable from your environment OR if you cannot confirm the `prod_activity_log` field set, do NOT auto-authorize on §F. Instead, classify §F as **unresolved MED risk** in the concerns table and surface it as a precondition Kim must close manually before implementation. Auto-authorization is forbidden when schema cannot be read.

G. SEQUENCING (§8 Phases A-H)
   - Build a dependency graph: which phase produces prerequisites for which? Write the graph inline.
   - Phase E amends DS-26 line 390. Phase F amends DS-26 again for §6.1's "one declaration per handoff" rule. Are these safely in sequence (E before F)? Could they collide if both ran in parallel?
   - Phase G test cases come AFTER Phase F. Should Phase G's tests run BEFORE Phase E (which closes the blocker), so that test failures don't accidentally close `DS_26_MECHANICAL_GATE_PENDING` prematurely?

H. CROSS-SKILL DRIFT
   - The spec lists 4 cross-skill drift sites in §14. Find any drift site missing from the list (e.g., does dashboard-gate need to know about Step 2.5c? does tech-spec skill need a reference?).
   - Does this spec require an update to CLAUDE.md (e.g., a new Rule, or an amendment to Rule 19's "no path open for error" prose)?

REQUIRED OUTPUT:

1. Preflight evidence (size, mtime, shasum, first 25 lines quoted, 4 companion shasum+first-line quotes per amendment #1, LD 578 row check or unreachable-note per amendment #4)
2. Algorithm walk-through (one row per §13 test case, predicted vs claimed)
3. Regex corpus table (10+ POS, 10+ NEG, pass/fail tally per amendment #2)
4. Anti-fakery line-count estimate + contradiction-chain analysis per amendment #3 (verdict implication if ≤5 lines + no contradiction)
5. Concerns table (mandatory citation format above)
6. Phase dependency graph (§8 Phases A-H)
7. Cross-skill drift completeness check
8. Schema check or fallback declaration per amendment #4
9. Final gate decision in STRICT form (pick exactly one):

   **AUTHORIZE_IMPLEMENTATION**: spec is sound; Kim can advance to a Terminal CLI implementation handoff. Forbidden if amendment #2 corpus < 100%, OR amendment #3 ≤5-line bypass possible, OR amendment #4 schema unreadable.
   **AMEND_V2**: spec needs a revision; list specific blocker concerns that must be addressed.
   **PAUSE_FOR_REDEBATE**: spec has fundamental design issues; recommend a fresh dual-Opus or expanded review.

10. If AMEND_V2 or PAUSE: provide the specific blocker list (one row per blocker).
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

## Why this v2 handoff (delta vs v1)

v1 already used the v2-hardened format inherited from the PERIODIC Cursor review. Cursor's review of the v1 handoff returned AUTHORIZE_IMPLEMENTATION but flagged 4 minor hardening points. v2 closes those gaps:

1. **Preflight integrity (§Step 0 #4)** — companion-file existence is no longer sufficient; v2 requires shasum + first non-blank line for all 4 companion files. This catches a stale or partially-written companion that an existence check would miss.
2. **Regex corpus (§Task B)** — v1 asked Cursor to validate regex robustness but did not require a minimum corpus. v2 mandates at least 10 positive + 10 negative test cases with an explicit pass/fail tally; sub-100% blocks AUTHORIZE.
3. **Anti-fakery threshold (§Task D)** — v1 asked Cursor to quantify bypass cost but did not tie quantification to a verdict. v2 sets a hard floor: if a fabricated bypass succeeds with ≤5 lines of fake output and no detectable contradiction, AUTHORIZE is forbidden.
4. **Schema fallback (§Task F)** — v1 asked Cursor to verify schema but did not specify behavior when Directus is unreachable. v2 routes that failure mode to "unresolved MED risk" rather than allowing AUTHORIZE on an unread schema.

The structural backbone (Step 0 preflight, Step 1 open project, Step 2 prompt block, Step 3 verdict branching, Why-this-format prose) is preserved unchanged from v1.

---

## What you DON'T need to do

- Don't have Cursor edit the spec (review-only).
- Don't have Cursor implement Step 2.5c (Terminal CLI handoff after AUTHORIZE).
- Don't have Cursor write Directus rows or close the `DS_26_MECHANICAL_GATE_PENDING` blocker — implementation session does that, not review.
- Don't paste sensitive info; the spec doesn't contain any.

---

*End of HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v2.md.*

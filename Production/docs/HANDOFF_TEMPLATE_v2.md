# Handoff Template v2

**Authority:** LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (2026-05-08, the v1 template's authority) + LD `WORKTREE_CONFUSION_PREVENTION_V1` (2026-05-08, this v2's additional authority).
**Companion rules:** zero-error-qa SKILL.md DS-26 (Gate-Check Discipline — No Autonomous-Mode Bypass) + DS-27 (Worktree Confusion Prevention — Absolute-Path Discipline).

**Why v2 exists:** Cursor cross-reviewed three different v1-derived handoffs (Q1 Part 2 spec, DS-23/24/25 gate spec, DS-26 gate spec) on 2026-05-08 and surfaced the SAME 3 MED hardening findings on each. The recurrence is a TEMPLATE-level signal: v1 of the template authorized handoff structure, but did not encode the citation-anchoring discipline, concise→full escalation rule, or numeric AMEND_V2 thresholds that Cursor consistently flags as missing. v2 bakes those 3 fixes into the template itself so future handoffs inherit them automatically and do not require per-handoff re-amendment.

A second incident — Terminal-A-style worktree confusion (agents `cd`-ing into `.claude/worktrees/...` subdirectories and editing the wrong tree, hit twice in this session on duplicate-deletion + calendar-dep wiring work) — adds a second hard rule (absolute-path-only filesystem discipline) preserved as DS-27 + a hard rule in this template.

This template is **canonical for all handoffs** authored from 2026-05-08 forward. Existing handoffs (including v1-format historical handoffs) may stay as-is; new handoffs MUST adopt this v2 structure.

---

## §0.1 v2 Changelog — recurring Cursor findings + worktree-confusion incidents

| # | Source pattern | Severity | v2 fix |
|---|----------------|----------|--------|
| 1 | Brittle line-number / fixed-line-range quotes in preflight blocks (recurring across Q1 Part 2 v1, DS-23/24/25 v1, DS-26 v1 Cursor reviews) | MED → template-level | §"Anchored citation discipline" + Step 0 preflight rule |
| 2 | Concise mode allowed without full-evidence dependency: under-evidenced area could pass concise (recurring across same 3 reviews) | MED → template-level | §"Concise→full escalation rule" mandate |
| 3 | Analysis sections ask "is X acceptable?" with no numeric verdict trigger; Cursor could pass on hand-wave (recurring across same 3 reviews) | MED → template-level | §"Numeric AMEND_V2 threshold pattern" mandate |
| 4 | Worktree confusion: agents `cd`-ing into `.claude/worktrees/<name>/` and editing the wrong tree (twice this session — duplicate-deletion + calendar-dep wiring) | HARD → template-level | §"Absolute-path filesystem discipline" hard rule |

**Source handoffs used as evidence for the recurring 3 findings:**
- `Production/docs/HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508.md` (v1) → reviewed → `HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md` (v2, this session)
- `Production/docs/HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508.md` (v1) → reviewed → `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` (v2, parallel agent)
- `Production/docs/HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508.md` (v1) → reviewed → `HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v2.md` (v2, parallel agent)

**v1 sections preserved verbatim:** Required structure outline, HALT gates §A (autonomous-mode reminder), HALT gates §B (gate enumeration), Hard rules required bullets, Final report required structure, anti-patterns list, cross-references, origin incident record. Edits below are insert/append, not replace.

---

## Required structure (preserved from v1, extended)

A handoff document MUST contain, in order, these sections:

1. **Header** — title, target session, source session/spec, estimated time.
2. **What you're doing** — one-paragraph description of the task.
3. **HALT gates** — explicit enumeration (see §"HALT gates" below). REQUIRED even if the answer is "none".
4. **Pre-flight** — preconditions to verify before Phase 2 (Mechanical Execution). MUST use anchored citation discipline per v2 §"Anchored citation discipline" below.
5. **Sequence** — phases A→N with deliverables, gates, rollback per phase.
6. **Hard rules** — MUST/MUST-NOT bullets specific to this task. MUST include the v2 absolute-path discipline rule + concise→full escalation rule (where applicable) + numeric AMEND_V2 thresholds (where the handoff is a review handoff with verdict semantics).
7. **Final report format** — proof-of-execution structure expected at session end.

Any additional sections (reference files, fixture state, etc.) are optional and follow §6.

---

## HALT gates — REQUIRED section (preserved verbatim from v1)

Every handoff MUST contain a section titled exactly `## HALT gates` (or `## Halt Gates`) immediately after "What you're doing" and BEFORE "Pre-flight". This is the section DS-26 detection scans first.

The section MUST contain BOTH of the following:

### A. The autonomous-mode reminder (verbatim)

The following paragraph MUST appear at the top of the HALT gates section, copy-pasted verbatim:

> **Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.
>
> Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### B. Gate enumeration

A numbered list of gates that MUST be MET before Phase 2 begins. For each gate:

- **Gate text** — the precondition stated as a yes/no question Claude can answer by inspecting evidence.
- **Evidence source** — exactly where to look (Directus collection + row id, file path + anchored section/snippet, chat message quote, prior session's activity-log row, etc.) — anchored citation discipline (v2) applies; do NOT cite by absolute line number alone.
- **Pass criterion** — what constitutes a clear MET state.
- **Fail action** — what to write to `prod_activity_log` and where to surface (always: `HALTED_AWAITING_AUTHORIZATION` row + halt-report doc + Kim surface).

If the handoff has zero HALT gates, the section MUST still exist and read:

> No HALT gates. Standard preflight applies (Phase 0 / DS-19 standing escape hatches still active).

This is a BLOCKING declaration, not silence — DS-26 detection treats absence-of-HALT-gates-section as a violation of handoff hygiene, not a "no gates implied".

---

## HALT gates — example (preserved verbatim from v1)

```markdown
## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Phase 2)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Has Cursor reviewed v1 of the spec? | `prod_locked_decisions` notes for `<LD_KEY>` OR a `CURSOR_REVIEW_PASSED_<spec>` row in `prod_activity_log` | At least one such row dated >= spec authoring date | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; write halt-report; surface to Kim |
| 2 | Are §15's pre-implementation gates 1-10 checked off? | Spec §15 itself OR `prod_locked_decisions` notes for `<LD_KEY>` OR a `PRE_IMPLEMENTATION_GATES_APPROVED_<spec>` row | All 10 gates have explicit Kim-approved evidence | Write `HALTED_AWAITING_AUTHORIZATION` row; halt-report; surface |
| 3 | Has the migration cohort drift been verified? | Anchored: locate `## §7` (cohort drift) header in spec; capture line range; confirm Directus `prod_locked_decisions` row `<N>` `notes` field substring-matches the §7 paragraph | Notes match spec content (substring-overlap, not absolute-line) | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
```

---

## v2 NEW — Anchored citation discipline (replaces "quote line N" patterns)

**Recurring Cursor finding #1.** v1 templates and handoffs frequently asked reviewers to "quote lines 32-35 verbatim" or "quote first 30 lines verbatim" as proof-of-fresh-read. This is brittle: a benign edit shifts lines, the preflight HALTs incorrectly, and the reviewer wastes a turn negotiating around the false-fail.

**v2 mandate:** every preflight or evidence-citation requirement that asks the reviewer to "read file X" MUST cite by **anchored section/header + snippet match**, not by absolute line number alone.

### The pattern

For each citation requirement, the handoff specifies:

1. **Anchor** — a header text, section number (`## §6`, `## DS-23`), or content marker (`BYPASS=`, `OVERRIDE=`, `--no-verify`) that the reviewer can locate by string-search regardless of line position.
2. **Capture** — the reviewer captures the line range the anchor currently occupies (so future audits can resolve the citation), AND
3. **Snippet match** — the reviewer quotes the substring at/under the anchor that proves they read the actual content (not a cached or fabricated view).

### Example transformation

**v1 pattern (deprecated):**
> "Quote `Production/scripts/git_hooks/pre-commit` lines 32-35 verbatim."

**v2 pattern (canonical):**
> "Locate the existing override-pattern block in `Production/scripts/git_hooks/pre-commit` (anchor: `BYPASS=` or `OVERRIDE=` or `--no-verify` handling, whichever matches the existing pattern); capture current line range; quote the matched block verbatim."

### Required citation table

For handoffs with 2+ citation requirements, render the requirements as a table with columns:

| Anchor target | v1 (deprecated) | v2 anchored check |
|---------------|-----------------|-------------------|
| `<file path + content focus>` | `<the old line-number-based requirement>` | `<header/snippet anchor + capture-line-range + verbatim-quote rule>` |

This makes the v2 discipline explicit and audit-able.

### Acceptance criterion

If any anchor cannot be located by header/snippet pattern, the reviewer HALTs and reports which anchor failed. Line-shift tolerance is intentional in v2; missing-anchor is a real failure.

---

## v2 NEW — Concise→full escalation rule (mandate)

**Recurring Cursor finding #2.** v1 review handoffs sometimes authorized concise mode "if no blockers found" without specifying behavior when the reviewer cannot fully evidence required analysis areas. Reviewers could pass concise mode while leaving required tasks under-evidenced (e.g., "I think §X is fine" without quoted evidence) — a silent failure of review rigor.

**v2 mandate:** every handoff that supports a concise/short verdict path MUST include the following clause (verbatim or near-verbatim) in the prompt block:

> If any required section cannot be evidenced, full mode is mandatory.

### Operational definition of "cannot be evidenced"

The reviewer is REQUIRED to escalate to full mode if any of the following holds for any required analysis area:

- Could not read a referenced file (path missing, permission denied, mtime suggests stale cache).
- Could not reproduce an anchor (no header/snippet match in the actual file content).
- The spec section the question targets is missing or ambiguous.
- The reviewer's evidence is "I think" or "probably" rather than a quoted citation.
- The reviewer skipped the question to save tokens.

Documenting WHICH area was under-evidenced is REQUIRED in the full-mode output.

### Where to place the clause

For Cursor-cross-review handoffs, the clause goes inside the Step 2 prompt block — under a heading like `CONCISE→FULL ESCALATION RULE — v2 amendment (mandatory)` — so it ships verbatim to the reviewer.

For implementation handoffs (no concise mode), the clause is N/A; document N/A explicitly to prove the author considered the rule.

---

## v2 NEW — Numeric AMEND_V2 threshold pattern (mandate)

**Recurring Cursor finding #3.** v1 review handoffs frequently asked "is X acceptable?" — about cost caps, FP rates, recursion-guard joint-failure probability, race-condition windows, etc. — with no numeric trigger that ties the answer to a verdict. Reviewers could opine ("seems fine") and authorize without a defensible threshold. The same hand-wave appeared on cost-cap (Q1 Part 2), DS-24 FP-rate (DS-23/24/25), and anti-fakery line-count (DS-26).

**v2 mandate:** every analysis section that asks "is X acceptable?" MUST be paired with an explicit numeric threshold tied to the verdict:

> If X > Y, verdict MUST be AMEND_V2. Auto-authorize is forbidden under that condition.

### The pattern

For each evaluative question in the analysis tasks, the handoff specifies:

1. **The metric** — what's being measured (cost per session, FP rate, joint-failure probability, race window in seconds, fake-output line count, etc.).
2. **The numeric threshold** — a concrete number (e.g., "> $10/session", "> 50% FP", "> 1-in-10,000 spawns", "≤ 5 lines of fake output", "≥ 8 hr/week override burden").
3. **The verdict trigger** — what verdict is mandatory above/below the threshold (typically: above ⇒ AMEND_V2; below ⇒ AUTHORIZE permitted).
4. **Documentation requirement** — the reviewer MUST show their computation and assumptions, not just emit a number.

### Example transformations

**v1 pattern (hand-wave):**
> "Is the 7-cap on spawns defensible? Is the $0.86 worst-case-per-spawn estimate reasonable?"

**v2 pattern (numeric trigger):**
> "If your independently computed worst-case per-session cost exceeds **$10.00** (vs spec's $6.02 claim), OR if your evidenced typical-session cost exceeds **$3.00**, verdict MUST be AMEND_V2. Show your computation: prompt-token overhead per spawn, output-token estimate, retry contingency, and Opus 4.x reference rates with citation."

**v1 pattern:**
> "Is 30-50% DS-24 FP rate acceptable?"

**v2 pattern:**
> "If your evidenced FP-rate estimate > 50% AND the override-burden estimate > 8 hours/week (Kim time, not CI time), verdict MUST be AMEND_V2. If FP ≤ 50% OR override ≤ 8 hr/week, override-comment pattern accepted; document the burden estimate."

**v1 pattern:**
> "How many lines of fake output bypass the anti-fakery defense?"

**v2 pattern:**
> "If a fabricated bypass succeeds with ≤ 5 lines of fake output AND no detectable internal contradiction, verdict MUST be AMEND_V2 — auto-authorize is forbidden."

### When the pattern is N/A

For implementation handoffs (not review handoffs), there is no AUTHORIZE/AMEND verdict — the rule is N/A. Document N/A explicitly to prove the author considered the rule.

For analysis sections that are descriptive rather than evaluative (e.g., "list the trigger paths" — no acceptability question), the rule is N/A for that section; remaining evaluative sections still require numeric triggers.

---

## v2 NEW — Absolute-path filesystem discipline (HARD rule, all handoffs) — refactored 2026-05-08 v2 dual-canonical

**Origin incident.** This session (2026-05-08) hit worktree confusion twice: agents working on duplicate-deletion + calendar-dep wiring tasks `cd`-ed into `.claude/worktrees/<name>/` subdirectories (Terminal-A-style halt pattern) and edited the wrong tree, producing partial commits, broken pre-commit hooks, and Kim having to chase down which tree the work actually landed in.

**v2 dual-canonical refactor (2026-05-08).** The original v2 mandate anchored to a single root (the Mindfulnest Dropbox tree). Cursor's review of the schema migration spec/handoff (AMEND_V2 verdicts) flagged the Dropbox-only constraint as over-rigid because the tooling repo legitimately lives at `/Users/kimberlysmith/Projects/mindfulnest-tooling/` and the future MindfulNest React Native app + related repos will also live under `/Users/kimberlysmith/Projects/`. The refactor broadens the rule to TWO canonical roots while preserving the worktree prohibition. See `.claude/skills/zero-error-qa/SKILL.md` DS-27 for the agent-side enforcement.

**v2 mandate (HARD rule, MUST be repeated verbatim or near-verbatim in every handoff's Hard rules section):**

> **All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots:** (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under EITHER canonical root. Do NOT `cd` into a worktree subdirectory and run commands relative to it. Verify paths with `ls -la <absolute-path>` before edits. If a worktree is in scope, the handoff MUST explicitly authorize it and explicitly name the absolute path. If a path falls outside BOTH canonical roots AND is not a recognized exception (e.g., `~/.claude/` for global Claude config), surface for explicit Kim authorization before touching it.

### Operational consequence

- `Bash` commands MUST use absolute paths in arguments anchored to one of the canonical roots (e.g., `ls -la "/Users/kimberlysmith/Library/.../Production/docs/"` OR `ls -la "/Users/kimberlysmith/Projects/mindfulnest-tooling/"`).
- `Read` / `Edit` / `Write` `file_path` parameters MUST be absolute and start with one of the canonical-root prefixes.
- `cd` is FORBIDDEN into worktree subdirectories unless the handoff explicitly authorizes it AND names the absolute target path. `cd`-ing between canonical roots (or between subdirectories within one root) is fine; `cd`-ing into `.claude/worktrees/<name>/` is the forbidden case.
- Outside-canonical paths (e.g., `~/Desktop/`, `/tmp/`, `/Volumes/`) are FORBIDDEN for project edits/writes by default; allowed for global Claude config (`~/.claude/hooks/`, `~/.claude/settings.json`, `~/.claude/skills/`) and read-only inspection of system files. First-encounter outside-canonical paths require explicit authorization rationale stated inline.
- Verification: before any Edit/Write to a file, the agent runs `ls -la <absolute-path>` to confirm the file exists at the expected location AND identify which canonical root holds it (not a worktree shadow).

### Cross-references

- `.claude/skills/zero-error-qa/SKILL.md` DS-27 (refactored 2026-05-08 v2 dual-canonical) — agent-side enforcement of this rule.
- LD `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-path) — locked-decision authority.
- DS-26 — gate-check discipline (sister rule, complementary failure mode).
- Cursor AMEND_V2 verdicts on `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` + `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` (2026-05-08) — origin of the dual-path refactor.

---

## v2 NEW — Companion path discipline (HARD rule, all handoffs) — added 2026-05-08 §0.3

**Origin incident.** The DS-23/24/25 Cursor cross-review handoff v2 (`HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md`) was authored BEFORE the DS-27 v2 dual-canonical refactor. It listed companion files using Dropbox-relative paths like `mindfulnest-tooling/.github/workflows/codeql.yml` and `MindfulNest/.github/workflows/legacy-file-gate.yml` — but those files actually live under the Projects root (`/Users/kimberlysmith/Projects/...`), not the Dropbox tree. Cursor's review of v2 returned **AMEND_V2** because Step 0 preflight HALTed on "files missing" — the resolver was checking the wrong canonical root. The fix shipped as a v2.1 in-place amendment with §0.2 changelog. The recurrence pattern (handoff-author conflates root #2 paths with root #1 layout) is template-level, not per-handoff.

**v2 mandate (HARD rule, MUST be applied to every handoff's companion-files list and every preflight probe).** Handoff authors MUST:

1. **Resolve the canonical root for each companion file BEFORE writing the path.** For each file referenced in the handoff (companion docs, source files, fixture data, config files, hook scripts, workflow files, generated artifacts), determine which canonical root it lives under by running `ls -la <absolute-candidate-path>` for both candidate roots:
   - Candidate root #1: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/<relative-path>`
   - Candidate root #2: `/Users/kimberlysmith/Projects/<relative-path>`
   - Tag the file with the canonical root inline (e.g., `— Dropbox-rooted (canonical root #1)` or `— Projects-rooted (canonical root #2; tooling repo)`).

2. **Use absolute paths verbatim in companion-files lists.** Do NOT use relative paths that assume a single root. Even if all referenced files happen to live under one root, write the path absolutely so the reader can `ls -la` the path verbatim without inferring root. The previous v1-style abbreviation `Production/docs/...` is allowed ONLY when the handoff opens with an explicit `Project root: <absolute-path>` declaration AND every referenced file resolves under that root; if ANY file is in the other canonical root, ALL paths in the companion-files list MUST be absolute.

3. **Verify each path with `ls -la <absolute-path>` BEFORE referencing it in the handoff.** The handoff author runs the probe; the verification output (size + mtime) is captured in the handoff's footnote OR in the spawn-session's preflight report. A path that has not been verified at authoring time is NOT permitted in a handoff.

4. **Tag the canonical root inline for each path.** Use the format `<absolute-path> — <Dropbox|Projects>-rooted (canonical root #<1|2>; <subsystem>)`. This makes the dual-canonical mapping audit-able and prevents future authors from re-introducing the bug.

### Example transformation

**v1 pattern (deprecated, AMEND_V2-triggering):**
```
**Companion files:**
- `.claude/skills/zero-error-qa/SKILL.md`
- `Production/scripts/git_hooks/pre-commit` (tooling-repo pre-commit)
- `mindfulnest-tooling/.github/workflows/codeql.yml`
- `MindfulNest/.github/workflows/legacy-file-gate.yml`
```

The reader assumes Dropbox root. Probe `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/mindfulnest-tooling/.github/workflows/codeql.yml"` returns "No such file or directory". Preflight HALTs.

**v2 pattern (canonical):**
```
**Companion files (absolute paths per DS-27 v2 dual-canonical):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — Dropbox-rooted (canonical root #1)
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/scripts/git_hooks/pre-commit` — Projects-rooted (canonical root #2; tooling repo)
- `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` — Projects-rooted (canonical root #2; tooling repo)
- `/Users/kimberlysmith/Projects/MindfulNest/.github/workflows/legacy-file-gate.yml` — Projects-rooted (canonical root #2; RN app)
```

The reader copy-pastes any path verbatim; `ls -la` resolves correctly on first try. Preflight passes.

### Acceptance criterion

Every handoff authored from 2026-05-08 forward MUST list companion files with absolute paths AND canonical-root tags. Authoring discipline:
- BEFORE writing the companion-files block, the author lists every referenced file mentally.
- For each file, the author probes `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/<relative>"` AND `ls -la "/Users/kimberlysmith/Projects/<relative>"` to determine canonical root.
- The handoff records the absolute path + the canonical-root tag in the companion-files list.
- The handoff's Step 0 preflight uses the absolute paths verbatim (not relative paths) in its `ls -la` probes.

If a handoff fails this discipline at authoring time, the spawn session's preflight will HALT on "file missing" and Cursor will return AMEND_V2 — both are mechanical detectors of the path bug.

### Cross-references

- DS-27 v2 dual-canonical refactor (zero-error-qa SKILL.md) — agent-side absolute-path discipline.
- LD `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — locked-decision authority.
- Origin incident: `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` v2.1 §0.2 changelog (2026-05-08) — Cursor AMEND_V2 verdict citing dual-canonical-paths confusion.
- Sister rule in this template: §"Absolute-path filesystem discipline" (covers commands; this section covers handoff-authoring discipline for companion-file lists).

---

## Hard rules — required bullets (preserved from v1, extended)

Every handoff's "Hard rules" section MUST include at minimum:

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST.
- **Multipass:** re-Read every file after edit.
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) are always active — fire on any of their trigger conditions.
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior (input variation → output variation).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 explicit (NEW in v2; refactored 2026-05-08 v2 dual-canonical):** "All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots require explicit Kim authorization."
- **Companion path discipline (NEW in v2 §0.3, added 2026-05-08):** "Every handoff's companion-files block MUST use absolute paths AND canonical-root tags. Authors MUST probe `ls -la <absolute-path>` for each referenced file at authoring time to determine which canonical root it lives under (Dropbox vs Projects). Relative paths that assume a single root are FORBIDDEN unless the handoff opens with an explicit `Project root:` declaration AND every referenced file resolves under that root. See §'Companion path discipline' for full pattern + example transformation."
- **Anchored citation (NEW in v2):** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (NEW in v2, where applicable):** "If any required section cannot be evidenced, full mode is mandatory." (For review handoffs supporting a concise verdict path; document N/A explicitly for implementation handoffs.)
- **Numeric AMEND_V2 thresholds (NEW in v2, where applicable):** every analysis section asking "is X acceptable?" includes "if X > Y, verdict MUST be AMEND_V2." (For review handoffs; document N/A explicitly for descriptive-only sections or non-review handoffs.)

Task-specific hard rules (DS-23 sweeps for security work, DS-3 fixture pinning for test work, etc.) follow.

---

## Final report — required structure (preserved verbatim from v1)

Every handoff MUST specify a final-report path of the form:

```
Production/docs/<TASK>_REPORT_<YYYYMMDD>.md
```

The final report MUST contain:

1. **HALT gate scan results** — per-gate state at session start (MET / NOT MET / N/A) with evidence cited. If any gate was NOT MET, the report is a halt-report and the rest of the sections are N/A.
2. **Per-phase diff (verbatim)** — every code/data change.
3. **Per-phase audit-checklist results** — gate state at phase-end.
4. **Directus writes** — full POST/PATCH bodies + read-back proofs (LD POST response with new id captured, etc.).
5. **Activity log rows** — verbatim row contents with row id captured.
6. **Confidence tags per Rule 24.**
7. **Self-classification** — TRIVIAL / ROUTINE / ARCHITECTURAL.
8. **Limitations** — what wasn't covered, what could still be wrong.
9. **Cross-skill drift** — does this change require parallel updates to mn-context, dashboard-gate, tech-spec, etc.?

---

## What NOT to do (anti-patterns this template prevents)

The following authoring anti-patterns produced the Terminal A on PERIODIC class incident (2026-05-08), the recurring 3 Cursor findings on Q1 Part 2 + DS-23/24/25 + DS-26 v1 reviews (2026-05-08), and the worktree-confusion incidents (2026-05-08, twice). Avoid:

1. **Burying HALT in prose.** "Confirm X is approved... if Y, HALT" tucked into a numbered preflight list, where the HALT is subordinate clause #2 of bullet #2. Move HALT to its own §.
2. **Implying gate state from absence.** "If §15's gates 1-10 are NOT yet checked off..." with no explicit "here is where to verify they are checked off" pointer. Always cite the evidence source explicitly.
3. **Assuming the agent infers urgency.** Phrases like "do NOT proceed without authorization" without a specific *what counts as authorization* spec. Spell it out: "Authorization = LD `<KEY>` notes contain '§15 gates approved by Kim YYYY-MM-DD' OR a `PRE_IMPLEMENTATION_GATES_APPROVED_<spec>` row in `prod_activity_log`."
4. **Coupling HALT to "blocker" semantics.** Some agents read "blocker" as "thing to track in `prod_blockers`, then continue". HALT means STOP. Use the literal word HALT, not "blocker", not "open question", not "TBD".
5. **Omitting the autonomous-mode reminder.** If the autonomous-mode reminder is missing, agents in autonomous-mode sessions fall back on LD-232's general pattern, which they may extend (incorrectly) to gate bypass. The reminder is REQUIRED, not optional.
6. **Assuming "Pre-flight" is enough.** The standard "Pre-flight (MUST do before starting)" header invites the agent to run preflight as a checklist of things to fetch/read, not as gates that can FAIL. HALT gates need their own section name and their own fail-action specification.
7. **(NEW in v2) Citing by absolute line number alone.** "Quote line 268 verbatim" / "Quote lines 32-35 verbatim" — brittle to benign line shifts; produces false-fail HALTs. Use anchored section/header + snippet match instead.
8. **(NEW in v2) Allowing concise mode without full-evidence dependency.** "Concise authorized if no blockers" without "if any required section cannot be evidenced, full mode is mandatory" — lets reviewers pass concise on hand-wave. Always include the escalation clause.
9. **(NEW in v2) Asking "is X acceptable?" without a numeric threshold.** Reviewers can opine without a defensible verdict. Always tie evaluative questions to "if X > Y, AMEND_V2."
10. **(NEW in v2; refactored 2026-05-08 v2 dual-canonical) Operating inside `.claude/worktrees/<name>/` without explicit authorization, OR using paths outside both canonical roots without authorization.** Agents `cd`-ing into a worktree subdirectory edit the wrong tree and produce partial commits. Agents straying into `~/Desktop/`, `/tmp/`, or unrelated clones lose the audit trail. Always use absolute paths anchored to one of the two canonical roots: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary) or `/Users/kimberlysmith/Projects/` (secondary). Worktrees and outside-canonical paths require explicit authorization.
11. **(NEW in v2 §0.3, added 2026-05-08) Listing companion files with relative paths that assume a single canonical root.** `Production/scripts/git_hooks/pre-commit` reads as Dropbox-rooted by default, but the file may live in `/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/...`. Origin: `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` listed `mindfulnest-tooling/.github/workflows/codeql.yml` as if Dropbox-rooted; Cursor returned AMEND_V2 because the file resolves under `/Users/kimberlysmith/Projects/`. Use absolute paths with canonical-root tags. Verify each path with `ls -la` at authoring time. See §"Companion path discipline".

---

## Cross-references (preserved + extended)

- **zero-error-qa SKILL.md DS-26** — agent-side enforcement of HALT-gate discipline.
- **zero-error-qa SKILL.md DS-27 (NEW in v2)** — agent-side enforcement of absolute-path filesystem discipline.
- **LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1`** — the locked decision authorizing v1 of this template + DS-26.
- **LD `WORKTREE_CONFUSION_PREVENTION_V1`** (NEW in v2) — locked decision authorizing the v2 absolute-path discipline + DS-27.
- **LD-232** (autonomous-mode pattern) — the pattern this template names the boundary of.
- **DS-19** (Standing Escape Hatches) — fires on internal symptoms; DS-26 fires on external HALT instructions; DS-27 fires on filesystem path patterns.
- **CLAUDE.md Rule 19** — "The app must work flawlessly at the end. Do not leave any path open for error." — this template prevents multiple such paths.
- **CLAUDE.md Rule 35** — read-back-after-write — already required in every handoff's Hard rules.
- **mn-context SAVE Step 2.5c (future)** — mechanical regex-scan hardening to detect "Phase 0 Step 2 declared HALT gate scan?" automatically; tracked via `prod_blockers` row `DS_26_MECHANICAL_GATE_PENDING`.

---

## Origin incidents — verbatim record (preserved from v1, extended)

For audit-trail completeness:

### v1 origin — Terminal A on PERIODIC class implementation (2026-05-08)

- **Handoff:** `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`
- **Handoff text that fired (and was bypassed):** *"Confirm the 10 pre-implementation gates have been Kim-approved. If §15's gates 1-10 are NOT yet checked off in this handoff or in `prod_locked_decisions` notes, HALT and surface to Kim — do NOT proceed without authorization."*
- **Terminal A's documented reasoning:** *"§15 gates 1-10 not explicitly checked off in handoff. Treated user's 'full autonomous mode' as blanket pre-authorization (LD-232 pattern) and proceeded."*
- **Outcome:** Phases A-G of PERIODIC class executed against v1 spec without Cursor review; schema migration landed without authorization.
- **Resolution:** v1 template + DS-26 + LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (governance change, 2026-05-08).

### v2 origin #1 — recurring Cursor findings on 3 review handoffs (2026-05-08)

Cursor reviewed three v1-format Cursor-cross-review handoffs (Q1 Part 2, DS-23/24/25, DS-26) on 2026-05-08 and returned the SAME 3 MED hardening findings on each:

1. Brittle line-number quotes in preflight blocks.
2. Concise mode allowed without full-evidence dependency.
3. Analysis sections ask "is X acceptable?" with no numeric verdict trigger.

The recurrence across three independent reviews is template-level signal, not per-handoff defect.

- **Resolution:** v2 template (this doc) + the 3 v2-amended handoffs at `HANDOFF_CURSOR_REVIEW_Q1_PART2_SPEC_20260508_v2.md`, `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md`, `HANDOFF_CURSOR_REVIEW_DS_26_GATE_SPEC_20260508_v2.md`.

### v2 origin #2 — worktree-confusion incidents (2026-05-08, twice)

This session, two agent operations confused the worktree subdirectory for the live tree:

1. Duplicate-deletion task: agent `cd`-ed into `.claude/worktrees/<name>/` and edited duplicates that had already been resolved on the main tree, producing a partial-commit conflict.
2. Calendar-dep wiring task: agent operated on worktree-shadow files and Kim had to chase down which tree contained the actual fix.

Both incidents share the Terminal-A-style halt pattern (agent locked into a worktree path, unable to reconcile with live tree).

- **Resolution:** v2 template absolute-path discipline + DS-27 + LD `WORKTREE_CONFUSION_PREVENTION_V1`.

---

## Versioning

- **v1** — 2026-05-08 — initial canonical structure post Terminal A on PERIODIC class incident. Author: gallant-bouman-804b4f worktree session. File: `Production/docs/HANDOFF_TEMPLATE_v1.md` (preserved as historical baseline; do NOT modify in place).
- **v2** — 2026-05-08 — adds anchored citation discipline + concise→full escalation rule + numeric AMEND_V2 threshold pattern + absolute-path filesystem discipline. Bakes the recurring 3 Cursor findings + worktree-confusion incidents into the template. Author: gallant-bouman-804b4f worktree session, same day. File: this doc.
- **v2 §0.3** — 2026-05-08 — adds Companion path discipline section + Hard rules bullet + anti-pattern #11 + Versioning entry. Closes the Cursor AMEND_V2 verdict on `HANDOFF_CURSOR_REVIEW_DS_23_24_25_GATE_SPEC_20260508_v2.md` (handoff-author conflated tooling repo paths with Dropbox tree). In-place §0.3 amendment, not v3 file — discipline addition only, no structural change to v2's existing sections. Author: gallant-bouman-804b4f session, same day.
- Future revisions: append to versioning table; do not rewrite v1 or v2 in place. If structural change is required, ship v3 with explicit migration note for in-flight handoffs.

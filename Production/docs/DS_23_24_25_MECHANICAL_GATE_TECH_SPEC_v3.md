# DS-23 / DS-24 / DS-25 Mechanical Gate Tech Spec v3

**Status:** GOVERNANCE-AUTHORING (re-framed in v3-C from v3-A's "DESIGN-ONLY for production code") — awaiting Kim authorization for downstream Phase A implementation. NO production code implementation in this session; spec-authoring artifacts (LD + activity-log) ARE the deliverables (see §0).
**Author:** Claude (subagent, dual-Opus advocate/counter pattern per `tech-spec` + `zero-error-qa` skills).
**Date:** 2026-05-09 (v3 authored in response to Cursor's round-2 review of v2.)
**Classification:** ARCHITECTURAL (governance + CI/local-hook infrastructure; touches both `Production/scripts/git_hooks/pre-commit` + new `prepare-commit-msg` + tooling-repo GHA workflows).
**Predecessors (preserved verbatim except where v3 explicitly supersedes):**
- v1 baseline: `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` (sha256 not re-hashed in v3 — unchanged from v1's recorded state).
- v2 amendment: `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` (sha256 `a05a5dbf28b3b4514ab7afa6f783d3b1e00d504da8ed7fb3014f244fef101a6e`, 516 lines, captured at v3 author time).
- v2 LD: LD-617 `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V2_WORKFLOW_TRIGGER_AUDIT_FIX_V1`.

**Predecessors / inputs (carried forward from v1 + v2):**
- `.claude/skills/zero-error-qa/SKILL.md` DS-23/24/25 + DS-22 + Phase 7.5 Step 6 + Step 7. [VERIFIED in v1.]
- `.claude/skills/mn-context/SKILL.md` Step 2.5 + 2.5b. [VERIFIED in v1.]
- `Production/scripts/git_hooks/pre-commit` — existing hook. [VERIFIED in v1.]
- `mindfulnest-tooling/.github/workflows/codeql.yml`, `ai_review.yml`, `smoke.yml`. [VERIFIED in v1.]
- `MindfulNest/.github/workflows/legacy-file-gate.yml`. [VERIFIED in v1.]
- LD `DS_23_24_25_DISCIPLINE_STANDARDS_V1` (LD-580). [INFERRED in v1.]
- LD-617 (v2 LD) — locks v2 design choices; v3 inherits all v2 mitigations except where superseded below.

**v3-specific input (NEW):**
- Cursor round-2 review of v2 (2026-05-09) — surfaced 3 HIGH (HIGH-1 design-only / mandated mutation contradiction; HIGH-2 ds23 placeholder; HIGH-3 swept grammar drift) + 3 MEDIUM (M-1 codeql workflow_run filter; M-2 phase-E halt mechanism ambiguity; M-3 details `_contains` jsonb portability) + 1 LOW (PR `commits/<sha>/pulls .[0]` ambiguity under cherry-picks / multi-PR association) findings. v3-A addressed the 6 HIGH/MEDIUM in-line and deferred the LOW; **v3-B (this revision, 2026-05-09) closes the LOW** by adding a multi-PR-detect step at §7.3.1 that exits 1 (with prod_blockers row) when >1 open PR references the head_sha, exits 0 (notice-only) when 0 PRs reference it, and proceeds normally when exactly 1 does. v3 addresses each as enumerated in §0.1.
- `prod_activity_log` schema confirmed at v3 author time via `DirectusAdminClient.fields('prod_activity_log')`: `details` is `json/jsonb` — supports nested key filter `filter[details][<key>][_eq]=<val>`. [VERIFIED at v3 author time.]
- DS-23 SKILL.md grammar inspected at lines 246–274 of `.claude/skills/zero-error-qa/SKILL.md`: canonical commit-message block per v1 SKILL is `Swept <FILE> for \`<PATTERN_REGEX>\`:` with bulleted line-list. v2 §7.1.1/§7.1.2 introduced an implicit grammar swap to `Swept: <files>` / `Verified: <count>`. HIGH-3 is genuine. [VERIFIED at v3 author time.]

---

## §0 Operating Mode Declaration (per zero-error-qa §0)

**Mode (RE-FRAMED v3-C — addresses Cursor round-3 HIGH-2; supersedes v3-A's "DESIGN-ONLY for production code" wording):** GOVERNANCE-AUTHORING. The deliverable of this session class is the spec file + the paired LD row + the paired activity-log row. Specifically:

- **NO production code edits.** Hooks (`Production/scripts/git_hooks/pre-commit`, future `prepare-commit-msg`), CI workflows (`.github/workflows/*` in either repo), shell scripts under `Production/scripts/git_hooks/`, `production_server.py`, and any other implementation surface are NOT touched in this session.
- **NO `.github/workflows/` files modified** in either `MindfulNest/` or `mindfulnest-tooling/`. (READ-ONLY inspection of `mindfulnest-tooling/.github/workflows/codeql.yml` for trigger-set hardening per round-3 MEDIUM is permitted; no writes.)
- **NO git_hook scripts modified or installed.**
- **NO SKILL.md edits.** (The DS-23 SKILL grammar update flagged in HIGH-3 below is a Phase F implementation task; v3 documents the change here as a spec-level decision but does not author it into SKILL.md.)
- **NO settings.json / settings.local.json edits.**
- **NO commits.**
- **NO parallel agents.**

**Spec-authoring artifacts ARE the canonical pattern (re-framed v3-C — supersedes v3-A "carve-out" language):** filing this revision's LD via `Production/scripts/lock_decision.py lock` AND posting an activity-log row to `prod_activity_log` ARE the deliverables of governance-authoring sessions per the project-wide Rule 35 / DS-29 / dashboard-gate discipline. These are NOT production code mutations and are NOT an exception or "carve-out" — they are how a spec session proves it shipped. Treating them as forbidden Directus mutations would force the spec to ship as an orphan doc with no audit trail, which is the opposite of the doctrine. v3-C therefore replaces v3-A's "DESIGN-ONLY + carve-out" framing (which Cursor round-3 HIGH-2 flagged as conflicting with explicit in-session mutation intent) with the cleaner "GOVERNANCE-AUTHORING" classification: production-code surfaces are off-limits; spec-authoring artifacts are the work product. §15-v3, §15-v3-B, and §15-v3-C all describe spec-authoring artifacts under this classification — they are the same thing the §0 banner endorses, not exceptions to it.

- **Tier:** Tier C (architectural; gate infra that BLOCKS commits/PR merges; lands across two surfaces) — preserved from v1 + v2.
- **Scope risk class:** governance-doctrine-shaping + multi-stage + side-effect — preserved.
- **Six-Layer applicability (DS-13):** Layers 3, 4, 6 apply — preserved.
- **Authoring discipline (DS-15):** every v3 amendment cites either Cursor's quoted finding OR a v2/v1 line range OR a v3-author-time-verified fact. No new claims about existing system state without citation.
- **Confidence tags (Rule 24):** `[VERIFIED]` for facts cross-checked at v3 author time (e.g. jsonb schema for `details`, DS-23 SKILL grammar); `[VERIFIED-FROM-V2]` for v2 facts inherited intact; `[INFERRED]` for derivations from Cursor round-2 findings; `[ASSUMED]` for items pending external verification (e.g. mindfulnest-tooling CodeQL workflow trigger config — not in this checkout); `[DESIGN]` for v3's own proposed semantics.

### §0.1 v3 Changelog — Cursor round-2 amendments applied

Cursor's round-2 review of v2 returned 3 HIGH + 3 MEDIUM + 1 LOW. v3-A addressed the 6 HIGH/MEDIUM and deferred the LOW (PR `.[0]` ambiguity); **v3-B (2026-05-09) closes the LOW** with the multi-PR-detect step described in the table row below + §7.3.1 implementation + OD12 + RR11 cross-references. All v2 sections are preserved by reference except where a finding required a targeted insert/replace.

### §0.1-v3-E (2026-05-09) — Cursor round-5 fix-and-consolidate summary (NEW row, ABOVE v3-D — consistent with §0.1 latest-first convention)

| # | Closure | Sections amended | Driver |
|---|---------|-------------------|--------|
| **v3-E (round-5 fix-and-consolidate, 6 findings)** | (1) HIGH-1 DEAD halt code: §7.1.1 v3-A loop populated `HALTED_FILES` from `prod_blockers` query (lines 266-268) but the file-iteration loop at the original lines 291-297 never read it — DS-24 halt-skip semantics were aspirational. v3-E rewrites the loop to actually consult `HALTED_FILES` per staged path; populates a sibling `DS_24_HALTED_FILES` array; emits `DS_24_HALTED_BY_BLOCKER: <file>` notice on stderr per halted file; documents the downstream §7.2 DS-24 sweep contract that must consult `DS_24_HALTED_FILES` before sweeping. (2) HIGH-2 Tier 3 PR-merge gate ABSENT from §7.3.1 YAML: §11.7-v3-C narrative documented the Tier 3 `DS_24_PR_MERGE_BLOCKED_*` PR-merge gate but deferred the YAML step to Phase D as DESIGN-only. v3-E folds the step into §7.3.1 YAML directly as `Check DS-24 PR-merge halt blockers` (id `ds24_halt_check`), positioned AFTER `codeql_scope` check and BEFORE `Require sweep block in PR body`; reads `prod_blockers` for `DS_24_PR_MERGE_BLOCKED_*` rows + writes `DS_24_PR_MERGE_BLOCKED_GATE_FIRED` activity-log row + exits 1 on any active row. §11.7-v3-C narrative updated to reflect concrete v3-E spec (no longer Phase D-deferred DESIGN-only). (3) MEDIUM-1 §12 changelog row order: v3-D was listed BEFORE v3-C (reverse-chronological mid-table), violating chronological ordering. v3-E reorders §12 chronologically (v3-A → v3-B → v3-C → v3-D → v3-E). §0.1 retains latest-first convention separately (§0.1-v3-E above §0.1-v3-D above §0.1-v3-C above §0.1-v3-B). (4) MEDIUM-2 missing §15-v3-D + §15-v3-E LD-filing intent blocks: §15 had §15-v3 / §15-v3-B / §15-v3-C but no §15-v3-D and no §15-v3-E — broken pattern symmetry. v3-E adds both blocks matching the §15-v3-C structure. (5) MEDIUM-3 duplicate G14 label: v3-D introduced "G14 extension (v3-D) — `SECURITY_GLOBS` includes BOTH top-level and nested `functions/src/` patterns" alongside the base G14 — two gates sharing one label. v3-E renames "G14 extension" to G16 (next available gate number after G15-v3-B; G14 stays as base canonical-pattern-config gate). The pre-existing v3-C G16 (CodeQL trigger-set re-read) is renumbered to G17 to free up G16; semantic content preserved. Cross-references throughout the spec updated (§0.1 v3-C row, §7.3.1 inline note, §11.8 RR8, §12 v3-C row, §14.2 LD-633, §15 [VERIFIED-IN-V3-C] line, §16 reviewer expectations). (6) LOW §13 stale enumeration: §13 referenced "AT14–AT19 + AF8–AF9" only — failed to incorporate v3-D's AT20+AF10+AT21+AF11. v3-E updates §13 to "AT14–AT21 + AF8–AF11". CONSOLIDATE-not-overlay discipline: all 6 fixes applied in place; no v3-E-specific RR rows piled atop earlier rounds. CODE-BLOCK-AUDIT discipline: HIGH-1 + HIGH-2 are real implementation bugs in code blocks; pre-edit + post-edit grep inventories verify correctness. | §0.1-v3-E row (THIS) + §7.1.1 hook loop (HALTED_FILES live consultation + DS_24_HALTED_FILES array + stderr notice loop + downstream contract) + §7.3.1 YAML (Tier 3 PR-merge gate step folded in as `ds24_halt_check`) + §11.7-v3-C narrative (Phase D deferral → v3-E concrete spec) + §12 changelog (chronological reorder + v3-E entry appended) + §10-v3 G16 rename (was "G14 extension") + §10-v3 G17 renumber (was G16) + §15-v3-D NEW + §15-v3-E NEW + §13 enumeration AT14-AT21 + AF8-AF11 + cross-reference updates throughout (§0.1 v3-C row, §7.3.1 note, §11.8 RR8, §12 v3-C row, §14.2 LD-633, §15 [VERIFIED-IN-V3-C], §16 reviewer expectations). | Cursor round-5 review of v3-D — 2 HIGH (real bugs: DEAD halt code + missing YAML step) + 3 MEDIUM (consistency: §12 ordering + §15 symmetry + G14 duplicate) + 1 LOW (§13 stale enumeration); FIX-AND-CONSOLIDATE with CODE-BLOCK-AUDIT discipline (no overlay). |

### §0.1-v3-D (2026-05-09) — Cursor round-4 fix-and-consolidate summary (NEW row, ABOVE v3-C)

| # | Closure | Sections amended | Driver |
|---|---------|-------------------|--------|
| **v3-D (round-4 fix-and-consolidate, 4 findings)** | (1) HIGH-1 OD10 contradiction: §9-v3 OD10 was open-ended ("default to no `\b` for v3 launch") while §7.1.1 v3-C had already TIGHTENED the canonical regex to `\b...\b`. v3-D rewrites OD10 IN PLACE to RESOLVED-in-v3-C; Phase G 30-day audit data demoted from "deciding factor" to "confirming data point". (2) HIGH-2 glob coverage: bash `case`-glob `functions/src/**/*.ts` matches ONLY nested files (depth >= 2), silently bypassing top-level `functions/src/index.ts` (canonical Firebase Functions entry). v3-D adds 2-pattern coverage (`*.ts` top-level + `**/*.ts` nested) for both `.ts` and `.js`; matcher behavior verified empirically at v3-D author time. (3) MEDIUM-1 AT20/AF10 dangling: G15 referenced "AT20 + AF10 (when added)" but tests were never authored. v3-D ADDS AT20 + AF10 (multi-PR-detect synthetic matrix) AND AT21 + AF11 (glob coverage positive + negative) to §6.5; G15 wording updated to "now defined". G14 extension added for the glob fix. (4) MEDIUM-2 INFERRED/VERIFIED contradiction: §15 had a stale `[INFERRED]: CodeQL workflow trigger key set` line directly above the `[VERIFIED-IN-V3-C]: codeql.yml on: keys` line — same claim, two confidence tiers. v3-D REMOVES the stale [INFERRED] claim. CONSOLIDATE-not-overlay discipline: OD10 rewritten in place, [INFERRED] stale claim removed in place, no v3-D-specific RR rows piled atop v3-C RR rows. | §0.1-v3-D row (THIS) + §6.5 (AT20/AF10/AT21/AF11 added) + §7.1.1 hook structure (`SECURITY_GLOBS` array — 2-pattern coverage) + §9-v3 OD10 (rewritten — RESOLVED) + §10-v3 G15 (wording updated) + §10-v3 G14 extension (NEW) + §15 [INFERRED] line (stale claim removed). | Cursor round-4 review of v3-C — 2 HIGH (real bugs: OD10 contradiction + glob false-negative) + 2 MEDIUM (wording: AT20/AF10 dangling + INFERRED/VERIFIED dedup); FIX-AND-CONSOLIDATE discipline (no overlay). |

### §0.1-v3-C (2026-05-09) — Cursor round-3 cleanup summary (NEW row, ABOVE v3-B)

| # | Closure | Sections amended | Driver |
|---|---------|-------------------|--------|
| **v3-C (round-3 cleanup, 5 findings)** | (1) HIGH-1 multi-section LOW sweep: §16 line 717 + §15-v3 line for `low_deferred` + §12 v3-A row + §10-v3 G15 narrative all qualified as historical/closed. (2) HIGH-2 §0 banner RE-FRAMED from "DESIGN-ONLY for production code + carve-out" to "GOVERNANCE-AUTHORING" — spec-authoring artifacts ARE the deliverables, not exceptions. RR5 + §0.3 row updated. (3) MEDIUM regex word-boundaries: §7.1.1 default canonical regex REPLACED with explicit `\b...\b` allow-list; AT16 + RR6 + §15 ASSUMED→VERIFIED-IN-V3-C updated; RR12 added. (4) MEDIUM DS-24 escalation: §11.7-v3-C NEW with 3-tier escalation (skip-and-notice → repeated-halt blocker → PR-merge gate); RR9 strengthened; RR13 added. (5) MEDIUM CodeQL trigger hardening: codeql.yml LOCATED + READ at `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`; actual triggers verified (push to main, pull_request to main, schedule Mondays); v3-A `if`-clause confirmed superset; M-1 + RR8 upgraded ASSUMED→VERIFIED-IN-V3-C; G16 (NEW HARD-STOP install-time re-read gate) added. | §0 banner (re-framed) + §0.3 banner row + §6.5 AT16 (regex updated) + §7.1.1 (regex replaced + rationale) + §7.3.1 (M-1 note upgraded) + §10-v3 G16 (NEW) + §11.7-v3-C (NEW) + §11.8 (header + RR5/RR6/RR8/RR9 updated; RR12 + RR13 NEW) + §12 changelog v3-C entry + §14.2-v3 LD-NEW substituted + §15 ASSUMED→VERIFIED-IN-V3-C + §15-v3-C (NEW LD intent) + §16 line 717 (LOW deferral→LOW closure). | Cursor round-3 review of v3-B — 2 HIGH + 3 MEDIUM cleanup pass; STRENGTHENED final-self-review discipline. |

### §0.1-v3-B (2026-05-09) — LOW closure summary (NEW row, above v3-A)

| # | Closure | Sections amended | Driver |
|---|---------|-------------------|--------|
| **v3-B (LOW closure)** | PR `commits/<sha>/pulls .[0]` ambiguity now actively detected. New step in §7.3.1 enumerates open PRs referencing `$HEAD_SHA`; exits 0 (notice) on 0 matches, exits 1 (with `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` blocker row) on >1 matches, proceeds with the single PR on exactly 1 match. Phase G post-30-day audit retained as DEFENSE-IN-DEPTH (no longer the primary mitigation). OD12 + RR11 + §0.1-v3-A LOW row + §7.3.1 inline comments + §10-v3 G15 (NEW v3-B gate) all updated to "CLOSED" with cross-reference here. | §7.3.1 (PR resolution hardened) + §0.1-v3-A LOW row (status flipped) + §9 OD12 (CLOSED) + §10-v3 G15 (NEW gate) + §11.8 RR11 (CLOSED) + §12 changelog v3-B entry + §15-v3-B LD-filing intent. | Cursor round-2 LOW closure — second-pass internal-consistency sweep across 5 spec sections. |


| # | Cursor finding (severity) | v2 lines / behavior cited | v3 section addressing it |
|---|---------------------------|---------------------------|--------------------------|
| **HIGH-1 (round-2)** | DESIGN-ONLY posture conflicts with mandated Directus mutation. v2 §0 says "no Directus PATCHes" but v2 §15-v2 mandates filing an LD via lock_decision.py. Direct contradiction. | v2 §0 line 27; v2 §15-v2 line 503 | §0 (THIS section) — **v3-A response (historical)**: banner narrowed to "DESIGN-ONLY for hooks, CI workflows, scripts, production code. LD filing + activity-log POST permitted (spec-authoring artifacts, not implementation)." Carve-out documented explicitly. **v3-C response (RE-FRAMED)**: Cursor round-3 HIGH-2 flagged residual conflict between "DESIGN-ONLY" and explicit in-session mutation intent. v3-C replaced the carve-out framing with "GOVERNANCE-AUTHORING" classification — spec-authoring artifacts ARE deliverables, not exceptions. See §0 banner + RR5. |
| **HIGH-2 (round-2)** | DS-23 prepare-commit-msg sketch ships with non-normative `<security-fix-pattern>` placeholder. Implementers cannot copy. No deterministic rule tying "security-adjacent commit" to a sweep template. | v2 §7.1.1 lines 172, 178 (literal `<security-fix-pattern>` in grep) | §7.1.1 — **v3-A response (historical)**: placeholder REPLACED by a CANONICAL pattern selector. Pattern source-of-truth = `Production/scripts/ds23_pattern_config.txt` (hook-readable file authored in Phase A). v3-A default canonical regex was `(secret\|credential\|token\|password\|api[_-]?key\|auth(?:_\|-)?(?!or)[a-z]*)` (case-insensitive; unbounded suffix). **v3-C response (TIGHTENED)**: Cursor round-3 MEDIUM flagged unbounded `[a-z]*` overmatching (`authentic`, `authentication`, etc.). v3-C replaced regex with explicit allow-list bounded by `\b` word boundaries. SKILL.md DS-23 section becomes the documented home of the canonical grammar (Phase F task). See §7.1.1 + RR12. |
| **HIGH-3** | DS-23 CI regex no longer aligns with v1 SKILL grammar. v2 §7.1.2 checks `^Swept:` (line 227, 248) and bypass strings. SKILL.md DS-23 (line 261) documents `Swept <FILE> for \`<PATTERN_REGEX>\`:` (no colon-after-Swept; FILE token; pattern in backticks). Implicit contract swap that breaks anyone generating canonical SKILL grammar OR misses CI until SKILL/templates rewritten. | v2 §7.1.2 line 227 + line 248; SKILL.md `.claude/skills/zero-error-qa/SKILL.md` line 261 | §7.1.2 (v3) — chose **option (b) BOTH-grammar acceptance** (decision rationale below). Single normative regex accepts BOTH legacy `^Swept <FILE> for ` AND new `^Swept: ` forms. CI grep + commit-msg hook explicitly enumerate both. **AND** Phase F task added: rewrite DS-23 SKILL.md section to document BOTH forms as accepted, mark `Swept: <files>` as the preferred shorter form for hook-generated commits and `Swept <FILE> for \`pattern\`:` as the preferred form for hand-authored multi-line sweep audits. |
| **MEDIUM-1** | DS-25 workflow_run job gate may filter out legitimate runs. v2 §7.3.1 line 282 requires `github.event.workflow_run.event == 'pull_request'`. CodeQL often runs on push or schedule; under those, the job never fires despite `workflow_run` triggering. Race-mitigating path quietly disabled. | v2 §7.3.1 lines 280–282 | §7.3.1 (v3-A then HARDENED v3-C) — broadened `if` clause accepts `pull_request | push | schedule | workflow_dispatch` workflow_run originating events. **v3-A** could not read `mindfulnest-tooling/.github/workflows/codeql.yml` and treated the broadening as `[ASSUMED]`. **v3-C** located the file at `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml`, read it end-to-end, confirmed actual triggers are `push: branches: [main]` + `pull_request: branches: [main]` + `schedule: cron "0 9 * * 1"`. The v3-A broadened set is a SUPERSET of actual triggers — no event missed. v3-C upgrades the assumption to `[VERIFIED-IN-V3-C]`. G13 retained as soft re-read at install; G17 (formerly G16 in v3-C; RENUMBERED in v3-E to eliminate G16 duplicate label) is the HARD-STOP install-time re-read gate. |
| **MEDIUM-2** | Phase E "halt the DS-24 gate for that file" is ambiguous. Weekly preflight raises blockers/reports; git pre-commit has no standardized "halt per file pending Kim." Without defining where halt state lives, it's aspirational prose. | v2 Phase E line 384 | §8 Phase E (v3 + new §11.7) — halt mechanism PINNED. Source of truth = `prod_blockers` row keyed `DS_24_FP_LOOP_SUSPECTED_<filepath>` (one row per halted file path; `is_resolved=false` while halt active). Pre-commit hook reads `prod_blockers` feed once per commit (cached for the lifetime of the hook process); for each staged path the hook checks for an active blocker; if found, the hook emits `DS_24_HALTED_BY_BLOCKER` notice (stderr) and SKIPS the DS-24 sweep for that file (does not block commit). Refresh latency: hook re-fetches blockers feed at hook start (per-commit, not cached across commits). Resolution path: Kim PATCHes the blocker row to `is_resolved=true` (or runs `Production/scripts/resolve_blocker.py <id>` if available); next commit re-enables DS-24 for that file. |
| **MEDIUM-3** | Directus `filter[details][_contains]=SHA` assumes JSON-string containment semantics. `details` is JSON/object; portability of `_contains` vs nested keys (`details.commit_sha`) isn't nailed down. Fragile audits + false rejects. | v2 §7.1.2 line 233; v2 §7.3.1 line 352 | §7.1.2 + §7.3.1 (v3) — `filter[details][_contains]=$COMMIT_SHA` REPLACED by keyed nested filter `filter[details][commit_sha][_eq]=$COMMIT_SHA`. **Schema verification at v3 author time**: `DirectusAdminClient.fields('prod_activity_log')` returns `details \| json \| jsonb` — Directus's nested-key filter syntax IS supported on jsonb columns. Bypass-row writers (DS-23 hook + DS-25 reviewer authors) MUST include `commit_sha` as a top-level key in the `details` object (not nested deeper). v3 documents the canonical bypass-row shape; Phase A authors the writer helpers. |
| **LOW (CLOSED in v3-B 2026-05-09)** | PR `commits/<sha>/pulls .[0]` ambiguity under cherry-picks / multi-PR association. Single commit may belong to multiple PRs; `.[0]` arbitrarily picks one. | v2 §7.3.1 line 295 | **CLOSED in v3-B.** §7.3.1 (v3-B) replaces `--jq '.[0].number'` with an enumerate-then-branch block: (a) 0 open PRs → exit 0 with `::warning::DS_25_NO_OPEN_PR` notice; (b) >1 open PRs → exit 1 with `::error::DS_25_AMBIGUOUS_PR_CONTEXT` AND write a `prod_blockers` row keyed `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` so Kim can rebase/merge to disambiguate; (c) exactly 1 open PR → proceed normally. Phase G post-30-day audit retained as DEFENSE-IN-DEPTH for residual cherry-pick rare-case drift (e.g. closed-PR cherry-picks). See §7.3.1 + OD12 + §10-v3 G15 + §11.8 RR11. |

**No HALT condition raised by Cursor round-2.** v3 proceeds as a targeted amendment. v2's mitigations carry forward except where superseded above.

### §0.2 Scope (preserved verbatim from v1 §0.1 + v2 §0.2)

In-scope and out-of-scope items unchanged. See v1 §0.1 + v2 §0.2.

### §0.3 What changes in v3 vs v2

| Section | v2 status | v3 status |
|---|---|---|
| §0 Operating Mode banner | "DESIGN-ONLY ... no Directus PATCHes" (line 27) | **REPLACED in v3-A (narrowed banner with carve-out)** then **RE-FRAMED in v3-C** to "GOVERNANCE-AUTHORING" — spec-authoring artifacts (LD + activity-log) are the deliverables, not exceptions |
| §1 Background | Preserved by reference (from v1) | Preserved by reference (from v1) |
| §2 Existing landscape | Preserved by reference (from v1) | Preserved by reference (from v1) |
| §3 Gate locations + check semantics | Preserved by reference (from v1) | **AMENDED in v3** — §3 explicitly notes commit-message grammar now accepts BOTH `Swept <FILE> for ` AND `Swept: ` forms (HIGH-3); SKILL.md update is a Phase F implementation task |
| §4 Dual-Opus debate | Preserved by reference (from v1) | Preserved by reference (from v1) |
| §5 Resolution | Preserved by reference (from v1) | Preserved by reference (from v1) |
| §6 Acceptance criteria | v1 §6.1–§6.3 + v2 §6.4 | **AMENDED in v3** — §6.5 (NEW) adds AT14–AT19 + AF8–AF9 covering the 6 round-2 findings |
| §7.1.1 DS-23 pre-commit | v2 commit-msg-anchored, with `<security-fix-pattern>` placeholder | **REPLACED in v3** — placeholder replaced with canonical regex + config file |
| §7.1.2 DS-23 CI check | v2 with `^Swept:`-only regex + `_contains` filter | **REPLACED in v3** — both-grammar regex + nested-key jsonb filter |
| §7.2 DS-24 | v2 (preserved with §7.2.3 note) | Preserved by reference (from v2) |
| §7.3.1 DS-25 CI workflow | v2 with `workflow_run.event == 'pull_request'` filter | **REPLACED in v3** — broadened `if` clause + nested-key jsonb filter for bypass row |
| §7.3.2 DS-25 no pre-commit | Preserved by reference (from v1) | Preserved by reference (from v1) |
| §8 Implementation phases | v2 amended Phase E | **AMENDED in v3** — Phase A adds canonical pattern config + bypass-row writer helpers; Phase E pins halt mechanism (new §11.7); Phase F adds SKILL.md DS-23 grammar update task; new gate G13 (CodeQL workflow trigger verification) |
| §9 Open Decisions | v1 OD1–OD7 + v2 OD8–OD9 | **AMENDED in v3** — OD10–OD12 added (canonical regex tuning, multi-PR-per-commit deferred case, halt-blocker resolver authority) |
| §10 Pre-implementation gates | v1 G1–G10 + v2 G11–G12 | **AMENDED in v3** — G13 (CodeQL trigger verification) + G14 (canonical pattern config + bypass writer helpers in place before Phase A→B promotion) |
| §11 Risk assessment | v1 §11.1+§11.3–§11.5 + v2 §11.2 + v2 §11.6 | **AMENDED in v3** — §11.7 (NEW v3) explicitly defines halt mechanism (MEDIUM-2); §11.8 (NEW v3) risk rows for the 3 HIGH + 3 MEDIUM round-2 findings |
| §12 Rollback | Preserved | **APPENDED v3 entry** to changelog table |
| §13 Testing plan | Preserved (from v1 + v2 §6.4 add-ons) | Preserved + AT14–AT19 fold into the same synthetic PR matrix |
| §14 Reference index | v1 §14 + v2 §14.1–§14.5 | **AMENDED in v3** — adds v2 baseline path + v3 self-reference + v3-A LD (LD-624) + v3-B LD (LD-627) + v3-C LD (LD-633); §14.2-v3 lists all three IDs explicitly |
| §15 Confidence sweep + LD intent | v2 has `§15-v2 — LD-filing intent` | **AMENDED in v3** — `§15-v3` records v3 LD-filing intent + activity-log row intent |
| §16 Self-classification | Preserved (from v1) | Preserved (from v1) |

All v1 + v2 sections not enumerated above are preserved verbatim by reference. No content silently changed.

---

## §1 Background — preserved verbatim from v1 §1 (via v2)

(See `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v1.md` §1.1, §1.2, §1.3 — unchanged in v2 + v3.)

---

## §2 Existing Landscape — preserved verbatim from v1 §2 (via v2)

(See v1 §2.1 mn-context SAVE-time gates, §2.2 tooling-repo pre-commit, §2.3 existing CI workflows, §2.4 Phase 7.5 Step 6 + Step 7. Unchanged in v2 + v3.)

---

## §3 Proposed Design — preserved verbatim from v1 §3, with v3 amendment to §3.2

(See v1 §3.1 three-rules-three-surfaces table, §3.2 check-semantics summary, §3.3 FP-defense rationale.)

### §3.2-v3 — Amendment to check-semantics: BOTH-grammar acceptance for DS-23 (HIGH-3)

v1 SKILL.md DS-23 section (line 261, file `.claude/skills/zero-error-qa/SKILL.md`) documented the canonical commit-message block as:

```
Swept <FILE> for `<PATTERN_REGEX>`:
  - L (fixed)
  - L'_1 (fixed | marked safe — reason)
  - ...
```

v2 introduced a hook-generated shorter form `Swept: <files>` / `Verified: <count>` (v2 §7.1.1 lines 174–178) and v2's CI check (§7.1.2 line 227) only matched `^Swept:`. This was an implicit grammar contract swap not flagged in v2's text.

**v3 decision (option b — both-grammar acceptance):**

DS-23's commit-message gate accepts EITHER form:
- `^Swept <FILE> for \`<PATTERN_REGEX>\`:` followed by a bulleted line-list (legacy SKILL grammar; preferred for hand-authored multi-line audits where line-by-line disposition matters).
- `^Swept: <FILE_LIST>` plus optional `^Verified: <count>` line (v2 hook-generated shorter form; preferred for routine sweeps where the hook auto-captures all matches).

CI's normative regex matches both: `^Swept(:| .+ for \\\`)`. The DS-23 SKILL.md section MUST be updated in Phase F to document both forms as accepted. Until that update lands, hand-authored sweep blocks following the legacy grammar still pass the v3 CI check; nothing pre-existing breaks.

**Rationale for option (b) over option (a):** option (a) (declare new grammar canonical, retire old) would invalidate every existing SKILL.md example AND any historical commits whose authors followed the SKILL grammar. Option (b) preserves backward compatibility, lets the hook-generated form stand alongside the hand-authored form, and converts a contract swap into a documented union — strictly additive.

---

## §4 Dual-Opus Debate — preserved verbatim from v1 §4 (via v2)

(See v1 §4.1 advocate, §4.2 counter, §4.3 advocate response, §4.4 counter response, §4.5 resolution.)

---

## §5 Resolution + Decision Criteria — preserved verbatim from v1 §5 (via v2)

(See v1 §5.1 decisions resolved, §5.2 decisions deferred.)

---

## §6 Acceptance Criteria

§6.1–§6.3 preserved verbatim from v1; §6.4 preserved verbatim from v2; §6.5 NEW in v3.

### §6.4 — preserved verbatim from v2

(v2 §6.4: AT8 commit-msg sweep block; AT9 workflow_run PR resolution; AT10 no-PR edge; AT11 + AT12 concrete bypass-row check; AT13 24h flap halt; AF7 missing-block CI catch.)

### §6.5 (NEW v3) — round-2 acceptance criteria

| Test case | Expected outcome | Source rule | Cursor round-2 finding addressed |
|---|---|---|---|
| AT14 (v3): Hand-authored commit msg uses legacy grammar `Swept production_server.py for \`(secret|credential|token)\`:` followed by 4 bulleted line-disposition entries | DS-23 CI gate PASSES (legacy grammar still accepted) | DS-23 | HIGH-3 |
| AT15 (v3): Hook-generated commit msg uses new grammar `Swept: production_server.py` + `Verified: 3` | DS-23 CI gate PASSES (new grammar still accepted) | DS-23 | HIGH-3 |
| AT16 (v3-C): Pre-commit hook reads `Production/scripts/ds23_pattern_config.txt`, file declares v3-C pattern `\b(secret\|credential\|token\|password\|api[_-]?key\|auth\|authn\|authz\|authentication\|authorization\|jwt\|bearer\|oauth\|saml\|sso\|session[_-]?(?:id\|key\|token))\b`, hook greps staged set | Hook produces a deterministic, non-placeholder regex match list bounded by word boundaries | DS-23 | HIGH-2 (v3-A) + MEDIUM regex tightening (v3-C) |
| AT17 (v3): CodeQL workflow runs on `push: branches: [main]`; PR-less push triggers `workflow_run`; v3 broadened `if` clause matches `(workflow_run && (event == 'pull_request' \|\| event == 'push' \|\| event == 'schedule' \|\| event == 'workflow_dispatch'))` | DS-25 job fires; `Resolve PR context` step branches; if no PR for SHA, writes `DS_25_NO_PR_CONTEXT` audit row exit 0 | DS-25 | M-1 |
| AT18 (v3): A bypass row written by DS-23 hook to `prod_activity_log` has `details = {"commit_sha":"abc123","reason":"...","actor":"kim"}`; CI queries `filter[details][commit_sha][_eq]=abc123` | Returns 1+ rows; CI gate PASSES | DS-23 + DS-25 | M-3 |
| AT19 (v3): `prod_blockers` has active row `DS_24_FP_LOOP_SUSPECTED_production_server.py` (`is_resolved=false`); pre-commit fires on a commit touching `production_server.py` | DS-24 sweep is SKIPPED for that file with `DS_24_HALTED_BY_BLOCKER` notice on stderr; commit proceeds | DS-24 | M-2 |
| AF8 (v3): Bypass row written WITHOUT `commit_sha` key in `details` (legacy `_contains` shape); CI queries v3 nested-key filter | Returns 0 rows; CI gate FAILS with explicit "bypass row malformed (missing commit_sha key)" error — author rewrites bypass row with canonical shape | DS-23 + DS-25 | M-3 |
| AF9 (v3): CodeQL workflow trigger config later changes (e.g. drops `pull_request`, adds `workflow_dispatch` only); v3's `if` clause is checked against new config in next preflight | Phase E preflight emits `DS_25_TRIGGER_DRIFT_DETECTED` blocker if observed CodeQL run-event mode lies outside the v3 broadened `if` | DS-25 | M-1 |
| AT20 (v3-D): Synthetic PR matrix for §7.3.1 multi-PR-detect step. Three sub-cases: (a) commit SHA referenced by 0 open PRs → `PR_COUNT == 0` branch fires, exits 0, writes `DS_25_NO_OPEN_PR` activity-log row (notice-only); (b) commit SHA referenced by exactly 1 open PR → `PR_COUNT == 1` branch fires, proceeds with `PR_LIST \| jq -r '.[0]'`, gate runs to completion; (c) commit SHA referenced by >1 open PRs (cherry-pick fan-out) → `PR_COUNT > 1` branch fires, exits 1, writes `prod_blockers` row `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` AND emits `DS_25_AMBIGUOUS_PR_CONTEXT` activity-log row | All three branches behave per §7.3.1 v3-B implementation; G15 verification gate confirms wiring before workflow merge | DS-25 | LOW (CLOSED in v3-B) |
| AF10 (v3-D): Synthetic PR matrix counter-cases — multi-PR-detect step misconfigured (e.g. `select(.state == "open")` filter omitted; defaults to `.[0]` arbitrary selection on >1-PR case without writing blocker row) | G15 verification gate FAILS pre-merge; CI surfaces missing-`prod_blockers`-write OR missing-state-filter; PR cannot merge until §7.3.1 v3-B implementation matches G15 checklist exactly | DS-25 | LOW (CLOSED in v3-B) |
| AT21 (v3-D): Pre-commit hook on staged set including `functions/src/index.ts` (Firebase Functions top-level entry file) containing the canonical pattern (e.g. `const SESSION_TOKEN = ...`) | DS-23 sweep DETECTS the file, appends `Swept: functions/src/index.ts` block to commit message; commit proceeds with audit evidence | DS-23 | v3-D HIGH-2 (glob coverage fix) |
| AF11 (v3-D): Pre-commit hook on staged set including `functions/src/index.ts` with canonical pattern, but `SECURITY_GLOBS` MISSING the v3-D `functions/src/*.ts` top-level pattern (legacy v3-A globs only) | DS-23 sweep MISSES the file (bash `**/*.ts` does not match top-level files); commit proceeds with NO sweep evidence — silent false-negative on canonical Firebase Functions entry path. G14 pre-implementation gate (extended in v3-D) MUST verify both top-level and nested patterns are present in `SECURITY_GLOBS` array before Phase A→B promotion | DS-23 | v3-D HIGH-2 (glob coverage fix) |

---

## §7 Per-Rule Check Semantics

### §7.1 DS-23 — Post-fix pattern sweep

#### §7.1.1 Pre-commit check (REPLACED in v3 — canonical pattern selector, no placeholder)

**v2 had:** commit-message-anchored evidence (correct doctrine, preserved) BUT a literal `<security-fix-pattern>` placeholder inside the grep snippet (v2 §7.1.1 lines 172, 178). Implementer cannot copy and run.

**v3 fix:** the pattern lives in a hook-readable config file `Production/scripts/ds23_pattern_config.txt`. The hook reads it; the regex is deterministic and copyable. Default canonical regex documented inline below; SKILL.md DS-23 section becomes the authoritative home of the canonical grammar (Phase F update).

**Canonical default pattern (lives in `ds23_pattern_config.txt` after Phase A creates it; v3-C TIGHTENED — addresses Cursor round-3 MEDIUM regex overmatch):**

```
# DS-23 canonical pattern config — controls which staged file edits trigger the post-fix sweep.
# Edit this file to broaden / narrow which identifier-fragments count as security-adjacent.
# Hook applies pattern via `grep -iE`. Comments (lines starting with `#`) are ignored.
# v3-C: explicit allow-list bounded by \b word boundaries; trade-off documented in §11.8 RR12.
\b(secret|credential|token|password|api[_-]?key|auth|authn|authz|authentication|authorization|jwt|bearer|oauth|saml|sso|session[_-]?(?:id|key|token))\b
```

**v3-C rationale (supersedes v3-A unbounded `auth(?:_|-)?(?!or)[a-z]*` form):** Cursor round-3 MEDIUM flagged the v3-A pattern as overmatching. The `(?!or)` negative lookahead correctly excludes `author`/`authority` but `[a-z]*` is greedy and unbounded — `authentic`, `authentication`, `authorization` all matched as a side effect (some intentionally, but unprincipled). The v3-C pattern replaces the unbounded suffix with an explicit allow-list of security-adjacent vocabulary, anchored by `\b` word boundaries on both ends. Trade-off: slightly less catchy regex; new vocabulary requires editing the config file (treat as a feature — additions go through PR review). Documented as RR12 in §11.8.

This pattern matches (each enclosed by word boundaries):
- `secret`, `secrets`
- `credential`, `credentials`
- `token`, `tokens`
- `password`, `passwords`
- `api_key`, `api-key`, `apikey`
- `auth`, `authn`, `authz`, `authentication`, `authorization`
- `jwt`, `bearer`, `oauth`, `saml`, `sso`
- `session_id`, `session-id`, `sessionid`, `session_key`, `session-key`, `sessionkey`, `session_token`, `session-token`, `sessiontoken`

This pattern explicitly does NOT match (because `\b` and explicit allow-list, not `[a-z]*`):
- `author`, `authority` (no longer match because `auth` is a separate alternation; `\b...auth\b` requires `auth` standalone or at a word boundary)
- `secretkey` (concatenated; would have matched in v3-A unbounded form)
- `bearertoken` (concatenated; matches `bearer` and `token` separately if hyphen/underscore present)
- arbitrary `auth*` derivations (e.g. `authentic` is not in allow-list — but `authentication` is)

**v3 hook structure** (illustrative — implementation in Phase A; this is the design):

```bash
# ============================================================================
# DS-23: Post-fix pattern sweep gate (v3 — canonical pattern config + commit-msg-anchored evidence)
# Hook surface: prepare-commit-msg (passes commit message file path as $1)
# ============================================================================

PATTERN_CFG="${REPO_ROOT}/Production/scripts/ds23_pattern_config.txt"
if [[ ! -f "$PATTERN_CFG" ]]; then
    echo "FATAL DS-23: pattern config $PATTERN_CFG missing — Phase A pre-implementation gate G14 not satisfied."
    exit 1
fi
# Strip comments, take first non-empty line as the pattern
DS23_PATTERN=$(grep -vE '^\s*(#|$)' "$PATTERN_CFG" | head -n1)
if [[ -z "$DS23_PATTERN" ]]; then
    echo "FATAL DS-23: pattern config exists but contains no non-comment line."
    exit 1
fi

# Override
if [[ "${MN_SKIP_DS23_GATE:-}" = "1" ]]; then
    echo "PRE-COMMIT: MN_SKIP_DS23_GATE=1 — DS-23 gate bypassed (CI will validate audit row)."
    echo "" >> "$1"
    echo "DS-23 sweep waived (MN_SKIP_DS23_GATE=1; see DS_23_GATE_BYPASSED audit row)" >> "$1"
    exit 0
fi

# Halt-on-FP-loop check (M-2): consult prod_blockers for DS_24_FP_LOOP_SUSPECTED_<file>.
# Note: this halt list applies to DS-24, not DS-23, but the hook process owns ONE blockers
# fetch per commit; both rules consult the same list. See §11.7 for halt mechanism.
HALTED_FILES=$(curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" \
    "$DIRECTUS_URL/items/prod_blockers?filter[blocker_type][_starts_with]=DS_24_FP_LOOP_SUSPECTED_&filter[is_resolved][_eq]=false&fields=blocker_type" \
    | jq -r '.data[].blocker_type' 2>/dev/null || echo "")

# Identify security-adjacent paths in the staged set
SECURITY_GLOBS=(
    'production_server.py'
    'Production/lib/*.py'
    'firestore/rules/*'
    'functions/src/*.ts'        # v3-D: top-level files directly under functions/src/ (Cursor round-4 HIGH-2 fix)
    'functions/src/**/*.ts'     # v3-A: nested files under functions/src/<subdir>/
    'functions/src/*.js'        # v3-D: top-level files directly under functions/src/
    'functions/src/**/*.js'     # v3-A: nested files
)
# v3-D rationale: bash `case "$staged" in functions/src/**/*.ts)` matches ONLY files
# at depth >= 2 under functions/src/ (e.g. functions/src/nested/foo.ts), NOT top-level
# files like functions/src/index.ts. Verified at v3-D author time: bash glob match for
# `functions/src/**/*.ts` against `functions/src/index.ts` returns NO MATCH; against
# `functions/src/nested/foo.ts` returns MATCH. Without the `*.ts` / `*.js` companion
# patterns, top-level entry-point files (functions/src/index.ts is the canonical
# Firebase Functions entry) silently bypass DS-23 sweep enforcement — a HIGH-severity
# false-negative. v3-D adds the 2-pattern combo (top-level + nested) for full coverage.
SECURITY_FILES=()
DS_24_HALTED_FILES=()  # files we will report as DS_24_HALTED_BY_BLOCKER (visible degradation; v3-E HIGH-1 fix)
while IFS= read -r staged; do
    for pattern in "${SECURITY_GLOBS[@]}"; do
        case "$staged" in
            $pattern)
                # v3-E HIGH-1 FIX (Cursor round-5): actually consult HALTED_FILES populated above.
                # Prior v3-A loop populated HALTED_FILES from prod_blockers but never read it — DEAD halt code.
                # Per §11.7 + §11.7-v3-C, DS-24 halt is per-file: skip DS-24 sweep, but DS-23 sweep continues
                # (DS-23 halt is separate per §11.7-v3-C; DS-23 has no halt-blocker class in v3 scope).
                halt_key="DS_24_FP_LOOP_SUSPECTED_${staged}"
                if echo "$HALTED_FILES" | grep -qFx "$halt_key"; then
                    DS_24_HALTED_FILES+=("$staged")
                    # File is halted from DS-24 sweep but STILL added to SECURITY_FILES so DS-23 sweep runs.
                    # The DS-24 sweep code (governed in §7.2 — preserved from v1+v2) MUST consult
                    # DS_24_HALTED_FILES before sweeping each file; this is the v3-E enforcement contract.
                    SECURITY_FILES+=("$staged")
                else
                    SECURITY_FILES+=("$staged")
                fi
                break
                ;;
        esac
    done
done < <(git diff --cached --name-only)

# v3-E HIGH-1: emit DS_24_HALTED_BY_BLOCKER notice for each halted file (visible degradation per §11.7).
# This is the user-visible side of the halt: stderr notice + activity-log row (writer responsibility per §11.7 step 6).
for halted in "${DS_24_HALTED_FILES[@]}"; do
    echo "DS_24_HALTED_BY_BLOCKER: $halted skipped from DS-24 sweep per active prod_blockers row" >&2
done

# v3-E DOWNSTREAM CONTRACT: the DS-24 sweep (governed in §7.2 — preserved from v1+v2) MUST check
# DS_24_HALTED_FILES before sweeping each file. If $staged is in DS_24_HALTED_FILES, DS-24 sweep is
# SKIPPED (commit not blocked). This contract closes the v3-A "DEAD halt code" bug surfaced by Cursor
# round-5 HIGH-1: prior code populated HALTED_FILES but never consulted it in the loop.

if [[ ${#SECURITY_FILES[@]} -gt 0 ]]; then
    SWEPT_FILES=$(printf '%s\n' "${SECURITY_FILES[@]}" | xargs grep -liE "$DS23_PATTERN" 2>/dev/null || true)
    if [[ -n "$SWEPT_FILES" ]]; then
        # New short-form grammar (v2-introduced, v3-retained):
        echo "" >> "$1"
        echo "Swept: $(echo "$SWEPT_FILES" | tr '\n' ' ')" >> "$1"
        # Optional verified-count line for the canonical short form
        VERIFIED_COUNT=$(printf '%s\n' "${SECURITY_FILES[@]}" | xargs grep -cE "$DS23_PATTERN" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
        echo "Verified: $VERIFIED_COUNT" >> "$1"
        echo "Pre-commit DS-23 gate: sweep evidence appended to commit message (short form)."
    else
        # Security file modified but no pattern hit; still REQUIRE explicit annotation.
        # CI accepts BOTH legacy and short forms via the union regex (HIGH-3 v3 §7.1.2).
        if ! grep -qE '^Swept(:| .+ for `)' "$1"; then
            echo "FATAL DS-23: security-adjacent file modified, no Swept block in commit message."
            echo "  Either accept the canonical short form via the hook's auto-append,"
            echo "  OR hand-author the legacy form (\`Swept <FILE> for \\\`pattern\\\`:\`),"
            echo "  OR set MN_SKIP_DS23_GATE=1 + write DS_23_GATE_BYPASSED audit row with details.commit_sha=<sha>."
            exit 1
        fi
    fi
fi
exit 0
```

**Why this closes HIGH-2:** the placeholder is gone. The pattern source-of-truth is a single editable file (`Production/scripts/ds23_pattern_config.txt`); the hook reads it deterministically; the default regex matches the standard security-adjacent identifier-fragment vocabulary. Implementers can copy-paste the snippet and run it.

**Why this is M-2 compliant:** the hook also consults `prod_blockers` once per process invocation for active `DS_24_FP_LOOP_SUSPECTED_*` rows; the DS-24 sweep (governed in §7.2 — preserved from v1+v2) reads this list. See §11.7 for the full halt mechanism.

#### §7.1.2 CI check (REPLACED in v3 — both-grammar regex + nested-key jsonb filter)

**v2 had:** `^Swept:`-only regex (HIGH-3); `filter[details][_contains]=$COMMIT_SHA` (M-3).

**v3 fix:** union regex matches BOTH `Swept <FILE> for \`pattern\`:` AND `Swept: <files>` forms; bypass row query uses `filter[details][commit_sha][_eq]=$COMMIT_SHA` against the verified jsonb column.

```yaml
ds_23_check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
      with: { fetch-depth: 0 }
    - name: Identify security-adjacent commits in PR range
      id: scan
      env:
        DIRECTUS_URL: ${{ secrets.DIRECTUS_URL }}
        DIRECTUS_TOKEN: ${{ secrets.DIRECTUS_TOKEN }}
      run: |
        BASE="${{ github.event.pull_request.base.sha }}"
        HEAD="${{ github.event.pull_request.head.sha }}"
        SECURITY_GLOBS='production_server.py|Production/lib/.*\.py$|firestore/rules/|functions/src/.*\.(ts|js)$'
        # v3 HIGH-3: union regex accepts BOTH legacy `Swept <FILE> for ` AND new `Swept: ` forms.
        SWEPT_REGEX='^Swept(:| .+ for `)'
        FAIL=0
        for COMMIT_SHA in $(git rev-list "$BASE..$HEAD"); do
          if git show --name-only --format= "$COMMIT_SHA" | grep -qE "$SECURITY_GLOBS"; then
            BODY=$(git log -1 --format=%B "$COMMIT_SHA")
            if echo "$BODY" | grep -qE "$SWEPT_REGEX"; then
              echo "  $COMMIT_SHA: DS-23 sweep block present (matches union grammar)"
            elif echo "$BODY" | grep -qE 'DS_23_GATE_BYPASSED|DS-23 sweep waived'; then
              # v3 M-3: nested-key jsonb filter, NOT _contains string match.
              # `details` confirmed jsonb at v3 author time via DirectusAdminClient.fields('prod_activity_log').
              AUDIT_ROW=$(curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" \
                "$DIRECTUS_URL/items/prod_activity_log?filter[action][_eq]=DS_23_GATE_BYPASSED&filter[details][commit_sha][_eq]=$COMMIT_SHA" \
                | jq '.data | length')
              if [[ "$AUDIT_ROW" -lt 1 ]]; then
                  echo "::error::DS-23 BYPASS rejected: no audit row with details.commit_sha == $COMMIT_SHA"
                  echo "::error::Bypass row writers MUST include commit_sha as a top-level key in details (v3 canonical shape)."
                  FAIL=1
              else
                  echo "  $COMMIT_SHA: DS-23 sweep waived; audit row verified ($AUDIT_ROW match on details.commit_sha)"
              fi
            else
              echo "::error::$COMMIT_SHA: DS-23 BLOCK MISSING in commit message (neither short form nor legacy form found)"
              FAIL=1
            fi
          fi
        done
        echo "fail=$FAIL" >> "$GITHUB_OUTPUT"
    - name: Fail if any commit lacks sweep block
      if: steps.scan.outputs.fail == '1'
      run: exit 1
```

**Canonical bypass-row shape (writers MUST conform):**

```json
{
  "action": "DS_23_GATE_BYPASSED",
  "details": {
    "commit_sha": "<full-40-char-sha>",
    "reason": "<>=50-char rationale>",
    "actor": "<github-handle-or-kim>",
    "rule": "DS-23"
  },
  "performed_by": "<github-handle-or-kim>"
}
```

The Phase A bypass-writer helper (`Production/scripts/write_ds_gate_bypass.py`, NEW in v3 Phase A scope) MUST emit this shape; ad-hoc writers MUST follow it. AF8 (§6.5) catches malformed bypass rows.

**Why this closes HIGH-3 + M-3 (DS-23 half):**
- HIGH-3: union regex accepts both forms; nothing pre-existing breaks; SKILL.md update folded into Phase F task list.
- M-3: nested-key jsonb filter is the documented Directus path-filter syntax for jsonb columns; `_contains` string-match guesswork is gone; canonical bypass shape documented for writers.

### §7.2 DS-24 — preserved verbatim from v2 §7.2

(§7.2.1 + §7.2.2 + §7.2.3 unchanged from v2. §7.2.3 v2 amendment about DS-24 24h flap threshold and week-1 override-rate report carries forward; M-2's halt mechanism PIN is in §11.7 below — Phase E references §11.7 instead of inline prose.)

### §7.3 DS-25 — Adjacent risk sweep after CodeQL triage

#### §7.3.1 CI check (REPLACED in v3 — broadened workflow_run if-clause + nested-key jsonb filter)

**v2 had:** `if` clause requiring `github.event.workflow_run.event == 'pull_request'` (M-1); `filter[details][_contains]=$HEAD_SHA` (M-3).

**v3 fix:** `if` clause broadened to `pull_request | push | schedule | workflow_dispatch` for `workflow_run` mode; bypass-row query uses nested-key jsonb filter; pre-implementation gate G13 verifies CodeQL workflow trigger config aligns at install time.

```yaml
name: DS-25 Adjacent Risk Sweep Gate

on:
  workflow_run:
    workflows: [CodeQL]
    types: [completed]
  pull_request:
    types: [opened, synchronize, reopened, edited]

jobs:
  ds_25_check:
    if: >-
      (github.event_name == 'pull_request' && github.event.pull_request.base.ref == 'main') ||
      (github.event_name == 'workflow_run' &&
       (github.event.workflow_run.event == 'pull_request' ||
        github.event.workflow_run.event == 'push' ||
        github.event.workflow_run.event == 'schedule' ||
        github.event.workflow_run.event == 'workflow_dispatch'))
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Resolve PR context
        id: pr
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          if [[ "$GITHUB_EVENT_NAME" == "workflow_run" ]]; then
            HEAD_SHA="${{ github.event.workflow_run.head_sha }}"
            # v3-B (LOW CLOSED 2026-05-09): enumerate open PRs referencing $HEAD_SHA before
            # resolving PR_NUMBER. Three branches:
            #   (a) 0 open PRs   → notice-only skip (DS_25_NO_PR_CONTEXT activity-log row).
            #   (b) >1 open PRs  → hard-fail + write prod_blockers row DS_25_AMBIGUOUS_PR_CONTEXT_<sha>.
            #   (c) exactly 1 PR → proceed with that PR.
            # Closed-PR cherry-picks are handled as defense-in-depth by Phase G 30-day audit
            # (see §11.8 RR11 + OD12 + §10-v3 G15). Multi-PR ambiguity is no longer arbitrary .[0] selection.
            PR_LIST=$(gh api "/repos/${{ github.repository }}/commits/$HEAD_SHA/pulls" \
              --jq 'map(select(.state == "open")) | map(.number)')
            PR_COUNT=$(echo "$PR_LIST" | jq 'length')
            if [[ "$PR_COUNT" -eq 0 ]]; then
              echo "::warning::DS_25_NO_OPEN_PR: head_sha $HEAD_SHA has no associated open PR; skipping gate."
              # v3 M-3 + v3-B: nested-key jsonb shape for the audit row write; trigger_event preserved.
              curl -s -X POST -H "Authorization: Bearer ${{ secrets.DIRECTUS_TOKEN }}" \
                -H "Content-Type: application/json" \
                "${{ secrets.DIRECTUS_URL }}/items/prod_activity_log" \
                -d "{\"action\":\"DS_25_NO_PR_CONTEXT\",\"details\":{\"commit_sha\":\"$HEAD_SHA\",\"reason\":\"workflow_run with no open PR\",\"trigger_event\":\"${{ github.event.workflow_run.event }}\"}}"
              echo "skip=1" >> "$GITHUB_OUTPUT"
              exit 0
            elif [[ "$PR_COUNT" -gt 1 ]]; then
              echo "::error::DS_25_AMBIGUOUS_PR_CONTEXT: $PR_COUNT open PRs reference $HEAD_SHA: $PR_LIST. Operator must rebase/merge to disambiguate before gate runs."
              # v3-B: write prod_blockers row so Kim sees the ambiguity in dashboard.
              curl -s -X POST -H "Authorization: Bearer ${{ secrets.DIRECTUS_TOKEN }}" \
                -H "Content-Type: application/json" \
                "${{ secrets.DIRECTUS_URL }}/items/prod_blockers" \
                -d "{\"blocker_type\":\"DS_25_AMBIGUOUS_PR_CONTEXT_$HEAD_SHA\",\"is_resolved\":false,\"details\":{\"commit_sha\":\"$HEAD_SHA\",\"open_pr_numbers\":$PR_LIST,\"open_pr_count\":$PR_COUNT,\"reason\":\"multi-PR ambiguity surfaced by DS-25 PR resolution step\"}}"
              # And an audit-log echo so Phase G can correlate.
              curl -s -X POST -H "Authorization: Bearer ${{ secrets.DIRECTUS_TOKEN }}" \
                -H "Content-Type: application/json" \
                "${{ secrets.DIRECTUS_URL }}/items/prod_activity_log" \
                -d "{\"action\":\"DS_25_AMBIGUOUS_PR_CONTEXT\",\"details\":{\"commit_sha\":\"$HEAD_SHA\",\"open_pr_numbers\":$PR_LIST,\"open_pr_count\":$PR_COUNT,\"trigger_event\":\"${{ github.event.workflow_run.event }}\"}}"
              exit 1
            fi
            PR_NUMBER=$(echo "$PR_LIST" | jq -r '.[0]')
            echo "pr_number=$PR_NUMBER" >> "$GITHUB_OUTPUT"
          else
            echo "pr_number=${{ github.event.pull_request.number }}" >> "$GITHUB_OUTPUT"
          fi
          echo "skip=0" >> "$GITHUB_OUTPUT"

      - name: Check if this PR touches CodeQL-flagged files
        id: codeql_scope
        if: steps.pr.outputs.skip != '1'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_NUMBER="${{ steps.pr.outputs.pr_number }}"
          FILES=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path')
          ALERTS=$(gh api -H "Accept: application/vnd.github+json" \
              "/repos/${{ github.repository }}/code-scanning/alerts?state=open" \
              --jq '.[] | select(.most_recent_instance.location.path) | .most_recent_instance.location.path' 2>/dev/null || echo "")
          TOUCHED=0
          for file in $FILES; do
              if echo "$ALERTS" | grep -qF "$file"; then
                  TOUCHED=1; break
              fi
          done
          echo "touched=$TOUCHED" >> "$GITHUB_OUTPUT"

      - name: Check DS-24 PR-merge halt blockers
        id: ds24_halt_check
        if: steps.pr.outputs.skip != '1'
        env:
          DIRECTUS_TOKEN: ${{ secrets.DIRECTUS_TOKEN }}
          DIRECTUS_URL: ${{ secrets.DIRECTUS_URL }}
        run: |
          # v3-E HIGH-2 FIX (Cursor round-5): Tier 3 DS_24_PR_MERGE_BLOCKED_* gate.
          # §11.7-v3-C documented this gate as Phase D scope; v3-E folds it into §7.3.1 YAML directly.
          # Reads prod_blockers for DS_24_PR_MERGE_BLOCKED_<file> rows (is_resolved=false); if any active
          # row exists, gate hard-fails the PR. Resolution: Kim PATCHes the underlying
          # DS_24_FP_LOOP_SUSPECTED_<F> row to is_resolved=true (Tier 3 row auto-resolves on next preflight).
          HALT_BLOCKERS=$(curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" \
            "$DIRECTUS_URL/items/prod_blockers?filter[blocker_type][_starts_with]=DS_24_PR_MERGE_BLOCKED_&filter[is_resolved][_eq]=false&fields=blocker_type,details" \
            | jq -r '.data[] | "\(.blocker_type) — \(.details // {} | tojson)"')
          if [ -n "$HALT_BLOCKERS" ]; then
            echo "::error::DS-24 PR-MERGE BLOCKED — active prod_blockers rows prevent merge:"
            echo "$HALT_BLOCKERS"
            # Audit-log echo so the block is observable in prod_activity_log.
            curl -s -X POST -H "Authorization: Bearer $DIRECTUS_TOKEN" \
              -H "Content-Type: application/json" \
              "$DIRECTUS_URL/items/prod_activity_log" \
              -d "{\"action\":\"DS_24_PR_MERGE_BLOCKED_GATE_FIRED\",\"details\":{\"pr_number\":\"${{ steps.pr.outputs.pr_number }}\",\"blockers\":\"$HALT_BLOCKERS\"}}"
            exit 1
          fi
          echo "DS-24 PR-merge halt check: no active blockers; proceeding."

      - name: Require sweep block in PR body
        if: steps.codeql_scope.outputs.touched == '1'
        env:
          DIRECTUS_URL: ${{ secrets.DIRECTUS_URL }}
          DIRECTUS_TOKEN: ${{ secrets.DIRECTUS_TOKEN }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_NUMBER="${{ steps.pr.outputs.pr_number }}"
          BODY=$(gh pr view "$PR_NUMBER" --json body --jq '.body')
          HEAD_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid')
          if echo "$BODY" | grep -qE 'Adjacent risk sweep on .+ after CodeQL triage'; then
              BLOCK=$(echo "$BODY" | sed -n '/Adjacent risk sweep on /,/Result:/p')
              if [[ ${#BLOCK} -lt 100 ]]; then
                  echo "::error::DS-25 sweep block present but <100 chars (placeholder rejected)"
                  exit 1
              fi
              echo "DS-25 gate: sweep block found, length OK"
          elif echo "$BODY" | grep -qE 'ADJACENT_RISK_SWEEP_WAIVED|DS_25_GATE_BYPASSED'; then
              # v3 M-3: nested-key jsonb filter (replaces v2 _contains).
              AUDIT_ROW=$(curl -s -H "Authorization: Bearer $DIRECTUS_TOKEN" \
                "$DIRECTUS_URL/items/prod_activity_log?filter[action][_eq]=DS_25_GATE_BYPASSED&filter[details][commit_sha][_eq]=$HEAD_SHA" \
                | jq '.data | length')
              if [[ "$AUDIT_ROW" -lt 1 ]]; then
                  echo "::error::DS-25 BYPASS rejected: no audit row with details.commit_sha == $HEAD_SHA"
                  exit 1
              fi
              echo "DS-25 gate: waiver row referenced; audit row verified (nested-key match)"
          else
              echo "::error::PR touches CodeQL-flagged file(s) but PR body lacks DS-25 adjacent risk sweep block"
              exit 1
          fi
```

**Note (v3-C — UPGRADED from v3-A "[ASSUMED]" to "[VERIFIED-IN-V3-C]"):** At v3-A author time the CodeQL workflow was inaccessible and the broadened `if`-clause was treated as an assumption. At v3-C author time the workflow file was located at `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` and read end-to-end. Actual CodeQL `on:` keys: `push: branches: [main]`, `pull_request: branches: [main]`, `schedule: cron "0 9 * * 1"` (Mondays 09:00 UTC). NO `workflow_dispatch`, NO `repository_dispatch`. The v3-A broadened `if`-clause (`pull_request | push | schedule | workflow_dispatch`) is therefore a SUPERSET of the actual triggers — every real CodeQL run satisfies the `if`-clause; `workflow_dispatch` is listed defensively for the case where a future operator adds manual-dispatch (zero false-negatives, harmless false-positive cost in unused branch). Phase A is no longer required to extend the `if`-clause; Phase A IS still required to re-read codeql.yml at install time per the v3-C-hardened G17 below (formerly G16 in v3-C; RENUMBERED in v3-E to eliminate G16 duplicate label) (in case of drift between v3-C author time and Phase A install time). Phase E preflight `DS_25_TRIGGER_DRIFT_DETECTED` retained for ongoing drift detection (see §6.5 AF9).

**Why this closes M-1 + M-3 (DS-25 half):**
- M-1: broadened `if` accepts 4 originating events; G13 forces verification at install; AF9 catches drift later.
- M-3: nested-key jsonb filter replaces `_contains`; canonical bypass-row shape documented (matches DS-23 §7.1.2 above).

#### §7.3.2 No pre-commit equivalent — preserved verbatim from v1.

---

## §8 Implementation Phases

Phases A–D + F–G preserved by reference from v1 except Phase A and Phase F amendments below; Phase E preserved by reference from v2 except for the §11.7 halt-mechanism PIN.

### Phase A (AMENDED v3) — adds canonical pattern config + bypass-row writer helper

In addition to v1 + v2 Phase A scope, Phase A v3 adds:

1. **Author `Production/scripts/ds23_pattern_config.txt`** with the canonical default regex from §7.1.1. File is editable; comments-allowed; first non-comment line is the active pattern.
2. **Author `Production/scripts/write_ds_gate_bypass.py`** (helper) that POSTs the canonical bypass-row shape (`details = {commit_sha, reason, actor, rule}`) to `prod_activity_log`. Used by hook bypass paths AND by reviewers writing manual waivers.
3. **Confirm CodeQL workflow `on:` keys in `mindfulnest-tooling/.github/workflows/codeql.yml`** (G13 below). If the actual CodeQL `on:` keys do NOT subset the v3 broadened `if`, extend the `if` clause OR document exclusions.

### Phase E (AMENDED in v3) — Weekly preflight audit hook + DS-24 halt mechanism PINNED

1. Carries forward v1 + v2 Phase E logic (>3 bypasses/7-day window, rationale-length check, 24h flap, week-1 override rate).
2. **(v3 PIN — addresses M-2)** Halt mechanism is `prod_blockers` row keyed `DS_24_FP_LOOP_SUSPECTED_<filepath>` (one row per halted file path; `is_resolved=false` while halt active; `is_resolved=true` releases the file). See §11.7 for the full mechanism.
3. **(v3 NEW — addresses M-1)** Preflight audit additionally checks: query `prod_activity_log` for the last 7 days of `DS_25_NO_PR_CONTEXT` rows; aggregate the `details.trigger_event` distribution; if the dominant trigger event is NOT in the v3 broadened `if` clause, write `DS_25_TRIGGER_DRIFT_DETECTED` blocker.
4. All other Phase E logic preserved verbatim from v2.

### Phase F (AMENDED v3) — adds SKILL.md DS-23 grammar update task

Phase F v3 adds:

- **Update `.claude/skills/zero-error-qa/SKILL.md` DS-23 section (line 261 area)** to document BOTH commit-message grammars as accepted (HIGH-3):
  - `Swept: <FILE_LIST>` + optional `Verified: <count>` — preferred for hook-generated routine sweeps.
  - `Swept <FILE> for \`<PATTERN_REGEX>\`:` + bulleted line-list — preferred for hand-authored multi-line audits where line-by-line disposition matters.
- This is a SKILL.md edit and is therefore IMPLEMENTATION-PHASE work; v3 (the spec) does NOT edit SKILL.md.

### Phase E.5 — preserved (was added in earlier amendment work outside this session) — N/A in v3.

### All other phases — preserved verbatim from v1 + v2.

---

## §9 Open Decisions — preserved from v1 + v2; v3 adds OD10–OD12

(See v1 §9 OD1–OD7 + v2 §9-v2 OD8–OD9.)

### §9-v3 — additional open decisions surfaced by Cursor round-2

| # | Question | v3 recommendation |
|---|----------|-------------------|
| OD10 (v3 — RESOLVED in v3-C 2026-05-09) | Should the canonical DS-23 regex be tightened to require word-boundary anchors (`\\b`) to reduce false-positive hits on substring matches (e.g. file containing `tokensuffix` matching `token`)? | **RESOLVED in v3-C: canonical pattern uses `\b...\b` word boundaries with explicit allow-list (see §7.1.1).** v3-C replaced v3-A's unbounded `auth(?:_\|-)?(?!or)[a-z]*` form with explicit `\b(secret\|credential\|token\|...)\b` allow-list per Cursor round-3 MEDIUM. The conservative choice was made; OD10 is now CLOSED. Phase G 30-day FP audit data is now a CONFIRMING data point (validates the v3-C tightening was correctly tuned), not a deciding factor. See §7.1.1 + §11.8 RR12 + §15 [VERIFIED-IN-V3-C] line. |
| OD11 (v3) | What is the canonical resolution path for a `DS_24_FP_LOOP_SUSPECTED_<file>` blocker — direct PATCH by Kim, or a CLI helper? | Recommended: author `Production/scripts/resolve_blocker.py <id>` in Phase A (folds into the bypass-writer helper module). Kim CAN PATCH directly via dashboard; CLI is preferred for audit-log cleanliness. |
| OD12 (v3 — LOW CLOSED in v3-B 2026-05-09) | If a single SHA belongs to multiple PRs (cherry-pick or fork-PR scenarios), v3-A §7.3.1's `gh api commits/<sha>/pulls --jq .[0]` arbitrarily picks the first. Should v3 iterate? | **CLOSED in v3-B.** §7.3.1 (v3-B) enumerates open PRs and branches: 0 open → notice-only skip + activity-log row; >1 open → hard-fail + write `prod_blockers` row `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` so Kim resolves before gate re-runs; exactly 1 → proceed normally. Defense-in-depth: Phase G 30-day audit retained for residual closed-PR cherry-pick rare-case drift (catches scenarios where commit shows in closed-PR history but gate bypassed via 0-open-PR path). See §0.1-v3-A LOW row + §10-v3 G15 + §11.8 RR11. |

---

## §10 Pre-Implementation Gates — preserved from v1 + v2; v3 adds G13–G14

(See v1 §10 G1–G10 + v2 §10-v2 G11–G12.)

### §10-v3 — additional pre-implementation gates

- [ ] **G13 (v3) — CodeQL workflow trigger compatibility verified.** Before Phase D wires the DS-25 workflow, check `mindfulnest-tooling/.github/workflows/codeql.yml` `on:` keys. The DS-25 broadened `if` clause (§7.3.1 v3) accepts `pull_request | push | schedule | workflow_dispatch` for the `workflow_run` event mode. If CodeQL uses any event NOT in this set (e.g. `repository_dispatch`), extend the `if` clause OR document exclusion rationale before merging the DS-25 workflow.
- [ ] **G14 (v3) — canonical pattern config + bypass writer helper landed.** `Production/scripts/ds23_pattern_config.txt` exists and contains a non-comment regex line. `Production/scripts/write_ds_gate_bypass.py` exists, accepts `--rule {DS-23,DS-25}`, `--commit-sha`, `--reason`, `--actor`, and POSTs the canonical bypass-row shape (`details.commit_sha` top-level key). Phase A is incomplete until both land.
- [ ] **G15 (v3-B; AT/AF defined in v3-D) — multi-PR-detect step in §7.3.1 wired correctly.** Before merging the DS-25 workflow, verify the PR resolution step matches the v3-B implementation: (a) `PR_LIST` enumerates open PRs only (`select(.state == "open")`), (b) `PR_COUNT == 0` exits 0 with `DS_25_NO_OPEN_PR` activity-log row, (c) `PR_COUNT > 1` exits 1 AND writes `prod_blockers` row keyed `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` AND emits a `DS_25_AMBIGUOUS_PR_CONTEXT` activity-log row, (d) `PR_COUNT == 1` proceeds with `PR_LIST | jq -r '.[0]'`. **AT20 + AF10 (now defined in §6.5 per v3-D)** cover the synthetic test matrix for the three branches. This gate is the runtime enforcement of the v3-B closure of the v3-A historical LOW item (now CLOSED — see §0.1-v3-B + RR11 + OD12); without this gate the cherry-pick / multi-PR ambiguity would revert to arbitrary `.[0]` selection.
- [ ] **G16 (v3-D; RENAMED in v3-E from "G14 extension") — `SECURITY_GLOBS` includes BOTH top-level and nested `functions/src/` patterns.** Before Phase A→B promotion, verify the pre-commit hook's `SECURITY_GLOBS` array contains all four `functions/src/` patterns: `'functions/src/*.ts'` (top-level), `'functions/src/**/*.ts'` (nested), `'functions/src/*.js'` (top-level), `'functions/src/**/*.js'` (nested). Verified at v3-D author time: bash `case`-glob matching for `**/*.ts` does NOT match `functions/src/index.ts` (top-level entry — canonical Firebase Functions entry-point file); only the `*.ts` companion pattern catches it. AT21 + AF11 (defined in §6.5 per v3-D) cover the positive + negative test cases. Without this extension, top-level `functions/src/index.ts` silently bypasses DS-23 sweep enforcement. **v3-E rename rationale (Cursor round-5 MEDIUM-3):** v3-D labelled this "G14 extension" which created a duplicate-G14 surface vs the base canonical-pattern-config gate. v3-E promotes the glob-coverage extension to its own gate number. G14 stays as the base canonical-pattern-config gate; G16 covers the v3-D glob-coverage extension.
- [ ] **G17 (v3-C; RENUMBERED in v3-E from G16) — CodeQL trigger-set re-read at install time (HARDENS G13).** v3-C author-time read of `mindfulnest-tooling/.github/workflows/codeql.yml` confirmed actual triggers: `push: branches: [main]`, `pull_request: branches: [main]`, `schedule: cron "0 9 * * 1"`. The v3-A broadened `if`-clause (`pull_request | push | schedule | workflow_dispatch`) is a superset — no event missed. Phase A install MUST re-read codeql.yml at install time (in case of drift between v3-C author time and install time); if a NEW trigger has been added that lies outside the v3-A `if`-clause set, Phase A extends the `if`-clause OR documents why the new event mode is intentionally excluded. This is HARD STOP gate (Phase A blocks promotion to Phase B until G17 is satisfied with explicit codeql.yml citation in the install log). G13 retained as soft-version of the same check; G17 is the hard-stop tightening. **v3-E renumber rationale (Cursor round-5 MEDIUM-3):** v3-C originally numbered this gate G16; v3-E renumbers to G17 because the v3-D glob-coverage extension (formerly "G14 extension") was promoted to G16 to eliminate the duplicate-G14 label. Semantics unchanged.

---

## §11 Risk Assessment

§11.1 + §11.3 + §11.4 + §11.5 preserved verbatim from v1; §11.2 preserved from v2; §11.6 preserved from v2; §11.7 NEW v3; §11.8 NEW v3.

### §11.7 (NEW v3) — DS-24 halt mechanism PINNED (addresses M-2)

**Risk:** v2 Phase E says "halt the DS-24 gate for that file" but doesn't pin where halt state lives. Without a defined source-of-truth, the halt is aspirational prose; implementations diverge.

**v3 mechanism (PINNED):**

1. **Source of truth:** `prod_blockers` collection. Halt state for file path `<F>` is encoded as one row with `blocker_type = "DS_24_FP_LOOP_SUSPECTED_<F>"` and `is_resolved = false`. While the row is active and unresolved, DS-24 sweeps for `<F>` are skipped.
2. **Writer:** Phase E preflight audit (`Production/scripts/weekly_preflight_audit.py`) creates the row when 24h flap threshold (>5 events on `<F>`) is breached. Hook itself does NOT write halt rows; only preflight does.
3. **Reader:** the pre-commit hook (Phase A scope) fetches `prod_blockers` once per process invocation, filtering for `blocker_type[_starts_with]="DS_24_FP_LOOP_SUSPECTED_"` AND `is_resolved[_eq]=false`. The fetched list is cached for the lifetime of the hook process (one commit). Re-fetched on next hook invocation (next commit).
4. **Cache TTL:** per-commit. Hook starts → fetch → check staged paths → exit. Next commit → fresh fetch.
5. **Skip semantics:** if any active halt blocker matches a staged path's filename, the hook emits `DS_24_HALTED_BY_BLOCKER: <F> (blocker id=<N>)` notice on stderr and SKIPS the DS-24 sweep for that file. The COMMIT IS NOT BLOCKED. Only the DS-24 audit step for `<F>` is bypassed.
6. **Resolution path:** Kim PATCHes the blocker row to `is_resolved=true` (via Directus dashboard or `Production/scripts/resolve_blocker.py <id>` per OD11). Next commit re-enables DS-24 for `<F>`.
7. **Audit:** every halt-skip emits an activity-log row `DS_24_HALTED_BY_BLOCKER` with `details = {commit_sha, file_path, blocker_id}` so halt usage is observable in the same audit channel as bypasses.

**Why this closes M-2:** halt state is no longer "aspirational prose"; it's a Directus row with explicit lifecycle (preflight writes, Kim resolves), explicit reader (pre-commit hook, per-commit fetch), and explicit observability (activity-log row per skip). Aspirational → mechanical.

### §11.7-v3-C (NEW v3-C 2026-05-09) — DS-24 escalation tiers (addresses Cursor round-3 MEDIUM "skip-don't-block weakens enforcement")

Cursor round-3 flagged that v3-A's halt-skip semantics (commit not blocked when DS-24 is halted on a file) could permit repeated changes during sustained flap conditions, reducing deterrence unless coupled with stronger visibility/escalation. v3-C retains the developer-friendly skip-at-commit-time mechanism (deterrent at commit time would block Kim mid-flow on a file that the gate itself misclassified) but adds a 3-tier escalation chain that closes the deterrence gap at progressively heavier enforcement points:

| Tier | Trigger | Mechanism | Enforcement weight | Visibility |
|------|---------|-----------|---------------------|------------|
| **Tier 1 — Skip + notice (v3-A baseline, RETAINED)** | Pre-commit hook detects active `DS_24_FP_LOOP_SUSPECTED_<F>` blocker matching staged path | Hook emits `DS_24_HALTED_BY_BLOCKER` notice on stderr + writes activity-log row; SKIPS DS-24 sweep for `<F>`; commit proceeds | Soft (commit not blocked) | Per-commit stderr + per-commit activity-log row |
| **Tier 2 — Repeated-halt escalation blocker (NEW v3-C)** | Same `<F>` accumulates >3 `DS_24_HALTED_BY_BLOCKER` activity-log rows in a 7-day rolling window | Pre-commit hook (or weekly_preflight_audit, see Tier 3) writes `prod_blockers` row keyed `DS_24_REPEATED_HALT_<F>` with `is_resolved=false`; row carries the count + the most-recent halt activity-log row ids | Medium (visible in dashboard; does not block commits but shows up in Kim's blocker queue) | `prod_blockers` row + dashboard surface |
| **Tier 3 — PR-merge gate (NEW v3-C)** | Kim's review on the original `DS_24_FP_LOOP_SUSPECTED_<F>` blocker (Tier 1 source) auto-creates a derived `prod_blockers` row keyed `DS_24_PR_MERGE_BLOCKED_<F>` ONLY for unresolved blockers persisting >14 days OR with Tier 2 escalations attached | DS-25 CI gate reads `prod_blockers` for `DS_24_PR_MERGE_BLOCKED_*` rows touching files in the PR; if any active row touches a PR file, gate hard-fails the PR (PR cannot merge until Kim PATCHes the underlying `DS_24_FP_LOOP_SUSPECTED_<F>` row to `is_resolved=true`) | Hard (PR merge blocked — heavier than commit-gate; affects merge to main, not local commit) | `prod_blockers` row + DS-25 CI gate failure on PR |

**Hooks-to-data wiring (v3-C):**
- Tier 2 trigger: pre-commit hook (Phase A scope) MAY write the `DS_24_REPEATED_HALT_<F>` blocker row at commit time when the count threshold is breached, OR (preferred for performance — avoid extra Directus call per commit) defer the count aggregation to `Production/scripts/weekly_preflight_audit.py` which queries `prod_activity_log` for `DS_24_HALTED_BY_BLOCKER` rows in the last 7 days, aggregates by `details.file_path`, and writes the Tier 2 blocker row when threshold exceeded.
- Tier 3 derivation: a NEW Phase E preflight task (`v3-C-preflight-tier3-derivation`) reads active `DS_24_FP_LOOP_SUSPECTED_<F>` rows; for each, checks (a) age > 14 days OR (b) presence of a `DS_24_REPEATED_HALT_<F>` Tier 2 row; if either is true, derives a `DS_24_PR_MERGE_BLOCKED_<F>` Tier 3 row (one-to-one mapping; Tier 3 row carries `derived_from_blocker_id` in its details).
- DS-25 PR-merge gate: §7.3.1 v3 workflow gains a NEW step. **v3-C documented this as Phase D scope (DESIGN-only).** **v3-E (Cursor round-5 HIGH-2 fix) folds the step into §7.3.1 YAML directly** as `Check DS-24 PR-merge halt blockers` (named id `ds24_halt_check`), runs AFTER `codeql_scope` check and BEFORE `Require sweep block in PR body`. Behavior: read `prod_blockers` for `blocker_type[_starts_with]=DS_24_PR_MERGE_BLOCKED_` AND `is_resolved[_eq]=false`; if ANY active row exists, write `::error::DS-24 PR-MERGE BLOCKED` + emit `DS_24_PR_MERGE_BLOCKED_GATE_FIRED` activity-log row + exit 1. Both this gate AND the existing CodeQL-scope check must pass for the PR to merge.
- Resolution: Kim PATCHes the underlying `DS_24_FP_LOOP_SUSPECTED_<F>` row to `is_resolved=true` (or `Production/scripts/resolve_blocker.py <id>` per OD11). On next preflight run, the Tier 3 row is auto-resolved (preflight checks for orphaned Tier 3 rows whose underlying Tier 1 source has been resolved).

**Why this closes the round-3 MEDIUM:** v3-A's skip-don't-block semantics protected developer flow but provided weak deterrence under sustained flap. v3-C keeps the developer-friendly Tier 1 (no commit blocked at the moment of edit), then adds Tier 2 dashboard visibility once the file repeatedly halts (Kim sees the recurring symptom in the blocker queue) and Tier 3 PR-merge gate (PR cannot ship to main while the underlying false-positive loop remains unresolved). Three tiers means three independent deterrence points with progressively heavier enforcement — sustained flap can't slip through silently. Documented as RR13 in §11.8.

### §11.8 (NEW v3 — RR11 status flipped to CLOSED in v3-B 2026-05-09; RR12 + RR13 added in v3-C 2026-05-09) — Risk rows for the 6 round-2 findings + 1 LOW (now CLOSED) + 2 round-3 MEDIUM additions

| Risk row | Failure mode | Cursor round-2 finding | v3 mitigation |
|---|---|---|---|
| RR5 — Banner contradiction blocks LD filing | v2 §0 forbids "Directus PATCHes" while v2 §15-v2 mandates filing the v2 LD. Subagent following v2 strictly cannot file LD-617. | HIGH-1 (round-2) + HIGH-2 (round-3 framing tightening) | §0 (v3-A then RE-FRAMED v3-C) — v3-A used "DESIGN-ONLY for production code + carve-out for LD/activity-log" framing. Cursor round-3 HIGH-2 flagged residual conflict with explicit in-session mutation intent. **v3-C replaces with "GOVERNANCE-AUTHORING" classification** — spec-authoring artifacts (LD + activity-log) are the deliverables, not exceptions. Production code mutation remains forbidden; spec authoring IS the work product. §15-v3 / §15-v3-B / §15-v3-C all describe deliverables under this classification. |
| RR6 — Hook ships with non-runnable placeholder | v2 §7.1.1 grep snippet contains literal `<security-fix-pattern>` placeholder. Implementer cannot copy. Phase A ships broken hook OR has to re-derive pattern from scratch. | HIGH-2 | §7.1.1 (v3-A then v3-C) — placeholder REPLACED by `Production/scripts/ds23_pattern_config.txt` (Phase A creates) + canonical default regex (v3-C TIGHTENED: `\b(secret\|credential\|token\|password\|api[_-]?key\|auth\|authn\|authz\|authentication\|authorization\|jwt\|bearer\|oauth\|saml\|sso\|session[_-]?(?:id\|key\|token))\b` — word-boundary bounded explicit allow-list, supersedes v3-A unbounded `auth(?:_\|-)?(?!or)[a-z]*` form). Hook reads file; pattern is editable; SKILL.md DS-23 becomes documented home in Phase F. See RR12 for v3-C tightening rationale. |
| RR7 — DS-23 grammar contract swap breaks SKILL canon | v2 §7.1.2 CI regex `^Swept:` only matches the new short form. Anyone generating the SKILL canonical `Swept <FILE> for \`pattern\`:` block fails CI. Implicit contract swap. | HIGH-3 | §3.2-v3 + §7.1.2 (v3) — union regex `^Swept(:\| .+ for \`)` accepts BOTH forms. Phase F task added: SKILL.md DS-23 section update to document both. Backward-compatible; nothing pre-existing breaks. |
| RR8 — DS-25 race-mitigation silently disabled | v2 `if` clause requires `workflow_run.event == 'pull_request'` but CodeQL frequently runs on push or schedule. Job never fires for those modes; race window stays open. | M-1 | §7.3.1 (v3-A then HARDENED v3-C) — broadened `if` accepts 4 events. **v3-C verified actual codeql.yml triggers at author time** — the v3-A broadened set is a superset (no event missed). G13 (soft re-read) + G17 (formerly G16 in v3-C; RENUMBERED in v3-E HARD-STOP install-time re-read) + AF9 + Phase E preflight catch drift. |
| RR9 — Halt mechanism is prose-only | v2 Phase E says halt the gate but doesn't pin where halt state lives. Implementations diverge; halt may not actually take effect. | M-2 | §11.7 (NEW v3-A) — PINNED: `prod_blockers` row `DS_24_FP_LOOP_SUSPECTED_<file>`, per-commit hook fetch, activity-log on every skip. STRENGTHENED in v3-C with 3-tier escalation (see §11.7-v3-C + RR13). |
| RR10 — `_contains` filter is jsonb-fragile | v2 audit-row queries use `filter[details][_contains]=$SHA`. `details` is jsonb; the filter shape may match substrings, fail under nested objects, or be silently malformed. False rejects + false accepts. | M-3 | §7.1.2 + §7.3.1 (v3) — replaced by `filter[details][commit_sha][_eq]=$SHA` against verified jsonb column. Canonical bypass-row shape `{commit_sha, reason, actor, rule}` documented; AF8 catches malformed bypass writers. |
| RR11 — Multi-PR cherry-pick edge case (LOW CLOSED in v3-B 2026-05-09) | v3-A `gh api commits/<sha>/pulls --jq .[0]` arbitrarily picked the first PR for SHAs belonging to multiple PRs. v3-B replaces this with an enumerate-then-branch step that detects 0 / >1 / 1 open-PR cases explicitly. | LOW (CLOSED in v3-B) | §7.3.1 (v3-B) multi-PR-detect block + §10-v3 G15 (verification gate) + §0.1-v3-A LOW row (status flipped) + §0.1-v3-B summary row + OD12 (CLOSED). On >1-open-PR collision, gate hard-fails + writes `prod_blockers` row `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` so the operator must rebase/merge before re-run. Phase G 30-day audit retained as defense-in-depth for residual closed-PR cherry-pick drift (rare). |
| RR12 — DS-23 canonical regex overmatches (NEW v3-C 2026-05-09) | v3-A pattern `(secret\|credential\|token\|password\|api[_-]?key\|auth(?:_\|-)?(?!or)[a-z]*)` uses unbounded `[a-z]*` suffix; matches `authentic`, `authentication`, `authorization` and other arbitrary `auth*` derivations as side effects. False-positive pressure on identifiers that contain security-vocabulary substrings. | round-3 MEDIUM (regex word-boundaries) | §7.1.1 (v3-C) — pattern REPLACED with explicit allow-list bounded by `\b` word boundaries: `\b(secret\|credential\|token\|password\|api[_-]?key\|auth\|authn\|authz\|authentication\|authorization\|jwt\|bearer\|oauth\|saml\|sso\|session[_-]?(?:id\|key\|token))\b`. Trade-off: less catchy regex; new vocabulary requires PR to add (treat as a feature — additions are reviewable). AT16 + RR6 + §15 ASSUMED→VERIFIED-IN-V3-C all updated. |
| RR13 — DS-24 halt-skip semantics weak under sustained flap (NEW v3-C 2026-05-09) | v3-A halt-on-blocker emits `DS_24_HALTED_BY_BLOCKER` notice and skips the sweep; commit is NOT blocked. Sustained flap (developer keeps editing the same file while halt is active) lets repeated changes proceed with no progressively stronger deterrence. | round-3 MEDIUM (DS-24 enforcement strengthening) | §11.7-v3-C (NEW) — 3-tier escalation: Tier 1 retains skip-don't-block (developer flow protected); Tier 2 writes `DS_24_REPEATED_HALT_<F>` blocker on >3 halts/7-day-window (dashboard visibility); Tier 3 derives `DS_24_PR_MERGE_BLOCKED_<F>` for unresolved blockers >14 days OR with Tier 2 escalations attached, and DS-25 PR-merge gate hard-fails the PR until underlying `DS_24_FP_LOOP_SUSPECTED_<F>` is resolved. Deterrence at 3 progressively heavier enforcement points. |

---

## §12 Rollback Per Phase — preserved verbatim from v1 §12

§12 changelog (v3 entry appended to v1 + v2 entries):

| Date | Version | Change | Driver |
|---|---|---|---|
| 2026-05-08 | v1 | Initial spec authored. | Tech-spec dual-Opus debate per §4. |
| 2026-05-08 | v2 | Cursor v1 review (4 findings: 2 HIGH + 2 MED) addressed. §7.1.1 + §7.1.2 + §7.3.1 + §11.2 + Phase E amended. §0.1 v2 changelog row added. §6.4 + §11.6 + §10-v2 gates appended. | Cursor's AMEND_V2 verdict on v1. |
| **2026-05-09** | **v3 (v3-A)** | **Cursor round-2 review on v2 (7 findings: 3 HIGH + 3 MEDIUM + 1 LOW deferred at v3-A author time; LOW subsequently CLOSED in v3-B — see next row). §0 banner narrowed (later RE-FRAMED in v3-C). §3.2 + §6.5 + §7.1.1 + §7.1.2 + §7.3.1 + Phase A + Phase E + Phase F amended; §9 OD10–OD12 + §10 G13–G14 + §11.7 + §11.8 added. All other v1 + v2 sections preserved verbatim by reference.** | **Cursor's round-2 review of v2.** |
| **2026-05-09** | **v3-B** | **Cursor round-2 LOW deferral CLOSED. §7.3.1 PR resolution step replaced: enumerate-then-branch (0 / >1 / 1 open-PR cases) instead of arbitrary `.[0]` selection; multi-PR ambiguity now writes `prod_blockers` row `DS_25_AMBIGUOUS_PR_CONTEXT_<sha>` and hard-fails. §0.1-v3-A LOW row + §9 OD12 + §11.8 RR11 statuses flipped DEFERRED→CLOSED. §0.1-v3-B summary row added. §10-v3 G15 (NEW gate) added. Phase G 30-day audit retained as defense-in-depth.** | **Round-2 LOW closure pass; multi-section internal-consistency sweep.** |
| **2026-05-09** | **v3-C** | **Cursor round-3 review on v3-B (5 findings: 2 HIGH + 3 MEDIUM) addressed. (1) HIGH-1: §16 line 717 LOW-deferral language repaired to LOW-closure; multi-section sweep across `low_deferred`/`LOW deferral` patterns. (2) HIGH-2: §0 banner RE-FRAMED from "DESIGN-ONLY for production code + carve-out" to "GOVERNANCE-AUTHORING" framing. (3) MEDIUM regex word-boundaries: §7.1.1 default canonical regex replaced with explicit `\b...\b` allow-list. (4) MEDIUM DS-24 escalation: §11.7-v3-C added with 3-tier escalation. (5) MEDIUM CodeQL trigger hardening: codeql.yml LOCATED + READ at v3-C author time; v3-A `if`-clause confirmed superset of actual triggers (push to main, pull_request to main, schedule Mondays); G17 (originally numbered G16 in v3-C; RENUMBERED in v3-E to eliminate G16 duplicate label after v3-D glob-coverage extension was promoted to G16) NEW HARD-STOP install-time re-read gate. RR12 + RR13 added; RR5/RR6/RR8/RR9 updated. Final-self-review pass mandatory (5-point checklist).** | **Cursor's round-3 review of v3-B; STRENGTHENED final-self-review discipline.** |
| **2026-05-09** | **v3-D** | **Cursor round-4 fix-and-consolidate (4 findings: 2 HIGH real bugs + 2 MEDIUM wording). (1) OD10 contradiction RESOLVED — rewritten in place to "RESOLVED in v3-C" (no longer references "default to no `\b`"). (2) Glob coverage HIGH-2 FIXED — `SECURITY_GLOBS` adds top-level `functions/src/*.ts` + `*.js` companions to nested patterns (bash `case`-glob misses top-level under `**/*.ts`; verified empirically). (3) AT20 + AF10 (multi-PR-detect) + AT21 + AF11 (glob coverage) ADDED to §6.5; G15 wording updated to "now defined"; G14 extension NEW. (4) Stale `[INFERRED]` CodeQL trigger-key-set claim REMOVED from §15 (kept only the `[VERIFIED-IN-V3-C]` line). CONSOLIDATE not OVERLAY — fixes applied in place; no v3-D RR rows piled atop v3-C.** | **Cursor's round-4 review of v3-C; FIX-AND-CONSOLIDATE discipline.** |
| **2026-05-09** | **v3-E** | **Cursor round-5 fix-and-consolidate (6 findings: 2 HIGH real bugs + 3 MEDIUM consistency + 1 LOW). (1) HIGH-1 DEAD halt code FIXED — §7.1.1 loop now actually consults `HALTED_FILES` populated upstream; emits `DS_24_HALTED_BY_BLOCKER` notice on stderr per halted file; downstream DS-24 sweep contract documented. Prior v3-A loop populated the list but never read it. (2) HIGH-2 Tier 3 PR-merge gate FOLDED INTO §7.3.1 YAML — `Check DS-24 PR-merge halt blockers` step added (id `ds24_halt_check`) BEFORE `Require sweep block in PR body`; reads `prod_blockers` for `DS_24_PR_MERGE_BLOCKED_*` rows + writes `DS_24_PR_MERGE_BLOCKED_GATE_FIRED` activity-log + exits 1 on any active row. v3-C deferred this to Phase D as DESIGN-only; v3-E specs it concretely. §11.7-v3-C narrative updated. (3) MEDIUM-1 §12 reordered chronologically (v3-A → v3-B → v3-C → v3-D → v3-E) — was misordered with v3-D before v3-C. (4) MEDIUM-2 §15-v3-D + §15-v3-E LD-filing intent blocks ADDED matching §15-v3-C pattern. (5) MEDIUM-3 G16 RENAMED — "G14 extension (v3-D)" relabeled to G16 to eliminate duplicate G14 label; G15 was already G15-v3-B; G16 is now glob-coverage extension. NOTE: this REPLACES the v3-C "G16 CodeQL trigger-set re-read" gate (which is renumbered to G17 in v3-E). (6) LOW §13 enumeration updated to "AT14–AT21 + AF8–AF11" (v3-D added AT20/AF10/AT21/AF11). CONSOLIDATE-not-overlay discipline: fixes applied in place; no v3-E RR rows piled atop earlier rounds.** | **Cursor's round-5 review of v3-D; FIX-AND-CONSOLIDATE with CODE-BLOCK-AUDIT discipline.** |

---

## §13 Testing Plan — preserved verbatim from v1 + v2

(v3-additional test cases AT14–AT21 + AF8–AF11 enumerated in §6.5 above — v3-A added AT14–AT19 + AF8–AF9; v3-D added AT20+AF10 multi-PR-detect synthetic matrix and AT21+AF11 glob-coverage positive/negative cases per Cursor round-4 MEDIUM-1; v3-E refreshes this enumeration per Cursor round-5 LOW. All extend the §13 synthetic PR matrix without removing any v1 or v2 test.)

---

## §14 Reference Index (per DS-15 §16)

§14.1–§14.5 preserved from v1 + v2. v3 amendments below.

### §14.1-v3 — additional files cited in v3

| File | Path | Confidence | Source/use |
|---|---|---|---|
| **v2 baseline (THIS spec's predecessor)** | `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v2.md` | [VERIFIED] (sha256 `a05a5dbf28b3b4514ab7afa6f783d3b1e00d504da8ed7fb3014f244fef101a6e` at v3 author time, 516 lines) | All preserved-by-reference sections from v2; v3 supersedes only the sections enumerated in §0.3. |
| **v3 self-reference** | `Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md` | [DESIGN] | This document. Cited from §0.1, §0.3, §3.2-v3, §6.5, §7.1.1–§7.1.2, §7.3.1, §8 Phase A + Phase E + Phase F, §11.7, §11.8. |
| **DS-23 SKILL.md (cited for HIGH-3)** | `.claude/skills/zero-error-qa/SKILL.md` line 261 area | [VERIFIED] (read at v3 author time) | Documents legacy `Swept <FILE> for \`pattern\`:` grammar; Phase F (v3) adds short-form documentation alongside. |
| **DS-23 pattern config (NEW Phase A artifact)** | `Production/scripts/ds23_pattern_config.txt` | [DESIGN] | Source-of-truth for the canonical regex consumed by the prepare-commit-msg hook. Phase A creates. |
| **DS gate bypass writer (NEW Phase A artifact)** | `Production/scripts/write_ds_gate_bypass.py` | [DESIGN] | Helper that POSTs canonical bypass-row shape `{commit_sha, reason, actor, rule}` to `prod_activity_log`. Phase A creates. |
| **prod_activity_log details column** | Directus collection schema | [VERIFIED] (`DirectusAdminClient.fields('prod_activity_log')` at v3 author time returns `details \| json \| jsonb`) | Confirms M-3 fix is well-formed: nested-key jsonb filter `filter[details][commit_sha][_eq]=<sha>` is the documented Directus path-filter syntax for jsonb columns. |
| **LD-617 (v2 LD)** | Directus `prod_locked_decisions` id=617 key=`DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V2_WORKFLOW_TRIGGER_AUDIT_FIX_V1` | [VERIFIED] (queried at v3 author time) | v3 LD cross-references LD-617; v3 does NOT supersede LD-617; v3 LD records the round-2 amendments stacked atop. |
| **Cursor round-2 review record** | (Cursor session output, captured in v3 authoring brief) | [VERIFIED] | Cited verbatim in §0.1 row 1–7 + §11.8 RR5–RR11. |
| **Historical v3 amendment report (NOT this v3)** | `Production/docs/DS_23_24_25_V3_AMENDMENT_REPORT_20260508.md` | [VERIFIED] (24,497 bytes) | DIFFERENT artifact from this v3 spec. Documents earlier v3-flavored work (workflow_run/PR fix). UNTOUCHED in this session. Reader should NOT confuse with this spec file. |

### §14.2-v3 — LDs / blockers cited

- **LD-624 (v3-A LD; was "LD-NEW" at v3-A author time):** `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_DESIGN_BANNER_PATTERN_GRAMMAR_HALT_FILTER_V1` — filed at end of v3-A authoring session per §15-v3. Locks v3-A design decisions (banner narrowing, canonical pattern config, both-grammar acceptance, broadened workflow_run if-clause, halt mechanism PIN, nested-key jsonb filter).
- **LD-627 (v3-B LD):** `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_B_PR_AMBIGUITY_LOW_CLOSURE_V1` — filed at end of v3-B closure pass per §15-v3-B. Additive to LD-624 (does NOT supersede). Locks v3-B PR-ambiguity multi-PR-detect block + §10-v3 G15 + §0.1-v3-B summary row.
- **LD-633 (v3-C LD):** `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_C_ROUND_3_FIXES_V1` — filed at end of v3-C round-3 cleanup pass per §15-v3-C. Additive to LD-624 + LD-627 (does NOT supersede either). Locks v3-C: §0 GOVERNANCE-AUTHORING re-framing (round-3 HIGH-2); §16 line 717 + multi-section LOW sweep (round-3 HIGH-1); §7.1.1 word-boundary regex tightening (round-3 MEDIUM); §11.7-v3-C 3-tier escalation (round-3 MEDIUM); §7.3.1 trigger-set verification + §10-v3 G17 hard-stop (originally numbered G16 in v3-C; RENUMBERED in v3-E) (round-3 MEDIUM). Cursor round-3 verbatim quotes embedded.
- **LD-643 (v3-E LD; THIS revision's own LD):** `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_E_ROUND_5_FIXES_V1` — filed at end of v3-E round-5 fix-and-consolidate pass per §15-v3-E. Additive to LD-624 + LD-627 + LD-633 + LD-638 (does NOT supersede any). Locks v3-E: §7.1.1 HALTED_FILES live consultation in pre-commit loop (round-5 HIGH-1 — DEAD halt code fix); §7.3.1 YAML Tier 3 PR-merge gate step `ds24_halt_check` folded in concretely (round-5 HIGH-2 — was Phase D-deferred DESIGN-only); §12 chronological reorder (round-5 MEDIUM-1); §15-v3-D + §15-v3-E LD-filing intent blocks added (round-5 MEDIUM-2 — pattern symmetry); §10-v3 G16 rename + G17 renumber (round-5 MEDIUM-3 — duplicate G14 label eliminated); §13 enumeration AT14-AT21 + AF8-AF11 (round-5 LOW). Cursor round-5 verbatim quotes embedded. CODE-BLOCK-AUDIT discipline: HALTED_FILES use verified live; PR-merge gate YAML step verified present.
- **LD-638 (v3-D LD; one revision back):** `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_D_ROUND_4_FIXES_V1` — filed at end of v3-D round-4 fix-and-consolidate pass. Additive to LD-624 + LD-627 + LD-633 (does NOT supersede any). Locks v3-D: §9-v3 OD10 rewritten in place to RESOLVED (round-4 HIGH-1 — OD10 contradiction with §7.1.1 v3-C regex tightening); §7.1.1 SECURITY_GLOBS array adds top-level `functions/src/*.ts` + `*.js` companions to nested patterns (round-4 HIGH-2 — bash glob false-negative on Firebase Functions entry, verified empirically); §6.5 AT20+AF10+AT21+AF11 defined (round-4 MEDIUM-1 — closing dangling G15 reference); §15 stale [INFERRED] CodeQL-trigger-key-set claim removed (round-4 MEDIUM-2 — internal contradiction with [VERIFIED-IN-V3-C]); §10-v3 G14 extension added (verifies all four functions/src/ patterns). Cursor round-4 verbatim quotes embedded. Glob matcher test result embedded in --text.
- **LD-617 (v2 LD):** preserved by reference; v3 LDs (624 + 627 + 633) cross-reference it; v2 LD is NOT superseded.
- All v1-cited LDs (LD-580, LD-551) preserved by reference from v1 §14.2.
- **NEW blocker class introduced by v3 §11.7:** `DS_24_FP_LOOP_SUSPECTED_<filepath>` — one row per halted file, `is_resolved` lifecycle, written by Phase E preflight, read by Phase A pre-commit hook. [DESIGN — not yet created.]
- **NEW blocker class introduced by v3-C §11.7-v3-C Tier 2:** `DS_24_REPEATED_HALT_<filepath>` — written when same file accumulates >3 `DS_24_HALTED_BY_BLOCKER` activity-log rows in 7-day rolling window. Dashboard visibility tier. [DESIGN — not yet created.]
- **NEW blocker class introduced by v3-C §11.7-v3-C Tier 3:** `DS_24_PR_MERGE_BLOCKED_<filepath>` — derived by Phase E preflight when underlying `DS_24_FP_LOOP_SUSPECTED_<F>` row is unresolved >14 days OR has Tier 2 escalation attached. DS-25 PR-merge gate hard-fails the PR. [DESIGN — not yet created.]
- **NEW blocker class introduced by v3 Phase E:** `DS_25_TRIGGER_DRIFT_DETECTED` — written when observed CodeQL trigger event lies outside the v3 broadened `if`. [DESIGN — not yet created.]
- v2's `DS_24_FP_LOOP_SUSPECTED` (single row) + `DS_24_FP_TUNING_NEEDED` blocker classes preserved from v2.

### §14.3-v3 — Memory references — preserved verbatim from v1 + v2.

### §14.4-v3 — Cross-references between this spec's sections

Preserved from v2. v3 adds:
- §0 (banner narrowing) ↔ §15-v3 (LD filing intent) — narrowed banner is what allows §15-v3's LD filing without contradicting §0.
- §3.2-v3 (both-grammar decision) ↔ §6.5 AT14 + AT15 (acceptance criteria for both grammars) ↔ §7.1.2 (union regex implementation) ↔ Phase F (SKILL.md update task) — HIGH-3 trace.
- §7.1.1 (canonical pattern config) ↔ Phase A G14 + §10-v3 G14 (gate verifying both Phase A artifacts landed) ↔ §6.5 AT16 (acceptance criteria) — HIGH-2 trace.
- §7.3.1 (broadened if-clause) ↔ §10-v3 G13 (verification gate) ↔ Phase E (drift detection) ↔ §6.5 AT17 + AF9 — M-1 trace.
- §11.7 (halt mechanism) ↔ §6.5 AT19 ↔ Phase E + Phase A — M-2 trace.
- §7.1.2 + §7.3.1 (nested-key jsonb filter) ↔ canonical bypass shape ↔ §6.5 AT18 + AF8 ↔ Phase A bypass writer — M-3 trace.

### §14.5-v3 — preserved verbatim from v1 + v2.

---

## §15 Confidence Sweep (per Rule 24)

Every v3 amendment carries a confidence tag:
- **[VERIFIED]:** v2 sha256 + line count cross-checked (`shasum -a 256` at v3 author time). DS-23 SKILL grammar read verbatim. `prod_activity_log` schema confirmed (`details` is `json/jsonb`). LD-617 existence confirmed via Directus query.
- **[VERIFIED-FROM-V2]:** all v2 facts inherited intact (workflow_run payload-shape rationale, sentinel-file replacement doctrine, 24h flap + week-1 override-rate thresholds, Phase E preflight integration).
- **[INFERRED]:** Directus jsonb nested-key filter syntax (`filter[details][<key>][_eq]=<val>`) — Directus documents this for jsonb columns; the v3 hook's bypass query uses it; pre-merge AT18 + AF8 will validate empirically. (v3-D: stale CodeQL-trigger-key-set [INFERRED] claim REMOVED — superseded by the [VERIFIED-IN-V3-C] line below; keeping both created an internal contradiction flagged by Cursor round-4 MEDIUM-2.)
- **[VERIFIED-IN-V3-C]:** `mindfulnest-tooling/.github/workflows/codeql.yml` `on:` keys read at v3-C author time from `/Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml` — actual triggers: `push: branches: [main]`, `pull_request: branches: [main]`, `schedule: cron "0 9 * * 1"` (Mondays 09:00 UTC). NO `workflow_dispatch`, NO `repository_dispatch`. v3-A broadened `if`-clause (`pull_request | push | schedule | workflow_dispatch`) is a SUPERSET of actual triggers — no event missed; `workflow_dispatch` listed defensively for future trigger additions. G13 retained for install-time re-verification; G17 (NEW v3-C as G16; RENUMBERED in v3-E to G17 to eliminate duplicate G16 label after v3-D glob-coverage extension was promoted to G16) hardens to actual trigger set.
- **[VERIFIED-IN-V3-C]:** Canonical regex pattern (`\b(secret\|credential\|token\|password\|api[_-]?key\|auth\|authn\|authz\|authentication\|authorization\|jwt\|bearer\|oauth\|saml\|sso\|session[_-]?(?:id\|key\|token))\b`) — explicit allow-list, word-boundary bounded; supersedes v3-A's unbounded `auth(?:_\|-)?(?!or)[a-z]*` form (Cursor round-3 MEDIUM). Operator-tunable via `Production/scripts/ds23_pattern_config.txt`; new vocabulary additions go through PR review. Revisit at Phase G 30-day audit (OD10).
- **[DESIGN]:** all v3 YAML examples in §7.1.1, §7.1.2, §7.3.1, §11.7, §11.8 RR rows, §10-v3 gates — proposed design, not extant.

### §15-v3 — LD-filing intent + activity-log row intent

At end of this session:

1. **File LD via `Production/scripts/lock_decision.py lock`:**
   - `--key DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_DESIGN_BANNER_PATTERN_GRAMMAR_HALT_FILTER_V1`
   - `--name "DS-23/24/25 v3 — design-banner narrowed + pattern selector + grammar reconcile + halt mechanism + filter syntax"`
   - `--text` cites all 6 round-2 findings + LD-617 cross-ref + v2 sha256
   - `--severity SOFT --task-category governance --enforcement-type awareness_only --scope-domain infra`
   - `--source-document Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md`

2. **POST activity-log row** to `prod_activity_log`:
   - `action = "DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_AUTHORED_V1"`
   - `details = {spec_path, spec_sha256, spec_lines, v2_path, v2_sha256, ld_id, cursor_findings_addressed (6), low_closed_in_v3_b (1, see §0.1-v3-B), cross_references (LD-580, LD-617, LD-617's source v2)}`
   - `details` does NOT include `task_description` per CLAUDE.md Rule 35 schema gotcha (silent migration; field is REQUIRED on prod_locked_decisions, NOT prod_activity_log).

### §15-v3-B (NEW 2026-05-09) — round-2 LOW closure LD-filing intent

At end of THIS session (v3-B closure pass):

1. **File NEW v3-B LD via `Production/scripts/lock_decision.py lock`** (additive — does NOT supersede LD-624):
   - `--key DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_B_PR_AMBIGUITY_LOW_CLOSURE_V1`
   - `--name "DS-23/24/25 v3-B — PR-ambiguity LOW closure + multi-section consistency"`
   - `--text` cites: §7.3.1 multi-PR-detect block (3-branch); §0.1-v3-A LOW row + OD12 + RR11 status flipped to CLOSED; §10-v3 G15 (NEW gate) added; defense-in-depth Phase G audit retained; predecessor LD-624 cross-ref; v3 spec sha256 pre/post.
   - `--severity SOFT --task-category governance --enforcement-type awareness_only --scope-domain infra`
   - `--source-document Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md`

2. **POST activity-log row** to `prod_activity_log` via `try_post_or_queue` (DS-30 canonical client):
   - `action = "DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_B_CLEANUP_V1"`
   - `details = {spec_path, spec_sha256_pre, spec_sha256_post, spec_line_count_post, ld_id_new, ld_id_predecessor (624), low_finding_closed: "PR_COMMITS_SHA_PULLS_DOT_ZERO_AMBIGUITY", pr_ambiguity_handling_added: true, grep_inventory_pre, grep_inventory_post, internal_consistency_verified: true, ds29_source_tagging: true}`
   - `details` does NOT include `task_description` per LD-597 (silent migration; field is REQUIRED on prod_locked_decisions, NOT prod_activity_log).

### §15-v3-C (NEW 2026-05-09) — round-3 cleanup LD-filing intent

This section describes a spec-authoring artifact (NOT production code mutation) per the §0 GOVERNANCE-AUTHORING re-framing.

At end of THIS session (v3-C round-3 cleanup pass):

1. **File NEW v3-C LD via `Production/scripts/lock_decision.py lock`** (additive — does NOT supersede LD-624 or LD-627):
   - `--key DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_C_ROUND_3_FIXES_V1`
   - `--name "DS-23/24/25 v3-C — multi-section LOW sweep + DESIGN-ONLY framing + regex word-boundaries + DS-24 escalation + CodeQL hard-gate"`
   - `--text` cites all 5 round-3 findings + Cursor verbatim quotes + LD-624 (v3-A predecessor) + LD-627 (v3-B predecessor) + v3 spec sha256 pre/post + line count + 5-finding resolution table.
   - `--severity SOFT --task-category governance --enforcement-type awareness_only --scope-domain infra`
   - `--source-document Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md`

2. **POST activity-log row** to `prod_activity_log` via `try_post_or_queue` (DS-30 canonical client):
   - `action = "DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_C_ROUND_3_CLEANUP_V1"`
   - `details = {spec_path, spec_sha256_pre, spec_sha256_post, spec_line_count_post, ld_id_new, ld_id_predecessors: [624, 627], all_5_findings_resolution: {high_1_line_717_low_deferral: "FIXED — line 717 + sweep across low_deferred/LOW deferral patterns", high_2_design_only_framing: "FIXED — re-framed to GOVERNANCE-AUTHORING per Option (a)", med_regex_word_boundaries: "FIXED — explicit \\b...\\b allow-list", med_ds24_escalation: "FIXED — 3-tier (skip+notice → repeated-halt blocker → PR-merge gate)", med_codeql_hard_gate: "FIXED — codeql.yml LOCATED + READ + verified superset; G16 NEW hard-stop"}, grep_inventory_pre, grep_inventory_post, codeql_yml_search_result: "FOUND at /Users/kimberlysmith/Projects/mindfulnest-tooling/.github/workflows/codeql.yml; actual triggers: push to main + pull_request to main + schedule cron Mondays 09:00 UTC; NO workflow_dispatch", final_self_review_pass: true, internal_consistency_verified: true, ds29_source_tagging: true}` (note: at v3-C author time the hard-stop CodeQL gate was numbered G16; subsequently RENUMBERED in v3-E to G17.)
   - `details` does NOT include `task_description` per LD-597.

### §15-v3-D (NEW 2026-05-09 — added in v3-E for symmetry with §15-v3-C) — round-4 cleanup LD-filing intent

This section describes a spec-authoring artifact (NOT production code mutation) per the §0 GOVERNANCE-AUTHORING re-framing.

At end of v3-D session (round-4 fix-and-consolidate pass):

1. **File NEW v3-D LD via `Production/scripts/lock_decision.py lock`** (additive — does NOT supersede LD-624, LD-627, or LD-633):
   - `--key DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_D_ROUND_4_FIXES_V1`
   - `--name "DS-23/24/25 v3-D — OD10 RESOLVED + glob coverage fix + AT20/AF10/AT21/AF11 + INFERRED dedup"`
   - `--text` cites all 4 round-4 findings + Cursor verbatim quotes + LD-624 (v3-A predecessor) + LD-627 (v3-B predecessor) + LD-633 (v3-C predecessor) + v3 spec sha256 pre/post + line count + 4-finding resolution table + glob matcher empirical test result.
   - `--severity SOFT --task-category governance --enforcement-type awareness_only --scope-domain infra`
   - `--source-document Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md`

2. **POST activity-log row** to `prod_activity_log` via `try_post_or_queue` (DS-30 canonical client):
   - `action = "DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_D_ROUND_4_CLEANUP_V1"`
   - `details = {spec_path, spec_sha256_pre, spec_sha256_post, spec_line_count_post, ld_id_new, ld_id_predecessors: [624, 627, 633], all_4_findings_resolution: {high_1_od10_contradiction: "FIXED — OD10 rewritten in place to RESOLVED in v3-C; Phase G demoted to confirming data point", high_2_glob_coverage: "FIXED — SECURITY_GLOBS adds top-level functions/src/*.ts + *.js companions; verified empirically", med_1_at20_af10_dangling: "FIXED — AT20+AF10+AT21+AF11 added to §6.5; G15 wording updated; G14 extension added", med_2_inferred_verified_contradiction: "FIXED — stale [INFERRED] CodeQL trigger-key-set claim removed from §15"}, grep_inventory_pre, grep_inventory_post, glob_matcher_test_result: "verified empirically at v3-D author time: bash case-glob 'functions/src/**/*.ts' against 'functions/src/index.ts' → NO MATCH; against 'functions/src/nested/foo.ts' → MATCH", final_self_review_pass: true, internal_consistency_verified: true, ds29_source_tagging: true}` (note: at v3-D author time the glob-coverage gate was labelled "G14 extension"; subsequently RENAMED in v3-E to G16 to eliminate G14 duplicate label.)
   - `details` does NOT include `task_description` per LD-597.

### §15-v3-E (NEW 2026-05-09) — round-5 cleanup LD-filing intent

This section describes a spec-authoring artifact (NOT production code mutation) per the §0 GOVERNANCE-AUTHORING re-framing.

At end of THIS session (v3-E round-5 fix-and-consolidate pass):

1. **File NEW v3-E LD via `Production/scripts/lock_decision.py lock`** (additive — does NOT supersede LD-624, LD-627, LD-633, or LD-638):
   - `--key DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_E_ROUND_5_FIXES_V1`
   - `--name "DS-23/24/25 v3-E — HALTED_FILES live + Tier 3 PR-merge gate in YAML + §12 chronological + §15-v3-D/E + G16 rename + §13 AT enumeration"`
   - `--text` cites all 6 round-5 findings + Cursor verbatim quotes + LD-624 (v3-A predecessor) + LD-627 (v3-B predecessor) + LD-633 (v3-C predecessor) + LD-638 (v3-D predecessor) + v3 spec sha256 pre/post + line count + 6-finding resolution table + CODE-BLOCK-AUDIT discipline note.
   - `--severity SOFT --task-category governance --enforcement-type awareness_only --scope-domain infra`
   - `--source-document Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md`

2. **POST activity-log row** to `prod_activity_log` via `try_post_or_queue` (DS-30 canonical client):
   - `action = "DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_V3_E_ROUND_5_CLEANUP_V1"`
   - `details = {spec_path, spec_sha256_pre, spec_sha256_post, spec_line_count_post, ld_id_new, ld_id_predecessors: [624, 627, 633, 638], all_6_findings_resolution: {high_1_dead_halt_code: "FIXED — §7.1.1 loop now actually consults HALTED_FILES; emits DS_24_HALTED_BY_BLOCKER notice on stderr per halted file; downstream DS-24 sweep contract documented", high_2_tier3_pr_merge_gate_yaml: "FIXED — §7.3.1 YAML gains 'Check DS-24 PR-merge halt blockers' step (id ds24_halt_check) BEFORE 'Require sweep block in PR body'; reads prod_blockers DS_24_PR_MERGE_BLOCKED_* + writes DS_24_PR_MERGE_BLOCKED_GATE_FIRED activity-log + exits 1 on any active row", med_1_changelog_chronological: "FIXED — §12 reordered chronologically (v3-A → v3-B → v3-C → v3-D → v3-E)", med_2_section_15_d_e_blocks: "FIXED — §15-v3-D + §15-v3-E LD-filing intent blocks added matching §15-v3-C pattern", med_3_g16_duplicate_rename: "FIXED — 'G14 extension (v3-D)' renamed to G16; v3-C G16 (CodeQL re-read) renumbered to G17; cross-references updated throughout", low_section_13_enumeration: "FIXED — §13 enumeration updated to AT14-AT21 + AF8-AF11"}, code_block_audit_result: {halted_files_use_count_post: "verified consulted in §7.1.1 loop", ds_24_pr_merge_blocked_yaml_step_present: true}, grep_inventory_pre, grep_inventory_post, final_self_review_pass: true, internal_consistency_verified: true, ds29_source_tagging: true}`
   - `details` does NOT include `task_description` per LD-597.

---

## §16 Self-Classification

**Tier:** ARCHITECTURAL (governance + CI infra) — preserved from v1 + v2.
**Risk classes affected:** governance-doctrine-shaping, side-effect, multi-stage, async — preserved. v3-A specifically targeted the design-only-vs-mutation contract + grammar-contract + halt-state + filter-portability classes (round-2 findings); v3-C specifically targeted the GOVERNANCE-AUTHORING framing tightening + regex word-boundary precision + DS-24 enforcement-tier strengthening + CodeQL trigger-set verification (round-3 findings).
**Six-Layer applicable layers:** 3, 4, 6 — preserved.
**Reviewer expectations:** Cursor v3 cross-review handoff (next file, NOT authored in this session) requires preflight evidence for the seven amended/added sections (§0, §3.2-v3, §6.5, §7.1.1, §7.1.2, §7.3.1, §11.7) + STRICT verification that all 6 Cursor round-2 findings (HIGH-1, HIGH-2, HIGH-3, M-1, M-2, M-3) are each addressed end-to-end with no residual TODO + LOW closure (multi-PR-per-commit ambiguity) is documented in §7.3.1 v3-B (multi-PR-detect block) + §0.1-v3-B summary row + §9 OD12 (CLOSED) + §10-v3 G15 (NEW gate) + §11.8 RR11 (CLOSED). v3-C cross-review additionally requires preflight evidence for the 5 round-3 findings (HIGH-1 multi-section LOW sweep + line 717 fix; HIGH-2 GOVERNANCE-AUTHORING framing replacing DESIGN-ONLY/Directus carve-out; MEDIUM regex word-boundary tightening §7.1.1 v3-C; MEDIUM DS-24 3-tier escalation §11.7-v3-C; MEDIUM CodeQL trigger-set hardening §7.3.1 v3-C + §10-v3 G17 [originally numbered G16 in v3-C; RENUMBERED in v3-E to G17 to eliminate G16 duplicate label]) — see §0.1-v3-C row. v3-E cross-review additionally requires preflight evidence for the 6 round-5 findings (HIGH-1 §7.1.1 HALTED_FILES live consultation; HIGH-2 §7.3.1 Tier 3 PR-merge gate step folded into YAML; MEDIUM-1 §12 chronological reorder; MEDIUM-2 §15-v3-D + §15-v3-E LD-filing intent blocks added; MEDIUM-3 G16 rename with v3-C G16 → G17 renumber; LOW §13 enumeration AT14-AT21 + AF8-AF11) — see §0.1-v3-E row.

---

*End of `DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md`.*

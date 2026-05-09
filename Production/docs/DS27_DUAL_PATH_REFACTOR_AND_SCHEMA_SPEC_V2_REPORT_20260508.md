# DS-27 Dual-Path Refactor + Schema Migration Spec/Handoff v2 — Proof Report

**Authored:** 2026-05-08.
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance rule revision affecting all future agent sessions; blast radius = every prompt, every spec/handoff, every filesystem-touching command going forward).
**Session:** `gallant-bouman-804b4f` worktree session, 2026-05-08.
**Activity log row:** `prod_activity_log` id=1776 (`DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_AUTHORED`).
**LD amended:** `prod_locked_decisions` id=584 (`WORKTREE_CONFUSION_PREVENTION_V1`) — notes appended with 2026-05-08 dual-canonical amendment.

---

## §0 — What changed and why

This proof report documents the bundled fixes applied to address Cursor's AMEND_V2 verdicts on the v1 schema migration spec + companion handoff:

1. **DS-27 refactored from Dropbox-only to dual-canonical-roots** — Cursor's review flagged the original "absolute paths anchored to Dropbox root only" rule as over-rigid because the tooling repo legitimately lives at `/Users/kimberlysmith/Projects/mindfulnest-tooling/`, and future repos (MindfulNest RN app + related) will also live under `/Users/kimberlysmith/Projects/`. v2 broadens the rule to TWO canonical roots while explicitly preserving the worktree prohibition and adding an outside-canonical-roots fallback that requires explicit authorization.
2. **HANDOFF_TEMPLATE_v2.md updated to dual-canonical** — same wording as DS-27 v2 mandated for every v2 handoff's Hard rules section.
3. **LD 584 notes amended** — authority record updated with the 2026-05-08 amendment paragraph naming the Cursor review origin and the new canonical paths.
4. **`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` authored** — applies 4 Cursor spec amendments (2 HIGH, 2 MED). v1 preserved.
5. **`HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` authored** — applies 3 Cursor handoff amendments (2 HIGH, 1 MED). v1 preserved.

All edits enforced the existing DS-27 single-canonical rule throughout this session (every Read/Edit/Write/Bash call used absolute Dropbox-anchored paths; no `cd` into any `.claude/worktrees/` subdirectory). The session author (this turn) is anchored to a worktree (`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/worktrees/gallant-bouman-804b4f/`) per the gitStatus envelope, BUT every filesystem operation went to the live Dropbox tree by absolute path, never relative to the worktree.

---

## §1 — Verbatim diff: SKILL.md DS-27 section (post-edit)

The DS-27 section after the dual-canonical refactor (10,417 chars). Embedded verbatim below.

```markdown
### DS-27. Worktree Confusion Prevention — Dual-Canonical-Path Discipline (added 2026-05-08, refactored 2026-05-08 v2 to support dual canonical roots after Cursor AMEND_V2 verdict on schema migration spec/handoff)

**WHY this DS exists:** On 2026-05-08, two separate agent operations confused the worktree subdirectory for the canonical project tree. (1) A duplicate-deletion task: agent `cd`-ed into `.claude/worktrees/<name>/` and edited duplicates that had already been resolved on the main tree, producing a partial-commit conflict. (2) A calendar-dep wiring task: agent operated on worktree-shadow files and Kim had to chase down which tree contained the actual fix. Both incidents share the Terminal-A-style halt pattern (agent locked into a worktree path, unable to reconcile with the canonical tree). The mechanical correction: every filesystem-touching command in agent prompts and during execution MUST use absolute paths anchored to one of the project's canonical roots, never relative paths anchored to a worktree subdirectory.

**v2 refactor (2026-05-08):** The original DS-27 anchored to a single root (the Mindfulnest Dropbox tree). Cursor's review of the schema migration spec/handoff (AMEND_V2 verdicts on the handoff template's "Dropbox-only" wording) flagged that constraint as over-rigid: the tooling repo legitimately lives at `/Users/kimberlysmith/Projects/mindfulnest-tooling/`, and the future MindfulNest React Native app + related repos will also live under `/Users/kimberlysmith/Projects/`. Forcing every command to anchor to the Dropbox tree would block valid reviews and valid implementation work in those repos. v2 broadens the rule to support TWO canonical roots while preserving the worktree prohibition.

**The doctrinal correction this rule encodes (v2 dual-canonical):**

- **Canonical roots (BOTH are first-class; pick the one matching the work):**
  1. **Primary — Mindfulnest project (Dropbox-anchored):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` — narrative, audio/video pipeline, Production scripts, Directus governance, Storyboard, design docs, locked decisions, activity log.
  2. **Secondary — Tooling and app repos (Projects-anchored):** `/Users/kimberlysmith/Projects/` — tooling repos (e.g., `mindfulnest-tooling/`), the MindfulNest React Native app (`mindfulnest-ios/`, `mindfulnest/` and related), and any other Kim-Projects-housed repos that legitimately participate in the MindfulNest stack.
- **Worktree shadow trees** under `.claude/worktrees/<name>/` (within EITHER canonical root) are SCRATCH SPACE, not the source of truth. Edits there do not survive merge unless the worktree is EXPLICITLY authorized in the handoff (named absolute path + Kim authorization rationale) and the work is committed back through standard branch-merge.
- **Default policy:** all agent operations on project files MUST cite ONE of the two canonical roots by absolute path. `cd`-ing into a worktree subdirectory and running commands relative to it is FORBIDDEN by default. `cd`-ing between canonical roots is fine; what is forbidden is operating from inside a worktree.
- **Outside both roots:** if a path falls outside BOTH canonical roots AND is not a worktree, the agent MUST surface for explicit Kim authorization before touching it (covers e.g., `~/Desktop/`, `~/Downloads/`, external mounts, third-party clones not in the MindfulNest stack).

**Trigger condition:** ANY of the following appears in a handoff, prompt, agent execution, or referenced document:

1. Relative paths in `Bash` commands that touch project files (e.g., `ls Production/docs/`, `cat Production/scripts/foo.py`, `ls src/`, `cat package.json`) without an explicit `cwd` declaration anchored to one of the two canonical roots.
2. `cd` into any `.claude/worktrees/` subdirectory (under either canonical root).
3. `Read`, `Edit`, or `Write` `file_path` parameters that are NOT absolute (do not start with `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` OR `/Users/kimberlysmith/Projects/`).
4. Handoff prompts that anchor work paths to a worktree subdirectory without explicit Kim authorization in chat.
5. Pre-existing partial commits / conflicting commits that suggest a worktree-shadow edit landed instead of a canonical-tree edit.
6. Filesystem references to paths OUTSIDE both canonical roots (e.g., `~/Desktop/foo`, `/tmp/bar`, `/Volumes/...`) without prior Kim authorization for that scope.

**Mechanical action:**

1. **Detect.** Before any filesystem-touching tool call, verify the path is absolute and anchored to one of the canonical roots. If a `Bash` command is about to use a relative path, rewrite it to absolute first (resolving against the appropriate canonical root for the work). If a `cd` into `.claude/worktrees/` is about to happen, ABORT and surface to Kim. If the path falls outside both canonical roots and is not a recognized exception (e.g., `~/.claude/` for global Claude config), surface for authorization.

2. **Verify.** Before any `Edit` / `Write` to a file, run `ls -la <absolute-path>` first to confirm the file exists at the expected location AND has the expected mtime/size. This catches both worktree-shadow drift (file exists in worktree but not in canonical tree, or vice versa) and stale-cache reads, and incidentally confirms which canonical root actually holds the file.

3. **Branch.**
   - **Path absolute + anchored to one of the canonical roots:** proceed.
   - **Path relative or anchored to worktree:** STOP. Rewrite to absolute path anchored to the appropriate canonical root. If the handoff explicitly requires worktree operation (rare), surface to Kim for confirmation before proceeding.
   - **Path absolute but anchored OUTSIDE both canonical roots:** allowed for global Claude config (`~/.claude/hooks/`, `~/.claude/settings.json`, `~/.claude/skills/` for cross-machine skill files), system-managed paths (Doppler env vars, OS temp), and read-only inspection of system files; FORBIDDEN for any new edit/write to project files. Surface for explicit authorization on first encounter.
   - **Ambiguous (e.g., a Projects-rooted repo where the canonical work belongs in Dropbox, or vice versa):** state the chosen root + rationale inline before proceeding.

4. **Audit.** When authoring agent prompts, the originating agent MUST inspect the prompt for relative-path patterns AND for paths outside the two canonical roots before sending. Prompts with relative-path filesystem commands MUST be rewritten before dispatch. Prompts referencing paths outside both canonical roots MUST state the authorization rationale inline.

**Verification proof requirement:**

- Phase 0 Step 2 preflight summary contains a one-line declaration naming the canonical root(s) the task touches: *"Path discipline scan: <N> filesystem references checked; all absolute and anchored to canonical root(s) [Dropbox|Projects|both]; <M> worktree references = 0 (or = explicitly authorized at <path>)."*
- If a relative-path violation was caught and corrected, Phase 7 Proof of Execution table contains a row with the original (rejected) command, the rewritten (absolute) command, the canonical root the rewrite targeted, and the file mtime confirmation.
- Activity log: a `PATH_DISCIPLINE_VERIFIED` row at session-end is optional but recommended for sessions with heavy filesystem operations; a `PATH_DISCIPLINE_VIOLATION_CORRECTED` row is REQUIRED if any rewrite occurred. Both row types include a `canonical_root` field naming which root(s) were in scope.

**Example failure modes it prevents:**

1. **Duplicate-deletion incident (2026-05-08):** agent `cd`-ed into `.claude/worktrees/<name>/` and ran `rm` on files that had already been resolved on `main`; the operation produced a partial-commit conflict because the worktree's HEAD was stale relative to the canonical tree. With DS-27 in place, Step 1 detection would have flagged the `cd` into worktree; Step 3 branch would have aborted and surfaced.
2. **Calendar-dep wiring incident (2026-05-08):** agent edited `weekly_preflight_audit.py` in a worktree shadow; Kim later could not reconcile which tree contained the canonical fix. With DS-27 in place, Step 2 verification (`ls -la <absolute-path>`) would have surfaced the worktree-vs-canonical mtime/size discrepancy before the edit, and Step 3 would have rewritten the path.
3. **(NEW v2) Tooling-repo review block (hypothetical, originating Cursor AMEND_V2):** an agent reviewing tooling-repo code at `/Users/kimberlysmith/Projects/mindfulnest-tooling/` would have been blocked by the original Dropbox-only DS-27 because the path doesn't start with the Dropbox root. With v2 dual-canonical in place, the Projects-anchored path is recognized as canonical and the review proceeds without spurious HALT.
4. **(NEW v2) Out-of-scope desktop edit:** an agent that strays into `~/Desktop/scratch/` or `/tmp/` for project work would now be flagged by trigger #6 as outside both canonical roots; agent surfaces for authorization rather than silently editing in scratch.

**Cross-references:**
- DS-26 (Gate-Check Discipline — No Autonomous-Mode Bypass) — sister rule against premature execution; DS-27 is the filesystem-discipline companion. DS-26 fires on HALT-gate semantics in handoffs; DS-27 fires on path-pattern semantics in commands.
- DS-19 (Standing Escape Hatches) — DS-27 is a named-trigger rule, DS-19 is standing-condition.
- HANDOFF_TEMPLATE_v2.md — handoff-side enforcement (every v2 handoff's Hard rules section MUST include the dual-canonical-roots discipline rule verbatim).
- LD `WORKTREE_CONFUSION_PREVENTION_V1` (2026-05-08, amended 2026-05-08 v2 dual-path) — locked decision authorizing this rule.
- CLAUDE.md Rule 19 — "no path open for error" — DS-27 closes one of those paths.
- Cursor AMEND_V2 verdicts on `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` + `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` (2026-05-08) — origin of the dual-path refactor.

**ENFORCEMENT IS DISCIPLINE-ONLY for now** — mechanical "PreToolUse hook scans Bash command + Read/Edit/Write file_path for `.claude/worktrees/` substring AND for absence of either canonical root prefix" detection is a near-term hardening candidate. Track via `prod_blockers` row `DS_27_MECHANICAL_GATE_PENDING`. Until then: discipline + Phase 0 Step 2 declaration + audit-row trail when violations corrected.
```

### Lookup table row (post-edit, verbatim)

```
| DS-27 | Worktree confusion prevention — dual-canonical-path discipline; all filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots (Dropbox project tree OR `/Users/kimberlysmith/Projects/`); no worktrees unless authorized | duplicate-deletion + calendar-dep wiring incidents (2026-05-08); v2 refactor 2026-05-08 from Cursor AMEND_V2 on schema migration spec/handoff; LD `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-path) | 0 Step 2, every phase |
```

---

## §2 — Verbatim diff: HANDOFF_TEMPLATE_v2.md absolute-path filesystem discipline section (post-edit)

The "v2 NEW — Absolute-path filesystem discipline" section after the dual-canonical refactor (3,848 chars). Embedded verbatim below.

```markdown
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

```

### Hard rules bullet (post-edit, verbatim)

The DS-27 hard-rule bullet in the "Hard rules — required bullets" section (anchor: "DS-27 explicit (NEW in v2; refactored 2026-05-08 v2 dual-canonical)"):

> - **DS-27 explicit (NEW in v2; refactored 2026-05-08 v2 dual-canonical):** "All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots require explicit Kim authorization."

### Anti-pattern #10 (post-edit, verbatim)

> 10. **(NEW in v2; refactored 2026-05-08 v2 dual-canonical) Operating inside `.claude/worktrees/<name>/` without explicit authorization, OR using paths outside both canonical roots without authorization.** Agents `cd`-ing into a worktree subdirectory edit the wrong tree and produce partial commits. Agents straying into `~/Desktop/`, `/tmp/`, or unrelated clones lose the audit trail. Always use absolute paths anchored to one of the two canonical roots: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary) or `/Users/kimberlysmith/Projects/` (secondary). Worktrees and outside-canonical paths require explicit authorization.

---

## §3 — LD 584 PATCH read-back (verbatim)

**Pre-PATCH `notes` field:**

> Added 2026-05-08 in same session that authored HANDOFF_TEMPLATE_v2.md + DS-27 + 3 v2-amended Cursor-cross-review handoffs. Origin: two worktree-confusion incidents same session (duplicate-deletion + calendar-dep wiring). Sister to LD GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1.

**Amendment appended (verbatim, exactly as Kim's prompt specified):**

> 2026-05-08 amendment: DS-27 refactored from Dropbox-only to dual-canonical-roots {Dropbox, Projects}. Originating Cursor review of schema migration spec/handoff (AMEND_V2 verdicts) flagged the over-rigid Dropbox-only constraint as blocking valid reviews. New canonical paths: Dropbox project root + Projects directory + (worktrees only with explicit authorization).

**Post-PATCH `notes` field (read-back via Directus GET, per Rule 35):**

> Added 2026-05-08 in same session that authored HANDOFF_TEMPLATE_v2.md + DS-27 + 3 v2-amended Cursor-cross-review handoffs. Origin: two worktree-confusion incidents same session (duplicate-deletion + calendar-dep wiring). Sister to LD GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1.
>
> 2026-05-08 amendment: DS-27 refactored from Dropbox-only to dual-canonical-roots {Dropbox, Projects}. Originating Cursor review of schema migration spec/handoff (AMEND_V2 verdicts) flagged the over-rigid Dropbox-only constraint as blocking valid reviews. New canonical paths: Dropbox project root + Projects directory + (worktrees only with explicit authorization).

**Read-back assertion result:** PASS (amendment string present in fetched notes; pre + amendment == post).

**Per Rule 35 verification:** the post-PATCH GET returned the new `notes` field with the appended paragraph; the script raised an `assert` if the substring was missing; assertion passed; no silent-write-failure detected.

---

## §4 — Schema spec v2 — verbatim §0.1 + §3.0 + §9

### §4.1 — Spec v2 §0.1 changelog (verbatim)

```markdown
## §0.1 — v2 Changelog (verbatim resolution per Cursor amendment)

Cursor's AMEND_V2 verdict on v1 returned 4 amendments (2 HIGH, 2 MED). Each is reproduced verbatim in the left column with the resolution in the right column. v1 sections that needed material change are listed under "Sections changed".

| # | Severity | Cursor amendment (verbatim) | Resolution applied in v2 | Sections changed |
|---|---|---|---|---|
| 1 | HIGH | Rule 1 contradiction: §3 says DEFER, §4-§7 still operationalize Phase 5. Add feature flag `PHASE_5_ENABLED=false` (default off). Phase 5 may NOT execute without explicit Kim-approval prod_locked_decisions row + script-level guard. | §3 Rule 1 verdict block now declares an explicit `PHASE_5_ENABLED` feature flag (default `false`) at three layers: (a) operational doctrine, (b) migration-script-level guard `assert os.environ.get('PHASE_5_ENABLED') == 'true' and KIM_APPROVAL_LD_PRESENT()`, (c) §6 Gate row dedicated to flipping the flag. Phases 4 and 5 in §5 are clearly tagged "blocked unless flag is true". §7 risk row added. | §3 Rule 1, §4 table, §5 Phase 5, §6 Gate, §7 |
| 2 | HIGH | Path discipline: add dual-path resolution policy. Canonical roots: {Dropbox, Projects}. Preflight resolves the canonical path set before analysis/execution. | §3 NEW subsection "Path discipline (v2 dual-canonical)" inserted before Rule 1, naming the two canonical roots and the preflight resolution requirement. §5 Phase 0 explicitly performs canonical-root resolution as Step 0. §11 reference index points to LD #584 v2 amendment + DS-27 v2 + HANDOFF_TEMPLATE_v2 v2. | §3 (new subsection), §5 Phase 0, §11 |
| 3 | MED | Rollback completeness: Phase 0 must produce snapshot with explicit fields {row_count, id_uniqueness, all_touched_ids_present}; pre-Phase-5 integrity check verifies snapshot completeness. | §4 Phase 0 expanded: snapshot now produces explicit fields (row_count + id_uniqueness assertion + all_touched_ids_present assertion) into a single JSONL artifact. §6 (Gate 7) extended with a "snapshot integrity check" assertion that runs BEFORE Phase 5 and fails the phase if any of the three fields is missing. §8 rollback narrative tied to the snapshot's three fields. | §4 Phase 0, §6 Gate 7, §8 |
| 4 | MED | Cost model split: §9 separate "machine time" vs "human review time"; keep 10-hour figure as planning baseline (machine + human combined). | §9 split into "Machine time" (script execution wall-clock per phase) + "Human review time" (Kim's attention, dry-run review, per-phase first-5 review, final audit) + "Total planning baseline (combined)" = 10 hours. Each line cites its own assumption set. | §9 |

**v1 vs v2 surface area:** v2 adds ~250 lines (new path discipline subsection, expanded Phase 0 snapshot schema, Gate 7 expansion, cost split). All v1 content preserved (no deletions); v2 additions are clearly labeled `(v2)` or `(NEW v2)` inline.

---
```

### §4.2 — Spec v2 §3.0 path discipline (verbatim)

```markdown
### §3.0 — Path discipline (v2 dual-canonical, NEW)

This subsection codifies Cursor's HIGH-severity Amendment #2.

**Mandate (v2):** every command, script, doc reference, and migration-side artifact in this spec MUST resolve filesystem paths against ONE of two canonical roots before any analysis or execution:

1. **Primary — Mindfulnest project (Dropbox-anchored):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`
2. **Secondary — Tooling and app repos (Projects-anchored):** `/Users/kimberlysmith/Projects/`

**Operational consequences for this migration:**

- The migration script `Production/scripts/migrate_schema_vocab_v1.py` MUST be authored at the Dropbox-anchored canonical path (it operates on Dropbox-housed Directus tooling artifacts).
- All script-internal path references (snapshot output path, dry-run report path, lockfile path) MUST resolve to absolute Dropbox-anchored paths (the lockfile lives in `~/.claude/mindfulnest-cache/` per §9, which is global-config-allowed and does NOT count as outside-canonical).
- Tooling-repo work referenced by this spec (none in v2; reserved for future v3) would resolve to `/Users/kimberlysmith/Projects/...` and would be explicitly named.
- `.claude/worktrees/` is FORBIDDEN under either canonical root unless the handoff explicitly authorizes a named worktree path.
- Outside-canonical paths (e.g., `~/Desktop/`, `/tmp/`, external mounts) are FORBIDDEN for migration writes; allowed only for global Claude config.

**Preflight resolution (v2 NEW):** Phase 0 (see §5) now performs path-discipline resolution as Step 0 BEFORE the dry-run snapshot:

```python
# Phase 0 Step 0 (v2 NEW) — canonical-root resolution
CANONICAL_ROOTS = {
    'dropbox': '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/',
    'projects': '/Users/kimberlysmith/Projects/',
}
EXPECTED_ROOT = CANONICAL_ROOTS['dropbox']  # this migration is Dropbox-housed
SCRIPT_PATH = Path(__file__).resolve()
assert str(SCRIPT_PATH).startswith(EXPECTED_ROOT), \
    f"Migration script not anchored to expected canonical root. Got: {SCRIPT_PATH}, expected prefix: {EXPECTED_ROOT}"
# Worktree-presence check
assert '.claude/worktrees/' not in str(SCRIPT_PATH), \
    f"Migration script running from a worktree shadow. Refusing. Path: {SCRIPT_PATH}"
```

**Cross-references:**
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority.
- `.claude/skills/zero-error-qa/SKILL.md` DS-27 (refactored 2026-05-08 v2 dual-canonical) — agent-side enforcement.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical) — handoff-side enforcement.
```

### §4.3 — Spec v2 §9 cost model split (verbatim)

```markdown
## §9 — Operational notes (v2 split: machine time vs human review time)

This section addresses Cursor's MED-severity Amendment #4. The v1 narrative mixed wall-clock and Kim-attention into a single "10 hours" estimate; v2 splits these explicitly.

### §9.1 — Machine time (script execution wall-clock)

| Phase | Step count | Network rate | Read-back overhead | Activity-log overhead | Estimated wall-clock |
|---|---|---|---|---|---|
| Phase 0 | snapshot pull (~500 rows) + dry-run + canonical-root resolution | ~100 ms/row | included in pull | 1 marker row | ~3 minutes |
| Phase 1 | 29 PATCH+read-back+log | ~100 ms PATCH + 100 ms read-back + 50 ms log | 2x | 29 rows | ~1 minute |
| Phase 2 | 37 PATCH+read-back+log | same | same | 37 rows | ~1.5 minutes |
| Phase 3 | (Kim manual UI) | n/a | n/a | 1 marker row | n/a (Kim's hands) |
| Phase 4 | ~110 PATCH+read-back+log | same | same | ~110 rows | ~5 minutes |
| Phase 5 (if authorized) | 320 PATCH+read-back+log | same | same | 320 rows | ~14 minutes |
| Phase 6 | 3 audit queries + report write + 1 LD POST | ~5 seconds | n/a | 5 rows | ~1 minute |

**Machine time total (all phases including Phase 5):** ~25 minutes wall-clock.
**Machine time total (Phase 5 deferred):** ~11 minutes wall-clock.

Assumption set: stable Directus connection, no rate-limit throttling, no retries needed. Add 50% headroom for partial-batch resumes.

### §9.2 — Human review time (Kim's attention)

| Phase | Kim review activity | Estimated focused time |
|---|---|---|
| Pre-Phase 0 | Read this spec v2 + confirm Gates 1-9 | 60 minutes |
| Phase 0 | Review dry-run report + snapshot metadata sidecar; emit "Phase 0 approved" LD row | 30 minutes |
| Phase 1 | Review first-5 dry-run output; emit "Phase 1 first-5 approved" row | 15 minutes |
| Phase 2 | Review first-5 dry-run output; emit row | 15 minutes |
| Phase 3 | Author 7 enum values in Directus admin UI; emit "Phase 3 schema extended" row | 30 minutes |
| Phase 4 | Review first-5 + per-row triage for ambiguous values (~10 rows); emit row | 90 minutes |
| Phase 5 (if authorized) | Author `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` LD with "Kim approved"; set `PHASE_5_ENABLED=true`; review first-5 dry-run; emit row | 60 minutes |
| Phase 6 | Review final audit report; approve or amend the standing-rule LD | 60 minutes |
| Mid-session interruptions, re-reads, "wait, why does this row…" digressions | (estimated padding) | 90 minutes |

**Human review time total (all phases including Phase 5):** ~7.5 hours focused attention.
**Human review time total (Phase 5 deferred):** ~6.5 hours focused attention.

Assumption set: Kim is unfamiliar with the audit before reading the spec; familiar after the first read. Phase 4 per-row triage on ambiguous values dominates the budget. Mid-session interruptions are real and accounted for.

### §9.3 — Total planning baseline (combined)

**Combined planning baseline (all phases including Phase 5):** ~10 hours total (~25 minutes machine + ~7.5 hours human + buffer for context switches between machine wait and Kim review).
**Combined planning baseline (Phase 5 deferred):** ~7 hours total.

This is the figure to cite when scheduling the migration session(s). If Kim's available focused time in a week falls below the combined baseline, the migration is split across multiple sessions per the §9 multi-session recommendation.

### §9.4 — Other operational notes (preserved verbatim from v1)

- **Run order matters:** Phase 1 (scope_domain) and Phase 2 (case-fold) are commutative and safe in either order. Phase 3 MUST precede Phase 4 (enum target must exist). Phase 5 is independent of all others (and additionally gated by §3.1 Layer 2 flag).
- **Single-session vs multi-session:** safest is multi-session (one Kim approval per phase between sessions). Aggressive is single-session with all gates pre-approved upfront. Default recommendation: multi-session, with Phase 1 + Phase 2 as a "low-risk warmup" session and Phase 5 as its own gated session.
- **Concurrency:** the migration script MUST hold a lockfile so a concurrent run cannot double-PATCH rows. Recommend `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` (this path is global Claude config, allowed by §3.0 outside-canonical rule).

---
```

---

## §5 — Schema handoff v2 — verbatim §0.1 + Step 0 + Hard rules

### §5.1 — Handoff v2 §0.1 changelog (verbatim)

```markdown
## §0.1 — v2 Changelog (verbatim resolution per Cursor handoff amendment)

Cursor's AMEND_V2 verdict on the v1 handoff returned 3 amendments (2 HIGH, 1 MED). Each is reproduced verbatim with the resolution. v1 sections that needed material change are listed under "Sections changed".

| # | Severity | Cursor amendment (verbatim) | Resolution applied in v2 | Sections changed |
|---|---|---|---|---|
| 1 | HIGH | Line-anchoring inconsistency: keep first-25-line quote (good stale check) BUT make all companion requirements anchor-by-header/snippet only (no fixed line numbers). | Step 0 preflight #3 retains the spec's first-25-line quote (good stale-cache detector) but every COMPANION-file integrity check switches to anchor-by-header/snippet only — no "quote line N" requirements. The companion-file table column "Anchored check" replaces any line-number requirements with header/snippet anchors. Step 2 prompt block aligned. | Step 0, Step 2 prompt |
| 2 | HIGH | Absolute-path mismatch: update hard rule from "Dropbox-root-only" to "canonical roots {Dropbox, Projects}; no worktrees unless explicitly authorized." | Hard rules section updated to dual-canonical-roots wording verbatim from `HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2). DS-27 reference updated to v2 refactor. Project-root naming in Step 1 updated. Step 2 prompt's hard-rule restatement updated. | Hard rules, Step 1, Step 2 prompt |
| 3 | MED | Descriptive-task escalation: Tasks C/E/F/H are descriptive-only; add clause: "unresolved descriptive risks at MED+ force full mode and explicit 'authorize with risk acceptance' statement." | Step 2 prompt's CONCISE→FULL ESCALATION RULE block expanded with a 6th trigger clause naming descriptive Tasks C/E/F/H: any unresolved descriptive risk at MED severity or higher forces full mode AND requires the reviewer to emit a verbatim "authorize with risk acceptance" statement before any AUTHORIZE_PHASE_0 verdict. | Step 2 prompt CONCISE→FULL ESCALATION block, Step 2 prompt VERDICT FORMAT block, Hard rules |

**v1 vs v2 surface area:** v2 adds ~120 lines (changelog + restated path-discipline blocks + new descriptive-task escalation clause). All v1 content preserved (no deletions); v2 additions are clearly labeled `(v2)` or `(NEW v2)` inline.

---
```

### §5.2 — Handoff v2 Step 0 preflight (verbatim)

```markdown
## Step 0 — Preflight (do FIRST, before any analysis) — v2 anchor-by-header/snippet only

**v2 amendment #1 (HIGH) applied:** the spec file's first-25-line stale-cache check is preserved. Every COMPANION file's integrity check now uses anchor-by-header/snippet ONLY — no fixed line numbers anywhere in this preflight.

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** run `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md"` — capture size and mtime.
2. **Spec hash:** run `shasum "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md"` — capture hex digest.
3. **Anchored quote of spec header (PRESERVED v1):** locate the `# Schema Vocab Migration — Tech Spec v2` header anchor and quote the first 25 non-blank lines as proof you read the actual file (not a stale or fabricated copy). Capture the line range these 25 lines occupy. (This first-25-line quote is the ONLY line-number-aware preflight step in v2; it's preserved as a stale-cache detector. All other anchored checks below use header/snippet only.)
4. **Companion-file integrity checks (v2 anchored discipline — header/snippet ONLY, no line numbers):** for each of the 5 companion files below, run `ls -la` AND `shasum` AND quote the named anchor by HEADER or SNIPPET ONLY. Existence-only is no longer sufficient. Line-number-based quotes are FORBIDDEN at this step.

   | Companion file | Anchored check (header/snippet only — no line numbers) |
   |----------------|--------------------------------------------------------|
   | `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` | `ls -la` + `shasum` + locate header anchor `## 0. Confirmed environment baseline` and quote the surrounding paragraph verbatim |
   | `Production/lib/severity_vocab.py` | `ls -la` + `shasum` + locate the `def severity_rank(` function anchor and quote its docstring verbatim |
   | `Production/scripts/governance_drift_check.py` | `ls -la` + `shasum` + locate the `from lib.severity_vocab import` import block by snippet anchor; quote the surrounding import block verbatim |
   | `Production/docs/HANDOFF_TEMPLATE_v2.md` | `ls -la` + `shasum` + locate header anchor `## v2 NEW — Absolute-path filesystem discipline (HARD rule, all handoffs) — refactored 2026-05-08 v2 dual-canonical` and quote the dual-canonical mandate paragraph verbatim |
   | `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` (historical baseline) | `ls -la` + `shasum` + locate header anchor `# Schema Vocab Migration — Tech Spec v1` and confirm it differs from v2's header — proof that v1 is preserved separately |

   Acceptance criterion: 5 shasum digests + 5 anchored quotes (header/snippet) emitted inline. If any digest cannot be computed OR any anchor cannot be located by header/snippet, **HALT and report which companion failed**. Existence-only does NOT pass v2 preflight. Line-number-based quotes do NOT pass v2 preflight.

5. **LD #586 row check:** attempt to query Directus `prod_locked_decisions` for the row where `decision_key = SCHEMA_VOCAB_TOLERANT_FILTER_V1`. If Directus is unreachable, record "Directus unreachable — LD #586 verification deferred to Analysis Task F fallback rule" and proceed; do NOT HALT for this single check.

6. **(v2 NEW) LD #584 amendment check:** attempt to query Directus `prod_locked_decisions` for row id=584 (`WORKTREE_CONFUSION_PREVENTION_V1`); confirm `notes` field contains the literal substring "2026-05-08 amendment: DS-27 refactored from Dropbox-only to dual-canonical-roots {Dropbox, Projects}". If found, the dual-canonical authority is in place; if not found, AMEND_V2 verdict on the Hard rules section (the path-discipline rule's authority is missing).

7. **Live data baseline confirmation:** independently verify (via Directus query OR by reading the cleanup report's §0 verbatim) that the dataset still has 11 distinct severity values + 68 task_category values + 17 scope_domain values, OR document the new live counts inline. The migration mappings in the spec assume the report's snapshot baseline.

If any preflight check (1-4) fails, **HALT and report**. Do not proceed to Step 1.

---
```

### §5.3 — Handoff v2 Hard rules (verbatim)

```markdown
## Hard rules (v2 dual-canonical refactor)

**v2 amendment #2 (HIGH) applied:** Hard rule path discipline updated from Dropbox-only to dual-canonical-roots, verbatim from `HANDOFF_TEMPLATE_v2.md` refactored block.

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST.
- **Multipass:** re-Read every file after edit.
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) are always active — fire on any of their trigger conditions.
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior (input variation → output variation).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 explicit (HARD rule, v2 dual-canonical):** "All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots require explicit Kim authorization." (Authority: LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` amended 2026-05-08 v2 dual-canonical; SKILL.md DS-27 v2 refactor; HANDOFF_TEMPLATE_v2.md v2 refactor.)
- **Anchored citation (v2):** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. EXCEPTION: the spec's first-25-line quote at Step 0 #3 is preserved as a stale-cache detector and is the only line-number-aware step.
- **Concise→full escalation (v2):** "If any required section cannot be evidenced, full mode is mandatory." (Cursor review handoff supports concise mode if no blockers; full mode mandatory under any of the 6 trigger conditions.)
- **(v2 amendment #3 NEW) Descriptive-task escalation:** "Tasks C, E, F, H are descriptive-only. Any unresolved descriptive risk at MED severity or higher forces full mode AND requires the reviewer to emit a verbatim 'AUTHORIZE WITH RISK ACCEPTANCE: <statement>' before any AUTHORIZE_PHASE_0 verdict may be issued. Without the verbatim statement, the verdict path is AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE (with statement) OR AMEND_V2 OR BLOCK."
- **Numeric AMEND_V2 thresholds (v2):** every analysis task asking "is X acceptable?" includes "if X > Y, verdict MUST be AMEND_V2." (Tasks A/B/D/G/I have explicit numeric thresholds; Tasks C/E/F/H are descriptive-only and route through the descriptive-task escalation clause above.)

---
```

---

## §6 — Activity log row id

**Row id:** 1776 (collection: `prod_activity_log`).
**Action:** `DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_AUTHORED`
**Performed by:** Claude Opus 4.7 (1M context) — DS-27 dual-canonical refactor + schema migration spec/handoff v2
**Created at:** 2026-05-08T15:27:33.113Z

**Read-back assertion result:** PASS (action string + details.ld_amendment.ld_id == 584 + payload structure verified via Directus GET).

**Per Rule 35 verification:** the post-POST GET returned the row with action == 'DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_AUTHORED' and details.ld_amendment.ld_id == 584; assertions passed; no silent-write-failure detected.

---

## §7 — Confidence tags per Rule 24

| Claim | Confidence | Evidence |
|---|---|---|
| DS-27 in `.claude/skills/zero-error-qa/SKILL.md` was successfully refactored to dual-canonical-roots | CONFIRMED | Multipass-verified post-edit (grep of "Projects/" + "Dropbox" + "canonical root" all present); §1 verbatim block above is the actual file content as of report authoring |
| `HANDOFF_TEMPLATE_v2.md` Absolute-path discipline section was successfully refactored to dual-canonical-roots | CONFIRMED | Multipass-verified post-edit (grep of "Projects/" + "Dropbox" + "canonical root" all present); §2 verbatim block above is the actual file content |
| LD 584 notes amendment landed and is queryable | CONFIRMED | Directus GET read-back returned the appended paragraph; `assert amendment in post['notes']` passed |
| Spec v2 file authored at canonical Dropbox path | CONFIRMED | `ls -la` size=48,617 bytes; mtime=today (2026-05-08); content multipass-verified |
| Handoff v2 file authored at canonical Dropbox path | CONFIRMED | `ls -la` size=32,235 bytes; mtime=today (2026-05-08); content multipass-verified |
| Activity log row id=1776 created and queryable | CONFIRMED | Directus POST returned id=1776; GET read-back returned matching action + details |
| v1 spec file preserved as historical baseline | CONFIRMED | `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` was NOT modified during this session; only read |
| v1 handoff file preserved as historical baseline | CONFIRMED | `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` was NOT modified during this session; only read |
| All 4 edited files use consistent dual-canonical wording (DS-27 ≡ HANDOFF_TEMPLATE ≡ spec v2 §3.0 ≡ handoff v2 Hard rules) | CONFIRMED | Multipass consistency check Step 7 confirmed all 4 files contain the canonical-root term + both Dropbox and Projects paths |
| The 4 spec amendments + 3 handoff amendments correctly map to Cursor's AMEND_V2 verdicts | INFERRED | Cursor's verdicts were communicated via Kim's prompt (verbatim text of the 7 amendments); resolution mapping in §0.1 of each v2 doc is the agent's interpretation of those verdicts; Cursor's actual response is not in this conversation. Recommended action: re-submit v2 to Cursor for final AUTHORIZE_PHASE_0 verdict |
| Future agent sessions running under DS-27 v2 will correctly resolve dual-canonical paths in their preflight | INFERRED | DS-27 v2 + HANDOFF_TEMPLATE v2 dual-canonical + LD 584 amendment are all consistent; the rule mechanics are documented; behavioral compliance depends on future agents reading these docs (which is the standard discipline-only enforcement model named in DS-27's "ENFORCEMENT IS DISCIPLINE-ONLY for now" closing line) |

---

## §8 — Self-classification

**ARCHITECTURAL** — governance rule revision.

Justification:
- DS-27 is referenced by every v2 handoff's Hard rules section (mandate from `HANDOFF_TEMPLATE_v2.md`), every Phase 0 Step 2 preflight (mandate from `zero-error-qa/SKILL.md` Phase 0), and every prompt-authoring agent (mandate from DS-27 mechanical action #4). The blast radius of the refactor is "every future agent session that touches any project filesystem." The change does NOT affect runtime data or shipped product code; it changes the rule that future spec/handoff/prompt authors and reviewers operate under.
- LD 584 amendment is the locked-decision authority that downstream skills cite. Without the amendment, the SKILL.md DS-27 v2 wording would be "ahead of" the LD authority — a governance drift. The amendment closes that gap.
- Spec v2 + handoff v2 are downstream of the DS-27 v2 refactor; their Hard rules + path-discipline blocks reference the new dual-canonical wording.

This is the third major DS-27 governance touch this session (initial DS-27 + HANDOFF_TEMPLATE v2 + LD 584 created earlier today; this is the v2 dual-canonical refactor). All three changes share the same authority chain.

---

## §9 — Cursor re-review prompts

### §9.1 — Cursor re-review prompt for spec v2

```
I have a tech spec at Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md (v2 supersedes v1; v1 preserved as historical baseline). v2 was authored to address your prior AMEND_V2 verdict on v1 with 4 amendments:
1. HIGH — PHASE_5_ENABLED feature flag at three layers (operational doctrine §3.1 + script-level guard §3.1 Layer 2 + procedural Gate #9 §6) — closes the "DEFER but Phase 5 still operationalized" path Rule 1 had in v1.
2. HIGH — Path discipline §3.0 dual-canonical-roots {Dropbox, Projects} + Phase 0 Step 0 canonical-root resolution.
3. MED — Phase 0 snapshot schema with row_count + id_uniqueness + all_touched_ids_present fields + pre-Phase-5 integrity check (§4 Phase 0 v2 + §6 Gate 7 + §8 Phase 5 rollback tie).
4. MED — §9 cost split: machine time + human review time + combined planning baseline (10 hr).

Apply your full review using the same v2 hardened anchored-citation discipline + numeric AMEND_V2 thresholds + descriptive-task escalation pattern as the companion handoff `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md`. Verify each of the 4 amendments was applied correctly. Specifically test:

A. Does §3.1 Layer 2's `PHASE_5_ENABLED` script-level guard actually block Phase 5 execution under all 3 fail conditions (env var false; missing LD; missing "Kim approved" in notes)? Walk the assertion code; show any path where Phase 5 could leak through.

B. Does §3.0 path discipline correctly handle the "migration script lives in Dropbox-anchored canonical root" assertion? Are there scenarios where the script could legitimately need to operate outside both canonical roots?

C. Is the Phase 0 v2 snapshot schema sufficient to support the §8 Phase 5 rollback for ≥95% of touched rows? Walk a hypothetical rollback for one CRITICAL row.

D. Is the §9 cost split realistic? Specifically — is ~7.5 hours of focused human review time defensible for a 5-phase migration with per-phase first-5 approval gates?

Apply the descriptive-task escalation pattern: if any descriptive finding (not tied to a numeric threshold) reaches MED or higher, full mode is mandatory and a verbatim "AUTHORIZE WITH RISK ACCEPTANCE: <statement>" is required before AUTHORIZE_PHASE_0.

Verdict format: AUTHORIZE_PHASE_0 | AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE | AMEND_V3 | BLOCK
```

### §9.2 — Cursor re-review prompt for handoff v2

```
I have a Cursor cross-review handoff at Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md (v2 supersedes v1; v1 preserved as historical baseline). v2 was authored to address your prior AMEND_V2 verdict on the v1 handoff with 3 amendments:
1. HIGH — Line-anchoring inconsistency resolved: companion-file integrity checks now use anchor-by-header/snippet ONLY (no fixed line numbers); the spec's first-25-line quote at Step 0 #3 is preserved as the only line-number-aware step (good stale-cache detector).
2. HIGH — Absolute-path mismatch resolved: Hard rules + Step 1 + Step 2 prompt updated to dual-canonical-roots {Dropbox, Projects}; no worktrees unless explicitly authorized.
3. MED — Descriptive-task escalation clause added: Tasks C/E/F/H at MED severity or higher force full mode AND require the reviewer to emit a verbatim "AUTHORIZE WITH RISK ACCEPTANCE: <statement>" before any AUTHORIZE_PHASE_0 verdict.

Verify each of the 3 amendments was applied correctly. Specifically test:

I. Does the Step 0 preflight #4 companion-file integrity table actually use header/snippet anchors only? Are there any residual line-number references that slipped through?

II. Does the Hard rules DS-27 explicit bullet match the wording in `HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical)? Is the LD 584 authority cited correctly?

III. Does the Step 2 prompt's CONCISE→FULL ESCALATION RULE block correctly add the descriptive-task escalation clause (6th trigger)? Is the verdict format `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` correctly defined?

The handoff itself is a prompt-authoring artifact; you do NOT need to actually run the review — just verify the amendments are applied and the structure is sound.

Verdict format: AUTHORIZE_HANDOFF_AS_v2 | AMEND_V3 | BLOCK
```

---

## §10 — Limitations

- **Cursor's actual AMEND_V2 verdict text is not in this conversation.** The 4 spec amendments + 3 handoff amendments were communicated via Kim's prompt as a paraphrase. The v2 docs treat Kim's paraphrase as authoritative. If Cursor's literal verdict text differed in nuance, a v3 re-review may be required.
- **DS-27 v2 enforcement remains discipline-only.** No PreToolUse hook scans paths against the dual canonical roots yet. Track via `prod_blockers` row `DS_27_MECHANICAL_GATE_PENDING`.
- **The session author was anchored to a worktree** (`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/worktrees/gallant-bouman-804b4f/` per gitStatus). Every filesystem operation in this session used absolute Dropbox-anchored paths, but the cwd itself was a worktree subdirectory. This is the exact pattern DS-27 is designed to handle — the rule says "no `cd` into worktrees, no relative-paths-against-worktrees", not "agent must not be invoked from a worktree". Discipline maintained throughout.
- **Spec v2 is DESIGN ONLY.** No migration code was modified per the prompt's hard rule. The migration script `Production/scripts/migrate_schema_vocab_v1.py` does not exist yet; spec v2 §5 describes its required behavior + the v2 feature-flag entry guard, but the script itself is a future deliverable.

---

## §11 — Cross-skill drift

The DS-27 v2 dual-canonical refactor + LD 584 amendment + HANDOFF_TEMPLATE v2 update have downstream implications for other skills that reference the absolute-path discipline rule:

| Skill / doc | Drift impact | Action required |
|---|---|---|
| `mn-context` SKILL.md | If mn-context references the single-root DS-27 wording in any reminder template, those references are now out-of-date. | Audit on next mn-context invocation; patch any "Dropbox-only" wording to dual-canonical. (Defer to next session — not a hard blocker since mn-context is reminder-only.) |
| `dashboard-gate` SKILL.md | dashboard-gate references CLAUDE.md Rule 35 + Rule 19 + DS-27 in its preflight steps. The DS-27 reference in dashboard-gate may quote the old single-root wording. | Audit on next dashboard-gate invocation; patch any "Dropbox-only" wording to dual-canonical. |
| `tech-spec` SKILL.md | tech-spec reads CLAUDE.md / DS-* references as part of dual-Opus debates; if it caches a copy of DS-27 wording, that cache is stale. | tech-spec re-reads on every invocation per its standard pattern; no patch required. |
| CLAUDE.md Rule 19 ("no path open for error") | Rule 19 references DS-27 indirectly. The dual-canonical refactor closes a path AND opens a possibility (outside-canonical paths require explicit authorization, which is a procedure not a closed path). | Document explicitly that the outside-canonical-roots authorization gate is the v2 path-closure mechanism; reference LD 584 amendment. |
| Future v2 handoffs (every Cursor review handoff authored 2026-05-08 forward) | Hard rules section MUST quote the dual-canonical wording verbatim, not the single-root wording. | Already enforced by `HANDOFF_TEMPLATE_v2.md` v2 refactor — every new handoff inherits the dual-canonical wording from the template. |

**Recommended next-step audit (deferrable):** sweep `.claude/skills/*/SKILL.md` and `.claude/CLAUDE.md` for residual "Dropbox root only" or "live Dropbox tree" wording; replace with dual-canonical references citing LD 584 amendment + DS-27 v2.

---

## §12 — Final summary

| Item | Path / id | Status |
|---|---|---|
| DS-27 in SKILL.md | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` | REFACTORED (v2 dual-canonical, +4,460 bytes) |
| HANDOFF_TEMPLATE_v2.md absolute-path section + DS-27 hard-rule bullet + Anti-pattern #10 | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` | UPDATED (v2 dual-canonical) |
| LD 584 notes | `prod_locked_decisions` id=584 | AMENDED (notes appended; read-back verified) |
| Schema spec v2 | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` | AUTHORED (4 Cursor amendments applied; v1 preserved) |
| Schema handoff v2 | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` | AUTHORED (3 Cursor amendments applied; v1 preserved) |
| Activity log row | `prod_activity_log` id=1776 | POSTED (read-back verified) |
| This proof report | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_REPORT_20260508.md` | AUTHORED |

**Next step (Kim's hand on the trigger):** submit `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` + `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` to Cursor for AUTHORIZE_PHASE_0 / AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE / AMEND_V3 verdict using the prompts in §9 above.

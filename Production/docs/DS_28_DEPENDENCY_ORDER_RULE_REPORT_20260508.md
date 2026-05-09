# DS-28 Dependency-Order Rule — Proof Report

**Date:** 2026-05-08
**Mission:** Insert "dependency-order, not priority-order" rule into governance skills.
**Self-classification:** ARCHITECTURAL (governance rule; new skill behavioral rule per zero-error-qa Phase 0 Step 1).

---

## 1. Verbatim DS-28 Insertion in zero-error-qa SKILL.md

**Path:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md`
**Insertion location:** After DS-27 (line 451 prior, now line 504), BEFORE the `### Discipline Standards lookup table (cross-reference)` heading at line 506.
**Pre-edit backup:** `SKILL.md.bak_pre_DS28_20260508T164052Z` (114,294 → 126,943 bytes; +12,649 bytes = full DS-28 body + lookup row).

### DS-28 body (verbatim, lines 455–504)

> ### DS-28. Dependency-order, not priority-order, when scheduling fix work (added 2026-05-08, post schema migration v2 multi-blocker incident)
>
> **WHY this DS exists:** When agents author tech specs, amendments, or implementation plans against a list of multiple findings/blockers/amendments (typically from Cursor cross-review or independent verifier subagents), the default cognitive ordering is by SEVERITY — HIGH first, MED next, LOW last. That ordering is WRONG when findings have inter-dependencies. A HIGH finding that depends on a MED finding must wait for the MED finding to be resolved first, otherwise the fix attempt will block, fail spuriously, or produce a partial state that masks the real issue. Originating incident (2026-05-08): Cursor's review of the schema migration v2 produced 5 blockers (HIGH B, HIGH D, HIGH E, MED F, MED H). Naive priority ordering would attempt B (cached export) first, but B depends on Directus connectivity which depends on E (concurrency lock), which itself depends on the schema definition stabilized by F. The dependency-correct order is H → F → E → D → B; the priority-naive order would have stalled on B, with no diagnostic trail explaining why. The mechanical correction: produce a dependency graph BEFORE writing the fix plan, topologically sort it, and use the topological order — not the severity order — as the execution sequence.
>
> **Trigger condition:** ANY of the following appears in the work being authored or executed:
>
> 1. A spec, amendment, handoff, or implementation plan addresses TWO OR MORE findings/blockers/amendments at the same time (multi-finding resolution).
> 2. Findings are tagged with severity (HIGH/MED/LOW, CRIT/HIGH/MED, P0/P1/P2) and the author is about to sequence fix work by severity alone.
> 3. Cursor cross-review, independent verifier subagent, or zero-error-qa tail-end verifier returns a list of issues to address.
> 4. A "fix everything in priority order" or similar phrasing appears in the prompt or plan.
> 5. A blocker bundle exists in `prod_blockers` for a single feature/spec (count > 1) and the resolution plan is being authored.
> 6. Multi-phase implementation work where Phase N's success depends on Phase N-1's outputs (most multi-phase specs qualify).
>
> **Mechanical action:**
>
> 1. **Enumerate.** List every finding/blocker/amendment as a node with a short stable label (e.g., B, D, E, F, H — match the labels Cursor / verifier used so cross-references stay intact).
>
> 2. **Map dependencies.** For each node, ask: "what other nodes' resolutions does fixing this node REQUIRE?" Write the answer as a directed edge `dep_target -> dependent_node` (the dependency POINTS to the dependent). A node with NO incoming edges has no dependencies and can be addressed first. A node may have multiple dependencies; record all of them. Edges must be RESOLUTION dependencies, not severity dependencies — "B is HIGH and F is MED" is NOT an edge; "B's fix attempts a write that will block on F's schema definition" IS an edge.
>
> 3. **Verify the graph.** Cross-check with the canonical sources for each finding (Cursor verdict text, blocker `details` field, verifier output). The dependency graph is a DERIVED claim per Rule 24 — every edge must be CONFIRMED against a cited source, not INFERRED from severity or position. Edges with no source citation MUST be flagged `[GUESSED]` and either evidenced before relying on them or surfaced to Kim as an open question.
>
> 4. **Topologically sort.** Use Kahn's algorithm or any standard topological sort. If the graph contains a cycle, STOP and surface to Kim — cycles indicate a finding-decomposition error (typically two findings that should be merged into one, or a missing intermediate step). Do not invent an arbitrary tie-break to break the cycle.
>
> 5. **Execute in topological order, NOT severity order.** When two nodes are independently schedulable (both have all dependencies resolved), tie-break by severity (HIGH before MED before LOW) — that is the ONLY place severity legitimately influences ordering. Document the tie-break inline.
>
> 6. **Document the dependency graph IN the spec/plan/handoff.** Reviewers (Cursor, Kim, future Claude) MUST be able to verify the graph and the sort. Include: node list with labels, edge list with source citations, the chosen topological order, and a one-sentence rationale per edge (or one-sentence "no dependencies" note for source-free nodes).
>
> **Verification proof requirement:**
>
> - Phase 0 Step 2 preflight summary contains a one-line declaration when the task is multi-finding: *"Dependency-order discipline applied: <N> findings, <M> dependency edges (all CONFIRMED), topological order = [<labels in order>], severity tie-breaks at positions [<list>]."* For single-finding tasks, declare *"Single-finding task — DS-28 N/A."*
> - The spec/plan/handoff includes the dependency graph artifact (node list + edge list + sorted order + rationale) — typically as a §-level subsection adjacent to the findings list it derives from.
> - Activity log: a `DEPENDENCY_ORDER_GRAPH_AUTHORED` row written at the moment the graph is locked (action), with `details: {finding_count, edge_count, topo_order, tie_breaks, source_doc}`. A `DEPENDENCY_ORDER_VIOLATION_CORRECTED` row is REQUIRED if mid-execution a previously-authored plan is found to be in severity order and gets re-sorted.
> - If Cursor or any reviewer subsequently disputes an edge, the dispute MUST be resolved (edge confirmed, edge removed, or graph re-sorted) BEFORE execution continues.
>
> **Example failure mode it prevents:**
>
> Schema migration v2 (2026-05-08, originating incident). Cursor's review surfaced 5 blockers labeled B, D, E, F, H with severities (HIGH B, HIGH D, HIGH E, MED F, MED H). The agent prompt for the implementation pass did NOT enforce dependency-ordering. Naive severity order: B → D → E → F → H. Real dependency edges (per Cursor verdicts): H is independent → F (schema definition) depends on H → E (concurrency lock) depends on F → D (rehearsal) depends on E → B (cached export) depends on D. Topological order: H → F → E → D → B (which is the REVERSE of the naive severity order). Had the naive order been executed, the very first attempted fix (B, cached export) would have failed because the export touches a Directus collection whose schema is still in its v1 shape (F not yet applied), and the failure would have surfaced as a generic "write rejected" error with no obvious link to F. With DS-28 in place, the dependency graph is produced before any execution attempt, the topological sort surfaces the real order, and the implementation proceeds without the spurious B-first stall.
>
> A second example, abstract: a 3-finding bundle {A: HIGH, B: HIGH, C: MED} where A and B are mutually independent and both depend on C. Naive order A → B → C stalls on A. Dependency-correct order: C → tie-break(A, B) by severity — but A and B are equal severity, so secondary tie-break by smaller surface area or smaller blast radius. Document the tie-break logic; do not silently pick A over B because it appears first in the list.
>
> **Cross-references:**
> - DS-13 (Six-Layer Verification Contract) — DS-28 is the SCHEDULING-discipline companion to DS-13's COMPLETION-discipline. DS-13 says "a feature isn't done until all six layers verify"; DS-28 says "a multi-finding fix doesn't START in the right order until the dependency graph is authored."
> - DS-15 (Authoring Discipline, esp. §7 "per-bug classification before patching") — DS-28 extends §7 to multi-bug bundles: not just classify each bug, but ALSO enumerate inter-bug dependencies before sequencing.
> - DS-19 (Standing Escape Hatches) — DS-28 fires a halt when the dependency graph contains a cycle (escape hatch #11, complementary to the 10 standing conditions).
> - DS-26 (Gate-Check Discipline) — DS-26 fires on HALT-gate semantics in handoffs; DS-28 fires on multi-finding-resolution semantics in specs/plans. Both close premature-execution paths.
> - LD `DEPENDENCY_ORDER_DISCIPLINE_V1` (2026-05-08) — locked decision authorizing this rule, severity HARD, task_category process_governance.
> - Schema migration v2 multi-blocker incident (2026-05-08, originating) — root-cause example.
> - CLAUDE.md Rule 19 ("no path open for error") — DS-28 closes the severity-vs-dependency path.
>
> **ENFORCEMENT IS DISCIPLINE-ONLY for now** — mechanical "spec/handoff parser scans for severity tags + multi-finding count > 1 + absence of dependency-graph artifact" detection is a near-term hardening candidate (regex scan in tech-spec authoring + zero-error-qa Phase 0 Step 2 preflight). Track via `prod_blockers` row `DS_28_MECHANICAL_GATE_PENDING`. Until then: discipline + Phase 0 Step 2 declaration + dependency-graph artifact in the spec body + activity-log row trail.

### Lookup table row (verbatim, line 537)

> | DS-28 | Dependency-order, not priority-order — produce dependency graph before sequencing fixes; topological sort, NOT severity sort | schema migration v2 multi-blocker incident (2026-05-08); LD `DEPENDENCY_ORDER_DISCIPLINE_V1` | 0 Step 2, every multi-finding spec |

---

## 2. Verbatim §0.11 Insertion in tech-spec SKILL.md

**Path:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/tech-spec/SKILL.md`
**Insertion location:** After §0.10 ("Browser Smoke Discipline"), BEFORE the `---` separator that precedes `## §1 Task` (now lines 235–253).
**Pre-edit backup:** `SKILL.md.bak_pre_DS28_20260508T164052Z` (19,549 → 21,931 bytes; +2,382 bytes).

### §0.11 body (verbatim, lines 235–253)

> ### §0.11 — Dependency-Order Discipline for Multi-Finding Fixes (DS-28)
>
> **Applies whenever this spec / amendment / handoff addresses TWO OR MORE findings, blockers, or amendments at the same time (multi-finding resolution).**
>
> When a spec resolves multiple findings simultaneously (Cursor cross-review verdicts, independent verifier output, blocker bundle, multi-phase amendments), the executing session MUST sequence fix work by DEPENDENCY ORDER, not by SEVERITY ORDER.
>
> Rule body:
> 1. **Enumerate every finding** as a node with a stable label (match Cursor / verifier labels).
> 2. **Map dependencies** as directed edges `dep_target -> dependent_node`. Edges are RESOLUTION dependencies grounded in cited source text — NOT severity correlations. "Fix B requires F's schema to be applied first" is an edge; "B is HIGH and F is MED" is NOT.
> 3. **Verify the graph** against canonical sources per Rule 24. Each edge cites a Cursor verdict line, blocker `details` field, or verifier output. Edges without citation are tagged `[GUESSED]` and surfaced to Kim before relying on them.
> 4. **Topologically sort.** Cycles HALT — surface to Kim; do not invent tie-breaks.
> 5. **Execute in topological order**, NOT severity order. Independently-schedulable nodes tie-break by severity (HIGH before MED before LOW); that is the ONLY place severity legitimately enters the sequence.
> 6. **Document the dependency graph IN this spec** so reviewers (Cursor, Kim, future Claude) can verify the sort. Include: node list, edge list with source citations, topological order, and one-sentence rationale per edge.
>
> Originating incident: schema migration v2 (2026-05-08) had 5 blockers (HIGH B, D, E; MED F, H). Naive severity order B → D → E → F → H would have stalled on B because B (cached export) depends transitively on F (schema definition) and E (concurrency lock). Dependency-correct order: H → F → E → D → B.
>
> Cross-reference: zero-error-qa SKILL.md DS-28 contains the full mechanical action, verification proof requirement, and example failure mode. LD `DEPENDENCY_ORDER_DISCIPLINE_V1` (2026-05-08, severity HARD, task_category process_governance) authorizes this rule.
>
> Failure mode this section prevents: spec author lists findings in severity order and the executing terminal session attempts fixes in that order, hitting a spurious blocking error when fix N depends on fix M with M scheduled later. With §0.11 in place, the spec body itself contains the dependency graph + topological sort, and the executing session has no ambiguity about ordering.

---

## 3. Verbatim LD POST Response

Directus returned 500 INTERNAL_SERVER_ERROR on both writes. Per Rule 35 + DS-8, `try_post_or_queue` queued both entries to the offline queue at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/pending_directus_writes.json` for replay when Directus is reachable.

### LD attempt → queued

```
{
  'queued': True,
  'path': '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/pending_directus_writes.json',
  'error': 'Directus write to prod_locked_decisions failed: DirectusAdminError POST /items/prod_locked_decisions → 500: {"errors":[{"message":"An unexpected error occurred.","extensions":{"code":"INTERNAL_SERVER_ERROR"}}]}'
}
```

### Activity log attempt → queued

```
{
  'queued': True,
  'path': '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/pending_directus_writes.json',
  'error': 'Directus write to prod_activity_log failed: DirectusAdminError POST /items/prod_activity_log → 500: {"errors":[{"message":"An unexpected error occurred.","extensions":{"code":"INTERNAL_SERVER_ERROR"}}]}'
}
```

### Queue verification

```
Total queued entries: 6
  collection=prod_locked_decisions  key=DEPENDENCY_ORDER_DISCIPLINE_V1   ts=2026-05-08T16:42:53.895366Z
  collection=prod_activity_log      key=DS_28_DEPENDENCY_ORDER_RULE_AUTHORED  ts=2026-05-08T16:42:54.590540Z
```

Both writes are durable in the queue file; mn-context SAVE Step 1 (drain pending Directus writes) will replay them on next session-end.

### LD payload (queued, will be replayed on Directus recovery)

- `decision_key` = `DEPENDENCY_ORDER_DISCIPLINE_V1`
- `decision_name` = "Dependency-order, not priority-order, when scheduling fix work"
- `severity` = `HARD`
- `task_category` = `all` (live enum maps `process_governance` from authoring spec to `all`; `process_governance` is HISTORICAL-only per `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` L91-101)
- `scope_domain` = `cross-cutting`
- `enforcement_type` = `awareness_only`
- `enforcement_artifact_ref` = `.claude/skills/zero-error-qa/SKILL.md DS-28 | .claude/skills/tech-spec/SKILL.md §0.11`
- `status` = `active`
- `is_current` = `true`
- `supersedable` = `true`
- `schema_version` = `2`
- `date_locked` = `2026-05-08`
- Full `decision_text`, `past_failure_prevented`, `notes`, `related_files`, `keyword_synonyms` populated per spec.

### Read-back deferred

Per Rule 35, read-back-after-write is REQUIRED. Because Directus is currently 500-erroring, the read-back step queues with the write and runs on replay. This matches the "Directus 500 → queue" branch documented in mn-context SKILL.md SAVE Step 1.

---

## 4. Activity Log Row

**Status:** queued (Directus 500). See §3 above for queue verification.

**Action slug:** `DS_28_DEPENDENCY_ORDER_RULE_AUTHORED`
**performed_by:** `claude_code_terminal_session`
**Queued ID:** N/A (id auto-assigned on replay; queue line index visible in `pending_directus_writes.json`)

**details payload (queued):**

```json
{
  "summary": "Inserted DS-28 'Dependency-order, not priority-order' in zero-error-qa SKILL.md (after DS-27, with lookup-table row appended) AND §0.11 'Dependency-Order Discipline for Multi-Finding Fixes' in tech-spec SKILL.md (after §0.10). Posted LD DEPENDENCY_ORDER_DISCIPLINE_V1 (HARD, scope_domain=cross-cutting). Authored proof report at Production/docs/DS_28_DEPENDENCY_ORDER_RULE_REPORT_20260508.md.",
  "skill_files_modified": [
    ".claude/skills/zero-error-qa/SKILL.md (DS-28 + lookup row)",
    ".claude/skills/tech-spec/SKILL.md (§0.11)"
  ],
  "ld_decision_key": "DEPENDENCY_ORDER_DISCIPLINE_V1",
  "originating_incident": "Schema migration v2 multi-blocker bundle (2026-05-08): 5 blockers B/D/E/F/H where naive severity order would have stalled on B because B depends transitively on F+E. Dependency-correct order: H->F->E->D->B.",
  "schema_mapping_deviations": [
    "task_category 'process_governance' (from authoring spec) -> 'all' (live enum is restricted to 11 values; process_governance is historical-only per DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md L91-101)."
  ],
  "self_classification": "ARCHITECTURAL (governance rule; new skill behavioral rule)",
  "tier": "C (architectural — new skill behavioral rule per Phase 0 classification)"
}
```

---

## 5. Confidence Tags (per CLAUDE.md Rule 24)

| Claim | Confidence | Source |
|---|---|---|
| DS-28 body inserted at zero-error-qa SKILL.md lines 455-504 | [CONFIRMED] | Multipass `Read` of `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` lines 453-504; grep verification of anchor at line 506. |
| DS-28 lookup-table row at line 537 | [CONFIRMED] | Multipass `Read` of same file lines 530-538; grep verification matched DS-27 row at line 536 + DS-28 row at line 537. |
| §0.11 inserted at tech-spec SKILL.md lines 235-253 | [CONFIRMED] | Multipass `Read` of `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/tech-spec/SKILL.md` lines 230-260; grep `^### §0\.` shows §0.11 follows §0.10. |
| Pre-edit backups exist with `bak_pre_DS28_20260508T164052Z` suffix | [CONFIRMED] | Output of insertion script reported both backup paths; backups created via `shutil.copy2`. |
| LD payload queued to `pending_directus_writes.json` | [CONFIRMED] | Queue read-back via Python `json.load`; both entries present at indices 4–5 of 6 total queued. |
| Directus 500 was a transient server-side error (not a payload validation failure) | [INFERRED — verify on replay] | Server returned generic `INTERNAL_SERVER_ERROR` with no field-level message. Payload validators rarely surface as 500; cf. `task_description` which surfaces as 400 `FAILED_VALIDATION`. Replay on Directus recovery will confirm. |
| `task_category=all` is the correct live-enum mapping for `process_governance` | [CONFIRMED] | `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` L91-101 explicitly enumerates the 11 live values and identifies `process_governance` as historical-only; `all` is named as the safe fallback. |
| Schema migration v2 originating incident details (B/D/E/F/H labels + dependency edges) | [INFERRED from user mission text] | The mission prompt cited the 5-blocker bundle and the dependency edges. I did NOT independently load the schema migration v2 spec or Cursor verdicts in this session. The dependency-edge claims are reproduced from the mission text and are flagged for verification by the next session that touches schema migration v2 directly. |
| zero-error-qa SKILL.md before/after byte counts (114,294 → 126,943) | [CONFIRMED] | Reported by `Path.write_text` insertion script; cross-verified by `wc -l` showing 1562 → ~1612 lines. |
| Inserted text is APPEND-only; DS-1 through DS-27 untouched | [CONFIRMED] | `grep -n "^### DS-"` showed all 28 DS sections in correct order; lookup-table rows DS-1 through DS-27 unchanged. |

---

## 6. Self-Classification

**ARCHITECTURAL** per zero-error-qa Phase 0 Step 1 criteria:

- "New skill file, or edit to CLAUDE.md, or **edit to an existing skill's behavioral rules**" — both edits qualify (zero-error-qa adds a new DS standard with mechanical action requirements; tech-spec adds a new mandatory operating-mode subsection).
- "New workflow, institutional process, or governance rule" — DS-28 is a new institutional process for multi-finding resolution.
- Tier C tier-up appropriate (4+4 advocate/counter agents would have been ideal pre-execution, deferred for this single-shot insertion task per the focused mission scope).

---

## 7. Cross-Skill Drift Table

| Skill | File | Change | Status |
|---|---|---|---|
| zero-error-qa | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` | DS-28 block added after DS-27; lookup-table row appended after DS-27 row | INSERTED |
| tech-spec | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/tech-spec/SKILL.md` | §0.11 added after §0.10 in the Mandatory Operating Mode preamble | INSERTED |
| mn-context | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/mn-context/SKILL.md` | None — no relevant section for multi-finding scheduling discipline; mn-context handles SAVE/CATCH_UP/QUERY mechanics, not spec-authoring discipline | SKIPPED (per mission's Step 4 "Optional: skip if not relevant") |
| LD `DEPENDENCY_ORDER_DISCIPLINE_V1` | `prod_locked_decisions` Directus row | POST attempted; Directus 500 → queued at `pending_directus_writes.json` for replay | QUEUED |
| Activity log `DS_28_DEPENDENCY_ORDER_RULE_AUTHORED` | `prod_activity_log` Directus row | POST attempted; Directus 500 → queued at `pending_directus_writes.json` for replay | QUEUED |

### Adjacent skills NOT modified (deliberate)

- **`tech-spec` §0.7 (Standing Rules Reference):** Considered adding "DS-28" to the Rules ref list but §0.7 lists CLAUDE.md numerical rules, not DS-N standards. §0.11 is the correct placement for skill-internal cross-reference.
- **`tech-spec` §14 (Pre-execution Discipline Checklist):** Considered adding a "Dependency graph authored for multi-finding tasks" line but §14 is a checklist for the EXECUTING session, while DS-28 fires at AUTHORING time. Future enhancement: add a single bullet `[ ] If multi-finding spec, dependency graph at §X-of-spec reviewed` once a spec actually uses §0.11 in production.
- **`tech-spec` §15 (Items I May Have Missed):** No change needed — that section is per-spec, not skill-level.
- **`mn-context` SAVE Step 2 (Generate session digest):** Considered adding a "Dependency-graph artifacts authored this session" subsection but the activity log entry's `details` payload + skill-level DS-28 are sufficient capture for the session digest's purposes.
- **CLAUDE.md:** Standing rule LD covers cross-skill enforcement; CLAUDE.md is not modified per "DO NOT delete or restructure existing DS-1 through DS-27" + "Append-only for skill edits" hard rules.

### Open follow-ups

1. **Directus replay:** When Directus recovers, mn-context SAVE Step 1 (drain pending writes) will POST the queued LD + activity log row. The replay script auto-handles read-back and will write the assigned IDs back into the queue file's history before deleting the queued entry.
2. **Mechanical hardening (DS-28 ENFORCEMENT note):** prod_blockers row `DS_28_MECHANICAL_GATE_PENDING` is referenced in the DS-28 enforcement note but NOT yet authored as a Directus row. Recommended follow-up: author this blocker in a future session that has Directus connectivity, alongside `DS_27_MECHANICAL_GATE_PENDING` (referenced under DS-27 with the same posture). Both share the regex-scan-at-SAVE pattern of DS-20 + DS-22.

---

## 8. Path Discipline Declaration (DS-27)

Path discipline scan: 5 filesystem references checked; all absolute and anchored to canonical root (Dropbox primary); 0 worktree references. Edits via Bash+Python one-shot per `feedback_skill_edits_via_python.md` (skill directory sandbox-restricted to `Edit`/`Write`).

| Path | Canonical root | Operation |
|---|---|---|
| `.claude/skills/zero-error-qa/SKILL.md` | Dropbox primary | Read + Python-mediated Write (insert DS-28 + lookup row) |
| `.claude/skills/zero-error-qa/SKILL.md.bak_pre_DS28_20260508T164052Z` | Dropbox primary | Created by `shutil.copy2` (backup) |
| `.claude/skills/tech-spec/SKILL.md` | Dropbox primary | Read + Python-mediated Write (insert §0.11) |
| `.claude/skills/tech-spec/SKILL.md.bak_pre_DS28_20260508T164052Z` | Dropbox primary | Created by `shutil.copy2` (backup) |
| `Production/docs/DS_28_DEPENDENCY_ORDER_RULE_REPORT_20260508.md` | Dropbox primary | This file (Write) |

`pending_directus_writes.json` lives at the Dropbox project root and is the canonical queue file (Rule 35).

---

*— End of DS-28 Proof Report 2026-05-08 —*

---
name: zero-error-qa
description: >
  Zero-error QA protocol for all production work. 7-phase process: error categorization,
  mechanical execution, adversarial counter-agent review, fix + re-verify, blast radius
  cascade, blind spot report, and proof of execution. Use whenever completing any scaffold
  step, writing TypeScript/config, creating documentation, or any work where errors propagate
  downstream. Trigger on: 'zero error', 'QA process', 'verify completion', 'proof of execution',
  'use rigor', or when finishing any feature/fix/document.
---

# Zero-Error QA Protocol

## Why This Exists

Production errors in MindfulNest compound rapidly. A single wrong field type breaks module loading. A stale reference in documentation confuses the next session. An overlooked security gap surfaces in user testing. This process catches errors BEFORE they propagate, using the exact 7-phase protocol that achieved 0 errors across Steps 2-4 of Stage 1 scaffold (April 15-16, 2026).

## Core Principles

1. **Categorize before executing.** Enumerate all error categories for the specific task BEFORE writing anything.
2. **Compile immediately.** `tsc --noEmit` after every code change. Validate syntax before moving forward.
3. **Adversarial review is non-negotiable.** A fresh agent reads BOTH source spec AND output, compares line-by-line.
4. **Blast radius is not optional.** Grep the entire project for stale references. Update EVERY affected document.
5. **Locked decisions go to Directus.** Every design choice registered in `prod_locked_decisions`. Python urllib.request, never curl.
6. **Blind spots are explicit.** After finishing, list what could STILL be wrong. If Kim says fix it, launch agents.
7. **Proof is quantified.** Every check has evidence: line numbers, grep output, compiler output.

---

---

## Discipline Standards (codified weekend 2026-05-03/04 across LDs 506-510, 519-521)

These 12 standards emerged from the v59 storyboard tool's painful retroactive bug-discovery weekend (PR #1 proper-fix + PR #2 retroactive coverage + PR #3 S5.5f + PR #4 Wave 1 architectural fix). They are project-wide non-negotiable discipline; halting + surfacing is the correct response when any standard cannot be met. They extend Core Principles (above) with concrete behavioral rules tied to specific LDs.

### DS-1. Playwright e2e for every functional behavior gate

Every functional behavior in a feature spec MUST have a Playwright e2e test in `Production/tools/storyboard-v2/e2e/<session>_smoke.spec.ts`. Network-spy assertions for `pathappPatch` routing + scope-key auto-injection in body. Server-side gate green != user-visible correctness — Cursor v9 named this pattern during S5.5c+e proper-fix; LD-507 `MANDATORY_E2E_GATE_V1` codifies. Operationalized by Phase 6.5 + Phase 6.7.

### DS-2. TDD strict ordering per phase (RED -> GREEN -> CI proof)

Write failing Playwright tests FIRST -> commit + push -> verify CI red on the new tests -> implement feature code -> commit + push -> verify CI GREEN. Never write feature code before tests. Never merge with CI red. Per LD-508 `CI_PLAYWRIGHT_ON_COMMIT_V1`. Operationalized by Phase 2 + Phase 7.

### DS-3. Fixture pinning (test data isolation)

All e2e tests use a dedicated fixture directory (e.g., `Production/Event_e2e_fixture/`). NEVER mutate live event data (`Production/Event_1/`, `Event_2/`) in tests. If a test needs different fixture state, ADD to fixture (document in PR body). If a fixture mutation is unavoidable, create `Event_e2e_fixture_v2/` rather than evolving v1 destructively. Per S5.5c+e proper-fix §17. Operationalized by Phase 1.6 Input Data Sanity (extends to test data).

### DS-4. Critical-path tests never quarantined

Tests covering CRITICAL paths (R-bugs, AF-tests, F-gates, G-gates, +NewEvent) NEVER quarantined for flake. If a critical-path test flakes, diagnose root cause + fix. Non-critical tests flaking 2x in 7 days without code change -> quarantine via `test.fixme` + `prod_activity_log` `TEST_QUARANTINED` row. Per S5.5c+e proper-fix §16 flake governance. Operationalized by Phase 4.

### DS-5. Mutation channel discipline (pathappPatch only)

Every state mutation in client code goes through `pathappPatch` at `src/api/client.ts:175`. NO raw `fetch()` to `MUTATION_ENDPOINTS` or to mutation URLs (`/api/stitch_editor/{preview,bake,job}`, `/api/video/{set_active,create}`, etc.). Wave 1 grep CI gate (LD-519 `MUTATION_CHANNEL_INVARIANT_V1`) enforces structurally — violations break CI on the next push. Adding a new mutation endpoint requires extending `MUTATION_ENDPOINTS` catalog in `src/api/endpoints.ts` FIRST, then converting via pathappPatch. Operationalized by Phase 1.5 + grep CI gate at `.github/workflows/playwright_e2e.yml`.

### DS-6. Server fail-loud (no silent print on caught exceptions)

Any caught exception in a server write path (Python or otherwise) -> structured log + raise (or fail the request). NEVER silent `print(...)`. F-SVR-001 was the example that codified this — `production_server.py:3899` swallowed `TypeError 'int' object is not iterable` for sessions before retroactive sprint v1 detected it. Per LD-520 `SERVER_SILENT_FAILURE_FAIL_LOUD_V1`. Exception: writers documented as INTENTIONALLY non-fatal (e.g., `_write_sidecar_L_json`) replace silent print with structured WARN log + `prod_blockers` row creation; never unconditional raise (would break the non-fatal contract). Operationalized by Phase 6.5 (probe should detect silent failures via log scan).

### DS-7. Server staleness check (Rule 29)

After ANY edit to a server file (e.g., `production_server.py`), restart the server before running probe tests. Local: `pkill -f "production_server.py.*<event>"` then re-launch. CI: workflow does this automatically. Stale server = false-pass on tests that reference behavior the disk has but memory doesn't. Operationalized by Phase 6.5 Step 1 (SERVER_START < PY_MTIME check).

### DS-8. Directus writes via try_post_or_queue + read-back (Rule 35)

Every Directus write goes through `Production/lib/directus.py::try_post_or_queue` with explicit read-back verification of the actual landed row. Schema gotchas (per `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`):
- `prod_activity_log` does NOT accept bare `summary` field (silent drop) — use `details.summary` JSON
- `prod_preflight_reviews` does NOT accept `classification`/`advocates_count`/`counters_count`/`date_reviewed` (silent drops) — use `task_type` for classification + `agent_advocates`/`agent_counters` JSON arrays
- `prod_reference_docs` requires `file_path` + `status`; uses `notes` (text) + `tags` (json), NOT `details`

Always re-verify enum choices via `GET /fields/<collection>/<field>` before writing handoffs that target enum fields. Schema migrations are silent (no rejection of old values). Operationalized by Phase 0 Steps 5/6/8.

### DS-9. HARD/SOFT severity for new LDs (post 2026-04-28 schema migration)

`prod_locked_decisions.severity` enum migrated from `{CRITICAL, HIGH, MEDIUM, LOW}` to `{HARD, SOFT}` between 2026-04-28 and 2026-05-04. Historical rows still hold old values; write validators do NOT reject old values (mixed-enum coexistence). For NEW LDs use HARD/SOFT only:
- **HARD** = behaviorally enforced (CI gate, code invariant, structural rule, mechanical enforcement)
- **SOFT** = awareness/UX/cosmetic (documented but not mechanically blocked)

`scope_domain` similarly extended to `{content, production, app-dev, infra, cross-cutting}`. `task_category` restricted to 11 live values; use `all` as fallback if no fit. Operationalized by Phase 0 Step 5.

### DS-10. CI workflow extension — APPEND not replace, no globs

When extending the Playwright workflow's test command in `.github/workflows/playwright_e2e.yml`, APPEND the new spec file to the explicit list. NEVER replace existing entries. NEVER use a glob (would silently include deferred scaffold or drag in untested files). When the explicit list exceeds 15 specs, migrate to Playwright project/tag-based grouping in `playwright.config.ts` (per-project explicit `testMatch` patterns) while preserving deterministic non-glob inclusion. Operationalized by Phase 1.5 (CI is a contract surface).

### DS-11. No "future" comments in shipped code

If a behavior is not done, it does not ship. Code comments like `// TODO: wired in a future session` or `// FIXME: drag-drop deferred` are not acceptable in merged code. Either implement the behavior + test it, or scope-cut it from the spec. The retroactive sprint v1 found `LibraryPanel.tsx:6` literally said "future drop" — that comment was the smoking gun for R2 drag-drop shipping unworking. Per LL-28 lessons learned. Grep for `future|TODO|FIXME|XXX|HACK` markers in modified files during Phase 3 review. Operationalized by Phase 3 Counter-Agent Adversarial Review.

### DS-12. Phase boundary commit + push (atomic phase closeout)

Each phase closes with: tests committed -> feature code committed -> CI confirms green -> THEN advance to next phase. NEVER mid-phase checkpoint, NEVER cross phase boundary with CI red. If session context tightens before the natural end, checkpoint at the PREVIOUS phase boundary (continuation handoff doc + `prod_activity_log` `CHECKPOINT_AT_PHASE_<X>_DONE` row + surface to Kim). Mid-phase checkpoints leave the branch in a half-built state and are forbidden. Operationalized by Phase 7 Proof of Execution + Compaction-Aware Checkpoint Authority.

### DS-13. Six-Layer Verification Contract (added 2026-05-06)

Every feature this phase touches is NOT done until ALL six layers verify:

1. **UI element exists** — button rendered, drop zone reactive, textarea editable
2. **UI → backend wiring** — input reaches server in expected payload shape with expected field names (no silently-dropped fields)
3. **Backend processing matches intent** — server actually USES the input (not just "request returns 200")
4. **State update propagation** — result written to right partition / row / file with right metadata (iteration_notes, parent_asset_id, timestamps)
5. **UI re-render reflects new state** — user sees the correct outcome
6. **End-to-end smoke test** — vary input → output changes meaningfully. Same input twice → same output. Different input → different output.

**Layer 6 fail = RELEASE-BLOCKER, not partial completion.** Server-side gates (DS-1 Playwright e2e, py_compile, curl probes, npm build) verify Layers 1-4. Browser smoke is the final arbiter for any UI work — Layers 5 + 6 require it.

**Source:** `feedback_six_layer_feature_verification.md` + `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` §0.2 + Kim 2026-05-06 directive ("decisions we made about eliminating various error categories").

### DS-14. Eight Risk Classes for Silent Failure (added 2026-05-06)

Identify which apply per item in scope; add explicit smoke tests per class:

| Risk class | Specific risk | Mitigation |
|---|---|---|
| **AI-driven** (Suggest Script, GPT generation, watercolor animate) | Input dropped client-side OR AI ignores input | Smoke: vary input → verify output changes meaningfully |
| **Multi-stage pipelines** (LD-375 5-stage, Phase B Cedric, magic compositor) | Stage N silently fails / no-ops | Per-stage logging + final-output validation |
| **Async / fire-and-forget** (Send for Lipsync, Send for Animation) | Success/failure not surfaced to UI | Status polling + Toast + activity_log row on terminal |
| **Drag-drop interactions** (Library → drop zones) | Wrong asset path / format / target | Smoke: drag → verify state.X.Y.Z updates correctly |
| **Side-effect captures** (registered_write, iteration_notes, parent_asset_id) | Works 95% of time, skipped on edge cases | grep all write-paths; add Playwright assertion that find_asset returns row |
| **Cost / metric displays** (cost toasts, beat counts) | Hardcoded estimates instead of real API response data | Validate against actual API response field |
| **Conditional rendering** (hide-on-milestone, dynamic labels, magic button success state) | Happy path tested, edges fail | Smoke each conditional branch explicitly |
| **State persistence** (textarea persist, signal swap, scope changes) | Works in current session, fails after page refresh | Smoke: edit → reload → verify retained |

### DS-15. Authoring Discipline (added 2026-05-06, applies to spec authoring + execution)

1. Don't invent UI specifics — LOOSE terms unless cited (LD or Kim chat)
2. Don't hallucinate endpoint names — grep `endpoints.ts` MUTATION_ENDPOINTS catalog first
3. Verify field names per Rule 35 (`DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`)
4. Verify agent claims against code via Read/Glob (don't recurse with more agents)
5. "Already wired" / "exists" in docs is NOT proof — run 6-layer verification anyway
6. Per-bug classification before patching (status audit FIRST)
7. Don't recommend legacy tool when new has gaps
8. Author handoffs AFTER predecessor ships (not during)

### DS-16. Don't Rely on Memory or Guess (added 2026-05-06, Kim directive)

*"do not rely on memory or guess, always make sure to check all the way to the end, rather than assuming."*

- Read every file you reference; re-read at phase boundaries
- Per Rule 24 confidence annotation: tag claims `[CONFIRMED against <source>]` / `[INFERRED — verify]` / `[GUESSED]`
- "I think this works" → verify smoke. "I think this exists" → grep first. "I think this LD is current" → query `prod_locked_decisions`.

### DS-17. Tail-End Independent Verifier Subagent (added 2026-05-06, recommended pattern)

At end of each phase, BEFORE marking COMPLETE: spawn Explore agent (or general-purpose) for independent end-to-end verification. Spot-check 5-10 random items from this phase's scope via 6-layer contract. Pattern proven in S5.5a1 + a2 + b — caught nothing in those cases, but absence of evidence ≠ evidence of absence; the rigor matters.

### DS-18. Deviation Logging Pattern (added 2026-05-06, from a1/a2/b honesty pattern)

Specs are always incomplete. Deviations are NORMAL. Log honestly via `prod_activity_log`:
- a1 logged 2 prompt-vs-spec deviations
- a2 logged scope-vs-stub deviation (~50 vs ~30 edits)
- b logged Cursor-reports-not-on-disk + Bug 5/7 status-unknown classifications

Pattern: when spec says X but reality is Y, write `<phase>_DEVIATION_<id>` row with `details: {spec_says, reality_is, resolution, approved_by}`. Surface to Kim before silently substituting.

**The behavior to AVOID:** silently substituting OR pretending no deviation happened. The audit trail is what makes long-running multi-session work safe.

### DS-19. Standing Escape Hatches (added 2026-05-06)

These conditions apply EVERY phase. STOP and surface to Kim when any fire:

1. Cursor review (if run) flags release-blocker
2. Layer 6 smoke fails (input variation → no output variation)
3. Schema drift detected (collection shape ≠ reference doc)
4. LD this spec amends/supersedes not found at expected key
5. Handler refactor breaks py_compile
6. Client refactor breaks npm build
7. Phase A surfaces architectural issue (not just bug) → invoke tech-spec
8. Rule 26 Opus escalation triggered (failed patch ×2, cross-system, conflicting authorities, ≥3 frustration phrases)
9. Test fixtures don't match current state
10. Discovery during execution that prior phase's work was incomplete

### DS-20. Verbal-deferral mechanical gate (added 2026-05-07, post LD 551)

Every session-end via `mn-context SAVE` runs a verbal-deferral regex scan against the
assistant turns since `session_start`. Any match without a corresponding `prod_blockers`
or LD row written this session HALTS the SAVE.

Patterns scanned (case-insensitive): `deferred`, `defer to`, `follow-up`, `next session`,
`out of scope`, `to be done`, `will do later`, `TODO`, `FIXME`, `placeholder`,
`future session`, `come back to`, `punt`, `kick the can`, `add to follow-up list`,
`leave for later`, time-estimate phrases like `estimated 2-3 hours`.

Per LD 551 `VERBAL_DEFERRAL_TRACKING_REQUIRED_V1`, every deferred item requires either:
- A `prod_blockers` row via `try_post_or_queue`, OR
- An LD with severity HARD/SOFT, OR
- An explicit waive in `checkpoint.deferrals_waived[]` with one-line rationale.

`enforcement_type=awareness_only` proved insufficient (V59 gap-fix overnight session
produced 4-5 fresh untracked deferrals AFTER LD 551 was active — see
`SILENT_DEFERRALS_AUDIT_20260507.md` items 2-14 for the failure-mode evidence).

**ENFORCEMENT IS MECHANICAL:** the regex + Directus cross-check lives in mn-context SAVE
Step 2.5. Override requires `MN_SKIP_VERBAL_DEFERRAL_GATE=1` env var AND a
`VERBAL_DEFERRAL_GATE_BYPASSED` audit row. Mirrors DS-21's pattern.

CATCH_UP Step 5 also surfaces `checkpoint.deferrals_unresolved[]` from the prior session
and refuses to render the "recommended first move" until each is resolved.

This rule is the discipline-standard companion to DS-21 — both close the loop between
"work was claimed complete" and "work was actually tracked / actually verified."

### DS-21. Browser Smoke is a HARD Prerequisite for Phase COMPLETE (added 2026-05-07, V59 gap-fix Phase F)

A `<phase>_COMPLETE` row in `prod_activity_log` MUST NOT be written until a `KIM_BROWSER_SMOKE_PASSED` row exists with the phase's verification table reproduced verbatim and Kim's verbatim confirmation ("looks good", "confirmed", "passed", "ship it") attached.

If terminal cannot drive a browser to perform the smoke, the executing session MUST defer to Kim. Defer means PHASE INCOMPLETE — not "complete pending verification." Any subsequent phase that depends on this phase MUST NOT begin until the SMOKE_PASSED row is written.

**ENFORCEMENT IS MECHANICAL (NOT DISCIPLINE-ONLY)** per LD `BROWSER_SMOKE_MECHANICAL_GATE_V1`. `try_post_or_queue` in `Production/lib/directus.py` rejects any `prod_activity_log` write where `action` ends in `_COMPLETE` unless a matching `KIM_BROWSER_SMOKE_PASSED` row exists. To override (e.g. infra-only phase with no UI), set env var `MN_SKIP_BROWSER_SMOKE_GATE=1` AND write a `BROWSER_SMOKE_DEFERRED` audit row first explaining the deferral. Both checks happen in code, not Claude self-policing.

This rule is a tightening of Phase 6.6 (Browser Console Gate). 6.6 said "browser console reviewed"; DS-21 says "phase boundary depends on it, enforced in the library."


### DS-22. State-claim verification mechanical gate (added 2026-05-07)

When Claude asserts that a system, mechanism, or wiring exists ("X is wired",
"Y will fire", "Z surfaces", "auto-loads", "executes when", "the gate runs"),
the claim MUST be either:

- Verified inline via grep/read/query in the SAME turn it's stated, OR
- Tagged per Rule 24 as `[INFERRED — verify]` or `[GUESSED]`, OR
- Explicitly waived in `checkpoint.unverified_claims_waived[]` with rationale.

Untagged + unverified state claims are the failure pattern that produced
LD 565+567's "dashboard-gate Phase 0.7 reads this LD and surfaces 'closure approaching'
starting 30 days before cap" claim — which was false-but-confidently-stated. DS-22 is
the mechanical safety net behind Rule 24's discipline rule.

Patterns scanned (case-insensitive) by mn-context SAVE Step 2.5b:
`is wired`, `will fire`, `auto-fires`, `auto-loads`, `surfaces`, `executes when`,
`fires at`, `runs on`, `gates on`, `enforces`, `mechanically prevents`,
`the gate (catches|fires|runs)`, `cron-driven`, `auto-surfaced`,
`hooks into`, `is read by`, `reads from`, `cross-references`.

`enforcement_type=awareness_only` proved insufficient (verbal-deferral pattern,
LD 551). DS-22 mirrors DS-20's mechanical pattern at the same SAVE-time hook.

ENFORCEMENT IS MECHANICAL: regex scan in mn-context SAVE Step 2.5b. Override:
env var `MN_SKIP_STATE_CLAIM_GATE=1` AND a `STATE_CLAIM_GATE_BYPASSED` audit
row. Mirrors DS-21 + DS-20 patterns.

Cross-references: Rule 24 (policy), mn-context SAVE Step 2.5b (mechanism),
DS-20 + DS-21 (companion gates), LD 551 (verbal-deferral META authority).

### DS-23. Post-fix pattern sweep (added 2026-05-07, post PR #8 CRIT-1)

**WHY this DS exists:** PR #8 adversarial security review surfaced CRIT-1 — a CodeQL-driven point-fix at one site left 4 sister-pattern instances of the same bug unfixed in the same file (including a brand-new instance authored in the same PR). Triage was reactive (CodeQL-driven) instead of proactive (pattern-driven). The bundle agent fixed only what CodeQL flagged; nothing in the workflow forced a file-level sweep for the same pattern.

**Trigger condition:** ANY security or correctness fix at line `L` of file `F` driven by a static analyzer alert (CodeQL, semgrep, Snyk, manual finding, adversarial review). Applies whether the fix is one line or many.

**Mechanical action:**

1. After patching line `L`, extract the *pattern shape* (the bug class — e.g., "`startswith(root)` without `os.sep` anchor", "`except Exception: pass` swallowing security check return", "`os.path.join` with unsanitized user input").
2. Run a `grep -n` (or ripgrep) over file `F` for the pattern's regex signature.
3. For EACH additional hit `L'`:
   - Either fix it with the same patch shape, OR
   - Mark it explicitly safe with a one-line code comment citing why (e.g., `# safe: input is constant from config`) AND a `prod_blockers` row if the safety reasoning is non-obvious.
4. Document the sweep in the commit message before push, in this exact form:
   ```
   Swept <FILE> for `<PATTERN_REGEX>`:
     - L (fixed)
     - L'_1 (fixed | marked safe — reason)
     - L'_2 (fixed | marked safe — reason)
     - ...
   ```

**Verification proof requirement:** Commit message contains the sweep block above. CI grep gate (when added) verifies that the most recent commit touching `F` for a security fix has a `Swept <FILE>` line in the message OR a `POST_FIX_SWEEP_WAIVED` row in `prod_activity_log` with rationale.

**Example failure mode it prevents:** PR #8 CRIT-1. Bundle agent fixed `_handle_magic_still:8249` after CodeQL flagged it. Did NOT grep for the same `\.startswith\(.*project_root` pattern in `production_server.py`. Sister sites at lines 6140, 6195, 8364 stayed vulnerable. Line 8364 was brand-new code in the same PR — the bug was authored AND shipped under cover of the partial fix.

**Cross-references:** PR #8 CRIT-1 (origin), DS-24 (copy-source audit, sister rule), DS-25 (adjacent risk sweep, sibling rule), Phase 4 (Fix + Re-Verify, where this runs), CLAUDE.md Rule 19 ("flawless app, no path open for error").

**ENFORCEMENT IS DISCIPLINE-ONLY for now** — mechanical CI grep gate is a future hardening (track via `prod_blockers` row `DS_23_MECHANICAL_GATE_PENDING`). Until then: discipline + commit-message inspection during Phase 7.5 PR review.

### DS-24. Audit copy source before copy (added 2026-05-07, post PR #8 CRIT-3)

**WHY this DS exists:** PR #8 adversarial security review surfaced CRIT-3 — when authoring new code at line 8364 (`_handle_magic_video`), the agent copy-pasted the containment pattern from `_handle_magic_still:8249`. The source pattern had `except Exception: pass` swallowing the security check's exception. The bug propagated verbatim into the new handler. The agent never independently audited line 8249 before treating it as a template.

**Trigger condition:** Whenever new code is authored by copying, paraphrasing, or "modeling after" an existing block in the same or different file. Applies to handler scaffolding, validation patterns, error-handling shapes, security checks, retry logic, anything copy-template-shaped.

**Mechanical action:**

1. BEFORE pasting the template into the new location, run an independent safety audit of the source line(s):
   - Read the source block in full (not just the lines you're copying — include the surrounding `try`/`except`, the return path, the error response).
   - Apply Six-Layer (DS-13) mentally to the source: does it actually do what its name claims?
   - Grep the source line for the same risk classes from DS-14 (silent failures, side-effect captures, swallowed exceptions, etc.).
   - Check if the source is on the file's known-bad list (look for `prod_blockers` rows, recent CodeQL alerts, FIXME/TODO comments nearby).
2. Document the verification verbatim in the new code's commit message OR in an inline comment above the copied block:
   ```
   # Copied containment pattern from <SOURCE>:<LINE>.
   # Audited 2026-05-07: realpath check uses os.sep anchor [confirmed],
   # no `except: pass` swallow [confirmed], error response is 403 [confirmed].
   # Safe to copy.
   ```
3. If the source is found UNSAFE: STOP. Fix the source first (which triggers DS-23 sweep), then copy from the fixed version. Do NOT propagate the bug forward and "fix later."

**Verification proof requirement:** Commit message OR inline comment in the new file references the source line + lists the audit checks performed. Phase 3 Counter-Agent Adversarial Review verifies the audit comment is present whenever new code structurally matches an existing block.

**Example failure mode it prevents:** PR #8 CRIT-3. The new `_handle_magic_video` at line 8364 inherited `_handle_magic_still:8249`'s `except Exception: pass` exception swallow because no one read the source carefully before copying. The vulnerability was duplicated into a brand-new code path. Combined with DS-23's missing post-fix sweep, the same bug now lived at four sites in production.

**Cross-references:** PR #8 CRIT-3 (origin), DS-23 (post-fix pattern sweep, sister rule for the OTHER direction — fixing one and missing siblings), DS-13 (Six-Layer applied to source), DS-14 (Risk Classes applied to source), Phase 2 (Mechanical Execution, where this runs), Phase 3 (Adversarial Review, where it's verified).

**ENFORCEMENT IS DISCIPLINE-ONLY for now** — mechanical "did this commit add new code structurally similar to existing code?" detection is hard. Future hardening: AST-similarity grep at PR open time (track via `prod_blockers` row `DS_24_MECHANICAL_GATE_PENDING`). Until then: discipline + Phase 3 reviewer eyeballing for copy-pasted blocks lacking audit comments.

### DS-25. Adjacent risk sweep after CodeQL triage (added 2026-05-07, post PR #8 CRIT-2)

**WHY this DS exists:** PR #8 adversarial security review surfaced CRIT-2 — a pre-existing vulnerability sat adjacent to the CodeQL-flagged sites in `production_server.py`. CodeQL did not flag it (sanitizer-recognition gap or out-of-scope rule). Nothing in the workflow said "after CodeQL triage, manually sweep adjacent regions of the file for siblings CodeQL might miss." The vulnerability shipped because the workflow trusted CodeQL coverage as complete.

**Trigger condition:** ANY CodeQL run completes (PR scan, scheduled scan, manual rerun) on file `F` AND any alert is acknowledged/fixed/dismissed. Triggers BEFORE the PR merges, not as a post-hoc adversarial review.

**Mechanical action:**

1. After CodeQL triage of `F` (any state — fixed, dismissed, acknowledged), enumerate the alert sites as a **hot zone**: the union of (a) the lines CodeQL flagged ± 200 lines, (b) the surrounding function bodies, (c) any function in `F` that name-matches the flagged functions (e.g., if `_handle_magic_still` was flagged, also scan `_handle_magic_video`, `_handle_magic_*`).
2. Manually scan the hot zone for sibling-pattern risks CodeQL is known to miss:
   - **Sanitizer-recognition gaps:** custom sanitizer wrappers CodeQL doesn't trust, even when they're correct.
   - **Regex bypasses:** lookalike regex patterns adjacent to flagged sites that match the same anti-pattern (e.g., `startswith` without separator anchor, `re.match` without `\Z`).
   - **Copy-pasted unsafe patterns:** structurally similar blocks (cf. DS-24).
   - **Swallowed exceptions:** `except: pass`, `except Exception: pass`, `try: ... except: return None` near the flagged region.
   - **Out-of-scope rule classes:** CodeQL only runs the rules in its query suite; if `F` has logic that lives in a class CodeQL doesn't query (e.g., business-rule auth checks, custom rate-limit logic), audit those manually.
3. Document findings in a structured block on the PR (or in `prod_activity_log` `ADJACENT_RISK_SWEEP` row) BEFORE merge:
   ```
   Adjacent risk sweep on <FILE> after CodeQL triage:
     - Hot zone: lines X-Y, functions A/B/C
     - Findings:
       - <line>: <pattern> — <fixed | filed as blocker | marked safe>
     - Out-of-scope rules audited: <list>
     - Result: <CLEAN | N findings, all addressed | DEFERRED with prod_blockers rows>
   ```
4. If findings are deferred, write a `prod_blockers` row per finding with severity HARD if security-relevant, SOFT otherwise (per DS-9).

**Verification proof requirement:** PR description or `prod_activity_log` row contains the structured sweep block above. PR cannot merge (per Phase 7.5 PR review gate) until either (a) sweep was done with documented findings, OR (b) `ADJACENT_RISK_SWEEP_WAIVED` row exists with rationale (e.g., "CodeQL alert was a typo fix, no security surface affected").

**Example failure mode it prevents:** PR #8 CRIT-2. CodeQL flagged the `startswith(root)` containment bypass at one site. Triage fixed that site. CodeQL did NOT flag a pre-existing adjacent vulnerability in the same hot zone (different code path, sanitizer-recognition gap). The fix shipped, the adjacent vulnerability shipped with it, surfaced only in the adversarial review post-merge. With DS-25 in place, the manual hot-zone sweep would have caught the adjacent finding BEFORE merge.

**Cross-references:** PR #8 CRIT-2 (origin), DS-23 (post-fix pattern sweep, complementary — DS-23 sweeps for the SAME pattern, DS-25 sweeps for SIBLING patterns CodeQL missed), DS-24 (copy-source audit), CLAUDE.md Rule 19, Phase 7.5 PR + Review Mechanics (where this gate runs).

**ENFORCEMENT IS DISCIPLINE-ONLY for now** — mechanical "did the PR description contain a sweep block?" check is feasible (string-match in `gh pr view --json body`) and is a near-term hardening (track via `prod_blockers` row `DS_25_MECHANICAL_GATE_PENDING`). Until then: discipline + Phase 7.5 reviewer requires the sweep block on the PR body before approving merge.

### Discipline Standards lookup table (cross-reference)

| DS-# | Standard | LDs / Source | Phase op |
|---|---|---|---|
| DS-1 | Playwright e2e for every functional gate | LD-507 | 6.5, 6.7 |
| DS-2 | TDD strict ordering | LD-508 | 2, 7 |
| DS-3 | Fixture pinning | proper-fix §17 | 1.6 |
| DS-4 | Critical-path never quarantined | proper-fix §16 | 4 |
| DS-5 | Mutation channel discipline | LD-519 | 1.5 + grep CI gate |
| DS-6 | Server fail-loud | LD-520 | 6.5 |
| DS-7 | Server staleness check | Rule 29 | 6.5 Step 1 |
| DS-8 | Directus writes via try_post_or_queue + read-back | Rule 35 | 0.5, 0.6, 0.8 |
| DS-9 | HARD/SOFT severity | Schema migration 2026-05-04 | 0.5 |
| DS-10 | CI workflow APPEND not replace | LD-507 (e2e gate hygiene) | 1.5 |
| DS-11 | No "future" comments | LL-28 lessons learned | 3 |
| DS-12 | Phase boundary commit + push | (this skill's ordering) | 7 |
| DS-13 | Six-Layer Verification Contract | 2026-05-06 amendment | 0–7 |
| DS-14 | Eight Risk Classes for Silent Failure | 2026-05-06 amendment | 1.5 + 6.5 |
| DS-15 | Authoring Discipline (12 rules) | 2026-05-06 amendment | 0–3 |
| DS-16 | Don't rely on memory or guess | 2026-05-06 amendment | every phase |
| DS-17 | Tail-end independent verifier subagent | 2026-05-06 amendment | 7.5 |
| DS-18 | Deviation Logging Pattern | 2026-05-06 amendment | every phase |
| DS-19 | Standing Escape Hatches (10 conditions) | 2026-05-06 amendment | every phase |
| DS-20 | Verbal-deferral mechanical gate — regex + Directus cross-check at SAVE | LD 551 `VERBAL_DEFERRAL_TRACKING_REQUIRED_V1` (V59 gap-fix Phase G, 2026-05-07) | mn-context SAVE 2.5, CATCH_UP 5 |
| DS-21 | Browser smoke is a HARD prerequisite for COMPLETE — mechanically enforced in `try_post_or_queue` | LD `BROWSER_SMOKE_MECHANICAL_GATE_V1` (V59 gap-fix Phase F, 2026-05-07) | 6.6, 7.5 |
| DS-22 | State-claim verification mechanical gate — regex scan for unverified wiring/surfacing claims at SAVE | Rule 24 + LD 551 + DS-22 (2026-05-07) | mn-context SAVE 2.5b |
| DS-23 | Post-fix pattern sweep — grep file for sister instances after security fix | PR #8 CRIT-1 (2026-05-07) | 4, 7.5 |
| DS-24 | Audit copy source before copy — independently verify template safety before pasting | PR #8 CRIT-3 (2026-05-07) | 2, 3 |
| DS-25 | Adjacent risk sweep after CodeQL triage — manual hot-zone scan for siblings CodeQL misses | PR #8 CRIT-2 (2026-05-07) | 7.5 |

When a standard cannot be met, halt + surface to Kim. Silent shortcuts are not the correct response.

---

## PHASE 0: Pre-Flight Protocol (MANDATORY — runs every task, cannot be skipped)

**This phase is the meta-enforcement mechanism for CLAUDE.md Rule 19 ("The app must work flawlessly at the end. Do not leave any path open for error.").** It runs BEFORE Phase 1 on every task, with no exceptions. A weekly automated audit (see Part 5 below) compares `app_activity_log` against `prod_preflight_reviews` and auto-creates blockers for any work that bypassed Phase 0.

### Step 1 — Classify the task (apply criteria, not judgment)

- **trivial**: typo fix, rename one variable, update one comment only. Nothing else.
- **routine**: apply a documented pattern, follow an existing skill end-to-end, a small documented change that touches files already in the pattern's scope.
- **architectural**: ANY of the following →
  - Change to `firestore.rules` or any other security rule file
  - New skill file, or edit to CLAUDE.md, or edit to an existing skill's behavioral rules
  - New `prod_*` or `app_*` Directus collection, or new required field on an existing one
  - Reorder, close, or resolve a CRITICAL blocker
  - Dependency version change (`package.json`, `Podfile`, Python requirements)
  - Change to auth flows, data schemas, or API contracts
  - New workflow, institutional process, or governance rule

**If in doubt between routine and architectural → classify as architectural.** The cost of over-classifying is 3 extra Sonnet agent calls (~$0.11); the cost of under-classifying is a missed blind spot that can cascade into production errors.

#### Step 1 Output — State the classification aloud (LD-262 `CLASSIFICATION_INSIDE_PHASE_0_STEP_1`)

Before writing the 3-sentence preflight summary in Step 2, Claude MUST state the classification in this exact form, as the first visible act of Phase 0:

> **Classifying: [TRIVIAL | ROUTINE | ARCHITECTURAL] — [one-sentence plan referencing a specific architectural criterion above, OR the explicit phrase "none of the architectural criteria apply". Proceed?**

Two non-negotiable substrings must appear in the sentence after the em-dash:
1. Either the name of ONE criterion from the architectural bullet list above (e.g. "edit to an existing skill's behavioral rules", "new prod_* Directus field", "change to auth flows") OR the literal string **"none of the architectural criteria apply"**. This blocks habituation — you cannot collapse the sentence into a stock phrase without picking a criterion or explicitly negating all of them.
2. The trailing token **"Proceed?"** (with the question mark).

**Interactive-mode branch:** If the session is interactive (Kim is at the keyboard, responses expected in real time), Claude MUST WAIT for Kim's explicit yes/go-ahead/directive before moving to Step 2. Silence is NOT consent. A new unrelated message from Kim is NOT consent — re-ask.

**Autonomous-mode branch (LD-232 pattern):** If the session is running under explicit pre-authorization — Kim has said something equivalent to "autonomous mode", "you have my yes on all N in advance", "proceed without pausing" — Claude states the classification sentence FOR AUDIT TRAIL (the sentence is still required) and proceeds immediately to Step 2 without waiting. The stated classification must match the `task_type` eventually written to `prod_preflight_reviews` in Step 5; a mismatch is itself a Phase 0 violation.

The sentence is Step 1's observable output — it is not a new step. It does not duplicate the tier criteria (those live above in this same Step 1). The goal is a load-bearing verbal artifact that Kim, or a future audit, can cross-check against the Directus row.

**Validation Tier — also declared in Step 1 output (alongside Change Class):**

- **Tier A (fast, every change):** Mandatory on EVERY task. Compile/lint/type checks + directly impacted tests + protocol gates triggered by the diff. Any task at any Change Class runs at minimum Tier A.
- **Tier B (architectural):** Mandatory when Change Class = architectural, OR the diff touches an auth/schema/contract/runtime boundary. All Tier A + adversarial/counter checks + boundary/actor validation gates (Phases 2.7, 3.5, 6.5).
- **Tier C (nightly/pre-release):** Mandatory for release branch, nightly CI, App Store submission, or large cross-system diffs. All Tier B + full mobile E2E invariants (Phase 6.7) + media golden probes (Phase 6.8) + extended replay suites.

**Tier selection rules:**
- TRIVIAL → Tier A by default; escalate to Tier B if touching auth/contracts/security rules.
- ROUTINE → Tier A by default; escalate to Tier B if cross-boundary or role-access changes.
- ARCHITECTURAL → Tier B minimum.
- Tier C is event-driven (nightly/release-candidate/pre-release), independent of Change Class — supersedes upward.

**Extended Step 1 Output (LD-262, Tier addendum):** The classification sentence must declare BOTH axes in the same output:

> **Classifying: [TRIVIAL | ROUTINE | ARCHITECTURAL] — [criterion or "none of the architectural criteria apply"]. Validation Tier: [Tier A | Tier B | Tier C] — [one-sentence tier rationale]. Proceed?**

The Tier declaration appends to the same output sentence — not a new step. Interactive mode: wait for Kim's yes on the combined output. Autonomous mode: state both axes for audit trail, proceed immediately.

### Step 1.5 — Architectural Decision Triggers (added 2026-05-06)

MANDATORY check after Tier classification, BEFORE Step 2. This step
fires architectural-decision halt patterns that would otherwise be
forgotten across sessions.

**Trigger 1 — Main React Native app CI/CD work:**
If task touches `MindfulNest/.github/workflows/`, the
`kimhyla/mindfulnest-ios` repo CI/CD, or specs mentioning
App Store / TestFlight / EAS Build / Expo build / iOS build /
Android build / mobile CI / mobile deploy, OR proposes copying
workflows from `Production/github_actions/` or
`Production/tools/storyboard-v2/` as templates for the main app:
1. Query `prod_locked_decisions` for `MAIN_APP_CICD_GREENFIELD_DESIGN_V1`
2. Read `decision_text` fully
3. Surface verbatim to Kim with explicit halt
4. Wait for confirmation
5. If `tech-spec` skill is invoked, research agents MUST be told NOT to
   load tooling-repo workflow files as templates — only use them for
   "what to AVOID" reference.

Authority: `LD MAIN_APP_CICD_GREENFIELD_DESIGN_V1` (HIGH, active),
memory file `project_main_app_cicd_greenfield_lock.md`.

**Pattern for additional triggers:** this is the FIRST trigger.
Future LDs that fit "load-bearing only when domain arises" get added
here as Trigger 2, 3, etc. Examples that might warrant future
triggers: SHORTCUT exception scopes (Rule 19 escape hatches that
expire and must be revisited); domain-specific "always X never Y"
locks that don't apply to all tasks but must fire when domain matches.

### Step 1.6 — Git Hygiene Precondition (added 2026-05-06, autonomous)

MANDATORY check after Step 1.5, BEFORE Step 2. Silent and autonomous —
halts ONLY on real anomaly. No prompts to Kim unless something is wrong.

Run these checks in order:

1. **Working tree clean OR all dirty files belong to this task.**
   - `git status --porcelain` returns empty → clean. Proceed.
   - Returns non-empty → list of dirty files. If ALL paths match files
     this task is about to touch, OK to proceed (working directory is
     "this task in progress"). If ANY dirty file is unrelated to this
     task, HALT — surface the unrelated diffs to Kim with: "Working
     tree has unrelated changes in [file list]. Stash, commit, or
     confirm-discard before continuing?"

2. **Current branch is appropriate for the task.**
   - `git branch --show-current`
   - For Tier B / Tier C tasks (any governed-file edit per Rule 19):
     branch must NOT be `main` / `master`. If on main, HALT — surface:
     "On main branch for Tier [B|C] task. Need feature branch.
     Suggested name: feature/[task_id]. OK to create + checkout?"
   - For Tier A (trivial): no branch enforcement.

3. **CI on current branch is not failing or in-progress.**
   - `gh run list --branch <current_branch> --limit 1 --json status,conclusion`
   - If `conclusion=failure` → HALT, surface: "CI is red on [branch].
     Investigate before stacking new changes."
   - If `status=in_progress` → WARN one line, proceed: "CI in progress
     on [branch]; new commits will queue behind it."
   - If `conclusion=success` OR no runs yet → proceed silently.
   - If `gh` not installed / not authed → WARN once, proceed.

4. **Local main is reasonably fresh.**
   - For Tier B / Tier C tasks: ensure `git fetch origin` ran within
     last 24 hours. If older → run `git fetch origin` silently, then
     continue.

**Output (autonomous, terse):** state ONE line in Phase 0 output:

```
Git: clean | branch=feature/<name> | CI=green | fetch=fresh
```

Or if anomaly halted:

```
Git: HALT — [specific anomaly]
```

**Why autonomous:** these are mechanical checks Kim shouldn't have to
acknowledge for every routine task. They only matter when broken.

**Override:** if Kim has explicitly said "skip git checks for this
task" or granted a `SHORTCUT_GIT_HYGIENE_BYPASS_<task_id>` decision in
`prod_locked_decisions`, skip and log the bypass in `prod_activity_log`.

**Honest scope:** the `gh` checks depend on `gh auth login` having been
done at machine setup. The fetch check depends on network availability.
On a fresh machine or offline session, these checks WARN and proceed
rather than blocking — the goal is to catch real problems, not to
manufacture false halts.

### Step 2 — Write a 3-sentence pre-flight summary

1. **What I'm about to do** — one sentence, concrete files and changes.
2. **What error paths this could leave open** — the failure modes you'd flag in a code review.
3. **Whether any shortcut patterns apply** — reference the `no-shortcuts` skill list; if YES, Phase 0 halts and `no-shortcuts` runs first.
4. **Library claim verification (LD-158 PHASE0_LIBRARY_CLAIM_VERIFICATION)** — applies if and only if the plan proposes installing a NEW third-party library/package OR makes a specific capability claim about an existing library (e.g., "X supports dynamic routes", "X ships a config plugin"). Does NOT apply to incidental `import` references to libraries already in `package.json` whose claimed capabilities are not load-bearing for this plan. When triggered: cite the npm registry URL AND the README section / npm field that confirms the claim. WebFetch (or equivalent post-install source inspection) is required BEFORE the library name appears in the summary. If WebFetch is unavailable in this session, defer the library-naming decision to a follow-up task. Reference: `.auto-memory/project_ld158_library_claim_verification.md`.
5. **Size-budget claim verification (SIZE_BUDGET_V1)** — applies if and only if the plan:
   (a) produces a new asset that will be registered in `prod_assets` or shipped in the app bundle, OR
   (b) modifies the compression standards, delivery format, or bundle contents.
   When triggered: the plan MUST state the expected per-asset size and the SIZE_BUDGET_* decision(s) it will honor (SIZE_BUDGET_V1 / SIZE_BUDGET_VIDEO_V1 / SIZE_BUDGET_AUDIO_V1 / SIZE_BUDGET_IMAGE_V1 / BUNDLE_SIZE_CI_ENFORCEMENT_V1 / LD-283 SIZE_BUDGET_PER_MODULE_V1).
   Do NOT apply to intermediate working files, iteration scaffolding, or Kim-only production tools.
   If the plan's predicted size exceeds the per-asset or per-module ceiling (60 MB target / 80 MB ceiling per LD-283), STOP and either (a) adjust the compression plan, or (b) file a `SHORTCUT_SIZE_OVERRIDE_{asset_id}` (or `SHORTCUT_MODULE_{module_id}_CEILING_V1` for per-module overrides) escape-hatch decision with Kim's explicit approval.
   Reference: SIZE_BUDGET_AUDIT_20260418.md §4, §5; LD-283 for per-module override paper-trail requirement.

### Step 3 — Spawn required agents based on task_type

| task_type | Advocates | Counter-agents | Agent model | Skip to Phase 1? |
|---|---|---|---|---|
| trivial | 0 | 0 | — | Yes — still write the Directus row, but no agents |
| routine | 1 | 1 | Haiku | No |
| architectural | 3 | 3 | Sonnet | No |

**Advocate prompts (SHORT — each advocate answers under 200 words):**
Architectural advocates run in parallel. Each receives only: (a) the task specification or diff, and (b) their angle question below. Do NOT pass full CLAUDE.md to advocate agents — that context load is already paid in the main session.

1. **Speed / efficiency** — "What does this change cost at scale, and where does it speed up or slow the pipeline?"
2. **Safety + integrity** — "What failure modes does this change open or close, and does it contradict any locked decision? Cite LD keys for any conflicts. Check: Rule 19, LD-124, and any LD the task spec references."
3. **Maintainability / clarity** — "Will a future session understand and correctly apply this? What could be misread?"

**Counter-agents (Sonnet for architectural, Haiku for routine):** each reads ONE advocate's argument and returns structured findings ONLY:
- `[CRITICAL|HIGH|MED] — <weakness> — <proposed mitigation>` (one line per finding)
- OR: `No critical weakness found after checking: <list ≥3 specific things examined>.`

A generic "reviewed thoroughly" does not satisfy the gate. If a counter returns no structured finding and no explicit "none found" statement, treat as: `[HIGH] — Counter returned unstructured output — flag for Kim before proceeding.`

**Convergence gate (objective — replaces subjective "stop when counters agree"):**
Proceed to Step 4 (synthesis) only when ALL are true:
1. Every CRITICAL finding has a stated mitigation that addresses root cause — "log and monitor" does NOT clear a CRITICAL; the fix must close the failure mode
2. Every HIGH finding has a root-cause mitigation OR an explicit Kim-flag for session-end review
3. No unaddressed CRITICAL finding remains in synthesis

### Step 4 — Synthesize findings

For every CRITICAL or HIGH weakness raised by a counter-agent, either:
- **Address it** by modifying the plan before proceeding, OR
- **Document why it does not apply** with concrete reasoning (not "I think it's fine").

If ANY CRITICAL weakness cannot be addressed → STOP. Escalate to Kim with the synthesis.

### Step 5 — Write to Directus `prod_preflight_reviews`

POST a row with all fields populated:
- `task_id` (UUID or slug — must also be used in the eventual `app_activity_log` entry so the audit can join them)
- `task_type`
- `task_description`
- `claude_summary` (the 3-sentence preflight)
- `agent_advocates` (JSON array — empty for trivial)
- `agent_counters` (JSON array — empty for trivial)
- `synthesis`
- `approved_to_proceed` = true ONLY if all CRITICAL weaknesses are addressed
- `approved_at` = now (only if approved)

Use Python `urllib.request` via `lib/directus.py::DirectusClient`. Never curl.

### Step 6 — Confirm the row was written

Immediately query `prod_preflight_reviews` filtered by the `task_id` you just wrote. If the read returns 0 rows → STOP. Do not proceed to Phase 1.

### Step 7 — Proceed to Phase 1

Only after Steps 1-6 are complete and the Directus row exists.

### Step 8 — Embed task_id in every downstream Directus write (MANDATORY)

Every `app_activity_log`, `app_blockers`, or `prod_locked_decisions` entry produced during this task MUST carry the same `task_id` you used in Step 5. Two mechanisms (use BOTH):

1. **`details` JSON field** must include `{"task_id": "<task_id>", ...}`.
2. **`related_activity_log_id`** on the `prod_preflight_reviews` row must be PATCHed after the first activity log write to form the FK link (see `Production/scripts/create_prod_preflight_reviews.py` for payload shape).

This gives the weekly audit (`Production/scripts/weekly_preflight_audit.py`) an EXACT match by FK or task_id string, turning its architectural-keyword heuristic into a fallback rather than the primary signal. Missing the task_id on an activity log entry is itself a Phase 0 violation — the audit will flag it.

---

**Honest limit (transparent):** Claude can theoretically skip invoking zero-error-qa entirely, or skip Phase 0 within it. These skips are DETECTABLE via the weekly `weekly_preflight_audit.py` cron (creates a CRITICAL blocker in `app_blockers` that surfaces at next session start), but not PREVENTABLE in the moment without harness-level hooks. The detection loop runs automatically — Kim does not have to be the backstop.

**HARD GATE:** Do not run Phase 1 until Phase 0 is complete and the `prod_preflight_reviews` entry exists and was confirmed by read-back.

---

## PHASE 1: Error Category Identification

Before writing anything, create a **Master Error Table**:

| Category | Examples | Likelihood | Severity | How to Catch |
|---|---|---|---|---|
| [Type of error] | [1-2 concrete instances] | High/Med/Low | CRITICAL/HIGH/MED/LOW | [test/grep/compile/inspect] |

**MANDATORY row on EVERY task (never omit):**

| Shortcut detection | Is any blocker deferred, reordered, simplified, or skipped? | ALWAYS check | CRITICAL | Load `no-shortcuts` skill if YES |
| Size-budget | Does this task produce a new asset (image, audio, video, JSON) or change the compile/bundle output? Does the change exceed any lock in SIZE_BUDGET_* Directus decisions? | ALWAYS check when producing deliverables | CRITICAL | Run size-budget check script; if over-budget, either compress before registering or escalate via SHORTCUT_SIZE_OVERRIDE_{asset_id} |

Present to Kim if async. Update the table if new categories emerge during execution.

### Shortcut Detection Gate (HARD — blocks execution)

**EXECUTION CHECK — all three boxes must be checked before Phase 2 begins. If any box is unchecked, STOP. Do not run Phase 2. Do not compile. Do not execute.**

```
[ ] Shortcut detection question explicitly answered in the plan (YES or NO)?
[ ] If YES: no-shortcuts decision protocol COMPLETE (all 7 steps documented, escape hatch writes verified in Directus)?
[ ] If NO: Statement "Verified: no shortcuts in this plan" is in the plan output?
```

**Question to answer explicitly:** *"Does this plan include any shortcut, deferral, bypass, 'quick version', 'MVP' (feature-descoping sense), 'placeholder for shipping code', 'we'll add later', 'temporary', TODO/FIXME in shipping code, hardcoded assumptions, or reordering of registered Directus blockers?"*

**Handoff rules:**
- If decision = "do it properly" → continue Phase 2 with full-implementation plan
- If decision = "approved shortcut" → continue Phases 2-7 (approved shortcut does NOT bypass QA rigor); ADD the Shortcut Escape Hatch Checklist (6 items) to Phase 7 proof table
- If decision = "shortcut rejected by Kim or decision protocol" → STOP Phase 1. Return to planning: redesign to eliminate shortcut, OR escalate to Kim with 6-step analysis.

This gate exists because Kim's rule (locked April 16, 2026, Directus) is: "The app must work flawlessly at the end. Do not leave any path open for error." See CLAUDE.md Rule 19 and `.claude/skills/no-shortcuts/SKILL.md` for the full 7-step decision protocol.

### Size-Budget Detection Gate (HARD — blocks execution when asset-producing)

**EXECUTION CHECK — if this task produces any shippable asset, all three boxes must be checked before Phase 2 begins. If any box is unchecked, STOP.**

```
[ ] Is any new asset produced by this task that will be registered in `prod_assets` or bundled in the app? (YES / NO)
[ ] If YES: expected per-asset size stated in plan, AND the honored SIZE_BUDGET_* decision(s) named?
[ ] If NO: statement "No shippable asset produced in this task" is in the plan output?
```

This gate exists because every uncontrolled asset bitrate in current production traces back to an autonomous session that had no trigger to ask "how big is this?" Reference: SIZE_BUDGET_AUDIT_20260418.md §10.5 + LD SIZE_BUDGET_V1 + LD-283 SIZE_BUDGET_PER_MODULE_V1.


## PHASE 1.5: Boundary Contract Manifest (BLOCKING — runs whenever task adds/modifies a cross-boundary call)

**What this catches:** The class of bug where a client calls an endpoint with a query param variant (e.g. `?probe=1`) and the server handler never implements that variant — silently returning the wrong content type or shape. Also catches spec/implementation drift where Claude lists a variant in the spec but forgets to wire it in code. This is a DIFFERENT failure class from Phase 3 adversarial review: review catches internal inconsistency, this catches external contract gaps.

**Trigger:** ANY of the following in the diff: `fetch(`, `urllib.request`, `subprocess.`, a function call where caller and callee are in different files, or a new/modified HTTP route in the server.

**If not triggered:** State "No cross-boundary calls in this diff — Phase 1.5 skipped." This is a BLOCKING declaration, not silence.

### Manifest format

For every cross-boundary call, produce one row:

| id | caller (file:line) | endpoint/function | method | query_variants | expected_response_shape | callee_branch_grep |
|---|---|---|---|---|---|---|
| B-1 | template.html:725 | GET /api/finder_video | GET | `probe=0` (default), `probe=1` | probe=0: `video/mp4` bytes; probe=1: `application/json {duration_s:float, duration_ms:int, size_bytes:int}` | `if.*probe.*==.*1` in production_server.py |

**Rules:**
1. Every distinct query param value that CHANGES server behavior is a separate `query_variants` entry. `?probe=1` and `?probe=0` are different variants. Default (param absent) is also a variant.
2. For each variant, `expected_response_shape` must state both `Content-Type` AND the exact JSON keys+types (or "binary:<mime>" for non-JSON).
3. Run: `grep -n "<callee_branch_grep>" <handler_file>`. If grep returns 0 lines → **HARD STOP. Do not proceed to Phase 2.** The variant is specced but not implemented — write the handler branch before continuing.
4. If the callee file is >200 lines, Read the specific handler function verbatim (not a summary) before declaring the grep passed.

**Output:** Print the completed manifest table inline. It becomes the input to Phase 6.5 probes.

## PHASE 1.6: Input Data Sanity (BLOCKING — runs whenever the diff passes an on-disk file path to an external consumer)

**What this catches:** the class of bug where placeholder, corrupt, truncated, or under-sized files get passed to external generation APIs (gpt-image-1, Flux Kontext, Kling, Seedance, ElevenLabs, ByteDance LipSync) or media subprocesses (ffmpeg, ffprobe, imagemagick) — burning API budget on garbage and producing degraded outputs. This is a SCREEN against malformed bytes, not a content guarantee — see "What this does NOT catch" below.

**Trigger:** the diff adds or modifies code that, on the call site itself (not via opaque wrappers — see definition below), passes an on-disk file path positionally to ANY of:
- `urllib.request.urlopen(...)` / `requests.post(...)` targeting a known external generation API
- `subprocess.run([...])` where the path appears positionally to ffmpeg / ffprobe / imagemagick / similar media tool
- Any helper from `Production/tools/api_calls.py` or skill-equivalent that takes a path argument

**Opaque wrapper definition:** A function whose body is NOT modified by this diff AND which is listed in `Production/tools/api_calls.py` allowlist (or a skill-equivalent allowlist). If this diff modifies the wrapper itself, Phase 1.6 fires on the wrapper's internal call site. The runtime wrapper at `Production/lib/api_call_with_input_validation.py` (when present) is itself one of the in-scope call sites — Phase 1.6 fires INSIDE it on the urlopen/subprocess line, not on its own outward-facing API.

**If not triggered:** State `"Phase 1.6 skipped — no on-disk file inputs to external consumers in this diff."` This is a BLOCKING declaration, not silence.

**If the input is a URL, base64 string, data URI, in-memory bytes, stdin, or env-var (PARTIAL outcome):** Before declaring PARTIAL, run: `test -f Production/lib/api_call_with_input_validation.py`. If the wrapper file does NOT exist, escalate to **HARD STOP**: `"Phase 1.6 HARD STOP — non-disk input declared but runtime wrapper does not exist at Production/lib/api_call_with_input_validation.py. Build the wrapper, or open a SHORTCUT_PHASE_1_6_NO_RUNTIME_WRAPPER decision in prod_locked_decisions with Kim's approval."` Only if the wrapper file exists, declare PARTIAL: `"Phase 1.6 partial — non-disk input class; runtime wrapper at Production/lib/api_call_with_input_validation.py covers this. ACTION NEEDED: add Phase 6 blind-spot entry naming the wrapper line that handles this input class."`

**If the file is generated mid-diff (a step earlier in this diff produces it for a step later in this diff to consume — DEFERRED outcome):** Before declaring DEFERRED, run: `grep -nE 'sanity_check\(|api_call_with_input_validation' <runtime_call_site_file>`. If the grep returns ZERO matches, escalate to **HARD STOP**: `"Phase 1.6 HARD STOP — DEFERRED declared but runtime call site at <file> does not invoke sanity_check or the input-validation wrapper. Add the runtime call before the API submission."` Only if the grep returns ≥1 match, declare DEFERRED: `"Phase 1.6 DEFERRED for path <X>: file generated at runtime by step <N> in this diff. Runtime assert in Production/scripts/phase_1_6_input_sanity.py covers this case at the moment-of-call (verified at <file>:<line>)."` This grep gate mirrors Phase 1.5's grep-or-fail pattern and closes the DEFERRED enforcement loophole.

### The four checks (all four mandatory; HARD STOP on any failure)

For every triggering file path, classify by extension and run all applicable checks in order:

**(a) Existence.** `os.path.exists(path)` returns True. HARD STOP if False.

**(b) Size floor (does NOT apply to JSON):**
- Image (`.png .jpg .jpeg .webp`): file size > **10,000 bytes**
- Audio (`.mp3 .wav .m4a .ogg`): file size > **5,000 bytes**
- Video (`.mp4 .mov`): file size > **100,000 bytes**

HARD STOP on under-floor. (Floors calibrated above placeholder ceilings — 1px PNG ~70 B, ID3-only MP3 ~2 KB, header-only MP4 ~600 B — and below legitimate-content floors per Rule 6.1/6.2.)

**(c) Format decode:**
- Image PNG/WebP: `PIL.Image.open(path).verify()` succeeds
- Image JPEG: `PIL.Image.open(path).load()` succeeds (verify() is too lenient for JPEG truncation)
- Audio (MP3/WAV/M4A/OGG): `ffprobe -v error -of json -show_streams <path>` exits 0 AND returns at least one `streams[]` entry with `codec_type == "audio"`
- Video (MP4/MOV): same ffprobe command, must return at least one `streams[]` entry with `codec_type == "video"`
- JSON: `json.load(open(path))` succeeds (NO size floor for JSON — `{}` at 2 bytes is valid; only parse success matters)

HARD STOP on decode failure. (Catches truncated, zero-byte-padded, and format-mislabeled files. mutagen is NOT used: ffprobe is the canonical project media tool per LD-284 and provides a stricter audio decode contract.)

**(d) Character-asset reference checks (image only).** A path is a character reference IF AND ONLY IF either:
- the path contains the case-insensitive directory `Character_Assets/`, OR
- the basename matches the glob `*_master.<image-ext>` or `*_reference_master.<image-ext>` for a recognized image extension (`.png .jpg .jpeg .webp`)

This anchored matcher avoids false-positive HARD STOPs on `*_master.*` files that are NOT character references (e.g. `event_3_render_master.mp4`, `audio_master.wav`, `prompt_master.json`, `pipeline_master.py`).

For a triggering character-ref image, run in this order: (a) existence FIRST → registration check → (b) size → (c) decode → (d) dim:

1. AFTER existence (a) but BEFORE checks (b)–(c) above, run a direct `prod_assets` lookup via `DirectusAdminClient.get_items('prod_assets', filters={'file_path': {'_eq': <path>}}, limit=1)`. If the lookup returns zero rows, HARD STOP: `"Phase 1.6 HARD STOP — character-ref path <X> not registered in prod_assets. Per Rule 31/34, register via Production/tools/registered_write.py before passing to external API."` This direct Directus read is the SOLE allowed exception to Rule 34's "find_asset.py first" mandate — it is a path-equality registration verification, not an identity lookup. All other asset lookups continue to use `find_asset.py`.

After (b)–(c) pass for the image, run:

2. PIL.Image dimensions: `w >= 256 and h >= 256`. HARD STOP if either dim is below 256 px. (Floor is below the Rule 6 600-px delivery floor and well above 1px/8px placeholders.)

### Escape hatch (Rule 19 alignment)

A legitimate sub-floor file can be allowed via a `SHORTCUT_PHASE_1_6_FLOOR_OVERRIDE_{asset_id}` decision in `prod_locked_decisions` per Rule 19. The decision must:
- Be approved by Kim explicitly
- Name the asset_id and the floor it overrides
- Include an explicit `closure_date` field (date by which the shortcut is removed)
- Have `status=active` (not superseded, not closed)
- Be referenced in Phase 7 evidence

**Honoring the shortcut at QA time:** before treating a file as exempt, query `prod_locked_decisions` for the matching `SHORTCUT_PHASE_1_6_FLOOR_OVERRIDE_{asset_id}` row. HARD STOP if any of: row not found, `status != 'active'`, or `closure_date < today`. A lapsed shortcut is NOT a shortcut — it is a Rule 19 violation. This closes the shortcut-creep loophole flagged in the Phase 3.5 re-review.

### What this does NOT catch (honest scope statement)

Phase 1.6 is a SCREEN, not a content guarantee. It does NOT catch:
- A 12 KB white PNG (decodes fine; semantically empty) — Phase 6.8 catches the downstream output regression
- A 50 KB mostly-silent MP3 (passes ffprobe; LatentSync starves) — covered by §8.4 silcomp + Phase 6.8
- A 200 KB MP4 with one black frame (passes streams check) — Phase 6.8
- The wrong character master at the right dimensions (semantic mismatch) — Rule 31/34 + Phase 6.8 golden compare
- TOCTOU races between QA-time and call-time — covered by the runtime helper at the call site
- URL / base64 / stdin / env-var inputs — covered by the runtime wrapper at `Production/lib/api_call_with_input_validation.py`

### What this gate is for

If the check requires a network call, a Directus query (other than the prod_assets registration check for character refs), or a comparison artifact, it does NOT belong in Phase 1.6. Such checks live elsewhere (URL HEAD probes, Phase 6.5 / 6.8, etc.).

### Helper script

A reusable implementation of all four checks lives at `Production/scripts/phase_1_6_input_sanity.py`. It is callable from BOTH the QA gate (`python3 Production/scripts/phase_1_6_input_sanity.py --path <X> --kind <image|audio|video|json>`) AND from runtime wrappers (`from phase_1_6_input_sanity import sanity_check`). SKILL.md text is authoritative for the BLOCKING semantics; the helper is the canonical executable form.

### Outcome declaration (required)

- PASS: `"Phase 1.6 PASS — N inputs verified: [<path>: <size> B, decoded as <fmt>, <dims-if-image>, prod_assets registered if char-ref] ..."`
- HARD STOP: `"Phase 1.6 HARD STOP — <path>: <which check failed (a/b/c/d/find_asset)>: <detail>"`
- DEFERRED: `"Phase 1.6 DEFERRED for <path> — generated at runtime by step <N>; runtime helper covers this."`
- PARTIAL: `"Phase 1.6 partial — non-disk input class; runtime wrapper covers."`
- SKIP: `"Phase 1.6 skipped — no on-disk file inputs to external consumers in this diff."`


## PHASE 2: Mechanical Execution

1. Break the spec into discrete ordered tasks
2. Translate each spec section mechanically — no embellishments, no assumptions
3. Run `tsc --noEmit` immediately after writing
4. Self-check: each spec clause maps to output section


## PHASE 2.5: Python Validation Gate (BLOCKING — runs whenever a .py file is modified)

**What this catches:** Import path errors (`from lib.X import` when the correct form is `from X import`), syntax errors, and server startup failures — all of which are invisible to static review but surface immediately on first execution.

**Trigger:** Any `.py` file added or modified in this diff (including `production_server.py`, handler files, and utility modules in `Production/tools/` or `Production/scripts/`).

**If not triggered:** State "No .py files modified in this diff — Phase 2.5 skipped." This is a BLOCKING declaration, not silence.

### Validation steps

1. **Syntax check** — run on every modified `.py` file:
   ```bash
   python3 -m py_compile <file>
   ```
   **HARD STOP if any file fails.** Fix the syntax error, re-run Phase 2 on the fix, then re-run this gate.

2. **Import resolution** — for every new `import` or `from X import Y` added in this diff:
   ```bash
   python3 -c "import <module>"  # run from the file's own directory (cwd matters)
   ```
   If this fails: HARD STOP. Fix the import path before Phase 3. Do not declare "imports look correct" — actually run them.

3. **Smoke-test** (mandatory if the diff touches `production_server.py` or any file it imports):
   ```bash
   timeout 10 python3 production_server.py --smoke-test 2>&1 | tail -5
   ```
   - If smoke-test **passes** → continue.
   - If smoke-test **fails due to network** (Directus unreachable) → log `[Phase 2.5] offline-mode: smoke-test skipped — network unreachable` in `prod_activity_log` and continue. Never silently skip.
   - If smoke-test **fails due to code error** → HARD STOP. Fix before Phase 3.

**Outcome declaration (required):**
- PASS: `"Phase 2.5 PASS — py_compile clean, imports resolve, smoke-test [passed|offline-skipped]"`
- HARD STOP: `"Phase 2.5 HARD STOP — [syntax error|import error|smoke-test code failure]: <detail>"`


## PHASE 2.6: React Native / Expo Validation Gate (BLOCKING — runs whenever RN/Expo surface modified)

**Trigger:** Any diff touching React Native / Expo app code paths: `app/**`, `src/**`, `components/**`, `screens/**`, `hooks/**`, `navigation/**`, `app.json`, `eas.json`, `metro.config.*`, `babel.config.*`, `package.json` (RN deps), `ios/**`, `android/**`.

**If not triggered:** State `"Phase 2.6 skipped — no React Native / Expo files modified."` and proceed.

**Validation steps (all required when triggered):**

**Step 1 — Type + lint + unit safety:**
```
npm run typecheck
npm run lint
npm test -- --runInBand --watch=false
```
HARD STOP if any fail.

**Step 2 — Expo config + native prebuild sanity:**
```
npx expo config --json >/dev/null
npx expo-doctor
```
HARD STOP on invalid config, dependency mismatch, or doctor ERROR-level findings.

**Step 3 — Release-bundle parity check (Hermes/minified path):**
```
npx expo export --platform ios --output-dir /tmp/expo-export-ios
npx expo export --platform android --output-dir /tmp/expo-export-android
```
HARD STOP if export fails or bundle generation errors.

**Step 4 — Bundle-size guard (if app bundle output changed):**
- Compute JS bundle + assets size delta against baseline artifact.
- If exceeds SIZE_BUDGET_* lock: HARD STOP unless `SHORTCUT_SIZE_OVERRIDE` decision exists in Directus.

**Step 5 — Device capability + AI safety guard (iPad 9 / low-memory path):**
- Verify required runtime flags/features present (Hermes enabled; no unsupported APIs without fallback).
- Confirm startup entry path does not depend on `__DEV__` branches.
- For AI Coach integrations: confirm Claude API fallback (Haiku → Sonnet → Opus) survives simulated timeout. Run `python3 Production/scripts/ai_policy_replay.py` if the diff touches the coach router. HARD STOP if fallback breaks safety-layer continuity.

HARD STOP on any release-only incompatibility risk.

**Outcome declaration (required):**
- PASS: `"Phase 2.6 PASS — RN/Expo checks clean, release bundles generated, size budget [honored|N/A]"`
- HARD STOP: `"Phase 2.6 HARD STOP — [typecheck|lint|test|expo-config|release-export|size-budget|ai-safety] failure: <detail>"`

---

## PHASE 2.7: Firebase Actor Matrix Gate (BLOCKING — runs whenever Firebase security surface modified)

**Trigger:** Any diff touching `firestore.rules`, `firebase.json`, `firestore.indexes.json`, Cloud Functions auth/data paths, or Firestore access contract in app/server code.

**If not triggered:** State `"Phase 2.7 skipped — no Firebase access-control surface modified."` and proceed.

**Validation steps (all required when triggered):**

**Prerequisite — verify Firebase test deps (run before Step 1, once per app repo):**
```
node -e "require('@firebase/rules-unit-testing')" 2>/dev/null \
  || npm install --save-dev @firebase/rules-unit-testing firebase
```
If the install fails: HARD STOP — do not proceed to actor-matrix test.

**Step 1 — Run emulator-backed actor-matrix test:**
```bash
# From the MindfulNest app repo root:
npm run test:rules
```
*(Backed by `firestore-rules-test.yml` CI, which runs this automatically on every PR that touches Firebase paths. Run locally to verify before pushing. The prereq check above installs `@firebase/rules-unit-testing` if missing.)*

HARD STOP if script fails or any case errors.

**Step 2 — Required actor coverage (minimum — any missing actor = HARD STOP):**

| Actor | Required Positive | Required Negative |
|---|---|---|
| `child` | Own family docs | Cross-family docs |
| `parent` | Own family sessions | Cross-family sessions |
| `therapist` | Assigned family notes | Unassigned family notes |
| `unauthenticated` | — | All reads (PERMISSION_DENIED asserted) |

**Step 3 — Query-shape coverage (mandatory — all three required):**
- `get()` checks
- `list()`/`query` checks
- `collectionGroup` checks where applicable

HARD STOP if any query class is untested.

**Step 4 — Function-path parity:**
If a Cloud Function writes/reads guarded docs, verify equivalent actor restrictions enforced at function entry (not only client-side).
HARD STOP on parity mismatch.

**Outcome declaration (required):**
- PASS: `"Phase 2.7 PASS — Firebase actor matrix clean (child/parent/therapist/unauth × get/list/collectionGroup + positive/negative)"`
- HARD STOP: `"Phase 2.7 HARD STOP — Firebase actor matrix failure: <detail>"`

---

## PHASE 3: Counter-Agent Adversarial Review

**Cursor cross-review (OPTIONAL — Kim's call):**
Cursor is a useful second pair of eyes when Kim wants one — particularly for architectural decisions or when the implementation plan touches code Claude doesn't have full context on. Kim may request it; Claude may suggest it where it would clearly help. It is NOT required in any QA sequence and there is no "unavailable" declaration to make. If run, log findings alongside counter-agent input. If skipped, no acknowledgment needed.

Launch 1-2 agents with this structure:

**Discrepancy finder** — reads source spec + output, reports EVERY mismatch with severity + line numbers.

**Over-engineering checker** — finds anything in output that goes BEYOND spec. For each: "What failure mode does this prevent? If hypothetical — flag it."

Receive findings. Do NOT defend — if the agent misread something, that means it's ambiguous.


## PHASE 3.5: Cross-Model Boundary Diff (BLOCKING — runs whenever Phase 1.5 ran)

**What this catches:** Field-name mismatches between the JS client and the Python server that are invisible to Claude counter-agents because both sides share the same mental model and vocabulary. If Claude writes `i.name` in JS while the server returns `i.filename`, a same-model adversarial agent will often read both as "the name field" and declare them consistent. A verbatim key extraction and diff catches it.

**Trigger:** Runs whenever Phase 1.5 ran (i.e., whenever there are cross-boundary calls in the diff).

**If not triggered:** State "Phase 1.5 did not run — Phase 3.5 skipped."

### Step 1 — Claude-native verbatim extraction (ALWAYS runs; HARD STOP authority)

For every server handler → client consumer pair in the Phase 1.5 manifest:

1. **Extract Python return keys verbatim:** Read the handler function; list every top-level key in the `return self._send_json({...})` or `json.dumps({...})` call — literal strings only, no paraphrasing or summarizing.
2. **Extract JS property accesses verbatim:** Read the client fetch handler; list every `d.fieldName`, `r.fieldName`, `data.fieldName` property access on the parsed response — literal identifiers only.
3. **Diff the two lists:** Any identifier that appears in one list but not the other is a naming mismatch.
4. **HARD STOP if any mismatch found.** Fix in Phase 4. Do not defer.

**Output format (produce this table):**
```
BOUNDARY DIFF B-1 — POST /api/example:
  Python emits:  [key_a, key_b, key_c]
  JS reads:      [key_a, key_b, key_c]
  Delta: NONE — all keys match
```
or:
```
  Delta: Python has "slot_durations" / JS reads "slotDurations" → MISMATCH [CRITICAL]
```

### Step 2 — Cross-model second opinion (run when available; NEVER blocks on unavailability)

If a GPT-4o agent or separate Claude instance is accessible in this session, provide it the verbatim handler source and client consumer source and ask: "List every JSON key the server emits and every JSON key the client consumes. Do they match exactly?" Any `MISMATCH:` line returned is a HIGH finding — log it and fix before Phase 4.

**If no external model is available:** the Claude-native diff in Step 1 is sufficient. Log `"Phase 3.5: cross-model second opinion unavailable — native diff only"` in `prod_activity_log`. Phase 3.5 does NOT block on external model availability.

## PHASE 4: Fix + Re-Verify

1. Filter findings: CRITICAL and HIGH must fix. MEDIUM fix if quick. LOW document.
2. Apply surgical fixes (minimal, one per finding)
3. Recompile: `tsc --noEmit`
4. If 5+ CRITICAL/HIGH fixes or >20% code changed, re-run counter-agent

## PHASE 5: Blast Radius

1. List all changes made (new files, exports, config values, doc structure)
2. Define grep patterns for each change
3. Grep entire project for stale references (exclude archive/)
4. Update all active references using verified-edit or cross-document-update
5. Register locked decisions in Directus `prod_locked_decisions` (Python urllib.request)
6. Update `.auto-memory/` files and MEMORY.md index

## PHASE 6: Blind Spot Report

For each blind spot:

```
### Blind Spot N: [Title]
- What could go wrong: [description]
- Why I can't verify now: [root cause]
- Severity if materialized: CRITICAL / HIGH / MEDIUM / LOW
- Can fix now: Yes / No / Partial
- Recommendation: [Fix now / Requires runtime / Document and defer]
- Status: NO ACTION NEEDED / ACTION NEEDED
```

If Kim says "fix it now" — launch targeted agents, apply fixes, re-run Phase 3-4 on the fixes.


## PHASE 6.5: Live Boundary Probe (BLOCKING — runs whenever Phase 1.5 ran)

**What this catches:** Bugs where the handler branch EXISTS (Phase 1.5 manifest passed) but returns the wrong shape, wrong Content-Type, or wrong status. This is the only gate whose verifier input is NOT Claude's mental model — it is bytes from a running server.

**Pre-condition check (MANDATORY — per Rule 29):**
```
SERVER_PID=$(lsof -ti:<PORT> | head -1)
SERVER_START=$(ps -p $SERVER_PID -o lstart=)
PY_MTIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" <handler_file>)
# If SERVER_START < PY_MTIME → server is stale → restart before probing
```
If server predates the handler edit, restart. Running probes against a stale server is a false green.

**For every row in the Phase 1.5 manifest, run a probe:**

```python
# Production/tests/probes/<endpoint_id>_probe.py
import urllib.request, json, sys

PORT = 5111
for variant in VARIANTS:  # from manifest
    url = f"http://localhost:{PORT}{variant['path']}"
    resp = urllib.request.urlopen(url, timeout=5)
    ctype = resp.headers.get('Content-Type', '')
    body = resp.read()

    assert variant['expected_ctype'] in ctype,         f"FAIL B-{variant['id']}: expected Content-Type '{variant['expected_ctype']}', got '{ctype}'"

    if 'application/json' in ctype:
        data = json.loads(body)
        for key, typ in variant['expected_schema'].items():
            assert key in data, f"FAIL B-{variant['id']}: missing key '{key}'"
            assert isinstance(data[key], typ), f"FAIL B-{variant['id']}: '{key}' wrong type"

print("All boundary probes PASS")
```

Run: `python3 Production/tests/probes/<id>_probe.py`

**If any probe fails:** This is a Phase 2 regression — the handler was written but doesn't fulfill its contract. Fix the handler, re-run Phase 3-4 on the fix, re-run the probe. Do NOT proceed to Phase 7 with a failing probe.

**If probe fails AND Phase 1.5 manifest passed:** Log this as a **manifest-completeness gap** (the grep matched a branch, but the branch returns wrong shape). This is the harder bug class — the branch exists but is wrong. Flag for Phase 6 blind spot report.


**Valid-input probes for guarded endpoints:** If any handler contains an early-return guard (e.g., `if not slots: return 400` or `if not body: return 400`), the probe MUST include a second variant using the minimal valid input that bypasses the guard and reaches the actual handler body. A probe that only tests the 400 path does not confirm the happy path works — bugs in import paths, logic errors, and missing branches inside the guard are invisible without a valid-input probe. Add a `valid_input=True` variant row to the manifest for these endpoints.

**Proof:** Include probe stdout in Phase 7 verification table as "All boundary probes PASS" evidence.


## PHASE 6.6: Browser Console Gate (BLOCKING — runs whenever an HTML tool is produced or modified)

**What this catches:** JavaScript runtime errors that are invisible to Python probes. A Python probe confirms an endpoint returns HTTP 200 with the right JSON shape. It cannot catch that the client-side code throws `TypeError: Cannot read properties of undefined` when rendering that response into the DOM — which is what Kim sees as "button does nothing."

**Per DS-21 (V59 gap-fix Phase F, 2026-05-07):** This gate is a **HARD prerequisite for the phase COMPLETE row, mechanically enforced** in `Production/lib/directus.py::try_post_or_queue` via LD `BROWSER_SMOKE_MECHANICAL_GATE_V1`. Claude cannot skip this gate by self-discipline failure; the library rejects the `*_COMPLETE` write when no matching `KIM_BROWSER_SMOKE_PASSED` row exists. Override path requires `MN_SKIP_BROWSER_SMOKE_GATE=1` AND a `BROWSER_SMOKE_DEFERRED` audit row written FIRST (e.g. for infra-only phases with no UI surface).

**Trigger:** Any `.html` file added or modified in `Production/tools/` in this diff.

**If not triggered:** State "No HTML tool modified in this diff — Phase 6.6 skipped."

**If Chrome MCP is not connected:** State explicitly: `"Phase 6.6 SKIP — Chrome MCP not connected. Browser console errors remain a blind spot — ACTION NEEDED: manual click-through before delivery."` Do NOT leave the skip implicit or omit Phase 6.6 from the Phase 7 table.

### Steps (Chrome MCP)

1. `mcp__Claude_in_Chrome__navigate` → `http://localhost:<PORT>/<tool_path>`
2. `mcp__Claude_in_Chrome__read_console_messages` — baseline snapshot (note any pre-existing errors)
3. Click through the golden path: trigger every primary interactive element once — load library, click preview, click bake, tab switches, any modals. Use `mcp__Claude_in_Chrome__find` + left-click (or `browser_batch` for efficiency).
4. `mcp__Claude_in_Chrome__read_console_messages` — post-interaction snapshot
5. **Assert zero `console.error` entries from app code** (browser-extension noise is excluded). Any app-code error is a HARD STOP — fix the JavaScript, re-run Phase 3-4 on the fix, re-run this gate.
6. `console.warn` entries from app code: document each one in Phase 6 blind spot report. Not a hard stop, but must be named — not silently ignored.

**Outcome declaration (required):**
- PASS: `"Phase 6.6 PASS — 0 console.error, 0 network errors. Actions tested: [list]"`
- FAIL: `"Phase 6.6 FAIL — [N] console.error(s): [detail]. Fix before delivery."`
- SKIP: `"Phase 6.6 SKIP — Chrome MCP not connected. ACTION NEEDED before delivery."`


## PHASE 6.7: Mobile E2E + Invariant Gate (BLOCKING — Tier C or mobile behavior-critical flows modified)

**Trigger:** Any diff affecting gameplay, onboarding, dashboard/session tracking, navigation state, coin tally, offline sync, push resume, or animation timing — OR any Tier C execution context (release branch, nightly CI, App Store prep).

**If not triggered:** State `"Phase 6.7 skipped — no mobile behavior-critical flow modified and not Tier C context."` and proceed.

**Existing CI (already live — do NOT duplicate):**
`maestro-tier1.yml` runs automatically on every PR/push via GitHub Actions. Existing Maestro flows at `MindfulNest/maestro/flows/`:
- `smoke_launch.yaml` — app cold launch + navigation
- `full_module_flow.yaml` — gameplay loop end-to-end
- `home_screen.yaml` — home screen visibility + navigation
- `module_exit_smoke.yaml` — exit and resume paths

**Step 1 — Trigger CI or run locally:**
```bash
# CI: push to branch — maestro-tier1.yml fires automatically.
# Local (from MindfulNest app repo root, with device/simulator connected):
maestro test maestro/flows/
```
HARD STOP if any Maestro flow fails.

**Step 2 — Fault-path transitions (verify in `full_module_flow.yaml` or add steps):**
- Background → foreground
- Offline → online recovery
- App cold restart with persisted state
- Notification/deep-link resume

HARD STOP on state corruption, crash, or invariant break.

**Step 3 — Invariant assertions (must be present in flows or asserted separately):**
- Coin tally monotonic — no phantom increments
- Session IDs consistent across app + Firestore
- Role-based visibility invariants hold after sync/retry
- No duplicate side effects under retry/reconnect

*If any invariant is not yet asserted in the existing flows, add the assertion step to the relevant `.yaml` — do NOT skip and mark PASS.*

HARD STOP if any invariant violated.

**Step 4 — Crash + performance:**
- Zero fatal crashes in test run (CI surfaces these automatically)
- Frame-time within lock for tested scenes

HARD STOP on crash or budget breach.

**Outcome declaration (required):**
- PASS: `"Phase 6.7 PASS — Mobile E2E and invariants clean across iOS/Android release paths"`
- HARD STOP: `"Phase 6.7 HARD STOP — [E2E|invariant|crash|performance] failure: <detail>"`

---

## PHASE 6.8: Media Golden Probe (BLOCKING — runs whenever FFmpeg pipeline or shippable media output modified)

**Trigger:** Any diff touching the FFmpeg pipeline, lipsync composition, sprite/video render path, normalization step (LD-284), or generated shippable media assets.

**If not triggered:** State `"Phase 6.8 skipped — no media pipeline or shippable media output modified."` and proceed.

**Probe script:**
```
python3 Production/scripts/media_golden_probe.py \
  --candidate <candidate.mp4> \
  --golden <golden.mp4> \
  --target-dbfs <TARGET_DBFS>
```

**Assertions (all mandatory — any failure = HARD STOP):**

| # | Assertion | Threshold |
|---|---|---|
| 1 | Duration vs golden | ≤ ±50 ms |
| 2 | Frame rate | Exactly 24 fps |
| 3 | A/V sync drift | < 100 ms |
| 4 | Loudness vs target | ≤ ±1.0 dBFS |
| 5 | B-frames | Zero (`has_b_frames = 0`) |
| 6 | Decode errors | Zero (`ffmpeg -v error` pass) |

If any assertion fails: HARD STOP. Fix pipeline, regenerate candidate, re-run probe before Phase 7.

**Golden file management:** The golden file is the last Kim-approved output for that beat/segment, registered in `prod_assets` with `role='delivery'` and `kim_verdict='approved'`. Query via `Production/tools/find_asset.py` — never guess from disk filename (Rule 31, LD `DIRECTUS_BEFORE_DISK_GUESS_V1`).

**Outcome declaration (required):**
- PASS: `"Phase 6.8 PASS — Media golden probe clean (duration/fps/AV sync/loudness/B-frames/decode)"`
- HARD STOP: `"Phase 6.8 HARD STOP — Media probe failure: <detail>"`

---

## PHASE 7: Proof of Execution

Build verification table:

| Check | How Verified | Evidence | Status |
|---|---|---|---|
| [Criterion] | [test/grep/compile] | [line numbers, output] | PASS/FAIL |

All CRITICAL checks must show PASS. Present to Kim as the final deliverable.

### HARD RULE — No Static-Only Proof for Live Code (LD ZERO_ERROR_QA_LIVE_EXECUTION_V1)

**The following proof types are FORBIDDEN for any check that involves an HTTP endpoint, database write, subprocess call, or function that runs at user interaction time:**

- ❌ "Code looks correct" — not proof
- ❌ "grep confirms function exists" — not proof
- ❌ "server returns HTTP 200 on the index route" — not proof that functional routes work
- ❌ "smoke test passes" — not proof that API endpoints return correct shapes

**Required proof for every endpoint or handler introduced in this task:**
Show the ACTUAL output from a live call — the literal curl or Python urllib response including status code, Content-Type header, and response body (or first 200 bytes). This is the same output generated in Phase 6.5 probes. Copy it into the Phase 7 table as the Evidence field.

If Phase 6.5 ran: copy probe stdout here. Evidence field must contain actual server bytes, not a description of what the server should return.

If Phase 6.5 did not run (trivial/routine task with no new endpoints): still required to show at least one live call per new endpoint in the Evidence column. "No new endpoints in this diff" is a valid declaration — but must be stated explicitly.

**Why this rule exists:** The stitch editor was built with a complete Phase 0-7 QA pass. Phase 7 listed "HTTP 200 on /stitch_editor" as endpoint proof. Every functional API endpoint (`/library`, `/preview`, `/bake`, `/audio_extract`, etc.) was declared PASS based on code review alone. On first user interaction, every endpoint that was never called had bugs — wrong field names, wrong import paths, missing branches. Zero live calls = zero real proof. Static analysis is necessary but not sufficient. Actual bytes from a running server are the only ground truth. (Incident: 2026-04-26, stitch editor build.)

### Blind Spot Action Surface (MANDATORY — last act of Phase 7)

Before closing, confirm every blind spot from Phase 6 has been explicitly marked `NO ACTION NEEDED` or `ACTION NEEDED`. Then surface a consolidated list:

**Blind Spots — No Action Needed:**
- [Blind Spot N: title] — [one-line reason]

**Blind Spots — Action Needed:**
- [Blind Spot N: title] — [one-line action required]

If any blind spot was not assessed (missing Status field) → STOP. Go back to Phase 6 and assess it before closing. Present this surface summary to Kim as the final line of the QA output.

---

## PHASE 7.5: PR + Review Mechanics (BLOCKING for Tier B/C — runs after Phase 7 proof)

For Tier B (routine) and Tier C (architectural) tasks, Phase 7 proof of
execution is necessary but not sufficient. Code that ships goes through
PR review, branch protection, and AI review BEFORE merge. Phase 7.5
ensures these mechanics actually fire.

### Step 1 — PR open and pointing at correct base

- Run `gh pr view --json number,title,baseRefName,headRefName,state`
- If no PR exists for current branch → open one:
  `gh pr create --title "[task_id]: [one-line summary]" --body "[from Phase 7 table]"`
- Verify `baseRefName` is `main` (or designated integration branch).
- Verify `state=OPEN` (not draft unless intentional, not merged).

### Step 2 — AI review triggered

- Verify the AI review automation (CodeRabbit OR Claude API custom per
  V59_CICD_GAP_FIX_SPEC_v1.md gap #3) has commented on the PR.
- If no AI review comment within 10 min of PR creation → HALT, surface:
  "AI review didn't fire on PR #[N]. Check workflow permissions before
  merging."
- If AI review surfaced concerns: address them in a new commit, do NOT
  merge until concerns resolved.

### Step 3 — Branch protection rules satisfied

- For repos with branch protection (per V59_CICD_GAP_FIX_SPEC_v1.md
  gap #2): verify `gh pr checks` shows all required checks PASSING.
- Required check categories: CI (Playwright e2e), bundle size, AI
  review, deploy verification (where applicable per gap #1).
- If any required check is RED → HALT, do NOT use admin override.
- If any required check is PENDING → wait, then re-verify.

### Step 4 — Merge strategy declaration

State which merge strategy the PR will use:
- **Squash merge** (default for feature work): one clean commit on main.
- **Rebase merge** (preserve granularity): use only when each commit in
  the PR is independently meaningful.
- **Merge commit** (preserve PR boundary): use for release branch merges.

### Step 5 — Post-merge verification

After Kim approves merge:
- Confirm `main` HEAD is the expected SHA.
- Confirm CI on main is green: `gh run list --branch main --limit 1`.
- Confirm any auto-deploy workflow triggered (if applicable per gap #1).
- Update `prod_activity_log` with action `pr_merged_<pr_number>`.

### Output

Append to Phase 7 table:

| Check | How Verified | Evidence | Status |
|---|---|---|---|
| PR open + correct base | gh pr view | PR #[N] -> base=main, head=feature/[name] | PASS |
| AI review fired | gh pr view --comments | CodeRabbit comment at [timestamp] | PASS |
| Branch protection checks | gh pr checks | 5/5 required checks passing | PASS |
| Merge strategy | declaration | squash | PASS |
| Post-merge CI | gh run list --branch main --limit 1 | conclusion=success | PASS |

### When Phase 7.5 does NOT run

- **Tier A trivial tasks** (no PR required for typo fixes, comment-only
  edits, etc.) — state explicitly: "Phase 7.5 skipped — Tier A trivial."
- **Solo-dev session BEFORE the gap-fix spec is executed** (CI/CD
  infrastructure not yet built) — state: "Phase 7.5 deferred — CI/CD
  infrastructure pending V59_CICD_GAP_FIX_SPEC_v1.md execution. Use
  interim manual checklist (1: branch off main, 2: commit, 3: push,
  4: open PR via `gh pr create`, 5: self-review diff in PR view, 6:
  squash-merge after self-review)."

### Honest scope

Phase 7.5 is enforced by Claude self-discipline and `gh` CLI checks.
Branch protection rules and AI review automation are GitHub-side
controls — they enforce structurally, but only if configured correctly
per V59_CICD_GAP_FIX_SPEC_v1.md. This phase verifies the controls fired;
it does not guarantee they were configured. The weekly preflight audit
joins activity log against PR records to catch tasks that bypassed
Phase 7.5.

---

## Quick-Reference Checklist

```
PHASE 0: PRE-FLIGHT PROTOCOL (MANDATORY — HARD GATE)
[ ] Task classified (trivial / routine / architectural)
[ ] LD-262 classification sentence stated aloud — "Classifying: [TIER] — [criterion or none-apply]. Proceed?" (waited for Kim's yes if interactive; stated for audit if autonomous)
[ ] 3-sentence preflight summary written
[ ] Required agents spawned (0 / 1+1 / 4+4) per task_type
[ ] All CRITICAL/HIGH counter-agent weaknesses addressed or escalated
[ ] Row written to Directus prod_preflight_reviews
[ ] Row confirmed via read-back (task_id match)
[ ] approved_to_proceed = true
[ ] Step 1.6 git hygiene check: clean tree | feature branch | CI not red | fetch fresh — HALT if any anomaly (autonomous; only surfaces on real problem)

PHASE 1: ERROR CATEGORIES
[ ] Master error table created with severity ratings
[ ] Size-Budget Detection Gate three boxes checked if any shippable asset produced (SIZE_BUDGET_V1 / LD-283)
[ ] Kim approved (if async)

PHASE 1.5: BOUNDARY CONTRACT MANIFEST (if any cross-boundary call in diff)
[ ] Trigger declared: cross-boundary calls listed OR "Phase 1.5 skipped — no cross-boundary calls"
[ ] Manifest table produced: one row per boundary call, every query_variant listed
[ ] Every variant grep-matched to a callee branch (grep returns ≥1 line) — HARD STOP if any variant unmatched
[ ] Callee handler read verbatim (not from summary) if file >200 lines

PHASE 2: EXECUTE
[ ] Execution plan ordered
[ ] Code/docs written mechanically from spec
[ ] tsc --noEmit passes

PHASE 2.5: PYTHON VALIDATION GATE (if any .py file modified)
[ ] Trigger declared: modified .py files listed OR "Phase 2.5 skipped — no .py files modified"
[ ] python3 -m py_compile passes on all modified files — HARD STOP if any fail
[ ] New imports verified by running python3 -c "import <module>" (not just "looks correct")
[ ] Smoke-test run if production_server.py or its imports modified (10s timeout); WARN declared if fails; never silently skipped

PHASE 2.6: REACT NATIVE / EXPO VALIDATION GATE (if RN/Expo surface modified)
[ ] Trigger declared: RN/Expo files listed OR "Phase 2.6 skipped — no RN/Expo files modified"
[ ] npm run typecheck + lint + test all pass — HARD STOP if any fail
[ ] npx expo config + expo-doctor clean — HARD STOP on ERROR-level findings
[ ] Release export executed for iOS + Android — HARD STOP on export failure
[ ] Bundle-size decision honored or SHORTCUT_SIZE_OVERRIDE exists in Directus
[ ] AI Coach router tested via ai_policy_replay.py if coach diff in scope

PHASE 2.7: FIREBASE ACTOR MATRIX GATE (if Firebase/rules/functions surface modified)
[ ] Trigger declared: Firebase files listed OR "Phase 2.7 skipped — no Firebase access-control surface modified"
[ ] npm run test:rules passes (from MindfulNest app repo root) — HARD STOP if fails; same suite as firestore-rules-test.yml CI
[ ] child/parent/therapist + unauth positive/negative coverage present
[ ] get()/list()/collectionGroup all covered — HARD STOP if any class untested
[ ] Negative cases assert PERMISSION_DENIED
[ ] Function-path parity verified — HARD STOP on mismatch

PHASE 3: ADVERSARIAL REVIEW
[ ] Counter-agent(s) launched with spec + output
[ ] All findings received with severity + line numbers
[ ] Cursor cross-review: optional — log findings if performed, otherwise no acknowledgment needed

PHASE 3.5: CROSS-MODEL BOUNDARY DIFF (if Phase 1.5 ran)
[ ] Trigger declared: "Phase 3.5 runs — Phase 1.5 ran" OR "Phase 3.5 skipped — Phase 1.5 did not run"
[ ] Python return keys extracted verbatim from handler return/json.dumps
[ ] JS property accesses extracted verbatim from client fetch handler
[ ] Key lists diffed — HARD STOP if any mismatch; fix before Phase 4
[ ] Cross-model second opinion: run if available; "unavailable — native diff only" logged if not (never blocks)

PHASE 4: FIX
[ ] CRITICAL/HIGH findings fixed
[ ] Recompilation passes
[ ] Re-review if substantial changes

PHASE 5: BLAST RADIUS
[ ] Changes enumerated
[ ] Project grepped for stale references
[ ] All active references updated
[ ] Locked decisions registered in Directus
[ ] Memory files updated

PHASE 6: BLIND SPOTS
[ ] Blind spots identified with severity
[ ] Every blind spot explicitly marked NO ACTION NEEDED or ACTION NEEDED
[ ] Report delivered to Kim
[ ] Any "fix now" items addressed

PHASE 6.5: LIVE BOUNDARY PROBE (if Phase 1.5 ran)
[ ] Server staleness check: PID start-time AFTER handler file mtime (Rule 29) — restart if stale
[ ] Probe script written for every manifest row: asserts HTTP status + Content-Type + JSON shape
[ ] Valid-input variant included for any handler with early-return guard (not just error-path probe)
[ ] All probes exit 0 — HARD STOP if any probe fails; fix handler + re-run Phase 3-4 first
[ ] Probe stdout included as evidence in Phase 7 table

PHASE 6.6: BROWSER CONSOLE GATE (if any Production/tools/*.html modified)
[ ] Trigger declared: HTML file listed OR "Phase 6.6 skipped — no HTML tool modified"
[ ] If Chrome MCP unavailable: explicit SKIP declared in Phase 7 table with ACTION NEEDED (not void)
[ ] Navigated to tool URL; baseline console read
[ ] Clicked through golden path (every primary interactive element triggered once)
[ ] Zero console.error from app code — HARD STOP if any found; fix JS + re-run Phase 3-4 first
[ ] console.warn entries from app code documented in Phase 6 blind spot report
[ ] Console capture included as evidence in Phase 7 table

PHASE 6.7: MOBILE E2E + INVARIANT GATE (Tier C or mobile behavior-critical flow modified)
[ ] Trigger declared: flow/Tier C listed OR "Phase 6.7 skipped — not triggered"
[ ] maestro-tier1.yml CI passed OR `maestro test maestro/flows/` run locally — HARD STOP if any flow fails
[ ] Fault-path transitions executed (background/offline/restart/deep-link) — HARD STOP on state corruption
[ ] Invariant assertions: coin tally monotonic, session IDs consistent, role-visibility holds — HARD STOP on violation
[ ] Zero fatal crashes + frame-time within performance lock

PHASE 6.8: MEDIA GOLDEN PROBE (if FFmpeg pipeline or shippable media output modified)
[ ] Trigger declared: media pipeline files listed OR "Phase 6.8 skipped — no media output modified"
[ ] Candidate + golden artifacts identified (golden queried via find_asset.py, never guessed from disk)
[ ] Duration tolerance ≤ ±50ms — HARD STOP if fails
[ ] Frame rate exactly 24fps — HARD STOP if fails
[ ] A/V sync drift < 100ms — HARD STOP if fails
[ ] Loudness within ±1dBFS target — HARD STOP if fails
[ ] Zero B-frames + zero decode errors — HARD STOP if fails

PHASE 7: PROOF
[ ] Verification table with evidence
[ ] All CRITICAL checks PASS
[ ] LIVE EXECUTION: every new/modified HTTP endpoint shows actual curl/Python response output in Evidence column — no static-only proof accepted
[ ] If no new endpoints: explicit statement "No new endpoints in this diff" in table
[ ] Table presented to Kim
[ ] Blind Spot Action Surface completed — all blind spots assessed, ACTION NEEDED items surfaced to Kim

PHASE 7.5: PR + REVIEW MECHANICS (Tier B/C — runs after Phase 7)
[ ] Trigger declared: Tier B/C task running OR "Phase 7.5 skipped — Tier A trivial" OR "Phase 7.5 deferred — CI/CD infra pending gap-fix"
[ ] PR open via gh pr view (or created via gh pr create) — base=main, state=OPEN
[ ] AI review fired (CodeRabbit / Claude API custom comment present within 10 min)
[ ] Branch protection: gh pr checks shows all required checks PASS (no admin override on red)
[ ] Merge strategy declared (squash / rebase / merge commit)
[ ] Post-merge: main HEAD verified, CI green, prod_activity_log row written
```

## Skill Integration

| Skill | When Used |
|---|---|
| `verified-edit` | Phase 5 — surgical edits across documents |
| `cross-document-update` | Phase 5 — cascading changes |
| `dashboard-ops` | Phase 5 — Directus API calls |
| `dashboard-gate` | Phase 5 — session start protocol |
| Any production skill | Load zero-error-qa AFTER finishing work to verify |

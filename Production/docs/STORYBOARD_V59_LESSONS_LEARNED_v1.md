# Storyboard v59 — Lessons Learned (Weekend 2026-05-03/04)

**Date:** 2026-05-04
**Scope:** Lessons distilled from the v59 storyboard rewrite + the painful retroactive bug-discovery weekend (Sat 2026-05-03 → Mon 2026-05-04). Captures meta-patterns that should drive future work — both for the rest of the storyboard tool and for the MindfulNest app itself.
**Predecessor:** `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` (LL-1..LL-25 from the architecture revision); this doc adds LL-26..LL-40 from the post-architecture work.
**Companion:** `STORYBOARD_V59_ARCHITECTURE_OVERVIEW_v1.md` (this doc's "what" partner)

## §1 The single biggest lesson — discipline before features, not after

The v59 storyboard tool burned **24-32 engineer-hours over one weekend** on retroactive structural fixes (PR #1 proper-fix + PR #2 retroactive coverage + PR #4 architectural fix) for problems that would have cost zero hours had the structural pieces been in place before the first feature shipped:

- Mandatory e2e on every commit
- Tree-wide grep gates enforcing architectural patterns
- Test-with-feature spec template (no "future" comments)
- Schema lockfile + drift-fails-CI
- Silent-failure → fail-loud server hygiene

The retrofit cost was not "5 minutes per fix." It was 4 PRs, multiple Cursor review rounds, multi-session parallel orchestration, and 17 NEW LDs codifying what the discipline should have been from day 1.

**LL-26 (HARD):** Apply this lesson to the MindfulNest app — install foundation discipline BEFORE feature 1, not retroactively. Captured in `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` (LD-518) + master tech spec §14.13 + v6.2 changelog.

## §2 Convention-only architectural rules erode silently

`pathappPatch` was the canonical mutation channel by **convention**. Over months of feature work, raw `fetch()` calls slipped in:

- StitcherTab.tsx: 3 sites (preview / bake / save_job) — bypassed scope auto-injection, snapshot, 409/423 handling
- VideoSelector.tsx: 2 sites (set_active / create) — same bypass; one site **caused real test pollution** during retroactive sprint v1 (S6.7 mutated state.json globally, broke R1.1 next run)
- ProjectSelector × 2, EventSelector × 1, ProductionMapTab × 1 — discovered AFTER the grep gate landed (4 NEW prod_blockers #50-53 logged, deferred to Sprint D / Wave 3)

**Nine total raw-fetch sites** in a codebase whose authoritative rule was "all mutations through pathappPatch." Convention without mechanical enforcement = guaranteed drift.

**LL-27 (HARD):** Every architectural rule needs a structural enforcement gate (CI grep, ESLint custom rule, TypeScript brand type, runtime assertion) — not a "well, the convention is..." promise. Captured as `MUTATION_CHANNEL_INVARIANT_V1` (LD-519) for the storyboard; pattern generalized to the app via foundation spec Piece 3.

## §3 "Server-side gates green" ≠ "user-visible correctness"

S5.5c+e shipped 2026-05-03 with **31/31 server-side gates green**. Browser smoke (Kim hands-on, ~10 minutes) immediately surfaced 5 distinct integration bugs. Cursor v9 named the pattern: "'future' comments + server-only gates without Playwright/e2e on critical paths."

The "future" comments were the smoking gun. `LibraryPanel.tsx:6` literally said:
```
// TODO: drag-drop wired in a future session
```
Code shipped with the documented intent that critical behavior was deferred. Server tests passed because they didn't exercise drag-drop. Nobody noticed until Kim tried to use it.

**LL-28 (HARD):** No "future" comments in shipped code. If a behavior isn't done, it isn't shipped. Codified as part of `MANDATORY_E2E_GATE_V1` (LD-507) + spec template requirement.

## §4 Schema migrations are silent

Between 2026-04-28 (last DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md snapshot) and 2026-05-04 (S5.5c+e proper-fix terminal hit deviations), four `prod_locked_decisions` enum fields silently migrated:

- `severity`: `{CRITICAL, HIGH, MEDIUM, LOW}` → `{HARD, SOFT}`
- `scope_domain`: `{app-dev, cross-cutting, infra}` → added `content`, `production`
- `task_category`: 30+ values → restricted to 11 live choices
- `enforcement_type`: open enum → 10 specific values

**Crucially: write validators did NOT reject old values.** Historical rows still hold the old enum values; the schema choices changed but row data and validation didn't migrate. Mixed-enum coexistence became the steady state.

**LL-29 (SOFT):** Always re-verify enum choices via `GET /fields/<collection>/<field>` before writing handoffs that target enum fields. Don't trust documentation older than the last live schema snapshot. Captured in REFERENCE.md "Enum migration note 2026-05-04" + auto-memory entry `feedback_directus_schema_canonical.md`.

## §5 Cursor's file-cache lag — paste content verbatim, not paths

Cursor reads files from disk but its cache lagged Dropbox sync **at least twice this weekend**. Symptoms:
- Cursor reported R1-R6 not folded when they WERE folded on disk (verified via mtime + grep)
- Cursor cited "stale AF.1.1 line at 108" against a file where line 108 was different content

Each stale-cache incident wasted a Cursor round-trip. Solution that worked: paste the actual file content **verbatim quoted** in the Cursor prompt and ask "verify against this quoted text, not your read."

**LL-30 (SOFT):** When Cursor reports something contradicting what you just verified on disk, assume Cursor cache is stale. Verify disk truth via `wc -l`, `grep -c`, and `stat -f "%Sm"`. Re-paste with quoted content rather than a re-read directive. Don't burn cycles arguing with stale data.

## §6 Worktree parallelism works — for non-overlapping surfaces

S5.5f and retroactive coverage sprint v1 ran in **parallel via separate git worktrees**:
- S5.5f at `~/Projects/mindfulnest-tooling-s5_5f/` on `claude/s5_5f`
- Retroactive at `~/Projects/mindfulnest-tooling-retro/` on `claude/retroactive-coverage-sprint`

Each terminal had its own working dir, own branch, own context. Zero file conflicts. Both PRs merged cleanly (PR #2 first, then PR #3 with one workflow YAML conflict resolved via merge commit `fc8ac92`).

**Constraint:** worktree parallelism only works when surfaces don't overlap. If two sessions both touch `helpers.ts` or `playwright_e2e.yml`, merge cost balloons. Cursor's review correctly flagged this in the comprehensive plan §4.1 interleave guardrail.

**LL-31 (SOFT):** Use git worktree for parallel sessions when (a) the surfaces don't overlap and (b) each session can checkpoint independently. Do not run more than 2-3 parallel terminals at once — coordination overhead exceeds parallelism gain past that.

## §7 Tests-only sprint discipline (the retroactive coverage v1 pattern)

The retroactive coverage sprint v1 covered 6 surfaces with 41 tests in ~3 hours and **found 4 prod_blockers** (#46-49). Critical discipline that made it work:

- **HARD RULE: tests only, no inline fixes.** When a test surfaced a bug, log it as a `prod_blocker` row + `test.fixme` quarantine, do NOT diagnose deeply, do NOT propose fixes inline.
- **Fixture pinning.** Tests use `Production/Event_e2e_fixture/` only — never live `Event_1/` or `Event_2/`. Prevents test pollution AND prevents tests breaking when Kim authors new content.
- **Critical-path tests never quarantined.** Only NEW retroactive tests can be quarantined for flake; the proper-fix R-tests + s5_5f F-gates stay green or block merge.

The discipline let one sprint cover 6 surfaces in 3 hours. Mixing test-writing with bug-fixing would have produced 1 surface fixed in 3 hours.

**LL-32 (HARD):** Decouple discovery from repair. Tests-only sprints surface bugs; dedicated fix sessions resolve them. Codified in `STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md` §2 (5 hard rules) + `STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md`.

## §8 "Do not leave bugs" cannot mean zero bugs

Kim said "do not leave bugs" mid-weekend after seeing the 6-wave retroactive coverage plan was scoped down to "Sprint A mandatory + others opportunistic." The first response to that direction was over-correction: I drafted "all 6 waves mandatory" framing. **Cursor's second-opinion review (2026-05-04) correctly pushed back** — no methodology delivers 100% bug elimination; the right framing is "every honest discovery technique we have, fixing what we find, structurally preventing recurrence."

The plan now distinguishes:
- What "do not leave bugs" CAN deliver: every wave runs end-to-end if executed; structural enforcement gates per pattern; full activity trail
- What no methodology CAN: race conditions, timing-dependent behavior, browser-specific quirks, visual / a11y / performance — separate programs

**LL-33 (HARD):** Reframe anxious directives ("do not leave bugs") into honest deliverables ("here's what discipline delivers + here's the residual"). Don't tell Kim what she wants to hear; tell her what the methodology can actually achieve. Codified in the comprehensive plan §0.

## §9 Spec versioning + Cursor multi-round review patterns

Two specs went through 5+ round-trips of Cursor review this weekend:

- **Architectural fix spec:** Cursor v11 returned R1-R6 → folded → Cursor v12 returned 1 cleanup → folded → APPROVE
- **S5.5g spec:** Cursor v11 returned 5 R-rows on §19 amendment → folded → APPROVE

What worked:
1. Author the spec with §13 self-checklist asking the questions Cursor should weigh
2. Send to Cursor with explicit "review against §13" prompt
3. Cursor appends §14 with R-rows
4. Fold each R-row mechanically with §15 fold log documenting where each landed
5. Re-paste with §15 + ask Cursor to verify each landed correctly
6. APPROVE or another round of R-rows

The fold log discipline prevented Cursor from re-raising already-addressed issues and gave us a paper trail of what changed and why.

**LL-34 (SOFT):** Every Cursor review pass appends a §14-style audit trail; every fold pass appends a §15 fold log mapping R-row → location-applied. Don't squash review history; it's the audit record.

## §10 Master tech spec surgical insertion technique

The master tech spec (`MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` at Dropbox root) is a load-bearing reference. Adding the `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1` (LD-518) pointer required surgical insertion. Working pattern:

1. **Backup before edit:** `cp <spec> /tmp/<spec>.pre_<change>_<ts>.md`
2. **Multipass diff:** read file twice with different offsets, count headings + total lines, capture last line
3. **Edit tool only** (never Write — Write replaces; Edit only changes specified strings)
4. **Additive only:** insertion adds lines, NEVER replaces existing content
5. **Post-edit verification:** count headings + total lines + last line; assert deltas match exactly the inserted content
6. **No structural breakage:** assert markdown still parses (no orphan code blocks, no broken tables)

Applied successfully to v6.2 changelog + §14.13 row addition (5 lines added, 0 removed, last line unchanged).

**LL-35 (SOFT):** Surgical edits to canonical reference docs follow the 6-step pattern above. Backup → multipass diff → Edit tool → additive only → verify line counts + last line → markdown parse check. Codify in any tech-spec skill.

## §11 Tech-spec methodology with parallel sub-agents (or steelmanned inline)

The app architecture foundation spec was drafted via Opus agent using tech-spec methodology. The agent wanted to spawn parallel sub-agents (advocate "minimal foundation" vs counter "comprehensive foundation") but **Task tool was unavailable in its session**. Instead it steelmanned both positions inline + produced a 6-row divergence table making the resolution principled rather than reflexive.

Result: counter won 5/6, hybrid on 6th (custom ESLint rules / grep gates speculative vs as-needed). Cursor reviewed the synthesis + APPROVED.

**LL-36 (SOFT):** Tech-spec dual-perspective debate works inline OR via parallel sub-agents. Inline requires the author to explicitly steelman both positions + produce a divergence table; parallel agents require Task tool. When Task is unavailable, inline + divergence table is the documented fallback. Don't ship a spec without the dual-perspective synthesis — it's the load-bearing rigor that distinguishes spec from preference.

## §12 Cred plumbing across machines (Doppler + fallback)

Wave 1 architectural fix terminal hit a Directus cred issue: locally, `DIRECTUS_EMAIL` / `DIRECTUS_PASSWORD` env vars weren't set, but Doppler exports them as `DIRECTUS_ADMIN_EMAIL` / `DIRECTUS_ADMIN_PASSWORD`. The server's dlock required the bare `DIRECTUS_*` form; CI workflow had already mapped both forms but local hadn't.

Workaround:
```bash
eval "$(doppler secrets download --project mindfulnest --config dev --no-file --format env)"
export DIRECTUS_EMAIL="$DIRECTUS_ADMIN_EMAIL"
export DIRECTUS_PASSWORD="$DIRECTUS_ADMIN_PASSWORD"
```

Plus the fallback at `directus_admin_client._candidate_keys_paths` reads `Production/API_KEYS_MASTER.md` from Dropbox. So local Mac dev works without env var setup; CI requires explicit GitHub Secrets.

**LL-37 (SOFT):** When introducing any new server endpoint or test that hits Directus from CI, verify both env var forms (DIRECTUS_EMAIL/PASSWORD AND DIRECTUS_ADMIN_EMAIL/PASSWORD) are mapped in the workflow. Audit doc captures this for the Phase B-I session.

## §13 Sidecar / silent-failure pattern is a server-wide concern

F-SVR-001 was ONE silent failure site at `production_server.py:3899` (sidecar TypeError). Wave 1 fixed it via root-cause `isinstance` guard at line 3885. But the **pattern** (caught exception → log + continue without raising) likely exists in other server locations not surfaced by the retroactive sprint's 6 client-focused surfaces.

Sprint E (Wave 4) is specifically for this: server-side audit of silent-failure pattern beyond F-SVR-001. Recommended near-term per Cursor 2026-05-04 because silent server failures CAN surface during normal operation without new code touches (background jobs, file writes, edge data shapes, concurrency timing).

**LL-38 (HARD):** Server-side silent-failure pattern audit is its own program (Sprint E / Wave 4). Captured as `SERVER_SILENT_FAILURE_FAIL_LOUD_V1` (LD-520) which mandates fail-loud-or-fail-request behavior; Sprint E enforces tree-wide.

## §14 Mid-session compaction-aware checkpoints

S5.5f and S5.5g both checkpointed at the Phase A boundary because the full session estimate (5-7 hr / 1500-2000 LOC) reliably exceeded one Claude session's context budget. The pattern that worked:

1. Spec includes explicit **compaction-aware checkpoint authority** at named atomic boundaries
2. Terminal that hits the boundary writes a **continuation handoff doc** + activity_log row + commits Phase A artifacts
3. Fresh terminal opens via the continuation handoff (read first), inheriting all locked decisions
4. Phase B-I work happens in the fresh session

This is NOT failure — it's spec-authorized discipline. Mid-Phase checkpoints are forbidden; phase-boundary checkpoints are encouraged.

**LL-39 (SOFT):** Sessions estimated > 4 hr explicitly authorize compaction-aware checkpoints at named atomic boundaries. Continuation handoff doc + activity_log row + commits → fresh session inherits cleanly. Codified across S5.5f §19 + Wave 1 spec § + S5.5g §19.

## §15 The "audit doc" as canonical-snapshot pattern

S5.5g Phase A produced `STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md` (321 lines) capturing:
- Server contract reverse-engineering (line numbers, body shapes)
- Spec line-number drift documentation (8434 → 8507, 14659 → 14897, 14824 → 14920-14938)
- Schema findings (silent field drops on 2 collections)
- Decision rationale for trim backend, transition kind, dissolve scope
- 3 open questions for Kim before Phase B

The audit doc became authoritative for the Phase B-I session — fresh terminal reads it FIRST + inherits all the line-number corrections + locked decisions. Spec body stays as historical reference; audit doc is the live snapshot.

**LL-40 (SOFT):** When a Phase A audit surfaces drift between spec body + actual code, capture it in a Phase A audit doc that the Phase B-I terminal reads as canonical. Don't churn the spec body unless Phase I closeout demands it.

---

## §16 Meta-summary — the load-bearing pieces

Distilled from LL-26..LL-40, the discipline that should drive future work:

1. **CI from commit 1, no exceptions** (LL-26)
2. **Structural enforcement, not convention** (LL-27)
3. **No "future" comments** (LL-28)
4. **Re-verify schema enums before writes** (LL-29)
5. **Worktree parallelism for non-overlapping surfaces** (LL-31)
6. **Tests-only sprint discipline** (LL-32)
7. **Honest framing — no zero-bug promises** (LL-33)
8. **Cursor multi-round review with audit trails** (LL-34)
9. **Surgical edits to canonical docs** (LL-35)
10. **Tech-spec dual-perspective debate** (LL-36)
11. **Compaction-aware checkpoints at phase boundaries** (LL-39)
12. **Audit doc as canonical snapshot when spec drifts from code** (LL-40)

The app foundation spec (LD-518) operationalizes #1-#3 + #6-#7 for app-side work. The remaining lessons (#4, #5, #8-#12) are session-level practices captured here for future reference.

---

## §16.5 LL-41..LL-43 added post-S5.5g (2026-05-04 evening)

These three lessons emerged from S5.5g Phase B-I execution + closeout. They extend §16's load-bearing summary.

### LL-41 — e2e tests can pass while server-side logic is broken (route-level mocking limitation)

S5.5g Phase E surfaced a real coverage gap: G12 + G13 e2e tests for Production Map multi-event mapping passed during Phase E RED, BEFORE the server-side fix (`_handle_production_map` convention `Event_<m_num>` mapping at `production_server.py:8537`) was committed. Reason: the e2e tests mock `/api/production/map` at the Playwright route level, so the server bug never reached the UI under test.

**The tests are UI contract tests, not server-side tests.** They verify "given a correct map response, the UI renders + navigates correctly" — but they don't exercise "does the server actually return correct data?"

**Operational implication:** route-level mocking + e2e CI gate is NOT sufficient to catch server-side regressions. Sprint E (server audit) is the right program to close this — it would add server-side tests that hit the real `_handle_production_map` handler against fixture data and assert correct event_dir resolution per module.

**LL-41 (HARD):** When an e2e test mocks an API route, document explicitly that the test does NOT exercise server-side logic for that route. Server-side coverage requires either (a) an integration test that hits the real handler, or (b) a unit test on the handler function. Mock-based e2e tests close the UI contract; they do not close the server contract. Codify in Sprint E spec when authored.

### LL-42 — CSS-with-feature ordering (don't ship classes without styles)

S5.5g Phase B GREEN's first attempt failed because the new CSS classes (`.mn-stitcher-slot-waveform`, `.mn-stitcher-module-timeline`, etc.) were introduced in TSX render output WITHOUT corresponding style rules in `app.css`. Result: elements rendered with zero size; Playwright's `expect(...).toBeVisible()` failed the visibility check (a zero-size element is "not visible" by Playwright's default rules). Fixed in `bf59c66` by adding the CSS block. Cost: one extra commit.

**LL-42 (SOFT):** When a feature commit introduces new CSS classes, the same commit MUST include the style rules. Splitting "introduce class" from "style class" produces zero-size elements that fail Playwright visibility assertions for non-product reasons. Self-evident in retrospect; missed in the moment because tests were written first (correctly, per DS-2 TDD) and feature code was being landed before styles. Mitigation: a feature commit checklist item — "if I introduced new class names, did I also add the styles?" — or an ESLint rule that lints class names against the project's stylesheet.

### LL-43 — Phase-boundary commit + push works across long sessions (DS-12 validated empirically)

S5.5g Phase B-I proved DS-12 (phase boundary commit + push) at scale: 11 commits across 6 phases, each phase ending with tests committed → feature code committed → CI confirmed green BEFORE advancing. No mid-phase checkpoints. No half-built branch states. The session estimated at 5-7 hr completed in one terminal context with clean atomic phase boundaries.

**LL-43 (SOFT):** DS-12 phase-boundary discipline is operationally proven for sessions up to ~8 hr / ~3000 LOC / ~16 gates. Sessions exceeding that envelope should still rely on compaction-aware checkpoint authority at named phase boundaries. Don't assume "this one will fit" — declare checkpoint authority explicitly in the handoff so terminal Claude has permission to halt cleanly if the budget runs out.

---

## §17 References

- LD-505 TOOLING_REPO_CREATED_V1 → tooling repo + boundary
- LD-506-510 (proper-fix family) → 5 R-bugs + CI gate + e2e standard
- LD-511 RETROACTIVE_COVERAGE_SPRINT_V1_COMPLETE → discovery sprint
- LD-512-517 (S5.5f family) → Phase A/B parity infrastructure
- LD-518 MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1 → app foundation
- LD-519-521 (Wave 1 family) → mutation channel + fail-loud + requirements.txt
- `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` (Dropbox root) §14.13 + v6.2 changelog
- `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` (LL-1..LL-25 from prior session)
- `STORYBOARD_V59_ARCHITECTURE_OVERVIEW_v1.md` (companion architectural reference)

**End of Lessons Learned v1.**

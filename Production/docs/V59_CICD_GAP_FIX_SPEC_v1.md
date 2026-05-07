# Technical Spec: MindfulNest CI/CD Gap-Fix v1
Date: 2026-05-06
Produced by: tech-spec skill (dual-Opus debate research + Kim §13 LOCKED scope = "complete 20%, leverage 80%")

---

## §0 — Mandatory Operating Mode for Executing Sessions

**This section is read FIRST by every terminal session executing any phase of this spec. Do not skip. Do not skim. The §0 preamble is the recovery + prevention layer for the failure classes documented in tech-spec SKILL.md.**

### §0.1 — Skill load + Phase 0 classification (Rule 19)
- Load `zero-error-qa` skill before any edit in any phase below.
- Classify each phase per Tier A (Routine, 0 agents) / B (Cross-cutting, 1+1 agents) / C (Architectural, 4+4 agents). Per-phase classifications are stated explicitly in §4.
- Write a `prod_preflight_reviews` row via `try_post_or_queue` BEFORE any edit (Rule 35). One preflight row per phase. Reference this spec's path + the predecessor phase's preflight id.

### §0.2 — Six-Layer Verification Contract
For every feature this spec touches, NOT done until ALL six verify:
1. UI / surface element exists (workflow file present, hook installed, LD row written).
2. UI → backend wiring (right payload, right field names — Rule 35 schema verify).
3. Backend processing matches intent (server / GitHub Actions actually USES the input).
4. State update propagation (right partition, right metadata — `prod_locked_decisions`, `prod_activity_log`).
5. Surface re-render reflects new state (PR check appears, deploy log shows verification, hook blocks commit).
6. End-to-end smoke: vary input → output changes meaningfully (intentionally fail a check; confirm gate fires; revert).

**Layer 6 fail = RELEASE-BLOCKER for the phase, not partial completion.** Document any Layer 6 deferral as a Kim-hands-on browser/CLI smoke per §0.10.

### §0.3 — Eight Risk Classes for Silent Failure
Identify which apply per phase; add explicit smoke tests:
- AI-driven (input dropped or AI ignores it) — applies to Phase C (AI review automation)
- Multi-stage pipelines (stage N silently fails) — applies to Phase A (deploy script)
- Async / fire-and-forget (success/failure not surfaced) — applies to Phase D (RN workflows), Phase E (Playwright specs)
- Drag-drop (wrong asset/format/target) — N/A for this spec
- Side-effect captures (works 95%, skipped on edges) — applies to Phase G (pre-commit hook)
- Cost / metric displays (hardcoded estimates) — N/A
- Conditional rendering (happy path tested, edges fail) — applies to Phase A (only fires on dist mismatch)
- State persistence (works in-session, fails on refresh) — applies to Phase G (hook state across sessions)

### §0.4 — Authoring Discipline
1. Don't invent UI specifics — LOOSE terms unless cited (LD or Kim chat).
2. Don't hallucinate endpoint names — grep endpoints catalog first.
3. Verify field names per Rule 35 (DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md) before any `prod_*` write.
4. Verify agent claims against code via Read/Glob (don't recurse with more agents).
5. 6-layer end-to-end verification on every functional item.
6. Browser/CLI smoke mandatory after surface work (per phase: a curl GET, a hook fire, a PR comment).
7. Per-bug classification before patching (status audit FIRST).
8. Don't recommend legacy tool when new has gaps.
9. Author handoffs AFTER predecessor ships (not during).
10. Tech-spec skill for "wrong architectural model"; not quick patches.
11. "Already wired" / "exists" in docs is NOT proof — confirm at runtime.
12. Rule 32 absolute http://localhost:PORT URLs in production tool fetch() calls.

### §0.5 — Don't Rely on Memory or Guess
*"do not rely on memory or guess, always make sure to check all the way to the end, rather than assuming."*
- Read every file you reference; re-read at phase boundaries.
- Per Rule 24 confidence annotation: tag claims `[CONFIRMED against <source>]` / `[INFERRED — verify]` / `[GUESSED]` when reporting status to Kim.
- Existing infrastructure citations in §2 are tagged `[CONFIRMED]` against the user's locked-scope statement; verify at session start (workflow files exist? deploy script exists? LD rows present?).

### §0.6 — Tail-End Independent Verifier Subagent (Recommended)
At end of each phase, BEFORE marking COMPLETE: spawn an Explore agent for independent end-to-end verification. Spot-check 5-10 random items via the 6-layer contract. Pattern proven in S5.5a1 + a2 + b.

### §0.7 — Standing Rules Reference
Rules: 18 (activity log), 19 (no shortcuts), 24 (confidence annotation), 26 (Opus escalation), 27 (delete obsolete), 29 (server staleness check), 32 (absolute URLs), 33 (verify server+file), 35 (Directus schema verification + try_post_or_queue read-back), 36 (patch invariant persistence — applies if any storyboard JS patch is touched).

### §0.8 — Standing Escape Hatches (when to STOP and surface to Kim)
1. Cursor review (if run) flags release-blocker.
2. Layer 6 smoke fails (intentional break does not trigger gate).
3. Schema drift detected (collection shape ≠ reference doc).
4. LD this spec amends/supersedes not found at expected key.
5. GitHub Pro upgrade not yet completed (Phase B blocker).
6. CodeRabbit billing setup not yet completed (only relevant if Decision A path is overridden — see §3).
7. RN repo at `~/Projects/MindfulNest/` not present on executing machine (Phase D blocker).
8. Phase A deploy script restart fails (process management issue — escalate, do NOT silent-retry).
9. Rule 26 Opus escalation triggered (any second-failed-patch within a phase).
10. Discovery during execution that prior phase's work was incomplete.

### §0.9 — Deviation Logging Pattern
Specs are always incomplete. Deviations are NORMAL. Log honestly via `prod_activity_log` action=`<PHASE>_DEVIATION_<id>` with `details: {spec_says, reality_is, resolution, approved_by}`. The behavior to AVOID: silently substituting OR pretending no deviation happened.

### §0.10 — Browser / CLI Smoke Discipline
Mandatory after surface work. Server-side gates ≠ user-visible correctness. File:// links don't work in chat — Kim screenshots/records/describes verbally with timestamps. Phase does NOT mark COMPLETE until Kim confirms or explicitly defers via deferral plan documented in `prod_activity_log`.

For this spec specifically:
- Phase A smoke: Kim deploys to staging, intentionally edits a `.tsx` without running build, runs `deploy_storyboard_v59.sh`, confirms FATAL exit.
- Phase B smoke: Kim opens main branch settings on GitHub, confirms branch protection rules visible.
- Phase C smoke: Kim opens a test PR with a known issue (e.g., a forgotten `console.log`), confirms AI review comment appears within 5 min.
- Phase D smoke: Kim pushes a commit to MindfulNest repo, confirms `zero-error-qa.yml` workflow run starts.
- Phase E smoke: Kim looks at the latest playwright_e2e.yml run, confirms 18 specs pass (12 existing + 6 new).
- Phase F smoke: Documentation only — Kim re-reads SKILL.md DS-21 and confirms wording matches her intent.
- Phase G smoke: Kim makes an edit in Dropbox runtime tree (`Production/Event_1/storyboard_v59_prod.html`), tries `git commit` in tooling repo, confirms FATAL exit.

---

## §1 Task

Complete the missing 20% of MindfulNest's CI/CD infrastructure. The existing 80% — tooling repo per LD-505, smoke.yml + playwright_e2e.yml workflows, deploy_storyboard_v59.sh, branch+PR pattern, DS-1 through DS-19, 22 pytest files — is GREEN and stable. This spec fills 7 specific gaps that produce the recurring failure classes Kim has observed: silent stale-build deploys, force-pushes to main, missed PR review issues, drafted-but-undeployed RN workflows, deferred Playwright specs, browser-smoke-as-soft-step, and direct Dropbox edits bypassing version control. Total estimated effort: 8-12 focused hours. NOT IN SCOPE: redesigning what works, adding GitHub Enterprise tier features, touching the React Native app code itself.

## §2 Governing Decisions

**Existing LDs (compliance — this spec MUST honor):**
- `[CONFIRMED]` LD-505 — Tooling repo private at kimhyla/mindfulnest-tooling
- `[CONFIRMED]` LD-507 `MANDATORY_E2E_GATE_V1` — Playwright E2E gate is mandatory for storyboard merges
- `[CONFIRMED]` LD-508 `CI_PLAYWRIGHT_ON_COMMIT_V1` — Playwright runs on every commit
- `[CONFIRMED]` LD-519 `MUTATION_CHANNEL_INVARIANT_V1` — single mutation channel discipline
- `[CONFIRMED]` LD-531 `SCOPE_ROUTER_V1` — scope router is canonical
- `[CONFIRMED]` LD-541 `STORYBOARD_DEPLOY_PROCESS_V1` — deploy script defines rsync + sha256 of 4 Python files + server restart

**CLAUDE.md rules (apply throughout):**
- Rule 18 — Locked Decision Auto-Registration (Phase A and Phase G locked decisions must be registered immediately)
- Rule 19 — No Shortcuts, No Error Paths (governs every gap fix in this spec)
- Rule 24 — Confidence Annotation (executing sessions must tag claims)
- Rule 26 — Opus Escalation Protocol (second-failed-patch triggers spawn 3+3 debate)
- Rule 29 — Server Staleness Check (Phase A directly addresses this for deploy)
- Rule 32 — Absolute http://localhost:PORT URLs (no new fetch() calls in this spec; pre-existing tool URLs untouched)
- Rule 33 — Verify Correct Server and File Before Testing (Phase A bakes this into deploy script)
- Rule 35 — Directus Schema Verification + try_post_or_queue (every prod_* write in this spec)

**LDs proposed NEW by this spec (5 total — bumped from 4 by 2026-05-07 pre-execution amendment):**
- `DEPLOY_VERIFICATION_GATE_V1` (Phase A) — pre-deploy mtime + post-deploy sha256 + curl smoke; severity HARD; scope=production; supersedes informal verification gaps in LD-541's current implementation.
- `AI_REVIEW_AUTOMATION_V1` (Phase C) — Claude API custom integration on PR open/sync; severity SOFT; scope=tooling_ci.
- `PRE_COMMIT_DROPBOX_EDIT_GATE_V1` (Phase G) — pre-commit hook blocks divergent Dropbox edits; severity HARD; scope=local_dev.
- `BROWSER_SMOKE_MECHANICAL_GATE_V1` (Phase F) — `try_post_or_queue` rejects `*_COMPLETE` activity_log writes when no matching `KIM_BROWSER_SMOKE_PASSED` row exists; severity HARD; scope=production. Added 2026-05-06 by Kim before execution start because doc-only Phase F was discipline-dependent (§36.5 honesty model) — mechanical gate makes browser smoke truly hard.
- `CODEQL_DEPENDABOT_SECURITY_SCAN_V1` (Phase H) — CodeQL on PR + weekly cron + Dependabot weekly vuln PRs; tooling + RN repos; severity HARD; scope=production; recommended-pre-TestFlight per previous session's coverage gap.

**Documentation + mechanical update proposed:**
- DS-21 (Phase F.1) — append to `zero-error-qa` SKILL.md: "Browser smoke is a HARD prerequisite for phase COMPLETE row writes, NOT a deferred verification."
- Mechanical hook (Phase F.2) — modify `Production/lib/directus.py::try_post_or_queue` to enforce DS-21 in code, not Claude self-discipline.

**Severity enum note:** This spec uses LIVE schema enum `{HARD, SOFT}` per 2026-05-04 migration verified live 2026-05-07 against `/fields/prod_locked_decisions/severity`. Pre-migration values (HIGH/MEDIUM/LOW/CRITICAL) are still accepted on legacy rows but new writes use HARD/SOFT.

## §3 Approach

The spec attacks the 7 gaps in **dependency-order with parallelism**. Phase A is the highest priority because it eliminates today's recurring failure class (silent stale-build deploys) and is independent of every other phase. Phase B (branch protection) is a one-time GitHub UI configuration that gates Phase C (AI review uses required-status checks). Phase C uses the **Claude API custom integration** path (Decision B from the prompt) — Kim already has Anthropic API access, costs are O($0.01-0.10/PR) at solo-dev cadence, and the prompt template gives full control over what the reviewer enforces (Rule 24 / Rule 35 / DS-1 through DS-19 / 6-layer contract). Phases D, E, and G operate on different files and can run in parallel after Phase A. Phase F is documentation-only and can land alongside any other phase.

The spec does NOT introduce new vendors. It does NOT touch the React Native app itself (only activates 2 already-drafted workflows that target it). It does NOT replace deploy_storyboard_v59.sh — it adds verification gates to the existing script per LD-541. It does NOT replace the existing smoke.yml or playwright_e2e.yml workflows — it extends them.

The pre-commit hook in Phase G is intentionally local-only (lives in `.git/hooks/pre-commit`, NOT in the repo). This avoids Husky/lefthook complexity for solo-dev work, and the hook scope is "Kim's local laptop" — multi-developer concerns are out of scope per the locked 20% framing.

## §4 Implementation Phases

Each phase below states classification, Phase 0 prerequisites, the work itself, per-phase escape hatches in addition to §0.8 standing list, and the smoke gate that closes the phase.

---

### Phase A — Deploy Script Verification Gates (TIER B, HIGHEST PRIORITY)

**Estimated effort:** 1-2 hours.

**Tier classification rationale:** Cross-cutting (B). Touches deploy infrastructure that downstream phases depend on, but doesn't introduce a new architectural pattern — it strengthens an existing one (LD-541). Phase 0 spawns 1 advocate + 1 counter agent.

**Phase 0:**
- Load `zero-error-qa` skill.
- Spawn 1 advocate agent: "Validate this verification-gate plan against LD-541's existing deploy script. What invariants might it break?"
- Spawn 1 counter agent: "What failure modes does this plan miss? What stale-build edge case escapes pre-deploy mtime + post-deploy sha256 + curl smoke?"
- Synthesize → write `prod_preflight_reviews` row via `try_post_or_queue` referencing this spec § Phase A.

**Work:**

1. **Pre-deploy mtime check** added to top of `Production/scripts/deploy_storyboard_v59.sh`:
   ```bash
   # Pre-deploy: detect uncompiled .tsx edits
   DIST_HTML="Production/tools/storyboard-v2/dist/index.html"
   if [ ! -f "$DIST_HTML" ]; then
       echo "FATAL: $DIST_HTML missing. Run: cd Production/tools/storyboard-v2 && npm run build"
       exit 1
   fi
   DIST_MTIME=$(stat -f %m "$DIST_HTML" 2>/dev/null || stat -c %Y "$DIST_HTML")
   while IFS= read -r tsx; do
       TSX_MTIME=$(stat -f %m "$tsx" 2>/dev/null || stat -c %Y "$tsx")
       if [ "$TSX_MTIME" -gt "$DIST_MTIME" ]; then
           echo "FATAL: $tsx is newer than dist/index.html — uncompiled changes."
           echo "Run: cd Production/tools/storyboard-v2 && npm run build"
           exit 1
       fi
   done < <(find Production/tools/storyboard-v2/src -name "*.tsx" -o -name "*.ts" 2>/dev/null)
   ```

2. **Post-deploy sha256 verification** at all destinations (dist canonical + every Event_*/storyboard_v59_prod.html fanout):
   ```bash
   CANONICAL_SHA=$(shasum -a 256 "$DIST_HTML" | awk '{print $1}')
   echo "Canonical sha256: $CANONICAL_SHA"
   for fanout in Production/Event_*/storyboard_v59_prod.html; do
       [ -f "$fanout" ] || continue
       FANOUT_SHA=$(shasum -a 256 "$fanout" | awk '{print $1}')
       if [ "$FANOUT_SHA" != "$CANONICAL_SHA" ]; then
           echo "FATAL: $fanout sha256 mismatch."
           echo "  expected: $CANONICAL_SHA"
           echo "  got:      $FANOUT_SHA"
           exit 1
       fi
   done
   echo "All fanout copies match canonical sha256."
   ```

3. **Post-deploy curl smoke** for unique build marker. The build process is updated to inject the current commit SHA into the HTML at build time as a meta tag (`<meta name="build-sha" content="abc123...">`); the deploy script then asserts that marker is present in the served HTML:
   ```bash
   # Build emits BUILD_SHA into HTML. Deploy script verifies served HTML contains it.
   BUILD_SHA=$(git rev-parse --short HEAD)
   sleep 2  # let server settle after restart
   SERVED=$(curl -s http://localhost:5111/ || echo "")
   if ! echo "$SERVED" | grep -q "build-sha.*$BUILD_SHA"; then
       echo "FATAL: served HTML at http://localhost:5111/ does not contain build-sha=$BUILD_SHA"
       echo "Server may be serving stale content."
       exit 1
   fi
   echo "Server is serving fresh build (sha=$BUILD_SHA)."
   ```

4. **Build-time SHA injection** added to `Production/tools/storyboard-v2/vite.config.ts` (or equivalent build config) to emit `<meta name="build-sha" content="<git rev-parse --short HEAD>">` into the HTML head.

5. **Lock LD `DEPLOY_VERIFICATION_GATE_V1`** via `try_post_or_queue` to `prod_locked_decisions` (Rule 18 + Rule 35):
   - decision_key: `DEPLOY_VERIFICATION_GATE_V1`
   - severity: `HIGH`
   - scope_domain: `production`
   - decision_text: pre-deploy mtime + post-deploy sha256 + post-deploy curl smoke; FATAL on any miss; supersedes informal LD-541 verification gaps.

**Per-phase escape hatches:**
- If `find` returns no .tsx files, FATAL and surface (something is wrong with directory layout, do not silently pass).
- If curl returns non-200 or empty, retry once after 5s sleep; on second failure FATAL with diagnostic dump (lsof of port 5111, ps aux | grep production_server).
- If git rev-parse fails (e.g., detached HEAD), use `git log -1 --pretty=%h` as fallback; if both fail, FATAL.

**Phase A smoke gate:**
| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| A1 | Script lints clean (`bash -n deploy_storyboard_v59.sh`) | 1 | Auto | exit 0 |
| A2 | Pre-deploy detects stale build | 6 | Kim-CLI | Edit a .tsx without rebuild → run script → exit non-zero with FATAL message |
| A3 | Post-deploy sha256 catches mismatch | 6 | Kim-CLI | Manually corrupt one fanout → run script → exit non-zero with sha mismatch FATAL |
| A4 | Post-deploy curl smoke catches stale server | 6 | Kim-CLI | Skip server restart → run deploy → exit non-zero with build-sha miss FATAL |
| A5 | LD row present | 4 | Auto | `try_post_or_queue` read-back confirms `DEPLOY_VERIFICATION_GATE_V1` exists |
| A6 | Activity log row present | 4 | Auto | `prod_activity_log` action=`PHASE_A_COMPLETE` written |

---

### Phase B — Branch Protection on main (TIER A)

**Estimated effort:** 30 min (mostly billing setup + GitHub UI clicks).

**Tier classification rationale:** Routine (A). Configuration change with no code. 0 advocate/counter agents required.

**Phase 0:**
- Verify GitHub Pro subscription is active for kimhyla account ($4/mo). If not, BLOCK and surface to Kim — this is a paid prerequisite per §0.8 escape hatch 5.
- Write `prod_preflight_reviews` row.

**Work:**

1. Activate GitHub Pro on Kim's GitHub account ($4/mo).
2. Navigate to https://github.com/kimhyla/mindfulnest-tooling/settings/branches and configure rule on `main`:
   - Require pull request reviews before merging: ON, 1 reviewer minimum.
   - Allow specified actors to bypass: NONE (Kim self-reviews via the AI review or her own approval comment counts as 1).
   - Require status checks to pass before merging: ON.
     - Required: `smoke` (from smoke.yml) and `playwright_e2e` (from playwright_e2e.yml) and `ai_review` (from Phase C — wire AFTER Phase C ships).
   - Require branches to be up to date before merging: ON.
   - Require linear history: ON (no merge commits).
   - Do not allow bypassing the above settings: ON.
   - Restrict who can push to matching branches: NONE except via PR.
   - Allow force pushes: OFF.
   - Allow deletions: OFF.

3. Repeat the same configuration on `~/Projects/MindfulNest/` (the RN repo) main branch — this protects the React Native repo that Phase D activates workflows in.

4. Document the configuration in `prod_activity_log` action=`PHASE_B_COMPLETE` with `details: {tooling_repo_protected: true, rn_repo_protected: true, required_checks: [...]}`.

**Per-phase escape hatches:**
- If GitHub Pro upgrade not completed by Kim, STOP — this phase cannot complete on free tier (private-repo branch protection requires Pro).
- If RN repo doesn't exist on this machine, document with `RN_REPO_PROTECTION_DEFERRED` action and pick up on a machine that has it.

**Phase B smoke gate:**
| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| B1 | Tooling repo branch protection visible | 1 | Kim-browser | https://github.com/kimhyla/mindfulnest-tooling/settings/branches shows rule on main with all required checkboxes |
| B2 | Force-push to main blocked | 6 | Kim-CLI | Test: `git push --force origin main` → rejected with branch-protection error |
| B3 | Direct push without PR blocked | 6 | Kim-CLI | Test: `git push origin main` from main branch → rejected with PR-required error |
| B4 | RN repo branch protection visible | 1 | Kim-browser | Same check on MindfulNest repo |
| B5 | Activity log row present | 4 | Auto | `prod_activity_log` PHASE_B_COMPLETE |

---

### Phase C — AI Review Automation via Claude API (TIER B)

**Estimated effort:** 2-4 hours.

**Tier classification rationale:** Cross-cutting (B). New workflow + new external API integration on a familiar vendor (Anthropic) using a familiar SDK (claude-api skill). Phase 0 spawns 1 advocate + 1 counter agent.

**Phase 0:**
- Load `zero-error-qa` and `claude-api` skills.
- Spawn 1 advocate agent: "Is the prompt template enforcing Rule 24 / Rule 35 / DS-1..19 sufficient? What false-positives would it generate?"
- Spawn 1 counter agent: "Where could this AI reviewer silently no-op? What if the diff exceeds Claude's context window? What if Anthropic API is down?"
- Write `prod_preflight_reviews` row.

**Work:**

1. Add Anthropic API key to GitHub Actions secrets (tooling repo only):
   - GitHub repo → Settings → Secrets and variables → Actions → New repository secret
   - Name: `ANTHROPIC_API_KEY`
   - Value: from `Production/API_KEYS_MASTER.md`

2. Create `.github/workflows/ai_review.yml` in tooling repo:
   ```yaml
   name: AI Review (Claude)
   on:
     pull_request:
       types: [opened, synchronize, reopened]
   permissions:
     pull-requests: write
     contents: read
   jobs:
     claude_review:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
           with: { fetch-depth: 0 }
         - name: Get PR diff
           id: diff
           run: |
             git diff origin/main...HEAD > /tmp/pr.diff
             echo "diff_size=$(wc -c < /tmp/pr.diff)" >> $GITHUB_OUTPUT
         - name: Run Claude review
           env:
             ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
             PR_NUMBER: ${{ github.event.pull_request.number }}
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
           run: |
             python3 .github/workflows/scripts/claude_review.py
   ```

3. Create `.github/workflows/scripts/claude_review.py`:
   - Reads `/tmp/pr.diff`.
   - If diff > 100 KB, split into chunks; review each; concatenate findings (Anthropic context window is large but cost-aware).
   - Sends to Claude API (sonnet for cost efficiency at solo-dev cadence; per claude-api skill, use prompt caching for the system prompt across PRs).
   - System prompt cites: Rule 24 (confidence annotation), Rule 35 (Directus schema), DS-1 through DS-19 (zero-error-qa SKILL.md), 6-layer verification contract from §0.2. Asks reviewer to flag: missing tests, schema mismatches, hallucinated endpoint names, missing browser smoke, untagged confidence claims, Rule 19 shortcut violations.
   - Posts findings as a single PR review comment via `gh pr review $PR_NUMBER --comment --body "..."` OR via inline comments via the GitHub API. Initial impl: single comment (simpler); upgrade to inline if Kim wants in v2.
   - Sets job exit code based on whether ANY finding has severity=blocking. If blocking, fails the job (fails the required check, blocks merge).

4. The system prompt template lives at `.github/workflows/scripts/review_prompt.md` for transparency and easy tuning. Initial template:
   ```
   You are an AI code reviewer for the MindfulNest tooling repo. You review PR diffs against
   these specific MindfulNest rules:

   - Rule 24: every consequential claim or threshold MUST be tagged
     [CONFIRMED against <source>] / [INFERRED — verify] / [GUESSED]. Untagged claims are findings.
   - Rule 35: any code that writes to Directus prod_* collections MUST consult
     DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md and use try_post_or_queue. Direct urllib POSTs
     without try_post_or_queue are findings.
   - Rule 19: production code paths MUST NOT contain "TODO", "FIXME", "placeholder", "for now",
     "MVP", "we'll add later" without an accompanying SHORTCUT_* LD reference. Findings.
   - Rule 32: every fetch() in HTML production tools MUST use absolute http://localhost:PORT URLs.
     Relative paths are findings.
   - DS-1..19: per Production/.claude/skills/zero-error-qa/SKILL.md, applied to changed code.
   - 6-layer verification contract: changes to UI components without corresponding backend
     wiring tests, OR changes to backend handlers without corresponding state assertions, are
     findings.

   Output format:
   ## AI Review Findings
   ### Blocking
   - <finding 1 with file:line>
   ### Non-blocking
   - <finding 2 with file:line>
   ### Notes
   - <observation>

   If no findings, output:
   ## AI Review Findings
   No blocking issues found.

   Be specific. Cite file:line. Do not invent issues.
   ```

5. After Phase C ships, return to Phase B's branch protection config and add `ai_review` to the required-checks list.

6. Lock LD `AI_REVIEW_AUTOMATION_V1` via `try_post_or_queue`:
   - decision_key: `AI_REVIEW_AUTOMATION_V1`
   - severity: `MEDIUM`
   - scope_domain: `tooling_ci`
   - decision_text: PR open/sync triggers Claude API review against MindfulNest rules; blocking findings fail the required check.

**Per-phase escape hatches:**
- If Anthropic API down (5xx), the workflow MUST exit 0 with a "Review skipped — API unavailable" PR comment, not block the merge. Different from blocking findings — infrastructure unavailability is not a code finding.
- If diff > 1 MB, post a comment "Diff too large for AI review; please request manual review" and exit 0.
- If first PR after Phase C ships generates >5 false-positive findings, escalate to Kim before tuning prompt — do not silently weaken the rules.

**Phase C smoke gate:**
| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| C1 | Workflow file present + lints clean | 1 | Auto | `actionlint` clean on ai_review.yml |
| C2 | Secret configured | 1 | Kim-browser | GitHub repo settings shows ANTHROPIC_API_KEY secret |
| C3 | Test PR with known issue gets review comment | 6 | Kim-browser | Open test PR with `console.log('debug')` → AI comment appears within 5 min flagging it |
| C4 | Blocking finding fails required check | 6 | Kim-browser | Test PR shows `ai_review` check as red |
| C5 | API down failure mode is non-blocking | 6 | Kim-CLI | Manually break ANTHROPIC_API_KEY → retrigger workflow → check passes (skip mode) |
| C6 | LD row present | 4 | Auto | `try_post_or_queue` read-back confirms `AI_REVIEW_AUTOMATION_V1` |
| C7 | Activity log row present | 4 | Auto | PHASE_C_COMPLETE |

---

### Phase D — RN-Side Workflow Activation (TIER A)

**Estimated effort:** 1-2 hours.

**Tier classification rationale:** Routine (A). Two drafted workflows already exist; this phase moves them to the live location and configures secrets.

**Phase 0:**
- Verify `~/Projects/MindfulNest/` exists on this machine (Phase B-style §0.8 escape hatch 7).
- Read both drafts at `Production/github_actions/zero-error-qa.yml` and `Production/github_actions/rn-expo-gate.yml` to confirm they reference the right paths after move.
- Write `prod_preflight_reviews` row.

**Work:**

1. Copy (NOT move — keep tooling-repo copies for reference) drafts to RN repo:
   ```bash
   cp "Production/github_actions/zero-error-qa.yml" ~/Projects/MindfulNest/.github/workflows/zero-error-qa.yml
   cp "Production/github_actions/rn-expo-gate.yml"   ~/Projects/MindfulNest/.github/workflows/rn-expo-gate.yml
   ```

2. Inspect both files for path references that pointed to tooling-repo locations. Update any `Production/...` paths to either (a) the equivalent path in the RN repo, or (b) checked-out path if the workflow does cross-repo work via `actions/checkout` with `repository: kimhyla/mindfulnest-tooling`.

3. Verify supporting scripts referenced by zero-error-qa.yml are accessible:
   - `Production/scripts/test_firestore_rules.js` — confirm path. If only in tooling, the workflow needs to checkout the tooling repo too.
   - `Production/scripts/ai_policy_replay.py` — same.
   - `Production/scripts/media_golden_probe.py` — same.

4. Configure secrets in MindfulNest repo Settings → Secrets:
   - `FIREBASE_SERVICE_ACCOUNT` (from existing setup)
   - `EXPO_TOKEN` (from existing setup)
   - `ANTHROPIC_API_KEY` (same value as tooling repo — for any AI-driven step inside zero-error-qa.yml)
   - Any others the drafts reference (read both YAML files for `secrets.X` references).

5. Investigate `dependency-audit.yml` failure on RN side (Kim flagged 8-day failing streak):
   - Open most recent run; read failure logs.
   - Common causes at this layer: out-of-date `package-lock.json`, deprecated action version, audit threshold too aggressive after a recent vuln disclosure.
   - Fix root cause; do not lower threshold to make it green (Rule 19).
   - If fix non-trivial (>30 min), file `prod_blockers` row with severity=`high` and continue Phase D — this is a separate concern.

6. Push commits to RN repo on a `claude/phase-d-activate-workflows` branch; open PR; verify both workflows show as `pending → running → success` on the PR.

**Per-phase escape hatches:**
- If RN repo workflows reference scripts that don't exist anywhere, defer that workflow's activation with a `WORKFLOW_DEFERRED_<name>` activity log row — do NOT silently delete the script reference.
- If dependency-audit.yml reveals a real vulnerability, file `prod_blockers` row with severity=`high` and surface to Kim.

**Phase D smoke gate:**
| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| D1 | Both workflows present at `~/Projects/MindfulNest/.github/workflows/` | 1 | Auto | `ls` confirms |
| D2 | Both workflows lint clean | 1 | Auto | `actionlint` exits 0 |
| D3 | Test PR triggers both workflows | 6 | Kim-browser | PR Checks tab shows zero-error-qa + rn-expo-gate runs |
| D4 | Both workflows pass on test PR | 6 | Kim-browser | Both green |
| D5 | dependency-audit.yml root cause documented | 4 | Auto | Either fixed (workflow green) OR `prod_blockers` row written |
| D6 | Activity log row present | 4 | Auto | PHASE_D_COMPLETE |

---

### Phase E — Wire 6 Deferred Playwright Specs (TIER B)

**Estimated effort:** 2-4 hours.

**Tier classification rationale:** Cross-cutting (B). Each spec needs fixture migration, which can affect parallelism and run-time. Phase 0 spawns 1 advocate + 1 counter agent.

**Phase 0:**
- Spawn 1 advocate agent: "Read each of the 6 deferred specs. What fixture data does each need? Map fixture-needs to current Event_1 contents."
- Spawn 1 counter agent: "Per DS-10, when total spec count exceeds 15, migrate to Playwright project/tag-based grouping. Current count after this phase = 18. What does that migration look like?"
- Write `prod_preflight_reviews` row.

**Work:**

1. For each of the 6 specs (`behavioral-parity.spec.ts`, `rollback.spec.ts`, `smoke.spec.ts`, `touchpoint-a.spec.ts`, `storyboard-v59-bg-scope-sync.spec.ts`, `storyboard-v59-display-order-empty.spec.ts`):
   - Read the spec; identify fixture data referenced (image filenames, JSON keys, sequence ordering).
   - Identify the corresponding files in `Production/Event_1/` that the spec depends on.
   - Copy minimum needed to `Production/Event_e2e_fixture/.pristine/` (the canonical E2E fixture directory).
   - Update the spec's path constants to use fixture-relative paths (NOT Event_1 paths).
   - Run the spec in isolation: `npx playwright test path/to/spec.ts` → confirm pass against fixture.

2. Append each spec to `playwright_e2e.yml` step list (no glob per DS-10 — each spec listed by name).

3. **Per DS-10 trigger met (18 specs > 15):** Migrate to Playwright project/tag-based grouping in `playwright.config.ts`:
   - Define projects: `core`, `behavior`, `regression`, `smoke`.
   - Tag each spec with `@core`, `@behavior`, etc. (Playwright `test.describe` annotations).
   - Update CI to run `--project=core` for fast PR checks (subset, ~5 min) and full suite on push to main (all 18, ~15 min).
   - This is a structured response to DS-10's threshold, not a scope creep — it's required by the existing rule.

4. Verify in CI: open a test PR; confirm Playwright runs all 18 specs (or projected subset depending on grouping config); all pass.

**Per-phase escape hatches:**
- If a spec needs fixture data that doesn't exist anywhere (e.g., a Phase B that hasn't been produced), document `SPEC_BLOCKED_ON_<name>` activity log row and SKIP that spec — do NOT mock the data. Mocking creates test-vs-reality drift.
- If migration to project-based grouping breaks any existing 12 wired specs, ROLLBACK the grouping change and surface to Kim — group migration is a follow-up if it's risky.
- If runtime exceeds 20 min for full suite, escalate per Rule 26 (cost/perf concern); investigate parallelism config.

**Phase E smoke gate:**
| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| E1 | All 6 specs run locally against fixture | 6 | Auto (local) | `npx playwright test` shows 6 new specs pass |
| E2 | All 18 specs run in CI | 6 | Kim-browser | Latest playwright_e2e.yml run shows 18 passing tests |
| E3 | Project-based grouping config valid | 1 | Auto | `npx playwright test --list` shows expected grouping |
| E4 | Activity log row present | 4 | Auto | PHASE_E_COMPLETE |

---

### Phase F — Browser Smoke as HARD Prerequisite + Mechanical Gate (TIER B)

**Estimated effort:** 90 min (was 30 min before 2026-05-06 amendment — increased to cover mechanical hook implementation + unit tests).

**Tier classification rationale:** Cross-cutting (B). Originally Tier A (doc-only); upgraded by Kim's pre-execution amendment 2026-05-06 because documentation alone is discipline-dependent (Rule 36 §36.5 honesty model — "Claude-side discipline" = soft enforcement). Adding mechanical enforcement via `try_post_or_queue` library hook makes browser smoke truly hard. Phase 0 spawns 1 advocate + 1 counter agent.

**Why this phase upgraded:** Kim 2026-05-06 chat — "i am so PTSD'd... the system enforces correctness mechanically; you stop being the detection mechanism." Doc-only Phase F left Phase-COMPLETE-without-smoke as a Claude-self-discipline failure path. The mechanical hook removes Claude from the loop on this gate.

**Phase 0:**
- Read current `Production/.claude/skills/zero-error-qa/SKILL.md` to confirm latest DS number.
- Read `Production/lib/directus.py::try_post_or_queue` to identify hook insertion point. Confirm `DirectusAdminClient.get_items` supports nested JSON filter on `details.phase`.
- Spawn 1 advocate agent: "Validate the smoke-gate query design. What false positives would block legitimate phase-complete writes? What about phases with no UI surface (e.g., pure-infra phases like gap-fix Phase A itself)? What about retroactive smoke (Kim confirms after the fact)?"
- Spawn 1 counter agent: "Where can the gate silently bypass? What if Directus is offline at the moment of smoke-row query — does the gate fail-open or fail-closed? What about race conditions if smoke-row is written concurrently with phase-complete? What if `details.phase` filter has Directus syntax issues — does the query return empty falsely?"
- Synthesize → write `prod_preflight_reviews` row via `try_post_or_queue` (note: this row is itself written via the modified library, but `prod_preflight_reviews` is not `prod_activity_log` and the gate scopes to activity_log only — verify in Phase 0).

**Work:**

**[F.1] Documentation: append DS-21 to zero-error-qa SKILL.md** (bumped from F.1 in original spec — content unchanged):

```
DS-21: Browser Smoke is a HARD Prerequisite for Phase COMPLETE
----------------------------------------------------------------
A `<phase>_COMPLETE` row in `prod_activity_log` MUST NOT be written until
a `KIM_BROWSER_SMOKE_PASSED` row exists with the phase's verification
table reproduced verbatim and Kim's verbatim confirmation
("looks good", "confirmed", "passed", "ship it") attached.

If terminal cannot drive a browser to perform the smoke, the executing
session MUST defer to Kim. Defer means PHASE INCOMPLETE — not "complete
pending verification." Any subsequent phase that depends on this phase
MUST NOT begin until the SMOKE_PASSED row is written.

ENFORCEMENT IS MECHANICAL (NOT DISCIPLINE-ONLY) per LD
BROWSER_SMOKE_MECHANICAL_GATE_V1: `try_post_or_queue` in
`Production/lib/directus.py` rejects any `prod_activity_log` write where
`action` ends in `_COMPLETE` unless a matching KIM_BROWSER_SMOKE_PASSED
row exists. To override, set env var `MN_SKIP_BROWSER_SMOKE_GATE=1` AND
write a `BROWSER_SMOKE_DEFERRED` audit row first explaining the
deferral. Both checks happen in code, not Claude self-policing.

This rule is a tightening of Phase 6.6 (Browser Console Gate). 6.6 said
"browser console reviewed"; DS-21 says "phase boundary depends on it,
enforced in the library."
```

**[F.2] Mechanical hook: modify `Production/lib/directus.py::try_post_or_queue`.**

Insert validation block at top of `try_post_or_queue` BEFORE the `post_item_verified` call:

```python
def try_post_or_queue(collection, payload, client=None):
    # NEW: Browser-smoke gate per DS-21 / LD BROWSER_SMOKE_MECHANICAL_GATE_V1
    if collection == "prod_activity_log":
        action = payload.get("action", "")
        if _is_phase_complete_action(action):
            phase_key = _extract_phase_key(action)
            override_active = os.environ.get("MN_SKIP_BROWSER_SMOKE_GATE") == "1"
            try:
                smoke_present = _smoke_row_exists(phase_key, client=client)
            except Exception:
                # Fail-CLOSED on Directus error — do not allow COMPLETE writes
                # if we can't verify smoke. Returns queued sentinel so caller
                # can retry once connectivity restores.
                return {
                    "queued": False,
                    "browser_smoke_gate_unverifiable": True,
                    "phase_key": phase_key,
                    "error": "Smoke-gate query failed; refusing COMPLETE write.",
                }
            if not smoke_present and not override_active:
                return {
                    "queued": False,
                    "browser_smoke_missing": True,
                    "phase_key": phase_key,
                    "error": (
                        f"Cannot write {action!r} — no KIM_BROWSER_SMOKE_PASSED "
                        f"row found for phase={phase_key!r}. Browser smoke is a "
                        f"hard prerequisite per DS-21. To override, set "
                        f"MN_SKIP_BROWSER_SMOKE_GATE=1 AND write a "
                        f"BROWSER_SMOKE_DEFERRED row first explaining why."
                    ),
                }
            if not smoke_present and override_active:
                # Override path — require explicit BROWSER_SMOKE_DEFERRED audit row.
                if not _smoke_deferred_row_exists(phase_key, client=client):
                    return {
                        "queued": False,
                        "override_without_audit": True,
                        "phase_key": phase_key,
                        "error": (
                            f"MN_SKIP_BROWSER_SMOKE_GATE=1 but no "
                            f"BROWSER_SMOKE_DEFERRED row exists for "
                            f"phase={phase_key!r}. Write that row first."
                        ),
                    }
    # ... existing post_item_verified + queue logic (unchanged below) ...
```

**Helpers (add to `directus.py`):**

- `_is_phase_complete_action(action: str) -> bool` — returns True if `action` matches regex `^.*_COMPLETE$`. Covers `PHASE_A_COMPLETE`, `S5_5C_PASS2_COMPLETE`, `PHASE_F_COMPLETE`, etc.
- `_extract_phase_key(action: str) -> str` — strips trailing `_COMPLETE` and returns phase key (e.g. `S5_5C_PASS2_COMPLETE` → `S5_5C_PASS2`).
- `_smoke_row_exists(phase_key, client) -> bool` — queries `prod_activity_log` with filter `{action: {_eq: KIM_BROWSER_SMOKE_PASSED}, details: {phase: {_eq: phase_key}}}`. Returns True if 1+ rows.
- `_smoke_deferred_row_exists(phase_key, client) -> bool` — same but for action=`BROWSER_SMOKE_DEFERRED`.

**Recursion safety:** `KIM_BROWSER_SMOKE_PASSED` and `BROWSER_SMOKE_DEFERRED` actions do NOT end in `_COMPLETE` and naturally bypass the gate. Verify with explicit unit test (gate F8 below).

**[F.3] Smoke row schema contract (canonical payload shape — both rows go to `prod_activity_log`).**

Per CLAUDE.md Rule 35, `prod_activity_log.details` is JSON. Both contracts use a consistent `details.phase` key for the gate's filter:

```python
# KIM_BROWSER_SMOKE_PASSED — written by Kim's session-end confirmation flow
{
    "action": "KIM_BROWSER_SMOKE_PASSED",
    "details": {
        "phase": "S5_5C_PASS2",            # MUST match phase_key the gate extracts
        "verification_table": "<gate-by-gate pass/fail reproduced from spec>",
        "kim_quote": "<verbatim confirmation, e.g. 'looks good'>",
        "captured_at": "<ISO timestamp>",
    },
}

# BROWSER_SMOKE_DEFERRED — written when Kim explicitly approves an override
{
    "action": "BROWSER_SMOKE_DEFERRED",
    "details": {
        "phase": "<PHASE_KEY>",
        "reason": "<why deferral is justified — e.g. infra-only phase, no UI>",
        "approved_by": "<kim chat line referencing approval>",
        "deferred_until": "<ISO timestamp or 'next session' or 'never — phase has no UI'>",
    },
}
```

**[F.4] Update Phase 6.6 in zero-error-qa SKILL.md** (existing spec content, expanded):

- Original: "Browser console reviewed for errors after UI work."
- Updated: "Browser console reviewed for errors after UI work. Per DS-21, this is a HARD prerequisite for the phase COMPLETE row, **mechanically enforced** in `try_post_or_queue` via LD `BROWSER_SMOKE_MECHANICAL_GATE_V1` — Claude cannot skip this gate by self-discipline failure; the library rejects the write."

**[F.5] Update `prod_reference_docs` entry for SKILL.md** per Rule 15 — bump version, update `notes` to reference the mechanical hook.

**[F.6] Lock LD `BROWSER_SMOKE_MECHANICAL_GATE_V1`** via `try_post_or_queue` to `prod_locked_decisions`:

- decision_key: `BROWSER_SMOKE_MECHANICAL_GATE_V1`
- severity: `HARD`
- scope_domain: `production`
- task_category: `tech_stack`
- enforcement_type: `code_invariant`
- date_locked: 2026-05-06 (Kim's amendment date)
- source_document: `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` §Phase F
- decision_text: full Phase F.2 contract (gate logic + helpers + recursion safety + override mechanism + fail-closed semantics)

**Per-phase escape hatches:**
- If DS-20 already exists, use DS-22 instead — never overwrite/renumber existing DS slots.
- If `details.phase` filter syntax does NOT work on Directus (test in Phase 0 — query a known row), fall back to a flat `details` field strategy (e.g. add a top-level `phase_key` column to activity_log payloads) and document the deviation per §0.9.
- If a phase legitimately has no UI surface (gap-fix Phase A is a pure-infra example), the executing session MUST write a `BROWSER_SMOKE_DEFERRED` row explaining "no UI in this phase" before the COMPLETE write. The override env var alone is not sufficient — the audit row is required.
- If unit tests F6-F9 fail, REVERT the directus.py change via git and stop — do not patch on broken behavior.

**Phase F smoke gate (10 gates — bumped from 5):**

| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| F1 | DS-21 visible in SKILL.md | 1 | Auto | `grep -n DS-21 zero-error-qa/SKILL.md` finds entry |
| F2 | Phase 6.6 cross-reference present | 1 | Auto | grep finds DS-21 reference in 6.6 + "mechanically enforced" wording |
| F3 | Reference docs entry updated | 4 | Auto | `try_post_or_queue` PATCH on prod_reference_docs row, read-back confirms |
| F4 | Kim re-reads SKILL.md + confirms wording matches intent | 6 | Kim-CLI | Verbatim confirmation in chat |
| F5 | Mechanical gate code present in directus.py | 1 | Auto | `grep _is_phase_complete_action Production/lib/directus.py` finds 4 helpers |
| F6 | Unit test: missing smoke row → reject `*_COMPLETE` write | 6 | Auto | pytest with mock client returning [] → result has `browser_smoke_missing: true` |
| F7 | Unit test: smoke row present → allow `*_COMPLETE` write | 6 | Auto | pytest with mock smoke row → result is the verified row dict (id present) |
| F8 | Unit test: KIM_BROWSER_SMOKE_PASSED itself bypasses gate (recursion safe) | 6 | Auto | pytest writing a smoke row → write succeeds without gate check |
| F9 | Unit test: override path requires DEFERRED row | 6 | Auto | pytest with `MN_SKIP_BROWSER_SMOKE_GATE=1` but no DEFERRED → reject; same with DEFERRED present → allow |
| F10 | LD `BROWSER_SMOKE_MECHANICAL_GATE_V1` registered | 4 | Auto | `try_post_or_queue` read-back confirms row in `prod_locked_decisions` |
| F11 | Activity log row PHASE_F_COMPLETE | 4 | Auto | written via try_post_or_queue (note: F itself requires a SMOKE_PASSED row first — Kim confirms F1-F10 passed by writing the smoke row, then PHASE_F_COMPLETE proceeds) |

**Self-application note:** Phase F is the FIRST phase whose own COMPLETE row is gated by the mechanical hook it just installed. This is intentional — it proves the gate works on real traffic, not just unit tests. If the gate is broken, Phase F can't close itself, which surfaces the bug immediately.

---

### Phase G — Pre-commit Hook Blocking Direct Dropbox Edits (TIER B)

**Estimated effort:** 1 hour.

**Tier classification rationale:** Cross-cutting (B). New filesystem-level integration with potential edge cases (symlinks, file moves, untracked files). Phase 0 spawns 1 advocate + 1 counter agent.

**Phase 0:**
- Spawn 1 advocate agent: "Validate the bidirectional mtime check logic. What edge cases break it (file rename, symlink, .gitignore'd files)?"
- Spawn 1 counter agent: "When does this hook block a legitimate commit? What's the override mechanism if Kim genuinely needs to commit despite drift?"
- Write `prod_preflight_reviews` row.

**Work:**

1. Write hook to `~/Projects/mindfulnest-tooling/.git/hooks/pre-commit` (NOT in repo — this is local-only, see §3 rationale):
   ```bash
   #!/usr/bin/env bash
   # Pre-commit: block divergent Dropbox runtime tree edits.
   # Lock: PRE_COMMIT_DROPBOX_EDIT_GATE_V1.
   set -euo pipefail

   DROPBOX_ROOT="$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
   TOOLING_ROOT="$(git rev-parse --show-toplevel)"

   # Override mechanism: Kim sets env var when legitimate divergence (e.g., she ran a deploy
   # in a different shell and the runtime tree is intentionally newer).
   if [ "${MN_SKIP_DROPBOX_EDIT_GATE:-}" = "1" ]; then
       echo "PRE-COMMIT: MN_SKIP_DROPBOX_EDIT_GATE=1 — gate bypassed."
       exit 0
   fi

   FATAL=0

   # Check 1: any staged file whose Dropbox runtime mtime is newer than tooling-repo file.
   while IFS= read -r staged; do
       [ -z "$staged" ] && continue
       repo_path="$TOOLING_ROOT/$staged"
       dropbox_path="$DROPBOX_ROOT/$staged"
       [ -f "$repo_path" ] || continue
       [ -f "$dropbox_path" ] || continue
       repo_mtime=$(stat -f %m "$repo_path" 2>/dev/null || stat -c %Y "$repo_path")
       dropbox_mtime=$(stat -f %m "$dropbox_path" 2>/dev/null || stat -c %Y "$dropbox_path")
       if [ "$dropbox_mtime" -gt "$repo_mtime" ]; then
           echo "FATAL: $staged has newer mtime in Dropbox runtime tree."
           echo "  Run deploy_storyboard_v59.sh first, or set MN_SKIP_DROPBOX_EDIT_GATE=1."
           FATAL=1
       fi
   done < <(git diff --cached --name-only)

   # Check 2 (symmetric): any tooling-tracked file edited in Dropbox after last deploy.
   # We use the .last_deploy timestamp file written by deploy_storyboard_v59.sh.
   LAST_DEPLOY_FILE="$TOOLING_ROOT/.last_deploy"
   if [ -f "$LAST_DEPLOY_FILE" ]; then
       last_deploy=$(cat "$LAST_DEPLOY_FILE")
       while IFS= read -r tracked; do
           dropbox_path="$DROPBOX_ROOT/$tracked"
           [ -f "$dropbox_path" ] || continue
           dropbox_mtime=$(stat -f %m "$dropbox_path" 2>/dev/null || stat -c %Y "$dropbox_path")
           if [ "$dropbox_mtime" -gt "$last_deploy" ]; then
               echo "WARN: $tracked edited in Dropbox after last deploy."
               echo "  This commit may not include those edits. Set MN_SKIP_DROPBOX_EDIT_GATE=1 to override."
               FATAL=1
           fi
       done < <(git ls-files | head -100)  # bounded scan
   fi

   if [ $FATAL -eq 1 ]; then
       echo ""
       echo "Pre-commit blocked. See above."
       exit 1
   fi
   echo "Pre-commit Dropbox-edit gate: clean."
   ```

2. Update `Production/scripts/deploy_storyboard_v59.sh` (Phase A's file) to write `.last_deploy` timestamp at end of successful deploy:
   ```bash
   date +%s > "$TOOLING_ROOT/.last_deploy"
   ```

3. Write a setup script `Production/scripts/install_pre_commit_hook.sh` that copies the hook into place. Kim runs it once on each machine.

4. Lock LD `PRE_COMMIT_DROPBOX_EDIT_GATE_V1` via `try_post_or_queue`:
   - decision_key: `PRE_COMMIT_DROPBOX_EDIT_GATE_V1`
   - severity: `HIGH`
   - scope_domain: `local_dev`
   - decision_text: pre-commit hook blocks commits when Dropbox runtime tree has diverged from tooling repo; override via `MN_SKIP_DROPBOX_EDIT_GATE=1`.

**Per-phase escape hatches:**
- If `git ls-files | head -100` skips a relevant file, raise the limit cautiously (each file is a stat call). If perf becomes an issue, switch to `find -newer` strategy.
- If hook blocks a legitimate commit during normal Kim workflow, surface to Kim immediately — false positive rate must be near-zero or the hook will be bypassed and useless.
- If both Dropbox path and repo path don't resolve on a different machine (Windows PC), the hook silently exits 0 (`[ -f ... ] || continue`). This is intentional fail-open per §0.8 — better than blocking commits on a machine where the gate doesn't apply.

**Phase G smoke gate:**
| # | Gate | Layer | Type | Pass criteria |
|---|------|-------|------|---------------|
| G1 | Hook executable + lints clean | 1 | Auto | `bash -n .git/hooks/pre-commit` clean; `chmod +x` set |
| G2 | Hook fires on Dropbox-newer file | 6 | Kim-CLI | Edit `Production/Event_1/storyboard_v59_prod.html` in Dropbox → try `git commit` in tooling repo → exit non-zero |
| G3 | Override env var bypasses cleanly | 6 | Kim-CLI | `MN_SKIP_DROPBOX_EDIT_GATE=1 git commit` → exits 0 |
| G4 | `.last_deploy` written after successful deploy | 6 | Kim-CLI | Run deploy_storyboard_v59.sh → `cat .last_deploy` shows recent timestamp |
| G5 | LD row present | 4 | Auto | `try_post_or_queue` read-back |
| G6 | Activity log row present | 4 | Auto | PHASE_G_COMPLETE |

---

## §5 Files Created / Modified

**Created:**
- `Production/scripts/install_pre_commit_hook.sh` — installer for Phase G hook (Phase G).
- `mindfulnest-tooling/.github/workflows/ai_review.yml` — AI review workflow (Phase C).
- `mindfulnest-tooling/.github/workflows/scripts/claude_review.py` — review orchestrator (Phase C).
- `mindfulnest-tooling/.github/workflows/scripts/review_prompt.md` — Claude system prompt (Phase C).
- `~/.git/hooks/pre-commit` (in `mindfulnest-tooling`, local only) — pre-commit hook (Phase G).
- `mindfulnest/.github/workflows/zero-error-qa.yml` — copied from `Production/github_actions/zero-error-qa.yml` (Phase D).
- `mindfulnest/.github/workflows/rn-expo-gate.yml` — copied from `Production/github_actions/rn-expo-gate.yml` (Phase D).
- `Production/Event_e2e_fixture/.pristine/` — fixture data for 6 newly wired specs (Phase E).

**Modified:**
- `Production/scripts/deploy_storyboard_v59.sh` — pre-deploy mtime check, post-deploy sha256 fanout verification, post-deploy curl smoke, `.last_deploy` write (Phase A + Phase G).
- `Production/tools/storyboard-v2/vite.config.ts` (or equivalent build config) — inject build-sha meta tag (Phase A).
- `mindfulnest-tooling/.github/workflows/playwright_e2e.yml` — append 6 new specs; restructure to project-based grouping per DS-10 (Phase E).
- `mindfulnest-tooling/playwright.config.ts` — define projects `core`/`behavior`/`regression`/`smoke` (Phase E).
- 6 Playwright specs (path constants updated to fixture-relative): `behavioral-parity.spec.ts`, `rollback.spec.ts`, `smoke.spec.ts`, `touchpoint-a.spec.ts`, `storyboard-v59-bg-scope-sync.spec.ts`, `storyboard-v59-display-order-empty.spec.ts` (Phase E).
- `Production/.claude/skills/zero-error-qa/SKILL.md` — append DS-21; update Phase 6.6 cross-reference (Phase F).
- GitHub Settings (no file): branch protection rules on `kimhyla/mindfulnest-tooling/main` and `kimhyla/MindfulNest/main` (Phase B).
- GitHub Secrets (no file): `ANTHROPIC_API_KEY` added to both repos; existing `FIREBASE_*`/`EXPO_*` verified on RN repo (Phase C + D).

## §6 Directus Writes Required

All writes via `try_post_or_queue` from `Production/lib/directus.py` per Rule 35.

**`prod_locked_decisions` (3 NEW rows):**

| decision_key | severity | scope_domain | task_category | status |
|---|---|---|---|---|
| `DEPLOY_VERIFICATION_GATE_V1` | HIGH | production | operations | active |
| `AI_REVIEW_AUTOMATION_V1` | MEDIUM | tooling_ci | tech_stack | active |
| `PRE_COMMIT_DROPBOX_EDIT_GATE_V1` | HIGH | local_dev | operations | active |

Each row's `decision_text` written per Rule 18 with the full text from §4. `date_locked = 2026-05-06` or actual execution date. `source_document = Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md`.

**`prod_preflight_reviews` (7 NEW rows, one per phase):**

| task_type | claude_summary | approved_to_proceed |
|---|---|---|
| Phase A preflight | (synthesis of advocate+counter) | true after Kim approves |
| Phase B preflight | (no agents, Tier A) | true |
| Phase C preflight | (advocate+counter synthesis) | true after Kim approves |
| Phase D preflight | (no agents, Tier A) | true |
| Phase E preflight | (advocate+counter synthesis) | true after Kim approves |
| Phase F preflight | (no agents, Tier A) | true |
| Phase G preflight | (advocate+counter synthesis) | true after Kim approves |

**`prod_activity_log` (7+ rows):**

One `PHASE_<X>_COMPLETE` row per phase, with `details: {smoke_gates_passed: [...], deviations: [...], kim_browser_smoke_passed: <id>}`. Plus any `PHASE_<X>_DEVIATION_<id>` rows logged honestly per §0.9.

**`prod_reference_docs` (1 PATCH row):**

PATCH the `zero-error-qa` SKILL.md entry to bump version + note "DS-21 added per V59_CICD_GAP_FIX_SPEC_v1 Phase F" in `notes` field. Per Rule 15.

**`prod_blockers` (0-1 rows, conditional):**

If Phase D dependency-audit.yml investigation surfaces a real vulnerability or non-trivial fix, write a `prod_blockers` row with severity=`high` and link to the activity log.

## §7 Error Cases and Handling

Per Rule 19, no error path is left silent.

| Error | Phase | Handling |
|---|---|---|
| `find` returns no .tsx files | A | FATAL — directory layout is broken; surface to Kim |
| Server restart fails | A | FATAL with full diagnostic dump (lsof, ps); do NOT silent-retry |
| `git rev-parse` fails (detached HEAD) | A | Fallback to `git log -1 --pretty=%h`; if still fails, FATAL |
| GitHub Pro not active | B | BLOCK phase; surface to Kim before any work |
| Anthropic API down (5xx) | C | Skip review with "API unavailable" PR comment; exit 0 (don't block merge on infra) |
| Diff > 1 MB | C | Skip review with "diff too large" comment; exit 0 |
| AI generates >5 false positives on first PR | C | Escalate to Kim; do NOT silently weaken prompt rules |
| RN repo not on this machine | D | Defer with `RN_REPO_PROTECTION_DEFERRED` activity log; pick up on a machine that has it |
| Workflow references missing script | D | Defer that workflow with `WORKFLOW_DEFERRED_<name>`; do NOT silently delete reference |
| dependency-audit.yml has real vuln | D | File `prod_blockers` severity=high; surface to Kim; do NOT lower threshold |
| Playwright spec needs missing fixture | E | SKIP with `SPEC_BLOCKED_ON_<name>` log; do NOT mock |
| Playwright project grouping breaks existing 12 specs | E | ROLLBACK grouping change; surface to Kim |
| Playwright runtime > 20 min | E | Escalate per Rule 26; investigate parallelism config |
| DS-20 already exists when adding DS-21 | F | Use DS-21 (continue numbering); never overwrite |
| Hook blocks legitimate commit | G | Surface to Kim immediately; false-positive rate must be near-zero |
| Hook on a machine where Dropbox path doesn't resolve | G | Silent fail-open via `[ -f ... ] || continue` (intentional) |
| Override env var abused (frequent use) | G | Audit `prod_activity_log` weekly for `MN_SKIP_DROPBOX_EDIT_GATE=1` traces; surface to Kim if pattern emerges |

## §8 Verification

Per-phase smoke gate tables in §4 are authoritative. Summary:

- **Auto gates** (lint, syntax, sha256, hook script lint, schema verify): run inside CI or via shell commands. No Kim involvement required.
- **Kim-CLI gates**: Kim runs a command and observes exit code or output. Per §0.10 mandatory after surface work.
- **Kim-browser gates**: Kim opens GitHub UI or test PR and confirms expected state.

**Per DS-21 (Phase F):** `<PHASE>_COMPLETE` row CANNOT be written until `KIM_BROWSER_SMOKE_PASSED` row is also written for any phase that has Kim-CLI or Kim-browser gates (i.e., all phases except F).

## §9 Rollback

Per-phase rollback procedures.

| Phase | Rollback procedure |
|---|---|
| A | `git revert` the deploy script change. The added gates are pure additive; pre-deploy mtime + post-deploy sha256 + curl smoke can each be commented out independently to isolate problems. The build-sha injection in vite.config.ts also git-revertable. LD row stays as `superseded` for traceability. |
| B | GitHub UI: turn off branch protection rules. (Risk: someone could force-push during the window — coordinate with Kim before rolling back.) |
| C | Disable `ai_review.yml` workflow (rename to `.disabled`); remove from required-checks list in branch protection. The Anthropic API key can stay (no harm idle). LD row stays as `superseded`. |
| D | Move `zero-error-qa.yml` and `rn-expo-gate.yml` back to `.disabled` extension in RN repo. Drafts in `Production/github_actions/` remain unchanged. |
| E | `git revert` the playwright_e2e.yml + playwright.config.ts changes. Remove fixture data from `Event_e2e_fixture/.pristine/` if uncomfortable having it (low risk to leave). The 6 specs remain in the repo as-is — re-defer them with a comment block. |
| F | `git revert` the SKILL.md change. DS-21 entry removed. Phase 6.6 cross-reference removed. PATCH `prod_reference_docs` to revert version. |
| G | Delete `~/.git/hooks/pre-commit` from the local checkout. (Hook is local-only, not committed — rolling back is one rm command.) `.last_deploy` file can stay or be deleted; it's harmless either way. LD row stays as `superseded`. |

**Cross-phase rollback:** If multiple phases are landed in the same session and one needs rollback, prefer per-phase rollback over wholesale revert. Each phase is independent at the file level.

## §10 Out of Scope (V1)

Explicitly NOT in this spec — prevents scope creep during execution.

- Redesigning smoke.yml or playwright_e2e.yml beyond Phase E's project grouping.
- Touching React Native app code (only activating already-drafted workflows).
- Migrating to GitHub Enterprise tier or any tooling beyond GitHub Pro.
- Introducing Husky / lefthook / any cross-machine pre-commit framework (Phase G is intentionally local-only).
- Adding inline AI review comments via the GitHub Reviews API (Phase C uses single-PR-comment as v1; inline as v2 if Kim wants).
- Building a custom GitHub App or Probot bot (Decision A from prompt was deferred in favor of Decision B).
- Rewriting deploy_storyboard_v59.sh from scratch (LD-541 stands; we add gates).
- Multi-repo synchronization beyond Phase D's RN workflow activation.
- Automated rollback on failed deploy (Phase A's gates are pre-checks; rollback automation is a separate concern).
- Slack / email notifications on PR review or deploy failures.
- Cost dashboard for AI review API usage (per Rule 19, hardcoded estimates are forbidden — but a real dashboard is V2).

## §11 Dependencies

**Hard prerequisites (must exist before phase begins):**

- Phase A: existing `Production/scripts/deploy_storyboard_v59.sh` (LD-541). Existing `Production/tools/storyboard-v2/dist/index.html`. Existing fanout files at `Production/Event_*/storyboard_v59_prod.html`.
- Phase B: GitHub Pro subscription active. Kim's owner-level access to both `kimhyla/mindfulnest-tooling` and `kimhyla/MindfulNest`.
- Phase C: Phase B complete (so `ai_review` can be added to required-checks). `Production/API_KEYS_MASTER.md` accessible. claude-api skill loaded.
- Phase D: `~/Projects/MindfulNest/` checked out on this machine. Existing drafts at `Production/github_actions/zero-error-qa.yml` and `Production/github_actions/rn-expo-gate.yml`. Supporting scripts at `Production/scripts/{test_firestore_rules.js, ai_policy_replay.py, media_golden_probe.py}`.
- Phase E: existing `Production/Event_1/` content. 6 deferred specs already in repo (just unwired).
- Phase F: `Production/.claude/skills/zero-error-qa/SKILL.md` accessible. Rule 15 reference docs registry sync OK.
- Phase G: Phase A complete (deploy script writes `.last_deploy`). Local checkout of tooling repo at expected path.

**Soft dependencies (nice-to-have but not blocking):**

- Phase A's vite.config.ts injection: easier if vite is already used; if not, build-sha can be injected by a post-build sed step instead.
- Phase E's project grouping: cleaner if all 18 specs can be tagged consistently; if 1-2 specs resist tagging, leave them as `default` project.

**Unblocks downstream:**

- Phase A unblocks: every future deploy. Eliminates today's recurring failure class.
- Phase B unblocks: Phase C (required-checks need branch protection).
- Phase C unblocks: high-leverage PR review at solo-dev cadence; surfaces issues before merge.
- Phase D unblocks: RN repo has zero-error-qa enforcement parity with tooling repo.
- Phase E unblocks: 6 existing specs go from "written" to "actually running"; behavioral parity is now CI-enforced.
- Phase F unblocks: future phase boundaries are HARD on browser smoke (eliminates the "almost done" failure class).
- Phase G unblocks: trustworthy commits — what's in the repo matches what Kim is running.

**Parallelism:**

- Phase A first (highest priority + several phases reference its `.last_deploy`).
- Phase B can run in parallel with Phase A (independent surfaces).
- Phase C requires Phase B done.
- Phases D, E, F, G can run in parallel after Phase A.
- Total wall-clock with parallelism: ~6-8 hours focused work. Without: 8-12 hours.

## §12 Cursor Cross-Review Prompt

Copy-pasteable for Kim to send to Cursor before terminal execution:

```
You are doing a Cursor cross-review of a tech spec for MindfulNest CI/CD gap-fix work.
The spec is at:
Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md

Read the full spec. Then answer these specific questions:

1. PHASE A — DEPLOY VERIFICATION GATES
   a. Does the pre-deploy mtime check correctly handle the case where dist/index.html
      is missing entirely vs. older than a .tsx?
   b. Does the post-deploy sha256 verify catch the case where one fanout copy is correct
      but another isn't?
   c. Is the curl smoke build-sha injection mechanism robust against a server that's been
      running but cached the OLD HTML?
   d. What happens if vite.config.ts can't be modified (e.g., spec assumes vite but project
      uses webpack/esbuild)?

2. PHASE C — AI REVIEW AUTOMATION
   a. Does the prompt template's rule list match the actual current state of CLAUDE.md?
      Specifically: Rule 24, Rule 32, Rule 35, Rule 19, DS-1..19. Any drift?
   b. Does the system prompt use prompt caching correctly (per claude-api skill)?
   c. What's the failure mode if a PR has multiple commits and the diff cumulates findings
      that contradict each other?
   d. Does the workflow handle the case where the PR is from a fork (different secret access)?

3. PHASE E — PLAYWRIGHT WIRING
   a. Are 18 specs in CI a realistic number — what's the runtime cost? Does the spec's
      proposed project-based grouping (per DS-10) actually reduce runtime, or just
      reorganize?
   b. Is `Production/Event_e2e_fixture/.pristine/` the right canonical location for fixtures,
      or does another path already serve this purpose?

4. PHASE G — PRE-COMMIT HOOK
   a. The hook is local-only (not committed). What happens if Kim works on her work PC
      (Windows) — the hook needs to be installed there separately. Does the install script
      handle Windows / Git Bash environments?
   b. The bidirectional check uses .last_deploy timestamp. What if .last_deploy doesn't
      exist (fresh checkout)? Does the hook fail open or fail closed?
   c. Are there race conditions if Kim runs deploy AND tries to commit at the same time?

5. CROSS-CUTTING
   a. Are there any LDs the spec references that don't actually exist in prod_locked_decisions?
      (Verify LD-505, 507, 508, 519, 531, 541 keys exactly.)
   b. Are the 3 proposed NEW LD keys structurally consistent with existing LD naming
      (decision_key + severity + scope_domain + task_category)?
   c. Does Phase F's DS-21 conflict with any existing DS-N entry I might not have seen?
   d. Does Phase D's "investigate dependency-audit.yml failure" actually have enough
      diagnostic information for a terminal session to act on?

6. RELEASE BLOCKERS
   List anything you'd flag as "do not execute Phase X until Y is resolved." Be specific.

Output as a structured table. No narrative paragraphs.
```

## §13 Notes for Executing Sessions

- Re-read §0 before starting any phase. Especially §0.4 #2 ("don't hallucinate endpoint names") and §0.5 ("don't rely on memory").
- Phase A is HIGHEST priority. Do it first. Today's recurring deploy failures stop the moment Phase A ships.
- Phases B-G can be batched into one or more sessions. Suggested grouping: (B+C as one session — they chain), (D+F as one session — both Tier A), (E and G as separate sessions — each is Tier B).
- Per Rule 35, every `prod_*` write uses `try_post_or_queue`. If the helper isn't importable, halt and surface to Kim — do NOT implement an ad-hoc POST.
- Per Rule 18, the 3 new LDs are registered to Directus IMMEDIATELY when locked, not at session end.
- Per DS-21 (which this spec proposes), no `<phase>_COMPLETE` row writes until Kim's browser/CLI smoke is confirmed.
- The Cursor cross-review prompt at §12 is RECOMMENDED before terminal execution. Run it; fold findings into Phase 0 of whichever phase ships first.

## §14 Pre-execution Discipline Checklist

Use this before starting any phase. Do not proceed until all boxes checked.

```
PHASE X PRE-EXECUTION CHECKLIST
[ ] §0 read fully (Mandatory Operating Mode)
[ ] zero-error-qa skill loaded
[ ] Phase 0 classification confirmed: Tier ___ (A/B/C)
[ ] Phase 0 advocate+counter agents spawned (per tier: 0 / 1+1 / 4+4)
[ ] prod_preflight_reviews row written via try_post_or_queue (Rule 35)
[ ] Predecessor preflight referenced + this spec referenced
[ ] All source files cited in this phase READ FRESH (not from memory)
[ ] Cursor review (if Kim ran it) findings folded in
[ ] Risk classes for this phase identified (per §0.3)
[ ] Smoke gates per phase verification table reviewed
[ ] Escape hatches list reviewed (§0.8 standing + per-phase additions)
[ ] Server staleness baseline captured (lsof PID + .py mtimes) [N/A for non-server phases]
[ ] DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md reviewed for prod_* writes
[ ] Endpoints catalog reviewed — no invented endpoint names [N/A for this spec — minimal new endpoints]
[ ] State shape verified — read actual state.json [N/A for this spec]
[ ] Confidence annotations [CONFIRMED/INFERRED/GUESSED] applied
[ ] Browser smoke deferral plan documented (per §0.10 phase-specific table)

END-OF-PHASE CHECKLIST:
[ ] All smoke gates from phase verification table PASS
[ ] py_compile + npm run build clean (where applicable)
[ ] Server restart + /api/health 200; PID lstart > .py mtime (Rule 29) [Phase A only]
[ ] All Directus writes verified via try_post_or_queue read-back (Rule 35)
[ ] Activity log row <phase>_COMPLETE written with full gate summary +
    deviations honestly documented (per §0.9)
[ ] Independent tail-end verifier subagent run; verdict captured
[ ] KIM_BROWSER_SMOKE_PASSED row written (per DS-21 / Phase F)
[ ] Next-phase handoff stub written
```

## §15 Items I May Have Missed (audit pass)

Honest gap-flag from spec author. Items potentially under-specified or deferred:

1. **Vite vs other build tools.** Phase A's build-sha injection assumes the storyboard-v2 build pipeline uses Vite. If it uses something else (webpack, esbuild, plain TypeScript compiler), the injection mechanism needs to adapt. Mitigation: Cursor cross-review §1d explicitly asks this; executing session must verify before Phase A starts.

2. **GitHub fork PR security model.** Phase C's `ai_review.yml` uses `pull_request` event; on fork PRs, secrets are NOT exposed. This is correct GitHub behavior but means fork PRs get no AI review. For solo-dev work this is fine; for community contributions it's a gap. Mitigation: Cursor cross-review §2d asks this; not a release-blocker for Kim's solo workflow.

3. **`Production/Event_e2e_fixture/.pristine/` may not exist as canonical fixture path.** I asserted this path but did not verify it. If a different fixture path is canonical, Phase E needs to use that one. Mitigation: Cursor cross-review §3b asks this.

4. **Windows / Git Bash compatibility for Phase G hook.** The hook uses `stat -f %m` (BSD/macOS) with `stat -c %Y` (GNU/Linux) fallback — Windows / Git Bash may need a third path. The install script needs to handle this. The §10 escape hatch covers fail-open on path-not-resolved, but doesn't cover the `stat` flag mismatch on Windows. Risk: low (Kim is currently on Mac primarily) but real (work PC pending per memory).

5. **Race conditions in deploy + commit overlap.** Phase G's `.last_deploy` timestamp can race with deploy_storyboard_v59.sh writing it AND a pre-commit hook reading it. Mitigation: low probability for solo-dev work, but Cursor §4c flags it.

6. **Phase E project grouping behavior across the existing 12 wired specs.** I asserted that grouping is additive without breaking the existing 12. If those 12 specs have setup/teardown that depends on running in a specific order, project grouping could break them. Mitigation: per-phase escape hatch says "rollback grouping if it breaks existing 12."

7. **AI review prompt token cost at solo-dev cadence.** I asserted O($0.01-0.10/PR) but did not actually compute against typical PR sizes. A 5K-line PR using sonnet-4 input pricing is genuinely close to $0.50. If Kim has 20 PRs/month, that's $10/month — still cheap, but worth verifying. Mitigation: monitor cost in first month; if it trends high, switch to claude-haiku-4 for review (sonnet only for blocking-finding deep dives).

8. **CodeRabbit Decision A path is fully deferred.** If Decision B (Claude API) underperforms in the first 2 weeks, the Decision A path requires re-doing Phase C from scratch. The spec doesn't currently include a Decision A fallback section. Mitigation: not a release-blocker; can be added in v2 if Kim sees that need.

9. **`prod_reference_docs` PATCH for SKILL.md (Phase F)** assumes the SKILL.md is registered. If it's not yet registered, Phase F also needs to CREATE a row. Mitigation: Phase F Phase 0 step should query first to determine PATCH vs POST.

10. **dependency-audit.yml investigation has indeterminate scope.** Phase D step 5 says "fix root cause" without bounding the work. If the root cause is a real CVE that requires upgrading a deeply-coupled dependency, that's a multi-hour investigation — not the 1-2 hour Phase D estimate. Mitigation: per-phase escape hatch escalates to `prod_blockers` if non-trivial; Kim can re-prioritize.

11. **No spec-level rollback if multiple phases land then one fails.** §9 has per-phase rollbacks but no holistic strategy if (e.g.) Phases A + C + E all merge then Phase E retroactively breaks behavior the AI review catches in Phase C. Mitigation: per-phase merge discipline (each phase is its own PR), so isolated revert is possible.

12. **No automated audit of `MN_SKIP_DROPBOX_EDIT_GATE=1` overrides.** Phase G's override env var could be silently abused. I wrote a "weekly audit" handling note in §7 but did not specify the mechanism. Mitigation: V2 — a cron in `Production/scripts/weekly_preflight_audit.py` or equivalent could grep `prod_activity_log` for the override usage pattern.

---

### Pre-execution amendment 2026-05-06 (Kim, before Phase A starts):

13. **Phase F was originally Tier A (doc-only), discipline-dependent.** Kim flagged 2026-05-06 chat that doc-only enforcement (§36.5 honesty model) leaves the most consequential failure class — Claude declares COMPLETE without browser smoke — as a self-discipline path that has historically failed (Bug 3 origin). Amendment: Phase F upgraded to Tier B with a mechanical hook in `Production/lib/directus.py::try_post_or_queue` that rejects `*_COMPLETE` activity_log writes without a matching `KIM_BROWSER_SMOKE_PASSED` row. New LD `BROWSER_SMOKE_MECHANICAL_GATE_V1` locks the contract. New gates F5–F10 unit-test the hook. Closure: complete; covered in Phase F as written.

14. **CodeRabbit-vs-custom-Claude reversal during Q1 Cursor consult.** Outgoing session initially recommended custom Claude; flipped to CodeRabbit after Cursor's verdict; flipped back to custom Claude after Kim challenged the reversal. Honest reasoning: CodeRabbit catches generic code-quality issues but does NOT enforce Rule 24 / Rule 35 / DS-1..19 / Rule 32 / six-layer contract — i.e., the exact rule classes that have produced Kim's recurring failure patterns. Custom Claude with the prompt template in §Phase C step 4 covers both generic + MindfulNest-specific. Cursor's "least maintenance" argument doesn't hold up because the prompt template is already authored. Closure: spec stays with custom Claude (Phase C unchanged); CodeRabbit explicitly NOT subscribed.

15. **Security scanning was missing from v1 spec.** Previous session's coverage table flagged "Security scanning (CodeQL + Dependabot — easy add to gap-fix; recommend before TestFlight)" but the actual phase was never written. Added 2026-05-07 by Kim's pre-execution amendment as Phase H. Closure: complete; covered in Phase H as written.

## §16 Reference Index

**Sources read for this spec:**
- `Production/.claude/skills/tech-spec/SKILL.md` (template confirmation, §0 / §14 / §15 / §16 mandate)
- Kim's user prompt 2026-05-06 with the LOCKED scope (§13 of skill applies)
- CLAUDE.md (project root) — Rules 18, 19, 24, 26, 27, 29, 32, 33, 35, 36 cited
- Memory: `feedback_directus_schema_canonical.md`, `project_v59_features_planning.md`, `feedback_browser_smoke_required.md`

**Files modified by this spec (re-read at phase start):**
- `Production/scripts/deploy_storyboard_v59.sh` (Phase A + G)
- `Production/tools/storyboard-v2/vite.config.ts` (Phase A; verify build tool)
- `Production/.claude/skills/zero-error-qa/SKILL.md` (Phase F)
- `Production/lib/directus.py` (used in every phase via `try_post_or_queue`)
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` (consulted before every prod_* write)

**Files created by this spec:**
- `Production/scripts/install_pre_commit_hook.sh` (Phase G)
- `mindfulnest-tooling/.github/workflows/ai_review.yml` (Phase C)
- `mindfulnest-tooling/.github/workflows/scripts/claude_review.py` (Phase C)
- `mindfulnest-tooling/.github/workflows/scripts/review_prompt.md` (Phase C)
- `~/.git/hooks/pre-commit` in tooling repo, local only (Phase G)
- `Production/Event_e2e_fixture/.pristine/` fixture data (Phase E)

**External documentation:**
- GitHub Pro pricing + branch protection: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Anthropic API: https://docs.claude.com/en/api/getting-started (claude-api skill provides structured patterns)
- Playwright project configuration: https://playwright.dev/docs/test-projects

**Existing LDs cited (verify present at execution time per §0.5):**
- LD-505 — Tooling repo private at kimhyla/mindfulnest-tooling
- LD-507 — `MANDATORY_E2E_GATE_V1`
- LD-508 — `CI_PLAYWRIGHT_ON_COMMIT_V1`
- LD-519 — `MUTATION_CHANNEL_INVARIANT_V1`
- LD-531 — `SCOPE_ROUTER_V1`
- LD-541 — `STORYBOARD_DEPLOY_PROCESS_V1`

**LDs proposed NEW by this spec (will be locked at execution time):**
- `DEPLOY_VERIFICATION_GATE_V1` (Phase A)
- `AI_REVIEW_AUTOMATION_V1` (Phase C)
- `PRE_COMMIT_DROPBOX_EDIT_GATE_V1` (Phase G)

**DS proposed NEW by this spec:**
- DS-21 in `zero-error-qa` SKILL.md (Phase F)

---

*— End of Spec —*

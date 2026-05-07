# V59 Process Structural Fix — Mandatory E2E Coverage Spec v1

**Date:** 2026-05-03
**Classification:** PROCESS STRUCTURAL FIX — addresses Cursor v9/v10 process smell + Kim's "million more bugs" anxiety
**Predecessor (must ship first):** S5.5c+e bugfix v2 (with Playwright tests written for H12)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Why this exists (the honest answer)

Kim asked Cursor v9 directly: "is this becoming patchwork? am I going to face a million more bugs?"

Cursor v9 answer was 2-part:
1. **Codebase smell:** No. R1/R2/R3/R5 are integration debt; R4 is data policy. Not architectural rot.
2. **Process smell:** YES. "'Future' comments + server-only gates without Playwright/e2e on critical paths — address via H12 + CI, not more prose."

Cursor v10 reinforced: the v10 release-blockers (creature_name vs colloquial_name, lib_key vs key) are EXACTLY the kind of spec↔code drift that mandatory e2e would catch automatically. Without CI running Playwright on every commit, every feature session repeats the loop:

```
spec says X is done
→ server-side gates green
→ Kim opens browser
→ X is actually broken
→ bugfix session
→ repeat
```

This spec breaks the loop. Three structural changes:

1. **Mandatory e2e gate** on every feature session's claimed-functional behaviors
2. **CI workflow** that runs Playwright on commit; gates aren't green unless e2e passes
3. **Lessons-learned doc entry** so future Claudes inherit the standard

## §2 Governing Decisions

### LDs respected

| LD | Reason |
|---|---|
| LD-19 / Rule 19 | No shortcuts; e2e mandatory means no "ship without tests" |
| LD-453 PATCH_INVARIANT_PERSISTENCE_V1 | Pattern of "scaffolded + ship + bugfix" was already a CLAUDE.md Rule 36 concern; this extends to e2e |
| LD-465 PRODUCTION_MAP_V1 + LD-471 STITCHER_FULL_UI_V1 + LD-472 WAVESURFER_TIMELINE_V1 + every feature LD | All have functional gates that should have e2e tests |
| LL-15 (v3 lessons-learned) | "Server-side gates ≠ user-visible correctness" — this spec acts on that lesson |

### NEW LDs this spec writes (3)

| Key | Severity | Purpose |
|---|---|---|
| `MANDATORY_E2E_GATE_V1` | CRITICAL | Cross-session standard: every spec's §4 Phase E gates that test FUNCTIONAL behavior MUST have corresponding Playwright tests in `e2e/`. Server-side gate green + e2e gate green is the minimum. Either alone is insufficient. |
| `CI_PLAYWRIGHT_ON_COMMIT_V1` | HIGH | GitHub Actions workflow runs Playwright on every commit to a feature branch + on PR open + on merge to main. CI status must be green before any "feature shipped" claim. |
| `BROWSER_SMOKE_REDEFINED_V1` | MEDIUM | Browser smoke (Kim hands-on) is now scoped to "does it FEEL right?" subjective UX. NOT "does anything actually work?" — that layer is automated via e2e. Reduces Kim's smoke time from ~15 min/session to ~5 min/session. |

## §3 Approach

### §3.1 Mandatory e2e gate (process change)

**Standard (added to master overview §6):**

> 7. **Mandatory e2e coverage:** Every spec's §4 Phase E (or equivalent) gates that test FUNCTIONAL behavior MUST have corresponding Playwright tests in `Production/tools/storyboard-v2/e2e/`. Server-side gate green + e2e gate green is the minimum. Either alone is insufficient. If a behavior cannot be cleanly e2e-tested, that's a redesign signal — surface to Kim before shipping. Rule 19 (no shortcuts) explicitly extends to e2e: "we'll add tests later" is forbidden.

Applied retroactively to remaining feature sessions:
- **S5.5f** spec already has gate F18 (Playwright). Verify F18 covers every functional gate F1-F17, not just a sample.
- **S5.5g** spec already has gate G15 (Playwright). Same verification.
- **Any future S5.5x or S6+ session:** spec MUST include an e2e gate for every functional behavior in its claim.

### §3.2 CI Playwright workflow

**File:** `Production/github_actions/playwright_e2e.yml` (NEW)

```yaml
name: Playwright e2e

on:
  push:
    branches: [main, claude/*, feature/*]
  pull_request:
    branches: [main]

jobs:
  e2e:
    runs-on: macos-latest  # match Kim's dev environment
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - uses: actions/setup-python@v5
        with:
          python-version: '3.9'
      - name: Install client deps
        working-directory: Production/tools/storyboard-v2
        run: npm ci
      - name: Build dist
        working-directory: Production/tools/storyboard-v2
        run: npm run build
      - name: Install Playwright browsers
        working-directory: Production/tools/storyboard-v2
        run: npx playwright install --with-deps chromium
      - name: Run Playwright e2e
        working-directory: Production/tools/storyboard-v2
        run: npx playwright test --reporter=line
        env:
          STORYBOARD_BASE_URL: http://localhost:5111
      - name: Upload test artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: Production/tools/storyboard-v2/playwright-report/
          retention-days: 7
```

**Critical:** the workflow's `playwright.config.ts` `webServer` field (set in S5.5c+e bugfix v2 H12) handles spinning up production_server.py. CI inherits that config — no separate server-management code in the workflow.

### §3.3 Lessons-learned doc new entry

**File:** `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` (existing v3 lessons doc) OR a new dated doc — terminal Claude picks based on which is canonical.

**New LL entry (LL-26 or equivalent):**

> **LL-26: Server-side gates + Playwright e2e on critical paths is the minimum bar. Either alone produces integration debt.**
>
> Context: v59 client S5.5c+e shipped 2026-05-03 with 31/31 server-side gates green. Browser smoke (Kim hands-on) immediately surfaced 5 distinct integration bugs (drag-drop never wired, scope-refresh missing, contract mismatches, etc.). Cursor v9 named the pattern: "'future' comments + server-only gates without Playwright/e2e on critical paths."
>
> The fix is structural, not better specs:
> - Every functional spec gate has a corresponding Playwright test in `e2e/`
> - CI runs Playwright on every commit; gates aren't green unless e2e passes
> - Browser smoke (Kim) becomes "does it feel right?" subjective UX, not "does anything work?"
>
> Without this fix: every feature session needs a 2-3 hr bugfix session afterwards. With it: bugs catchable by automated test are caught before Kim sees them; her smoke time drops from ~15 min/session to ~5 min/session focused on subjective UX.
>
> Trigger to apply: any time a session ships features that pass server-side gates and immediately surface integration bugs in browser smoke. If this happens twice without the structural fix, STOP feature work and add the fix before the next session.
>
> Reference: `STORYBOARD_V59_PROCESS_STRUCTURAL_FIX_SPEC_v1.md`; `MANDATORY_E2E_GATE_V1`, `CI_PLAYWRIGHT_ON_COMMIT_V1`, `BROWSER_SMOKE_REDEFINED_V1`.

### §3.4 Verify existing Playwright scaffold (Phase A)

Per Agent B audit: `Production/tools/storyboard-v2/e2e/` already has scaffold:
- `smoke.spec.ts`
- `behavioral-parity.spec.ts`
- `rollback.spec.ts`
- `touchpoint-a.spec.ts`
- `helpers.ts`
- `playwright.config.ts`

Phase A audits:
- Are existing tests actually runnable? (`npx playwright test` passes locally?)
- Do they cover any v3 / S5.5c+e functional behaviors? (probably partial)
- What's the coverage gap that S5.5f / S5.5g / future sessions need to fill?

This isn't "build e2e from scratch" — it's "the scaffold exists; lock in mandatory + CI + start filling coverage gaps."

## §4 Implementation Phases

### Phase A — Pre-flight

**A1.** Read this spec + master overview + bugfix v2 (which writes the FIRST e2e tests this spec depends on).

**A2.** Audit `Production/tools/storyboard-v2/e2e/`:
- List existing test files + what each covers
- Run `cd Production/tools/storyboard-v2 && npx playwright test` locally — does the scaffold pass?
- If broken: fix scaffold FIRST before adding new gates (otherwise CI is born red)

**A3.** Verify `playwright.config.ts:webServer` field is set per bugfix v2 H12. If not (because bugfix hasn't shipped yet), STOP — this spec's Phase B depends on bugfix v2's H12.

**A4.** `prod_preflight_reviews` row.

### Phase B — Master overview amendment

**B1.** Edit `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` §6 — add convention #7 per §3.1 above.

**B2.** Read S5.5f and S5.5g specs; verify their existing Playwright gates (F18, G15) actually cover EVERY functional behavior in their respective gate lists. If gaps: add gate amendments (in spec) before they execute.

**B3.** `npm run build` clean.

### Phase C — CI workflow

**C1.** Create `Production/github_actions/playwright_e2e.yml` per §3.2 above.

**C2.** Test workflow locally via `act` (GitHub Actions local runner) OR by pushing to a feature branch and observing CI run.

**C3.** Verify failure mode: deliberately break a Playwright test → push → CI goes red → confirm UI shows red status.

**C4.** Verify success mode: fix the test → push → CI green.

**C5.** Document in workflow file's header comment: any CI failure blocks merge to main; fix tests OR fix code, never disable the workflow.

### Phase D — Lessons-learned amendment

**D1.** Edit `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` — add LL-26 per §3.3 above. (Or create new dated doc per terminal Claude's call.)

**D2.** Register doc in `prod_reference_docs` if creating new doc; PATCH `is_current` if amending existing.

### Phase E — S5.5f and S5.5g spec coverage audit (Phase B's deferred work)

**E1.** Re-read S5.5f spec §4 Phase F gates. Cross-reference each functional gate (F3-F17) against F18's Playwright spec list. If any gate is functional but not in F18's coverage list: amend F18 to include OR justify why exception applies.

**E2.** Same for S5.5g spec §4 Phase G gates vs G15.

**E3.** Both spec amendments via small Edit calls; not full rewrite.

### Phase F — Verification (10 gates)

**F1.** `npm run build` clean.
**F2.** `cd Production/tools/storyboard-v2 && npx playwright test` exits 0 LOCALLY (existing scaffold + bugfix H12 tests).
**F3.** Master overview §6 has new convention #7 about mandatory e2e.
**F4.** `Production/github_actions/playwright_e2e.yml` exists + has correct workflow definition.
**F5.** Push to feature branch → CI workflow triggers → Playwright runs → reports status.
**F6.** Deliberately break a test (revert one v2 H12 test's expectation) → push → CI goes red.
**F7.** Fix the test → push → CI green.
**F8.** Lessons-learned doc has LL-26 entry.
**F9.** S5.5f spec F18 coverage cross-checked against F3-F17; gaps amended.
**F10.** S5.5g spec G15 coverage cross-checked against G3-G14; gaps amended.

### Phase G — LD writes

**G1.** Write 3 NEW LDs: `MANDATORY_E2E_GATE_V1`, `CI_PLAYWRIGHT_ON_COMMIT_V1`, `BROWSER_SMOKE_REDEFINED_V1`.

### Phase H — Closeout

**H1.** `prod_activity_log` row `PROCESS_STRUCTURAL_FIX_COMPLETE` with full 10-gate summary.

**H2.** Update master overview status table with process-structural-fix shipped note.

**H3.** Tail-end verifier subagent.

**H4.** Git commit: `Process structural fix — mandatory e2e + CI Playwright + lessons-learned LL-26 (10 gates green)`.

## §5 Files Created / Modified

### Created
- `Production/github_actions/playwright_e2e.yml` (~50 lines)

### Modified
- `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` (§6 add convention #7)
- `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` (add LL-26)
- `Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md` (F18 coverage amendment if gaps found)
- `Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md` (G15 coverage amendment if gaps found)

## §6 Directus Writes

- `prod_locked_decisions`: 3 NEW LDs
- `prod_activity_log`: phase rows + COMPLETE
- `prod_preflight_reviews`: 1 row
- `prod_reference_docs`: PATCH lessons-learned doc OR POST new dated doc per Phase D2

## §7 Error Cases

| Failure | Handling |
|---|---|
| Existing Playwright scaffold doesn't run cleanly | Fix scaffold FIRST in Phase A2; CI born red is worse than no CI |
| CI workflow runs slow (>30 min) | Profile + parallelize tests; fall back to changed-file-aware test selection if necessary |
| Bugfix v2 hasn't shipped (H12 webServer config missing) | STOP this session; ship bugfix v2 first; this spec depends on H12 infrastructure |
| GitHub Actions billing limits hit (private repo, large team) | Surface to Kim; explore alternatives (Vercel, CircleCI free tier) |
| Test flakiness (intermittent failures) | Mark flaky tests with `test.fixme` until stabilized; do NOT disable the workflow |
| S5.5f or S5.5g coverage gap is large (>5 functional gates without e2e) | Surface to Kim; spec amendments may need to expand scope of those sessions |

## §8 Verification

Done when all 10 gates pass + 3 LDs registered + CI workflow runs green on a real commit + LL-26 entry in lessons-learned + S5.5f/g specs verified for coverage.

## §9 Rollback

- CI workflow file: `git rm Production/github_actions/playwright_e2e.yml`
- Master overview amendment: `git checkout -- Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`
- Lessons-learned amendment: `git checkout -- LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md`
- LDs: PATCH to `status='superseded'`

If CI proves disruptive (false positives, infra issues), workflow can be disabled via repo settings; LDs stay valid as the standard, just unenforced until CI is fixed.

## §10 Out of Scope (defer)

- Adding e2e tests for v3 baseline behaviors (deferred; covered organically as features ship)
- Visual regression testing (Percy or similar) — defer; functional e2e is the priority
- Cross-browser testing (Safari, Firefox) — Chromium-only this session; expand later
- Performance/load testing — defer
- Test coverage reporting — defer
- E2E for milestone-only flows (already lightly covered in bugfix v2 H4) — expand as needed in S5.5f/g
- E2E for backend-only changes (Python script tests) — Python's existing pytest setup handles those; this spec is e2e/UI-focused

## §11 Dependencies

**Hard dependency:** S5.5c+e bugfix v2 must ship FIRST. Bugfix v2 writes the H12 Playwright tests + sets up `playwright.config.ts:webServer`. This spec extends that to CI + makes it mandatory.

**Soft dependencies:** S5.5f and S5.5g specs already have Playwright gates (F18, G15); this spec verifies their coverage and amends if needed.

## §12 Notes for the Executing Session

- This is a PROCESS spec, not a feature spec. The deliverable is a workflow file + 3 doc edits + 3 LDs.
- DO NOT attempt to "make the whole codebase have e2e coverage" in this session. Out of scope. Coverage grows organically as features ship.
- The CI workflow is the LOAD-BEARING piece. The doc amendments + LDs codify the standard but the CI is what enforces it.
- If existing Playwright scaffold is broken (Phase A2 fail): FIX SCAFFOLD before continuing. Born-red CI is worse than no CI.
- `act` (local GitHub Actions runner) is recommended for Phase C2 testing without burning CI minutes; alternative is push-to-feature-branch.
- The "process smell" Cursor v9 named is real. This spec acts on it. Future sessions inherit the standard.
- Kim's anxiety about "a million more bugs": this is the answer. Mandatory e2e + CI catches integration debt at commit time, not at browser smoke time.

## §13 Cursor Review Checklist (optional; can skip if scope tight)

If sending to Cursor:

1. Is the GitHub Actions workflow YAML syntactically correct + uses pinned action versions?
2. macos-latest runner: does Anthropic / your team have macOS minutes available? Would ubuntu-latest work for headless Chromium?
3. Should the workflow trigger on every push or only on PR open + main? Tradeoffs.
4. `npm ci` requires `package-lock.json` exact match — is that current in the repo?
5. `--with-deps chromium` install — does this work on macos-latest runners cleanly?
6. STORYBOARD_BASE_URL env var: is `playwright.config.ts` configured to read it OR is hardcoded baseURL fine for CI?
7. Test artifacts upload on failure: 7-day retention OK or longer?
8. Is the LL-26 entry the right level of detail, or too prescriptive?
9. Should `MANDATORY_E2E_GATE_V1` be CRITICAL severity or HIGH? Critical = blocks future merges; high = strong recommendation.
10. Should we add a CHANGELOG.md or release-notes practice as a follow-up to this spec, or is git history + Directus activity log sufficient?

Append findings as §14.

---

**End of process structural fix spec v1.**

Designed for terminal execution AFTER S5.5c+e bugfix v2 ships. Cursor pre-review is optional given the scope is mostly mechanical (workflow file + doc amendments).

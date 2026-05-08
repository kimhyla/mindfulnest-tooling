# Gap-Fix Full Execution (Pattern B Clustered) — Fresh Terminal Handoff

> **⚠️ SUPERSEDED 2026-05-07 evening — DO NOT USE**
>
> This handoff was authored before the storyboard side-fix session shipped (2026-05-07 → 2026-05-08 overnight). The canonical gap-fix handoff is now [V59_GAP_FIX_HANDOFF_20260508.md](V59_GAP_FIX_HANDOFF_20260508.md), which:
> - Targets the **tooling repo** (`~/Projects/mindfulnest-tooling`) per LD-505, not the Dropbox tree
> - Uses **overnight autonomous mode** (single PR, morning report) instead of Pattern B clustered halts
> - Incorporates side-fix outcomes: Bug 1 fixed (PR #7 → 5733b21), Bug 2/4 deferred Tier C, Option B locked, LD 545 closure mechanism
> - Acknowledges the 28-file Dropbox/tooling divergence (preserved on `claude/preserve-uncommitted-divergence-20260507`)
> - Is paired with the side-fix morning report at [V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md](V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md)
>
> The spec amendments referenced below (Phase F mechanical hook, Phase H security scanning, URL correction with `grep -c`) are STILL CANONICAL — they live in `V59_CICD_GAP_FIX_SPEC_v1.md` and execute under either handoff. Only this handoff document is superseded; the spec it references is current.
>
> Preserved as historical record of the Pattern B clustered approach in case it's useful for future reference.

---

**For:** Fresh Claude Code terminal CLI session (Hardened Session Protocol per CLAUDE.md Rule 19)
**Spec:** `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` (1208 lines, post-2026-05-07 amendments — Phase F mechanical hook + Phase H security scanning + §3/§16 drift cleanup)
**Phases:** ALL (A through H) in one session, with 3 cluster halt points
**Classification:** mixed (per phase — see spec); Cluster 1 starts Tier B
**Estimated execution:** 10-15 hours background; ~30 min Kim active time across 3 checkpoints
**Authored:** 2026-05-07 by Desktop prep session (Kim's gap-fix execution kickoff)
**Amended:** 2026-05-07 — converted from per-phase scope to all-8-phases Pattern B clustered execution

---

## What was done in prep (you start with these already true)

`[CONFIRMED — Desktop prep session 2026-05-07]`

1. **Greenfield LD registered.** `prod_locked_decisions` id=544, `decision_key=MAIN_APP_CICD_GREENFIELD_DESIGN_V1`, severity=HARD, scope_domain=production. Prior queued write had silent-failed on stale enum values (HIGH→HARD, architectural→tech_stack, missing date_locked + source_document); re-registered cleanly.

2. **Pending writes queue cleared.** 5 stale `prod_activity_log` entries (May 3-6) re-encoded with `details` as dict (not string) and posted as ids 1591–1595. 2 superseded `prod_locked_decisions` retries dropped. Queue file now `[]`. Backup at `pending_directus_writes.json.bak.20260507` (gitignored).

3. **Spec amended (Phase F upgrade + Phase H insertion).** §0 + §2 + Phase F (TIER A → TIER B with mechanical browser-smoke gate in `try_post_or_queue`) + Phase H (NEW — CodeQL + Dependabot security scanning) + §3 / §16 drift cleanup. New LDs queued for execution-time lock: `BROWSER_SMOKE_MECHANICAL_GATE_V1`, `CODEQL_DEPENDABOT_SECURITY_SCAN_V1`. Live schema enums verified `{HARD, SOFT}` per 2026-05-04 migration.

4. **Pre-Phase-A inventory committed.** Branch `claude/pre-phase-a-inventory-20260507` @ HEAD `bd15511a` from base `main` @ `9efaabd`. 28 commits, +493 files (62→555 tracked). Both anchor files now in git: `Production/lib/directus.py` (commit `a08b1c0`) and `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` (commit `4697393`). 673 files surfaced for Kim review at `/tmp/SURFACE_FOR_KIM_REVIEW.tsv`. 47 skipped (`_temp_`, `_sandbox`, `.deploy_backups`). 27 pre-existing modifications untouched.

5. **Drift cleanup pass.** §16 LDs list brought to parity with §2 (5 entries). Handoff doc `V59_FRESH_THREAD_HANDOFF_20260506.md` updated 5 stale references (was "7 phases A-G / 983 lines"; now "8 phases A-H / 1206 lines"). MEMORY.md line 4 updated to current state with historical context preserved. §3 of spec updated to "8 phases (A-H) ... originally 7 gaps."

6. **Q1-Q4 architectural questions resolved.**
   - Q1: **PATCH** (Cursor verdict 2026-05-07 — patch the existing tooling-repo CI/CD; no rebuild)
   - Q2: **Custom Claude API** (NOT CodeRabbit — CodeRabbit catches generic issues but doesn't enforce Rule 24 / Rule 35 / DS-1..21 / Rule 32 / six-layer)
   - Q3: **GitHub Pro purchased** (Kim 2026-05-07; confirm active before Phase B)
   - Q4: **Manual deploy + CI verify-after** (no self-hosted runner — Phase A's FATAL gates + Phase G's pre-commit hook close the loop without runner maintenance)

7. **Pattern B clustered execution agreed.** Kim 2026-05-07 chat: "yes lets go with the pattern b execution." Single CLI session, 3 cluster halt points (after C, after E, after H), `BROWSER_SMOKE_DEFERRED` audit rows handle Phase F's mechanical-hook for mid-cluster phases until cluster boundary confirms full smoke. Cluster 1 = A→B→C (~3-7 hr execution; ~15 min Kim active); Cluster 2 = D→E (~3-6 hr; ~5 min Kim); Cluster 3 = F→G→H (~2.5 hr; ~10 min Kim). Total: ~10-15 hr background; ~30 min Kim active across 3 checkpoints.

---

## Pre-paste checklist (Kim — verify before pasting cold-start prompt)

- [ ] You are in **Claude Code terminal CLI**, NOT Desktop (Hardened Session Protocol per CLAUDE.md Rule 19; PreToolUse hooks for governed-file edits silently no-op in Desktop)
- [ ] CWD will be the main repo root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files`
- [ ] Branch `claude/pre-phase-a-inventory-20260507` exists locally with HEAD `bd15511a` (verify: `git log --oneline -1 claude/pre-phase-a-inventory-20260507`)
- [ ] GitHub Pro upgrade COMPLETED on `kimhyla` account (`gh api user --jq '.plan.name'` returns non-null) — REQUIRED before pasting because Cluster 1 includes Phase B branch protection which can't land without Pro.
- [ ] No production_server.py running on port 5111 OR you accept it will be restarted during Phase A's smoke gates (verify: `lsof -ti:5111`)
- [ ] Anthropic API key available in `Production/API_KEYS_MASTER.md` (for Phase C in Cluster 1)
- [ ] You have ~10-15 hours of wall-clock window for the terminal session to run in background. Expect 3 ping-back moments at cluster boundaries (~15 min, ~5 min, ~10 min Kim time).

---

## Cold-start prompt — paste everything between `===BEGIN===` and `===END===` into the fresh terminal

```
===BEGIN===
You are executing the FULL gap-fix (all 8 phases A→B→C→D→E→F→G→H) in
ONE session per Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md, using
Pattern B clustered execution. You halt at 3 cluster boundaries for
Kim's confirmation; otherwise you run autonomously.

Phase A is HIGHEST PRIORITY first because it eliminates today's recurring
failure class: silent stale-build deploys (Bug 3 origin: 2026-05-06 —
Phase A of v59 features declared COMPLETE without ever running
deploy_storyboard_v59.sh; browser served 6+ hour stale UI for 4 hours).

OPERATING MODE (mandatory):

1. **You are in Claude Code terminal CLI** per Hardened Session Protocol.
   Confirm via system prompt — if anything suggests Desktop/Cowork, STOP
   and tell Kim to switch.

2. **Phase 0 pre-flight (per phase, per spec §4 tier classification):**
   Load skills ONCE at session start; re-spawn agents per phase.
   - Load `zero-error-qa` skill (governs Phase 0 + DS-1 through DS-21)
   - Load `tech-spec` skill (in case architectural decision surfaces)
   - Load `no-shortcuts` skill (Rule 19 enforcement)
   - Load `dashboard-gate` skill (Directus discipline)
   - Per-phase agent counts: A=1+1 (Tier B), B=0 (Tier A), C=1+1 (Tier B),
     D=0 (Tier A), E=1+1 (Tier B), F=1+1 (Tier B), G=1+1 (Tier B),
     H=0 (Tier A). Synthesize → write `prod_preflight_reviews` row via
     try_post_or_queue per phase referencing this spec.

3. **Skills + LD existence preflight (per spec §0.1):** Each phase's LDs:
   - A: DEPLOY_VERIFICATION_GATE_V1 (new)
   - B: BRANCH_PROTECTION_TOOLING_V1, BRANCH_PROTECTION_RN_V1 (new)
   - C: AI_REVIEW_AUTOMATION_V1 (new)
   - D: (no new LD — workflow activation only; documents N/A)
   - E: (no new LD — Playwright spec additions; documents N/A)
   - F: BROWSER_SMOKE_MECHANICAL_GATE_V1 (new) + DS-21 SKILL.md edit
   - G: PRE_COMMIT_DROPBOX_EDIT_GATE_V1 (new)
   - H: CODEQL_DEPENDABOT_SECURITY_SCAN_V1 (new)
   No AMEND/SUPERSEDE expected in this gap-fix; document N/A per phase.
   Rule 36 N/A (no Path B HTML patches in any gap-fix phase).

READ FIRST (in order, targeted reads — do NOT full-read large files):

1. CLAUDE.md (Rules 18, 19, 24, 26, 27, 29, 32, 33, 35, 36 — full read
   of each rule)
2. Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md (§0 full, §2 governing
   decisions, §3 approach, §4 Phase A through Phase H — ALL eight phase
   sections, not just Phase A; §15 audit, §16 reference index)
3. Production/scripts/deploy_storyboard_v59.sh (Phase A modifies; Phase G
   reads `.last_deploy` written here)
4. Production/tools/storyboard-v2/vite.config.ts (Phase A — build-sha
   injection)
5. Production/lib/directus.py (Phase F modifies try_post_or_queue;
   verify importable now per Rule 35)
6. Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md (§1
   prod_locked_decisions schema — confirm enum values for severity
   {HARD,SOFT}, task_category, scope_domain; §N prod_activity_log)
7. Production/.claude/skills/zero-error-qa/SKILL.md (Phase F edits DS-21
   + Phase 6.6)
8. Memory: feedback_six_layer_feature_verification.md (six-layer
   contract; foundation for Cluster smoke confirmations)

CURRENT STATE (per prep session 2026-05-07):

- Branch: claude/pre-phase-a-inventory-20260507 @ HEAD bd15511a (28
  commits ahead of main)
- 27 pre-existing modifications in working tree (un-staged) — leave alone
- GitHub Pro purchased on kimhyla
- Greenfield LD MAIN_APP_CICD_GREENFIELD_DESIGN_V1 registered as id=544
- Both anchor files (directus.py + gap-fix spec) committed
- Q1 PATCH / Q2 custom Claude / Q3 Pro / Q4 manual+CI-verify all locked

PATTERN B CLUSTER EXECUTION — MANDATORY:

You will execute all 8 phases in this single session, halting at 3
cluster boundaries for Kim's confirmation.

Cluster 1: Phases A → B → C
Cluster 2: Phases D → E
Cluster 3: Phases F → G → H

Cluster halt protocol (at end of each cluster):
1. Write a CLUSTER_<N>_PASS_REQUEST activity_log row via
   try_post_or_queue. details: {cluster_number, phases_completed,
   verification_summary, kim_action_required, expected_kim_time_min}
2. Surface to Kim verbatim:
   "Cluster <N> complete. Phases <list>. Verification summary:
   <summary>. Your turn (~<X> min):
   <numbered list of concrete tasks>
   Confirm with 'cluster <N> pass' or specific issues."
3. WAIT for Kim's verbatim confirmation in chat. Do NOT advance to
   the next cluster without it.
4. On Kim confirmation:
   a. Write KIM_BROWSER_SMOKE_PASSED rows — one per phase in the
      cluster — with details: {phase: "PHASE_X", verification_table:
      "<reproduced from spec>", kim_quote: "<verbatim>", captured_at:
      "<ISO>"}.
   b. Then write each phase's PHASE_X_COMPLETE row.
   c. Resume next cluster.

Phase F mechanical hook interaction:
- Phase F installs the try_post_or_queue gate that rejects *_COMPLETE
  writes without a matching KIM_BROWSER_SMOKE_PASSED row.
- Phase F lands MID-CLUSTER-3, before G and H complete.
- For Phases F, G, H within Cluster 3: write the COMPLETE rows AFTER
  the cluster boundary confirms (so the SMOKE_PASSED rows exist
  first). Order at end of cluster 3:
    1. Kim confirms cluster 3 pass
    2. Write SMOKE_PASSED for F, G, H (each with own details.phase)
    3. Write PHASE_F_COMPLETE, PHASE_G_COMPLETE, PHASE_H_COMPLETE in
       order
- For Clusters 1 and 2 (BEFORE Phase F's hook is installed): the
  mechanical gate is not yet active, so write SMOKE_PASSED rows then
  COMPLETE rows in the same order, but with no library enforcement —
  this still satisfies DS-21 by discipline + audit-trail.
- If you absolutely must write a COMPLETE row mid-cluster (e.g., Phase
  F's own self-application contract), use BROWSER_SMOKE_DEFERRED
  override path:
    1. Set env var MN_SKIP_BROWSER_SMOKE_GATE=1 in your subprocess
    2. Write BROWSER_SMOKE_DEFERRED row first with details:
       {phase: "PHASE_X", reason: "cluster boundary deferred — SMOKE
       will land at end of cluster", approved_by: "Kim 2026-05-07
       Pattern B agreement", deferred_until: "cluster 3 confirmation"}
    3. Then write the COMPLETE row
    4. Verify by querying the row exists; if not, halt and surface.
  Default behavior: avoid the deferral path; just batch COMPLETE writes
  at cluster boundaries.

PER-PHASE SUMMARY (full detail in spec §4 — do not duplicate here):

Phase A — Deploy Verification Gates (Tier B, 1+1 agents, 1-2 hr)
- Files: Production/scripts/deploy_storyboard_v59.sh,
  Production/tools/storyboard-v2/vite.config.ts
- LD: DEPLOY_VERIFICATION_GATE_V1
- 6 gates A1-A6 (A2/A3/A4 are Kim-CLI smoke at Cluster 1 boundary)
- Cluster 1, runs first

Phase B — Branch Protection (Tier A, 0 agents, 30 min)
- Files: GitHub repo settings (kimhyla/mindfulnest-tooling +
  kimhyla/mindfulnest-ios) — gh api PATCH
- LDs: BRANCH_PROTECTION_TOOLING_V1, BRANCH_PROTECTION_RN_V1
- 5 gates B1-B5 (B1/B2/B3/B4 are Kim-browser/Kim-CLI at Cluster 1)
- Cluster 1, requires GitHub Pro confirmed

Phase C — AI Review Custom Claude (Tier B, 1+1 agents, 2-4 hr)
- Files: ~/Projects/mindfulnest-tooling/.github/workflows/ai_review.yml
  (NEW), prompt template
- LD: AI_REVIEW_AUTOMATION_V1
- 7 gates C1-C7 (C2/C3/C4/C5 are Kim-browser/Kim-CLI at Cluster 1)
- Cluster 1, requires Phase B done first for required-checks wiring;
  needs ANTHROPIC_API_KEY secret in GitHub

Phase D — RN Workflow Activation (Tier A, 0 agents, 1-2 hr)
- Files: ~/Projects/MindfulNest/.github/workflows/zero-error-qa.yml,
  rn-expo-gate.yml
- No new LD
- 6 gates D1-D6 (D3/D4 are Kim-browser at Cluster 2)
- Cluster 2, parallel-safe with E

Phase E — Playwright Specs (Tier B, 1+1 agents, 2-4 hr)
- Files: ~/Projects/mindfulnest-tooling/tests/e2e/*.spec.ts (6 new),
  playwright.config.ts
- No new LD
- 4 gates E1-E4 (E2 is Kim-browser at Cluster 2)
- Cluster 2

Phase F — Browser Smoke + Mechanical Hook (Tier B, 1+1 agents, 90 min)
- Files: Production/.claude/skills/zero-error-qa/SKILL.md,
  Production/lib/directus.py, prod_reference_docs PATCH
- LD: BROWSER_SMOKE_MECHANICAL_GATE_V1 + DS-21 entry
- 11 gates F1-F11 (F4 is Kim-CLI re-read at Cluster 3)
- Cluster 3, lands MID-cluster — see Phase F mechanical hook
  interaction above

Phase G — Pre-commit Dropbox-edit Hook (Tier B, 1+1 agents, 1 hr)
- Files: ~/Projects/mindfulnest-tooling/.git/hooks/pre-commit (LOCAL,
  not in repo), Production/scripts/install_pre_commit_hook.sh
- LD: PRE_COMMIT_DROPBOX_EDIT_GATE_V1
- 6 gates G1-G6 (G2/G3/G4 are Kim-CLI at Cluster 3)
- Cluster 3

Phase H — Security Scanning CodeQL + Dependabot (Tier A, 0 agents, 30 min)
- Files: ~/Projects/mindfulnest-tooling/.github/workflows/codeql.yml,
  .github/dependabot.yml; same in mindfulnest-ios
- LD: CODEQL_DEPENDABOT_SECURITY_SCAN_V1
- 6 gates H1-H6 (H3/H4 are Kim-browser at Cluster 3)
- Cluster 3, runs LAST

CLUSTER BOUNDARY TASKS FOR KIM (your job to surface verbatim):

Cluster 1 boundary (~15 min Kim time) — after Phases A+B+C:
- (A) Run 3 intentional-break smoke tests for deploy gates (gates
  A-2/A-3/A-4):
  1. cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" && touch Production/tools/storyboard-v2/src/components/SomeFile.tsx && bash Production/scripts/deploy_storyboard_v59.sh
     → expect FATAL exit (uncompiled changes); revert touch
  2. echo "corrupt" >> Production/Event_1/storyboard_v59_prod.html && bash Production/scripts/deploy_storyboard_v59.sh
     → expect FATAL exit (sha mismatch); restore via git checkout Production/Event_1/storyboard_v59_prod.html
  3. kill $(lsof -ti:5111) && bash Production/scripts/deploy_storyboard_v59.sh
     → expect FATAL exit (build-sha curl miss); restart server manually after
     ℹ️ When you implement Phase A.3 deploy script curl probe: the URL is
     http://localhost:5111/ (root), NOT /storyboard_v59_prod.html. The
     server serves the SPA at root; filename probes 404 by design. Use
     `grep -c "build-sha.*$BUILD_SHA"` for diagnostic count, FATAL when
     count == 0. See feedback memory feedback_storyboard_url_serves_at_root.md
     and spec §Phase A.3.
- (B) Verify branch protection (gates B1+B2):
  gh api repos/kimhyla/mindfulnest-tooling/branches/main/protection | jq '.required_status_checks.contexts'
  → expect array with smoke + playwright_e2e + ai_review
- (C) Verify AI review fires (gates C3+C4): terminal Claude opens a test
  PR with `console.log('debug')`; you wait 5 min; check PR for AI comment
  via gh pr view <num> --comments; comment should flag the console.log
- Reply in chat: "cluster 1 pass" OR "cluster 1 fail: <specific issues>"

Cluster 2 boundary (~5 min Kim time) — after Phases D+E:
- (D) Run gh run list -R kimhyla/mindfulnest-ios --limit 5 → confirm
  zero-error-qa.yml + rn-expo-gate.yml ran green on the test PR
  (gates D3+D4)
- (E) Run gh run list -R kimhyla/mindfulnest-tooling --workflow=playwright_e2e.yml --limit 1
  → confirm 18 specs pass on most recent run (gate E2)
- Reply in chat: "cluster 2 pass" OR specific issues

Cluster 3 boundary (~10 min Kim time) — after Phases F+G+H:
- (F) Read DS-21 paragraph in Production/.claude/skills/zero-error-qa/SKILL.md.
  Confirm the wording matches your intent (gate F4 — the only gate that
  genuinely requires human judgment, not automation).
- (G) Test pre-commit hook (gate G2):
  cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" && touch Production/Event_1/storyboard_v59_prod.html && cd ~/Projects/mindfulnest-tooling && git add . && git commit -m "test"
  → expect FATAL exit referencing Dropbox runtime tree drift
- (H) Confirm Dependabot active (gate H4):
  gh api repos/kimhyla/mindfulnest-tooling/vulnerability-alerts -i 2>&1 | head -1
  → expect HTTP/2.0 204 No Content (active)
- Reply in chat: "cluster 3 pass" OR specific issues

END-OF-SESSION PROTOCOL:

After cluster 3 pass:
- Write final activity_log row GAPFIX_ALL_PHASES_COMPLETE with details
  summarizing all 8 phases + LD ids.
- Run bash Production/scripts/deploy_storyboard_v59.sh ONCE with new
  gates active to validate the full pipeline (this is the actual deploy
  that closes Bug 3).
- Draft handoff stub at Production/docs/POST_GAPFIX_BUG_DIAGNOSIS_HANDOFF.md
  — covers (a) re-test Bug 1 (BG ref drop 400), (b) re-test Bug 2
  (Add Beat no-render), (c) resume v59 features Phase B/C/D/E.
- Report final state to Kim.

ESCAPE HATCHES (per spec §0.8 — standing):

- Cursor v8/v9 review flagged release-blocker → STOP (N/A — Cursor
  verdict PATCH already obtained)
- Layer 6 smoke fails → STOP (mid-cluster smoke failure halts the
  cluster; do NOT cross the cluster boundary)
- Schema drift detected → STOP, update reference doc + memory
- LD AMEND/SUPERSEDE not found → STOP (N/A — gap-fix only adds, no
  supersession)
- Handler refactor breaks py_compile → STOP, revert via git
- Rule 26 Opus escalation triggered → STOP, escalate

Phase-specific (apply within the right cluster):

- Phase A: find returns no .tsx files → FATAL and surface (directory
  layout wrong); curl returns non-200 or empty → retry once after 5s
  sleep; second fail → FATAL with diagnostic dump (lsof -ti:5111, ps aux
  | grep production_server); git rev-parse fails (detached HEAD) → use
  git log -1 --pretty=%h fallback; if both fail, FATAL
- Phase F: if details.phase filter syntax does NOT work on Directus
  (test in Phase 0 — query a known row), fall back to flat phase_key
  column strategy and document deviation per §0.9; if unit tests F6-F9
  fail, REVERT directus.py via git and stop — do not patch on broken
  behavior
- Phase G: hook fail-open on path-not-resolved (per spec §10); Windows
  / Git Bash stat flag mismatch is known risk — surface if hit
- Phase H: if Phase B branch protection not yet active, do NOT add
  CodeQL as required-status check; document and surface

GIT DISCIPLINE:

- Currently on branch claude/pre-phase-a-inventory-20260507 (from prep)
- Create per-cluster feature branches FROM this base branch:
  - Cluster 1: git checkout -b claude/gapfix-cluster-1-deploy-protect-aireview
  - Cluster 2 (after cluster 1 merged or separately branched from base):
    git checkout -b claude/gapfix-cluster-2-rn-playwright
  - Cluster 3: git checkout -b claude/gapfix-cluster-3-smoke-precommit-security
- All commits to feature branches only — NEVER to main
- Use specific file adds (git add <path>), NEVER git add -A or git add .
- Commit message convention per phase, e.g.:
  feat(gapfix): add deploy verification gates (Phase A)
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
- DO NOT push (Kim reviews before push)

Apply Rule 24 confidence annotation throughout.
Apply Rule 27 (delete obsolete workarounds): when fixing the deploy gate,
audit any prior "manual deploy reminder" patterns and DELETE them.
Apply Rule 33 (verify server + file before "try it now").
Apply spec §0.9 deviation logging when reality diverges from spec.

BEGIN:
- Run Phase 0 pre-flight (per phase, per Tier classification)
- Read source files cited above FRESH (per §0.5 — don't rely on memory)
- Execute Cluster 1 (A → B → C) → halt for Kim
- Execute Cluster 2 (D → E) → halt for Kim
- Execute Cluster 3 (F → G → H) → halt for Kim
- Write GAPFIX_ALL_PHASES_COMPLETE + post-gapfix handoff stub
- Report back with proof of execution per cluster
===END===
```

---

## Notes for Kim (post-paste)

### What Kim does at Cluster 1 boundary (~15 min) — after Phases A+B+C

1. **(A) Three intentional-break smoke tests for deploy gates** (gates A-2/A-3/A-4):
   - **A-2:** `cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" && touch Production/tools/storyboard-v2/src/components/SomeFile.tsx && bash Production/scripts/deploy_storyboard_v59.sh` → expect FATAL exit (uncompiled changes); revert touch.
   - **A-3:** `echo "corrupt" >> Production/Event_1/storyboard_v59_prod.html && bash Production/scripts/deploy_storyboard_v59.sh` → expect FATAL exit (sha mismatch); restore via `git checkout Production/Event_1/storyboard_v59_prod.html`.
   - **A-4:** `kill $(lsof -ti:5111) && bash Production/scripts/deploy_storyboard_v59.sh` → expect FATAL exit (build-sha curl miss); restart server manually after.
   ℹ️ The deploy script's curl probe targets `http://localhost:5111/` (root), NOT `/storyboard_v59_prod.html`. The server serves the SPA at root; filename probes 404 by design. See feedback memory `feedback_storyboard_url_serves_at_root.md`.
2. **(B) Verify branch protection** (gates B1+B2): `gh api repos/kimhyla/mindfulnest-tooling/branches/main/protection | jq '.required_status_checks.contexts'` → expect array with smoke + playwright_e2e + ai_review.
3. **(C) Verify AI review fires** (gates C3+C4): terminal Claude opens a test PR with `console.log('debug')`; you wait 5 min; check PR for AI comment via `gh pr view <num> --comments`; comment should flag the console.log.
4. **Reply in chat:** "cluster 1 pass" OR "cluster 1 fail: <specific issues>".

### What Kim does at Cluster 2 boundary (~5 min) — after Phases D+E

1. **(D)** `gh run list -R kimhyla/mindfulnest-ios --limit 5` → confirm zero-error-qa.yml + rn-expo-gate.yml ran green on the test PR (gates D3+D4).
2. **(E)** `gh run list -R kimhyla/mindfulnest-tooling --workflow=playwright_e2e.yml --limit 1` → confirm 18 specs pass on most recent run (gate E2).
3. **Reply in chat:** "cluster 2 pass" OR specific issues.

### What Kim does at Cluster 3 boundary (~10 min) — after Phases F+G+H

1. **(F)** Read DS-21 paragraph in `Production/.claude/skills/zero-error-qa/SKILL.md`. Confirm the wording matches your intent (gate F4 — the only gate that genuinely requires human judgment, not automation).
2. **(G)** Test pre-commit hook (gate G2): `cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files" && touch Production/Event_1/storyboard_v59_prod.html && cd ~/Projects/mindfulnest-tooling && git add . && git commit -m "test"` → expect FATAL exit referencing Dropbox runtime tree drift.
3. **(H)** Confirm Dependabot active (gate H4): `gh api repos/kimhyla/mindfulnest-tooling/vulnerability-alerts -i 2>&1 | head -1` → expect `HTTP/2.0 204 No Content` (active).
4. **Reply in chat:** "cluster 3 pass" OR specific issues.

### What runs autonomously between clusters

- **Cluster 1 internals:** Phase A internals (script edits, vite.config.ts injection, LD lock) + Phase B configuration (branch protection via gh api) + Phase C AI review wiring (workflow file + prompt template + secret check).
- **Cluster 2 internals:** Phase D RN moves (workflow files + actionlint) + Phase E spec wiring (6 new Playwright spec files + config updates).
- **Cluster 3 internals:** Phase F hook code (directus.py edits + DS-21 SKILL.md edit + LD lock) + unit tests (F6-F9) + Phase G hook script (pre-commit + installer) + Phase H workflow files (codeql.yml + dependabot.yml across both repos).

You are NOT pinged during these — only at the 3 cluster boundaries.

### Verification at end of session

Ask the terminal session to recite back the contents of the `GAPFIX_ALL_PHASES_COMPLETE` activity_log row, which per the cold-start protocol summarizes all 8 phases + LD ids + per-cluster smoke confirmations. If it can recite cleanly with [CONFIRMED] tags, the gap-fix is genuinely done.

### Escape valve

If the session hits an unexpected blocker mid-cluster, spec §0.9 deviation logging applies: write a `S5_5_GAPFIX_PHASE_<X>_DEVIATION_<id>` row in `prod_activity_log` with `details: {spec_says, reality_is, resolution_proposed, awaiting_kim_decision}`. Note: deviations within a cluster are reported at the cluster boundary, not mid-cluster, unless they trigger a §0.8 hard halt (release-blocker, schema drift, py_compile failure, Rule 26 Opus escalation, Layer 6 smoke fail). Surface verbatim. Don't silently substitute.

---

**End of handoff.**

`[CONFIRMED — handoff authored 2026-05-07 by Desktop prep session; amended 2026-05-07 to Pattern B clustered execution scope; all factual claims tagged with confidence annotation per Rule 24]`

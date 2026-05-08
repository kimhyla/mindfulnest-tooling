# V59 CI/CD Gap-Fix Handoff — 2026-05-08

**For:** Fresh terminal CLI session (Hardened Session Protocol per Rule 19)
**Predecessor:** Desktop session 2026-05-06 → 2026-05-08 + overnight side-fix terminal 2026-05-07 → 2026-05-08
**Status when authored:** Bug 1 server-side fixed (PR #7 → 5733b21 on `claude/post-redeploy-bug-triage`); Bug 2 + Bug 4 deferred Tier C with Option B locked; SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 LD id=545 active; 28-file Dropbox/tooling divergence preserved; gap-fix infrastructure NOT YET BUILT
**Supersedes:** `V59_FRESH_THREAD_HANDOFF_20260506.md` (which is itself in the 28-file divergence and out of date)

---

## ⚠️ Critical context: two-git-tree state

**This project has two parallel git repositories:**

1. **Tooling repo** (`~/Projects/mindfulnest-tooling`) — per LD-505, supposed to be canonical CODE. Has its own `.git/`.
2. **Dropbox tree** (`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files`) — has its OWN `.git/`. De-facto development tree because most editing happens in-place here.

**Current divergence:** 28 files of substantive Dropbox-tree work that does not exist in any tooling repo branch. Preserved on `claude/preserve-uncommitted-divergence-20260507` (Dropbox-resident commit 95e4462). Includes:
- `production_server.py`: +3983/-1889 lines
- `BgTab.tsx`: 517 changed
- `StitcherTab.tsx`: 585 changed
- `state/scope.ts`: present in divergence (relevant to Option B)
- `V59_CICD_GAP_FIX_SPEC_v1.md`: 91 lines changed (THIS spec is in the divergence)
- `V59_FRESH_THREAD_HANDOFF_20260506.md`: 12 lines changed (predecessor handoff is in the divergence)
- 22 other client/server/state files

**Implication:** the spec you're about to execute exists in TWO versions. The Dropbox-tree version (current, with amendments) is what Kim has been working with. The tooling-repo version is older.

**Pre-execution requirement:** sync the relevant docs from Dropbox → tooling BEFORE starting gap-fix execution. See "Pre-execution prep" section below.

**Long-term resolution:** outside this session's scope. Add to follow-up after gap-fix.

---

## Pre-execution prep (Kim does these BEFORE pasting cold-start prompt)

### Step 1 — Sync relevant docs Dropbox → tooling

The gap-fix session reads specs from disk. The current versions are in Dropbox tree. Copy them to tooling so the session sees up-to-date versions:

```bash
TOOLING=~/Projects/mindfulnest-tooling
DROPBOX="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"

cp "$DROPBOX/Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md"                 "$TOOLING/Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md"
cp "$DROPBOX/Production/docs/V59_GAP_FIX_HANDOFF_20260508.md"             "$TOOLING/Production/docs/V59_GAP_FIX_HANDOFF_20260508.md"
cp "$DROPBOX/Production/docs/V59_STORYBOARD_SIDEFIX_HANDOFF_20260507.md"  "$TOOLING/Production/docs/V59_STORYBOARD_SIDEFIX_HANDOFF_20260507.md"
cp "$DROPBOX/Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md" "$TOOLING/Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md"

cd "$TOOLING"
git checkout -b feature/v59-gap-fix-2026-05-08
git add Production/docs/
git commit -m "sync gap-fix docs from Dropbox tree (pre-execution)"
git status
```

Then verify `pwd` shows tooling, branch shows `feature/v59-gap-fix-2026-05-08`, `git status` shows clean working tree.

### Step 2 — Decide whether to also sync the OTHER 24 files (code + state)

The 28-file divergence includes:
- 4 docs (synced in Step 1 above)
- 1 state file (`production_state.json`)
- 1 storyboard HTML (already deployed)
- 22 code files (production_server.py + 21 client/state files)

**Recommendation: do NOT sync the 22 code files in this session.** Reasons:
1. Code files include uncommitted in-progress work (BG-37 audit-trail, BG-22+C-9 refactor) that needs review, not blind merge
2. `state/scope.ts` will be modified by Option B post-gap-fix — better to do that as part of Option B
3. `production_server.py` is +3983/-1889 lines — needs careful review

**Treat the 22-file code reconciliation as a SEPARATE session** between gap-fix and Option B. Plan for ~2-3 hrs.

### Step 3 — Resolve the 4 open architectural questions

The original handoff flagged these as gating gap-fix execution. My recommendations (your call):

| Q | Question | My recommendation | Status |
|---|---|---|---|
| 1 | Patch-vs-rebuild for tooling CI/CD | **PATCH** — gap-fix is additive (7 phases), no need to tear down. Cursor consult was requested but never obtained; if you still want it, do as 5-min sanity check, not blocker. | Needs Kim lock or Cursor consult |
| 2 | AI review tool — CodeRabbit ($24/mo) vs Claude API custom vs both | **Claude API custom** — $0 marginal cost, you have the key, easier to tune for MindfulNest patterns. Add CodeRabbit later if needed. | Needs Kim lock |
| 3 | Branch protection on main — GitHub Pro $4/mo | **YES, take it** — without it, gap-fix's Phase 7.5 PR mechanics are unenforceable. $4/mo is trivial. | Needs Kim lock |
| 4 | CI deploy — self-hosted runner vs manual + CI verify-after | **Manual + CI verify-after** — simpler infrastructure, no maintenance overhead, fine for solo dev pre-launch. | Needs Kim lock |

If you lock all four with my recommendations, the gap-fix session has zero pending decisions and can run end-to-end.

### Step 4 — Confirm server state

The storyboard server should still be running from the side-fix session (PID 91533 unless killed). Verify:
```bash
lsof -ti:5111
```

If empty, restart:
```bash
cd "$DROPBOX"
python3 Production/tools/production_server.py --event-dir Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1 > /tmp/storyboard_server.log 2>&1 &
```

---

## Reading order in fresh session

1. `CLAUDE.md` — Rules 19, 24, 26, 27, 28, 29, 33, 35, 36
2. **This file** (`V59_GAP_FIX_HANDOFF_20260508.md`) — full read
3. `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` — the 8-phase spec (A-H), full read
4. `Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md` — what just happened with the storyboard side-fix, what state things are in
5. `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` — §0, §16 (Reference Index) for context only

---

## Current bug state (pre-gap-fix)

### Resolved
- **Bug 1** — BG ref drop returns 400. Server-side validation fix landed (PR #7 → 5733b21 on `claude/post-redeploy-bug-triage`). Browser smoke confirmed toast fires (Kim 2026-05-08). NOT yet on main — pending whenever `claude/post-redeploy-bug-triage` merges.

### Deferred (Tier C, post-gap-fix)
- **Bug 2** — Add Beat fires server-side but UI doesn't refresh. Root cause: `bg_add_beat` writes to scope-derived segment, `bg_session_state` reads from `active_context` segment. Two stores diverge.
- **Bug 4** — BG ref drop UI doesn't display dropped image even after server success. Same architectural class as Bug 2.
- **Option B locked**: `bg_session_state` will derive segment from `scope_event_id`, ignoring `active_context`. BG dropdown becomes secondary filter. Single change resolves Bug 2 + Bug 4.

### Regression deferred (post-Option B)
- **Manual-drop-on-options regression**: in old storyboard, library images could be drag-dropped into the 3 option boxes (option 1/2/3) as alternatives to AI-generated stills. v59 doesn't preserve this handler. Required for image reuse across beats.

### Untested
- Other 6 tabs: Cropper, Storyboard, Phase B, Phase A, Stitcher, Library. Phase A skipped six-layer verification across the entire UI; expect more bugs of similar architectural class.

---

## Decision sequencing locked

1. **THIS SESSION (terminal CLI, today):** Execute V59_CICD_GAP_FIX_SPEC_v1.md per the spec. ~8-12 hours.
2. **IMMEDIATELY AFTER #1 (post-gap-fix, pre-divergence):** Execute LD-505 boundary tightening migration — eliminate the Dropbox-resident `.git/`; make tooling repo the sole canonical git tree. Spec at `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (45 KB, authored 2026-05-07, Cursor cross-review pending before lock). → **resolves `prod_blockers` id=55** (Item 3: two-git-tree structural problem).
3. **AFTER #2:** Cherry-pick the 22 remaining divergence files into tooling (now operating on unified tree). ~2-3 hours. → **resolves `prod_blockers` id=54** (Item 2: 22-file divergence) and **id=57** (Item 10: 27 pre-existing modifications — likely overlap with id=54; verify during execution).
4. **AFTER #3:** Option B fix session. `bg_session_state` derives segment from `scope_event_id`. ~2-4 hours including six-layer verification. → **closes `prod_locked_decisions` id=545** (`SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1`) by superseding the shortcut + resolving Bug 2 + Bug 4 architectural root cause.
5. **AFTER #4:** Manual-drop-on-options regression port. ~1-2 hours. → **resolves `prod_blockers` id=59** (Item 5).
6. **AFTER #5:** Smoke-test other 6 tabs comprehensively. ~2-3 hours. → **resolves `prod_blockers` id=56** (Item 4: 6 tabs untested).

**Sequencing change 2026-05-07 (Kim directive):** LD-505 boundary tightening
migration was promoted from "after 6-tab smoke" to "immediately after gap-fix
lands." Rationale: path-mismatch failures in sessions touching both tooling
repo and Dropbox tree have repeatedly caused agent halts and rework. LD-505
eliminates the dual-tree state; doing it earlier makes subsequent sessions
(22-file divergence, Option B, etc.) operate on a unified tree.

---

## Tracking artifacts registered 2026-05-07 (silent deferrals audit Items 2-14)

Per Kim 2026-05-07 directive (`prod_locked_decisions` id=551 `VERBAL_DEFERRAL_TRACKING_REQUIRED_V1`, severity=HARD): every verbal deferral from prior sessions MUST have a Directus tracking artifact. The full audit lives at `Production/docs/SILENT_DEFERRALS_AUDIT_20260507.md`. Registered 2026-05-07 by Desktop prep session, all read-back-verified per Rule 35:

**`prod_blockers` rows (7) — actionable defects, severity-graded:**

| Audit # | Blocker id | Severity | Resolves when... |
|---|---|---|---|
| 2 | 54 | high | Future session #2 (22-file divergence cherry-pick) |
| 3 | 55 | high | Future session #6 (two-git-tree decision; Tier C) |
| 4 | 56 | high | Future session #5 (6-tab smoke pass; pre-TestFlight) |
| 5 | 59 | medium | Future session #4 (manual-drop regression port) |
| 6 | 60 | medium | Beat_22 corruption investigation (no scheduled session yet — file with prep for Option B) |
| 10 | 57 | high | Future session #2 OR dedicated investigation (27 pre-existing mods provenance) |
| 13 | 58 | high | Audit pass mapping 66 lessons → LDs/skills/memory (no scheduled session — informational track) |

**`prod_locked_decisions` LDs (6) — design/awareness:**

| Audit # | LD id | Decision key | Severity | Closure |
|---|---|---|---|---|
| 7 | 546 | `DEFERRED_SCHEMA_DOC_INCONSISTENCY_V1` | SOFT | Inline edit when schema reference doc next opens |
| 8 | 547 | `DEFERRED_BROWSER_SMOKE_MEMORY_CROSSLINK_V1` | SOFT | One-line append to feedback_browser_smoke_required.md |
| 9 | 548 | `DEFERRED_INVENTORY_BRANCH_RECONCILIATION_V1` | SOFT | Decision in architectural-fix or gap-fix Phase 0 |
| 11 | 549 | `DEFERRED_DESKTOP_WORKTREE_CLEANUP_V1` | SOFT | When Desktop session ends |
| 12 | 550 | `DEFERRED_PENDING_WRITES_BAK_CLEANUP_V1` | SOFT | ~30 days hence (or leave; gitignored, harmless) |
| 14 | 551 | `VERBAL_DEFERRAL_TRACKING_REQUIRED_V1` | **HARD** | Ongoing — operationalized via dashboard-gate skill + weekly_preflight_audit |

**`prod_locked_decisions` LD 545 (`SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1`)** — pre-existing from side-fix; will be superseded when Option B (sequence #3) lands. Status `active` until then.

**Audit Item 1 (.gitignore for runtime state) — already RESOLVED inline 2026-05-07** before BLOCK 2 paste. Tooling commit `0abfadf`, Dropbox commit on `claude/storyboard-bug-1-fix-20260507`. No tracking row needed (resolved before registration phase).

**Instruction to gap-fix terminal Claude:** when each future session lands its scoped work, PATCH the relevant `prod_blockers` row with `is_resolved=true, resolved_at=<ISO>`. For LDs being closed, PATCH with `status='superseded', superseded_by_id=<new_LD_id>` (or just leave SOFT informational LDs at status='active' if they decay naturally). Do NOT delete blocker/LD rows — supersession is the audit-preserving pattern.

---

## URL correction (CRITICAL — gap-fix Phase A depends on this)

The original handoff and the current gap-fix spec specified `curl http://localhost:5111/storyboard_v59_prod.html` for served-HTML probes. **This is wrong.** The storyboard SPA serves at root `/`, not at the file-named path. The full-filename path 404s by design.

**Correct probe:** `curl -s http://localhost:5111/`

The gap-fix session MUST update Phase A "Deploy verification gates" to use this corrected URL. Otherwise the mechanical assertions it builds will be checking a permanently-404 endpoint.

---

## Cold-start prompt for paste

After completing pre-execution prep Steps 1-4 above, paste everything between `===BEGIN===` and `===END===` into a fresh terminal CLI session. **Must be terminal CLI per Rule 19 Hardened Session Protocol** — gap-fix touches `MindfulNest/.github/workflows/`, `firestore.rules`, `Production/tools/storyboard-v2/.github/workflows/` — all governed-file scope.

```
===BEGIN===
FIRST ACTION — switch to tooling repo (canonical for gap-fix per LD-505):
cd ~/Projects/mindfulnest-tooling
pwd  # confirm
git status  # confirm clean working tree on feature/v59-gap-fix-2026-05-08
git branch --show-current  # confirm feature/v59-gap-fix-2026-05-08

If not on feature/v59-gap-fix-2026-05-08, STOP — Kim's pre-execution prep
Step 1 was incomplete. Surface to morning report; do not proceed.

SECOND ACTION — verify storyboard server is running (left over from side-fix
session). Server runs against the DROPBOX tree, not tooling, so this is
just a "is it alive" check:
lsof -ti:5111  # should return a PID
If empty, restart per the handoff's Pre-execution prep Step 4.

THIRD ACTION — load required skills:
- execute (autonomous preamble — this is overnight unsupervised)
- zero-error-qa (DS-13..DS-19, Phase 0 Step 1.5/1.6, Phase 7.5)
- dashboard-gate
- no-shortcuts
- tech-spec (in case Tier C escalation is needed mid-execution)

OPERATING MODE — OVERNIGHT AUTONOMOUS:
You run unsupervised. Apply autonomous mode per execute skill.
Do NOT halt-and-wait. Convert every "HALT — surface to Kim" to
"PAUSE this line of work + document in morning report + continue
with safe work."

Two TERMINAL conditions only (write report, stop):
1. Catastrophic infrastructure failure (Directus unreachable >30 min,
   GitHub unreachable, repo cannot clone, build cannot launch)
2. Loss of disk integrity (writes fail, permissions broken)

Everything else is documented + work continues.

PHASE 0 EXPECTATIONS:
- Expected classification: Tier C (architectural CI/CD changes,
  governed-file scope, multiple workflows + scripts modified)
- Spawn 4+4 advocate+counter-agents per Rule 19 / execute skill
- State classification aloud for audit trail per LD-232 autonomous pattern
- Proceed without waiting

OPEN ARCHITECTURAL QUESTIONS — RESOLVED PER KIM 2026-05-08:
1. Patch-vs-rebuild: PATCH the existing tooling repo CI/CD
2. AI review tool: Claude API custom (GitHub Action calling Claude API)
3. Branch protection on main: YES (Kim will activate GitHub Pro)
4. CI deploy: manual local deploy + CI verify-after

If any of these turn out to need adjustment mid-execution, document
in morning report and continue with safe work that doesn't depend
on the contested choice.

CRITICAL CORRECTION TO V59_CICD_GAP_FIX_SPEC_v1.md PHASE A:
The spec's deploy verification probe must use:
  curl -s http://localhost:5111/
NOT:
  curl -s http://localhost:5111/storyboard_v59_prod.html
The storyboard SPA serves at root /, not at file-named path. The
full-filename path returns {"error":"not found"} by design.

When implementing Phase A "Deploy verification gates," patch the
deploy_storyboard_v59.sh script to assert against / not the
filename. Update spec inline as you go (Rule 27 — fix obsolete
recipe).

EXECUTE V59_CICD_GAP_FIX_SPEC_v1.md PHASES A-H:

Per the spec, in order. The spec has 8 phases (A-H):
- Phase A: Deploy verification gates (sha256, mtime, curl)
- Phase B: Branch protection on main
- Phase C: AI review automation (Claude API custom — see Q2 above)
- Phase D: RN-side workflow activation
- Phase E: 6 deferred Playwright specs
- Phase F: Browser smoke as HARD prereq for COMPLETE
- Phase G: Pre-commit hook blocking direct Dropbox edits
- Phase H: Security scanning (CodeQL + Dependabot)

Each phase is its own commit + tag in the feature branch:
  git commit -m "<phase>: <one-line>"
  git tag gapfix-phase-<letter>-complete

Apply zero-error-qa Phase 0-7.5 to each phase as a sub-task.

KEY RULES TO APPLY:
- Rule 19: no shortcuts, no deferrals, no "we'll add it later"
  patterns. Every gap-fix phase must leave NO error path open.
- Rule 24: tag every claim [CONFIRMED]/[INFERRED]/[GUESSED]
- Rule 27: when a phase's fix makes an obsolete workaround redundant
  (e.g., manual deploy reminder docs once mechanical gates exist),
  DELETE the obsolete workaround
- Rule 28: if a fix that should resolve a symptom doesn't, treat
  as evidence of 2+ more concurrent bugs
- Rule 29: server staleness check after every .py edit
- Rule 33: every "ready to test" message must include 4-line
  verification (server PID + lstart, file mtime, served HTML grep,
  curl probe) — substitute curl-only probe overnight since no
  human eyes
- Rule 35: schema verification before any Directus write; use
  try_post_or_queue with read-back; closure_date is NOT a valid
  field on prod_locked_decisions (lesson from 2026-05-08)
- Rule 36: when adding new patches, declare INVARIANTS: comment
  block + register healthcheck assertions

REGISTER INCREMENTAL LDs as gap-fix phases land (Rule 18/20):
- LD per phase: DEPLOY_VERIFICATION_GATE_V1, BRANCH_PROTECTION_V1,
  AI_REVIEW_AUTOMATION_V1, etc.
- Each LD: severity HARD, scope_domain production, status active,
  date_locked 2026-05-08, source_document
  V59_CICD_GAP_FIX_SPEC_v1.md, decision_text describing what the
  phase implemented + how it mechanically prevents the failure
  class, notes referencing relevant test evidence

PR + MERGE STRATEGY:
- This entire gap-fix session works on feature/v59-gap-fix-2026-05-08
- Per phase: commit + tag (no PR per phase)
- After all 8 phases complete: open ONE PR for the whole gap-fix
- gh pr create --title "V59 CI/CD gap-fix: Phases A-H mechanical
  infrastructure" --body "<from spec §15 + Phase 7.5 evidence
  table per phase>"
- Self-review the diff (gh pr view --web is unavailable overnight;
  use git diff main...HEAD --stat + git log --stat)
- Squash merge to main after self-review:
  gh pr merge --squash
  This collapses 8 phase commits into 1 main commit. Phase tags
  preserve granular history.

POST-MERGE VERIFICATION:
- Confirm main HEAD = expected SHA
- Confirm CI on main is green
- Run final deploy_storyboard_v59.sh to verify the new mechanical
  assertions work end-to-end
- Update prod_activity_log with action gap_fix_v1_merged_<sha>
- Close SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 LD by PATCHing
  status='superseded' (the closure mechanism Kim referenced is now
  satisfied — gap-fix landed, mechanical infrastructure live)

MORNING REPORT (mandatory — last action before terminating):
Write to:
Production/docs/V59_GAP_FIX_MORNING_REPORT_<TS>.md (UTC timestamp)

Sections (in this exact order):
1. Executive summary (3 sentences)
2. Phases completed (per-phase: scope, commits, evidence, LD registered)
3. Phases NOT completed (with reason — Tier C escalation, infra
   blocker, etc.)
4. PR + merge state (PR #, squash-merge SHA, post-merge CI status)
5. Manual discipline compliance (per-phase Phase 7.5 evidence)
6. Self-violations (Rule 19 patterns, scope shrinkage, etc.)
7. Things that felt off but aren't clearly bugs
8. Concerning signals (self-audit on confidence calibration)
9. Recommended next session: cherry-pick the 22 remaining
   divergence files into tooling (per V59_GAP_FIX_HANDOFF_20260508.md
   sequencing #2)

If session compacts or hits API timeout mid-execution: write
whatever-state-was-reached report. Partial progress > no report.

DELIVERABLE TO KIM (one-line summary written to terminal stdout
before exit):
"V59 CI/CD gap-fix complete. See morning report at <path>.
Phases completed: <A-H or partial>. PR <#>: <merged|open>.
SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 closure: <yes|deferred>.
Mechanical infrastructure: <live on main|pending merge>.
Recommended next: cherry-pick 22-file divergence per handoff §2."
===END===
```

---

## Notes for Kim (post-paste)

### What to verify in the morning

1. **PR landed on main with all 8 phases.** Check `gh pr list --state merged` and `git log main --oneline -5`.

2. **CI is green on main.** `gh run list --branch main --limit 5`. Required for gap-fix's own deploy verification gates to function.

3. **Each phase has an LD registered.** Query Directus for `decision_key` containing GAP_FIX or DEPLOY_VERIFICATION or BRANCH_PROTECTION or AI_REVIEW or PRE_COMMIT — should see 7-8 new LDs from this session.

4. **SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 (id=545) status changed to `superseded`.** That's the closure mechanism firing.

5. **Run deploy_storyboard_v59.sh manually post-merge** — confirm the new mechanical assertions (sha256, mtime, served-HTML grep) all fire and pass. If they 404, the URL correction wasn't applied.

### What this session does NOT do

- Does NOT fix Bug 2 or Bug 4 (those need Option B in a separate session)
- Does NOT cherry-pick the 22 remaining divergence code files (separate session #2)
- Does NOT port manual-drop-on-options regression (separate session)
- Does NOT smoke-test other 6 tabs (separate session)
- Does NOT resolve the two-git-tree structural problem (eventual follow-up)

### Calibrated success expectation

Gap-fix is large but tractable. Realistic outcomes:
- ~80% chance all 8 phases complete cleanly
- ~15% chance 6-7 phases complete with 1-2 deferred for architectural review
- ~5% chance significant blocker hit mid-execution (e.g., GitHub Pro not active when Phase B tries to set branch protection)

Don't expect "everything works" tomorrow. Expect "mechanical infrastructure is live, PR merged, follow-ups documented."

### Conservative-read fallback

Per Kim's standing preference (`feedback_decision_coupling_watch.md`): if the session encounters ambiguity, pick the conservative read AND flag the ambiguity in one line — don't halt for non-architectural questions. Halting is reserved for genuine Tier C escalation that wasn't covered in the spec.

---

**End of handoff.**

`[CONFIRMED — handoff authored 2026-05-08 by Desktop session, supersedes V59_FRESH_THREAD_HANDOFF_20260506.md, all factual claims tagged with confidence annotation per Rule 24, current state captured as of 2026-05-08 09:30 PT.]`

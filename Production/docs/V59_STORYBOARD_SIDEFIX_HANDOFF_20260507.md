# V59 Storyboard Side-Fix Handoff — 2026-05-07 (OVERNIGHT EXECUTION)

> **⚠️ POST-EXECUTION CORRECTION (2026-05-07):** Step 6c at line 271 below specifies `curl -s http://localhost:5111/storyboard_v59_prod.html` — this is **WRONG**. `production_server.py` serves the SPA at URL `/`, not at the filename path. Correct recipe: `curl -s http://localhost:5111/ | grep -c "<unique_marker>"` (≥ 1). The file-mtime check (Step 6a) IS correct. See feedback memory `feedback_storyboard_url_serves_at_root.md` for full context. This handoff is preserved as historical record; the gap-fix Phase A spec already uses the correct URL.

**For:** Fresh terminal CLI session, running unsupervised overnight (2026-05-07 → 2026-05-08 morning)
**Predecessor:** Desktop session 2026-05-06 → 2026-05-07
**Scope:** Fix Bug 1 (BG ref drop → 400) + Bug 2 (Add Beat → no render) + smoke-test other UI surfaces, with manual discipline substituting for missing CI/CD infrastructure
**Status when authored:** v59 Phase A executed; deploy gap caused Bugs 1+2 to be invisible at user level; gap-fix scheduled for separate terminal session 2026-05-08 morning
**Decision sequence locked:** This side-fix TONIGHT → gap-fix execution TOMORROW MORNING → Phase B AFTER

---

## Overnight execution mode (READ FIRST — overrides handoff defaults)

This session runs unsupervised overnight. Kim will check the morning report when she wakes up. Apply autonomous mode per `execute` skill — do NOT halt-and-wait for input mid-session.

**Convert every "HALT — surface to Kim" instruction in this handoff to:**
> "PAUSE this line of work + document in morning report + continue with whatever else is safe."

The session NEVER halts overnight except for two terminal conditions:
1. **Catastrophic infrastructure failure** (e.g., Directus completely unreachable for >30 min, repo cannot be cloned, terminal CLI cannot launch the build) — write whatever-state-was-reached morning report and stop.
2. **Loss of disk integrity** (e.g., file writes failing, permissions errors blocking deploy) — same: report and stop.

Anything else (Tier C escalation, additional bugs, registration failure, ambiguous diagnosis) is documented in the morning report and the session continues with safe work.

**Calibrated success expectation (Kim's framing):**
- Bug 1 + 2 fixed: ~85% likely
- All storyboard surfaces working: ~40% likely (Phase A skipped six-layer verify everywhere; smoke will likely surface more bugs)
- Reasonable morning state: incremental progress + a triage list, not "everything works"

The session should treat "found 3-5 additional bugs during smoke, fixed 2 inline, escalated 1-3 for Kim review" as a SUCCESS outcome, not a failure.

---

## Closure date for the SHORTCUT exception (LOCKED)

`SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1` closure_date: **2026-05-08**

Rationale: Kim is executing V59_CICD_GAP_FIX_SPEC_v1.md in a separate terminal CLI session 2026-05-08 morning. The manual discipline window is ~12 hours (overnight + morning gap-fix execution). After gap-fix PR merges 2026-05-08, the SHORTCUT closes structurally — mechanical infrastructure replaces manual discipline.

---

## Pre-paste checklist (Kim — verify before pasting cold-start prompt)

- [x] `Production/docs/V59_STORYBOARD_SIDEFIX_HANDOFF_20260507.md` (this file) — confirmed at write
- [x] `Production/docs/V59_FRESH_THREAD_HANDOFF_20260506.md` — keep on disk for tomorrow's gap-fix session
- [x] `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` — 82,043 bytes, used by tomorrow's session, NOT this one
- [x] `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` — for context only, do NOT re-execute Phase A
- [x] `Production/docs/V59_S5_5_C_PASS2_HANDOFF.md` — Phase A's claimed-shipped behavior
- [x] `Production/scripts/deploy_storyboard_v59.sh` — invoked manually with verification per discipline checklist

---

## What to read FIRST in fresh session (in order)

1. `CLAUDE.md` — Rules 19, 24, 27, 28, 29, 33, 35, 36
2. **This file** — full read
3. `Production/docs/V59_S5_5_C_PASS2_HANDOFF.md` — Phase A's claimed-shipped behavior (cross-check vs actual bugs)
4. `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` — §0 (Operating Mode), Phase A summary, §16 (Reference Index), for context
5. Memory files (auto-loaded): `feedback_six_layer_feature_verification.md`, `feedback_browser_smoke_required.md`, `project_v59_architecture_corrected_model.md`, `feedback_directus_schema_canonical.md`

---

## Current bug status

### Bug 1 — BG ref drop returns 400 Bad Request
- **Symptom:** Drag library image to Char ref or BG ref slot in Beat Generator → HTTP 400
- **Suspected cause:** `scope_event_id` mismatch (BG panel showing Arc 1 Event 2 segment while ProjectSelector is on Event_1) `[INFERRED — verify before fixing]`
- **Files implicated:** `Production/tools/storyboard-v2/src/components/StitcherTab.tsx` and/or BG panel components, `Production/tools/storyboard-v2/src/state/scope.ts`, `Production/tools/production_server.py`

### Bug 2 — Add Beat fires server-side but new beat does NOT render
- **Symptom:** Click "Add Beat" → toast "Beat added" → list does not refresh
- **Server response:** HTTP 200
- **Suspected cause:** Either (a) UI doesn't refetch after POST, or (b) beat written to wrong segment `[INFERRED — verify before fixing]`
- **Files implicated:** Same as Bug 1

### Bug 3 — Deploy gap (structural fix deferred to tomorrow)
- **Symptom:** Phase A declared COMPLETE without running deploy script; browser shows stale UI
- **Mechanical fix used in this session:** manually run `deploy_storyboard_v59.sh` after build, with 3-check verification per manual discipline checklist
- **Structural fix:** deferred to tomorrow's gap-fix session

---

## Cold-start prompt for paste (READY TO USE — overnight execution baked in)

Paste everything between `===BEGIN===` and `===END===` into a fresh **terminal CLI** session.

```
===BEGIN===
FIRST ACTION — switch to project root:
cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"

SECOND ACTION — confirm + start the storyboard server:
Kim closed all terminal sessions before starting this one. There
is NO server running. Before any diagnosis or smoke testing:

1. Verify nothing is on port 5111: `lsof -ti:5111` (should return empty)
2. Launch server in background:
   `python3 Production/tools/production_server.py > /tmp/storyboard_server.log 2>&1 &`
   Capture the PID: `echo $!` — note it for staleness checks later.
3. Wait for server ready (poll up to 30s):
   `until curl -sf http://localhost:5111/ > /dev/null; do sleep 1; done`
4. Confirm server log has no startup errors:
   `tail -20 /tmp/storyboard_server.log` — look for "Running on" or
   equivalent ready signal. If errors, surface to morning report
   under "Concerning signals" and attempt to diagnose before
   proceeding.
5. Server-staleness baseline: capture `ps -p <PID> -o lstart` —
   this is your baseline for Rule 29 checks. Server start time
   MUST be > any production_server.py edit you make later.

If server fails to start (port conflict, missing dependency,
import error): write morning report with the failure, mark all
bugs as "BLOCKED — server unreachable," stop session.

THIRD ACTION — start the build-server for the storyboard-v2 dev:
The storyboard-v2 SPA must be built before deploy. Verify Node
toolchain exists:
- `which npm` (or `bun` if applicable)
- `cd Production/tools/storyboard-v2 && npm install` (only if
  node_modules missing) then `cd -` back to project root.

If toolchain missing: morning report failure, stop session.

NOW PROCEED WITH HANDOFF:

You are continuing the MindfulNest v59 features build, running
unsupervised overnight 2026-05-07 → 2026-05-08 morning. Kim will
check the morning report when she wakes up.

DECISION SEQUENCE LOCKED (do NOT reorder):
1. THIS SESSION (overnight): side-fix Bugs 1 + 2 + smoke-test other
   UI surfaces, with manual discipline substituting for missing
   CI/CD infrastructure.
2. NEXT SESSION (Kim runs tomorrow morning, separate terminal):
   execute V59_CICD_GAP_FIX_SPEC_v1.md.
3. AFTER gap-fix lands: Phase B (S5.5e-pass2), then C/D/E.

OPERATING MODE — OVERNIGHT AUTONOMOUS:

You run unsupervised. Apply autonomous mode per execute skill.
Do NOT halt-and-wait. Convert every "HALT — surface to Kim" in
the handoff to "PAUSE this line of work + document in morning
report + continue with safe work."

Two TERMINAL conditions only (write morning report, stop):
1. Catastrophic infrastructure failure (Directus unreachable >30
   min, repo cannot clone, build cannot launch).
2. Loss of disk integrity (writes fail, permissions broken).

Everything else is documented + work continues.

PHASE 0 EXPECTATIONS:
- Expected classification: Tier B (routine bug fix on existing
  surface) per LD-262.
- Tier C escalation gate: if diagnosis reveals scope router itself
  broken, mutation channel broken, or store sharing across events
  broken — DO NOT fix, DO NOT invoke tech-spec mid-session.
  Document in morning report. Mark bug as "Tier C — needs Kim
  review tomorrow." Proceed to smoke-test other surfaces and any
  safe fixes.
- State classification aloud for audit trail per LD-232 autonomous
  pattern. Proceed without waiting.

LOAD SKILLS at session start:
- execute (autonomous preamble)
- zero-error-qa (DS-13..DS-19, Phase 0 Step 1.5/1.6, Phase 7.5)
- dashboard-gate
- no-shortcuts

REGISTER FIRST (before any code change):
SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 in prod_locked_decisions:
- decision_key: SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1
- decision_name: "Side-fix storyboard Bugs 1+2 before V59 CI/CD
   gap-fix executes; manual discipline substitutes for missing infra"
- severity: HARD
- scope_domain: production
- task_category: tech_stack (or 'all' fallback per Rule 35)
- enforcement_type: code_invariant
- status: active
- date_locked: 2026-05-07
- closure_date: 2026-05-08
- decision_text: "Per Kim 2026-05-07: storyboard Bugs 1+2 fix
   executes BEFORE gap-fix infrastructure. Manual discipline
   checklist substitutes for the mechanical gates the gap-fix would
   install. Rule 19 SHORTCUT, valid until closure_date 2026-05-08
   when gap-fix PR merges. Every storyboard task during this
   window MUST execute the 10-step manual discipline checklist
   with literal evidence in Phase 7 table."
- notes: "Closure mechanism: gap-fix PR merges to main 2026-05-08
   morning. Validation: deploy_storyboard_v59.sh has mechanical
   sha256/mtime/curl assertions per Phase A of
   V59_CICD_GAP_FIX_SPEC_v1.md."

Use try_post_or_queue with read-back per Rule 35. If write returns
silent_write_failure or id=None: retry once, then proceed without
it. Flag the failure prominently in morning report. Do NOT halt.

DIAGNOSIS-FIRST PROTOCOL (do this BEFORE any code change):

Bug 1 diagnosis (~30 min):
1. Run deploy_storyboard_v59.sh manually with 3-check verification
   (manual discipline below). Without fresh deploy, you cannot tell
   if Bug 1 was already fixed in dist/ but undeployed.
2. After deploy + hard-reload: capture actual 400 response body
   when dragging library image to BG ref. Use server logs +
   programmatic curl probe to reproduce the failing request.
   Capture the literal field name + error message.
3. Trace what scope_event_id the client is sending vs what the
   server validator expects:
   - Client: grep `scope_event_id` in StitcherTab.tsx + BG panel
     files. Confirm value computed at drop time.
   - Server: grep `scope_event_id` in production_server.py around
     BG handler. Confirm value validator expects.
4. State the actual mismatch in plain language. Do NOT proceed to
   fix until cause is CONFIRMED, not INFERRED.

Bug 2 diagnosis (~30 min):
1. After deploy + hard-reload: trigger Add Beat, capture 200
   response body. Confirm beat was actually written.
2. Query production_state.json for the most recently written beat.
   Confirm its segment_id matches what the UI is filtering on.
3. If beat IS written to right segment but UI isn't refreshing:
   trace the React component — does it invalidate query / call
   refetch / mutate signal state after POST?
4. State actual cause in plain language. Do NOT proceed to fix
   until cause is CONFIRMED.

If either diagnosis reveals architectural cause (scope router,
mutation channel, store sharing): STOP coding, document in
morning report, mark Tier C, proceed to smoke testing.

EXECUTION (Phase 2-7.5 of side-fix):

After both bugs are CONFIRMED-cause-diagnosed:
1. Apply zero-error-qa Phases 1-7.5.
2. Smallest possible code change addressing actual root cause.
   No bandages, no fallbacks/try-catches that hide errors, no
   "I'll add X later" patterns (Rule 19).
3. Use manual discipline checklist below per fix iteration.

ALSO smoke-test these surfaces (Phase A skipped six-layer everywhere):
- Cropper tab (full interaction sweep)
- Beat Generator (chips, ref slots, all interactive elements)
- Storyboard tab (beat list, drag-drop, audio cues)
- Phase B tab (cue tile picker, text editor, suggest script btn)
- Phase A tab (clip selector, voice settings)
- Stitcher tab (transitions, SFX, trims, preview)
- Library tab (search, drag sources)

For each additional bug found:
- Small (≤30 LOC, root cause clear, no architectural risk):
  fix inline with full manual discipline. Add to Phase 7 table.
- Larger (architectural, ambiguous, multi-file): document in
  morning report. Do NOT attempt fix.

MANDATORY MANUAL DISCIPLINE CHECKLIST (per fix iteration):

1. Edit-target gate: confirm `pwd` shows tooling repo
   (~/Projects/mindfulnest-tooling), NOT Dropbox runtime tree.
2. Branch off main (once at session start):
   `git checkout -b feature/storyboard-bug-1-2-fix-20260507`
3. Edit code from confirmed diagnosis.
4. Build: `npm run build` (or `bun run build`).
5. Deploy: `bash Production/scripts/deploy_storyboard_v59.sh`
6. Verify deploy reached user (3 checks — ALL must pass):
   a. `ls -la Production/tools/storyboard-v2/dist/index.html
      Production/Event_1/storyboard_v59_prod.html` — Event_1
      mtime MUST be > dist/ mtime.
   b. Grep unique marker from your edit:
      `grep -c "<unique_marker>" Production/Event_1/storyboard_v59_prod.html`
      MUST be ≥ 1.
   c. ⚠️ WRONG (see banner at top): `curl -s http://localhost:5111/storyboard_v59_prod.html |
      grep -c "<unique_marker>"` — should be `curl -s http://localhost:5111/ |
      grep -c "<unique_marker>"` MUST be ≥ 1.
   If ANY fails → fix deploy, do NOT proceed to step 7.
7. Server staleness check (Rule 29):
   `lsof -ti:5111` then `ps -p <PID> -o lstart`. Server start
   time MUST be > any .py edit mtime; restart if stale.
8. Browser smoke (overnight: programmatic substitute since no
   human eyes available):
   - Programmatic curl probe of the changed endpoint to confirm
     correct response shape + status code.
   - For UI changes that don't have endpoints: use Playwright or
     puppeteer headless to drive the actual click + capture
     pass/fail. If neither available, document the limitation and
     proceed; flag in morning report that UI behavior was inferred
     from JS bundle inspection.
9. Phase 7 evidence requirement:
   - Phase 7 table MUST include literal mtime output, grep output,
     curl output, server PID start time, and browser smoke result.
   - "Code looks correct" / "deploy ran" without literal output
     is NOT acceptable — flag self-violation in morning report.
10. PR + self-review (Phase 7.5):
    - `git push -u origin feature/storyboard-bug-1-2-fix-20260507`
    - `gh pr create --title "Side-fix Bugs 1+2 + smoke additional
       surfaces" --body "<from Phase 7 table + bug list + evidence>"`
    - Self-review diff in `gh pr view --web` (overnight: at minimum
      run `git diff main...HEAD --stat` + `git diff main...HEAD`
      and inspect for unintended changes; document review in PR body).
    - Squash merge: `gh pr merge --squash`.
    - Post-merge: confirm main HEAD = expected SHA, run final
      deploy + smoke from main.

APPLY THROUGHOUT:
- Rule 24: tag every claim [CONFIRMED against <source>] /
  [INFERRED — verify] / [GUESSED]. Morning report MUST be heavy
  on [CONFIRMED] evidence; [INFERRED] flags signal places Kim
  must verify in the morning.
- Rule 27: if you discover obsolete workarounds adjacent to your
  fix, DELETE them — don't layer fixes on top.
- Rule 28: if a fix that should resolve a symptom doesn't, treat
  as evidence of 2+ more concurrent bugs; diagnose all before
  patching.
- Rule 33: every "ready to test" claim MUST include 4-line
  verification (server PID + start time, file mtime, served HTML
  grep, curl probe) — though there's no Kim to test overnight,
  this self-discipline catches stale-state bugs in your own work.
- Rule 36: when adding new patches, declare INVARIANTS: comment
  block + register healthcheck assertions to window.__patchHealth.

MORNING REPORT (mandatory — last action before terminating session):

Write to:
Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md

Sections (in this exact order):

1. Executive summary (3 sentences max):
   - What was fixed
   - What was documented but NOT fixed
   - Recommended Kim action for the gap-fix session

2. Bugs fixed
   For each: root cause (CONFIRMED, with literal evidence —
   400 response body, code grep, etc.), fix description, Phase 7
   table extract showing mtime/grep/curl/server-lstart/smoke output.

3. Bugs documented but NOT fixed (Tier C / architectural)
   For each: diagnosis, why fix was deferred, recommended approach,
   blast radius (which other features may be affected).

4. Additional bugs found during smoke testing
   For each: severity, action taken (fixed inline / escalated),
   surface where found, reproduction steps.

5. PR + merge state
   PR number, merge SHA, post-merge CI status, files touched
   (so gap-fix session knows what to expect on rebase).

6. Manual discipline compliance
   - SHORTCUT LD registered? (id, status)
   - Every iteration tagged with which discipline checklist
     items ran? Any skipped? Why?
   - Any self-violations (Rule 19 patterns: bandages, fallbacks,
     "later" patterns)? List them.

7. Things that felt off but aren't clearly bugs
   Kim judgment-call territory — places where the codebase looks
   suspicious but didn't manifest as a failure during smoke.

8. Concerning signals (self-audit)
   - Did diagnosis stay [CONFIRMED] or did some fixes ship on
     [INFERRED] assumptions?
   - Was browser smoke programmatic only? What was inferred vs
     proven?
   - Any rationalized skips of the discipline checklist?

9. Recommended first action for gap-fix session
   E.g., "Rebase onto main first; side-fix touched X/Y/Z files."
   E.g., "Tier C bug in Bug 1 unfixed — gap-fix should run AS
   PLANNED then we revisit Bug 1 with mechanical infrastructure
   in place."

If session compacts mid-execution: write whatever-state-was-reached
report. Partial progress > no report.

DELIVERABLE TO KIM (one-line summary written to terminal stdout
before exit):
"Storyboard side-fix overnight complete. See morning report at
V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md. Bug 1: <FIXED|TIER_C>.
Bug 2: <FIXED|TIER_C>. Additional bugs found: <N> (<M> fixed inline,
<K> escalated). PR <#>: <merged|open>. SHORTCUT_*  closure_date 2026-05-08
honored: <yes|with caveats>."
===END===
```

---

## Notes for Kim (post-paste)

### What to check in the morning

1. **Open the morning report first** — `Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md`. The executive summary tells you whether to expect a working storyboard or a triage list.

2. **Spot-check Phase 7 evidence** — for each bug "fixed," confirm the morning report includes literal mtime, grep, curl output. If the evidence column says "code looks correct" or "deploy ran" without literal data, the fix may not have actually landed. Re-test in browser before trusting.

3. **Verify the SHORTCUT closure plan** — confirm gap-fix is truly your next session. If you can't run gap-fix today, EXTEND the SHORTCUT closure_date in Directus by PATCHing the LD row before starting any other work. Ignoring an expired SHORTCUT is a Rule 19 violation per the closure mechanism.

4. **Smoke test 3-5 additional surfaces yourself** — even if the report says "all surfaces tested clean." Phase A's "all clear" claim is what got us here. 5 minutes in browser will catch what programmatic smoke missed.

### Concerning signals to watch for in the morning report

- "Smoke tested all surfaces, no additional issues found" → almost certainly insufficient; ask the next session to recite specific click sequences.
- "Bug 1 cause was scope mismatch" without literal capture of failing 400 response body → diagnosis was inferred, not confirmed.
- Phase 7 evidence column missing literal mtime/grep/curl → fix may not have deployed.
- "Fixed by adding fallback / try-catch / default value" → Rule 19 bandage, not root-cause fix.
- "Diagnosis revealed deeper issue" without specifying the issue → ambiguous escalation; needs you to dig.

### What this session does NOT do

- Does NOT execute V59_CICD_GAP_FIX_SPEC_v1.md (that's tomorrow's separate terminal session)
- Does NOT modify deploy_storyboard_v59.sh (gap-fix's job — adds mechanical assertions in Phase A)
- Does NOT touch MindfulNest/.github/workflows/ (gap-fix Phase D)
- Does NOT add Playwright test specs (gap-fix Phase E)
- Does NOT add pre-commit hooks (gap-fix Phase G)

### After this session merges → start the gap-fix session

Use `V59_FRESH_THREAD_HANDOFF_20260506.md` for the gap-fix session, with these adjustments:
- Storyboard fix is no longer Step 2 in the sequencing — it's done (or partially done with Tier C remaining)
- New sequencing: gap-fix execution → Phase B → Phase C/D/E
- The 4 open architectural questions still gate gap-fix execution; resolve via Cursor consult or direct decision before starting

### Calibrated success expectation

Don't expect "fully working storyboard" tomorrow. Expect:
- ~85% chance Bug 1 + 2 fixed
- ~40% chance all surfaces work without additional issues
- A morning report with a triage list, not a clean bill of health

That framing keeps you from disappointment AND keeps the session from rushing past genuine issues to claim a clean win.

---

**End of handoff.**

`[CONFIRMED — handoff authored 2026-05-07 by outgoing Desktop session, baked-in overnight execution mode + locked closure_date 2026-05-08, all factual claims tagged with confidence annotation per Rule 24.]`

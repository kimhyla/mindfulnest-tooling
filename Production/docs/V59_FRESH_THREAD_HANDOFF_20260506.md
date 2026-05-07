# V59 Fresh-Thread Handoff — 2026-05-06

**For:** Fresh Desktop OR terminal Claude session
**Predecessor session:** Desktop 2026-05-03 → 2026-05-06 (heavy compaction risk; comprehensive context preserved per Kim directive)
**Status when authored:** v59 Phase A executed but DEPLOY GAP unresolved; CI/CD gap-fix spec authored in conversation but NOT yet on disk; storyboard fix BLOCKED on CI/CD gap-fix
**Authored by:** Outgoing Desktop session, 2026-05-06 ~16:00 PT

---

## Pre-paste checklist (Kim — read BEFORE pasting to fresh session)

Before pasting the cold-start prompt below, confirm these files exist and are reachable:

- [ ] `Production/docs/V59_FEATURES_BUILD_SPEC_v1.md` `[CONFIRMED via ls 2026-05-06 — 78 KB, mtime 15:15]`
- [ ] `Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md` `[CONFIRMED via ls — 47 KB, mtime 14:27]`
- [ ] `Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md` `[CONFIRMED via ls — 67 KB, mtime 2026-05-03]`
- [ ] `Production/docs/V59_S5_5_C_PASS2_HANDOFF.md` `[CONFIRMED via ls — 12 KB, mtime 15:34]`
- [ ] `Production/docs/V59_S5_5_E_PASS2_HANDOFF.md` `[CONFIRMED via ls — 15 KB, mtime 16:00]`
- [ ] `Production/scripts/deploy_storyboard_v59.sh` `[CONFIRMED via find — exists at Production/scripts/, NOT Production/tools/]`
- [ ] `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` `[CONFIRMED via ls 2026-05-06 23:36 PT — 82,043 bytes (~1206 lines, 8 phases A-H, 5 new LDs). Authored by parallel agent post-handoff; amended 2026-05-06 to add Phase F mechanical browser-smoke gate and Phase H security scanning. Spec covers CI/CD gap inventory.]`
- [ ] `LESSONS_LEARNED_May06_2026_v59_Features_Build_And_CICD_Discovery.md` `[CONFIRMED via ls 2026-05-06 22:47 PT — 56,705 bytes (~583 lines, 66 lessons across 6 categories). Registered in Directus prod_reference_docs id=202.]`

Both files exist on disk and are ready for fresh session to read. No re-derivation needed.

---

## What to read FIRST in fresh session (in order)

Read these BEFORE running any tool, in this exact order. Each read is targeted (sections noted) — do not full-read 78 KB files.

1. **`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/CLAUDE.md`** — Phase 0 pre-flight banner + Rule 19 (Hardened Session Protocol) + Rule 26 (Opus escalation) + Rule 35 (Directus schema verification). `[CONFIRMED — file is the project CLAUDE.md, system-loaded.]`

2. **This file** (`Production/docs/V59_FRESH_THREAD_HANDOFF_20260506.md`) — full read.

3. **`Production/docs/V59_FEATURES_BUILD_SPEC_v1.md`** — read §0 (Mandatory Operating Mode), §13 / §13c (Kim's locks), §14 (Pre-execution Checklist), §15 (Audit), §16 (Reference Index), Phase A summary. `[CONFIRMED exists]`

4. **`Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md`** — Cursor v6 verdicts + Kim §13/§13c locks. Skim for which features Phase A *was supposed to* deliver, vs the bug list below. `[CONFIRMED exists]`

5. **`Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md`** — Spec covers the gaps that allowed the deploy-skipped failure class (8 phases A-H post-amendment). Read §0 (Mandatory Operating Mode), gap inventory, Phase A (Deploy gates), §15 (Items Missed), §16 (Reference Index). `[CONFIRMED exists, 82,043 bytes]`

6. **`Production/docs/V59_S5_5_C_PASS2_HANDOFF.md`** — what Phase A claimed it shipped (server-side). Cross-check against the bug list below. `[CONFIRMED exists]`

7. **Memory files** — already auto-loaded via MEMORY.md. Pay special attention to `feedback_six_layer_feature_verification.md` (six-layer contract) and `project_skills_updated_with_error_elimination_20260506.md` (tech-spec / zero-error-qa updates).

---

## Current bug status (UNRESOLVED, top of mind)

These are the symptoms Kim sees in the browser. They are NOT independent — Bug 3 explains why Bugs 1 + 2 cannot be debugged from the browser yet.

### Bug 1 — BG ref drop returns 400 Bad Request

- **Symptom:** Dragging a library image to the Char ref or BG ref slot in the Beat Generator returns HTTP 400.
- **Server response:** Validation rejection (specific field name not yet captured — fresh session: capture the response body).
- **Suspected cause:** `scope_event_id` mismatch. BG panel is showing an Arc 1 Event 2 segment while ProjectSelector is set to Event_1. Drop payload may carry one event ID while server expects the other. `[INFERRED — verify via Network tab capture of the failing request body + server logs.]`
- **Files implicated:** `Production/tools/storyboard-v2/src/components/StitcherTab.tsx` and/or BG panel components, `Production/tools/storyboard-v2/src/state/scope.ts`, `Production/tools/production_server.py` (the validating endpoint). All four are in `git status` as modified — exact diffs not captured in this handoff.

### Bug 2 — Add Beat fires server-side but new beat does NOT render

- **Symptom:** Click "Add Beat" → toast says "Beat added" → list does not refresh with the new beat.
- **Server response:** HTTP 200.
- **Suspected cause:** Either (a) UI does not refetch after the POST, or (b) the beat is being written to the wrong segment (different `scope_event_id` than the one the UI is filtering on). `[INFERRED — verify via (a) check whether the React component invalidates its query / refetches after POST, (b) query Directus / state.json for the most recently written beat and check its segment ID.]`
- **Files implicated:** Same as Bug 1 — same scope-mismatch root suspect.

### Bug 3 — Deploy gap (root cause blocking 1 + 2 debug)

- **Symptom:** Phase A terminal session declared COMPLETE without ever running `Production/scripts/deploy_storyboard_v59.sh`. Browser shows stale UI.
- **Evidence:** `[CONFIRMED via ls 2026-05-06 16:00]`
  - `Production/tools/storyboard-v2/dist/index.html` mtime: **2026-05-06 15:53** (post-build)
  - `Production/Event_1/storyboard_v59_prod.html` mtime: **2026-05-06 09:39** (pre-build)
  - The deploy step (copy dist → Event_1) never ran. Browser loads `storyboard_v59_prod.html`, which is 6+ hours stale.
- **Why this happened:** Server-side gates (`py_compile`, `npm run build`, curl probes) all passed. Layer 5 (UI re-render in user's actual browser context) was never verified. Per `feedback_six_layer_feature_verification.md`, six-layer verification is mandatory; Phase A skipped layers 5 and 6.
- **Mechanical fix to unblock testing of Bugs 1 + 2 (immediate):**
  ```bash
  bash "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/deploy_storyboard_v59.sh"
  ```
  Then hard-reload browser. **Do NOT do this until** the fresh session has run Phase 0 pre-flight on the gap-fix spec and confirmed this is the right mechanical move (see "Decision sequencing locked" — the gap-fix spec exists precisely to make this kind of deploy mechanically protected, not driven by Claude memory).
- **Structural fix:** the gap-fix spec (Step 1 below).

`[INFERRED — verify]`: Bugs 1 and 2 may either persist or vanish once the deploy runs and the browser sees the fresh dist. Don't assume; capture evidence from browser smoke after deploy.

---

## Decision sequencing locked

Per Kim's chat direction 2026-05-06 (outgoing session), in this exact order — do NOT reorder without Kim's explicit override:

1. **NEXT — Execute `V59_CICD_GAP_FIX_SPEC_v1.md`** (close the deploy-skipped failure class FIRST). Estimated ~8–12 hrs in atomic terminal session. `[INFERRED — time estimates per Kim's feedback memory `feedback_time_estimates.md` are unreliable; treat as rough only.]`
   - Closes the gap inventory across 8 phases (A-H). Mechanically protects deploy step so future Phase X cannot "complete" without it.
   - **Cursor consult outstanding** on patch-vs-rebuild question for tooling repo CI/CD — see "Open architectural questions" #1 below. Do NOT execute until Cursor verdict obtained OR Kim explicitly waives.

2. **THEN — Storyboard fix** (Bug 1 + Bug 2) using mechanically-protected deploy. Estimated ~2–3 hrs.
   - With the gap-fix in place, the deploy is atomic with the build. Bugs 1 + 2 then get six-layer verification by construction.

3. **THEN — Phase B (S5.5e-pass2)** per existing handoff stub at `Production/docs/V59_S5_5_E_PASS2_HANDOFF.md`. `[CONFIRMED exists, 16 KB, mtime 16:00]`.
   - **WARNING:** Per `feedback_handoff_authoring_timing.md`, this handoff was authored DURING Phase A's execution. It may have 7+ gaps. Fresh session must Phase-0-review the stub before treating it as canonical.

4. **THEN — Phase C, D, E** follow per `V59_FEATURES_BUILD_SPEC_v1.md` (S5.5f, S5.5g, S5.5h-pass2 respectively). `[INFERRED — exact phase boundaries are in the spec §0 / §16 reference index.]`

---

## Skills auto-active (updated 2026-05-06)

Both updates are filesystem-resident; fresh session will load them on next invocation. No action needed by Kim.

- **`tech-spec/SKILL.md`** — now mandates §0 Mandatory Operating Mode + §14 Pre-execution Checklist + §15 Audit + §16 Reference Index in every produced spec. `[CONFIRMED via memory file `project_skills_updated_with_error_elimination_20260506.md`]`

- **`zero-error-qa/SKILL.md`** — gained DS-13 through DS-19:
  - DS-13: Six-Layer Verification Contract
  - DS-14: Eight Risk Classes
  - DS-15: Authoring Discipline
  - DS-16: Don't Rely on Memory
  - DS-17: Tail-End Verifier
  - DS-18: Deviation Logging Pattern
  - DS-19: Standing Escape Hatches
  `[CONFIRMED via memory file]`

- **`execute/SKILL.md`** — Tier C autonomous execution preamble (3+3 advocate/counter-agent debates, per Rule 19 + Rule 26). Fresh terminal session for the gap-fix should invoke this skill at session start. `[CONFIRMED — skill description present in available-skills list at this handoff time.]`

---

## Memory files auto-loaded (from MEMORY.md, 2026-05-06)

These are auto-loaded by the harness on session start. Most-relevant to v59 work, in priority order:

- `feedback_six_layer_feature_verification.md` — UI shell + 200 ≠ done. Six layers required. `[CONFIRMED]`
- `project_skills_updated_with_error_elimination_20260506.md` — tech-spec / zero-error-qa upgrades. `[CONFIRMED]`
- `project_v59_features_planning.md` — sub-session plan (S5.5c/e/f/g). `[CONFIRMED]`
- `project_v3_spec_evolution.md` — v3 spec history + 4 locked decisions. `[CONFIRMED]`
- `project_v59_architecture_corrected_model.md` — tabs in production order. `[CONFIRMED]`
- `feedback_browser_smoke_required.md` — server gates ≠ user-visible correctness. `[CONFIRMED]`
- `feedback_handoff_authoring_timing.md` — don't author handoffs mid-flight. `[CONFIRMED]`
- `feedback_verify_agent_findings.md` — agents misreport file existence + line numbers. `[CONFIRMED]`
- `project_beat_generator_3_options_not_grid.md` — BG = 3 options, not 9 stills. `[CONFIRMED]`
- `project_phase_b_is_cedric_lipsynced.md` — Phase B = Cedric lipsynced video. `[CONFIRMED]`
- `project_stitch_editor_v59_canonical.md` — v59 Stitcher tab is canonical. `[CONFIRMED]`
- `feedback_never_recommend_legacy_tool.md` — never tell Kim to use the old version. `[CONFIRMED]`
- `feedback_directus_schema_canonical.md` — schema enums silently migrated 2026-05-04; verify via /fields. `[CONFIRMED]`
- `feedback_tech_spec_for_wrong_architecture.md` — invoke tech-spec on architecture symptoms. `[CONFIRMED]`
- `project_v1_scope_final_20260422.md` — V1 scope 10 arcs / 59 modules / 6 creatures / 7 stones. `[CONFIRMED]`
- `feedback_no_babysitting.md` + `feedback_no_bedtime_suggestions.md` + `feedback_time_estimates.md` — Kim's pacing preferences. `[CONFIRMED]`

Full memory index at: `/Users/kimberlysmith/.claude/projects/-Users-kimberlysmith-Library-CloudStorage-Dropbox-Claude-Mindfulnest-Project-Files/memory/MEMORY.md`

---

## Open architectural questions (awaiting Kim's decision)

Per Kim 2026-05-06, these gate execution of the gap-fix spec. Fresh session: surface these to Kim early; do NOT silently pick a side.

1. **Patch-vs-rebuild for tooling repo CI/CD.** Cursor consult requested before executing the gap-fix spec. **Cursor verdict NOT YET OBTAINED** as of this handoff. `[CONFIRMED — Kim's directive captured in conversation 2026-05-06.]`

2. **AI review tool.** Three options on the table: (a) CodeRabbit at $24/mo, (b) Claude API custom integration, (c) both. Outgoing session's recommendation in spec: Claude API custom. `[INFERRED — recommendation reflects outgoing session's reasoning; Kim has not locked.]`

3. **Branch protection on `main`.** Requires GitHub Pro at $4/mo per user. Open question whether worth it for solo dev. `[CONFIRMED — pricing accurate per GitHub public pricing page as of session knowledge cutoff; Kim: re-verify if pricing matters.]`

4. **CI-driven deploy via self-hosted runner vs manual local deploy with CI verify-after.** Trade-off: full automation vs simpler infrastructure. `[INFERRED — both approaches close the deploy-gap failure class; pick based on Kim's tolerance for self-hosted runner maintenance.]`

---

## Cold-start prompt for paste

Paste everything between the `===BEGIN===` and `===END===` markers below into a fresh Claude session (Desktop OR terminal CLI). Per Rule 19 Hardened Session Protocol, **prefer terminal CLI** — the gap-fix spec edits CI workflows + scripts that are governed-file scope, and Desktop's PreToolUse hooks silently no-op on those.

```
===BEGIN===
You are continuing the MindfulNest v59 features build. Predecessor
session 2026-05-03 → 2026-05-06 surfaced a deploy-skipped failure
class. CI/CD gap-fix spec is the next priority before resuming
storyboard work.

OPERATING MODE (mandatory):
1. Phase 0 pre-flight per CLAUDE.md Rule 19 + Directus decision 124
   PREFLIGHT_PROTOCOL_STEP_0. Classify task: this is ARCHITECTURAL
   (CI/CD changes, governed-file scope) — spawn 4+4 advocate +
   counter-agents per Rule 19 / `execute` skill.
2. Confirm you are in Claude Code terminal CLI (Hardened Session
   Protocol). If you are in Desktop / Cowork, STOP and tell Kim to
   switch to terminal — Desktop's PreToolUse hooks no-op on
   governed-file edits, which means Phase 0 enforcement silently
   fails.
3. Load skills: `execute`, `tech-spec`, `zero-error-qa`,
   `dashboard-gate`, `no-shortcuts`. The first three were updated
   2026-05-06 with the error-elimination doctrine (DS-13..DS-19,
   §0 / §14 / §15 / §16 spec authoring discipline).

READ FIRST (in order, targeted reads — do NOT full-read large files):
1. CLAUDE.md (Rules 19, 26, 27, 28, 29, 33, 35, 36 — full read of
   each rule)
2. Production/docs/V59_FRESH_THREAD_HANDOFF_20260506.md (this file
   — full read)
3. Production/docs/V59_FEATURES_BUILD_SPEC_v1.md (§0, §13, §13c,
   §14, §15, §16, Phase A summary)
4. Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md (Cursor v6
   verdicts + Kim §13/§13c locks)
5. Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md (CONFIRMED on
   disk, 82,043 bytes / ~1206 lines, 8 phases A-H, 5 new LDs).
   Read §0, gap inventory, Phase A, §15, §16.
6. Production/docs/V59_S5_5_C_PASS2_HANDOFF.md (what Phase A
   claimed to ship server-side — cross-check against bug list)

CURRENT STATE (per handoff, 2026-05-06 ~16:00 PT):
- Phase A executed; server-side gates passed (py_compile, npm
  build, curl probes); Layer 5/6 (UI re-render in browser, smoke
  test) NOT verified.
- Deploy gap CONFIRMED: dist/index.html mtime 15:53 vs
  storyboard_v59_prod.html mtime 09:39 — 6+ hr drift. Deploy
  script `Production/scripts/deploy_storyboard_v59.sh` exists but
  was never invoked.
- Bug 1: BG ref drop → HTTP 400 (suspected scope_event_id
  mismatch — Arc 1 Event 2 BG segment vs Event_1 ProjectSelector).
- Bug 2: Add Beat → HTTP 200, toast fires, list doesn't refresh.
  Suspected: missing refetch after POST OR write to wrong segment.
- Bugs 1+2 NOT INDEPENDENTLY DEBUGGABLE until deploy gap closes —
  browser is showing stale UI.

DECISION SEQUENCING (locked, do not reorder without Kim's
explicit override):
1. Execute V59_CICD_GAP_FIX_SPEC_v1.md (Phase A: Deploy gates).
   Tier C, 4+4 advocate+counter agents.
2. Storyboard fix (Bug 1 + Bug 2) with mechanically-protected
   deploy.
3. Phase B (S5.5e-pass2) per existing handoff stub. BUT: stub was
   authored mid-flight; Phase-0-review it before treating as
   canonical.
4. Phase C, D, E follow per build spec.

OPEN ARCHITECTURAL QUESTIONS (surface to Kim BEFORE executing
any judgment-call gate):
1. Patch-vs-rebuild for tooling CI/CD — Cursor consult requested
   2026-05-06 by Kim, NOT YET OBTAINED. Do NOT execute gap-fix
   spec until Cursor weighs in OR Kim explicitly waives.
2. AI review tool: CodeRabbit ($24/mo) vs Claude API custom vs
   both. Outgoing session recommended Claude API custom — Kim
   has NOT locked.
3. Branch protection on main: GitHub Pro $4/mo/user. Open.
4. Self-hosted runner CI deploy vs manual deploy with CI
   verify-after.

BEGIN:
- Per spec §0 (Mandatory Operating Mode) + Phase 0 classification
  + pre-execution checklist (§14).
- Surface the four open architectural questions to Kim FIRST —
  do NOT spawn 4+4 agents on a spec that may need scope changes
  pending Cursor verdict.
- After Kim resolves #1 (Cursor verdict on patch-vs-rebuild):
  execute V59_CICD_GAP_FIX_SPEC_v1.md Phase A (Deploy gates) —
  Tier C, 4+4 advocate+counter agents per Rule 19.
- Surface any additional judgment-call gates to Kim before
  proceeding beyond Phase A.

Apply Rule 24 confidence annotation throughout: tag every
numeric claim, threshold, LD citation, scope assumption, and
math result with [CONFIRMED against <source>] / [INFERRED —
verify] / [GUESSED]. Kim relies on these tags to scan for
unverified claims.

Apply Rule 27 (delete obsolete workarounds): when fixing the
deploy gate, audit any prior "manual deploy reminder" patterns
in the codebase and DELETE them — once the deploy is mechanical,
parallel reminder layers race the real fix.

Apply Rule 33 (verify server + file before "try it now"): every
time you tell Kim to test, confirm (a) correct server on
expected port, (b) server start time AFTER last .py edit, (c)
HTML file Kim opens contains the new feature (grep for unique
marker + check mtime), (d) if multi-server, Kim is testing the
right one.
===END===
```

---

## Notes for Kim (post-paste)

### How to verify everything landed

After the fresh session loads, ask it to recite back:
- The four open architectural questions (it should know all four without re-reading)
- The deploy gap evidence (the two specific mtimes: 15:53 vs 09:39)
- The four-step decision sequence (gap-fix → storyboard fix → Phase B → C/D/E)
- The four enforcement layers for MAIN_APP_CICD_GREENFIELD_DESIGN_V1 (memory file, LD, zero-error-qa Step 1.5, tech-spec via Phase 0)

If it can recite all four cleanly, context loaded correctly. If anything is fuzzy, paste this handoff again.

**Note (2026-05-06 22:47 PT):** Both `V59_CICD_GAP_FIX_SPEC_v1.md` and `LESSONS_LEARNED_May06_2026_v59_Features_Build_And_CICD_Discovery.md` are now CONFIRMED on disk — the original `[INFERRED — NOT FOUND]` flags in this handoff have been corrected. Fresh session does NOT need to re-derive these.

**Side-chat enforcement landed (2026-05-06 ~22:55 PT):** MAIN_APP_CICD_GREENFIELD_DESIGN_V1 lock is enforced via 4 layers:
1. Memory file `project_main_app_cicd_greenfield_lock.md` (auto-loaded via MEMORY.md pointer).
2. Locked decision registered in Directus (try_post_or_queue returned id=None — verify next session via direct query for `decision_key=MAIN_APP_CICD_GREENFIELD_DESIGN_V1`; if missing, re-register).
3. `zero-error-qa/SKILL.md` Phase 0 Step 1.5 — Architectural Decision Triggers, Trigger 1 covers main app CI/CD work.
4. tech-spec skill check via Phase 0 (since Phase 0 governs all spec work).

**Trigger:** any task touching `MindfulNest/.github/workflows/`, kimhyla/mindfulnest-ios repo CI/CD, App Store / TestFlight / EAS Build / Expo build / iOS build / Android build / mobile CI / mobile deploy specs, OR proposes copying tooling-repo workflows as templates → fresh session MUST surface decision_text verbatim, halt, await Kim confirmation. tech-spec research agents must be told NOT to use tooling-repo workflows as templates.

### Browser smoke note (when ready)

Once the fresh session executes the deploy gap-fix and tells you to test:
- Hard-reload the storyboard tab (Cmd+Shift+R) — soft reload may serve cached JS bundle.
- Confirm `Production/Event_1/storyboard_v59_prod.html` mtime is now AFTER `dist/index.html` (deploy step writes it).
- Then re-test Bug 1 (drag library image to Char/BG ref) and Bug 2 (Add Beat → list refreshes).
- Capture Network tab → Headers + Response body for any 400 — fresh session needs the server's actual error message to fix scope_event_id mismatch.

### Both spec + lessons-learned files CONFIRMED on disk (post-handoff verification 2026-05-06 22:47 PT)

The two files this handoff originally flagged as possibly missing are now confirmed:
1. `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` — 82,043 bytes (~1206 lines). CI/CD gap-fix spec, 8 phases A-H, 5 new LDs (post-2026-05-06 amendment added Phase F mechanical browser-smoke gate + Phase H security scanning).
2. `LESSONS_LEARNED_May06_2026_v59_Features_Build_And_CICD_Discovery.md` — 56,705 bytes (~583 lines, 66 lessons across 6 categories). Registered in Directus prod_reference_docs id=202.

Both authored by parallel agents during outgoing session's mn-context SAVE flow. Fresh session can read directly — no re-derivation needed.

### Conservative-read fallback (per Kim's standing preference)

If the fresh session encounters ambiguity, per `feedback_decision_coupling_watch.md` and Kim's general "flag in one line — don't halt" preference, it should pick the conservative read AND flag the ambiguity in one line — not stop and ask. Halting is reserved for Phase 0 architectural review and Open Question #1 (Cursor verdict).

---

**End of handoff.**

`[CONFIRMED — handoff authored 2026-05-06 ~16:00 PT, all factual claims tagged with confidence annotation per Rule 24.]`

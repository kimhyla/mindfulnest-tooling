# Storyboard v59 — Comprehensive Retroactive Coverage PLAN v1

**Date:** 2026-05-04
**Classification:** MULTI-SESSION PROGRAM PLAN — not a single executable spec; defines the wave structure for systematic retroactive bug discovery across the v59 client + server
**Predecessor:** Retroactive Coverage Sprint v1 (PR #2, 41 tests, 4 blockers found, 6 surfaces) — this plan extends that approach to the rest of the codebase
**Companion:** `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` (Wave 1 fixes; in flight)

## §0 Honest framing — read first

**Scope posture revised 2026-05-04 after Cursor second-opinion review.** The plan documents 6 waves of available retroactive coverage work. After Sprint A (Wave 1) ships and the structural CI gate is live, **the rest are NOT all-or-nothing mandatory.** Recommended posture (Cursor 2026-05-04):

1. **Sprint A is load-bearing** — it fixes 4 known bugs + installs the mutation channel + CI/e2e enforcement that converts the failure mode from "unknown breakage" to "breakage caught early when touched." This MUST run.
2. **Server-focused wave (Wave 4 / Sprint E) is the next-most-important** — silent server failures (F-SVR-001 class) can surface during normal operation without new code touches; client-side CI doesn't catch them. This SHOULD run soon after Sprint A.
3. **Remaining waves (2a-e, 3, 5, 6) are high-value insurance that should be scheduled by risk/change frequency** — prioritize whichever wave overlaps S5.5f/g touched surfaces; defer pure UI retro waves until capacity exists.

The original "ALL 6 mandatory" framing was an over-correction to anxiety. The structural discipline (CI Playwright + grep gates + e2e standard) is what makes the codebase safer; the additional waves are valuable but not blockers for shipping v59 client.

Kim's direction "do not leave bugs" CAN mean (and this plan delivers via Sprint A + the recommended near-term Sprint E):

What that direction CAN mean (and this plan delivers):

1. **Every wave runs end-to-end** — no skipping the "polish" waves; tests + bugs + fixes through Wave 6
2. **Each wave's findings get fixed before the next wave starts** — no carried-forward debt; the architectural-fix template (Wave 1) is the model: discover → spec → fix → ship → next wave
3. **Mandatory grep gates inherit and extend** — Wave 1's `MUTATION_CHANNEL_INVARIANT_V1` gate is structurally enforced **for the covered patterns/signatures** (the specific grep regexes in architectural-fix spec §5 Phase 3.4 against `src/components/`, `src/state/`, `src/utils/`); later waves add similar gates for other bug classes (silent-failure pattern, scope-bypass, asset-registration-bypass, etc.). **Honest blind spots** (per Cursor R2): the gate covers `fetch(MUTATION_ENDPOINTS.…)`, `fetch(/api/stitch_editor/{preview,bake,job})`, `fetch(/api/video/{set_active,create})` — but it does NOT catch (a) raw `fetch()` to URLs constructed via string templates that don't match the regex, (b) callers outside the three listed directories (e.g., test files, build scripts), (c) alternate HTTP wrappers if any exist (axios, ky, etc. — none currently in use but worth noting). Closing these blind spots requires either expanding the gate's pattern set explicitly OR enforcing a single mutation-call discipline (only `pathappPatch` exists) at TypeScript level. Both are tracked as candidate hardening for Wave 3
4. **Forward feature work pauses or runs in parallel via worktrees** — the discipline established (proper-fix → retroactive → architectural-fix) sequences this cleanly

What that direction CANNOT mean (limits of methodology, regardless of effort):

1. **No methodology finds 100% of bugs in any nontrivial codebase.** Race conditions, timing-dependent behavior, browser-specific quirks, rare-input edges, visual / accessibility regressions, performance regressions — these slip past every testing approach including the most rigorous. We minimize via the techniques in §2 + §5; we don't claim elimination.
2. **"Bug-free" is not a state the codebase can be put into and held in.** As features ship, new bugs land. The discipline is *fast detection + structural prevention*, not *one-time elimination*.
3. **Some bug classes are out of scope for this program** — performance, visual regression, a11y, cross-browser, mobile, security. §7 enumerates these; each is its own program if pursued.

What this plan honestly delivers:

- **High confidence** that prior shipped v59 client + server code, in covered surfaces, behaves as designed under the test conditions exercised
- **Structural enforcement** of every bug-class pattern we surface (via grep gates, e2e gates, CI workflow checks)
- **A trail of activity_log + prod_blockers + LDs** that documents what was checked, what was found, what was fixed
- **Diminishing actual lurking-bug count** in covered code — but never exactly zero; "lurking" means "would surface under conditions we haven't tested"

Reading this plan as "we will catch every bug" misframes it. Reading it as "we are running every honest discovery technique we have, fixing everything we find, and structurally preventing recurrence of every pattern we identify" — that's accurate.

## §1 Goal

Bring retroactive Playwright + unit-test coverage of the v59 client + server to a level where:

- Every public user-facing behavior in every component has at least one e2e test
- Every `MUTATION_ENDPOINTS` consumer has at least one test asserting `pathappPatch` usage + scope-key auto-injection
- Every server endpoint that mutates state has at least one e2e or integration test
- Every "critical path" (defined in §3) has both happy-path and error-path tests
- Tree-wide grep gates enforce the established patterns going forward (mutation channel invariant gate from architectural-fix Phase 3.4 is the prototype)

When all waves complete, bugs that lurk are a) in non-critical paths, b) in race conditions / timing-dependent behavior the test framework can't easily reach, c) in visual / browser-specific surface, OR d) in edge cases below the cost-benefit threshold of the wave that would have covered them.

## §2 Wave structure

Six waves, each a discrete session. Each wave follows the retroactive sprint v1 discipline (per `STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md` §2): tests only, bugs found get logged + quarantined + deferred to fix sessions, no inline fixes.

### Wave 1 (IN FLIGHT) — Architectural fix from sprint v1 findings

Spec: `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md`

Already specced; awaiting Cursor v2 review + terminal execution. Fixes 4 blockers (F-S2-001, F-S2-002, F-SVR-001, F-CI-001) AND adds the mandatory `MUTATION_CHANNEL_INVARIANT_V1` grep gate which provides **structural enforcement for covered patterns/signatures across `src/components/`, `src/state/`, `src/utils/` directories** for the F-S2 class.

**Authoritative gate definition (per Cursor R3):** see `STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` §5 Phase 3.4 for the exact YAML grep step. It greps the three listed directories (excluding `src/api/` where `pathappPatch` legitimately uses `MUTATION_ENDPOINTS` internally) for these regexes and fails CI on any match:
- `fetch\(.*MUTATION_ENDPOINTS\.` (any raw use of the constants)
- `fetch\(.*\/api\/stitch_editor\/(preview|bake|job)` (URL-literal mutation calls; `/jobs` list READ excluded)
- `fetch\(.*\/api\/video\/(set_active|create)` (URL-literal mutation calls)

**Wave 1 provides retroactive coverage (with bounded scope per Cursor R2 honesty):**
- The 5 known mutation sites converted (StitcherTab × 3, VideoSelector × 2)
- Any future raw-fetch-to-mutation violation **matching the above patterns within the three covered directories** caught at next CI run
- One server-side silent-failure site (sidecar TypeError at line 3899) fixed
- Recurring CI dep friction (F-CI-001 → requirements.txt) prevented

**Wave 1 does NOT cover** (requires later wave hardening):
- Raw mutation calls via templated URLs that don't match the exact regexes (e.g., `fetch(\`${BASE}/${path}\`)`)
- Callers outside `src/components/`, `src/state/`, `src/utils/` (e.g., scripts, ad-hoc test code, hypothetical future directories)
- Alternate HTTP libraries (axios, ky) if introduced
- Server-side silent-failure pattern beyond the one fixed site (Wave 4 audits the rest)

### Wave 2 — Client component behavior coverage (split into 2a-2e by area)

Goal: every component's primary user behaviors have at least one Playwright test.

**Wave 2a — Beat Generator + Storyboard tab edges:**
- Beat option construction beyond R3 (which gated falsy `key`)
- Beat regeneration / re-prompting flow
- Beat note editing
- Beat magic invocation flow (S5.5e R-class wasn't comprehensive)
- Beat lifecycle transitions beyond what S1 covered

**Wave 2b — Phase A/B producers (RUN AFTER S5.5f SHIPS):**
- Phase A 3-clip handling edges
- Phase B audio source priority edge cases
- Voice stem upload error paths
- Ambient preset selector validation
- Cue popover all 3 animations × duration edges
- Watercolor drag-drop on edge timestamps (0ms, end-of-clip, beyond duration)

**Wave 2c — Production Map + scope/event management:**
- Module enumeration across all arcs (not just creature_name display from R4)
- Adding new modules (if UI exists)
- Module → event linking
- Event editing
- Milestone CRUD

**Wave 2d — Scope/state management edges:**
- Rapid scope switches (event → milestone → event)
- Scope persistence across browser refresh
- Scope race conditions (mid-mutation event swap)
- Concurrent tab interactions

**Wave 2e — Library / cropper / asset system:**
- Library category filters
- Cropper modal canvas behaviors beyond basic drag-drop
- AssetTile click vs drag discrimination
- Asset registration flow (LD-421 / LD-422)
- Library tier rendering edge cases

Each wave 2x is ~3 hours. Total: 5 sessions = ~15 hours.

### Wave 3 — Mutation channel comprehensive

Goal: every consumer of `MUTATION_ENDPOINTS` has tests asserting:
- pathappPatch is used (architectural-fix grep gate enforces this on commit)
- Body has scope-key auto-injection per `scopeKeyFor()`
- 409 (scope_mismatch) handling fires correctly
- 423 (event_changed_mid_job) handling re-hydrates + retries

Catalog walk: enumerate every key in `MUTATION_ENDPOINTS`, find every component consumer via grep, write tests for each. This is mostly behavioral verification of pathappPatch wiring (which the architectural-fix gate enforces structurally; this wave verifies semantics).

Estimated 1 session (~3 hours).

### Wave 4 — Server-side audit

Goal: server-side hygiene patterns that aren't visible from the client.

- `pathappPatch` envelope acceptance on all mutation handlers (do all `_handle_*` functions accept `scope_event_id` or `event_id` as expected?)
- Silent-failure pattern audit beyond F-SVR-001 (grep `print(f"[*] write failed`, `print(f"[*] error`, etc. — any other "log + continue" sites?)
- Pre-write state snapshot consistency (per LD M1 — every mutation creates snapshot before)
- Concurrency / drain protocol coverage (`@with_pin_and_drain` decorator usage; race conditions during concurrent edits)
- 409/423 server-side response correctness

Estimated 1 session (~4 hours; server-side is harder to test than client).

### Wave 5 — Static analysis pass

Goal: catch bug classes that runtime tests don't see.

- TypeScript strict mode audit (if `strict: true` not already on, what breaks when it is?)
- ESLint rule expansion: dead code, unused exports, unhandled promise rejections, exhaustive switch
- Python: mypy strict mode pass on `production_server.py` + lib (slow first run, valuable catches)
- Optional: dependency audit (npm audit, pip-audit)
- Optional: bundle size regression check (was added in BUNDLE_SIZE_CI_ENFORCEMENT_V1 LD; verify it's wired)

Estimated 1 session (~3 hours).

### Wave 6 — Manual code review (highest-risk areas only)

Goal: catch architectural smells + bug-attractor patterns that automation can't reliably find.

NOT a full-codebase review. Targeted at:
- pathappPatch implementation itself (`client.ts:175+`) — this is load-bearing infrastructure
- `production_server.py` mutation handlers (audit a sample for race conditions, scope handling, drain interaction)
- State management signals (`src/state/scope.ts`, etc.) — signal subscription bugs are subtle
- Asset registration / file write paths (LD-421/422 critical infrastructure)

Estimated 1 session (~4 hours).

### Total program scope

8 sessions × ~3-4 hr each = ~24-32 hours of dedicated retroactive work, spread over weeks. **NOT all-at-once.** Interleaved with forward feature work (S5.5f, S5.5g, app integration).

## §3 "Critical paths" definition

For each wave, "critical paths" are tested with both happy + error paths. Critical = any of:

- User-visible state mutation (changes anything stored in `state.json`)
- Asset writes (anything via `register_asset()`)
- Scope-bound operations (event load, milestone load, video switch)
- External API calls (lipsync, Kling, magic, voice stem upload)
- File system operations (concat, mix, register video / audio outputs)

Non-critical paths (read-only views, derived computations, pure UI primitives) get happy-path tests only — error paths are lower-priority.

## §4 Sequencing strategy

**Don't pause forward work to do all retroactive at once.** Pacing:

- Wave 1: in flight (architectural-fix session)
- Wave 2a: after architectural-fix ships, BEFORE S5.5f resumes (gives clean baseline)
- Wave 2b: after S5.5f ships
- Wave 2c-e + Wave 3: interleaved with S5.5g
- Wave 4: post-S5.5g (server-side audit makes most sense once client is feature-complete)
- Wave 5: any time after Wave 1; static analysis is mostly orthogonal
- Wave 6: post all other waves; manual review of remaining smell

Realistic timeline: weeks-to-months at solo-dev pace.

### §4.1 Interleave guardrail (per Cursor R6)

**No forward feature merges that touch a wave's target surface while that wave's blocking structural fix is red or in-flight.** Concrete rules:

- While Wave 1 (architectural-fix) is unmerged, no forward feature PR may merge if it touches `StitcherTab.tsx`, `VideoSelector.tsx`, or the sidecar write path at `production_server.py:3899`. (S5.5f currently in flight does NOT touch these — safe to continue in parallel via worktree.)
- While any Wave N's structural gate is being added, no forward feature PR touching that wave's target surface may merge until the gate is green on main.
- If a forward feature session must touch a wave's target surface mid-wave, the wave session pauses, the forward session uses TDD with the wave's discovery in mind, and the wave resumes with the forward session's changes incorporated.
- Worktree parallelism (proven by S5.5f vs retroactive-coverage parallel run 2026-05-04) is the right model when surfaces don't overlap.

**No stopping criterion before completion** (per Kim's "do not leave bugs" direction). Every wave runs to its defined surface coverage end-state. A wave producing 0 bugs in a session is signal to verify the test sensitivity (are tests actually exercising the surface, or are they happy-path only?) — NOT to skip the wave's remaining sessions.

## §5 Per-wave session structure (template)

Each wave session:

1. **Phase 0 pre-flight** — preflight row, predecessor gate (prior wave shipped), CI green on main
2. **Phase 1 discovery** — scope the wave (which behaviors / handlers / patterns); audit existing coverage; output gap map
3. **Phase 2 prioritize** — within wave scope, rank by risk
4. **Phase 3 write tests** — TDD pattern; tests describe expected behavior (which may or may not match actual)
5. **Phase 4 log findings** — bugs found get prod_blockers row + test.fixme quarantine; do NOT fix in-session
6. **Phase 5 CI verification** — branch goes green (or only quarantined tests skipped)
7. **Phase 6 closeout** — results doc + wave LD + activity log + master overview update + git push + PR

Same discipline as retroactive sprint v1. Hard rules:

| # | Rule |
|---|---|
| 1 | Tests only — no fixes |
| 2 | Bugs found → log + quarantine, never inline-fix |
| 3 | Fixtures are pinned (`Event_e2e_fixture/` only) |
| 4 | Critical-path tests never quarantined for flake |
| 5 | Each wave is its own branch, its own PR |

## §6 Metrics + when to stop a wave

Per wave:

- **Test count:** baseline target 30-50 new tests per wave
- **Surface coverage:** at start, audit which functional surfaces are uncovered; at end, ≥80% of identified gaps closed
- **Bug yield:** number of prod_blockers logged per wave
- **Quarantine count:** number of test.fixme entries (signal of how much hidden bug-mass surfaced)

Stopping a wave:

- A wave is "done" when EVERY identified surface gap in its scope has at least 1 e2e test AND every test is green or quarantined-with-blocker. NOT when bug count drops.
- If a wave bloats past 5 sessions, split into wave-N-v2/v3 — but ALL splits ship; no abandoning.

Stopping the entire program:

- The program is done when ALL 6 waves have shipped to their completion criteria above.
- "0 bugs in 2 waves" is NOT a stop signal — it's a *trust* signal that prior fixes held + tests are sensitive enough. Continue.
- Forward work pacing: waves run interleaved with feature sessions per §4 sequencing; no wave is dropped to free capacity for forward work.

## §7 Out of scope (forever or until specifically prioritized)

Each out-of-scope category is a SEPARATE PROGRAM. Per Cursor R5: every deferred finding gets logged with explicit program tag + owner + target session/program so deferrals don't become invisible debt.

| Category | Separate program | Owner | Target |
|---|---|---|---|
| **Performance regression testing** | `PERF_REGRESSION_PROGRAM` | TBD (likely Kim post-S5.5g) | After v59 client feature-complete |
| **Visual regression testing** | `VISUAL_REGRESSION_PROGRAM` (Percy / Chromatic / Playwright snapshots) | TBD | Post-v59-client; pairs with brand-voice work |
| **Accessibility audit** | `A11Y_AUDIT_PROGRAM` (axe-core, WCAG) | TBD | Pre-app-store-launch (parent-app surface) |
| **Cross-browser testing** | `CROSS_BROWSER_PROGRAM` (Safari/Firefox/Edge) | TBD | Post-v59-client; Chromium-only baseline first |
| **Mobile / touch testing** | `MOBILE_TOUCH_PROGRAM` | N/A current | If mobile targets emerge |
| **Production database / Directus health** | `DIRECTUS_OPS_PROGRAM` | Kim (ongoing) | Continuous |
| **Penetration testing / security audit** | `SECURITY_AUDIT_PROGRAM` | TBD | Pre-app-store-launch |
| **Localization / i18n** | `I18N_PROGRAM` | N/A current | If non-English targets emerge |
| **Server-side load testing** | `LOAD_TEST_PROGRAM` | TBD | Pre-multi-tenant if applicable |

**Logging rule:** any finding in any wave that's actually one of the above → write `prod_blockers` row with `program_tag=<category>`, `assigned_owner=<owner or 'unassigned'>`, `target_program=<program key>`, `defer_reason="out of scope of comprehensive retroactive coverage plan"`. The blocker stays open until the target program runs. No deferral is silent.

## §8 Cost-benefit honest framing (revised per Cursor R4)

**Cost (revised — original was discovery-only; full program is higher):**

| Cost dimension | Estimate |
|---|---|
| Discovery + test-writing sessions (8 wave sessions) | 24-32 hours |
| Bug-fix follow-up sessions (one per wave's findings; pattern from Wave 1: 4 findings → 1 fix session) | +12-24 hours (assume ~3 hr per fix session × 4-8 sessions across all waves) |
| CI flake stabilization (per proper-fix experience: roughly 10-20% of test work needs flake-fixing) | +4-8 hours |
| Fixture data extension (Event_e2e_fixture/ likely needs additions for Waves 2b-2e and 4) | +2-4 hours |
| Spec amendments + Cursor reviews (per-wave overhead) | +4-8 hours |
| Manual review effort in Wave 6 | already in 24-32h baseline |
| **TOTAL revised:** | **~46-76 hours over weeks/months** |

The original "24-32h" was honest but narrow — it counted discovery sessions only. The revised total includes everything to actually ship the program (find → fix → flake-stabilize → review). Plan honestly: **~50-75 hours of program work**, distributed.

**Benefit:**
- Confidence that prior shipped code, in covered surfaces, isn't sitting on quietly-broken behaviors
- Bugs caught early via tests rather than late via user-visible failure
- Each wave's tests become permanent regression protection (CI runs them forever)
- Patterns surfaced (like the F-S2 class) become structural enforcements via grep gates

**Tradeoff:**
- Time NOT spent on forward features
- Each wave session + fix session is a context-heavy engagement requiring focus

**Per Kim's "do not leave bugs" direction:** all 6 waves are mandatory; no "core 3" optimization. Waves 2b-2e + 3 + 5 + 6 are NOT polish to skip — they are coverage of code paths the v1 sprint did not exercise. Skipping any wave leaves untested surface.

**Sequencing (re-affirmed from §4):** waves run in priority order with forward feature work interleaved via worktree parallelism, NOT serial. Wave 4 (server-side) waits only because S5.5g may add server endpoints that need to be in scope. Wave 6 (manual review) goes last because it benefits from all prior waves' findings.

**Cost trade is real:** ~50-75 hours over weeks/months IS the price of "do not leave bugs" at the comprehensive level the plan defines. Lower cost (e.g., "stop after Wave 4") means more lurking bugs in the un-covered waves' surfaces.

## §9 Dependencies

- Retroactive Coverage Sprint v1 (PR #2 merged 2026-05-04 as `724942d`) — baseline
- Architectural Fix spec (Wave 1, in flight) — establishes patterns + grep gate
- S5.5c+e proper-fix (PR #1 merged) — CI infrastructure + flake governance + fixture pinning
- `Production/Event_e2e_fixture/` (created in proper-fix) — fixture for all retroactive tests
- `zero-error-qa` SKILL.md — methodology for each session

## §10 Per-wave LD pattern

Each completed wave writes:
- `RETROACTIVE_COVERAGE_WAVE_<N>_COMPLETE` LD (severity SOFT — these are infrastructure milestones, not behavioral locks)
- `prod_activity_log` `WAVE_<N>_COMPLETE` row
- Per-bug `prod_blockers` rows (severity HARD/SOFT per finding)
- Master overview row appended

## §11 Notes for the executing sessions

- Read the predecessor wave's results doc before starting
- Prior wave's prod_blockers are FYI; not this wave's job to fix
- Each wave is its own branch + PR for clean review
- Tests use `Production/Event_e2e_fixture/`; if fixture data needs extending, OK to add (note in PR body)
- Session terminal should treat this PLAN as direction, not as the executable spec — write the wave-specific spec at session start (mirroring retroactive v1 pattern)

## §12 Cursor review questions

For Cursor to assess this plan:

1. Is "comprehensive" framed honestly, or does the plan still over-promise?
2. Are the 6 waves the right grain — too many? too few? wrong split?
3. Wave sequencing — is the mandatory order (1 → 2a → 2b → 2c-e → 3 → 4 → 5 → 6) correct, given all-waves-mandatory framing? ("Core 3" optimization framing was removed per Cursor R1; only sequencing remains a question.)
4. Sequencing strategy (interleave with forward work) — defensible, or should retroactive block until done?
5. Per-wave session structure — appropriate inheritance from retroactive v1 + proper-fix patterns?
6. "Critical paths" definition (§3) — too broad? too narrow?
7. Out-of-scope §7 — anything missing that should be defended?
8. Stopping criteria (§6) — defensible, or could "no bugs" itself be a signal that tests are too shallow?
9. Cost estimate (24-32 hours over weeks/months) — reasonable, or low-ball?
10. Are there bug classes this plan systematically misses? (race conditions, timing, browser-specific, visual)
11. The "Wave 1 grep gate is structurally retroactive" claim — does that genuinely close the F-S2 class across the whole tree, or are there blind spots?
12. Should any wave be promoted to mandatory before forward feature work continues? Or is interleaving genuinely the right call?

Append findings as §13 if reviewing.

## §13 Cursor v11 review findings (2026-05-04)

**Verdict:** **REVISE BEFORE SHIP**

The plan is strong and substantially honest, but a few claims/ordering details need tightening so "do not leave bugs" remains credible under execution pressure.

### §12 Q1-Q12 answers

1. **Q1 (honesty of "comprehensive"):** **Mostly yes.** §0 is materially honest and distinguishes deliverable discipline from mythical zero-bug claims.
2. **Q2 (6-wave grain):** **Good grain.** Split is pragmatic for reviewability and fatigue control; wave decomposition is sensible.
3. **Q3 (priority/order):** **Needs correction in checklist wording.** §4 sequencing and mandatory-all-waves framing are good; §12 Q3 still references "core 3" framing that conflicts with the current mandatory-all-waves stance.
4. **Q4 (interleave with forward work):** **Defensible with one caveat.** Interleave is right after Wave 1 ships; before Wave 1, structural mutation-channel gaps should block further feature merges touching the same surfaces.
5. **Q5 (session template):** **Approved.** Inherits proven retroactive-v1 discipline and keeps sessions auditable.
6. **Q6 (critical-path definition):** **Good baseline.** Slightly broad but workable; broadness is acceptable in a multi-wave plan.
7. **Q7 (out-of-scope):** **Mostly good; tighten mitigation note.** Categories are clear, but add "how these are tracked/escalated" so deferrals do not become invisible debt.
8. **Q8 (stopping criteria):** **Defensible.** Good anti-self-deception framing ("0 bugs is trust signal, not stop signal").
9. **Q9 (24-32 hour estimate):** **Likely low for full program reality.** Reasonable for discovery/testing sessions alone, but optimistic once bug-fix follow-up sessions, CI flakes, fixture upkeep, and review churn are included.
10. **Q10 (systematically missed bug classes):** **Partially addressed; should be tighter.** §7 names classes, but add explicit risk statement for race/timing/browser-specific blind spots and expected follow-on programs.
11. **Q11 (Wave 1 grep gate "structurally retroactive"):** **Overstated as written.** Strong improvement, but not full closure of F-S2 class unless enforcement covers all raw mutation-call shapes (not just one grep signature) and all relevant directories.
12. **Q12 (should Wave 1 block forward work):** **Yes, conditionally.** Wave 1 should block merges for touched mutation surfaces until shipped/green. After that, interleaving by worktree is the right model.

### Required edits before ship

- **R1 — Align §12 Q3 with current policy:**  
  Replace "core 3" language with mandatory-all-waves order language matching §0/§4 (e.g., "is the mandatory sequence 1 -> 2a -> 2b -> 2c-e -> 3 -> 4 -> 5 -> 6 correct?").
- **R2 — Tighten Q11 claim language in §2 Wave 1 and §0 bullet 3:**  
  Reword "structurally retroactive across the whole component tree" to "structurally enforced for covered patterns/signatures," and list blind spots (direct URL fetches, non-component callers, alternate HTTP wrappers) unless explicitly gated.
- **R3 — Strengthen enforcement specification reference:**  
  Point to exact mandatory gate definition (grep/lint rule scope + directories + failing patterns) so Wave 1's protection level is auditable, not aspirational.
- **R4 — Adjust cost framing (§8 / §2 total):**  
  Clarify whether 24-32h includes only discovery/testing sessions or includes resulting fix sessions; if full-program, revise estimate upward.
- **R5 — Tighten §7 with explicit follow-on obligation:**  
  Add one line: out-of-scope categories must be logged with program tag + owner + target program/session, not only "defer."
- **R6 — Clarify interleave guardrail in §4:**  
  Add explicit rule: "No forward merges that touch a wave's target surface while that wave's blocking structural fix is red/in flight."

### Final recommendation

With R1-R6, this plan is approvable and well-aligned with Kim's "do not leave bugs" direction while staying honest about methodological limits.

---

**End of Comprehensive Retroactive Coverage Plan v1.**

This is a multi-session program plan, NOT an executable spec. Each wave gets its own session-level spec at execution time, modeled on the retroactive sprint v1 spec template.

---

## §14 R1-R6 fold log (2026-05-04 post-Cursor §13 review)

All 6 required edits from §13 folded into the plan body. Mapping:

| Cursor required edit | Where it landed |
|---|---|
| R1 — Align §12 Q3 wording with mandatory-all-waves sequencing | §12 Q3 rewritten — "core 3" optimization framing removed; question is now about sequence order only |
| R2 — Tone down "structurally retroactive" overstatement; document blind spots | §0 bullet 3 + §2 Wave 1 description rewritten — gate is "structurally enforced for covered patterns/signatures" with explicit blind spots enumerated (templated URLs, callers outside three dirs, alternate HTTP libs) |
| R3 — Reference exact mandatory enforcement scope | §2 Wave 1 now points to architectural-fix spec §5 Phase 3.4 for the authoritative grep YAML; lists exact regex patterns + directory scope |
| R4 — Clarify 24-32h estimate scope | §8 split into discovery + fix + flake-stabilization + fixture + spec-review subtotals; revised total ~46-76 hours for the full program |
| R5 — Out-of-scope items need program tag + owner + target | §7 rewritten as a 9-row table with `program_tag` + `owner` + `target` columns + explicit logging rule for deferrals |
| R6 — Interleave guardrail in §4 | §4.1 (NEW) explicit rules: no forward merges touching a wave's surface while wave's structural fix is red/in-flight; worktree parallelism only when surfaces don't overlap |

Plan now ready for terminal execution start (Wave 1 = architectural-fix spec, already terminal-handoff-ready post its own §15/§16 fold).

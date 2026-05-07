# Storyboard v59 — Deferred Retroactive Coverage Backlog

**Created:** 2026-05-04
**Purpose:** snapshot of retroactive-coverage work that was specced but deferred. Read this if you start hitting bugs in v59 client + want to know "what was the plan to find these proactively?"

## §1 What got deferred and why

After the retroactive coverage sprint v1 (PR #2) found 4 bugs in 6 surfaces with 41 tests, a comprehensive 6-wave plan was drafted to systematically check the rest of the codebase. After Cursor weighed in, the plan was scoped down to **mandatory Sprint A + recommended near-term Sprint E + opportunistic everything else**.

The "everything else" is what's tracked here.

## §1.5 v59 ship status (added 2026-05-04 22:38 UTC post-S5.5g merge)

**v59 storyboard client = FEATURE-COMPLETE.** All 5 weekend PRs merged to `kimhyla/mindfulnest-tooling/main`:

| PR | Squash commit | Title |
|---|---|---|
| #1 | `1d375de` | Proper-fix (5 R-bugs + CI Playwright + mandatory e2e standard) |
| #2 | `724942d` | Retroactive coverage v1 (41 e2e tests / 6 surfaces / 4 blockers found) |
| #3 | `82c3fae` | S5.5f Phase A/B parity |
| #4 | `1b40d1b` | Wave 1 architectural fix (4 blockers fixed + grep gate) |
| #5 | `d11e573` | S5.5g Stitcher SFX/transitions/trims + Production Map fixes (FEATURE-COMPLETE) |

**91+ e2e tests green** in CI on every commit. **24 NEW LDs** (505-528). **/stitch_editor retirement clock** started 2026-05-04 22:38 UTC; deprecate at day 15, delete at day 45.

This backlog captures items NOT done — work that's been deferred per scope discipline. None of it blocks daily v59 use.

---

## §2 Current state of v59 hygiene (snapshot 2026-05-04 post-S5.5g)

What's already locked in:
- ✅ CI Playwright workflow live on every commit (LD-508)
- ✅ Mandatory e2e standard for new functional code (LD-507)
- ✅ Mutation channel grep gate retroactive across `src/components/`, `src/state/`, `src/utils/` (Sprint A delivers this; LD `MUTATION_CHANNEL_INVARIANT_V1`)
- ✅ Fixture pinning — tests use `Production/Event_e2e_fixture/`, never live event data (proper-fix §17)
- ✅ Flake governance — critical-path tests never auto-quarantined (proper-fix §16)
- ✅ Tooling repo with separate working tree + PR audit trail
- ✅ Schema enum migration documented (HARD/SOFT)
- ✅ ~95 e2e tests in CI baseline (13 from proper-fix + 41 from retroactive + Sprint A's ~10 + S5.5f's eventual additions)

What this means: any NEW bug Kim ships gets caught at commit time if it's in a tested code path. Pre-existing bugs in untested surfaces only surface when those surfaces are touched OR when a user (Kim) hits them.

## §3 Deferred sprints — what they cover, when to run

Source spec (full): `Production/docs/STORYBOARD_V59_COMPREHENSIVE_RETROACTIVE_COVERAGE_PLAN_v1.md`

### NEW POST-S5.5g — items added 2026-05-04 22:38 UTC

**Phase E test coverage gap (LL-41 — falls into Sprint E scope):**
S5.5g Phase E exposed that route-level mocking in e2e tests doesn't exercise server-side handlers. G12 + G13 tests passed during Phase E RED before the `_handle_production_map` server fix was committed. The fix DID land in `production_server.py:8537` (Phase E GREEN), but if a future regression breaks the server-side mapping logic, the e2e tests won't catch it. Sprint E is the right place to add server-side integration tests that hit `_handle_production_map` against fixture data and assert correct event_dir resolution per module.

**F14 transient flake watch (per DS-4 critical-path tests never quarantined):**
Single occurrence of F14 (Voice stem button) flake in S5.5g Phase B RED CI logs. Treated as transient (retries:1 caught it; no recurrence in subsequent runs). If it recurs without code change → it's a real bug to diagnose; promote to a fix session. NOT quarantined.

**Module-level SFX cue rendering + delete (S5.5g scope extension):**
S5.5g G6 implements drop-creates-module-cue (writes to `state.module_sfx_cues`). Reading + deleting existing module cues from that array was NOT in scope. To use module-level SFX cues end-to-end, a future session adds: (a) StitcherTab renders existing module cues as markers in the module timeline strip (below slots), (b) clicking a marker opens SfxCuePopover scoped to module-level, (c) Delete in popover removes from `state.module_sfx_cues` via pathappPatch. Estimated ~1-2 hr.

**Visual scrubber for trims (Cursor v8 Q9 deferred UX polish):**
Per-slot trims currently use numeric inputs in seconds. Spec mentioned drag handles on a video scrubber. UX polish work; trims function correctly today via numeric inputs. Estimated ~2 hr.

**LibraryPanel SFX tier filter UI:**
Spec §3.2 mentions a tier filter for the LibraryPanel SFX tab. S5.5g tests use synthetic drops, so the contract is verified. A real "drag from the SFX tier" experience for Kim is a UX polish task. Estimated ~1 hr.

---

### Sprint E — Server-side audit (RECOMMENDED NEAR-TERM per Cursor 2026-05-04)

**Surfaces:**
- pathappPatch envelope acceptance on all server mutation handlers
- Silent-failure pattern audit beyond F-SVR-001 (`grep "[*] write failed"`, `grep "[*] error"` for "log + continue" sites)
- Pre-write state snapshot consistency (per LD M1)
- Concurrency / drain protocol coverage (`@with_pin_and_drain` decorator usage; race conditions during concurrent edits)
- 409/423 server-side response correctness

**Why prioritized:** silent server failures CAN surface during normal operation without new code touches. Client-side CI doesn't catch them. F-SVR-001 was one such site; pattern likely has more instances.

**Estimated cost:** ~4 hours

**Trigger to run:** any of the following:
- After Sprint A ships (recommended baseline)
- Strange data corruption observed (e.g., state.json drifts unexpectedly)
- Background job failures (lipsync, magic, kling) you can't explain
- "Something feels off" with the server — slow, inconsistent, partial writes

### Sprint B — Beat Generator + Storyboard tab + Production Map (combined Wave 2a + 2c)

**Surfaces:**
- Beat option construction beyond R3 (which gated falsy `key`)
- Beat regeneration / re-prompting flow
- Beat note editing
- Beat magic invocation flow
- Beat lifecycle transitions beyond what S1 covered
- Module enumeration across all arcs (not just creature_name display from R4)
- Adding new modules (if UI exists)
- Module → event linking
- Event editing
- Milestone CRUD

**Estimated cost:** ~6 hours

**Trigger to run:** any of the following:
- Bug surfaces in Beat Generator (regen, edit, magic, lifecycle states)
- Storyboard tab refresh issues beyond R1
- Production Map data behaviors look wrong
- ProjectSelector / event creation flows misbehave

### Sprint C — Phase A/B + scope/state edges (combined Wave 2b + 2d)

**Surfaces:**
- Phase A 3-clip handling edges
- Phase B audio source priority edge cases
- Voice stem upload error paths
- Ambient preset selector validation
- Cue popover all 3 animations × duration edges
- Watercolor drag-drop on edge timestamps
- Rapid scope switches (event → milestone → event)
- Scope persistence across browser refresh
- Scope race conditions (mid-mutation event swap)
- Concurrent tab interactions

**Prerequisite:** S5.5f must ship first (testing a moving target = wasted work)

**Estimated cost:** ~6 hours

**Trigger to run:** any of the following:
- Bug surfaces in Phase A/B producer (post-S5.5f)
- WaveSurfer behavior wrong
- Cue popover misfires
- Scope swap edge cases hit (e.g., event→milestone→event sequence corrupts state)
- Voice stem or ambient preset misbehaviors

### Sprint D — Library/cropper/asset + mutation channel comprehensive (combined Wave 2e + Wave 3)

**Surfaces:**
- Library category filters
- Cropper modal canvas behaviors beyond basic drag-drop
- AssetTile click vs drag discrimination
- Asset registration flow (LD-421 / LD-422)
- Library tier rendering edge cases
- Every consumer of `MUTATION_ENDPOINTS` has tests asserting pathappPatch usage + scope-key auto-injection + 409/423 handling

**Pre-loaded backlog from Wave 1 (incidentally found 2026-05-04):**
- prod_blocker #50: ProjectSelector raw-fetch event_load violation
- prod_blocker #51: ProjectSelector raw-fetch event_load violation (second site)
- prod_blocker #52: EventSelector raw-fetch event_load violation
- prod_blocker #53: ProductionMapTab raw-fetch event_load violation

These 4 pre-existing violations were detected by the Wave 1 grep gate but NOT fixed in Wave 1 per scope discipline (Cursor R6 / spec §10). The right fix per Wave 1 closeout note: use the existing `loadEvent` helper in `src/api/client.ts` (event swap intentionally skips the M1 snapshot, which is why pathappPatch is the wrong channel for it). When Sprint D runs, these 4 are first-priority work; the gate's strict-warning step continues to surface them every CI run until resolved.

**Estimated cost:** ~5 hours (now closer to ~6-7 hr with the 4 known fixes pre-loaded)

**Trigger to run:** any of the following:
- The 4 pre-loaded blockers above start blocking real work (currently warning-level only)
- Bug surfaces in library rendering (filters, click vs drag, scroll)
- Cropper modal acts up
- Asset registration fails or duplicates
- Mutation channel issues elsewhere (StitcherTab + VideoSelector covered by Sprint A; this checks the rest)
- The strict-warning step's volume becomes annoying enough to fix-now

### Sprint F — Static analysis + manual review (combined Wave 5 + Wave 6)

**Coverage:**
- TypeScript strict mode audit (if `strict: true` not on, what breaks?)
- ESLint rule expansion: dead code, unused exports, unhandled promise rejections, exhaustive switch
- Python: mypy strict mode pass on `production_server.py` + lib
- Optional: dependency audit (`npm audit`, `pip-audit`)
- Manual review of pathappPatch implementation, mutation handlers, state management signals, asset registration paths

**Estimated cost:** ~5 hours

**Trigger to run:** any of the following:
- "Code feels brittle" — frequent unrelated breakage
- TypeScript or Python warnings have built up
- npm audit reports vulnerabilities
- Want to push the codebase quality bar up before a milestone (e.g., before app store launch, before adding collaborators)

## §4 How to start one of these sprints (template)

When you decide to run a deferred sprint:

1. **Tell me which sprint** (E, B, C, D, or F) — or describe the bug pattern you're seeing and let me pick
2. **I draft the session-level spec** for that sprint, modeled on `STORYBOARD_V59_RETROACTIVE_COVERAGE_SPEC_v1.md` (the v1 sprint template)
3. **Optional Cursor review** of the spec
4. **I produce the terminal handoff paste** for a fresh terminal
5. **You run it in the main tooling tree** at `~/Projects/mindfulnest-tooling/` (worktree only if you want parallelism with another sprint)
6. **Sprint follows the tests-only-no-fixes discipline** — bugs found get logged as `prod_blockers`, fixed in a follow-up session

Total cycle: ~30 min draft + Cursor review + ~3-6 hr execution + closeout PR.

## §5 Cumulative cost if all deferred sprints eventually run

Estimated remaining if you ran ALL deferred sprints:
- Sprint E: ~4 hr (recommended near-term)
- Sprint B: ~6 hr
- Sprint C: ~6 hr (post-S5.5f)
- Sprint D: ~5 hr
- Sprint F: ~5 hr
- Plus per-sprint findings → fix sessions: ~10-15 hr (estimate based on Sprint A's 4 findings → 5-6 hr fix ratio)
- Plus CI flake stabilization, fixture extension, Cursor reviews: ~10 hr distributed

**Total deferred work if all eventually run: ~40-55 hours.**

This is opportunity cost vs forward feature work. Run sprints by **risk × change frequency × bug-surface evidence**, not as a marathon.

## §6 Signals that a deferred sprint should be promoted to "run now"

- Same class of bug surfaces 2+ times in user-facing testing
- Sprint surface gets touched by a forward feature session and tests are needed for safety
- Quarterly hygiene review reveals coverage gaps that could affect release readiness
- Pre-launch QA (e.g., before app store submission) requires demonstrated test coverage of specific surfaces
- A `prod_blockers` row in the sprint's surface area gets HARD severity from a real user incident
- Idle capacity exists between forward feature work

## §7 Pointer documents

- Full plan: `Production/docs/STORYBOARD_V59_COMPREHENSIVE_RETROACTIVE_COVERAGE_PLAN_v1.md`
- Sprint A spec: `Production/docs/STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md`
- Retroactive sprint v1 results: `Production/docs/RETROACTIVE_COVERAGE_RESULTS_V1.md`
- Proper-fix patterns inherited: `Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` §16 (flake governance) + §17 (fixture pinning)
- Master overview: `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §8 Honest framing reminder

"Do not leave bugs" cannot mean zero bugs forever — no testing methodology delivers that. What it CAN mean:
- Sprint A delivers structural enforcement (mutation channel + e2e + CI gate)
- Sprint E (when run) covers the highest-risk silent-failure class
- Subsequent sprints (when run) push coverage deeper
- Bug classes specifically out of scope: performance, visual regression, a11y, cross-browser, mobile, security — each is its own program

Reading this backlog as "we have to do all of these eventually" is wrong framing. Reading it as "here are the next places to look if specific bug patterns surface" is correct framing.

---

**End of Deferred Retroactive Coverage Backlog.**

This is a living document. Update §3 as sprints get promoted to "run now" or as new patterns surface that warrant adding sprints.

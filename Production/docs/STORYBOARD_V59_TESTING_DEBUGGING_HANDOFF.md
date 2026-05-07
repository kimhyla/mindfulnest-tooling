# v59 Storyboard — Testing + Debugging Session Handoff

**Created:** 2026-05-04 (post-S5.5g merge `d11e573`)
**Audience:** Fresh Claude Code terminal session that Kim opens during v59 testing/debugging
**Purpose:** Provide complete context so the session can triage bugs, propose fixes, and ship cleanly under the discipline standards locked over the weekend.

---

## §1 Where we are right now

The v59 storyboard tool is **FEATURE-COMPLETE** as of 2026-05-04 22:38 UTC. All 5 weekend PRs merged on `kimhyla/mindfulnest-tooling/main`:

| PR | Squash | Title |
|---|---|---|
| #1 | `1d375de` | Proper-fix |
| #2 | `724942d` | Retroactive coverage v1 |
| #3 | `82c3fae` | S5.5f Phase A/B parity |
| #4 | `1b40d1b` | Wave 1 architectural fix |
| #5 | `d11e573` | S5.5g Stitcher + Production Map (FEATURE-COMPLETE) |

**91+ e2e tests green in CI on every commit. 24 NEW LDs (505-528). /stitch_editor retirement clock started.**

Kim is now testing the v59 client end-to-end. Bugs may surface. THIS handoff is for the session that triages those bugs.

## §2 How to launch the v59 storyboard

```bash
cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
python3 Production/tools/production_server.py \
  --event-dir Production/Event_1 \
  --storyboard storyboard_v59_prod.html \
  --event-id Event_1
```

Then open `http://localhost:5111/` in Chrome.

For Event_2: replace `Production/Event_1` + `Event_1` with `Production/Event_2` + `Event_2`. Same pattern for any future event.

## §3 Two trees + working tree boundary (LD-505)

Critical orientation:

| Tree | Path | Purpose |
|---|---|---|
| **Dropbox tree** (canonical) | `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` | Authoring, docs, state files, media, governance. Run server FROM HERE for production work. |
| **Tooling repo tree** (CI-bound) | `/Users/kimberlysmith/Projects/mindfulnest-tooling/` | Code that ships through CI; subset boundary. Run tests + push fixes FROM HERE. |

**Where bug fixes land:** tooling repo tree (the CI-bound side). Edits to `src/components/`, `src/api/`, `production_server.py`, `e2e/*.spec.ts` happen there. All 5 weekend PRs went through that repo.

**Where docs live:** Dropbox tree is canonical for `Production/docs/` + the master tech spec at root. The tooling repo's `Production/docs/` snapshot lags behind Dropbox (known minor follow-up).

Per LD-505 sync rule: tooling repo CANONICAL for boundary files (storyboard-v2/, server-related Python, lib/). Dropbox copies of those files become deprecated mirrors. Don't edit the Dropbox copy of code; edit in tooling repo.

## §4 Discipline standards (load this BEFORE making any fix)

The 12 Discipline Standards (DS-1..DS-12) live at `.claude/skills/zero-error-qa/SKILL.md` lines 32-110. Read them before any edit. Most relevant for testing/debugging:

- **DS-2 TDD strict ordering** — when fixing a surfaced bug: write a failing Playwright test FIRST that reproduces the bug → commit + push → CI red → implement fix → commit + push → CI green. Never fix code without a test that captures the regression.
- **DS-5 Mutation channel discipline** — every state mutation goes through `pathappPatch` (`src/api/client.ts:175`). NO raw `fetch()` to `MUTATION_ENDPOINTS` outside `src/api/`. Wave 1 grep gate (LD-519) enforces structurally.
- **DS-7 Server staleness check** — after ANY edit to `production_server.py`, restart the server before testing. Local: `pkill -f "production_server.py.*Event_1"` then re-launch.
- **DS-8 Directus writes via try_post_or_queue + read-back** — Rule 35.
- **DS-9 HARD/SOFT severity for new LDs** — schema migrated 2026-04-28 to 2026-05-04.
- **DS-10 CI workflow APPEND not replace, no globs** — when adding a new test spec, append to the explicit test command list in `.github/workflows/playwright_e2e.yml`.

If any standard cannot be met, halt + surface to Kim. Silent shortcuts are not the correct response.

## §5 Architecture quick reference

**Read first:** `Production/docs/STORYBOARD_V59_ARCHITECTURE_OVERVIEW_v1.md` (full architecture; ~620 lines including post-S5.5g §10 delta).

Quick mental model:

- **Client:** Preact + signals + TypeScript at `Production/tools/storyboard-v2/`. Vite-bundled, ~173 KB minified. Tabs: Beat Generator / Storyboard / Phase A/B / Stitcher / Production Map / Project (scope picker).
- **Server:** Python HTTP at `Production/tools/production_server.py` (~16k lines). Routes via `_handle_*` methods. State: `Production/Event_<N>/production_state.json` (atomic write per LD-368).
- **Mutation channel:** `pathappPatch` at `src/api/client.ts:175` → resolves `MUTATION_ENDPOINTS[endpoint]` → posts directly to real URL with auto-injected scope keys. M1 snapshot fires before every non-snapshot mutation. 409 (scope_mismatch) + 423 (event_changed_mid_job) handling built in.
- **CI:** `.github/workflows/playwright_e2e.yml` runs Playwright on every commit. 91+ tests across 10 spec files.
- **Mandatory grep gate:** Wave 1's `MUTATION_CHANNEL_INVARIANT_V1` (LD-519) — fails CI if raw fetch to mutation endpoints appears outside `src/api/`.

## §6 Known issues to be aware of (don't surface as new bugs)

These are TRACKED + DEFERRED. If Kim's testing surfaces one of these, it's known — don't spawn a session to fix unless she explicitly asks.

| Issue | Source | Status |
|---|---|---|
| `ProjectSelector` × 2 raw `fetch()` to event_load | Wave 1 grep gate finding | Blockers #50-#51, deferred to Sprint D / Wave 3 |
| `EventSelector` raw `fetch()` to event_load | Same | Blocker #52, deferred Sprint D |
| `ProductionMapTab` raw `fetch()` to event_load | Same | Blocker #53, deferred Sprint D |
| Phase E test coverage gap (route-level mocking) | LL-41 | Sprint E will close it |
| F14 (Voice stem) transient flake | Single occurrence S5.5g Phase B RED | Watch list; if recurs → diagnose |
| Module-level SFX cue rendering + delete | S5.5g G6 scope extension | ~1-2 hr follow-up |
| Visual scrubber for trims | Cursor v8 Q9 deferred | UX polish ~2 hr |
| LibraryPanel SFX tier filter UI | Spec §3.2 polish | ~1 hr |
| `/api/phase_b/regen_audio` misnamed (writes voice_stem) | Cursor v8 Q5 | Out of scope (rename would break integrations) |
| Local tooling-repo master overview stale | Dropbox is canonical | Minor; resync when convenient |

Full tracker: `Production/docs/STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md` (read §3 and the "NEW POST-S5.5g" subsection for the full list with triggers).

## §7 What "bug found during testing" looks like operationally

Kim runs through a real production workflow → notices something feels wrong (visual, behavioral, missing, etc.). Process:

### §7.1 Triage decision tree

1. **Is it in the known-issues table (§6)?** → No action needed; remind Kim it's tracked.
2. **Is it COSMETIC** (looks ugly, sluggish but functional)? → File as a low-priority blocker; defer to a UX polish session.
3. **Is it a CRITICAL functional break** (mutation fails, data corruption, scope leak, server error)? → Spawn a fix session. Use TDD per DS-2: write failing Playwright test first.
4. **Is it a STRUCTURAL regression** (e.g., `pathappPatch` not auto-injecting scope keys, mutation channel violation, server fail-loud broken)? → That's serious — the grep gate or a CI test should have caught it. HALT before proposing a fix; investigate why CI didn't catch first.

### §7.2 Bug ticket format (use for any new finding)

Write a `prod_blockers` row via `try_post_or_queue` with read-back:

```python
{
  "blocker_id": "F-<surface>-<seq>",  # e.g., "F-STITCHER-001"
  "title": "<short description>",
  "blocked_action": "<what user can't do>",
  "severity": "HARD" or "SOFT",  # HARD if data corruption / functional break / scope leak; SOFT if cosmetic / polish
  "is_resolved": False,
  "details": {
    "user_repro_steps": "...",
    "expected_behavior": "...",
    "actual_behavior": "...",
    "console_or_server_logs": "...",
    "browser_state": "...",  # which event, target_video, etc.
    "first_observed_commit": "<sha or 'unknown'>",
    "candidate_root_cause": "..."  # if known
  },
  "discovered_by": "kim_browser_smoke_2026-05-04"
}
```

### §7.3 Fix session structure

If Kim says "fix this":

1. **Open fresh terminal at `~/Projects/mindfulnest-tooling/`** (NOT Dropbox tree)
2. **`git checkout main && git pull`** — sync to latest
3. **`git checkout -b claude/fix-<descriptive-name>`** — feature branch
4. **Read** the relevant spec sections + the bug's `prod_blockers` row + this handoff
5. **Phase 0 preflight** per zero-error-qa SKILL.md — write `prod_preflight_reviews` row referencing the blocker as predecessor
6. **Phase 1 RED** — write a Playwright test in `e2e/<existing-spec>.spec.ts` (or new `e2e/fix_<name>.spec.ts`) that reproduces the bug. Commit + push. Confirm CI red on the new test.
7. **Phase 2 GREEN** — implement the fix. Test passes locally. Commit + push. Confirm CI green.
8. **Phase 3 verification** — full suite green; no other tests regressed; grep gate green; manual browser smoke if UI fix.
9. **Phase 4 closeout** — `prod_blockers` PATCH `is_resolved=true, resolved_at=now`; `prod_activity_log` `action=BUG_FIX_<name>_COMPLETE`; if pattern warrants codification, write a NEW LD (HARD if behavior-enforcing).
10. **PR open** — `gh pr create`; squash-merge after CI green.

## §8 Where to find specific things

| Need | Where |
|---|---|
| The full lessons-learned (LL-1..LL-43) | `Production/docs/STORYBOARD_V59_LESSONS_LEARNED_v1.md` |
| Architecture deep-dive (component tree, server, mutation channel, CI) | `Production/docs/STORYBOARD_V59_ARCHITECTURE_OVERVIEW_v1.md` |
| What's deferred (sprints, scope-extension items, polish backlog) | `Production/docs/STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md` |
| Discipline standards (12 DS) | `.claude/skills/zero-error-qa/SKILL.md` lines 32-110 |
| Schema gotchas (Directus field names) | `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` (incl 2026-05-04 enum migration note) |
| Master tech spec (cross-cutting) | `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` (Dropbox root; §14.13 has app foundation pointer) |
| Comprehensive retroactive coverage program plan | `Production/docs/STORYBOARD_V59_COMPREHENSIVE_RETROACTIVE_COVERAGE_PLAN_v1.md` |
| App foundation discipline (when ready to start app work) | `Production/docs/MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` |
| 5 PR squash commits for archaeology | `1d375de` / `724942d` / `82c3fae` / `1b40d1b` / `d11e573` |
| Master overview status table (single source of truth) | `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` |
| All 24 NEW LDs (505-528) full text | Directus `prod_locked_decisions` (query by id range) |

## §9 What this session should NOT do

- Do NOT modify `/stitch_editor` legacy code — it's in retirement clock
- Do NOT modify the 4 sanctioned event_load violations (#50-53) — Sprint D / Wave 3 territory
- Do NOT skip TDD (DS-2) — bug fixes write the regression test FIRST
- Do NOT write feature additions beyond bug-fix scope — surface to Kim
- Do NOT use HIGH/MEDIUM severity on new LDs (use HARD/SOFT per DS-9)
- Do NOT use globs in CI workflow extensions (per DS-10)
- Do NOT add `summary` field to `prod_activity_log` writes (silent drop; use `details.summary` JSON)
- Do NOT add `classification` / `advocates_count` / etc. to `prod_preflight_reviews` (silent drops; use `task_type`)
- Do NOT modify Dropbox folder's git state (still remoteless; tooling repo is the GitHub presence)

## §10 Forward direction (when Kim says "I'm done testing")

If Kim's testing surfaces zero blocking bugs:

1. **Sprint E (server audit) — recommended near-term.** Closes LL-41 server-side coverage gap + audits silent-failure pattern beyond F-SVR-001. ~4 hr session. Spec to be authored at session start mirroring retroactive sprint v1 template.
2. **Sprint D / Wave 3** — closes blockers #50-53 + comprehensive mutation channel coverage. ~5-7 hr.
3. **Sprints B / C / F** — opportunistic per backlog triggers. Run when specific bug patterns surface.
4. **MindfulNest app foundation work per LD-518** — when Kim is ready. The 5 load-bearing pieces (CI from commit 1, test-with-feature, structural enforcement, schema contracts, observability) are codified + ready.
5. **/stitch_editor retirement audit** — daily metric write per §19.11.1; deprecate at day 15, delete at day 45.

## §11 Operational reminders

- **Per Rule 29:** server staleness check after `production_server.py` edits before any test
- **Per Rule 35:** every Directus write via `try_post_or_queue` + read-back
- **Per Rule 36:** patch-invariant persistence — every PATCH read-back-verified
- **Per LD-509:** browser smoke = "feels right?" subjective UX (NOT "does anything work" — that's automated via 91+ tests)
- **Local Playwright env vars:** if running e2e locally, need `DIRECTUS_EMAIL` + `DIRECTUS_PASSWORD` (Doppler exports as `DIRECTUS_ADMIN_*`):
  ```
  eval "$(doppler secrets download --project mindfulnest --config dev --no-file --format env)"
  export DIRECTUS_EMAIL="$DIRECTUS_ADMIN_EMAIL"
  export DIRECTUS_PASSWORD="$DIRECTUS_ADMIN_PASSWORD"
  export PRODUCTION_SERVER_SINGLE_MACHINE=1
  ```

---

**End of Testing/Debugging Session Handoff.**

This handoff is the entry point for any session Kim opens during v59 testing. Read this first; the linked artifacts (lessons learned, architecture overview, deferred backlog, schema reference, master spec) carry the full context. The discipline standards in zero-error-qa SKILL.md govern how any fix gets shipped.

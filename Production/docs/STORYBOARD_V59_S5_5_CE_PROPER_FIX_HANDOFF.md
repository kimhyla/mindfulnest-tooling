# V59 S5.5c+e Proper Fix — Fresh-Terminal Handoff

**For:** Fresh Claude Code terminal session
**Predecessor:** S5.5c+e shipped 2026-05-03 (commits `bc12a4d` + `9efaabd`; 31/31 server gates green; browser smoke surfaced 5 integration bugs)
**Spec:** `Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` (Cursor v9/v10/v11 all folded)
**Status when authored:** Spec finalized; combined approach (TDD-ordered bugfix + CI structural fix) per Kim's 2026-05-03 direction; ready for atomic single-session execution

---

## Pre-paste checklist (Kim)

- [ ] Spec confirmed on disk: `Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` (~830 lines)
- [ ] No GPT/magic/assemble jobs currently running (check via `GET /api/admin/inflight_count`)
- [ ] Server fresh post-S5.5c+e (PID start time > production_server.py mtime)
- [ ] `dist/` build present (run `cd Production/tools/storyboard-v2 && npm run build` if not)
- [ ] Fresh terminal window, fresh `claude` session, no prior context
- [ ] cd to project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files`

If any unchecked: do NOT paste yet.

---

## Step 1 — Open fresh terminal + cd to project root

```
cd "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
claude
```

The cd is non-negotiable: zero-error-qa skill, project memory, `.claude/skills/`, and the `Production/` tree all require running from project root. Without it, terminal Claude can't find anything.

---

## Step 2 — Paste this block once `claude` is running

```
═══════════════════════════════════════════════════════════════════
You are executing the v59 S5.5c+e PROPER FIX session — combined
TDD-ordered bugfix + CI structural fix per
Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md
(Cursor v9 + v10 + v11 all folded).

CONTEXT: S5.5c+e shipped 2026-05-03 with 31/31 server gates green.
Browser smoke (Kim hands-on) immediately surfaced 5 integration
bugs (R1-R5) plus a missing + New Event UI. Cursor v9 named the
process smell ("'future' comments + server-only gates without
Playwright/e2e on critical paths"). Cursor v10 caught field-name
drift (creature_name not colloquial_name) + body-shape mismatch.
Cursor v11 caught the load-bearing CI install path (must be
.github/workflows/, not just Production/github_actions/).

Kim's direction (2026-05-03): combine bugfix + process structural
fix in ONE TDD-ordered session. NOT split. Don't optimize for
"ship now" — fix it properly. Mandatory e2e + CI is the structural
answer to "million more bugs" anxiety.

LOCKED DECISIONS — DO NOT re-litigate:
1. v3 architecture is final (37/37 gates green from S5.5d/d-cont)
2. S5.5c+e architectural choices are final (31/31 server gates)
3. Beat Generator = 3 OPTIONS (NOT 3×3) — locked LD
4. Phase B IS Cedric (memory corrected)
5. Production Map sources from GAMEPLAY_SCOPE_v3.md (V1 frozen
   per LD-357); R4 reframe = data policy not parser bug
6. Field name is `creature_name` NOT `colloquial_name` (Cursor v10)
7. bg_accept_lib_image body shape: {beat_id, key, filename,
   abs_path, slot_index} per Cursor v10
8. CI workflow MUST install at .github/workflows/ AT REPO ROOT,
   not just Production/github_actions/ (Cursor v11 — load-bearing)
9. ubuntu-latest runner per Cursor v11 (cheaper, fine for Chromium)
10. Combined TDD approach: Phase 1 (CI infra) → Phase 2 (failing
    tests, RED) → Phase 3 (fix code, GREEN) → Phase 3.7 (refactor)
    → Phase 4 (CI verification with deliberate test break) →
    Phase 5 (time-boxed S5.5f/g coverage audit) → Phase 6 (verify)
    → Phase 7 (LDs) → Phase 8 (closeout)

CURSOR v9 + v10 + v11 ALL FOLDED into spec. §15 has v9/v10 audit
trail; §18 has v11 audit trail. No outstanding review work.

OPERATING MODE FOR THIS SESSION (mandatory):

- Load the zero-error-qa skill and apply it through every phase.
- Phase 0 pre-flight is mandatory. Classify the task: COMBINED
  PROPER FIX (5 bug fixes + + New Event UI + CI Playwright +
  master overview amendment + lessons-learned LL-26 + flake
  governance + fixture pinning). Spawn appropriate advocate+counter
  agents per Rule 19 (tech-spec dual-Opus research happened in
  Desktop over v9/v10/v11 cycles; reference as architectural-review
  exemption per LD-124). Write prod_preflight_reviews row via
  try_post_or_queue BEFORE any edit; reference S5.5c+e preflight
  #199 as predecessor; confirm via read-back.
- Do not rely on memory or guess. Read every file you reference.
  Re-read at each phase boundary. If reasoning from "what I
  recall," stop and re-read instead.
- Multipass checks at every step: after each edit, read it back,
  npm run build clean OR py_compile clean, verify no unintended
  changes. Confirm execution all the way to the tail end of every
  phase before advancing.
- Provide proof of successful execution after each phase: file
  diffs, verification gate output, server restart confirmation,
  Directus write read-back, activity log entry IDs.
- Where the prompt and the spec differ, the SPEC is source of
  truth.

═══ CRITICAL: COMPACTION-AWARE CHECKPOINT AUTHORITY ═══

This combined session is ~5-6 hr / ~20 gates / ~1100+ LOC of
code+tests+config (Cursor v11 estimate; first-run reality
includes CI debugging + flake chasing). That is at the upper end
of what one session reliably ships. You have EXPLICIT AUTHORITY
to write a clean checkpoint handoff and STOP at one of these
natural boundaries if context is approaching limits:

  - AFTER Phase 1 (CI infrastructure) shipped + committed
  - AFTER Phase 2 (failing tests committed; CI red proof verified)
  - AFTER Phase 3 (all fixes green; CI green) BEFORE Phase 5 audit

If you halt at any boundary:
  - Write continuation handoff at
    Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_CONTINUATION_HANDOFF.md
  - Write prod_activity_log row CHECKPOINT_AT_PHASE_<N>_DONE
    noting what shipped + what's deferred
  - Surface to Kim with explicit reason

Don't checkpoint mid-Phase. Each phase is atomic at its boundary
(infra committed, RED proof committed, all tests GREEN +
committed, CI proof committed).

═══ THE THREE LOAD-BEARING FIXES (do not skimp) ═══

1. **Phase 1.3 dual-location workflow install** — workflow file
   MUST exist at BOTH:
   - Production/github_actions/playwright_e2e.yml (canonical source)
   - .github/workflows/playwright_e2e.yml (where GitHub Actions
     actually runs from — at REPO ROOT, not under Production/)
   Without the .github/workflows/ copy, GitHub Actions never runs
   the workflow. CI is paper-only. Cursor v11 caught this. G5
   gate verifies BOTH exist.

2. **§16 Flake governance** — without quarantine policy, retry
   discipline, and no-merge-on-flake rule for critical paths
   (R1-R5 + +NewEvent), the CI gate decays in 2 weeks. Cursor v11
   named this. Read §16 before Phase 2 test writing — flake
   tolerance shapes how tests are designed.

3. **§17 Fixture pinning** — tests MUST use dedicated
   Production/Event_e2e_fixture/ created via globalSetup; NEVER
   touch Production/Event_1/ or Event_2/ production data. Without
   this, R1.1 test breaks if Kim ever authors Event_2 resolution.
   Setup script + Playwright globalSetup config in Phase 1.

═══ EXECUTION ORDER ═══

Per spec §5 Phases 0 through 8:

- Phase 0: Pre-flight + diagnosis confirmation + scaffold audit +
  preflight row
- Phase 1: CI infrastructure (master overview §6 amendment +
  lessons-learned LL-26 + workflow YAML + dual-location install
  + playwright.config.ts:webServer + fixture pinning setup)
- Phase 2: Write failing Playwright tests (RED) — every R1-R5 +
  +NewEvent behavior + option_key gate per Cursor v9 Q5 + drag-
  hover visual cue. ~12 test cases. Confirm CI runs them and
  reports red.
- Phase 3: Fix code (GREEN). 3.1 R1 first (others harder to test
  without scope refresh). 3.2 R2. 3.3 R3. 3.4 R4 (cosmetic +
  UI note). 3.5 R5 (CSS). 3.6 + New Event (~30 lines server +
  client modal).
- Phase 3.7: Refactor (Kent Beck's red→green→REFACTOR loop).
  Optional, time-boxed 30 min, all tests stay green.
- Phase 4: CI verification — push to feature branch → CI green;
  deliberately break a test → CI red; restore → CI green.
  Validates the gate works.
- Phase 5 (TIME-BOXED): S5.5f/g coverage audit. ≤2 gaps per
  spec → amend in-session. 3+ gaps → defer to follow-up PR
  titled "S5.5f/g coverage audit v1." Don't let "audit the
  universe" creep into proper-fix scope.
- Phase 6: Verification (20 gates) — see spec §5 Phase 6.
- Phase 7: 5 NEW LDs (S5_5CE_PROPER_FIX_V1, MANDATORY_E2E_GATE_V1,
  CI_PLAYWRIGHT_ON_COMMIT_V1, BROWSER_SMOKE_REDEFINED_V1,
  NEW_EVENT_CREATION_UI_V1).
- Phase 8: Closeout — activity log COMPLETE row + master overview
  table update + tail-end verifier subagent + git commit.

═══ ESCAPE HATCH (when to STOP and surface) ═══

- Existing Playwright scaffold (Phase 0.4) doesn't run cleanly —
  fix scaffold FIRST in Phase 0.5; born-red CI is worse than no CI
- Phase 2 RED proof: tests don't all turn red (some passing
  despite bug existing) — diagnose; bug may already be partially
  fixed OR test isn't exercising the bug. Fix test before Phase 3.
- Phase 3 fix turns SOME other test red (regression in same
  session) — STOP; the fix is breaking something else. Diagnose
  before continuing.
- Phase 4 RED proof doesn't actually go red — CI workflow has
  a bug. DO NOT proceed; debug workflow (the gate is broken).
- _handle_event_create server addition exceeds 50 lines — surface
  to Kim; defer + New Event to follow-up if scope balloons.
- R1 fix surfaces deeper signal-architecture issue — STOP;
  surface for rethink (this would be the architectural smell
  scenario; Cursor v11 said it's not present in current code,
  but if discovered, halt).
- GitHub Actions billing tier limits hit — surface to Kim;
  alternatives exist (Vercel, CircleCI free tier).
- Phase 5 audit reveals 3+ coverage gaps in EITHER S5.5f or
  S5.5g spec — defer per time-box; do NOT amend in-session.
- Anything triggering Rule 26 Opus Escalation — STOP, surface.
- Browser smoke gates (G20) cannot be self-tested — DEFER to
  Kim hands-on with REDEFINED scope per spec ("does it feel
  right?" subjective UX, NOT "does anything work?").

═══ READ FIRST, in order ═══

1. Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md
   — executable spec for THIS session. SOURCE OF TRUTH. Read
   FULLY. §15 has v9/v10 audit trail; §18 has v11 audit trail.
   §16 flake governance; §17 fixture pinning. §13 has executing-
   session notes.
2. Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md
   — bundle context. §5 lists existing components (don't
   rebuild). §6 will be amended Phase 1.1.
3. Production/docs/STORYBOARD_V59_S5_5_C_SPEC_v2.md +
   STORYBOARD_V59_S5_5_E_SPEC_v1.md — what S5.5c+e shipped that
   needs fixing.
4. Production/docs/STORYBOARD_V59_S5_5_CE_BUGFIX_SPEC_v2.md —
   historical reference; superseded by proper-fix spec.
5. Production/docs/STORYBOARD_V59_S5_5_CE_HANDOFF.md — predecessor
   handoff (S5.5c+e); browser-smoke walkthrough in Notes section.
6. Production/docs/STORYBOARD_V59_PHASE_AB_REVISION_SPEC_v3.md
   — v3 architecture context.
7. CLAUDE.md Rules 19, 26, 27, 29, 35, 36
8. Production/tools/storyboard-v2/src/components/BgTab.tsx
   — Phase 0.5 audit target (effect deps line 126/152/477)
9. Production/tools/storyboard-v2/src/components/StoryboardTab.tsx
   — Phase 0.5 audit target (fetch effect line 729-747)
10. Production/tools/storyboard-v2/src/components/LibraryPanel.tsx
    — line 6 "future drop" comment is the R2 smoking gun
11. Production/tools/storyboard-v2/src/components/ui/AssetTile.tsx
    — Phase 3.2 extends API for drag prop forwarding
12. Production/tools/storyboard-v2/playwright.config.ts
    — Phase 1.4 webServer config target
13. Production/tools/storyboard-v2/e2e/ — existing scaffold
    (smoke / behavioral-parity / rollback / touchpoint-a +
    helpers.ts); Phase 0.4 audits runnability
14. Production/tools/production_server.py — Phase 3.6 adds
    _handle_event_create (~30 lines); confirm absence first per
    Cursor v9/v11 verified.
15. Production/scripts/populate_prod_modules_from_gameplay_scope.py
    — Phase 3.4 cosmetic placeholder change (creature_name field
    per Cursor v10)
16. Production/github_actions/rn-expo-gate.yml — reference pattern
    for the dual-location workflow install (Cursor v11 cited
    your April 2026 QA lessons doc)

═══ Scope Summary (combined proper fix) ═══

IN SCOPE:
1. CI infrastructure: workflow YAML at BOTH locations; master
   overview §6 convention #7; LL-26 entry; playwright.config.ts
   webServer; fixture pinning setup
2. Failing Playwright tests (~12 cases) for R1-R5 + +NewEvent
3. R1 fix: scope-change re-fetch (BgTab + StoryboardTab effect
   deps + 200ms debounce + change-only filter +
   ProjectSelector auto-load milestone after Create)
4. R2 fix: drag-drop wiring (AssetTile API extension; LibraryPanel
   draggable; BgTab beat option/char/BG ref drop targets;
   CropperModal canvas drop; CSS is-drag-over class)
5. R3 fix: option_key gate (BeatGenCard radio disabled if !key
   + tooltip; ensure all options have key at construction)
6. R4 fix (REFRAMED): cosmetic creature_name placeholder
   "M{n} — TBD"; Production Map UI note about TBD policy
7. R5 fix: library tile width ≤80px CSS variables
8. + New Event: server endpoint (~30 lines) + client modal +
   auto-load on Create
9. Refactor (Phase 3.7): time-boxed 30 min cleanup of
   duplication, all tests stay green
10. CI verification (Phase 4): RED-then-GREEN proof on real commit
11. S5.5f/g coverage audit (Phase 5): TIME-BOXED ≤2 gaps
12. 5 NEW LDs

OUT OF SCOPE (defer):
- Production Map multi-event mapping → S5.5g
- Voice profile UI → S6
- Phase A/B parity → S5.5f
- Stitcher SFX/transitions/trims → S5.5g
- Drag-drop on Safari (Chromium-only)
- Cross-browser e2e (Chromium-only)
- Visual regression testing (Percy etc.)
- Performance/load testing
- Full S5.5f/g spec amendments if Phase 5 finds 3+ gaps each
  (defer to follow-up)

═══ CRITICAL CONSTRAINTS (do NOT violate) ═══

1. TDD ORDER IS LOAD-BEARING. Phase 1 (infra) → 2 (RED) →
   3 (GREEN) → 3.7 (refactor) → 4 (CI proof). Don't write
   fixes before tests. Don't merge before CI green.
2. Mutation channel: every state write via pathappPatch from
   src/api/client.ts:170. NEVER raw fetch.
3. Asset registration per LD-421/422: every new media write via
   registered_write.register_asset(...). Never raw POST.
4. @with_pin_and_drain decorator (Cursor v8/v9) is server-side
   PYTHON ONLY. New _handle_event_create wraps with it. There is
   NO TypeScript equivalent.
5. 3 OPTIONS per beat NOT 3×3 matrix.
6. beat.final block (Cursor v10): NOT beat.use_as_final boolean.
7. creature_name field (Cursor v10): NOT colloquial_name.
8. bg_accept_lib_image body shape (Cursor v10):
   {beat_id, key, filename, abs_path, slot_index}.
9. **Workflow installs at .github/workflows/ AT REPO ROOT**
   (Cursor v11). Not just Production/github_actions/. G5 gate
   verifies both locations.
10. Test fixtures: dedicated Event_e2e_fixture/ via globalSetup;
    NEVER mutate Production/Event_1/ or Event_2/ in tests.
11. Flake governance: critical-path tests (R1-R5 + +NewEvent)
    NEVER quarantined. Diagnose + fix root cause.
12. Server staleness check (Rule 29) before any "test it" if
    production_server.py modified.
13. Rule 35: every Directus write via try_post_or_queue with
    read-back.
14. Rule 19: no shortcuts. No "we'll add tests later." No "ship
    without CI green." No "rerun CI, that flake will go away."

═══ VERIFICATION GATES (all 20 from spec §5 Phase 6) ═══

See spec for full list. Highlights:
- G1-G2: Build + server health
- G3: Existing Playwright scaffold passes
- G4: webServer config (per Phase 1.4)
- G5: BOTH workflow locations exist (Production/github_actions/
  AND .github/workflows/) — load-bearing CI install
- G6: Master overview §6 has convention #7
- G7: LL-26 entry in lessons-learned doc
- G8: e2e/s5_5ce_proper_fix.spec.ts exists with all R1-R5 +
  +NewEvent cases
- G9: Phase 4 RED proof — deliberate test break → CI red
- G10: Phase 4 GREEN restore → CI green
- G11-G16: All R1-R5 + +NewEvent tests pass
- G17: S5.5f F18 coverage audit
- G18: S5.5g G15 coverage audit
- G19: Tail-end verifier — no S5.5c+e gates broken
- G20: Browser smoke deferred to Kim with REDEFINED scope
  ("feels right?" subjective UX, NOT "does it work?")

═══ END-OF-SESSION DELIVERABLES ═══

If all 20 gates green:
- Final activity_log row S5_5CE_PROPER_FIX_COMPLETE with full
  20-gate summary + 5 root-cause diagnosis (R1-R5)
- Master overview status table updated with proper-fix shipped
  note
- Single git commit (TDD-ordered work captured atomically per
  Kim's "do it properly, no urgency" direction)

If checkpoint at phase boundary:
- Continuation handoff at
  STORYBOARD_V59_S5_5_CE_PROPER_FIX_CONTINUATION_HANDOFF.md
- Activity log CHECKPOINT_AT_PHASE_<N>_DONE row
- Surface to Kim with reason

If escape hatch fires mid-session:
- Document state at point of stop in prod_activity_log
- Surface to Kim with specific reason + decision request

═══ DIRECTUS REGISTRATION (Phase 0, before any edit) ═══

Use try_post_or_queue per Rule 35; consult schema reference doc.

prod_preflight_reviews:
- 1 row at session start: task_id="s5_5ce-proper-fix-20260503",
  task_type=feature_build, approved_to_proceed=true, references
  S5.5c+e preflight #199 as immediate predecessor

prod_reference_docs (verify all current=true; PATCH if stale):
- Master overview, S5.5c v2 spec, S5.5e v1 spec, proper-fix v1
  spec, bugfix v2 spec (legacy reference, is_current=false),
  process structural fix v1 spec (legacy reference,
  is_current=false; superseded by combined proper-fix)

═══ Begin ═══

Run Phase 0 pre-flight now via zero-error-qa. Register the
prod_preflight_reviews row + initial prod_activity_log row.
Then execute spec §5 Phases 0 through 8 in TDD order. Provide
proof of successful execution after each phase. Report back
when all 20 gates pass + Phase 8 closeout complete OR a clean
checkpoint is written at a phase boundary.
═══════════════════════════════════════════════════════════════════
```

---

## Notes for Kim (post-paste)

**Browser smoke (REDEFINED scope per Cursor v11 + Kim 2026-05-03):**

After terminal reports done, exercise the v59 client at
`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/storyboard-v2/dist/index.html`:

**Browser smoke is now "does it FEEL right?" subjective UX only.** Not "does anything work?" — that layer is automated via Playwright + CI. Reduces your smoke time from ~15 min to ~5 min.

The questions to ask while clicking:
1. Does the Beat Generator feel responsive when you switch between Event_1 / Event_2 / a new milestone?
2. When you drag a library tile to a beat option slot, does the visual cue (drop-target highlight) appear cleanly?
3. Is the Cropper canvas usable for the cropping you actually do?
4. Are the library thumbnails the right size to scan quickly?
5. Does the + New Event flow feel like the + New Milestone flow (consistent UX)?

If anything FEELS off (sluggish, ugly, confusing): tell me. If it WORKS but feels ugly: tell me, that's the smoke we still want.

If nothing FEELS off: smoke green; we're ready for S5.5f.

**CI workflow verification (1 min):**

1. Push the session's commit to GitHub (terminal Claude does this in Phase 8).
2. Within 30s, GitHub Actions should show a "Playwright e2e" workflow run starting.
3. Within ~5 min, the workflow should report green.
4. If it doesn't trigger AT ALL: the .github/workflows/ install was missed (Phase 1.3 critical fix). Tell me; we re-engage terminal to fix the install path.

**Quarantined-test list check (30 sec):**

After session: `cd Production/tools/storyboard-v2 && grep -rn "test.fixme" e2e/`. Expected: 0 matches (no quarantined tests). If 1+ matches: terminal Claude flagged something as flaky during the session — review the comment block to understand why.

**S5.5f next:** Once smoke is green + CI verified, the next session is S5.5f (Phase A/B feature parity — WaveSurfer, watercolor drag-drop, Phase A 3-clip handling). That session inherits the e2e+CI discipline this proper-fix locked in.

---

**End of S5.5c+e proper fix handoff.**

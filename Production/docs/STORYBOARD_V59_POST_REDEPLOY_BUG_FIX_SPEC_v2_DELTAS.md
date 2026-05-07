# Storyboard v59 — Post-Redeploy Bug-Fix Spec v2 — Deltas

**Date:** 2026-05-05
**Branch:** `claude/post-redeploy-bug-triage` (cut from `main` @ `d11e573`)
**Status:** HALT pending Kim direction. C1 surfaced one delta against spec premise; nothing committed; nothing improvised.

This file exists per handoff §9 ("If you hit something the spec didn't anticipate"). Each delta below is: (a) what I found, (b) what the spec/handoff says, (c) recommended path forward.

---

## Δ-C1 — Bug A premise inverted: BgTab dep array fix is **already on `main`**

### (a) What I found

`Production/tools/storyboard-v2/src/components/BgTab.tsx:134-186` — the useEffect already subscribes to all scope signals:

```tsx
}, [
  arcNumber,
  activeScope.value.event_id,
  activeProjectType.value,
  activeMilestoneId.value,
  activeTargetVideo.value,
]);
```

Plus a `prevDepsRef`-gated first-run-sync + 200ms debounce on subsequent re-fires (lines 158-174). Comment at line 129 reads: *"Initial load + scope-change re-fetch (R1 fix per spec §5 Phase 3.1). Deps include all scope signals so changing event/milestone/partition re-fires the fetch."*

Git blame confirms lines 180-186 + 129-133 are all attributable to commit `1d375ded` ("S5.5c+e proper fix: 5 bugs + +NewEvent + CI Playwright + mandatory e2e standard"), authored 2026-05-04 08:04:06 -0400 by `kimhyla`. This commit is one of the 5 weekend PRs that squash-merged into `d11e573` (`main` HEAD).

### (b) What the spec/handoff says

- Handoff §2: "Bug A — `BgTab.tsx` line ~149 useEffect dep array `[arcNumber]` only. Doesn't re-run on `activeScope`/`activeVideoRole` change → Beat Generator Segment dropdown stale → cross-event-edit risk."
- Spec §1.2: shows the buggy snippet ending in `}, [arcNumber];` — describing this as the current code.
- Spec §1.3 fix (minimal diff): adds `scopeKeyVal` + `videoRoleVal` and changes dep array to `[arcNumber, scopeKeyVal, videoRoleVal]`.
- Handoff C1 asks for a code patch + unit + e2e + LD `BG_TAB_SCOPE_SYNC_V1` (SOFT).

### (c) Why the symptom Kim observed was real but the diagnosis is off

- Kim's browser smoke that surfaced Bug A ran against the May 3 deployed bundle in `Dropbox/Production/Event_<N>/storyboard_v59_prod.html` (mtime May 3 00:05 — confirmed in the prior audit). That build predates `1d375de` (May 4 08:04).
- After yesterday's redeploy (Kim's "Option 1 confirmed" message in this session) the served HTML now contains the fixed BgTab code — so the symptom should already be gone.
- The spec was authored against the symptom-observation snapshot, not against current `main` source. A no-op patch would land on `claude/post-redeploy-bug-triage` if I executed C1 verbatim.

### (c) Recommended path forward — three options

**Option C1-A — Skip C1, write a SOFT contract LD only.** The dep array shape is already correct on `main`; write `BG_TAB_SCOPE_SYNC_V1` (SOFT) as a contract LD pointing at the existing code as the canonical implementation, plus a regression test (unit + e2e) that pins the behavior so a future refactor can't silently regress to `[arcNumber]`-only. **No code patch.** This still ships the LD per spec §6.2 and adds the test coverage spec §1.4 wanted, just without a phantom code change.

**Option C1-B — Re-verify Bug A symptom in a redeploy-fresh browser smoke first.** Kim opens `localhost:5111/`, repeats the Event_1 → Event_2 → Beat Generator switch from spec §1.1, and reports whether the Segment dropdown still goes stale. If yes → there's another root cause beyond the dep array, audit it; spec needs amending. If no → fall back to Option C1-A (LD + tests, no patch).

**Option C1-C — Execute spec §1.3 verbatim anyway.** The spec's diff would replace 5-element dep array with 3-element (`[arcNumber, scopeKeyVal, videoRoleVal]`), dropping `activeProjectType.value` + `activeMilestoneId.value`. This is a strict regression: milestone-scope changes would no longer re-fire the effect. **Disrecommended.**

I default to **Option C1-A** unless overridden. C1-B is also safe but adds a manual re-test step before any code work.

---

## Δ-INFRA-1 — Vitest/unit-test infrastructure does not exist

### (a) What I found

`Production/tools/storyboard-v2/package.json` `scripts` contains only `dev` / `build` / `preview` — no `test`. `devDependencies` has `@playwright/test` for e2e but **no `vitest`**, no `jest`, no `@testing-library/preact`, no jsdom. There is no `__tests__/` directory anywhere under `src/`. The spec's unit-test snippets (`vi.fn()`, `BgTab.spec.tsx`) assume infrastructure that hasn't been added.

### (b) What the spec says

- Spec §1.4 demands both unit (`BgTab.spec.tsx` w/ `vi.fn()` mocks) AND e2e (`storyboard-v59-bg-scope-sync.spec.ts`).
- Spec §6.3 totals "5 unit + 4 e2e + 1 retroactive + 4 cleanup-script goldens" — at least 6 of those 10 require non-e2e infra (5 src/-side unit + 1 DS-7 retroactive that loads JSON fixtures into a unit harness; cleanup-script goldens are Python and use a different stack).
- Handoff §4 step 4: "Run full test suite: `npm run test` + `pytest Production/tools/tests/`" — assumes `npm run test` exists.

### (c) Three options

**Option INFRA-A — Stand up Vitest in a separate commit (C0.5) before C1.** Adds `vitest` + `jsdom` + `@testing-library/preact` (or just `@testing-library/dom` since Preact components render via JSX without separate render utilities) to devDependencies, writes `vitest.config.ts`, adds `test` script, and lands ~5 lines of glue. ~15 min of work; commits cleanly; everything in C1-C8 that wants a unit test can then have one. C0.5 is purely infrastructure with no behavioral risk.

**Option INFRA-B (recommended for C1, possibly bundle-wide)** — Ship **e2e contract tests only** for C1; defer Vitest decision until a unit test is genuinely needed. The behavioral contract Kim cares about ("scope change → BG segment dropdown re-fetches scoped to new event") is fully observable via Playwright. The implementation-detail facts (5-element deps, `prevDepsRef`, 200ms debounce) get documented inline in the LD decision_text, not asserted at unit level. Future refactor that narrows the dep array fails the e2e test. **Cost:** loses spec §6.3's unit tests and the DS-7 retroactive-loaded-JSON pattern; e2e is slower and less precise but is what's already wired up. **Benefit:** one less infra change; cleaner bisect clarity for C1; the cleanup-script goldens (Python) aren't affected anyway since they use pytest.

**Option INFRA-C — Mix Vitest setup into C1 itself.** Disrecommended; muddies bisect clarity ("was the regression from infra setup or the contract test?").

### Default

Going with **INFRA-B for C1** (ship e2e contract test, no unit test, document deps internally in the LD decision_text). If during C2-C8 a unit-level invariant emerges that e2e can't reasonably observe (e.g., the C2b server prune of orphan beat keys at the `mutate_video_state` level — this might warrant a Python pytest, not Vitest), I'll surface it then. If you'd rather take INFRA-A so the whole bundle can use unit tests, say so and I cut C0.5 first.

---

## Δ-C1 RESOLUTION — shipped 2026-05-05

C1 closed. Decision: Option A + Kim's three modifications. Two GREEN
e2e contract tests (`storyboard-v59-bg-scope-sync.spec.ts`) + LD
`BG_TAB_SCOPE_SYNC_V1` (SOFT, id=529) + post-redeploy browser smoke
confirmation by Kim. Commit: `affb887` on `claude/post-redeploy-bug-triage`.

---

## Δ-C2 — premise CONFIRMED (no drift; execute-verbatim)

Re-verified `StoryboardTab.tsx:788-821` (C2a) and `production_server.py:1171-1199`
(C2b) against branch HEAD `affb887` (post-C1, equivalent to `main` for
the regions in question):

- **C2a — client renderer.** Lines 793-803 are exactly the
  `display_order ?? []` + `if (order.length > 0)` fallthrough pattern
  the spec describes. `git blame` attributes 793-803 to commit
  `b582f44` (initial extract from Dropbox tooling tree, 2026-05-03 23:44),
  i.e. predates all weekend work. NOT recently fixed.
- **C2b — server prune.** `mutate_video_state` at lines 1171-1199 wraps
  the partition mutator but does NOT prune `partition.beats[bid]` for
  bids missing from a new `display_order`. Same `b582f44` blame. NOT
  recently fixed.
- **C2c — cleanup script.** `Production/scripts/clean_orphan_beats_v3.py`
  does not exist; spec §2.3 Part 3 calls for a NEW file. No premise to
  invalidate.

**Decision:** execute-verbatim per spec §6.1 C2-bundle. All three parts
ship together per Cursor R7. No delta surfaces to Kim required.

---

## Δ-C5 — premise PARTIALLY fixed (different fix shape than spec wants)

### (a) What I found

`production_server.py:8537-8548` already has a partial fix for Bug C
Part 1, shipped in S5.5g with LD `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1`
(SOFT, S5.5g LD list per `s5_5g_phase_h_lds.py`):

```python
m_num = m.get("m_number")
edir: Path | None = None
if m_num is not None:
    candidate = production_root / f"Event_{m_num}"
    if candidate.is_dir():
        edir = candidate
```

`edir = event_dirs[0]` (the always-Event_1 bug spec §3.2 cites) is GONE.
Replaced with **convention-based** mapping: `m_number=N → Event_N`.
Comment (line 8542) explicitly says: "Avoids the prior bug where every
module reported Event_1." Each row's `event_dir` falls through to
`None` when the directory doesn't exist (M7-M59 etc.) so the row still
renders without segment artifacts.

### (b) What the spec says

Spec §3.3 Part 1 + §6.2 want **HARD** `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1`:
add nullable `event_number` to `prod_modules` schema, extend
`populate_prod_modules_from_gameplay_scope.py`, server reads
`event_number` (not the m_number convention), null returns warning marker.

The two solutions DIFFER in handling `m_number ≠ event_number`:
- Current SOFT convention: `M5` always maps to `Event_5`. If gameplay
  scope says M5 lives in Event_3, this is silently wrong.
- Spec HARD schema: `prod_modules.event_number` is the authority.
  M5 with `event_number=3` correctly maps to `Event_3`.

Per spec §8 question 2 and the on-page note, current creature
mapping is M1=Tessa, M2=Luna, M3=Benson, M4=Ember, M5=Bork,
M6=Bramble, M7-M15=TBD. Whether M-number = event-number for these
6 authored modules in the live `prod_modules` table is unknown without
querying Directus.

### (c) Three options

**Option C5-A — Skip-and-pin (defer the upgrade).** Treat the current
SOFT convention as sufficient for the present authored modules
(M1-M6 likely all match `m_number=event_number`). Add a contract
test that pins the convention works for the current data shape. No
schema migration. Drop the HARD upgrade from the bundle.

When this becomes wrong: when Kim authors a module whose m_number ≠
event_number. The convention silently maps to the wrong Event_<N>/.
At that point the test still passes (because it only pins the
authored modules) and the bug returns. So this is "defer" in the
literal sense — it works until it doesn't.

**Option C5-B — Verify-symptom in browser smoke first.** Have Kim
load Production Map post-redeploy and visually verify that each
authored module row's `event_dir` (now distinct per row, not
uniform Event_1) actually points to the correct Event_<N>/. If
authored M1-M6 all happen to satisfy m_number=event_number, the
SOFT convention is sufficient for now → fall back to Option A. If
any authored row resolves wrong, → Option C.

**Option C5-C — Execute-verbatim per spec §3.3 Part 1.** Upgrade
from SOFT convention to HARD schema-backed lookup:

  1. Add nullable `event_number` to `prod_modules` Directus schema.
  2. EXTEND `populate_prod_modules_from_gameplay_scope.py` to populate
     `event_number` from the same Storyline_v3 / GAMEPLAY_SCOPE_v3.md
     source it already reads for `creature_name`.
  3. Dry-run diff report — current vs proposed mapping per `m_number`.
     **Kim sign-off gate** (spec §3.3 Part 1 step 3 and handoff §3
     C5 explicit pause).
  4. Apply backfill; verify all authored rows populated.
  5. Update `_handle_production_map` to read `event_number` (not the
     m_number convention); null returns warning marker.
  6. CI test failing if any `prod_modules` row has null `event_number`.
  7. Mark LD `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` (SOFT) as
     superseded by `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1` (HARD).

### Default

Going with **Option C5-B** unless overridden — visual verification
in Kim's browser is cheap, and it determines whether the SOFT
convention is silently miscarrying any authored module right now.
Then either A (defer, write a contract test) or C (full upgrade)
based on what she sees. The Kim sign-off gate at C5 step 3 in the
verbatim path remains intact under Option C.

---

## Δ-C6, Δ-C7, Δ-C8 — pre-flight deferred until C5 outcome known

C6 (per-role status columns) is downstream of C5's event_dir resolution
path; if C5 takes Option A, C6's surface becomes a smaller column-split
edit. If C5 takes Option C, C6 absorbs the new schema field naturally.
Pre-flighting C6 in advance would make me re-do work depending on
Kim's C5 choice.

C7 (`.mn-video-selector` CSS) is purely additive — no premise to
invalidate; the audit already confirmed the rule is missing.

C8 (deploy script + LD) is fresh creation; no premise.

---

## Δ-C5.5 — smoke FAILED for the right reason: server-side Python deploy gap

### (a) What I found

Kim authorized Δ-C5 → Option B (smoke first). Smoke probe via
`curl /api/production/map` returned all 10 inspected rows with
**uniform `event_dir=Event_1`** and **uniform counts**
`{phase_a:14, phase_b:1, intro_or_resolution:36, final_concat:0}` —
M1 through M10 identical. That's the original Bug C symptom from
spec §3.1, still present at runtime.

But the local `production_server.py:8537-8548` HAS the S5.5g
convention fix (`m_number=N → Event_N`). Compared trees:

| File | mtime | size | sha256 |
|---|---|---|---|
| Local `Production/tools/production_server.py` | May 5 08:30 | 795,811 B | `ea487e9f102c…cb94665` |
| Dropbox `Production/tools/production_server.py` | May 3 15:28 | 778,777 B | `351faa36bf64…2e69e900` |

Different files. 17 KB delta in size. The running server (PID 63776,
CWD = Dropbox tree) is executing the stale May 3 code — confirmed by
reading Dropbox's file at lines 8537-8550 and finding it inside an
unrelated `_handle_stitch_loudnorm` body (line numbers don't match
between the two trees because of the 17 KB drift). The `event_dirs[0]`
always-Event_1 bug Bug C describes is the Dropbox runtime's actual
behavior.

### (b) What this matches

Yesterday's redeploy fixed the **SPA HTML** stale-build (May 3 SPA →
May 5 SPA in Dropbox/Event_1, Event_2). That session did NOT sync
`production_server.py`. Same two-tree boundary (LD-505) gap pattern,
on the Python side this time.

### (c) Why this is a blessing

It means Bug C Part 1 (event_dir mapping) is functionally a deploy
problem, not a code problem. The SOFT convention fix is in local
code; once deployed to Dropbox + server restarted, the smoke should
pass and Δ-C5 Option A's continuation plan applies cleanly:

1. Smoke shows M1≠M2 row counts → confirms Option A is the right path
2. PATCH `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` decision_text per
   Kim's 5-step plan (append the 1:1 design contract paragraph)
3. Write Python contract test pinning convention behavior
4. Drop spec §3.3 Part 1 from the bundle

### (d) Authorization needed

Re-deploying `production_server.py` local → Dropbox is a shared-state
write. Mirrors yesterday's SPA redeploy (which Kim explicitly
authorized for that specific deploy step). The Python redeploy needs
similar explicit go-ahead.

**Three options for handling the deploy gap:**

- **Option Δ-C5.5-X — Authorize Python redeploy now.** I `cp` local
  `production_server.py` → Dropbox (with timestamped backup), `pkill`
  + restart server with same flags, re-probe `/api/production/map`,
  confirm M1≠M2 counts, then close Δ-C5 with Option A per Kim's
  5-step plan. Most direct path to unblock C2/C5/C6.

- **Option Δ-C5.5-Y — Bundle Python deploy into C8.** Expand C8's
  `deploy_storyboard_v59.sh` to ALSO sync `production_server.py` (and
  any other server-side files in `Production/tools/`). Then run the
  full deploy script when C8 is ready. Cleaner architecturally — one
  deploy script handles BOTH SPA and server code.

  Cost: C2/C5/C6 work proceeds with the smoke for Δ-C5 still
  unconfirmed; we trust the local code is correct without runtime
  verification until C8 ships. We've been bitten by stale-deploy
  twice now; trusting code without runtime confirmation is the same
  failure mode in disguise.

- **Option Δ-C5.5-Z — Both.** Authorize Python redeploy now (X) for
  immediate Δ-C5 closure, AND expand C8's deploy script to handle
  server code (Y). Clean now, preventive going forward.

**Default** (pending authorization): **Z**. The path-of-least-stale-deploy.

---

## Recorded amendments (Kim 2026-05-05) — for durability across context

### Amendment A — C2c cleanup script walk path

Spec §2.3 Part 3 prescribes walking BOTH `Production/Event_*/production_state.json`
AND `Production/Milestones/*/state.json`. **Spec-as-written stays.**
The Milestones walk is a no-op in this bundle because the tree is
empty (Kim 2026-05-05: no authored milestones), but the code path
is correct. The future architecture chip will rename
`Production/Milestones/` → `Production/Milestone_*/`; the walk path
migrates with it then.

### Amendment B — C6 column scope

Add **Intro + Resolution status columns ONLY**. **DO NOT** add a
`Standalone` column for the `state.videos.standalone` role. Standalone
is milestone-scoped and milestones aren't in Production Map this
bundle.

### Amendment C — Phase A/B tab gating logic

**DO NOT** touch in this bundle. Current scope-type-keyed gating
(disabled when scope is milestone) stays. The state-presence-keyed
switch (disabled when state has no `phase_a`/`phase_b` key authored)
happens in the parked milestone-architecture-unify chip, not here.

### C6 — Five-state status glyph table (replaces spec §3.3 Part 2 three-state)

Per Kim 2026-05-05: "sometimes an event has no phase a, phase b, or
resolution video — it just goes straight to mp4 stitcher." Adds `—`
(n/a) for legitimate-absence-by-design.

| Column | `—` (n/a) when | `❌` when | `⏳` when | `✅` when |
|---|---|---|---|---|
| Phase A | `state.phase_a` key absent OR `phase_a_status` empty/null | key+status set BUT no `phase_a_stitched_*.mp4` | status set + render task in flight | `phase_a_stitched_*.mp4` exists |
| Phase B | `state.phase_b` key absent OR `phase_b_status` empty/null | key+status set BUT no `phase_b_lipsync_*.mp4` | status set + lipsync task in flight | `phase_b_lipsync_*.mp4` exists |
| Intro | `state.videos.intro` partition absent | partition present BUT no `<edir>/intro/scene_intro_*.mp4` | partition + beat subprocess pending | mp4 exists |
| Resolution | `state.videos.resolution` partition absent | partition present BUT no `<edir>/resolution/scene_resolution_*.mp4` | partition + beat subprocess pending | mp4 exists |
| Final concat | (never `—`; always one of the other 3) | no `<edir>/M{m}_*_final.mp4` and no concat task in flight | concat task in flight | `M{m}_*_final.mp4` exists |

PICKER-SPEC R3 BOUNDARY PRESERVED: the `—` determination reads
state.videos partition presence and state.phase_a/phase_b key presence,
both of which are PER-EVENT state in production_state.json — NOT
prod_modules schema columns. No Directus migration needed for any of
the five states. Conforms to picker-spec R3.

DO NOT enforce a "must have N phases lit before Final concat can
light" rule — Kim's "straight to mp4 stitcher" pattern means Final
concat is INDEPENDENT of how many phase columns are `—`.

C6 test fixtures (replaces spec §3.4 sketch):
- A: full 4-phase canonical, all artifacts on disk → all 5 ✅
- B: `videos.intro` only (no resolution partition, no phase_a/b keys),
  intro mp4 + final concat both on disk → Intro=✅, Resolution=`—`,
  Phase A=`—`, Phase B=`—`, Final concat=✅
- C: mid-authoring (`state.phase_a` set, no mp4 yet) → Phase A=❌
- D: Event_3 not authored at all (no production_state.json or empty)
  → all 5 columns `—`

Browser smoke addendum for post-C6: intro-only events should show `—`
in Resolution column, NOT ❌. Phase-A-less and Phase-B-less modules
also render `—` in their respective columns.

### Milestones architecture — PARKED

No authored milestone content; `Production/Milestones/` is empty/planned
only. Architecture cleanup (unify schema + Production Map view; keep
separate directory namespace) parked as a chip task for a future
dedicated session, not bundled here. When milestones later unify into
Production Map under a Type column, C6's per-role status columns
automatically work for them — they'll just be rows where Intro /
Resolution / Phase A / Phase B all render `—` and
`state.videos.standalone` carries the actual content. No code change
needed in this bundle for milestones.

---

## Δ-C5.5 RESOLUTION — Option Z executed 2026-05-05; smoke PASSED

### Δ-C5.5-X part executed (Python redeploy unblock)

| Step | Result |
|---|---|
| Backup dir | `Dropbox/Production/tools/.backups/` created |
| Pre-image backup | `production_server.py.preimage_20260505T143938Z_redeploy_C5_5.py` (May 3 15:28, 778,777 B, sha `351faa36…2e69e900`) |
| Sync local→Dropbox | `cp -p` complete |
| Verify sha | local `ea487e9f…cb94665` = dropbox `ea487e9f…cb94665` ✓ |
| Verify size | 795,811 B = expected ✓ |
| pkill+restart | broader pattern needed (`pkill -f "production_server.py"`); old PID 63776 → new PID 65783 |
| Restart flags | `--port 5111` flag rejected (not supported); default port is hardcoded; relaunched without it |
| Health probe | `{"status":"ok","event_id":"Event_1","uptime_seconds":6}` ✓ |

### Smoke evidence (Δ-C5 step 8)

`/api/production/map` response post-redeploy + restart:

```
M1 Tessa     event_dir=Event_1   counts={phase_a:14, phase_b:1, intro_or_resolution:36, final_concat:0}
M2 Luna      event_dir=Event_2   counts={phase_a:0,  phase_b:0, intro_or_resolution:2,  final_concat:0}
M3 Benson    event_dir=None      (Event_3/ doesn't exist on disk)
M4 Ember     event_dir=None      (Event_4/ doesn't exist on disk)
M5 Bork      event_dir=None      (Event_5/ doesn't exist on disk)
M6 Bramble   event_dir=None      (Event_6/ doesn't exist on disk)
M7-M59 TBD   event_dir=None      (TBD modules)
```

PASS criteria met: M1 ≠ M2 in BOTH event_dir AND counts. The convention
`m_number=N → Event_N` is active. The May 3 stale-Python-server bug
(uniform Event_1 across all rows) is gone. Convention also returns
None (not silent Event_1 fallback) when Event_<N>/ doesn't exist on
disk — which protects against the original Bug C symptom from
returning.

Note: M3-M6 resolving to None is correct behavior (Kim's design
contract per Δ-C5.5 carryover #2 — authored modules with corresponding
Event_<N>/ directories yet to be created on disk). Convention's null
path is what prevents the always-Event_1 silent fallback.

### Δ-C5.5-Y part — DEFERRED to C8 (per Option Z plan)

C8's `deploy_storyboard_v59.sh` will be expanded per Δ-C5.5-Y to sync
ALL tooling-repo → Dropbox runtime dependencies, not just SPA. Recorded
in deltas above. C8's LD `STORYBOARD_DEPLOY_PROCESS_V1` decision_text
will reflect the broader scope.

---

## Δ-C5 RESOLUTION — Option A closed 2026-05-05

Per Kim's 5-step plan (post-smoke-PASS):

1. ✅ **PATCH SOFT LD `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1`** with
   REFINED text per carryover #2.
   - LD id=527, decision_text length 578 → 2477 chars (+1899 appended)
   - Append marker + contract test reference present in read-back ✓
   - Script: `Production/scripts/c5_patch_production_map_multi_event_mapping_v1.py`
2. ✅ **Python contract test landed**.
   - `Production/tools/tests/test_production_map_m_to_event_convention.py`
   - 4/4 GREEN: `test_m1_resolves_to_event_1_dir`,
     `test_m2_resolves_to_event_2_dir`,
     `test_m3_resolves_to_none_when_event_3_missing`,
     `test_no_row_silently_falls_back_to_event_1`
   - Mocks `DirectusAdminClient` so the test runs without Directus
     credentials. Mirrors `test_tier3_server.py` HTTP-based pattern
     (real ProductionServer on ephemeral port + temp dir fixture).
3. ✅ **Spec §3.3 Part 1 DROPPED from bundle.** No `prod_modules.event_number`
   schema migration. No `populate_prod_modules_from_gameplay_scope.py`
   extension for `event_number`. No new HARD LD
   `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1`. The existing SOFT
   `PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1` (id=527, now PATCHed) is
   the canonical contract.
4. ✅ **Deltas note updated** (this file).
5. ⏭️ **Move to C2-bundle.**

---

## Action

C5 closure complete. Proceeding to C2-bundle (premise CONFIRMED clean
per Δ-C2 — execute-verbatim). Holding only commits between phases for
single-phase atomicity.

Branch `claude/post-redeploy-bug-triage`: `affb887` (C1) committed; C5
deliverables (test + LD-PATCH script) pending commit.

---

**End deltas v2 (post-C1, post-C5, pre-C2-bundle).**

---

## Δ-C2.5 — pre-`--apply` dry-run surfaces 6 unexpected orphans in Event_1

### (a) What I found

C2-bundle committed (`2a7fd13`). Per Kim's instruction, I ran the
cleanup script in dry-run against the Dropbox tree
(`MINDFULNEST_PRODUCTION_ROOT=$DROPBOX/Production`) before
`--apply --event 2`. The dry-run found **6 orphans in Event_1** that
nothing in the spec or handoff anticipated:

```
Event_1: 6 orphan(s)
  - role=intro beat_id=beat_12 text='"Guys... look at this writing next to the runestone..."
  - role=intro beat_id=beat_13 text="(looks at camera) Interesting .... that's what the Magic Hand…"
  - role=intro beat_id=beat_14 text="Oh this is the most EXCITING THING IN THE WORLD!!! I'll publ…"
  - role=intro beat_id=beat_15 text='What's THAT one say?  [pause] [pause]'
  - role=intro beat_id=beat_16 text='What does it mean, what does it mean…'
  - role=intro beat_id=beat_17 text='OK, Kiddo. (walking forward) Luna knows a lot about Everdal…'
Event_2: 1 orphan(s)  (the known beat_04 'MindfulNest...')
```

Plus 5 milestones, all clean (no orphans). Kim's amendment A said
"Milestones walk is a no-op in this bundle because the tree is empty";
empirically the tree has 5 milestones (looks like test-fixture content
— `e10test6df6cd`, `valid_test_smoke_001`, `verify_test_001`, etc.)
but zero orphans, so the no-op assertion holds in spirit.

### (b) Why this might NOT be "orphans to evict"

The 6 Event_1 beats look like substantive authored dialogue, not test
data. They're in `videos.intro.beats` but missing from
`videos.intro.display_order` (which is presumably `[]`). Pre-C2a-fix,
the StoryboardTab fell through to `Object.entries` and rendered all
6 — so Kim has likely been SEEING these beats in her UI as authored
content.

If the underlying problem is "display_order=[] when it should hold
these 6 beat_ids", the right fix is to repopulate display_order, NOT
delete the beats. The cleanup script's `--apply` would delete them
(with forensic backup, but still — they'd vanish from the rendered
storyboard once C2a deploys).

### (c) Held — Kim's call before any `--apply`

Two questions:

1. **Are Event_1/intro's beat_12-beat_17 authored content you'd lose
   visibility on after the C2a fix lands in the deployed SPA?**
   - Yes → don't evict; instead populate `display_order` with these
     ids (separate fix; likely a one-shot script repairing the live
     state). The C2a fix would then RENDER them correctly.
   - No (they're stale) → evict via `--apply --event 1`; full
     payload preserved in `prod_activity_log.removed_beat_payload`.

2. **Should `--apply --event 2` proceed as authorized?**
   - This is scoped to Event_2 only — touches beat_04 only.
   - Independent of the Event_1 question above.

Status: holding all `--apply` runs. Branch state:
- `affb887` C1
- `ea04c24` C5
- `2a7fd13` C2-bundle
Server: PID 65783, pinned to Event_1, uptime ~30 min.

---

**End deltas v2 (post-C2-bundle, awaiting Δ-C2.5 decision).**

---

## Δ-C2.5 RESOLUTION DIRECTION — Kim 2026-05-05: redistribute, don't delete

Kim's decision: the 7 stranded beats are **real authored content**, not
orphans to evict. The cleanup script (`clean_orphan_beats_v3.py`)
stays in the codebase as the right tool for true orphans (test
fixture leftovers, etc.) but does NOT run as a bundle action right
now. Skip `--apply --event 2` AND `--apply --event 1`. Instead,
build an audit tool, await Kim's mapping table, then execute
redistribution via a new data-driven script.

### Step 2+3 — audit tool result

`Production/scripts/audit_stranded_beats_20260505.py` (read-only).
Walks `Production/Event_*/production_state.json` AND
`Production/Milestones/*/state.json`. Prints each stranded beat in
Kim's requested format (`=== <scope>/<role>/<beat_id> ===` plus
speaker + text + current location + display_order snapshot +
proposed-target placeholder). Bonus: cross-event text-match scan to
flag any anchored beats elsewhere with matching text (handles
"Accept All copy" footprints).

**Run output (against Dropbox tree):**

| scope | role | stranded count | display_order has |
|---|---|---|---|
| Event_1 | intro | 6 | 11 entries (`beat_01..beat_11`) |
| Event_2 | intro | 1 | 0 entries (`[]`) |
| 5 milestones | — | 0 | clean |
| Total | | **7** | |

The 7 stranded beats:
- Event_1/intro: `beat_12`-`beat_17` (Tessa, Chipper, Luna dialogue
  about runestones, Magic Hands spell, "Stay loose and light",
  "Solve this mystery", "Help her calm down")
- Event_2/intro: `beat_04` (the "MindfulNest…" one)

### Cross-event text-match finding (against Kim's 'Accept All copy' hypothesis)

For each of the 7 stranded beats, the audit searched all OTHER
scopes' display_order'd (anchored) beats for matching text. Result:

> **TEXT-MATCH FOOTPRINT: no matching anchored text found in other
> scopes — likely unique to this scope** (for all 7).

This makes the "Accept All copying" hypothesis less likely: a true
cross-event-copy bug would leave both an original (anchored
elsewhere) AND the duplicate (stranded here). The shape here is
"lost from display_order in their own event," not "copied from
elsewhere."

The pattern instead suggests:
- **Event_1**: originally a 17-beat storyboard; something truncated
  display_order to 11 entries, leaving beat_12-beat_17 in `beats{}`
  but not in display_order. They CONTINUE the dialogue narrative
  (runestone-reading sequence) — clearly intended to be displayed.
  Likely target: re-extend display_order to include them in their
  current scope (Event_1/intro), preserving authoring order.
- **Event_2**: a single beat with display_order=[]. Could be
  authored-and-lost-from-display_order OR could be a true orphan
  from a partial Accept-All migration. Less clear; Kim should
  decide.

### Step 4 — Kim's mapping table needed

The audit's summary table is awaiting Kim's fill-in. Format from her
instruction:

```
beat_id     source_scope    source_role  →  target_event  target_role  display_order_position
beat_12     Event_1         intro            ???           ???           ???
beat_13     Event_1         intro            ???           ???           ???
beat_14     Event_1         intro            ???           ???           ???
beat_15     Event_1         intro            ???           ???           ???
beat_16     Event_1         intro            ???           ???           ???
beat_17     Event_1         intro            ???           ???           ???
beat_04     Event_2         intro            ???           ???           ???
```

If a beat's correct target is its CURRENT location (just needs
display_order populated, no scope move), Kim can use
`target_event=<source>` `target_role=<source>` and a position
integer. The redistribution script will handle "stay-in-place +
re-anchor" as a no-op move with display_order insertion.

### Step 5-6 — held until mapping arrives

`Production/scripts/redistribute_stranded_beats_20260505.py` (NOT
WRITTEN YET — data-driven from Kim's table) will execute her
mapping with the safety guards she specified:
- Pre-image backups of BOTH source and target state.json
- Atomic per-event mutation through `StateManager.mutate_video_state`
- prod_activity_log row per move (action=`redistribute_stranded_beat`,
  full pre-move payload)
- Dry-run first; --apply only after Kim confirms diff

Post-redistribution: re-run `clean_orphan_beats_v3.py` dry-run; expect
zero stranded beats remaining.

### Step 7 — C8 reorder

Hold C8 until redistribution complete. Otherwise the C2a fix in dist/
silently hides all 7 stranded beats from Kim's UI as soon as it
deploys via the deploy script, which would lose visibility on real
authored content during the redistribution decision window.

Revised order:
1. Δ-C2.5 redistribution audit + execute (this new step)
2. C6 (per-role status columns + 5-state glyph)
3. C7 (CSS)
4. C8 (deploy script + comprehensive expansion + LD)

### Step 8 — deltas updated (this entry)

C2-bundle commit (`2a7fd13`) STAYS. Renderer fix + server prune +
cleanup script + tests are correct regardless of whether the
stranded beats get deleted or redistributed; the cleanup script
just doesn't run as the immediate next bundle action.

Branch state:
- `affb887` C1
- `ea04c24` C5
- `2a7fd13` C2-bundle (renderer fix + server prune + cleanup script + tests + HARD LD #530)
- (audit script `Production/scripts/audit_stranded_beats_20260505.py`
  pending commit — read-only artifact for Δ-C2.5 audit trail)

Server: PID 65783, pinned to Event_1, executing the post-Δ-C5.5
synced production_server.py (pre-C2b — does NOT yet have the prune
in mutate_video_state). C2a fix is in source but NOT in deployed
SPA (Dropbox/Event_<N>/storyboard_v59_prod.html still has yesterday's
build). Both gaps are by design — held pending C8 deploy script
expansion + Kim's mapping arrival.

---

## Δ-architecture-tighten — clean_orphan_beats_v3.py removed; halt for tech-spec

Kim 2026-05-05 flagged "patches on patches and wrappers on wrappers"
pattern risk. Per `feedback_tech_spec_for_wrong_architecture.md`,
when Kim signals architectural concern, the right response is
tech-spec, not quick-patch.

Architectural tighten executed in this commit:
- clean_orphan_beats_v3.py + its test file DELETED. Server prune in
  mutate_video_state (C2b) covers the same case at write-time which
  is more correct than after-the-fact cleanup. Cleanup script was
  becoming dead code before it shipped.
- Production/scripts/.oneshot/ established with README. Audit script
  moved there. Future one-shots ship under this directory to keep
  them visibly separate from permanent infrastructure.
- LD #530 DISPLAY_ORDER_STRICT_V1 decision_text PATCHed to reflect
  2-layer enforcement (renderer + server prune); cleanup-script
  reference removed.

Bundle PAUSED at this commit. Pending items deferred to tech-spec:
- Δ-C2.5 redistribute (7 stranded beats Event_1 → Event_2)
- C6 per-role status columns

Independent items can ship either side of tech-spec:
- C7 CSS for .mn-video-selector
- C8 deploy script + LD STORYBOARD_DEPLOY_PROCESS_V1

Tech-spec scope (chip spawned for next session):
- Beat lifecycle invariants
- Cross-event move semantics (replacing the broken "Accept all beats")
- Storyboard tab UX gaps (reorder/add/delete)
- Speaker-tag drift root cause
- Recovery patterns canonicalization

Already-shipped fixes survive tech-spec (ratify, not replace):
- C1 BG_TAB_SCOPE_SYNC_V1 (LD #529)
- C5 PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 PATCH (LD #527)
- C2-bundle DISPLAY_ORDER_STRICT_V1 (LD #530, now PATCHed per
  this tighten)

---

**End deltas v2 (post-tighten, halted pending tech-spec on authoring workflow).**

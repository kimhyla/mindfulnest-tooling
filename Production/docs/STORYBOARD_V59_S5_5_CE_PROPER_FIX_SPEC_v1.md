# Storyboard v59 — S5.5c+e Proper Fix Spec v1 (TDD-style; combined bugfix + process)

**Date:** 2026-05-03
**Classification:** PROPER FIX — combines bugfix work + process structural fix in one TDD-ordered session
**Predecessor:** S5.5c+e (commits `bc12a4d` + `9efaabd`; 31/31 server-side gates green; browser smoke surfaced 5 distinct integration bugs)
**Supersedes:** `STORYBOARD_V59_S5_5_CE_BUGFIX_SPEC_v2.md` + `STORYBOARD_V59_PROCESS_STRUCTURAL_FIX_SPEC_v1.md` (both kept as historical reference)
**Master overview:** `STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md`

## §1 Why combined (Kim 2026-05-03 direction)

The split into "bugfix first → process structural fix second" was wrong framing. Kim made the call:

> "I am not concerned about the immediacy. I want the thing fixed properly, there is no 'get it fixed now so kim can use it', I am going to use it when its working for real. Would doing B automatically fix all the issues in A?"

**Direct answer:** B's discipline (mandatory e2e + CI) FORCES A's bugs to be fixed properly because Playwright tests for those bugs FAIL on commit and CI blocks merge until tests pass. So B doesn't bypass A — B makes A impossible to do sloppily. Combining them in one TDD-ordered session captures both:

1. **Phase 1:** Set up CI infrastructure (B's structural work)
2. **Phase 2:** Write failing Playwright tests for every bug (RED phase)
3. **Phase 3:** Fix code until tests pass (GREEN phase)
4. **Phase 4:** Verify CI gate works
5. **Phase 5:** Closeout

This addresses both the immediate bugs AND the process smell Cursor v9 named (`'future' comments + server-only gates`). Future feature sessions inherit the standard.

## §2 Task

Land 5 distinct bug fixes (R1-R5) + 1 small feature addition (+ New Event UI + server endpoint) + 3 process structural changes (mandatory e2e + CI workflow + lessons-learned LL-26) in one TDD-ordered atomic session.

## §3 Governing Decisions

### LDs respected
| LD | Reason |
|---|---|
| LD-19 / Rule 19 | No shortcuts — combined spec applies "no e2e, no ship" |
| LD-184 | Audio preview always-fresh (R1 must not regress; debounce mitigates re-fetch) |
| LD-357 | V1 scope frozen — R4 reframe respects |
| LD-421 / LD-422 | Asset registration via `registered_write.py` |
| LD-453 PATCH_INVARIANT_PERSISTENCE_V1 | This spec extends Rule 36 thinking to e2e |
| LD-456 / LD-460 / LD-461 | Standard scope + pin + body helper hygiene |
| LD-486 | Milestone independence (R1 milestone-load fix respects) |
| LD-494 | TargetVideoSelector visibility per scope |
| `BEAT_GEN_3_OPTIONS_NOT_GRID_V1` (S5.5c) | UI is 1×3 — must not change |
| `UI_PRIMITIVES_SHARED_V1` (S5.5c) | AssetTile primitive used; this spec EXTENDS its API |
| `DRAG_DROP_HELPER_V1` (S5.5c) | dragdrop.ts payload union exists; this spec wires it |
| `BEAT_LIFECYCLE_STATE_MACHINE_V1` (S5.5e) | R3 fix must not break |
| LL-15 (v3 lessons-learned) | "Server-side gates ≠ user-visible correctness" — this spec acts on it |

### NEW LDs this spec writes (5)

| Key | Severity | Purpose |
|---|---|---|
| `S5_5CE_PROPER_FIX_V1` | HIGH | Captures the full TDD-style fix: 5 bug fixes + + New Event + process structural changes in one atomic session. Supersedes the planned bugfix-then-process split. |
| `MANDATORY_E2E_GATE_V1` | CRITICAL | Cross-session standard: every spec's §4 Phase E (or equivalent) gates testing FUNCTIONAL behavior MUST have corresponding Playwright tests in `e2e/`. Server-side gate green + e2e gate green is the minimum. Either alone insufficient. Rule 19 (no shortcuts) explicitly extends to e2e. |
| `CI_PLAYWRIGHT_ON_COMMIT_V1` | HIGH | GitHub Actions workflow runs Playwright on every commit to feature branches + on PR open + on merge to main. CI status must be green before any "feature shipped" claim. |
| `BROWSER_SMOKE_REDEFINED_V1` | MEDIUM | Browser smoke (Kim hands-on) is now scoped to "does it FEEL right?" subjective UX. NOT "does anything actually work?" — that layer is automated via e2e. Reduces Kim's smoke time from ~15 min/session to ~5 min/session. |
| `NEW_EVENT_CREATION_UI_V1` | MEDIUM | "+ New Event" UI flow + new server endpoint `_handle_event_create` (~30 lines; verified absent by Cursor v9). |

### Data policy preserved (from bugfix v2 §2 — Cursor v9 reframe)

`PRODUCTION_MAP_TBD_HONEST_V1` informational policy: M7-M54 stay as TBD until Kim authors each arc. Cosmetic placeholder only ("M{n} — TBD" instead of bare "TBD") + UI note explaining policy. NO 53-row creature_name guesses; no Directus PATCHes beyond cosmetic.

## §4 Approach (TDD-ordered)

### §4.1 Diagnosis — root causes confirmed by direct code inspection (Cursor v9 + v10 verified)

| Root cause | Evidence | Fix |
|---|---|---|
| **R1: Scope-change doesn't trigger UI re-fetch** | `BgTab.tsx:126-149` first-load effect deps `[arcNumber]` only; `StoryboardTab.tsx:729-747` deps `[refreshTick]` only; + New Milestone Create button doesn't auto-call `/api/milestones/load` | Effect dep arrays MUST include scope signals via explicit `.value` reads; debounce 200ms; trigger only on event_id/milestone/partition CHANGE; auto-load milestone after Create |
| **R2: Drag-drop never wired** | `LibraryPanel.tsx:6` literal "future" comment; AssetTile primitive doesn't forward drag props; zero `draggable` / `onDragStart` in components | Extend AssetTile API; wire LibraryPanel; add drop targets (BgTab option slots, char/BG ref, CropperModal); CSS class `is-drag-over` (NOT `[draghover]`) |
| **R3: bg_accept_option 400** | Server expects `{beat_id, option_key}`; client sends `option_key` correctly per Cursor v9, but options can have falsy `key` field → silent no-op or 400 | Gate: option without `key` → radio button DISABLED + tooltip; ensure all options have key at construction |
| **R4: TBD creature names (data policy, NOT parser bug)** | GAMEPLAY_SCOPE_v3.md doesn't enumerate per-module data for arcs 2-9 (Cursor v9 verified). populate script hardcodes TBD by design (`populate_prod_modules_from_gameplay_scope.py:116-140`) | Cosmetic: placeholder from `"TBD"` to `"M{n} — TBD"` (uses `creature_name` field per Cursor v10 — NOT `colloquial_name`); UI note in Production Map; ~48 cosmetic PATCHes only |
| **R5: Library thumbnails too big** | LibraryPanel CSS sizing | Tile width ≤80px; rail height = 600px; scroll for overflow (measurable bounds, not "all visible") |
| **+ New Event missing UI + missing server endpoint** | `_handle_event_create` does NOT exist (Cursor v9 verified by grep) | Add ~30-line server handler + client modal; auto-load on Create |

### §4.2 TDD flow

**Phase 1 (CI infrastructure)** establishes the gate. **Phase 2 (failing tests)** documents every bug as an executable spec. **Phase 3 (fix code)** turns red tests green. **Phase 4 (CI verification)** validates the gate enforces correctly. This sequence makes regression structurally impossible.

### §4.3 bg_accept_lib_image body shape (Cursor v10 corrected)

Server `_handle_bg_accept_lib_image` (`production_server.py:9082-9097`) expects:
```
{ beat_id, key, filename, abs_path, slot_index }
```
Drag payload from LibraryPanel maps `payload.lib_key → key`; resolve `filename` + `abs_path` from library metadata; `slot_index` is 0/1/2 for option slots.

NOT `{lib_key, option_index}` — that was wrong in bugfix v1 + v2 pre-v10.

### §4.4 + New Event server endpoint design (Cursor v9 confirmed missing)

`_handle_event_create` (~30 lines) at `POST /api/event/create`:
- Body: `{event_id, event_label?}`
- Validates `event_id` regex `^[A-Z][A-Za-z0-9_]{2,63}$`
- Reserved word check: cannot start with `Test_`, `_`, `Tmp_`
- Case-insensitive uniqueness vs existing `Production/Event_*` dirs
- Creates dir + state.json via `StateManager._init_files` v3 path (DON'T invent partial JSON)
- Wraps with `@with_pin_and_drain('event_create', track_sync=False)` (server-side Python decorator)
- Returns `{ok, event_id, event_dir}` or 409 on collision

## §5 Implementation Phases

### Phase 0 — Pre-flight

**0.1.** Read this spec + master overview + bugfix v2 (historical) + process structural v1 (historical) + S5.5c v2 + S5.5e v1 + v3 spec.

**0.2.** `prod_preflight_reviews` row referencing S5.5c+e preflight #199 as predecessor.

**0.3.** Confirm bug reproduction in browser smoke per `STORYBOARD_V59_S5_5_CE_HANDOFF.md` Notes-for-Kim section.

**0.4.** Audit existing Playwright scaffold: `cd Production/tools/storyboard-v2 && npx playwright test` — does it pass against current code? If broken, fix scaffold FIRST (Phase 0.5).

**0.5.** Verify code locations from Cursor v9/v10:
- `BgTab.tsx:126,152,477` effect dep arrays
- `StoryboardTab.tsx:729-747` fetch effect deps
- `LibraryPanel.tsx` zero draggable
- `BgTab.tsx:293-296` option_key body
- `_handle_bg_accept_lib_image` at `production_server.py:9082-9097` body expectations
- `_handle_event_create` ABSENT (verify)
- `populate_prod_modules_from_gameplay_scope.py:164` PATCH_ALLOWED includes `creature_name` ✓
- `ProductionMapTab.tsx:25-26,105` renders `creature_name` ✓
- `playwright.config.ts:15-20` baseURL=5111, no webServer

### Phase 1 — CI infrastructure (B's structural piece)

**1.1.** Edit `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` §6 — add convention #7:

> 7. **Mandatory e2e coverage:** Every spec's §4 Phase E (or equivalent) gates that test FUNCTIONAL behavior MUST have corresponding Playwright tests in `Production/tools/storyboard-v2/e2e/`. Server-side gate green + e2e gate green is the minimum. Either alone is insufficient. If a behavior cannot be cleanly e2e-tested, that's a redesign signal — surface to Kim before shipping. Rule 19 (no shortcuts) explicitly extends to e2e.

**1.2.** Edit `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` — add LL-26:

> **LL-26: Server-side gates + Playwright e2e on critical paths is the minimum bar. Either alone produces integration debt.**
> Context: v59 client S5.5c+e shipped 2026-05-03 with 31/31 server-side gates green. Browser smoke (Kim hands-on) immediately surfaced 5 distinct integration bugs. Cursor v9/v10 named the pattern: "'future' comments + server-only gates without Playwright/e2e on critical paths."
> Fix is structural: every functional spec gate has a Playwright test in e2e/; CI runs on every commit; gates aren't green unless e2e passes; browser smoke (Kim) becomes "does it feel right?" subjective UX.
> Reference: `STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md`; LDs `MANDATORY_E2E_GATE_V1`, `CI_PLAYWRIGHT_ON_COMMIT_V1`, `BROWSER_SMOKE_REDEFINED_V1`.

**1.3.** Create `Production/github_actions/playwright_e2e.yml` (canonical source) AND copy/symlink to `.github/workflows/playwright_e2e.yml` at repo root (where GitHub Actions actually discovers + runs workflows). This dual-location pattern matches existing `Production/github_actions/rn-expo-gate.yml` → `.github/workflows/rn-expo-gate.yml` per April 2026 QA lessons-learned doc. **Without the `.github/workflows/` copy, GitHub Actions never runs the workflow — the CI gate is paper-only.** Cursor v11 caught this; it is THE load-bearing fix for Option 3 to function vs being theatrical.

```yaml
name: Playwright e2e

on:
  push:
    branches: [main, claude/*, feature/*]
  pull_request:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest  # Cursor v11 amendment: cheaper than macos-latest; Chromium runs fine on Ubuntu via `npx playwright install --with-deps chromium`. Switch to macos-latest only if a mac-specific failure is measured + documented.
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
      - name: Upload test artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: Production/tools/storyboard-v2/playwright-report/
          retention-days: 7
```

**1.4.** Configure `Production/tools/storyboard-v2/playwright.config.ts` `webServer:` field per Cursor v10 canonical path:

```typescript
webServer: {
  command: 'python3 ../../../Production/tools/production_server.py --event-dir ../../../Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1',
  url: 'http://localhost:5111/api/health',
  timeout: 30 * 1000,
  reuseExistingServer: !process.env.CI,
},
```

**1.5.** Verify: `cd Production/tools/storyboard-v2 && npx playwright test` exits with current scaffold passing (or surfaces existing scaffold bugs to fix first).

### Phase 2 — Write failing Playwright tests (RED)

**2.1.** Create `Production/tools/storyboard-v2/e2e/s5_5ce_proper_fix.spec.ts`. Tests for every R1-R5 + + New Event behavior listed in §4.1, plus the option_key gate from Cursor v9 Q5. ~200-300 lines of tests covering:

- **R1.1:** switch Video from intro to resolution on Event_2 → beats list clears (resolution empty); switch back → 17 beats reappear
- **R1.2:** + New Milestone Create → UI auto-loads milestone scope; scope chip shows milestone id; Video selector hides
- **R2.1:** drag library tile → drop on beat option slot 0 → POST `bg_accept_lib_image` with `{beat_id, key, filename, abs_path, slot_index: 0}` → option set
- **R2.2:** drag library tile → drop on char ref slot → ref set
- **R2.3:** drag library tile → drop on Cropper canvas → image loads
- **R2.4:** Drag-over visual cue: dragenter on drop target → element has `is-drag-over` class; dragleave → class removed
- **R3.1:** click radio on a valid option → POST `bg_accept_option` returns 200 → option marked
- **R3.2:** synthesize beat option with falsy `key` → radio button DISABLED + tooltip "Option missing key — regenerate beat"
- **R4:** Production Map shows M7-M54 as `M{n} — TBD` (using `creature_name` field); UI note visible explaining policy
- **R5:** library tile element computed width ≤ 80px on 1280px viewport; rail height = 600px; scroll appears with 50+ tiles
- **+ NewEvent.1:** + New Event modal opens; reserved-word `Test_X` rejected with regex error
- **+ NewEvent.2:** valid `Event_3` accepted; Create → server creates Event_3/ + state.json; UI auto-loads new event scope

**2.2.** Run tests locally: `cd Production/tools/storyboard-v2 && npx playwright test e2e/s5_5ce_proper_fix.spec.ts`. ALL TESTS SHOULD FAIL (RED) because bugs exist + + New Event endpoint doesn't exist + drag-drop not wired.

**2.3.** Commit Phase 2 changes (test file + workflow + master overview + lessons-learned amendments). Push to a feature branch. Verify CI runs the workflow → CI goes RED with all the failing tests visible. This proves the gate works.

### Phase 3 — Fix code (GREEN)

Each fix turns its corresponding test from red → green. Order matches priority (R1 first because R3 testing requires scope-refresh works).

**3.1. R1 — Scope-change re-fetch + auto-load milestone:**
- `BgTab.tsx:126-149` — explicit `.value` reads in deps:
```typescript
const eventId = activeScope.value.event_id;
const targetVideo = activeTargetVideo.value;
const projectType = activeProjectType.value;
const milestoneId = activeMilestoneId.value;
// ... fetch logic
}, [arcNumber, activeScope.value.event_id, activeTargetVideo.value, activeProjectType.value, activeMilestoneId.value]);
```
- Same pattern for `StoryboardTab.tsx:729-747` — bump `refreshTick` from a scope-watch effect.
- 200ms debounce; refetch only on event_id/milestone/partition CHANGE (compare prev via `useRef`)
- `ProjectSelector.tsx` — after `+ New Milestone` Create POST returns ok: auto-call `/api/milestones/load`. Same pattern for + New Event in 3.6.

Run R1.1 + R1.2 tests → should turn GREEN.

**3.2. R2 — Drag-drop wiring:**
- Extend `src/components/ui/AssetTile.tsx` to forward `draggable` / `onDragStart` / `onDragEnd` / `data-testid` (Cursor v9 Q3 + v10 Q3)
- `LibraryPanel.tsx` — set `draggable={true}` + `onDragStart={(e) => setDragData(e, {kind: 'lib-image', lib_key: it.key, tier: it.tier})}` on AssetTile
- `BgTab.tsx` beat option slots (3 per beat) — drop handlers using server-accurate body (Cursor v10 corrected):
```typescript
onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('is-drag-over'); }}
onDragLeave={(e) => e.currentTarget.classList.remove('is-drag-over')}
onDrop={async (e) => {
  e.preventDefault();
  e.currentTarget.classList.remove('is-drag-over');
  const payload = getDragData(e);
  if (payload?.kind !== 'lib-image') return;
  const lib_meta = libItemByKey(payload.lib_key);
  await pathappPatch(activeScope.value, 'bg_accept_lib_image', {
    beat_id,
    key: payload.lib_key,
    filename: lib_meta.filename,
    abs_path: lib_meta.abs_path,
    slot_index,  // 0/1/2 for which option slot
  });
}}
```
- Same drop handler pattern for char ref + BG ref slots — calls `bg_update_beat` with appropriate field
- `CropperModal.tsx` — drop target on canvas; on drop, set source image
- CSS `.mn-drop-target.is-drag-over { outline: 2px dashed var(--accent); ... }` (NOT invalid `[draghover]` selector)

Run R2.1-R2.4 tests → GREEN.

**3.3. R3 — option_key gate:**
- Audit option construction path; ensure all options have `key` field at creation
- `BeatGenCard:597` — radio button `disabled={!opt.key}`; tooltip "Option missing key — regenerate beat"
- DON'T silently no-op

Run R3.1 + R3.2 → GREEN.

**3.4. R4 — Cosmetic placeholder + UI note:**
- `populate_prod_modules_from_gameplay_scope.py` (`creature_name` field per Cursor v10):
  - Change placeholder from bare `"TBD"` to `"M{n} — TBD"` for arcs 2-9 modules
- Run script `--apply`: PATCHes M7-M54 `creature_name` (cosmetic only; ~48 PATCHes)
- `ProductionMapTab.tsx` — add UI note above table: "M7-M54 are V1 scope placeholders — author each by creating an Event. Once authored, run populate script to update creature_name from the doc."

Run R4 → GREEN.

**3.5. R5 — CSS sizing:**
- `src/index.css` (or LibraryPanel-scoped CSS) — define CSS variables:
  - `--ui-library-tile-size: 80px`
  - `--ui-library-rail-height: 600px`
- Apply to LibraryPanel tiles + container
- Verify on 1280px viewport: tile ≤80px; rail = 600px; scroll allowed for overflow

Run R5 → GREEN.

**3.6. + New Event — server + client:**
- Add `_handle_event_create` to `production_server.py` per §4.4 (~30 lines)
- `ProjectSelector.tsx` — add "+ New Event" entry → opens Modal (S5.5c primitive)
- Modal: regex-validated event_id input + label input
- On Create success → auto-call `/api/event/load` (mirrors R1 milestone fix)

Run +NewEvent.1 + +NewEvent.2 → GREEN.

### Phase 3.7 — Refactor (optional, keep tests green)

**3.7.** After all fixes turn tests GREEN: scan for opportunistic refactors. Goals: reduce duplication in scope-effect handling, tighten helpers (e.g., shared `useDebouncedScopeEffect` if multiple components do similar work), extract drag-drop scaffolding into a `useDraggable` / `useDropTarget` hook if patterns recur.

**Constraints:**
- All tests stay GREEN throughout.
- No behavior change.
- If refactor introduces complexity > what it removes: revert.
- Time-box to 30 min. If unfinished, commit as-is and defer to S5.5f.

This is Kent Beck's classic Red → Green → REFACTOR loop. Optional but recommended; Cursor v11 added.

### Phase 4 — CI verification

**4.1.** Local: all tests in `s5_5ce_proper_fix.spec.ts` GREEN.

**4.2.** Push to feature branch → CI runs → all tests GREEN.

**4.3.** **Validate the gate works (RED test):** deliberately revert one fix (e.g., remove the AssetTile draggable prop forwarding) → push → CI goes RED. Confirm UI shows red status.

**4.4.** Restore the fix → push → CI GREEN.

**4.5.** Document validation in commit message: "Validated CI gate enforces e2e coverage; deliberate test break → CI red → restore → CI green."

### Phase 5 — S5.5f and S5.5g spec coverage audit (TIME-BOXED per Cursor v11 Q7)

**5.1.** Re-read S5.5f spec §4 Phase F gates F1-F17. Cross-reference each functional gate against F18's Playwright spec list.

**5.2.** Same for S5.5g spec §4 Phase G gates G1-G14 vs G15.

**5.3. TIME-BOX:** if the gap audit reveals **2 OR FEWER** functional gates without Playwright coverage in either spec → amend in this session via small Edit calls. If **3+ gaps** in either spec → defer to a dedicated follow-up PR titled `S5.5f/g coverage audit v1`. Don't let "audit the universe" creep into proper-fix scope. (Cursor v11 amendment.)

**5.4.** Log the audit result + decision (amend in-session OR defer) to `prod_activity_log` action `S5_5CE_PHASE_5_COVERAGE_AUDIT_RESULT`.

### Phase 6 — Verification (20 gates)

**G1.** `npm run build` clean.
**G2.** Server `/api/health` 200; PID start time AFTER server edits (Rule 29).
**G3.** Existing Playwright scaffold (smoke.spec.ts + behavioral-parity etc.) passes locally.
**G4.** `playwright.config.ts:webServer` configured per Phase 1.4; spawns production_server.py on 5111. (Cursor v11 fixed cross-reference typo)
**G5.** `Production/github_actions/playwright_e2e.yml` exists AND `.github/workflows/playwright_e2e.yml` exists (copy/symlink). GitHub Actions only runs workflows at `.github/workflows/` — without this, the CI gate is paper-only. Verify by pushing to feature branch; CI should TRIGGER + RUN, not silently skip.
**G6.** Master overview §6 has new convention #7 about mandatory e2e (verify by grep).
**G7.** Lessons-learned doc has LL-26 entry.
**G8.** `e2e/s5_5ce_proper_fix.spec.ts` exists with all R1-R5 + +NewEvent test cases.
**G9.** Phase 4 RED proof: a deliberate test break caused CI to go red on a real commit.
**G10.** Phase 4 GREEN restore: fix → CI green.
**G11.** All R1.1-R1.2 tests pass (scope re-fetch + milestone auto-load).
**G12.** All R2.1-R2.4 tests pass (drag-drop wiring).
**G13.** All R3.1-R3.2 tests pass (option_key gate).
**G14.** R4 test passes (Production Map placeholders + UI note).
**G15.** R5 test passes (library tile sizing measurable bounds).
**G16.** +NewEvent.1 + .2 tests pass (modal + server endpoint + auto-load).
**G17.** S5.5f F18 coverage audit: every F1-F17 functional gate has corresponding Playwright test in F18's list (or documented exception).
**G18.** S5.5g G15 coverage audit: same.
**G19.** Tail-end verifier subagent: regression check (none of S5.5c+e's 31 originally-passing gates broken).
**G20.** Browser smoke deferred to Kim with REDEFINED scope: "does it feel right?" subjective UX. NOT "does anything work?" That's automated.

### Phase 7 — LD writes

**7.1.** Write 5 NEW LDs via `try_post_or_queue`:
- `S5_5CE_PROPER_FIX_V1` (HIGH)
- `MANDATORY_E2E_GATE_V1` (CRITICAL)
- `CI_PLAYWRIGHT_ON_COMMIT_V1` (HIGH)
- `BROWSER_SMOKE_REDEFINED_V1` (MEDIUM)
- `NEW_EVENT_CREATION_UI_V1` (MEDIUM)

### Phase 8 — Closeout

**8.1.** `prod_activity_log` row `S5_5CE_PROPER_FIX_COMPLETE` with full 20-gate summary + the 5 root-cause diagnosis.

**8.2.** Update master overview status table with proper-fix shipped note.

**8.3.** Tail-end verifier subagent (G19; cross-session regression check).

**8.4.** Git commit: `S5.5c+e proper fix — 5 bugs + New Event + CI Playwright + mandatory e2e standard (20 gates green; TDD-ordered)`.

## §6 Files Created / Modified

### Created
- `Production/github_actions/playwright_e2e.yml`
- `Production/tools/storyboard-v2/e2e/s5_5ce_proper_fix.spec.ts`

### Modified
- `Production/docs/STORYBOARD_V59_FEATURE_PARITY_MASTER_OVERVIEW.md` (§6 add convention #7)
- `LESSONS_LEARNED_May03_2026_v59_Architecture_Revision.md` (LL-26)
- `Production/tools/storyboard-v2/playwright.config.ts` (webServer config)
- `Production/tools/storyboard-v2/src/components/ui/AssetTile.tsx` (drag prop forwarding)
- `Production/tools/storyboard-v2/src/components/LibraryPanel.tsx` (draggable + drag handlers)
- `Production/tools/storyboard-v2/src/components/BgTab.tsx` (effect deps + drop handlers + option_key gate)
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` (effect deps)
- `Production/tools/storyboard-v2/src/components/CropperModal.tsx` (drop target + source from library)
- `Production/tools/storyboard-v2/src/components/ProjectSelector.tsx` (auto-load after Create + + New Event entry)
- `Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx` (UI note about TBD policy)
- `Production/tools/storyboard-v2/src/index.css` (drop-target classes + library tile sizing variables)
- `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (cosmetic `M{n} — TBD` for `creature_name`)
- `Production/tools/production_server.py` (~30 lines: `_handle_event_create`)
- `Production/docs/STORYBOARD_V59_S5_5_F_SPEC_v1.md` (F18 coverage amendment if gaps)
- `Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md` (G15 coverage amendment if gaps)

### Modified (Directus)
- `prod_modules`: ~48 cosmetic PATCHes (M7-M54 `creature_name` from `"TBD"` to `"M{n} — TBD"`)

## §7 Directus Writes

- `prod_locked_decisions`: 5 NEW LDs
- `prod_modules`: ~48 cosmetic PATCHes
- `prod_activity_log`: phase rows + COMPLETE
- `prod_preflight_reviews`: 1 row at session start
- `prod_reference_docs`: PATCH lessons-learned doc

## §8 Error Cases

| Failure | Handling |
|---|---|
| Existing Playwright scaffold doesn't run cleanly (Phase 0.4) | Fix scaffold FIRST in Phase 0.5; born-red CI is worse than no CI |
| Phase 2 tests don't all turn red (some passing despite bug) | Diagnose: maybe bug already partially fixed OR test isn't actually exercising the bug. Fix the test before proceeding. |
| Phase 3 fix turns SOME other test red (regression in same session) | STOP; that fix is breaking existing tests. Diagnose before continuing. |
| Phase 4 RED proof doesn't actually go red | CI workflow has a bug; debug workflow before proceeding |
| GitHub Actions billing limits hit (private repo) | Surface to Kim; explore alternatives |
| Test flakiness | Mark with `test.fixme` until stabilized; do NOT disable workflow |
| `_handle_event_create` server addition exceeds 50 lines | Surface to Kim; defer + New Event to follow-up if scope balloons |
| R1 fix surfaces deeper signal-architecture issue | STOP; surface for rethink |
| R2 drag-drop breaks Safari | Document; require Chromium for now; add to S5.5f/g browser matrix |
| populate script PATCH fails | Verify `creature_name` in PATCH_ALLOWED (Cursor v10 verified yes); should not fail |
| `webServer` config fails to spawn production_server.py in CI | Debug paths; CI macos-latest may have different env; fall back to documented manual server start with STORYBOARD_BASE_URL |

**No silent failures.** Per Rule 19.

## §9 Verification

20 gates green + 5 LDs registered + ~48 cosmetic PATCHes + CI workflow runs green on a real commit + RED-then-GREEN proof + browser smoke redefined to subjective UX only.

## §10 Rollback

- Client fixes: `git checkout -- src/components/`, `src/index.css`
- Server endpoint addition: `git checkout -- production_server.py`
- Populate script cosmetic: re-run with original placeholder OR PATCH 48 rows back to bare "TBD"
- CI workflow: `git rm Production/github_actions/playwright_e2e.yml`
- Master overview + lessons-learned: `git checkout -- ` those files
- LDs: PATCH to `status='superseded'`

If CI proves disruptive (false positives, infra issues), workflow can be DISABLED via repo settings; LDs stay valid; the standard is unenforced until CI is fixed.

## §11 Out of Scope (defer)

- Production Map multi-event mapping (deferred to S5.5g per spec)
- Voice profile UI (S6)
- Phase A/B feature parity (S5.5f)
- Stitcher SFX/transitions/trims (S5.5g)
- Drag-drop on Safari (Chromium-only this session)
- "+ New Module" UI concept — events are the granularity
- Authoring per-module data for arcs 2-9 (content authoring work, not code)
- Server-side option_key construction fix if root cause is server (defer; UI gate catches symptom)
- Visual regression testing (Percy or similar) — defer
- Cross-browser e2e (Safari, Firefox) — Chromium-only this session
- Performance/load testing — defer
- Test coverage reporting — defer
- E2E for milestone-only flows beyond +NewMilestone — covered as needed in S5.5f/g

## §12 Dependencies

**On v3:** state shape, scope signals, pathappPatch, Modal/Toast/Spinner/AssetTile/dragdrop primitives.
**On S5.5c+e:** all of it. This is the proper fix for what S5.5c+e shipped half-done.
**On Cursor v9 + v10 reviews:** both informed this combined spec.

## §13 Notes for the Executing Session

- **TDD ORDER IS LOAD-BEARING.** Phase 1 → 2 → 3 → 4. Don't write fixes before tests; don't merge before CI green. The TDD order IS the structural fix.
- **PRIORITY: R1 first in Phase 3.** All other bug fixes are easier to test once scope-refresh works.
- **Cursor v9 caught R4 was originally wrong** (parser fantasy); v2 reframed as data policy; this v3 carries the reframe. Don't try to populate creature names for arcs 2-9 — that data isn't in the doc.
- **Cursor v10 caught field name was `creature_name` not `colloquial_name`** — fixed throughout this spec. Verify in code; don't propagate the wrong name.
- **Cursor v10 caught bg_accept_lib_image body shape** — server expects `{beat_id, key, filename, abs_path, slot_index}`. NOT `{lib_key, option_index}`. Build payload from drag data correctly.
- **The "future drop" comment in LibraryPanel.tsx:6** is the smoking gun for R2. Spec said done; comment said future. Process smell named honestly per Cursor v9 Q10. This spec's mandatory-e2e standard prevents this class of bug going forward.
- **Don't expand scope.** Cursor v9 + v10 reviewed the underlying bugfix spec for completeness; if a deeper bug surfaces beyond R1-R5 + +NewEvent, surface to Kim. Don't quietly add fix #7.
- **+ New Event** server endpoint genuinely doesn't exist (Cursor v9 verified). Phase 3.6 ADDS it.
- **Playwright `webServer:` config (Phase 1.4) is mandatory.** Tests can't run against unstarted server. Canonical path per Cursor v10: spawn production_server.py on 5111. NO Vite dev server (port conflict risk).
- **R1 debounce 200ms** prevents fetch storm on rapid scope twitches (Cursor v9 amendment).
- **R3 option_key gate** prevents silent no-op (Cursor v9 Q5 amendment).
- **CI workflow (Phase 1.3) is the load-bearing piece.** Doc amendments + LDs codify the standard; CI is what enforces it.
- **The "process smell" Cursor v9 named is real.** This spec acts on it via mandatory e2e + CI. Future sessions inherit the standard.
- **Browser smoke (Kim) becomes "feels right?" subjective.** Reduces her ~15 min/session to ~5 min/session. The discipline is locked in BY landing this spec, not by writing it down.
- **Kim's anxiety about "a million more bugs"** — this is the answer ONLY if CI is honestly wired (Phase 1.3 workflow installed at `.github/workflows/`, not just `Production/github_actions/`) AND flake governance (§16) + fixture pinning (§17) are followed. Cursor v11 named these explicitly: "the anxiety shouldn't go to zero — it should shift from 'we didn't know' to 'we know how we'll detect and govern.'"
- **Time estimate first run: ~5-6 hr (Cursor v11 amendment from ~4 hr).** Reasons: CI path debugging on first install, flake chasing if any, Phase 5 time-boxed audit. Subsequent feature sessions inherit the discipline and run faster.
- Per Rule 29: server staleness check before any "test it now" if production_server.py modified.
- Per Rule 35: every Directus write via try_post_or_queue with read-back.
- Per Rule 19: no shortcuts. No "we'll add tests later." No "ship without CI green."

## §14 Cursor v11 Review Checklist

This spec combines work that was Cursor v9 + v10 reviewed in two prior specs. v11 should verify the combination didn't introduce new errors.

1. Did all Cursor v9 fixes from bugfix v2 carry into this combined spec? Check §3 R1-R5 rows match v9 reframes.
2. Did all Cursor v10 fixes (creature_name not colloquial_name; correct bg_accept_lib_image body shape; canonical Playwright bootstrap) carry over? Verify by grep on this spec.
3. TDD ordering (Phase 1 → 2 → 3 → 4): does this match well-known TDD discipline (red → green → refactor)? Or should we add a "refactor" phase before closeout?
4. Phase 4.3 deliberate test break to validate CI: is this a one-time validation OR should it be a recurring CI smoke gate (e.g., monthly)? Tradeoff.
5. macos-latest runner (Phase 1.3 workflow): is GitHub Actions billing tier OK with macOS minutes? Or should we use ubuntu-latest for cost?
6. `webServer:` config (Phase 1.4): the relative path `../../../Production/tools/production_server.py` — is that CI-friendly, or should we use absolute paths via `process.cwd()`?
7. Phase 5 S5.5f/g coverage audit: should this happen IN this session, or be its own follow-up? Pro: locks coverage now. Con: scope creep.
8. Test count (~12 cases in s5_5ce_proper_fix.spec.ts): is this enough granular coverage, or should we split into separate spec files per bucket?
9. Are 20 gates the right count? Should we drop any (e.g., G19 tail-end verifier) or add any?
10. Does the combined session estimate (~4 hr) feel right, or should we anticipate ~5 hr given TDD discipline overhead?
11. Pattern check (one final time): do you see ANY architectural smell across R1-R5 + the process gap that this combined approach doesn't address?

Append findings as §16 before terminal execution.

## §15 Cursor v9 + v10 audit trails (preserved from prior specs)

### v9 findings (from bugfix v2 §14)

| Finding | Resolution in this combined spec |
|---|---|
| Q1 R1 useEffect deps | §4.1 R1 row + §5 Phase 3.1 explicit `.value` reads + dep array |
| Q2 milestone create auto-load | §5 Phase 3.1 auto-call after Create |
| Q3 AssetTile API extension | §5 Phase 3.2 forwards drag props |
| Q4 drag-hover styling | §5 Phase 3.2 `is-drag-over` class (NOT `[draghover]`) |
| Q5 option_key gate | §5 Phase 3.3 + R3.2 test |
| Q6 GAMEPLAY_SCOPE format | §4.1 R4 reframed as data policy |
| Q7 _handle_event_create absent | §4.4 + §5 Phase 3.6 ADDS endpoint |
| Q8 Playwright webServer | §5 Phase 1.4 canonical config |
| Q9 12 gates not enough | §5 Phase 6 has 20 gates including CI proof |
| Q10 process smell | §5 Phase 1 IS the structural fix Cursor named |
| §3 R1 typo "must NOT" | §4.1 R1 row corrected |
| LD wording false claim | §4.4 acknowledges endpoint absence |
| R4 wrong diagnosis | §4.1 R4 reframed as data policy |
| H10 unmeetable | §5 Phase 3.5 measurable bounds |
| R1 refetch debouncing | §5 Phase 3.1 200ms + change-only |

### v10 findings (from bugfix v2 §15)

| Finding | Resolution in this combined spec |
|---|---|
| `colloquial_name` field name wrong | Global use of `creature_name` per §4.1 R4 + §5 Phase 3.4 |
| §4 C3 drag-drop body shape wrong | §4.3 documents correct shape; §5 Phase 3.2 example uses it |
| §7 PATCH_ALLOWED row | §8 error row updated; `creature_name` already in PATCH_ALLOWED |
| H12 Playwright bootstrap (Vite vs 5111) | §5 Phase 1.4 canonical: production_server.py on 5111, no Vite dev |
| Q1 useSignalEffect optional | §5 Phase 3.1 keeps explicit deps; useSignalEffect is alternative not required |
| Q2 debounce 200ms | KEEP (approved with note) |
| Q3 AssetTile {...rest} | KEEP (approved) |
| Q5 H8.1 disable + tooltip | KEEP (approved) |
| Q7 reserved words | OPTIONAL: could add `archive`, `tmp`, `system` for parity |
| TBD churn vs UI-note-only | This spec keeps cosmetic PATCH; if Kim wants zero churn, drop §5 Phase 3.4 PATCHes and keep UI note only |

---

## §16 Flake governance (NEW per Cursor v11 honest-answer)

Cursor v11 named flake as the second-order risk that decays the CI gate over time: "Without quarantine policy, retry discipline, and deterministic fixtures, you trade 'bugs at smoke time' for 'red CI roulette.'" Without policy, flaky tests produce false reds, people start ignoring CI, and we're back where we started.

### Policy

1. **Critical-path tests stay green or block merge.** R1.1, R1.2, R2.1, R2.2, R2.3, R3.1, R3.2, +NewEvent.1, +NewEvent.2 are critical paths. If any of these flake, we DO NOT quarantine — we diagnose the root cause and fix.

2. **Non-critical tests** that flake 2× in CI within 7 days WITHOUT a code change driving the difference → quarantine via `test.fixme(...)` with a comment block:
   ```
   // FLAKY: quarantined YYYY-MM-DD
   // CI run #N showed flake; root cause TBD
   // Owner: Kim / next session to investigate
   // Re-enable after: cause found + fix landed
   ```
   AND log to `prod_activity_log` action `TEST_QUARANTINED` with the test name + reason.

3. **Quarantine review.** At the start of every feature session, terminal Claude lists currently-quarantined tests (`grep test.fixme e2e/`). If list grows beyond 3, surface to Kim — that's a flake-debt signal worth pausing for.

4. **Re-enable discipline.** A test comes out of quarantine ONLY when:
   - Root cause identified
   - Fix landed
   - 5 consecutive CI runs pass
   Then remove `test.fixme`, log `TEST_REENABLED` activity row.

5. **Retry discipline.** Playwright config: `retries: 1` in CI mode (single retry for transient infra issues like network blip), `retries: 0` locally (so Kim sees flake immediately). NOT `retries: 3+` — that hides flake; we want to see it.

### Why this matters

Cursor v11: *"flaky tests are treated as seriously as failing tests."* Without policy, the first flaky test = "rerun the build." The second = "ignore it, we know that one." The tenth = CI is decoration, not enforcement. Policy keeps flake debt visible + bounded.

## §17 Fixture pinning (NEW per Cursor v11 honest-answer)

Cursor v11 flagged: "R1.1 assumes Event_2 intro vs resolution behavior; if data moves, tests become spec drift, not product bugs." If Kim later authors Event_2 resolution beats, the test that "Event_2 resolution shows empty" breaks for non-bug reasons.

### Policy

1. **Tests use dedicated fixtures, NOT production data.** Create `Production/Event_e2e_fixture/` directory + `production_state.json` with v3-shape state seeded for known testable conditions:
   - intro: 3 beats with known content
   - resolution: 0 beats (for R1.1 empty-partition test)
   - phase_a / phase_b: known mock state
   - One option per beat with `key` field present (for R3.1 test)
   - One option WITHOUT `key` (for R3.2 disabled-radio test)

2. **Setup step in Phase 1 (CI infrastructure):** Playwright `globalSetup` script copies `Event_e2e_fixture/` to a temp location + spawns production_server.py against THAT temp event_dir. Tests run against fixture, not Kim's real data.

3. **Teardown step:** Playwright `globalTeardown` removes temp event_dir + any test-created milestones.

4. **Read-only on real data:** tests should NEVER mutate `Production/Event_1/` or `Production/Event_2/` — only the temp fixture copy.

5. **Fixture versioning:** if a test legitimately needs different fixture state, create `Event_e2e_fixture_v2/` rather than mutating v1. Keeps fixtures reproducible across CI runs.

### What goes in Phase 1.3 (workflow) for this

Add CI step:
```yaml
- name: Seed e2e fixture
  working-directory: Production/tools/storyboard-v2
  run: cp -r ../../Event_e2e_fixture /tmp/e2e_test_event && export E2E_EVENT_DIR=/tmp/e2e_test_event
```

And `playwright.config.ts:webServer.command` reads `E2E_EVENT_DIR` env var instead of hardcoded `Production/Event_1`.

### Why this matters

Cursor v11: *"You need pinned fixtures or seed steps called out."* Without this, every time Kim authors content, e2e tests start failing in non-product ways. Fixture pinning = tests test the CODE, not the DATA.

## §18 Cursor v11 findings folded (audit trail)

| Finding | Resolution |
|---|---|
| RELEASE-BLOCKER: workflow at `Production/github_actions/` doesn't trigger CI; must also be at `.github/workflows/` | FIXED — Phase 1.3 explicitly requires both locations + G5 verifies presence. THE load-bearing fix. |
| AMEND: G4 cross-reference typo (§4.1.4 → Phase 1.4) | FIXED |
| AMEND: macos-latest costly; ubuntu-latest preferred for Chromium | FIXED — runner switched + rationale comment |
| AMEND: TDD ordering should add Refactor sub-phase | FIXED — Phase 3.7 added |
| AMEND: time estimate ~4 hr unrealistic; ~5-6 hr first run | FIXED — §13 Notes updated |
| AMEND: §15 v10 row pointer accuracy | KEEP — minor; will note in §15 if Kim wants tighter audit trail |
| AMEND: Phase 5 audit scope creep | FIXED — Phase 5.3 time-box: ≤2 gaps amend in-session, 3+ defer to follow-up PR |
| Q11 honest answer — residual risks | NAMED EXPLICITLY: §16 flake governance + §17 fixture pinning. Without these, CI gate decays. With them, the discipline is durable. |
| v9/v10 carry-over verification | ALL GREEN per §15 + Cursor v11 spot-check |

---

## §19 Tooling-repo migration amendment (added 2026-05-03 post-precondition session)

The "no GitHub remote" gap that halted the original proper-fix Phase 0 has been resolved by the precondition session documented in `TOOLING_REPO_SETUP_SPEC_v1.md` + `TOOLING_REPO_SETUP_RESULTS.md`. Resulting changes to this spec:

### §19.1 Working tree

All proper-fix execution moves from the Dropbox tree to:

```
/Users/kimberlysmith/Projects/mindfulnest-tooling
```

Directory layout mirrors `Production/` from Dropbox (per LD `TOOLING_REPO_CREATED_V1` + LD-505). Same paths in `playwright.config.ts:webServer.command` (`../../../Production/tools/production_server.py`) resolve correctly. No path rewrites required in the spec body.

### §19.2 Phase 1.3 simplified

The original Phase 1.3 dual-location pattern (`Production/github_actions/playwright_e2e.yml` AS canonical + `.github/workflows/playwright_e2e.yml` AS active) was a workaround for a tree that lacked a real GitHub `.github/workflows/`. The new tree has it (the precondition session created `smoke.yml` there).

**Revised Phase 1.3:** install ONLY `.github/workflows/playwright_e2e.yml` directly in the tooling-repo tree. No `Production/github_actions/` mirror. The full workflow YAML body is unchanged from the original Phase 1.3 (ubuntu-latest, Node 20, Python 3.9, npm ci/build/playwright install/test).

### §19.3 G5 simplified

**Revised G5:** verify `.github/workflows/playwright_e2e.yml` exists in the tooling-repo tree AND a real CI run triggered + reported on a real commit. (Previously checked dual locations.)

### §19.4 Document canonicality

The DROPBOX tree remains canonical for `Production/docs/` (specs, handoffs, lessons-learned). The tooling repo received a snapshot copy during the precondition session (per the subset-boundary decision), but **terminal sessions must read from the Dropbox path** to get the latest spec text. Convention going forward:

- Read specs/docs: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/...`
- Edit code: `~/Projects/mindfulnest-tooling/Production/...`
- Edit specs/docs: Dropbox tree (then sync if desired; not required for CI)

### §19.5 Cred resolution for the proper-fix session

Per `TOOLING_REPO_SETUP_RESULTS.md` §"Directus cred handling": for local Mac dev (where the proper-fix session runs), `directus_admin_client._candidate_keys_paths` falls back to the Dropbox `API_KEYS_MASTER.md` location. Directus writes work without env var setup.

For the eventual CI Playwright run: GitHub Actions Secrets must be set (DIRECTUS_URL, DIRECTUS_ADMIN_EMAIL, DIRECTUS_ADMIN_PASSWORD, plus any API keys exercised by tests). The original Phase 1.3 workflow YAML did NOT include `env:` blocks for these — **add them to the workflow** during Phase 1.3 install. Reference `.env.example` in the tooling repo for the variable names.

Phase 1 substep added (1.3.5): `gh secret set` calls for required Directus + API key secrets, OR document explicitly that the proper-fix session author runs them manually before pushing the workflow. Either path is acceptable; the gate is "CI run completes with no auth-related failures."

### §19.6 Phase 0 amendments

Phase 0 pre-flight in the new tree adds:

- **0.0 (NEW):** `cd ~/Projects/mindfulnest-tooling && git pull` (sync from origin/main; should be at the smoke commit `faa25ca` baseline)
- **0.1 (NEW):** `git checkout -b claude/s5_5ce-proper-fix` (feature branch)
- **0.2 (NEW):** install storyboard-v2 deps if not done: `cd Production/tools/storyboard-v2 && npm install && npx playwright install --with-deps chromium`
- **0.3 (NEW):** verify `npm run build` succeeds in this tree (catches any extraction-related issues before any test work)
- (existing 0.1-0.5 follow as 0.4-0.8)

### §19.7 Halted terminal

The original proper-fix session terminal that halted at Phase 0 has done its job (caught the gap that triggered this whole chain). It must be told to STAND DOWN cleanly: write `prod_activity_log` row `CHECKPOINT_HALTED_PENDING_TOOLING_REPO` with reason "no remote on Dropbox tree; tooling-repo precondition session ran separately and shipped LD-505," then exit. The new proper-fix session is a fresh terminal in the new working tree. Do NOT resume the halted terminal.

### §19.8 Reference LDs (read alongside this spec)

- `TOOLING_REPO_CREATED_V1` (LD-505, HIGH 2026-05-03) — canonical pointer to repo URL + working tree path + boundary
- `MINDFULNEST_GIT_REPO` (LD-121, CRITICAL) — iOS app repo off-limits
- `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA` (LD-185, HIGH) — separate-repos pattern
- `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` (LD-327, HIGH) — cred loading explicit

---

**End of S5.5c+e proper fix spec v1 (Cursor v11 fixes + §19 tooling-repo amendment folded).**

This is now ready for terminal execution in the new tooling-repo working tree. The CI workflow installation (Phase 1.3 single-location) + flake governance (§16) + fixture pinning (§17) + working-tree migration (§19) are the load-bearing pieces. Without them, Option 3 was theatrical. With them — and now with a real GitHub remote enforcing CI — Kim's "million more bugs" anxiety has a concrete structural answer: bugs of this class are caught at commit time on a real remote, not at browser smoke time.

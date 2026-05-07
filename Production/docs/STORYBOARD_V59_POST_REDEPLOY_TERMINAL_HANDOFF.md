# Storyboard v59 — Post-Redeploy Bug-Triage Terminal Handoff

**For:** Fresh terminal Claude session
**Date authored:** 2026-05-05
**Authored by:** main session post-Cursor v2 APPROVE
**Branch (target):** `claude/post-redeploy-bug-triage` — cut fresh from `main`. `claude/video-role-picker` is PARKED; do NOT continue that branch.

---

## 0. TL;DR — what this session does

You are landing 5 LDs across 6 sequential commits (C1, C2-bundle, C5, C6, C7, C8) onto `claude/post-redeploy-bug-triage`. Three HARD bugs + one SOFT cosmetic + one SOFT process LD. The authoritative execution doc is:

**`Production/docs/STORYBOARD_V59_POST_REDEPLOY_BUG_FIX_SPEC_v2.md`**

Read that file end-to-end BEFORE any code change. Cursor APPROVED v2 on 2026-05-05 after a v1 → v2 round (4 must-fix folded). Spec §6.1 is the atomic execution plan. Spec §6.2 is the LD list. Spec §8 captures Kim's locked answers to the three open questions.

If anything in this handoff conflicts with the spec, the spec wins.

---

## 1. Essential context (read before touching code)

### 1.1 Two-tree boundary (LD-505)

- Dropbox tree: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` — canonical for content, state, docs
- Tooling repo: `kimhyla/mindfulnest-tooling` — canonical for code (`Production/tools/storyboard-v2/src/`, `Production/tools/production_server.py`, etc.)
- Code edits go through the tooling repo. State edits go through the mutation channel only. Docs in `Production/docs/` live in Dropbox.

### 1.2 Mutation channel invariant (LD-519)

All client mutations go through `pathappPatch(scope, endpoint, body)` at `Production/tools/storyboard-v2/src/api/client.ts:175`. Scope keys (event_id, video_role) are auto-injected. There is a grep CI gate that fails if any client component calls `fetch` directly for a known mutation endpoint. Don't bypass it.

### 1.3 Discipline standards DS-1..DS-12

Codified in `.claude/skills/zero-error-qa/SKILL.md`. Most relevant for this session:
- **DS-1** Contract-first — write the failing unit + e2e BEFORE the patch
- **DS-2** Boundary — scope-key auto-injection enforced; cleanup script writes through `mutate_video_state` only
- **DS-7** Retroactive — real `Production/Event_2/production_state.json` shape ships as a unit fixture
- **DS-12** Severity — every LD tagged HARD or SOFT explicitly; no conditional forks

### 1.4 Storyboard launch URL (correct one — handoff doc id=198 has more)

- Server: `Production/tools/production_server.py --port 5111 --storyboard storyboard_v59_prod.html` (run from Dropbox tree CWD)
- Browser: **`http://localhost:5111/`** (root path, no filename suffix)
- Server reads from Dropbox tree `Production/Event_<N>/storyboard_v59_prod.html` — code merges DON'T update that file. Use the deploy script (see §3 C8) for redeploy.

### 1.5 Picker spec is the cross-check authority for Production Map role-status

`Production/docs/STORYBOARD_V59_VIDEO_ROLE_PICKER_SPEC_v1.md` — Cursor R3 locked: role-status columns are DERIVED-FROM-DISK; NO `prod_modules` schema expansion for role status. Spec v2 §3.6 states this inline. Don't introduce a second source of truth for role status.

---

## 2. The three HARD bugs in plain language

| Bug | Where | What's broken |
|-----|-------|---------------|
| **A** | `BgTab.tsx` line ~149 useEffect dep array | `[arcNumber]` only. Doesn't re-run on `activeScope`/`activeVideoRole` change → Beat Generator Segment dropdown stale → cross-event-edit risk. |
| **B** | `StoryboardTab.tsx` lines 760-781 + state hygiene | When `display_order: []`, falls through to `Object.entries(beats)` and renders all keys. Event_2 intro shows orphan `beat_04`. |
| **C** | `production_server.py:8429-8472` `_handle_production_map` | `edir = event_dirs[0]` — every M# row globs Event_1 only. AND `Role` column reads `prod_modules.video_role` (intent metadata, wrong source for status). |

Plus SOFT:
- **D** — `.mn-video-selector` has no CSS rule
- **E** — No documented redeploy step; merge-to-Dropbox gap cost ~1 day this weekend

---

## 3. C1 → C8 execution order (from spec §6.1)

Each commit should land on `claude/post-redeploy-bug-triage` separately, with its tests passing. Run `npm run test` (Vitest) + Python tests after each.

### C1 — Bug A (Beat Generator scope sync)

**Files:** `Production/tools/storyboard-v2/src/components/BgTab.tsx`
**Patch:** Add `scopeKeyVal = scopeKey(activeScope.value)` + `videoRoleVal = activeVideoRole.value`. Add both to the useEffect dep array at line ~149.
**Tests:**
- Unit: `Production/tools/storyboard-v2/src/components/__tests__/BgTab.spec.tsx` — mount with scope `M1E1/intro`, mutate to `M2E1/resolution`, assert effect re-fires
- e2e: `Production/tools/storyboard-v2/e2e/storyboard-v59-bg-scope-sync.spec.ts` — load Event_1, switch to Event_2 via EventSelector, switch tab to Beat Generator, assert request body carries `event_id=2`
**LD to file:** SOFT `BG_TAB_SCOPE_SYNC_V1`

### C2-bundle — Bug B (renderer + server prune + cleanup script)

Three parts in ONE commit per Cursor R7 (same root cause; partial-fix risk if split).

**C2a — Client renderer:** `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` lines 760-781. Replace the `display_order ?? []` + `if (order.length > 0)` pattern with `if (partition.display_order !== undefined)` so explicit `[]` means "render zero", not "fall through to Object.entries". Keep legacy fallback for `undefined`. Tests:
- Unit `StoryboardTab.spec.tsx` — three cases (`['beat_01','beat_02']` → 2; `[]` → 0; `undefined` → all sorted)
- e2e `storyboard-v59-display-order-empty.spec.ts` — fixture with `beats: { beat_04: ... }, display_order: []` → renders "No beats in this event yet."
- DS-7 retroactive — fixture loading actual current `Production/Event_2/production_state.json` shape; assert beat_04 NOT rendered

**C2b — Server prune:** `Production/tools/production_server.py` `mutate_video_state` (around line 1171). When the mutator writes a new `display_order`, drop any `partition.beats[bid]` whose `bid` is not in the new list. Atomic write through existing channel; respects LD-519. Test: `tests/test_production_state_mutate_video_state.py` — set `display_order=['beat_01']` while beats has `beat_01`+`beat_99`; assert `beat_99` dropped.

**C2c — Cleanup script:** `Production/scripts/clean_orphan_beats_v3.py`

```
USAGE
  python3 clean_orphan_beats_v3.py [--apply] [--event <event_id>]
                                   [--milestone <milestone_id>] [--all]

DEFAULT: dry-run.

SAFETY GUARDS:
  1. PRE-IMAGE BACKUP — before --apply, copy production_state.json to
     <event_dir>/.backups/state/preimage_<UTC>_clean_orphan_beats.json
  2. SCOPED MODE — --event or --milestone required for first live run.
     --all permitted only after at least one scoped run has been verified
     (track via marker file or activity-log lookup).
  3. AUDIT LOG — one prod_activity_log row per mutated event/milestone with:
     summary, event_id, video_role, removed_beat_ids, removed_beat_payload
     (FULL beat object, including text, so dialogue isn't lost),
     preimage_backup_path, applied_at, tags=[beat_cleanup, DISPLAY_ORDER_STRICT_V1]

LOGIC:
  - Walk Production/Event_*/production_state.json AND
    Production/Milestones/*/state.json
  - For each videos.<role> partition where display_order is a present list:
    drop beats[bid] for any bid not in display_order
  - Skip partitions where display_order is undefined (legacy)
  - Atomic write through ProductionState.mutate_video_state when --apply
```

Per Kim 2026-05-05: orphan auto-deletes on `--apply`. The full beat payload is captured in `removed_beat_payload` so the dialogue isn't lost.

Tests:
- Dry-run golden — fixture with 1 orphan; assert correct stdout, no mutation
- `--apply --event` golden — assert orphan removed, display_order untouched, pre-image file written, prod_activity_log row written with `removed_beat_payload`
- `--all` rejection — refuses without a prior scoped run
- Legacy-skip — fixture with `display_order: undefined`; assert nothing mutated

**LD to file (after C2-bundle):** HARD `DISPLAY_ORDER_STRICT_V1`

**Post-C2 action:** Run `python3 Production/scripts/clean_orphan_beats_v3.py --apply --event 2` to evict the live orphan `beat_04` from Event_2 intro. Verify pre-image backup file written + prod_activity_log row landed.

### C5 — Bug C Part 1 (event_dir mapping, Option A schema)

**Steps (from spec §3.3 Part 1):**
1. Add nullable `event_number` (integer) to `prod_modules` Directus schema
2. EXTEND `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (do NOT create a parallel backfill script) — the same script already populates `creature_name` from Storyline_v3 / GAMEPLAY_SCOPE_v3.md
3. Dry-run diff report: current vs proposed mapping per `m_number` — Kim signs off before live apply
4. Apply backfill; verify all rows populated
5. Update `_handle_production_map` (production_server.py:~8429) to read `event_number`, resolve `Production/Event_<event_number>/`, return warning marker if null (do NOT silently use Event_1)
6. CI/test validation that fails if any `prod_modules` row has null `event_number`

**Tests:**
- Python unit `test_production_map_endpoint.py` — fixture with two event_dirs + `prod_modules` rows with distinct `event_number`; assert each row's `event_dir` matches; null-event_number fixture asserts warning marker
- e2e — assert at least 2 distinct values in `event_dir` across map rows

**LD to file:** HARD `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1`

**Sign-off gate:** PAUSE between step 3 and step 4. Show Kim the dry-run diff. Don't apply backfill until she signs off.

### C6 — Bug C Part 2 (per-role status columns derived from disk)

**Files:**
- `Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx` — replace `SEGMENTS` constant. New columns: `phase_a`, `phase_b`, `intro_status`, `resolution_status`, `final_concat`. Drop the standalone `Role` column from `<thead>` and `<tbody>`.
- `Production/tools/production_server.py` `_handle_production_map` — replace `intro_or_resolution` glob with TWO separate globs:
  - `intro_status`: scan `<edir>/intro/scene_intro_*.mp4` → ✅/❌/⏳
  - `resolution_status`: scan `<edir>/resolution/scene_resolution_*.mp4` → same mapping
- ⏳ rule: state.json says partition exists but no mp4 yet
- Cell payload shape unchanged: `{status, count, latest_filename}`

**Tests:**
- Python unit — Event_1 fixture has intro mp4 only; Event_2 fixture has both. Assert Intro ✅ / Resolution ❌ for Event_1's M; both ✅ for Event_2's M
- e2e `storyboard-v59-production-map.spec.ts` — load map, assert both Intro and Resolution status columns present; assert no standalone `Role` column

**LD to file:** HARD `PRODUCTION_MAP_ROLE_STATUS_DERIVED_V1`

### C7 — Bug D (`.mn-video-selector` CSS)

**File:** `Production/tools/storyboard-v2/src/app.css`. Add the rules from spec §4.2 (mirror `.mn-event-selector` pattern). No tests required beyond visual smoke after C8 redeploy.

### C8 — Bug E (LD + deploy script)

**Steps:**
1. File LD `STORYBOARD_DEPLOY_PROCESS_V1` (SOFT) into `prod_locked_decisions`. Decision text from spec §5.2.
2. Write `Production/scripts/deploy_storyboard_v59.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/Production/tools/storyboard-v2"
npm run build
for evt in "$ROOT/Production/Event_"*/; do
  [[ "$(basename "$evt")" =~ ^Event_[0-9]+$ ]] || continue
  cp dist/index.html "$evt/storyboard_v59_prod.html"
  shasum -a 256 "$evt/storyboard_v59_prod.html" > "$evt/storyboard_v59_prod.html.sha256"
done
pgrep -f "production_server.py.*5111" >/dev/null || (cd "$ROOT" && nohup python3 Production/tools/production_server.py --port 5111 --storyboard storyboard_v59_prod.html >/tmp/mn_server.log 2>&1 &) && sleep 2
open "http://localhost:5111/"
```

3. `chmod +x Production/scripts/deploy_storyboard_v59.sh`
4. (Optional Phase 2 GitHub Action — deferred.)

**LD to file:** SOFT `STORYBOARD_DEPLOY_PROCESS_V1`

---

## 4. After C8 — verification + close-out

1. Run `./Production/scripts/deploy_storyboard_v59.sh` (it auto-launches server if not running, then opens browser)
2. Browser smoke at `http://localhost:5111/`:
   - Open Beat Generator tab on Event_1, switch to Event_2 via EventSelector, confirm Segment dropdown updates → **Bug A confirmed fixed**
   - Open Storyboard tab on Event_2 / intro, confirm "No beats in this event yet" message (no orphan beat_04) → **Bug B confirmed fixed**
   - Open Production Map, confirm distinct `event_dir` per row + Intro/Resolution status columns derived from on-disk presence → **Bug C confirmed fixed**
   - Visual confirmation `.mn-video-selector` styled (matches `.mn-event-selector`) → **Bug D confirmed fixed**
3. If `clean_orphan_beats_v3.py --apply --event 2` was NOT already run after C2-bundle, run it now
4. Run full test suite: `npm run test` + `pytest Production/tools/tests/`. e2e count target: 91 → ~99
5. mn-context SAVE — invoke the `mn-context` skill to update MEMORY index for this session
6. Push branch, open PR, paste the spec §6.1 commit list as PR description

---

## 5. Watch items (do NOT pre-emptively patch)

These are flagged in spec but DEFERRED:

- **`bg_session_state` server-side scoping (spec §1.5):** server stores `active_context` once per process. If during browser smoke you observe cross-tab/cross-event collision (editing in one tab silently overwrites another), HARD-promote and patch in a follow-up session. Until then, no LD filed.
- **GitHub Action auto-deploy (spec §5.3):** deferred to a separate session.

---

## 6. Files you'll touch (checklist)

```
Production/tools/storyboard-v2/src/components/BgTab.tsx                    [C1]
Production/tools/storyboard-v2/src/components/StoryboardTab.tsx            [C2a]
Production/tools/storyboard-v2/src/components/__tests__/BgTab.spec.tsx     [C1 NEW]
Production/tools/storyboard-v2/src/components/__tests__/StoryboardTab.spec.tsx  [C2a NEW]
Production/tools/storyboard-v2/e2e/storyboard-v59-bg-scope-sync.spec.ts    [C1 NEW]
Production/tools/storyboard-v2/e2e/storyboard-v59-display-order-empty.spec.ts   [C2a NEW]
Production/tools/storyboard-v2/e2e/storyboard-v59-production-map.spec.ts   [C5/C6 NEW or update]
Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx         [C6]
Production/tools/storyboard-v2/src/app.css                                 [C7]
Production/tools/production_server.py                                       [C2b, C5, C6]
Production/tools/tests/test_production_state_mutate_video_state.py         [C2b NEW]
Production/tools/tests/test_production_map_endpoint.py                      [C5/C6 NEW or update]
Production/scripts/clean_orphan_beats_v3.py                                 [C2c NEW]
Production/scripts/clean_orphan_beats_v3_test.py (or equivalent)            [C2c NEW]
Production/scripts/populate_prod_modules_from_gameplay_scope.py             [C5 EXTEND]
Production/scripts/deploy_storyboard_v59.sh                                 [C8 NEW]
prod_locked_decisions Directus rows                                          [LD x5]
```

---

## 7. Reference docs (Dropbox tree)

- **Spec (authoritative):** `Production/docs/STORYBOARD_V59_POST_REDEPLOY_BUG_FIX_SPEC_v2.md`
- Picker spec (boundary cross-check): `Production/docs/STORYBOARD_V59_VIDEO_ROLE_PICKER_SPEC_v1.md`
- Lessons learned: `Production/docs/STORYBOARD_V59_LESSONS_LEARNED_v1.md`
- Architecture overview: `Production/docs/STORYBOARD_V59_ARCHITECTURE_OVERVIEW_v1.md`
- Testing/debugging entry-point handoff (sibling): `Production/docs/STORYBOARD_V59_TESTING_DEBUGGING_HANDOFF.md` (prod_reference_docs id=198)
- Deferred coverage backlog: `Production/docs/STORYBOARD_V59_DEFERRED_RETROACTIVE_COVERAGE_BACKLOG.md`
- Discipline standards source: `.claude/skills/zero-error-qa/SKILL.md` lines 32-110

---

## 8. Branch hygiene

- `claude/post-redeploy-bug-triage` — cut from `main`. ALL work in this session lives here.
- `claude/video-role-picker` — PARKED. Do NOT continue. Re-spec was folded into v2 of the post-redeploy spec.
- After PR merge: redeploy via the new `deploy_storyboard_v59.sh` per LD `STORYBOARD_DEPLOY_PROCESS_V1`.

---

## 9. If you hit something the spec didn't anticipate

1. STOP. Don't improvise into the existing commits.
2. Write a brief note in `Production/docs/STORYBOARD_V59_POST_REDEPLOY_BUG_FIX_SPEC_v2_DELTAS.md` (NEW file).
3. Surface to Kim with: (a) what you found, (b) what the spec says, (c) recommended path forward.
4. Wait for direction. Do NOT mark the session complete with un-noted improvisations.

This protects the spec's status as the canonical execution doc and keeps the audit trail clean per DS-7.

---

**END HANDOFF**

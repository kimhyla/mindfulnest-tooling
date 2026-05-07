# Storyboard v59 — Post-Redeploy Bug-Fix Spec v2

**Date:** 2026-05-05
**Branch (target):** `claude/post-redeploy-bug-triage` (cut fresh; `claude/video-role-picker` parked)
**Source of bugs:** Browser smoke after redeploying fresh local build to Dropbox/Production/Event_<N>/storyboard_v59_prod.html
**Discipline:** zero-error-qa DS-1..DS-12; tooling-repo two-tree boundary (LD-505); tdd contract-first
**Cursor review:** v1 → REJECT-with-changes (4 must-fix); v2 folds all four. Re-reviewed v2 → APPROVE 2026-05-05 (single-pass: all four fold-checks CONFIRMED; stale-cache check passed; verdict in-conversation, not appended below to keep this doc as the spec, not its review chain).

## v2 changelog (vs v1)

- §3.3 **Part 2 LOCKED** — Production Map role-status columns are DERIVED from on-disk artifacts. NO prod_modules schema expansion for role status. Aligns with picker-spec R3 boundary (winner per Cursor R8).
- §3.3 Part 1 (event_dir mapping) remains Option A (Directus schema add for `event_number`/`event_dir`) — decision INDEPENDENT of role-status path.
- §2.3 Part 3 (cleanup script) gains 3 safety guards: (a) per-file pre-image timestamped backup before any `--apply`, (b) `--event <event_id>` scoped mode (first live run targets ONLY Event_2 before global sweep), (c) per-event `prod_activity_log` row summarizing removed beat_ids + count.
- §6.2 LD list canonicalized: 3 HARD + 2 SOFT, no conditional fork:
  - HARD `DISPLAY_ORDER_STRICT_V1`
  - HARD `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1` (renamed from PER_MODULE wording)
  - HARD `PRODUCTION_MAP_ROLE_STATUS_DERIVED_V1` (deterministic; no fork)
  - SOFT `BG_TAB_SCOPE_SYNC_V1`
  - SOFT `STORYBOARD_DEPLOY_PROCESS_V1`
- §6.1 atomic plan re-grouped: C1 (Bug A solo) → **C2-bundle** (Bug B renderer + server prune + cleanup script + tests) → C5 (Bug C event_dir mapping) → C6 (Bug C role-status derived columns) → C7 (Bug D CSS) → C8 (Bug E LD + deploy script).
- §1.5 Open question explicitly resolved: defer server-side `bg_session_state` scoping to follow-up. Logged as monitor item; HARD-promote if cross-scope collision observed during verification.
- §8 open questions for Kim RESOLVED 2026-05-05: (1) cleanup script auto-deletes orphan with audit + payload backup; (2) Production Map has no "active" filter — no Bug C masking; (3) deploy_storyboard_v59.sh is a single chained command (build → cp loop over Event_*/ → open browser).

---

## 0. Status of the three bugs (unchanged from v1)

| ID    | Symptom                                                                                                                                                  | Severity | Root cause confirmed via                                                                                          | Fix surface                            |
|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------|----------|-------------------------------------------------------------------------------------------------------------------|----------------------------------------|
| Bug A | Beat Generator "Segment" dropdown stays on prior event/phase after Event/Video scope changes via VideoSelector                                           | HARD     | `BgTab.tsx` useEffect depends on `arcNumber` only; not on `activeScope`/`activeVideoRole`                          | client (BgTab.tsx)                     |
| Bug B | Event_2 intro storyboard renders an unauthored beat (`beat_04`, "MindfulNest! Well don't you know? ...") even though `display_order = []`                | HARD     | `StoryboardTab.tsx:765-775`: when `display_order` is `[]`, falls through to `Object.entries(beats)` (renders all) | client (StoryboardTab.tsx) + data hygiene |
| Bug C | Production Map shows uniform Role=intro and identical counts (Phase A=14, Phase B=1, Storyboard=36, Final concat=0) for ALL M1..M59 rows                 | HARD     | `production_server.py:8429-8472`: `edir = event_dirs[0]` always — every row globs Event_1 only                    | server (production_server.py)          |

Plus two SOFT items folded in:
- **Bug D (CSS):** `.mn-video-selector` has no styling; selector renders raw next to `.mn-event-selector` and looks ugly
- **Bug E (process LD):** No documented "redeploy SPA to Dropbox tree" step; code-merge ≠ user-visible release. Already cost ~1 day of misdiagnosis this weekend.

---

## 1. Bug A — Beat Generator "Segment" dropdown sticky across scope changes

### 1.1 Reproduction

1. Load app at Event_1 / intro (default scope).
2. Switch to Beat Generator tab — observe Segment dropdown shows `event 1 pre — Intro`.
3. Switch event to Event_2 via EventSelector OR switch video via VideoSelector to `resolution`.
4. Switch back to Beat Generator tab.
5. **Observed:** Segment dropdown still shows `event 1 pre — Intro` (or whatever was selected pre-change). Editing/extracting beats here writes to the WRONG event.
6. **Expected:** Segment list re-fetches scoped to current event; default segment matches active scope.

### 1.2 Root cause

`Production/tools/storyboard-v2/src/components/BgTab.tsx`

```tsx
// Line 126-149 (current)
useEffect(() => {
  let cancelled = false;
  (async () => {
    setLoading(true);
    const segRes = await apiGet<BgSegmentsResponse>('bg_segments', { arc_number: String(arcNumber) });
    ...
    if (ctx) {
      setArcNumber(Number(ctx.arc_number) || arcNumber);
      setActiveSegment(`${ctx.event_id}|${ctx.phase}`);
    } else if (segs.length > 0) {
      setActiveSegment(`${segs[0].event_id}|${segs[0].phase}`);
    }
    ...
  })();
  return () => { cancelled = true; };
}, [arcNumber]);                       // <-- ONLY arcNumber; missing scope deps
```

Dependency array is `[arcNumber]`. When `activeScope` or `activeVideoRole` change, the effect does NOT re-run, so `activeSegment` keeps its stale value. The cross-event-edit risk is real because all `pathappPatch(activeScope.value, 'bg_*', { event_id, phase })` calls below pass `event_id` derived from `activeSegment`.

### 1.3 Fix (minimal diff)

```tsx
import { activeScope, activeVideoRole, scopeKey } from '../state/scope';
// ...

// Subscribe the load effect to scope changes too:
const scopeKeyVal = scopeKey(activeScope.value);
const videoRoleVal = activeVideoRole.value;

useEffect(() => {
  let cancelled = false;
  (async () => {
    setLoading(true);
    const segRes = await apiGet<BgSegmentsResponse>(
      'bg_segments', { arc_number: String(arcNumber) }
    );
    if (cancelled) return;
    const segs = segRes.data?.segments ?? [];
    setSegments(segs);

    const stateRes = await apiGet<BgSessionState>('bg_session_state');
    if (cancelled) return;
    const ctx = stateRes.data?.active_context;
    if (ctx) {
      setArcNumber(Number(ctx.arc_number) || arcNumber);
      setActiveSegment(`${ctx.event_id}|${ctx.phase}`);
    } else if (segs.length > 0) {
      setActiveSegment(`${segs[0].event_id}|${segs[0].phase}`);
    }
    setBeats(stateRes.data?.beats ?? []);
    setLoading(false);
  })();
  return () => { cancelled = true; };
}, [arcNumber, scopeKeyVal, videoRoleVal]);   // <-- add scope dependency
```

### 1.4 Test plan (DS-1 contract-first)

- **Unit:** `BgTab.spec.tsx` — mount with scope `M1E1/intro`, capture activeSegment; mutate `activeScope.value` to `M2E1/resolution`, assert effect re-fires and activeSegment resets to scoped value (use `vi.fn()` mocks for `apiGet`).
- **e2e:** `storyboard-v59-bg-scope-sync.spec.ts` — load Event_1, change to Event_2 via EventSelector, switch tab to Beat Generator, assert Segment dropdown reflects Event_2's segments; submit a `bg_extract_beats` and assert request body carries `event_id=2`.
- **Regression:** existing `bg-tab.spec.ts` tests unchanged (arc-number-only re-fetch path still works because dep array still includes arcNumber).

### 1.5 Server-side `bg_session_state` scoping — RESOLVED: defer

Per Cursor R1: this client-only fix is sufficient for the immediate bug. The server endpoint stores `active_context` once per server process, NOT per scope. Since Kim is single-user and runs a single server process, multi-tab/multi-event collision is unlikely in practice.

**Action:** Defer server re-architecture. **Monitor:** if any cross-scope collision is observed during verification (e.g., editing in one tab silently overwrites another's active context), HARD-promote and patch in a follow-up session. Logged as a watch item — no LD filed yet.

---

## 2. Bug B — Event_2 intro renders unauthored beat_04 (display_order fallthrough)

### 2.1 Reproduction

1. Load app at Event_2 / intro.
2. Storyboard tab shows 1 beat: `beat_04` "The MindfulNest! ... Well don't you know? ..."
3. Kim confirms she did NOT author this beat in v59. Likely arrived via:
   - Failed "Accept all beats from generator" attempt, or
   - Pre-v3-migration cross-event leak (Kim recalls "in the previous storyboard version, the first beat of event 2 intro video populated into the first beat of event 1")
4. Pre-migration backup `Production/Event_2/.backups/state/20260503T140831Z_pre_videos_migration.json` already contains `beats.beat_04` with that exact text — so it predates weekend work and survived migration.
5. Current v3 state at `Production/Event_2/production_state.json`:
   ```json
   "videos": {
     "intro": {
       "beats": { "beat_04": { "text": "The MindfulNest! ..." } },
       "display_order": []
     }
   }
   ```
   `display_order` is empty `[]` but the beat persists in `beats{}`.

### 2.2 Root cause

`Production/tools/storyboard-v2/src/components/StoryboardTab.tsx:760-781`

```tsx
const beatList = useMemo(() => {
  if (!state) return [];
  const role = activeTargetVideo.value;
  const partition = state.videos?.[role];
  if (partition?.beats && Object.keys(partition.beats).length > 0) {
    const order = partition.display_order ?? [];
    if (order.length > 0) {
      return order
        .filter((bid) => partition.beats?.[bid])
        .map((beat_id) => ({ beat_id, ...partition.beats![beat_id] }));
    }
    // ⚠️ FALLTHROUGH: when display_order is [], renders ALL beats.
    return Object.entries(partition.beats)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([beat_id, b]) => ({ beat_id, ...b }));
  }
  ...
});
```

`display_order = []` falls through to render-all-keys-in-`beats`. Two semantically distinct situations collapse together:
- "I have never set display_order on this partition" (pre-migration legacy) — rendering all is the legacy fallback we want
- "I have explicitly emptied display_order; only `beats[]` rows exist as orphans/cache" (current Event_2 state) — rendering should show 0 beats

### 2.3 Fix (minimal diff, three-part — all ship together per Cursor R2)

**Part 1 — client renderer (StoryboardTab.tsx):** Distinguish "absent" vs "explicitly empty":

```tsx
if (partition?.beats && Object.keys(partition.beats).length > 0) {
  // Honor display_order strictly when it's present (even if []).
  // display_order == [] means "no beats to render"; only fall through to
  // Object.entries() when display_order is genuinely missing (undefined).
  if (partition.display_order !== undefined) {
    return partition.display_order
      .filter((bid) => partition.beats?.[bid])
      .map((beat_id) => ({ beat_id, ...partition.beats![beat_id] }));
  }
  // Legacy pre-display_order partitions: sorted by beat_id.
  return Object.entries(partition.beats)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([beat_id, b]) => ({ beat_id, ...b }));
}
```

This preserves backward compat (legacy state shapes with no `display_order` key keep working) while honoring explicit `[]` as "no beats".

**Part 2 — server hygiene (production_server.py):** When `display_order` is mutated, prune `beats{}` of any keys not in `display_order`. Prevents orphan accumulation in storage. **LOCKED ship-with-fix per Cursor R2** — orphan accumulation is the same root cause.

Implementation: in the mutator path that writes `display_order`, add a final step that drops `partition.beats[bid]` for any `bid` not in the new `display_order`. Atomic via existing `mutate_video_state` channel; respects the mutation channel invariant LD-519.

**Part 3 — one-shot data cleanup script with three new safety guards (per Cursor R3):**

`Production/scripts/clean_orphan_beats_v3.py`:

```
USAGE
  python3 clean_orphan_beats_v3.py [--apply] [--event <event_id>]
                                   [--milestone <milestone_id>] [--all]

DEFAULT: dry-run; prints orphan summary without mutating.

SAFETY GUARDS (Cursor R3):
  1. PRE-IMAGE BACKUP — before any --apply, copy production_state.json to
     <event_dir>/.backups/state/preimage_<UTC-timestamp>_clean_orphan_beats.json
     Path returned in stdout for manual rollback.
  2. SCOPED MODE — --event <id> or --milestone <id> required for first live run.
     --all is permitted only after at least one scoped run has been verified.
     Default for the Event_2 cleanup: `--apply --event 2`.
  3. AUDIT LOG — each mutated event/milestone gets ONE prod_activity_log row:
     {
       "summary": "clean_orphan_beats_v3 evicted N beat(s)",
       "event_id": "<id>", "video_role": "<role>",
       "removed_beat_ids": ["beat_04", ...],
       "preimage_backup_path": "<path>",
       "applied_at": "<ISO8601>",
       "tags": ["beat_cleanup", "DISPLAY_ORDER_STRICT_V1"]
     }

LOGIC:
  - Walk Production/Event_*/production_state.json AND
    Production/Milestones/*/state.json
  - For each videos.<role> partition where display_order is a present list:
    drop beats[bid] for any bid not in display_order
  - Skip partitions where display_order is undefined (legacy); never auto-mutate those
  - Atomic write through ProductionState.mutate_video_state when --apply
```

### 2.4 Test plan (DS-1 + DS-7)

- **Unit:** `StoryboardTab.spec.tsx` — three cases: `display_order = ['beat_01','beat_02']` → 2 beats; `display_order = []` → 0 beats; `display_order = undefined` (legacy) → all beats sorted.
- **e2e:** `storyboard-v59-display-order-empty.spec.ts` — fixture with `beats: { beat_04: ... }, display_order: []` → assert renders "No beats in this event yet."
- **DS-7 retroactive:** Add unit fixture loading actual current `Production/Event_2/production_state.json` shape; assert beat_04 is NOT rendered. (Per "verify against actual code/state" feedback memory.)
- **Cleanup script tests:**
  - **Dry-run golden:** fixture state with 1 orphan; assert correct stdout summary, no mutation
  - **`--apply --event` golden:** fixture state with 1 orphan in Event_2; assert orphan removed, display_order untouched, pre-image backup file written, prod_activity_log row written
  - **`--all` rejection without prior scoped run:** assert script refuses `--all --apply` until at least one scoped `--apply` has been run (state-tracked via marker file or activity-log lookup)
  - **Legacy-skip:** fixture with `display_order: undefined`; assert nothing mutated
- **Server prune unit:** `test_production_state_mutate_video_state.py` — set display_order to `['beat_01']` while beats has `beat_01` + `beat_99`; assert beat_99 dropped post-mutation.

### 2.5 Severity rationale

HARD — silently surfaces stale/leaked beats to the user; breaks "what you see is what's authored" expectation; can cascade if Kim hits "Accept all beats into storyboard" while orphans exist.

---

## 3. Bug C — Production Map: every row shows Event_1 data

### 3.1 Reproduction

1. Load Production Map tab.
2. **Observed:** All rows M1..M59 show:
   - Role = `intro` (uniform)
   - Phase A = 14 / Phase B = 1 / Storyboard = 36 / Final concat = 0 (uniform)
3. **Expected:** Each module's row reflects ITS event_dir's artifacts AND per-role status DERIVED from on-disk artifacts.

### 3.2 Root cause

`Production/tools/production_server.py:8429-8472` (`_handle_production_map`):

```python
for m in modules or []:
    event_dirs = sorted(
        p for p in production_root.iterdir()
        if p.is_dir() and p.name.startswith("Event_") and "_" not in p.name[len("Event_"):]
    )
    edir = event_dirs[0] if event_dirs else None  # ⚠️ always Event_1
    ...
    if edir:
        phase_a = list(edir.glob("phase_a_stitched_*.mp4"))         # always Event_1's
        phase_b = list(edir.glob("phase_b_lipsync_*.mp4"))           # always Event_1's
        intro_or_resolution = list(edir.glob("storyboard_v*_prod.html"))
        final_concat = list(edir.glob(f"M{m.get('m_number')}_*_final.mp4"))
        ...
```

The comment in the file says: `"Take the first event dir (Event_1) as the canonical for now; multi-event would map M-number → event in S4."` — known incomplete shortcut. S4 work was never done.

The `Role` column rendering shows `m.get('video_role')` which is a Directus `prod_modules` field. Per Cursor R5/R8, this column is **REPLACED** in v2 by per-role status columns DERIVED from on-disk artifacts. The Directus `video_role` field is NOT used for role status (it remains as intent metadata only).

### 3.3 Fix (server, two parts — INDEPENDENT decisions)

**Part 1 — M-number → event_dir mapping (Cursor R4: Option A LOCKED)**

Add nullable `event_number` (integer) field to `prod_modules` Directus collection. Server reads `event_number` and resolves `Production/Event_<event_number>/`. Steps:

1. Add nullable `event_number` (integer) to prod_modules schema.
2. EXTEND existing `Production/scripts/populate_prod_modules_from_gameplay_scope.py` (already canonical for `creature_name` per Production Map header note) to ALSO populate `event_number` from the same Storyline_v3 / GAMEPLAY_SCOPE_v3.md source. Single canonical pipeline; do NOT create a parallel backfill script.
3. Dry-run diff report: current vs proposed mapping per `m_number`; Kim signs off.
4. Apply backfill; verify all rows populated.
5. Update `_handle_production_map` to read `event_number`, resolve `event_dir`, fallback+warn only if null (do NOT silently use Event_1).
6. Add CI/test validation that fails if any `prod_modules` row has null `event_number`.

LD: **HARD `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1`** — every row globs ITS OWN event_dir, resolved from `prod_modules.event_number`; Event_1 fallback is removed.

**Part 2 — Per-role status columns DERIVED from on-disk artifacts (Cursor R5 + R8 LOCKED)**

**Picker-spec R3 boundary wins** (per Cursor R8): role-status rendering uses on-disk artifact presence; no `prod_modules` schema expansion for role status.

Replace the single `Role` column with TWO status columns alongside Phase A / Phase B / Final concat:

| M# | Creature | Phase A | Phase B | Intro status | Resolution status | Final concat |
|----|----------|---------|---------|--------------|--------------------|--------------|

Per-role status cell derivation, per event_dir:

- **Intro status:** scan `<edir>/intro/scene_intro_*.mp4` → ✅ (≥1) / ❌ (0) / ⏳ (state.json says intro partition exists but no mp4 yet)
- **Resolution status:** scan `<edir>/resolution/scene_resolution_*.mp4` → same status mapping
- Status cell payload: `{status, count, latest_filename}` (same shape as existing Phase A/B cells).

LD: **HARD `PRODUCTION_MAP_ROLE_STATUS_DERIVED_V1`** — per-role status columns derived from on-disk presence; `prod_modules.video_role` is intent-metadata only and is NOT consulted for the Production Map. Aligns with picker-spec R3.

### 3.4 Test plan

- **Unit (Python):** `test_production_map_endpoint.py`:
  - Fixture with two event_dirs (Event_1 + Event_2) and `prod_modules` rows with distinct `event_number`s; assert each row's `event_dir` matches its `event_number`.
  - Fixture where Event_1 has `intro/scene_intro_*.mp4` but no `resolution/`; Event_2 has both. Assert Intro status ✅ for Event_1's M; Resolution ❌. Assert both ✅ for Event_2's M.
  - Fixture where `prod_modules.event_number` is null; assert response includes warning marker (do not silently fall back to Event_1).
- **e2e:** `storyboard-v59-production-map.spec.ts` — load map, assert at least 2 distinct values in `event_dir`; assert presence of both Intro and Resolution status columns; assert no single `Role` column.
- **DS-7 retroactive:** Run against current Directus `prod_modules` data set after backfill; assert no null `event_number`.

### 3.5 Severity rationale

HARD — Production Map is currently misleading. Kim flagged it explicitly: "production map still seems to think it knows the future... randomly goes thru 15 modules." Trust in the dashboard is broken; fixing the mapping AND the role-status derivation restores its purpose.

### 3.6 Cross-spec drift resolution (per Cursor R8)

**Drift identified by Cursor:** v1 of this spec leaned toward Directus schema expansion for role status, which contradicted picker-spec R3's locked boundary ("NO prod_modules schema migration; NO new Directus columns" for role-status rendering).

**v2 resolution — picker spec wins for role-status semantics:**
- Bug C Part 1 (event_dir mapping) IS a Directus schema add (`event_number`), but this is OUTSIDE the role-status path — it's pure module-to-event resolution. Independent decision; not in conflict with picker spec.
- Bug C Part 2 (role-status columns) is fully derived from on-disk artifacts — no schema expansion. Conforms to picker-spec R3.
- LD `PRODUCTION_MAP_ROLE_STATUS_DERIVED_V1` is HARD and deterministic; the v1 SOFT conditional fork is REMOVED.

**Implementation rule for downstream sessions:** when touching Production Map, role-status columns are DERIVED-FROM-DISK ONLY. Do not introduce a second source of truth for role status.

---

## 4. Bug D — CSS for `.mn-video-selector` (cosmetic)

### 4.1 Symptom

The video selector renders functional but unstyled, sitting raw next to the styled `.mn-event-selector`. Mismatched font/spacing.

### 4.2 Fix

`Production/tools/storyboard-v2/src/app.css` — add sibling rules mirroring `.mn-event-selector`:

```css
.mn-video-selector {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 12px;
}
.mn-video-selector-label {
  color: var(--text-dim);
  font-size: 11px;
  font-family: var(--mono);
}
.mn-video-select {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-family: inherit;
}
```

Note: The select element already has class `mn-video-select` per VideoSelector.tsx:161; just need the rule. Severity SOFT.

---

## 5. Bug E — STORYBOARD_DEPLOY_PROCESS_V1 LD (process gap)

### 5.1 Symptom

Server reads from Dropbox tree's `Production/Event_<N>/storyboard_v59_prod.html`. Code merges to tooling repo do NOT update that file. Result: Kim ran on a May 3 build for two days post-merge while the new VideoSelector + ProjectSelector + Beat Gen plumbing landed in code.

### 5.2 LD (proposed, SOFT)

**STORYBOARD_DEPLOY_PROCESS_V1 — Local SPA build must be deployed to Dropbox tree before browser smoke.**

Decision text (draft):

> After any merge that touches `Production/tools/storyboard-v2/src/`, the developer MUST:
>
> 1. `cd Production/tools/storyboard-v2 && npm run build`
> 2. `cp dist/index.html "<Dropbox>/Production/Event_1/storyboard_v59_prod.html"`
> 3. Repeat for every active `Event_<N>/` directory (currently Event_1, Event_2)
> 4. Sha256 the destination and verify size > 100 KB (post-VideoSelector baseline ~182 KB)
> 5. Commit the new sha256 sidecar (`storyboard_v59_prod.html.sha256`) to the Dropbox tree
>
> A `Production/scripts/deploy_storyboard_v59.sh` wrapper automates steps 1-5 plus opens the browser to `http://localhost:5111/` for smoke. Per Kim 2026-05-05: single chained command preferred. See §8 question 3 for the script body. Until the script ships, the manual checklist is mandatory before declaring a merge "shipped" or running browser smoke.
>
> Browser smoke that fails BEFORE this step is invalid — debug only AFTER deploy is verified.

**Severity:** SOFT (process)
**Scope:** storyboard_v59
**Enforcement:** documentation; optional pre-commit grep CI gate.

### 5.3 Optional Phase 2 — auto-deploy on merge

GitHub Action that runs `npm run build` and pushes `dist/index.html` to a Dropbox release path; or a local pre-push hook. Defer to a separate session.

---

## 6. Atomic execution plan (v2 re-grouped per Cursor R7)

### 6.1 Order (sequential commits, all on `claude/post-redeploy-bug-triage`)

1. **C1** — Bug A fix (BgTab.tsx dep array) + unit + e2e
   *Solo commit — bisect clarity for any regressions in BgTab segment-context flow.*

2. **C2-bundle (Bug B remediation, all-in-one)** — three parts in ONE commit:
   - **C2a** Renderer fix (StoryboardTab.tsx `display_order !== undefined` distinction) + unit (3 cases) + e2e + DS-7 retroactive Event_2 fixture
   - **C2b** Server prune in `mutate_video_state` (drop orphan keys when display_order mutates) + Python unit
   - **C2c** Cleanup script `Production/scripts/clean_orphan_beats_v3.py` + 4 golden tests (dry-run, scoped --apply, --all rejection, legacy-skip)

   *Bundled per Cursor R7: same root cause, reviewing together reduces partial-fix risk. After this commit lands, run `clean_orphan_beats_v3.py --apply --event 2` to evict the orphan beat_04 (audit row will reference the LD).*

3. **C5** — Bug C Part 1: event_dir mapping (Directus `event_number` schema add + backfill script + `_handle_production_map` rewire to read it + Python unit + e2e)
   *Solo commit — schema migration + server endpoint change.*

4. **C6** — Bug C Part 2: per-role status columns DERIVED from on-disk (replace single Role column with Intro + Resolution status columns; client `ProductionMapTab.tsx` updates `SEGMENTS` constant; server `_handle_production_map` adds intro/resolution glob + status derivation) + Python unit + e2e
   *Solo commit — UX shape change worth bisecting independently.*

5. **C7** — Bug D CSS for `.mn-video-selector` + visual smoke

6. **C8** — Bug E LD `STORYBOARD_DEPLOY_PROCESS_V1` written to `prod_locked_decisions` (Directus); `Production/scripts/deploy_storyboard_v59.sh` wrapper (Phase 2 GitHub Action deferred)

After C8: `npm run build` + redeploy to Dropbox tree per C8's own LD, browser smoke at `http://localhost:5111/`, run `clean_orphan_beats_v3.py --apply --event 2` (if not already done after C2-bundle), mn-context SAVE.

### 6.2 LDs to file (canonicalized per Cursor R6)

- **HARD `DISPLAY_ORDER_STRICT_V1`** — empty `display_order` means render zero beats; only `undefined` falls through to legacy sorted-keys path. Server prune ships with it.
- **HARD `PRODUCTION_MAP_EVENT_DIR_MAPPING_V1`** — every row resolves event_dir from `prod_modules.event_number`; Event_1 fallback removed; null `event_number` returns warning marker, never silent default.
- **HARD `PRODUCTION_MAP_ROLE_STATUS_DERIVED_V1`** — per-role status columns derived from on-disk artifact presence; `prod_modules.video_role` is intent metadata only, NOT consulted for Production Map. Aligns with picker-spec R3.
- **SOFT `BG_TAB_SCOPE_SYNC_V1`** — BgTab segment context re-syncs on `activeScope` OR `activeVideoRole` change.
- **SOFT `STORYBOARD_DEPLOY_PROCESS_V1`** — local build must be redeployed to Dropbox tree post-merge (see §5.2).

### 6.3 Tests added (gross count target)

- 5 unit (BgTab dep, StoryboardTab three cases, server prune helper, production_map event_dir resolve, production_map role-status derive)
- 4 e2e (bg-scope-sync, display-order-empty, production-map-multi-event, production-map-per-role-columns)
- 1 retroactive (DS-7) using actual Event_2 state fixture
- 4 cleanup-script goldens (dry-run, --apply --event, --all rejection, legacy-skip)

= ~14 tests, brings v59 e2e count from 91 → ~99 e2e (matching original projection) plus ~6 new unit/integration tests.

### 6.4 Discipline-standards alignment (per .claude/skills/zero-error-qa/SKILL.md)

- **DS-1 Contract-first:** every fix has unit + e2e drafted BEFORE patch
- **DS-2 Boundary:** scope-key auto-injection still enforced; BgTab fix relies on existing scope plumbing, doesn't bypass it; cleanup script writes through existing mutation channel only
- **DS-7 Retroactive:** real Event_2 state file shipped as fixture; current Directus `prod_modules` snapshot used in DS-7 verification of event_number backfill
- **DS-12 Severity:** every LD tagged HARD/SOFT explicitly above; no conditional forks

---

## 7. Cursor v1 review resolution table

| R-row | v1 default     | Cursor decision           | v2 resolution                                                              |
|-------|----------------|---------------------------|----------------------------------------------------------------------------|
| R1    | defer          | defer                     | §1.5 explicit defer + monitor                                              |
| R2    | ship-with-fix  | ship-with-fix             | §2.3 Part 2 ships with C2-bundle                                           |
| R3    | approve-as-spec'd | additional-safeguards-required | §2.3 Part 3 adds pre-image backup, --event scoped mode, prod_activity_log row |
| R4    | Option A       | Option-A-schema           | §3.3 Part 1 locked Option A with 6-step migration outline                  |
| R5    | (open)         | per-role-columns          | §3.3 Part 2 locked per-role columns derived from disk                      |
| R6    | (open)         | rename                    | §6.2 final LD list with renames; HARD `PRODUCTION_MAP_ROLE_STATUS_DERIVED_V1` |
| R7    | (open)         | bundle-C2-C3-C4           | §6.1 C2-bundle; C1, C5, C6 each solo                                       |
| R8    | no-drift hoped | drift-found, picker wins  | §3.6 cross-spec drift resolution stated inline; picker spec wins for role-status |

**Cursor verdict v1:** REJECT-with-changes. Four must-fix items: (1) align Bug C with picker-spec boundary, (2) cleanup-script safety guards, (3) canonicalize LD naming/severity, (4) resolve cross-spec drift inline. **All four folded.**

**Re-review:** optional. v2 is structurally ready to drive terminal handoff. If Cursor wants a re-review pass, paste this v2 file + ask for a single-pass APPROVE / REJECT verdict only (no R1-R8 re-do needed).

---

## 8. Open questions for Kim — RESOLVED 2026-05-05

1. **Orphan beat_04 disposition:** Kim — "go ahead and delete the orphan beat in the cleanup script."
   → Cleanup script auto-deletes on `--apply`. Permanent forensic record preserved via:
   - Pre-image backup at `Event_2/.backups/state/preimage_<UTC>_clean_orphan_beats.json`
   - `prod_activity_log` row carrying `removed_beat_ids: ["beat_04"]` + the original beat text in a `removed_beat_payload` field (so the dialogue isn't lost if Kim ever wants to recover it)
   - LD `DISPLAY_ORDER_STRICT_V1` referenced in audit row tags

2. **"Active" filter on Production Map:** Kim — "i do not see any 'active' filter do you?"
   → Confirmed: no active filter present. Screenshot 2026-05-05 09:35 (M1=Tessa, M2=Luna, M3=Benson, M4=Ember, M5=Bork, M6=Bramble, M7-M15=TBD) shows ALL modules rendered with no filter UI. The page header note reads: "M7-M54 are V1 scope placeholders — author each by creating an Event. Once authored, run `populate_prod_modules_from_gameplay_scope.py` to update creature_name from the doc."

   **Implication for Bug C migration (§3.3 Part 1):** The mentioned script `populate_prod_modules_from_gameplay_scope.py` already establishes the gameplay-scope-doc → `prod_modules` pipeline. The `event_number` backfill in v2 §3.3 Part 1 step 2 should EXTEND that script (single canonical mapping source) rather than create a parallel one. Cursor R4 migration outline step 2 amends to: *"Extend `populate_prod_modules_from_gameplay_scope.py` to also populate `event_number` from the same Storyline source."*

3. **Single chained command for build + redeploy + smoke:** Kim — "single chained command i think? any reason not to?"
   → No structural reason not to. Build is ~2s, copy is instant, browser smoke needs Kim's eyeballs regardless. The deploy script `Production/scripts/deploy_storyboard_v59.sh` (§5.2 + C8) becomes:

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
   open "http://localhost:5111/"   # launches browser smoke phase
   ```

   Loops over every `Event_<N>/` automatically (no manual list maintenance). Fails fast (`set -euo pipefail`). The `pgrep` line auto-launches `production_server.py` on :5111 if it's not already running (logs to `/tmp/mn_server.log`, 2-second warm-up). Last line opens the browser. Kim runs `./deploy_storyboard_v59.sh` post-merge — one command, no checklist, no manual server start.

---

**END SPEC v2**
